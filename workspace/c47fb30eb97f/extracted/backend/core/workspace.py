"""
Manages per-project workspace folders and a small JSON registry so we don't
re-analyze the same project on every request. This is deliberately simple
(a JSON file, not Postgres) for the MVP -- swap later without touching
callers, since everything goes through these functions.
"""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.config import settings

REGISTRY_FILE = "registry.json"


def _registry_path() -> Path:
    return Path(settings.WORKSPACE_DIR) / REGISTRY_FILE


def _load_registry() -> dict:
    path = _registry_path()
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return json.load(f)


def _save_registry(registry: dict) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(registry, f, indent=2, default=str)


def create_project() -> str:
    project_id = uuid.uuid4().hex[:12]
    project_dir = Path(settings.WORKSPACE_DIR) / project_id
    (project_dir / "raw").mkdir(parents=True, exist_ok=True)
    (project_dir / "extracted").mkdir(parents=True, exist_ok=True)
    (project_dir / "index").mkdir(parents=True, exist_ok=True)

    registry = _load_registry()
    registry[project_id] = {
        "project_id": project_id,
        "status": "created",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_registry(registry)
    return project_id


def project_dir(project_id: str) -> Path:
    return Path(settings.WORKSPACE_DIR) / project_id


def extracted_dir(project_id: str) -> Path:
    return project_dir(project_id) / "extracted"


def index_dir(project_id: str) -> Path:
    return project_dir(project_id) / "index"


def update_project(project_id: str, **fields: Any) -> dict:
    registry = _load_registry()
    if project_id not in registry:
        raise KeyError(f"Unknown project_id: {project_id}")
    registry[project_id].update(fields)
    registry[project_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_registry(registry)
    return registry[project_id]


def get_project(project_id: str) -> Optional[dict]:
    return _load_registry().get(project_id)


def list_projects() -> list:
    return list(_load_registry().values())
