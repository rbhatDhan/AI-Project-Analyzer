"""
Manages per-project workspace folders and the project registry. The
registry now lives in a real SQLite database (core/db.py + core/models.py)
instead of a single JSON file that got fully re-read/re-written on every
update -- same public functions as before, so nothing calling into this
module (api/projects.py, api/architecture.py, ingestion/pipeline.py) needs
to change.
"""
import uuid
from pathlib import Path
from typing import Any, Optional

from core.config import settings
from core.db import get_session, init_db
from core.models import ProjectRecord

init_db()


def create_project() -> str:
    project_id = uuid.uuid4().hex[:12]
    project_dir_path = Path(settings.WORKSPACE_DIR) / project_id
    (project_dir_path / "raw").mkdir(parents=True, exist_ok=True)
    (project_dir_path / "extracted").mkdir(parents=True, exist_ok=True)
    (project_dir_path / "index").mkdir(parents=True, exist_ok=True)

    session = get_session()
    try:
        record = ProjectRecord(project_id=project_id, status="created")
        session.add(record)
        session.commit()
    finally:
        session.close()
    return project_id


def project_dir(project_id: str) -> Path:
    return Path(settings.WORKSPACE_DIR) / project_id


def extracted_dir(project_id: str) -> Path:
    return project_dir(project_id) / "extracted"


def index_dir(project_id: str) -> Path:
    return project_dir(project_id) / "index"


def update_project(project_id: str, **fields: Any) -> dict:
    session = get_session()
    try:
        record = session.get(ProjectRecord, project_id)
        if record is None:
            raise KeyError(f"Unknown project_id: {project_id}")
        for key, value in fields.items():
            setattr(record, key, value)
        session.commit()
        session.refresh(record)
        return record.to_dict()
    finally:
        session.close()


def get_project(project_id: str) -> Optional[dict]:
    session = get_session()
    try:
        record = session.get(ProjectRecord, project_id)
        return record.to_dict() if record else None
    finally:
        session.close()


def list_projects() -> list:
    session = get_session()
    try:
        records = session.query(ProjectRecord).order_by(ProjectRecord.created_at.desc()).all()
        return [r.to_dict() for r in records]
    finally:
        session.close()
