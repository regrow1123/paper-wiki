"""Chroma + LlamaIndex vector store plumbing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

import chromadb
from chromadb.api.models.Collection import Collection
from llama_index.core import Settings, StorageContext, VectorStoreIndex
from llama_index.core.schema import TextNode
from llama_index.vector_stores.chroma import ChromaVectorStore

from .config import get_settings
from .dummy_llm import install_dummy_llm
from .embeddings import LlamaServerEmbedding


@dataclass
class IndexHandle:
    index: VectorStoreIndex
    vector_store: ChromaVectorStore
    collection: Collection
    client: chromadb.api.ClientAPI


_handle: Optional[IndexHandle] = None


_EMBED_INSTALLED = False


def _configure_settings() -> None:
    global _EMBED_INSTALLED
    install_dummy_llm()
    if not _EMBED_INSTALLED:
        Settings.embed_model = LlamaServerEmbedding()
        _EMBED_INSTALLED = True


def get_index() -> IndexHandle:
    """Return a cached Chroma-backed VectorStoreIndex, creating if needed."""
    global _handle
    if _handle is not None:
        return _handle

    _configure_settings()
    s = get_settings()
    chroma_path = s.resolve(s.chroma_dir)
    chroma_path.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.get_or_create_collection(name=s.chroma_collection)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_ctx = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_ctx)

    _handle = IndexHandle(index=index, vector_store=vector_store,
                          collection=collection, client=client)
    return _handle


def reset_index_cache() -> None:
    global _handle
    _handle = None


def delete_by_source_path(collection: Collection, source_path: str) -> int:
    """Delete all chunks whose metadata.source_path matches. Returns count removed."""
    res = collection.get(where={"source_path": source_path})
    ids: List[str] = res.get("ids", []) or []
    if ids:
        collection.delete(ids=ids)
    return len(ids)


def insert_nodes(handle: IndexHandle, nodes: List[TextNode]) -> int:
    if not nodes:
        return 0
    handle.index.insert_nodes(nodes)
    return len(nodes)


def collection_stats(collection: Collection) -> dict[str, Any]:
    """Aggregate counts by source_path and last indexed_at."""
    # Chroma doesn't expose aggregates — pull metadata only.
    got = collection.get(include=["metadatas"])
    metas = got.get("metadatas") or []
    total = len(metas)
    last_indexed: str = ""
    sources: dict[str, dict[str, Any]] = {}
    for m in metas:
        sp = m.get("source_path")
        if sp:
            entry = sources.setdefault(sp, {
                "path": sp,
                "title": m.get("title", sp),
                "chunk_count": 0,
                "indexed_at": m.get("indexed_at", ""),
            })
            entry["chunk_count"] += 1
            if m.get("indexed_at", "") > entry["indexed_at"]:
                entry["indexed_at"] = m["indexed_at"]
        ia = m.get("indexed_at", "")
        if ia > last_indexed:
            last_indexed = ia
    return {
        "total_chunks": total,
        "last_indexed_at": last_indexed,
        "sources": sources,
    }
