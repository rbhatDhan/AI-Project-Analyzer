from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ai.llm import generate_answer
from core.workspace import get_project
from rag.retriever import retrieve

router = APIRouter(prefix="/chat", tags=["chat"])


class AskRequest(BaseModel):
    project_id: str
    question: str
    top_k: int = 8


@router.post("/ask")
async def ask(req: AskRequest):
    project = get_project(req.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Unknown project_id.")
    if project.get("status") != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"Project is not ready yet (status: {project.get('status')}).",
        )

    try:
        chunks = retrieve(req.project_id, req.question, top_k=req.top_k)
        answer = generate_answer(req.question, chunks)
    except Exception as e:  # noqa: BLE001 - surface the real cause instead of a blank 500
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}")

    sources = [{
        "file_path": c.get("file_path"),
        "symbol": c.get("symbol"),
        "type": c.get("type"),
        "line_start": c.get("line_start"),
        "line_end": c.get("line_end"),
        "score": c.get("score"),
    } for c in chunks]

    return {"question": req.question, "answer": answer, "sources": sources}
