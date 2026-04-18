"""Typer CLI — mirrors the MCP tools for shell usage."""

from __future__ import annotations

import json

import typer

from . import ingest as ingest_mod
from . import search as search_mod
from .index import collection_stats, get_index
from .parsers import iter_all_sources

app = typer.Typer(help="Paper Wiki CLI", no_args_is_help=True)


def _print(obj) -> None:
    typer.echo(json.dumps(obj, ensure_ascii=False, indent=2))


@app.command("index-add")
def index_add(path: str) -> None:
    """Upsert a single paper PDF into the index."""
    _print(ingest_mod.ingest_one(path))


@app.command("index-remove")
def index_remove(path: str) -> None:
    """Remove all chunks belonging to a paper from the index."""
    _print(ingest_mod.remove_one(path))


@app.command("index-build")
def index_build() -> None:
    """Rebuild the index by walking raw/papers/."""
    _print(ingest_mod.reindex_all())


@app.command("reindex")
def reindex() -> None:
    """Alias for index-build."""
    _print(ingest_mod.reindex_all())


@app.command("search")
def search_cmd(
    query: str,
    top_k: int = typer.Option(10),
    no_rerank: bool = typer.Option(False, "--no-rerank"),
) -> None:
    """Search the index and return top-k reranked chunks."""
    _print(search_mod.search(query, top_k=top_k, rerank=not no_rerank))


@app.command("stats")
def stats_cmd() -> None:
    """Print index statistics."""
    handle = get_index()
    st = collection_stats(handle.collection)
    _print({
        "total_chunks": st["total_chunks"],
        "last_indexed_at": st["last_indexed_at"],
        "source_count": len(st["sources"]),
    })


@app.command("list-sources")
def list_sources_cmd() -> None:
    """List all indexed papers."""
    handle = get_index()
    st = collection_stats(handle.collection)
    items = list(st["sources"].values())
    items.sort(key=lambda s: s.get("indexed_at", ""), reverse=True)
    _print(items)


@app.command("list-raw")
def list_raw_cmd() -> None:
    """List paper PDFs present under raw/papers/ (not necessarily indexed)."""
    refs = [{"path": r.rel_path, "title": r.title} for r in iter_all_sources()]
    _print(refs)


if __name__ == "__main__":  # pragma: no cover
    app()
