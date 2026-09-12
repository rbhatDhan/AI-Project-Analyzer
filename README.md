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

## 6. Deploying to Vercel (Supabase-backed)

Local dev is untouched — SQLite + FAISS + local disk keep working with an
empty `.env`. Three env vars switch each layer independently to its
Supabase-backed equivalent, because Vercel's serverless functions have a
read-only, ephemeral filesystem (nothing written to local disk survives
between invocations):

1. **Registry** — create a Supabase project, then set `DATABASE_URL` to its
   Postgres connection string (Project Settings → Database → Connection
   string; use the **Transaction pooler** URI, not the direct connection —
   serverless opens a new connection per invocation and Postgres has a
   connection cap). Tables are created automatically on first run via
   `init_db()`, same as SQLite locally.
2. **Vector store** — run `supabase/migrations/001_pgvector.sql` once in the
   Supabase SQL editor, then set `VECTOR_BACKEND=pgvector`.
3. **Uploaded zips** — create a Storage bucket (name matches
   `SUPABASE_STORAGE_BUCKET`, default `project-zips`), set
   `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` (Project Settings → API — the
   *service_role* key, not anon, since uploads happen server-side) and
   `STORAGE_BACKEND=supabase`.

See `.env.example` for all the variable names.

**Known limitation worth knowing before you deploy:** ingestion
(`ingestion/pipeline.py`) currently runs via FastAPI's `BackgroundTasks`,
which assumes the process keeps running after the HTTP response is sent.
Vercel doesn't guarantee that — the function's execution context can be
frozen once the response goes out. Small projects will likely finish inside
Vercel's function timeout window anyway (raise `maxDuration` in
`vercel.json` if needed, up to 300s on Pro), but for anything larger you'll
want to move ingestion to a queue (e.g. a Vercel Cron endpoint that pulls
one `queued` project at a time from the registry) instead of relying on
`BackgroundTasks` finishing.

## 7. Suggested next slice (spec section 26, items 11–17)

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
