"""
Supabase Storage helpers for the uploaded project zip. Only used when
settings.STORAGE_BACKEND == "supabase" -- local dev keeps writing the zip
straight to WORKSPACE_DIR/<id>/raw/, same as before.

Why just the zip (not the extracted files or vector index): on Vercel, only
the raw zip needs to survive between separate function invocations.
Extraction and embedding happen synchronously inside run_pipeline() within
one request, so that step can keep using local /tmp disk -- it only needs
to survive until that one pipeline run finishes, not across requests. The
extracted source and embeddings themselves never need long-term local
storage: extracted files are discarded after chunking, and embeddings go
straight to pgvector (see rag/vector_store.py) when VECTOR_BACKEND=pgvector.
"""
from pathlib import Path

from core.config import settings

_client = None


def _get_client():
    global _client
    if _client is None:
        from supabase import create_client
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
            raise RuntimeError(
                "SUPABASE_URL / SUPABASE_SERVICE_KEY are not set. See .env.example. "
                "Create a Storage bucket named settings.SUPABASE_STORAGE_BUCKET first."
            )
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    return _client


def _storage_path(project_id: str) -> str:
    return f"{project_id}/project.zip"


def upload_zip(project_id: str, local_path: Path) -> str:
    """Uploads the zip at local_path to the projects bucket, keyed by project_id."""
    client = _get_client()
    storage_path = _storage_path(project_id)
    with open(local_path, "rb") as f:
        client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
            storage_path, f, {"content-type": "application/zip", "upsert": "true"}
        )
    return storage_path


def download_zip(project_id: str, dest_path: Path) -> Path:
    """Downloads the project's zip from storage to dest_path (e.g. under /tmp) for processing."""
    client = _get_client()
    data = client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).download(_storage_path(project_id))
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(data)
    return dest_path
