from fastapi import APIRouter, HTTPException

from core.workspace import get_project
from diagrams.mermaid_generator import generate_architecture_diagram, generate_endpoint_flow_diagrams

router = APIRouter(prefix="/architecture", tags=["architecture"])


@router.get("/{project_id}")
async def get_architecture(project_id: str):
    """
    Returns both views: `overview_mermaid` is the old tech-stack pipeline
    (still handy as a 10-second summary), and `flows` is a list of
    per-endpoint diagrams tracing the real call sequence -- what a student
    actually needs when explaining "what happens when the user does X" in
    a placement interview.
    """
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Unknown project_id.")
    if project.get("status") != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"Project is not ready yet (status: {project.get('status')}).",
        )
    analysis = project.get("analysis", {})
    overview = generate_architecture_diagram(analysis)
    flows = generate_endpoint_flow_diagrams(analysis)
    return {
        "project_id": project_id,
        "overview_mermaid": overview,
        "flows": flows,  # [{"name", "entry", "file", "mermaid"}, ...]
        "analysis_summary": {
            "languages": list(analysis.get("languages", {}).keys()),
            "frameworks": analysis.get("frameworks", []),
            "structure": analysis.get("structure", []),
        },
    }
