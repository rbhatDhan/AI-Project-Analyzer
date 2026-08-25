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


def get_vector_store(index_dir: Path, dim: int = 768) -> VectorStore:
    store = FaissVectorStore(index_dir=index_dir, dim=dim)
    store.load()
    return store
