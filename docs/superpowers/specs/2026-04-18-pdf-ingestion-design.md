# PDF Ingestion Design

**Date**: 2026-04-18
**Scope**: Replace `.tex` source tree ingestion with `.pdf` file ingestion in `paper-wiki`.

## Context

Paper Wiki currently reads academic papers from `raw/papers/<slug>/` as LaTeX source trees (`main.tex` + `\input` includes). In practice most papers are distributed as PDF only — arXiv tex sources are not always available and many journals never publish tex. This spec replaces tex support with PDF support outright. tex handling is removed, not kept as a fallback.

## Decisions

1. **Format**: PDF only. All `.tex`-related code is removed.
2. **Library**: [PyMuPDF](https://pymupdf.readthedocs.io/) (`fitz`). Fast (C-backed), wheel-installable, handles multi-column academic layouts and CJK fonts well.
3. **Directory layout**: Flat files at `raw/papers/<slug>.pdf`. No per-paper folder.
4. **Chunking**: Per-page — extract text page-by-page, run `SentenceSplitter` within each page, tag each chunk with a `page` metadata field (1-indexed).
5. **Title**: Filename stem as default; upgrade with `doc.metadata["title"]` if present and non-empty.
6. **Caching**: None. Extraction is cheap relative to embedding; reindex always re-extracts.
7. **OCR / scanned PDFs**: Out of scope. Empty-text PDFs produce 0 chunks.

## Path Conventions

| Attribute | Value |
|---|---|
| On-disk path | `raw/papers/<slug>.pdf` |
| `source_path` metadata | `papers/<slug>.pdf` |
| Slug | filename stem (e.g. `attention-is-all-you-need`) |

`resolve_source` accepts two forms:
- `papers/<slug>.pdf` — full relative path
- `papers/<slug>` — bare slug; `.pdf` is appended and existence checked

Resolution order: (1) if the input does not end in `.pdf`, append it; (2) resolve against `raw/`; (3) reject if the result is outside `raw/papers/`, is a directory, or does not exist.

## Code Changes (`src/paper_wiki/parsers.py`)

### Remove

- `_TEX_COMMENT_RE`, `_TEX_INPUT_RE`
- `_find_main_tex`, `_flatten_tex`, `_tex_title`
- `SourceRef.path` semantics as "paper folder"

### Add / Replace

```python
import fitz  # PyMuPDF

def _pdf_title(doc: fitz.Document, fallback: str) -> str:
    """Return non-empty metadata title, else fallback (slug)."""

def _extract_pages(path: Path) -> Iterable[tuple[int, str]]:
    """Yield (page_num_1indexed, text) per page via PyMuPDF."""

def resolve_source(path_input: str | Path) -> SourceRef:
    """Resolve to a paper PDF file under raw/papers/. Appends .pdf if missing."""

def load_nodes(ref: SourceRef) -> List[TextNode]:
    """Extract pages, split each page with SentenceSplitter, attach page metadata."""

def iter_all_sources() -> Iterable[SourceRef]:
    """Walk raw/papers/*.pdf."""
```

### `SourceRef` dataclass

```python
@dataclass
class SourceRef:
    path: Path       # absolute path to the .pdf file
    rel_path: str    # e.g. "papers/attention-is-all-you-need.pdf"
    slug: str        # filename stem
    title: str
```

### Node metadata schema

```python
{
    "source_path": "papers/attention-is-all-you-need.pdf",
    "slug": "attention-is-all-you-need",
    "title": "Attention Is All You Need",
    "page": 3,          # 1-indexed
    "chunk_id": 17,     # 0-based global counter within the document
    "indexed_at": "2026-04-18T12:00:00+00:00",
}
```

## Dependencies

Add to `pyproject.toml`:

```toml
"pymupdf>=1.24.0",
```

## Error Handling

| Condition | Behavior |
|---|---|
| Path does not exist | `FileNotFoundError` |
| Path is a directory or not under `raw/papers/` | `ValueError` |
| Encrypted PDF (`doc.needs_pass`) | `ValueError("Encrypted PDF not supported: <path>")` |
| Empty extracted text (scanned PDF, no OCR) | Return 0 chunks; caller sees `added_chunks: 0` |
| `fitz.FileDataError` / other parse failures | Propagate — CLI/MCP layer serializes as error response |

OCR is explicitly out of scope. Users must pre-OCR scanned PDFs before adding them.

## Documentation Updates

- `AGENTS.md` (= `CLAUDE.md`): replace "학술 논문 tex 소스", directory tree, ingest workflow paths with PDF equivalents.
- `README.md`: update "논문 tex source" → "논문 PDF 파일", adjust directory tree.
- Path-convention note: `raw/papers/<slug>/` → `raw/papers/<slug>.pdf`.

## Validation

No automated test suite exists in this repo. Validation is manual:

1. `uvx ruff check src/` — lint passes.
2. `uv run python -c "from paper_wiki import parsers, ingest, search"` — imports succeed.
3. Functional smoke test:
   - Download one real arXiv PDF into `raw/papers/attention-is-all-you-need.pdf`.
   - `uv run paper-wiki index-add papers/attention-is-all-you-need.pdf`
   - `uv run paper-wiki stats` — verify `total_chunks > 0`.
   - `uv run paper-wiki search "scaled dot product attention"` — verify top result includes a `"page": N` entry in metadata.

## Out of Scope

- OCR for scanned PDFs.
- Equation preservation (LaTeX math rendering). Would require a different backend (Marker, Nougat).
- Table extraction as structured data.
- Figure/caption cross-referencing.
- Citation graph extraction.
- Multi-PDF per paper (supplementary material).

These can be added later without disturbing this design.
