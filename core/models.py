"""
ORM model for a single project's registry record. Mirrors the fields the
old registry.json dict used to carry (see git history of core/workspace.py)
so nothing downstream (api/projects.py, api/architecture.py,
ingestion/pipeline.py) has to change -- they all just get a dict back from
core/workspace.py's functions, same as before.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectRecord(Base):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="created")
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Nested/structured data -- SQLAlchemy's JSON type serializes these to
    # TEXT under SQLite automatically, so callers still just get/set plain
    # Python dicts and lists exactly like before.
    extract_stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parse_errors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def to_dict(self) -> dict:
        """Matches the shape the old JSON-registry dict used to have."""
        return {
            "project_id": self.project_id,
            "status": self.status,
            "original_filename": self.original_filename,
            "chunk_count": self.chunk_count,
            "error": self.error,
            "extract_stats": self.extract_stats,
            "parse_errors": self.parse_errors,
            "analysis": self.analysis,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
