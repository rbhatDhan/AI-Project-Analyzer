"""
Decides which extracted files are worth analyzing. Keeps the noisy stuff
(dependency trees, build output, VCS internals, binaries) out of the
pipeline entirely so we never waste embeddings or LLM context on them.
"""
from pathlib import Path

IGNORED_DIR_NAMES = {
    "node_modules", ".git", "__pycache__", "venv", ".venv", "dist", "build",
    "target", ".next", ".idea", ".vscode", "coverage", "vendor", "bin", "obj",
    ".pytest_cache", ".mypy_cache", "egg-info",
}

IGNORED_FILE_NAMES = {".env", ".DS_Store"}

IGNORED_EXTENSIONS = {
    # binaries / media
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".mp4", ".mov", ".avi", ".mp3", ".wav",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".exe", ".dll", ".so", ".dylib", ".class", ".jar", ".pyc", ".o",
    ".woff", ".woff2", ".ttf", ".eot",
    ".pdf", ".lock",
}

# These files matter for dependency analysis even though they're not "code".
ALWAYS_KEEP_NAMES = {
    "package.json", "requirements.txt", "pyproject.toml", "pom.xml",
    "build.gradle", "cargo.toml", "go.mod", "dockerfile", "docker-compose.yml",
}

CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".rb", ".php",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".html", ".css", ".sql", ".json",
    ".yaml", ".yml", ".md",
}


def is_ignored(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    if any(part in IGNORED_DIR_NAMES for part in rel_parts[:-1]):
        return True
    if path.name in IGNORED_FILE_NAMES:
        return True
    if path.name.lower() in ALWAYS_KEEP_NAMES:
        return False
    if path.suffix.lower() in IGNORED_EXTENSIONS:
        return True
    return False


def collect_relevant_files(root: Path) -> list:
    """Walks the extracted project and returns paths worth analyzing."""
    relevant = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if is_ignored(path, root):
            continue
        relevant.append(path)
    return relevant
