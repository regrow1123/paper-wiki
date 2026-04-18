"""FastMCP stdio server exposing Paper Wiki operations to Claude Code."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

from fastmcp import FastMCP

from . import ingest as ingest_mod
from . import search as search_mod
from .config import get_settings
from .index import collection_stats, get_index

mcp = FastMCP("paper-wiki")

_MAX_DOC_BYTES = 1_000_000


def _safe_raw_path(rel_path: str) -> Path:
    """Resolve `rel_path` inside raw/; reject anything escaping the root."""
    s = get_settings()
    root = s.resolve(s.raw_dir)
    p = Path(rel_path)
    candidate = (p if p.is_absolute() else root / p).resolve()
    if not str(candidate).startswith(str(root)):
        raise ValueError(f"Path escapes raw/: {rel_path}")
    return candidate


@mcp.tool
def search(
    query: str,
    top_k: int = 10,
    rerank: bool = True,
) -> List[dict[str, Any]]:
    """Vector search + optional rerank over the Paper Wiki index.

    Args:
        query: natural-language query.
        top_k: number of chunks to return.
        rerank: if true, rerank top_k_retrieve candidates with Qwen3-Reranker.

    Returns a list of {path, text, score, metadata}.
    """
    return search_mod.search(query, top_k=top_k, rerank=rerank)


@mcp.tool
def rerank(
    query: str,
    documents: List[str],
    top_n: int = 10,
) -> List[dict[str, Any]]:
    """Rerank a caller-provided list of text documents against the query."""
    return search_mod.rerank_external(query, documents, top_n=top_n)


@mcp.tool
def get_document(path: str) -> dict[str, Any]:
    """Return the raw content of a file under raw/. Truncates at ~1 MB.

    Pass the path to a paper PDF (e.g. 'papers/<slug>.pdf').
    Returns {path, text, truncated, size}.
    """
    target = _safe_raw_path(path)
    if not target.is_file():
        raise FileNotFoundError(f"Not a file: {path}")
    size = target.stat().st_size
    truncated = size > _MAX_DOC_BYTES
    with target.open("rb") as f:
        data = f.read(_MAX_DOC_BYTES)
    text = data.decode("utf-8", errors="replace")
    return {"path": path, "text": text, "truncated": truncated, "size": size}


@mcp.tool
def index_add(path: str) -> dict[str, Any]:
    """Upsert a paper folder into the index."""
    return ingest_mod.ingest_one(path)


@mcp.tool
def index_remove(path: str) -> dict[str, Any]:
    """Remove a paper from the index."""
    return ingest_mod.remove_one(path)


@mcp.tool
def reindex() -> dict[str, Any]:
    """Rebuild the index from raw/papers/."""
    return ingest_mod.reindex_all()


@mcp.tool
def stats() -> dict[str, Any]:
    """Index-level statistics (chunk count, source count, last ingest time)."""
    s = get_settings()
    handle = get_index()
    st = collection_stats(handle.collection)
    return {
        "total_chunks": st["total_chunks"],
        "last_indexed_at": st["last_indexed_at"],
        "source_count": len(st["sources"]),
        "embed_model": str(s.embed_model_path),
        "rerank_model": str(s.rerank_model_path),
        "embed_url": s.embed_url,
        "rerank_url": s.rerank_url,
        "chroma_collection": s.chroma_collection,
    }


@mcp.tool
def list_sources() -> List[dict[str, Any]]:
    """List indexed papers with metadata ({path, title, chunk_count, indexed_at})."""
    handle = get_index()
    st = collection_stats(handle.collection)
    items = list(st["sources"].values())
    items.sort(key=lambda s: s.get("indexed_at", ""), reverse=True)
    return items


def main() -> None:
    """Entry point for `paper-wiki-mcp` — runs stdio MCP server."""
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
