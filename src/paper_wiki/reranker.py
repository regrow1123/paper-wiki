"""LlamaIndex NodePostprocessor backed by llama-server rerank endpoint."""

from __future__ import annotations

from typing import Any, List, Optional

import httpx
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import NodeWithScore, QueryBundle
from pydantic import Field, PrivateAttr

from .config import Settings, get_settings


class LlamaServerReranker(BaseNodePostprocessor):
    """Rerank nodes by calling llama-server `/v1/rerank` (or fallback `/rerank`).

    Qwen3-Reranker scores (query, document) pairs. The server returns items with
    index + relevance_score; we reorder nodes accordingly and keep top_n.
    """

    base_url: str = Field(description="llama-server base URL")
    top_n: int = Field(default=10)
    timeout: float = Field(default=120.0)

    _client: httpx.Client = PrivateAttr()

    def __init__(self, **kwargs: Any) -> None:
        s: Settings = get_settings()
        kwargs.setdefault("base_url", s.rerank_url)
        kwargs.setdefault("top_n", s.top_k_rerank)
        kwargs.setdefault("timeout", s.rerank_timeout)
        super().__init__(**kwargs)
        self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)

    @classmethod
    def class_name(cls) -> str:
        return "LlamaServerReranker"

    def _rerank(self, query: str, documents: List[str]) -> List[tuple[int, float]]:
        payload = {"query": query, "documents": documents, "top_n": len(documents)}
        # Try /v1/rerank first, fall back to /rerank (llama.cpp exposes both).
        for path in ("/v1/rerank", "/rerank"):
            try:
                r = self._client.post(path, json=payload)
            except httpx.HTTPError:
                continue
            if r.status_code == 404:
                continue
            r.raise_for_status()
            data = r.json()
            # llama.cpp returns {"results": [{"index": i, "relevance_score": s}, ...]}
            items = data.get("results") or data.get("data") or []
            return [(int(it["index"]), float(it.get("relevance_score", it.get("score", 0.0))))
                    for it in items]
        raise RuntimeError("No rerank endpoint available on llama-server")

    def score(self, query: str, documents: List[str]) -> List[float]:
        """Public helper used by the MCP `rerank` tool."""
        pairs = self._rerank(query, documents)
        # Ensure we return scores in original input order.
        scores = [0.0] * len(documents)
        for idx, s in pairs:
            if 0 <= idx < len(documents):
                scores[idx] = s
        return scores

    def _postprocess_nodes(
        self,
        nodes: List[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> List[NodeWithScore]:
        if not nodes or query_bundle is None:
            return nodes[: self.top_n]
        texts = [n.node.get_content() for n in nodes]
        pairs = self._rerank(query_bundle.query_str, texts)
        pairs.sort(key=lambda p: p[1], reverse=True)
        out: List[NodeWithScore] = []
        for idx, score in pairs[: self.top_n]:
            if 0 <= idx < len(nodes):
                nodes[idx].score = score
                out.append(nodes[idx])
        return out
