"""
Extracts structural symbols (classes, functions/methods, imports) from source
files using language-aware parsing where we have it, and falls back to
whole-file treatment otherwise.

Only Python (via the stdlib `ast` module) is implemented for the MVP, per the
project's phased plan. To add a language later: implement a new `parse_*`
function returning the same symbol shape and register it in `PARSERS`.
"""
import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "websocket"}


@dataclass
class Symbol:
    type: str            # "class" | "function" | "method"
    name: str
    line_start: int
    line_end: int
    parent: Optional[str] = None   # enclosing class name, for methods
    calls: list = field(default_factory=list)   # names this symbol calls
    source: str = ""
    is_route: bool = False          # True if decorated as an API endpoint
    route_method: Optional[str] = None   # "get" | "post" | ...
    route_path: Optional[str] = None     # literal path string, if present


def _extract_route_info(node) -> tuple:
    """
    Looks at a function/method's decorators for an API-route pattern, e.g.
    @app.post("/complaints") or @router.get("/projects/{id}"). Works for
    any object name (app, router, blueprint, ...) since student projects
    name these differently -- we only match on the HTTP-method attribute.
    Returns (is_route, method, path) with method/path None if not a route.
    """
    for deco in getattr(node, "decorator_list", []):
        call = deco if isinstance(deco, ast.Call) else None
        func = call.func if call else deco
        if isinstance(func, ast.Attribute) and func.attr.lower() in ROUTE_METHODS:
            path = None
            if call and call.args and isinstance(call.args[0], ast.Constant):
                if isinstance(call.args[0].value, str):
                    path = call.args[0].value
            return True, func.attr.lower(), path
    return False, None, None


@dataclass
class ParsedFile:
    file_path: str
    language: str
    imports: list = field(default_factory=list)
    symbols: list = field(default_factory=list)
    parse_error: Optional[str] = None


def _end_lineno(node) -> int:
    return getattr(node, "end_lineno", node.lineno)


def _extract_calls(node) -> list:
    # Order matters here: this list is used to reconstruct the actual
    # sequence of operations for flow diagrams. ast.walk() is breadth-first,
    # not source order, so we collect (lineno, name) pairs and sort by line
    # number to recover the real top-to-bottom sequence, then dedupe while
    # keeping each name's first occurrence position.
    found = []
    # Walk each body statement separately (not the whole node) so we don't
    # pick up decorator calls like @router.post("/ask") as if they were
    # calls made inside the function.
    for stmt in node.body:
        for child in ast.walk(stmt):
            if isinstance(child, ast.Call):
                func = child.func
                name = None
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name:
                    found.append((getattr(child, "lineno", 0), name))
    found.sort(key=lambda t: t[0])

    calls = []
    seen = set()
    for _, name in found:
        if name not in seen:
            seen.add(name)
            calls.append(name)
    return calls


def parse_python(file_path: Path, rel_path: str) -> ParsedFile:
    source = file_path.read_text(errors="ignore")
    parsed = ParsedFile(file_path=rel_path, language="python")

    try:
        tree = ast.parse(source, filename=rel_path)
    except SyntaxError as e:
        parsed.parse_error = f"SyntaxError: {e}"
        return parsed

    lines = source.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                parsed.imports.extend(a.name for a in node.names)
            else:
                module = node.module or ""
                parsed.imports.extend(f"{module}.{a.name}" if module else a.name for a in node.names)

    # Top-level classes and functions (module.body), plus methods within classes.
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            start, end = node.lineno, _end_lineno(node)
            parsed.symbols.append(Symbol(
                type="class", name=node.name, line_start=start, line_end=end,
                source="\n".join(lines[start - 1:end]),
            ))
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    cstart, cend = child.lineno, _end_lineno(child)
                    is_route, route_method, route_path = _extract_route_info(child)
                    parsed.symbols.append(Symbol(
                        type="method", name=child.name, parent=node.name,
                        line_start=cstart, line_end=cend,
                        calls=_extract_calls(child),
                        source="\n".join(lines[cstart - 1:cend]),
                        is_route=is_route, route_method=route_method, route_path=route_path,
                    ))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start, end = node.lineno, _end_lineno(node)
            is_route, route_method, route_path = _extract_route_info(node)
            parsed.symbols.append(Symbol(
                type="function", name=node.name, line_start=start, line_end=end,
                calls=_extract_calls(node),
                source="\n".join(lines[start - 1:end]),
                is_route=is_route, route_method=route_method, route_path=route_path,
            ))

    return parsed


PARSERS = {
    ".py": parse_python,
}


def parse_file(file_path: Path, rel_path: str) -> Optional[ParsedFile]:
    parser = PARSERS.get(file_path.suffix.lower())
    if parser is None:
        return None
    return parser(file_path, rel_path)
