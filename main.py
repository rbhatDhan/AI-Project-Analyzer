from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from api import architecture, chat, projects


app = FastAPI(
    title="AI Project Analyzer & RAG Assistant",
    description="Upload a project ZIP, get a searchable, grounded, project-specific AI assistant.",
    version="0.1.0-mvp",
)


# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------
# Dev-friendly CORS:
# - The bundled UI is served same-origin at /ui.
# - This also allows the API to be accessed from another
#   frontend during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# API Routers
# ---------------------------------------------------------
app.include_router(projects.router)
app.include_router(chat.router)
app.include_router(architecture.router)


# ---------------------------------------------------------
# Frontend / UI
# ---------------------------------------------------------
# Serves:
#     /ui
#
# Example:
#     http://localhost:8000/ui
#
# Vercel:
#     https://your-app.vercel.app/ui
app.mount(
    "/ui",
    StaticFiles(directory="static", html=True),
    name="ui",
)


# ---------------------------------------------------------
# Root Route
# ---------------------------------------------------------
# Automatically redirect the user from:
#
#     /
#
# to:
#
#     /ui
#
# Therefore opening:
#     https://your-app.vercel.app/
#
# will directly open the frontend.
@app.get("/")
async def root():
    return RedirectResponse(url="/ui")