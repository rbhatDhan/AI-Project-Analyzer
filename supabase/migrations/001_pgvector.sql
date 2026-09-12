-- Run this once in the Supabase SQL editor (or `supabase db push`) before
-- setting VECTOR_BACKEND=pgvector.

create extension if not exists vector;

create table if not exists chunk_embeddings (
    project_id  text not null,
    chunk_id    text not null,
    embedding   vector(3072) not null,  -- gemini-embedding-001 output size
    metadata    jsonb not null,
    created_at  timestamptz not null default now(),
    primary key (project_id, chunk_id)
);

-- Every query filters by project_id first (see rag/vector_store.py), so a
-- plain btree here is what actually matters -- no ivfflat/hnsw vector index
-- is built, since pgvector's ANN index types cap out around 2000 dimensions
-- and this table stores 3072-dim vectors. Search stays exact/brute-force
-- per project, same as the FaissVectorStore it replaces.
create index if not exists chunk_embeddings_project_id_idx on chunk_embeddings (project_id);
