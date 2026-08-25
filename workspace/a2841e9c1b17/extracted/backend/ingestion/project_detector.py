"""
Lightweight, dependency-free detection of languages, frameworks, and
manifest-declared dependencies. This is intentionally heuristic (extension
counts + manifest keyword matching) rather than a full build-system parse --
good enough to drive retrieval and diagram generation for the MVP.
"""
import json
import re
from collections import Counter
from pathlib import Path

EXT_TO_LANGUAGE = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
    ".c": "C", ".cpp": "C++", ".cs": "C#", ".html": "HTML",
    ".css": "CSS", ".sql": "SQL",
}

FRAMEWORK_MARKERS = {
    "react": "React", "next": "Next.js", "express": "Express",
    "fastapi": "FastAPI", "django": "Django", "flask": "Flask",
    "spring-boot": "Spring Boot", "@nestjs/core": "NestJS",
    "vue": "Vue.js", "angular": "Angular",
}

MANIFEST_HANDLERS = {
    "package.json": "npm",
    "requirements.txt": "pip",
    "pyproject.toml": "pip",
    "pom.xml": "maven",
    "build.gradle": "gradle",
    "cargo.toml": "cargo",
    "go.mod": "go modules",
}

# Maps an import's root module name -> (display label, category). Category
# drives which "lane" the library shows up in on the architecture diagram.
# This is checked against ACTUAL import statements (see
# detect_libraries_from_imports), not just manifest files -- many projects
# (like a Streamlit/OpenCV script with no requirements.txt) only reveal
# their stack this way.
LIBRARY_IMPORT_MARKERS = {
    # UI / web layer
    "streamlit": ("Streamlit", "ui"),
    "flask": ("Flask", "ui"),
    "fastapi": ("FastAPI", "ui"),
    "django": ("Django", "ui"),
    "gradio": ("Gradio", "ui"),
    "tkinter": ("Tkinter", "ui"),
    "kivy": ("Kivy", "ui"),
    # computer vision / ML
    "cv2": ("OpenCV", "cv"),
    "mediapipe": ("MediaPipe", "cv"),
    "PIL": ("Pillow", "cv"),
    "torch": ("PyTorch", "ml"),
    "tensorflow": ("TensorFlow", "ml"),
    "sklearn": ("scikit-learn", "ml"),
    "transformers": ("Transformers", "ml"),
    # data / viz / reporting
    "pandas": ("Pandas", "data"),
    "numpy": ("NumPy", "data"),
    "matplotlib": ("Matplotlib", "viz"),
    "seaborn": ("Seaborn", "viz"),
    "plotly": ("Plotly", "viz"),
    # storage
    "sqlalchemy": ("SQLAlchemy", "db"),
    "psycopg2": ("PostgreSQL", "db"),
    "pymongo": ("MongoDB", "db"),
    "sqlite3": ("SQLite", "db"),
    "redis": ("Redis", "db"),
    # external services
    "requests": ("External HTTP APIs", "api"),
    "httpx": ("External HTTP APIs", "api"),
    "boto3": ("AWS", "api"),
    "openai": ("OpenAI API", "api"),
    "google.generativeai": ("Gemini API", "api"),
}


def detect_languages(files: list, root: Path) -> dict:
    counts = Counter()
    for f in files:
        lang = EXT_TO_LANGUAGE.get(f.suffix.lower())
        if lang:
            counts[lang] += 1
    total = sum(counts.values()) or 1
    return {
        lang: {"files": n, "percent": round(n / total * 100, 1)}
        for lang, n in counts.most_common()
    }


def detect_structure(files: list, root: Path) -> list:
    """
    Top-level directories, used for the coarse project-structure view. If
    the whole project sits under a single wrapper directory (e.g. everything
    is inside `myproject/` with nothing at true top level), that one entry
    tells us nothing useful for a diagram -- so we descend one more level
    in that case to surface the real module folders.
    """
    top_level = set()
    for f in files:
        rel = f.relative_to(root)
        if len(rel.parts) > 1:
            top_level.add(rel.parts[0])

    if len(top_level) > 1:
        return sorted(top_level)

    deeper = set()
    for f in files:
        rel = f.relative_to(root)
        parts = rel.parts[:-1]
        if len(parts) >= 2:
            deeper.add("/".join(parts[:2]))
        elif len(parts) == 1:
            deeper.add(parts[0])
    return sorted(deeper) if deeper else sorted(top_level)


def _read_json_safe(path: Path) -> dict:
    try:
        return json.loads(path.read_text(errors="ignore"))
    except Exception:
        return {}


def detect_dependencies_and_frameworks(files: list) -> dict:
    dependencies = {}
    frameworks = set()

    for f in files:
        name = f.name.lower()
        if name not in MANIFEST_HANDLERS:
            continue

        pkg_manager = MANIFEST_HANDLERS[name]
        raw = f.read_text(errors="ignore")

        if name == "package.json":
            data = _read_json_safe(f)
            deps = {}
            deps.update(data.get("dependencies", {}))
            deps.update(data.get("devDependencies", {}))
            dependencies.setdefault(pkg_manager, {}).update(deps)
            for key, label in FRAMEWORK_MARKERS.items():
                if key in deps:
                    frameworks.add(label)

        elif name in ("requirements.txt",):
            deps = {}
            for line in raw.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                match = re.match(r"^([A-Za-z0-9_\-.]+)", line)
                if match:
                    deps[match.group(1)] = line
            dependencies.setdefault(pkg_manager, {}).update(deps)
            lowered = raw.lower()
            for key, label in FRAMEWORK_MARKERS.items():
                if key in lowered:
                    frameworks.add(label)

        else:
            # pom.xml / build.gradle / Cargo.toml / go.mod: store raw text,
            # detect frameworks via keyword search rather than full parsing.
            dependencies.setdefault(pkg_manager, {})["_raw_manifest"] = f.name
            lowered = raw.lower()
            for key, label in FRAMEWORK_MARKERS.items():
                if key in lowered:
                    frameworks.add(label)

    return {"dependencies": dependencies, "frameworks": sorted(frameworks)}


def detect_libraries_from_imports(all_imports: list) -> dict:
    """
    Groups detected libraries by category (ui / cv / ml / data / viz / db /
    api) based on real import statements collected across parsed files.
    Works even when no manifest file exists at all.
    """
    by_category: dict = {}
    for imp in all_imports:
        root_module = imp.split(".")[0]
        # also try full dotted prefix match for things like google.generativeai
        match = LIBRARY_IMPORT_MARKERS.get(imp) or LIBRARY_IMPORT_MARKERS.get(root_module)
        if match:
            label, category = match
            by_category.setdefault(category, set()).add(label)
    return {cat: sorted(labels) for cat, labels in by_category.items()}


def detect_project(files: list, root: Path, all_imports: list = None) -> dict:
    result = {
        "languages": detect_languages(files, root),
        "structure": detect_structure(files, root),
        **detect_dependencies_and_frameworks(files),
        "total_files_analyzed": len(files),
    }
    if all_imports:
        libraries = detect_libraries_from_imports(all_imports)
        result["libraries"] = libraries
        # Fold UI-layer libraries into "frameworks" too, so anything reading
        # that field (e.g. older callers) still sees Streamlit/Flask/etc.
        ui_labels = libraries.get("ui", [])
        result["frameworks"] = sorted(set(result["frameworks"]) | set(ui_labels))
    return result

