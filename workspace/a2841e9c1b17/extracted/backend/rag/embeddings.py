"""
Embedding provider abstraction. Only a Gemini implementation exists for now
(per the chosen stack), but callers depend on `EmbeddingProvider`, not on
Gemini directly, so a local/OSS model can be swapped in later without
touching chunker/vector_store/retriever.
"""
import time
from abc import ABC, abstractmethod
from typing import List

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

from core.config import settings

_configured = False


def _ensure_configured():
    global _configured
    if not _configured:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key "
                "from https://aistudio.google.com/apikey"
            )
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _configured = True


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        ...

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        ...


class GeminiEmbeddingProvider(EmbeddingProvider):
    """
    Free-tier Gemini keys have a low requests-per-minute ceiling for
    embedContent (varies by account, often single digits to ~15 RPM). Rather
    than tune a magic batch size, we retry on 429 with exponential backoff
    and pace requests with a fixed delay -- slower, but it won't die on a
    real project's chunk count.
    """

    def __init__(self, model: str = None, batch_size: int = 10,
                 request_delay_seconds: float = 4.0, max_retries: int = 5):
        self.model = model or settings.GEMINI_EMBED_MODEL
        self.batch_size = batch_size
        self.request_delay_seconds = request_delay_seconds
        self.max_retries = max_retries

    def _embed_with_retry(self, content, task_type: str):
        _ensure_configured()
        delay = self.request_delay_seconds
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return genai.embed_content(model=self.model, content=content, task_type=task_type)
            except ResourceExhausted as e:
                last_error = e
                time.sleep(delay)
                delay *= 2  # exponential backoff
        raise last_error

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        vectors = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            result = self._embed_with_retry(batch, task_type="retrieval_document")
            vectors.extend(result["embedding"])
            if i + self.batch_size < len(texts):
                time.sleep(self.request_delay_seconds)  # pace to stay under RPM
        return vectors

    def embed_query(self, text: str) -> List[float]:
        result = self._embed_with_retry(text, task_type="retrieval_query")
        return result["embedding"]


def get_embedding_provider() -> EmbeddingProvider:
    return GeminiEmbeddingProvider()
