"""
Traces a real execution flow starting from each detected API route (see
analysis/code_parser.py's is_route/route_method/route_path), following the
functions it calls -- and the functions those call, recursively -- to build
a step-by-step "what actually happens" sequence per endpoint.

This is the piece that turns the architecture diagram from "here's the tech
stack" into "here's how a request flows through the code", which is what a
student needs to explain their project in a placement interview.

Everything here works off analysis["symbols"], the flat list of
{file_path, type, name, parent, calls, is_route, route_method, route_path}
dicts populated by ingestion/pipeline.py. Matching a call name to a real
function is done by name only (no type inference), which is a deliberate
simplification for the MVP -- see _build_symbol_index.
"""

MAX_DEPTH = 5
MAX_STEPS_PER_FLOW = 14

# Calls that don't represent a meaningful step in the story (Python
# builtins, plain getters/formatters, logging, response helpers). Filtering
# these out keeps the flow readable instead of cluttered with noise.
NOISE_CALLS = {
    "str", "int", "float", "list", "dict", "set", "tuple", "len", "sorted",
    "range", "print", "isinstance", "getattr", "setattr", "hasattr", "super",
    "format", "join", "split", "strip", "lower", "upper", "append", "update",
    "get", "keys", "values", "items", "enumerate", "zip", "map", "filter",
    "open", "round", "sum", "min", "max", "any", "all", "next", "iter",
    "dataclass", "field", "Path",
}

# Keyword -> (category label, icon-ish short tag) used to classify calls
# that don't match a known project function. Order matters: first match
# wins, so more specific categories are listed before generic ones.
LEAF_CATEGORY_KEYWORDS = [
    (("commit", "session", "query", "add_all", "flush", "execute", "select",
      "insert", "delete_stmt", "save", "find", "aggregate"), "Database"),
    (("post", "requests", "httpx", "fetch", "urlopen"), "External API"),
    (("send_mail", "sendmail", "notify", "send_notification", "email"), "Notification"),
    (("verify", "authenticate", "check_password", "decode_token", "jwt"), "Auth Check"),
    (("dump", "load", "read_text", "write_text", "read_csv", "to_csv"), "File I/O"),
    (("embed", "encode", "predict", "generate_content"), "AI / ML Call"),
]


def _label(sym: dict) -> str:
    return f"{sym['parent']}.{sym['name']}" if sym.get("parent") else sym["name"]


def _build_symbol_index(symbols: list) -> dict:
    """
    name -> list of symbol dicts sharing that name. Multiple hits (same
    function name in different files) are possible in real projects; we
    keep them all but only follow the first when tracing, which is a
    simplification worth knowing about rather than silently guessing.
    """
    index: dict = {}
    for sym in symbols:
        if sym["type"] in ("function", "method"):
            index.setdefault(sym["name"], []).append(sym)
    return index


def _classify_leaf(call_name: str) -> str:
    lowered = call_name.lower()
    for keywords, category in LEAF_CATEGORY_KEYWORDS:
        if any(k in lowered for k in keywords):
            return category
    return ""  # not classifiable -- caller decides whether to drop it


def _trace(symbol: dict, index: dict, visited: set, depth: int, steps: list) -> None:
    if depth > MAX_DEPTH or len(steps) >= MAX_STEPS_PER_FLOW:
        return

    for call_name in symbol.get("calls", []):
        if len(steps) >= MAX_STEPS_PER_FLOW:
            return
        if call_name in NOISE_CALLS:
            continue

        matches = index.get(call_name)
        if matches:
            target = matches[0]
            target_label = _label(target)
            if target_label in visited:
                continue  # avoid cycles (e.g. recursive helpers)
            steps.append({"kind": "call", "name": target_label, "file": target["file_path"]})
            _trace(target, index, visited, depth + 1, steps)
        else:
            category = _classify_leaf(call_name)
            if category:
                steps.append({"kind": "leaf", "name": call_name, "category": category})
            # else: unclassifiable external/library call with no obvious
            # story value (e.g. a helper from an unparsed non-Python file)
            # -- silently skip rather than clutter the diagram.


def build_flows(analysis: dict) -> list:
    """
    Returns one flow per detected API route:
    {
        "name": "POST /complaints",
        "entry": "create_complaint",
        "file": "api/complaints.py",
        "steps": [{"kind": "call"|"leaf", "name": ..., ...}, ...],
    }
    Ordered by route_path/method for stable, predictable output.
    """
    symbols = analysis.get("symbols", [])
    if not symbols:
        return []

    index = _build_symbol_index(symbols)
    entry_points = [s for s in symbols if s.get("is_route")]
    entry_points.sort(key=lambda s: (s.get("route_path") or "", s.get("route_method") or ""))

    flows = []
    for entry in entry_points:
        steps: list = []
        visited: set = {_label(entry)}
        _trace(entry, index, visited, depth=1, steps=steps)
        method = (entry.get("route_method") or "call").upper()
        path = entry.get("route_path") or _label(entry)
        flows.append({
            "name": f"{method} {path}",
            "entry": _label(entry),
            "file": entry["file_path"],
            "steps": steps,
        })
    return flows
