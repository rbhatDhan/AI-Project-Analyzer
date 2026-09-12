import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from core.config import settings
from core.workspace import create_project, get_project, list_projects, project_dir, update_project
from ingestion.pipeline import run_pipeline
from ingestion.zip_extractor import ZipValidationError

router = APIRouter(prefix="/projects", tags=["projects"])


def _process_in_background(project_id: str, zip_path: Path):
    try:
        if settings.STORAGE_BACKEND == "supabase":
            # zip_path here is a local staging path, not the persisted copy --
            # the persisted copy already went to the Supabase bucket in
            # upload_project(). Re-download it into /tmp for this run so
            # run_pipeline() can extract from local disk as before.
            from core.storage import download_zip
            download_zip(project_id, zip_path)
        run_pipeline(project_id, zip_path)
    except ZipValidationError as e:
        update_project(project_id, status="failed", error=str(e))
    except Exception as e:  # noqa: BLE001 - surface any failure to the client via status
        update_project(project_id, status="failed", error=f"{type(e).__name__}: {e}")


@router.post("/upload")
async def upload_project(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted.")

    project_id = create_project()
    raw_path = project_dir(project_id) / "raw" / "project.zip"
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    with open(raw_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    if settings.STORAGE_BACKEND == "supabase":
        # This is the copy that actually needs to survive -- Vercel's local
        # disk won't persist raw_path between this request and whatever
        # invocation runs _process_in_background.
        from core.storage import upload_zip
        upload_zip(project_id, raw_path)

    update_project(project_id, status="queued", original_filename=file.filename)
    background_tasks.add_task(_process_in_background, project_id, raw_path)

    return {
        "project_id": project_id,
        "status": "queued",
        "message": "Upload accepted. Poll GET /projects/{project_id} for status.",
    }


@router.get("/{project_id}")
async def get_project_status(project_id: str):
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Unknown project_id.")
    return project


@router.get("")
async def get_all_projects():
    return list_projects()
