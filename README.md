# AI Project Analyzer & RAG Assistant — MVP

Implements MVP scope (spec section 26, items 1–10):
ZIP upload → extraction → file filtering → structure/language/framework
analysis → AST-based chunking → Gemini embeddings → FAISS vector store →
RAG question answering with source references → basic Mermaid architecture
diagram.

Deferred (per your instructions): knowledge graph (NetworkX later), frontend
(test via curl/Postman), interview/code-review/resume features.

## 1. Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and paste your free key from https://aistudio.google.com/apikey
```

## 2. Run

```bash
uvicorn main:app --reload --port 8000
```

Visit http://localhost:8000/docs for interactive Swagger UI (easier than curl
if you just want to click through it), or use the curl commands below.

## 3. Minimal UI

A single-file, no-build-step UI is bundled at `static/index.html` and served
by the backend itself — no separate frontend server needed.

```bash
uvicorn main:app --reload --port 8000
# then open:
http://localhost:8000/ui
```

It covers the current MVP surface end-to-end: drag/drop a ZIP, watch the
status pipeline (`queued → extracting → analyzing → chunking → embedding →
ready`), pick from previously-analyzed projects, ask questions with
expandable source citations, and render the Mermaid architecture diagram
inline. It's intentionally plain (vanilla HTML/CSS/JS, no framework) so it's
easy to extend once the next backend slice (knowledge graph, explanations,
etc.) lands.

If you ever want to point the UI at a different host (e.g. a deployed
backend), edit the URL field in the header — it defaults to whatever origin
served the page.

## 4. Test via curl

### Upload a project ZIP
```bash
curl -X POST http://localhost:8000/projects/upload \
  -F "file=@/path/to/your_project.zip"
```
Returns `{"project_id": "...", "status": "queued"}`. Analysis runs in the
background (extraction → parsing → chunking → embedding can take from
seconds to a couple minutes depending on project size).

### Poll status
```bash
curl http://localhost:8000/projects/<project_id>
```
Watch `status` go: `extracting` → `analyzing` → `chunking` → `embedding` →
`ready` (or `failed`, check the `error` field).

### Ask a question (once status is "ready")
```bash
curl -X POST http://localhost:8000/chat/ask \
  -H "Content-Type: application/json" \
  -d '{"project_id": "<project_id>", "question": "How does authentication work in this project?"}'
```
Returns an answer grounded in retrieved chunks, plus a `sources` array with
file paths, symbol names, and line ranges — paste the `mermaid` field or the
sources straight into anything that needs traceability.

### Get the architecture diagram
```bash
curl http://localhost:8000/architecture/<project_id>
```
Returns a Mermaid `graph TD` string — paste it into https://mermaid.live to
render it, or into any Markdown viewer that supports Mermaid.

## 5. Notes on what's real vs. simplified for the MVP

- **Code parsing**: Python only, via the stdlib `ast` module
  (`analysis/code_parser.py`). Non-Python files fall back to whole-file
  chunks (capped at ~6000 chars) so nothing is silently dropped — add a new
  language by writing one function and registering it in `PARSERS`.
- **Chunking**: class/function/method-level for Python, matching the
  metadata shape in the spec (file_path, symbol, type, line_start/end,
  dependencies = called function names).
- **Vector store**: FAISS behind a `VectorStore` interface
  (`rag/vector_store.py`) — swap in Chroma/pgvector later by implementing
  the same 4 methods.
- **Embeddings/LLM**: Gemini free tier (`text-embedding-004` +
  `gemini-2.0-flash`), both behind small interfaces
  (`rag/embeddings.py`, `ai/llm.py`) for the same reason.
- **Security**: zip-slip/path-traversal blocked, upload size / file count /
  per-file size capped, `.env` files never extracted-and-read into chunks
  (excluded in `ingestion/file_filter.py`), uploaded code is never executed.
- **Registry**: a flat `workspace/registry.json`, not Postgres — fine for
  local dev, swap for a real DB when you add multi-user support.

## 6. Suggested next slice (spec section 26, items 11–17)

In order of dependency:
1. **Dependency/knowledge graph** (`graph/knowledge_graph.py` with
   NetworkX) — build from the `dependencies` (call names) already captured
   per chunk; this unlocks better architecture diagrams and "what calls
   this" questions.
2. **Project explanation generator** — one Gemini call over a
   summarized-analysis + top-N chunks, no new infra needed.
3. **Interview question generation** — same idea, templated by category
   (spec section 16).
4. **Mock interview** — stateful multi-turn chat using the same retriever.
5. **Code review** — static checks (unused imports, bare excepts, etc. via
   `ast`) + an LLM pass over flagged spots, framed as "verify before
   claiming" per the accuracy requirements.

Tell me which one you want built next and I'll add it the same way — new
module(s) plumbed into `main.py`, tested against a real chunk before wiring
in.
