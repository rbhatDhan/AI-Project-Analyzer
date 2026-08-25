"""
Generates a Mermaid diagram from the project's detected structure and
libraries (see ingestion/project_detector.py). Libraries are grouped into
categories (ui, cv, ml, data, viz, db, api) detected from actual import
statements, not just manifest files -- so projects with no package.json/
requirements.txt (common in small ML/CV scripts) still get a meaningful
diagram instead of a generic "User -> Backend API" fallback.

The diagram is built as a left-to-right pipeline reflecting how data
actually flows through these categories, since that matches how most
single-purpose scripts/apps (the common case for student/portfolio
projects) are structured, rather than a generic client-server tree.
"""

CATEGORY_ORDER = ["ui", "cv", "ml", "data", "viz", "db", "api"]
CATEGORY_LABELS = {
    "ui": "Interface",
    "cv": "Vision Processing",
    "ml": "ML Inference",
    "data": "Data Processing",
    "viz": "Visualization",
    "db": "Storage",
    "api": "External Services",
}


def _sanitize(label: str) -> str:
    return label.replace('"', "'")


def _node_id(prefix: str, index: int) -> str:
    return f"{prefix}{index}"


def generate_architecture_diagram(analysis: dict) -> str:
    languages = list(analysis.get("languages", {}).keys())
    structure = analysis.get("structure", [])
    frameworks = analysis.get("frameworks", [])
    libraries = analysis.get("libraries", {})

    lines = ["graph TD", '    User["User"]']
    prev_node = "User"

    have_any_library = any(libraries.get(cat) for cat in CATEGORY_ORDER)

    if have_any_library:
        # Build one node per detected category, in pipeline order, chaining
        # them together so the diagram reads as an actual data flow.
        for cat in CATEGORY_ORDER:
            labels = libraries.get(cat, [])
            if not labels:
                continue
            node_id = f"Cat_{cat}"
            title = CATEGORY_LABELS[cat]
            tools = ", ".join(labels[:3])
            lines.append(f'    {prev_node} --> {node_id}["{_sanitize(title)}<br/>({_sanitize(tools)})"]')
            prev_node = node_id
    else:
        # No recognizable libraries at all (unusual, but keep a sane
        # fallback) -- use whatever web framework the manifest detection
        # found, or a generic label.
        backend_fw = next((fw for fw in frameworks if fw not in ()), None)
        label = backend_fw or "Application"
        lines.append(f'    {prev_node} --> App["{_sanitize(label)}"]')
        prev_node = "App"

    # Attach a couple of real module/folder names as children of the last
    # pipeline stage, so the diagram still reflects actual project layout.
    for i, d in enumerate(structure[:5]):
        node_id = _node_id("Mod", i)
        short_label = d.split("/")[-1]
        lines.append(f'    {prev_node} --> {node_id}["{_sanitize(short_label)}/"]')

    lines.append(f'    %% Detected languages: {", ".join(languages) or "unknown"}')
    return "\n".join(lines)
