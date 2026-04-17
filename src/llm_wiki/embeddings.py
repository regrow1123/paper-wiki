"""LlamaIndex embedding backed by llama.cpp llama-server HTTP /v1/embeddings."""

from __future__ import annotations

from typing import Any, List

import httpx
from llama_index.core.embeddings import BaseEmbedding
from pydantic import Field, PrivateAttr

from .config import Settings, get_settings


class LlamaServerEmbedding(BaseEmbedding):
    """Qwen3-Embedding via llama-server (OpenAI-compatible `/v1/embeddings`).

    Qwen3-Embedding is instruction-aware for retrieval: queries are prefixed,
    document passages are passed as-is.
    """

    base_url: str = Field(description="llama-server base URL")
    timeout: float = Field(default=120.0)
    query_prefix: str = Field(
        default=(
            "Instruct: Given a web search query, retrieve relevant passages "
            "that answer the query\nQuery: "
        ),
        description="Prefix applied to queries per Qwen3-Embedding retrieval recipe.",
    )

    _client: httpx.Client = PrivateAttr()

    def __init__(self, **kwargs: Any) -> None:
        s: Settings = get_settings()
        kwargs.setdefault("base_url", s.embed_url)
        kwargs.setdefault("timeout", s.embed_timeout)
        kwargs.setdefault("embed_batch_size", 16)
        super().__init__(**kwargs)
        self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)

    @classmethod
    def class_name(cls) -> str:
        return "LlamaServerEmbedding"

    def _post(self, inputs: List[str]) -> List[List[float]]:
        r = self._client.post("/v1/embeddings", json={"input": inputs})
        r.raise_for_status()
        data = r.json()["data"]
        data.sort(key=lambda d: d.get("index", 0))
        return [d["embedding"] for d in data]

    def _get_query_embedding(self, query: str) -> List[float]:
        return self._post([f"{self.query_prefix}{query}"])[0]

    def _get_text_embedding(self, text: str) -> List[float]:
        return self._post([text])[0]

    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        return self._post(texts)

    async def _aget_query_embedding(self, query: str) -> List[float]:
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> List[float]:
        return self._get_text_embedding(text)
