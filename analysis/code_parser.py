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


@dataclass
class Symbol:
    type: str            # "class" | "function" | "method"
    name: str
    line_start: int
    line_end: int
    parent: Optional[str] = None   # enclosing class name, for methods
    calls: list = field(default_factory=list)   # names this symbol calls
    source: str = ""


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
    calls = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                calls.append(func.id)
            elif isinstance(func, ast.Attribute):
                calls.append(func.attr)
    return sorted(set(calls))


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
                    parsed.symbols.append(Symbol(
                        type="method", name=child.name, parent=node.name,
                        line_start=cstart, line_end=cend,
                        calls=_extract_calls(child),
                        source="\n".join(lines[cstart - 1:cend]),
                    ))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start, end = node.lineno, _end_lineno(node)
            parsed.symbols.append(Symbol(
                type="function", name=node.name, line_start=start, line_end=end,
                calls=_extract_calls(node),
                source="\n".join(lines[start - 1:end]),
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
