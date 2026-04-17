"""Retriever + reranker pipeline exposed to MCP `search`."""

from __future__ import annotations

from typing import Any, List, Optional

from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.vector_stores import (
    ExactMatchFilter,
    MetadataFilters,
)

from .config import get_settings
from .index import get_index
from .reranker import LlamaServerReranker


def _build_filters(source_type: Optional[str]) -> Optional[MetadataFilters]:
    if not source_type:
        return None
    return MetadataFilters(filters=[ExactMatchFilter(key="source_type", value=source_type)])


def search(
    query: str,
    top_k: Optional[int] = None,
    source_type: Optional[str] = None,
    rerank: bool = True,
) -> List[dict[str, Any]]:
    s = get_settings()
    top_k = top_k or s.top_k_rerank
    handle = get_index()

    retriever = handle.index.as_retriever(
        similarity_top_k=max(s.top_k_retrieve, top_k),
        filters=_build_filters(source_type),
    )
    nodes: List[NodeWithScore] = retriever.retrieve(QueryBundle(query_str=query))

    if rerank and nodes:
        reranker = LlamaServerReranker(top_n=top_k)
        nodes = reranker.postprocess_nodes(nodes, query_bundle=QueryBundle(query_str=query))
    else:
        nodes = nodes[:top_k]

    return [
        {
            "path": n.node.metadata.get("source_path"),
            "text": n.node.get_content(),
            "score": float(n.score) if n.score is not None else None,
            "metadata": dict(n.node.metadata),
        }
        for n in nodes
    ]


def rerank_external(query: str, documents: List[str], top_n: Optional[int] = None) -> list[dict[str, Any]]:
    s = get_settings()
    top_n = top_n or s.top_k_rerank
    reranker = LlamaServerReranker(top_n=top_n)
    scores = reranker.score(query, documents)
    ranked = sorted(
        ({"index": i, "score": scores[i], "text": documents[i]} for i in range(len(documents))),
        key=lambda d: d["score"],
        reverse=True,
    )
    return ranked[:top_n]
