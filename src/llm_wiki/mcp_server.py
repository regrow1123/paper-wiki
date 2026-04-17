"""FastMCP stdio server exposing LLM Wiki operations to Claude Code."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from fastmcp import FastMCP

from . import ingest as ingest_mod
from . import search as search_mod
from .config import get_settings
from .index import collection_stats, get_index

mcp = FastMCP("llm-wiki")

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
    source_type: Optional[str] = None,
    rerank: bool = True,
) -> List[dict[str, Any]]:
    """Vector search + optional rerank over the LLM Wiki index.

    Args:
        query: natural-language query.
        top_k: number of chunks to return.
        source_type: optional filter — 'memo' or 'paper'.
        rerank: if true, rerank top_k_retrieve candidates with Qwen3-Reranker.

    Returns a list of {path, text, score, metadata}.
    """
    return search_mod.search(query, top_k=top_k, source_type=source_type, rerank=rerank)


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

    For paper folders, pass the path to the specific .tex file (e.g.
    'papers/<slug>/main.tex'). Returns {path, text, truncated, size}.
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
    """Upsert a source (memo file or paper folder) into the index."""
    return ingest_mod.ingest_one(path)


@mcp.tool
def index_remove(path: str) -> dict[str, Any]:
    """Remove a source from the index."""
    return ingest_mod.remove_one(path)


@mcp.tool
def reindex(source_type: Optional[str] = None) -> dict[str, Any]:
    """Rebuild the index from raw/. Optional source_type filter ('memo'|'paper')."""
    return ingest_mod.reindex_all(source_type)


@mcp.tool
def stats() -> dict[str, Any]:
    """Index-level statistics (chunk count, per-type counts, last ingest time)."""
    s = get_settings()
    handle = get_index()
    st = collection_stats(handle.collection)
    return {
        "total_chunks": st["total_chunks"],
        "sources_by_type": st["sources_by_type"],
        "last_indexed_at": st["last_indexed_at"],
        "source_count": len(st["sources"]),
        "embed_model": str(s.embed_model_path),
        "rerank_model": str(s.rerank_model_path),
        "embed_url": s.embed_url,
        "rerank_url": s.rerank_url,
        "chroma_collection": s.chroma_collection,
    }


@mcp.tool
def list_sources(source_type: Optional[str] = None) -> List[dict[str, Any]]:
    """List indexed sources with metadata ({path, title, source_type, chunk_count, indexed_at})."""
    handle = get_index()
    st = collection_stats(handle.collection)
    items = list(st["sources"].values())
    if source_type:
        items = [s for s in items if s["source_type"] == source_type]
    items.sort(key=lambda s: s.get("indexed_at", ""), reverse=True)
    return items


def main() -> None:
    """Entry point for `llm-wiki-mcp` — runs stdio MCP server."""
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
