from fastapi import APIRouter, HTTPException

from core.workspace import get_project
from diagrams.mermaid_generator import generate_architecture_diagram

router = APIRouter(prefix="/architecture", tags=["architecture"])


@router.get("/{project_id}")
async def get_architecture(project_id: str):
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Unknown project_id.")
    if project.get("status") != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"Project is not ready yet (status: {project.get('status')}).",
        )
    analysis = project.get("analysis", {})
    diagram = generate_architecture_diagram(analysis)
    return {"project_id": project_id, "mermaid": diagram, "analysis_summary": {
        "languages": list(analysis.get("languages", {}).keys()),
        "frameworks": analysis.get("frameworks", []),
        "structure": analysis.get("structure", []),
    }}
