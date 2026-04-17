"""Typer CLI — mirrors the MCP tools for shell usage."""

from __future__ import annotations

import json
from typing import Optional

import typer

from . import ingest as ingest_mod
from . import search as search_mod
from .index import collection_stats, get_index
from .parsers import iter_all_sources

app = typer.Typer(help="LLM Wiki CLI", no_args_is_help=True)


def _print(obj) -> None:
    typer.echo(json.dumps(obj, ensure_ascii=False, indent=2))


@app.command("index-add")
def index_add(path: str) -> None:
    """Upsert a single source (memo file or paper folder) into the index."""
    _print(ingest_mod.ingest_one(path))


@app.command("index-remove")
def index_remove(path: str) -> None:
    """Remove all chunks belonging to a source from the index."""
    _print(ingest_mod.remove_one(path))


@app.command("index-build")
def index_build(
    source_type: Optional[str] = typer.Option(None, help="memo | paper (default: all)")
) -> None:
    """Rebuild index by walking raw/."""
    _print(ingest_mod.reindex_all(source_type))


@app.command("reindex")
def reindex(
    source_type: Optional[str] = typer.Option(None, help="memo | paper (default: all)")
) -> None:
    """Alias for index-build."""
    _print(ingest_mod.reindex_all(source_type))


@app.command("search")
def search_cmd(
    query: str,
    top_k: int = typer.Option(10),
    source_type: Optional[str] = typer.Option(None),
    no_rerank: bool = typer.Option(False, "--no-rerank"),
) -> None:
    """Search the index and return top-k reranked chunks."""
    _print(search_mod.search(query, top_k=top_k, source_type=source_type, rerank=not no_rerank))


@app.command("stats")
def stats_cmd() -> None:
    """Print index statistics."""
    handle = get_index()
    st = collection_stats(handle.collection)
    _print({
        "total_chunks": st["total_chunks"],
        "sources_by_type": st["sources_by_type"],
        "last_indexed_at": st["last_indexed_at"],
        "source_count": len(st["sources"]),
    })


@app.command("list-sources")
def list_sources_cmd(
    source_type: Optional[str] = typer.Option(None),
) -> None:
    """List all indexed sources."""
    handle = get_index()
    st = collection_stats(handle.collection)
    items = list(st["sources"].values())
    if source_type:
        items = [s for s in items if s["source_type"] == source_type]
    items.sort(key=lambda s: s.get("indexed_at", ""), reverse=True)
    _print(items)


@app.command("list-raw")
def list_raw_cmd(
    source_type: Optional[str] = typer.Option(None),
) -> None:
    """List files present under raw/ (not necessarily indexed)."""
    refs = [{"path": r.rel_path, "source_type": r.source_type, "title": r.title}
            for r in iter_all_sources(source_type)]
    _print(refs)


if __name__ == "__main__":  # pragma: no cover
    app()
