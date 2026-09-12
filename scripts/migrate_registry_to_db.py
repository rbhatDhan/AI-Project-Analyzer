"""
One-time migration: reads the old workspace/registry.json (if present) and
inserts every record into the new SQLite database, skipping any project_id
that already exists there. Safe to run more than once.

Usage (from the backend/ directory):
    python scripts/migrate_registry_to_db.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings
from core.db import get_session, init_db
from core.models import ProjectRecord

FIELDS = {
    "status", "original_filename", "chunk_count", "error",
    "extract_stats", "parse_errors", "analysis",
}


def main() -> None:
    registry_path = Path(settings.WORKSPACE_DIR) / "registry.json"
    if not registry_path.exists():
        print(f"No registry.json found at {registry_path} -- nothing to migrate.")
        return

    data = json.loads(registry_path.read_text())
    init_db()
    session = get_session()
    migrated, skipped = 0, 0
    try:
        for project_id, rec in data.items():
            if session.get(ProjectRecord, project_id) is not None:
                skipped += 1
                continue
            row = ProjectRecord(project_id=project_id)
            for key in FIELDS:
                if key in rec:
                    setattr(row, key, rec[key])
            session.add(row)
            migrated += 1
        session.commit()
    finally:
        session.close()

    print(f"Migrated {migrated} project(s), skipped {skipped} already present.")
    print(f"registry.json is left untouched at {registry_path} -- safe to delete once you've verified the DB.")


if __name__ == "__main__":
    main()
