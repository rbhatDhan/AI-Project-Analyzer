"""
Vector store abstraction. `VectorStore` is the interface every retriever
call goes through; `FaissVectorStore` is the only implementation for the
MVP. Swapping to Chroma or pgvector later means writing one new class here,
nothing else in the codebase changes.

FAISS itself only stores vectors + integer ids, so we keep the chunk
metadata (file path, symbol, line range, text, ...) in a parallel JSON file
keyed by the same ids.
"""
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

import faiss
import numpy as np

from core.config import settings


class VectorStore(ABC):
    @abstractmethod
    def add(self, ids: List[str], vectors: List[List[float]], metadatas: List[dict]) -> None:
        ...

    @abstractmethod
    def search(self, query_vector: List[float], top_k: int = 8) -> List[dict]:
        ...

    @abstractmethod
    def save(self) -> None:
        ...

    @abstractmethod
    def load(self) -> bool:
        ...


class FaissVectorStore(VectorStore):
    def __init__(self, index_dir: Path, dim: int = 768):
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.dim = dim
        self.index_path = self.index_dir / "faiss.index"
        self.meta_path = self.index_dir / "metadata.json"

        self.index = faiss.IndexFlatIP(dim)  # cosine similarity via normalized vectors
        self.metadatas: List[dict] = []  # position i corresponds to faiss internal id i

    @staticmethod
    def _normalize(vectors: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1e-8
        return vectors / norms

    def add(self, ids: List[str], vectors: List[List[float]], metadatas: List[dict]) -> None:
        if not vectors:
            return
        arr = np.array(vectors, dtype="float32")
        arr = self._normalize(arr)
        self.index.add(arr)
        for chunk_id, meta in zip(ids, metadatas):
            record = dict(meta)
            record["chunk_id"] = chunk_id
            self.metadatas.append(record)

    def search(self, query_vector: List[float], top_k: int = 8) -> List[dict]:
        if self.index.ntotal == 0:
            return []
        q = np.array([query_vector], dtype="float32")
        q = self._normalize(q)
        scores, indices = self.index.search(q, min(top_k, self.index.ntotal))
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            record = dict(self.metadatas[idx])
            record["score"] = float(score)
            results.append(record)
        return results

    def save(self) -> None:
        faiss.write_index(self.index, str(self.index_path))
        with open(self.meta_path, "w") as f:
            json.dump(self.metadatas, f)

    def load(self) -> bool:
        if not self.index_path.exists() or not self.meta_path.exists():
            return False
        self.index = faiss.read_index(str(self.index_path))
        with open(self.meta_path, "r") as f:
            self.metadatas = json.load(f)
        return True


class PgVectorStore(VectorStore):
    """
    Supabase Postgres + pgvector backend. Same per-project scoping as
    FaissVectorStore, but rows live in a shared `chunk_embeddings` table
    (see supabase/migrations/001_pgvector.sql) instead of a local index file
    -- required on Vercel, where local disk doesn't persist between
    invocations.

    Search stays exact (brute-force cosine via `<=>`, filtered by
    project_id), matching FaissVectorStore's IndexFlatIP -- no behavior
    change, just a different place the vectors live. This also sidesteps
    pgvector's ~2000-dimension cap on ANN indexes (ivfflat/hnsw), since
    gemini-embedding-001 is 3072-dim and we never build one: a WHERE
    project_id = ... clause already keeps each query to one project's chunks
    (typically hundreds, not millions), so brute force is plenty fast.
    """

    def __init__(self, project_id: str, dim: int = 768):
        self.project_id = project_id
        self.dim = dim
        self._conn = None

    def _connection(self):
        if self._conn is None or self._conn.closed:
            import psycopg
            from pgvector.psycopg import register_vector
            # psycopg (v3) takes the plain postgresql:// URL as-is -- the
            # "+psycopg" driver suffix in core/db.py is a SQLAlchemy-only
            # convention and doesn't belong in a raw connection string here.
            self._conn = psycopg.connect(settings.DATABASE_URL)
            register_vector(self._conn)  # lets psycopg adapt Python lists <-> the vector type
        return self._conn

    def add(self, ids: List[str], vectors: List[List[float]], metadatas: List[dict]) -> None:
        if not vectors:
            return
        conn = self._connection()
        with conn.cursor() as cur:
            for chunk_id, vector, meta in zip(ids, vectors, metadatas):
                cur.execute(
                    """
                    INSERT INTO chunk_embeddings (project_id, chunk_id, embedding, metadata)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (project_id, chunk_id)
                    DO UPDATE SET embedding = EXCLUDED.embedding, metadata = EXCLUDED.metadata
                    """,
                    (self.project_id, chunk_id, vector, json.dumps(meta)),
                )
        conn.commit()

    def search(self, query_vector: List[float], top_k: int = 8) -> List[dict]:
        conn = self._connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT chunk_id, metadata, 1 - (embedding <=> %s::vector) AS score
                FROM chunk_embeddings
                WHERE project_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_vector, self.project_id, query_vector, top_k),
            )
            rows = cur.fetchall()
        results = []
        for chunk_id, metadata, score in rows:
            record = dict(metadata)
            record["chunk_id"] = chunk_id
            record["score"] = float(score)
            results.append(record)
        return results

    def save(self) -> None:
        pass  # writes are committed immediately in add(); nothing to flush

    def load(self) -> bool:
        conn = self._connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM chunk_embeddings WHERE project_id = %s LIMIT 1", (self.project_id,))
            return cur.fetchone() is not None


def get_vector_store(index_dir: Path, dim: int = 768) -> VectorStore:
    if settings.VECTOR_BACKEND == "pgvector":
        # index_dir is always workspace/<project_id>/index -- pull the id
        # back out rather than changing every call site's signature.
        project_id = Path(index_dir).parent.name
        store = PgVectorStore(project_id=project_id, dim=dim)
        store.load()
        return store

    store = FaissVectorStore(index_dir=index_dir, dim=dim)
    store.load()
    return store
