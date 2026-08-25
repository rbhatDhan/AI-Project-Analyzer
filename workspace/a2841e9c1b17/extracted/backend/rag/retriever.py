"""
Query-time retrieval. For the MVP this is vector search only; metadata
filtering and knowledge-graph traversal (spec section 12) are deferred but
this function is the natural place to add them later without touching the
API layer.
"""
from pathlib import Path

from core.workspace import index_dir
from rag.embeddings import get_embedding_provider
from rag.vector_store import get_vector_store

EMBED_DIM = 3072  # gemini-embedding-001 output size


def retrieve(project_id: str, question: str, top_k: int = 8) -> list:
    store = get_vector_store(index_dir(project_id), dim=EMBED_DIM)
    embedder = get_embedding_provider()
    query_vector = embedder.embed_query(question)
    return store.search(query_vector, top_k=top_k)
