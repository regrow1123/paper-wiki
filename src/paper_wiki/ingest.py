"""Ingestion operations: add / remove / reindex paper sources."""

from __future__ import annotations

from typing import Any

from .index import delete_by_source_path, get_index, insert_nodes
from .parsers import SourceRef, iter_all_sources, load_nodes, resolve_source


def ingest_one(path_input: str) -> dict[str, Any]:
    """Upsert a single paper by path (relative to raw/ or absolute)."""
    ref: SourceRef = resolve_source(path_input)
    handle = get_index()
    removed = delete_by_source_path(handle.collection, ref.rel_path)
    nodes = load_nodes(ref)
    added = insert_nodes(handle, nodes)
    return {
        "source_path": ref.rel_path,
        "title": ref.title,
        "removed_chunks": removed,
        "added_chunks": added,
    }


def remove_one(path_input: str) -> dict[str, Any]:
    ref: SourceRef = resolve_source(path_input)
    handle = get_index()
    removed = delete_by_source_path(handle.collection, ref.rel_path)
    return {"source_path": ref.rel_path, "removed_chunks": removed}


def reindex_all() -> dict[str, Any]:
    handle = get_index()
    added_total = 0
    removed_total = 0
    processed = 0
    for ref in iter_all_sources():
        removed_total += delete_by_source_path(handle.collection, ref.rel_path)
        nodes = load_nodes(ref)
        added_total += insert_nodes(handle, nodes)
        processed += 1
    return {
        "sources_processed": processed,
        "added_chunks": added_total,
        "removed_chunks": removed_total,
    }
