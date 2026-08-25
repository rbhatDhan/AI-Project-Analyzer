from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api import architecture, chat, projects

app = FastAPI(
    title="AI Project Analyzer & RAG Assistant",
    description="Upload a project ZIP, get a searchable, grounded, project-specific AI assistant.",
    version="0.1.0-mvp",
)

# Dev-friendly CORS: the bundled UI is served same-origin (see /ui below), but
# this also lets you open static/index.html directly (file://) or host the
# frontend elsewhere and point it at this API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(chat.router)
app.include_router(architecture.router)

# Minimal UI: open http://localhost:8000/ui
app.mount("/ui", StaticFiles(directory="static", html=True), name="ui")


@app.get("/")
async def root():
    return {
        "status": "ok",
        "ui": "GET /ui  (open this in a browser)",
        "endpoints": {
            "upload": "POST /projects/upload (multipart form field: file=<project.zip>)",
            "status": "GET /projects/{project_id}",
            "list": "GET /projects",
            "ask": "POST /chat/ask {project_id, question}",
            "architecture": "GET /architecture/{project_id}",
        },
    }
