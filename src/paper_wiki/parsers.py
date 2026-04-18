"""Source discovery and chunking for `.pdf` papers under `raw/papers/`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

import fitz  # PyMuPDF
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document, TextNode

from .config import get_settings


@dataclass
class SourceRef:
    path: Path       # absolute path to the .pdf file
    rel_path: str    # e.g. "papers/attention-is-all-you-need.pdf"
    slug: str        # filename stem
    title: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _pdf_title(doc: fitz.Document, fallback: str) -> str:
    """Return the PDF's metadata title if set and non-empty, else fallback."""
    title = (doc.metadata or {}).get("title", "") or ""
    title = title.strip()
    return title if title else fallback


def _extract_pages(path: Path) -> Iterable[tuple[int, str]]:
    """Yield (page_num_1indexed, text) per page via PyMuPDF."""
    with fitz.open(path) as doc:
        if doc.needs_pass:
            raise ValueError(f"Encrypted PDF not supported: {path}")
        for i, page in enumerate(doc, start=1):
            yield i, page.get_text("text")


def resolve_source(path_input: str | Path) -> SourceRef:
    """Resolve a path (relative to raw/ or absolute) to a paper PDF SourceRef.

    Resolution order:
      1. If the input does not end in ``.pdf``, append it.
      2. Resolve against ``raw/``.
      3. Reject if outside ``raw/papers/``, is a directory, or missing.
    """
    s = get_settings()
    raw_root = s.resolve(s.raw_dir)
    p = Path(path_input)
    if p.suffix.lower() != ".pdf":
        p = p.with_suffix(".pdf")
    if not p.is_absolute():
        p = (raw_root / p).resolve() if not str(p).startswith(str(raw_root)) else p.resolve()
    else:
        p = p.resolve()
    if not str(p).startswith(str(raw_root)):
        raise ValueError(f"Path escapes raw/: {p}")

    rel = p.relative_to(raw_root)
    parts = rel.parts
    if len(parts) != 2 or parts[0] != "papers" or not parts[1].endswith(".pdf"):
        raise ValueError(f"Path must be a PDF directly under raw/papers/: {rel}")
    if not p.is_file():
        raise FileNotFoundError(f"Paper PDF not found: {p}")

    slug = p.stem
    rel_path = f"papers/{p.name}"
    with fitz.open(p) as doc:
        title = _pdf_title(doc, slug)
    return SourceRef(p, rel_path, slug, title)


def _splitter() -> SentenceSplitter:
    s = get_settings()
    return SentenceSplitter(chunk_size=s.chunk_size, chunk_overlap=s.chunk_overlap)


def load_nodes(ref: SourceRef) -> List[TextNode]:
    """Extract pages, split each page, and attach page metadata."""
    splitter = _splitter()
    indexed_at = _now_iso()
    out: List[TextNode] = []
    chunk_id = 0
    for page_num, text in _extract_pages(ref.path):
        if not text.strip():
            continue
        doc = Document(
            text=text,
            metadata={"source_path": ref.rel_path, "title": ref.title},
        )
        for n in splitter.get_nodes_from_documents([doc]):
            content = n.get_content()
            if not content.strip():
                continue
            tn = TextNode(
                text=content,
                metadata={
                    "source_path": ref.rel_path,
                    "slug": ref.slug,
                    "title": ref.title,
                    "page": page_num,
                    "chunk_id": chunk_id,
                    "indexed_at": indexed_at,
                },
            )
            out.append(tn)
            chunk_id += 1
    return out


def iter_all_sources() -> Iterable[SourceRef]:
    """Walk raw/papers/*.pdf and yield one SourceRef per file."""
    s = get_settings()
    raw_root = s.resolve(s.raw_dir)
    papers_dir = raw_root / "papers"
    if not papers_dir.is_dir():
        return
    for pdf in sorted(papers_dir.glob("*.pdf")):
        try:
            yield resolve_source(pdf)
        except (ValueError, FileNotFoundError):
            continue
