# PDF Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace tex source ingestion with PDF ingestion in `paper-wiki`, storing per-page chunks with page metadata.

**Architecture:** Contained rewrite of `src/paper_wiki/parsers.py`. PyMuPDF extracts text per page; each page is split independently with `SentenceSplitter` and tagged with a `page` metadata field. Directory layout is flattened to `raw/papers/<slug>.pdf`. CLI, MCP server, index, ingest, search, config all remain structurally unchanged — they only carry updated docstrings / help text.

**Tech Stack:** PyMuPDF (`pymupdf>=1.24.0`) for PDF parsing; existing LlamaIndex `SentenceSplitter` for chunking; existing Chroma/llama-server pipeline downstream.

**Validation strategy:** This repo has no pytest suite (explicit project convention — see `AGENTS.md`). Validation per task is ruff + Python import smoke test; end-to-end validation is a manual functional test with a real arXiv PDF (Task 5).

---

### Task 1: Add PyMuPDF dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add pymupdf to dependencies**

Edit `pyproject.toml` — append `"pymupdf>=1.24.0",` to the `dependencies` array so the block reads:

```toml
dependencies = [
    "llama-index-core>=0.12.0",
    "llama-index-vector-stores-chroma>=0.4.0",
    "chromadb>=0.5.20",
    "httpx>=0.27.0",
    "fastmcp>=0.2.0",
    "typer>=0.12.0",
    "pydantic>=2.8.0",
    "pydantic-settings>=2.5.0",
    "python-dotenv>=1.0.0",
    "pymupdf>=1.24.0",
]
```

- [ ] **Step 2: Install the new dependency**

Run: `uv sync`
Expected: `pymupdf` and its transitive deps installed; exit 0.

- [ ] **Step 3: Verify PyMuPDF imports**

Run: `uv run python -c "import fitz; print(fitz.__doc__.splitlines()[0])"`
Expected: output starts with `PyMuPDF ...` (version string), exit 0.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add pymupdf dependency for PDF ingestion"
```

---

### Task 2: Rewrite `parsers.py` for PDF

**Files:**
- Modify: `src/paper_wiki/parsers.py` (full rewrite of tex-specific code)

- [ ] **Step 1: Replace file contents**

Overwrite `src/paper_wiki/parsers.py` with exactly this content:

```python
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
```

- [ ] **Step 2: Run ruff**

Run: `uvx ruff check src/`
Expected: `All checks passed!`

- [ ] **Step 3: Smoke-test imports**

Run: `uv run python -c "from paper_wiki import parsers, ingest, search, cli, mcp_server; print('OK')"`
Expected: prints `OK`, exit 0.

- [ ] **Step 4: Smoke-test resolve_source rejection paths**

Run:

```bash
uv run python -c "
from paper_wiki.parsers import resolve_source
# Non-existent path under papers/ should raise FileNotFoundError
try:
    resolve_source('papers/does-not-exist.pdf')
except FileNotFoundError as e:
    print('OK: FileNotFoundError raised')
# Outside papers/ should raise ValueError
try:
    resolve_source('assets/nope.pdf')
except ValueError as e:
    print('OK: ValueError raised')
"
```

Expected: two `OK:` lines.

- [ ] **Step 5: Commit**

```bash
git add src/paper_wiki/parsers.py
git commit -m "feat: replace tex parser with PyMuPDF-based PDF ingestion"
```

---

### Task 3: Update CLI / MCP docstrings that still reference tex layout

**Files:**
- Modify: `src/paper_wiki/cli.py` — `list-raw` help text
- Modify: `src/paper_wiki/mcp_server.py` — `get_document` tool docstring

- [ ] **Step 1: Update `cli.py` list-raw help**

In `src/paper_wiki/cli.py`, locate the `list_raw_cmd` function and replace its docstring:

```python
@app.command("list-raw")
def list_raw_cmd() -> None:
    """List paper PDFs present under raw/papers/ (not necessarily indexed)."""
    refs = [{"path": r.rel_path, "title": r.title} for r in iter_all_sources()]
    _print(refs)
```

(Only the docstring line changes from `List paper folders present under raw/papers/ (not necessarily indexed).` to `List paper PDFs present under raw/papers/ (not necessarily indexed).`.)

- [ ] **Step 2: Update `mcp_server.py` get_document docstring**

In `src/paper_wiki/mcp_server.py`, replace the `get_document` tool's docstring so it reads:

```python
@mcp.tool
def get_document(path: str) -> dict[str, Any]:
    """Return the raw content of a file under raw/. Truncates at ~1 MB.

    Pass the path to a paper PDF (e.g. 'papers/<slug>.pdf').
    Returns {path, text, truncated, size}.
    """
```

Note: the returned `text` will be UTF-8 decoded bytes from a binary PDF and will mostly be unreadable — this tool is retained for non-PDF auxiliary files (e.g. future sibling notes) and for inspecting raw bytes when debugging. Consumers that want parsed text should use `search` results.

- [ ] **Step 3: Run ruff**

Run: `uvx ruff check src/`
Expected: `All checks passed!`

- [ ] **Step 4: Verify CLI help still renders**

Run: `uv run paper-wiki list-raw --help`
Expected: help text shows `List paper PDFs present under raw/papers/`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add src/paper_wiki/cli.py src/paper_wiki/mcp_server.py
git commit -m "docs: update CLI/MCP help text for PDF layout"
```

---

### Task 4: Update project documentation

**Files:**
- Modify: `AGENTS.md` (symlinked as `CLAUDE.md`)
- Modify: `README.md`

- [ ] **Step 1: Update `AGENTS.md`**

Replace these specific passages in `AGENTS.md`:

(1) The opening paragraph of the "Paper Wiki — 유지보수 규약" section:

**Old:**
> 사용자는 원문 논문 소스(tex)를 `raw/papers/<slug>/`에 넣고 질문을 던진다.

**New:**
> 사용자는 논문 PDF를 `raw/papers/<slug>.pdf`로 넣고 질문을 던진다.

(2) The `uv run paper-wiki index-add` example comment in the 개발 명령 block:

**Old:** `uv run paper-wiki index-add papers/<slug>      # 단일 논문 upsert`
**New:** `uv run paper-wiki index-add papers/<slug>.pdf  # 단일 논문 upsert`

Also update `index-remove` and `list-raw` comments accordingly (`list-raw` comment becomes `# raw/papers/에 있는 PDF (색인 여부 무관)`).

(3) The `parsers.py` row in the 코드 아키텍처 table:

**Old:** `` `parsers.py` | `raw/papers/<slug>/` 트리를 스캔해 `SourceRef` 생성. 모든 경로 인자의 정규화 진입점. tex `\input`/`\include`를 재귀 플래튼. ``
**New:** `` `parsers.py` | `raw/papers/*.pdf`를 스캔해 `SourceRef` 생성. 모든 경로 인자의 정규화 진입점. PyMuPDF로 페이지별 텍스트 추출. ``

(4) 중요한 경로 규약 bullets:

**Old:**
- `raw/papers/<slug>/` 아래가 아닌 경로는 거부된다.

**New:**
- `raw/papers/*.pdf` 파일만 색인 대상. 디렉토리·다른 확장자는 거부된다.
- 경로 인자에 `.pdf` 확장자 생략 가능 (`papers/my-paper` → `papers/my-paper.pdf` 자동 부가).

(5) 디렉토리 트리 block — replace the `raw/` subtree:

**Old:**
```
raw/
  papers/<slug>/                      # 학술 논문 tex 소스
    main.tex, sections/, figures/, refs.bib
  assets/                             # 공용 이미지 등
```

**New:**
```
raw/
  papers/<slug>.pdf                   # 학술 논문 PDF
  assets/                             # 공용 이미지 등
```

(6) `sources` frontmatter example:

**Old:** `  - raw/papers/<slug>/main.tex`
**New:** `  - raw/papers/<slug>.pdf`

(7) Ingest workflow Step 1 and log.md example:

**Old:**
> 사용자가 `raw/papers/<slug>/` 아래에 새 논문을 추가하면 다음을 순서대로 수행:

**New:**
> 사용자가 `raw/papers/<slug>.pdf`로 새 논문을 추가하면 다음을 순서대로 수행:

log.md example: replace `- source: raw/papers/<slug>` with `- source: raw/papers/<slug>.pdf`.

(8) "원문 읽기" step 2:

**Old:** `mcp__paper-wiki__get_document(path)` 또는 Read 도구로 tex 원문 확인.
**New:** PDF 원문은 `search` 결과의 청크로 확인하고, 필요하면 외부 뷰어(또는 `get_document`로 바이너리) 사용.

- [ ] **Step 2: Update `README.md`**

Replace:

(1) The intro bullet list:

**Old:** `- `raw/papers/<slug>/`에 논문 tex 소스를 넣고,`
**New:** `- `raw/papers/<slug>.pdf`에 논문 PDF를 넣고,`

(2) "주요 디렉토리" tree block — replace the `raw/` subtree the same way as Task 4 Step 1 item (5).

(3) "MCP 도구" table row for `index_add`: keep, but description "논문 upsert" is already correct.

- [ ] **Step 3: Verify CLAUDE.md symlink still resolves**

Run: `cat CLAUDE.md | head -5`
Expected: first 5 lines match `AGENTS.md` (which now starts with `# CLAUDE.md` heading).

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md README.md
git commit -m "docs: update conventions to PDF-based layout"
```

---

### Task 5: Manual functional smoke test

This task is verification-only — no code changes, no commit. Use a real arXiv PDF to exercise the full pipeline.

**Prerequisites:** `llama-server` processes must be running (embed:8081, rerank:8082). If not:

```bash
scripts/start-llama-servers.sh
```

- [ ] **Step 1: Fetch a test PDF**

Run:

```bash
mkdir -p raw/papers
curl -L -o raw/papers/attention-is-all-you-need.pdf \
  https://arxiv.org/pdf/1706.03762
```

Expected: file saved, size > 500 KB.

- [ ] **Step 2: Index the PDF**

Run: `uv run paper-wiki index-add papers/attention-is-all-you-need.pdf`
Expected: JSON output with `"added_chunks"` > 0 and `"title"` showing `"Attention Is All You Need"` (or the filename stem if metadata is absent).

- [ ] **Step 3: Check stats**

Run: `uv run paper-wiki stats`
Expected: JSON with `"total_chunks"` > 0 and `"source_count": 1`.

- [ ] **Step 4: Run a search and verify page metadata**

Run: `uv run paper-wiki search "scaled dot product attention" --top-k 3`
Expected: JSON array of ≥1 hit. Each hit's `metadata` contains a `"page"` field with an integer ≥ 1.

- [ ] **Step 5: Rejection test — bad path**

Run: `uv run paper-wiki index-add papers/nonexistent.pdf`
Expected: non-zero exit with an error mentioning `FileNotFoundError` / not found.

- [ ] **Step 6: Clean up**

Decide whether to keep the test PDF. If removing:

```bash
uv run paper-wiki index-remove papers/attention-is-all-you-need.pdf
rm raw/papers/attention-is-all-you-need.pdf
```

Expected: `removed_chunks` matches the earlier `added_chunks`.

No commit for this task.

---

## Self-Review

**Spec coverage:**
- Flat layout `raw/papers/<slug>.pdf` → Task 2 (`resolve_source`, `iter_all_sources`) + Task 4 (docs) ✓
- PyMuPDF library → Task 1 (dep) + Task 2 (impl) ✓
- Per-page chunking with `page` metadata → Task 2 `load_nodes` ✓
- Title: filename stem + PDF metadata override → Task 2 `_pdf_title` ✓
- No caching → Task 2 extracts on every call ✓
- Encrypted PDF raises ValueError → Task 2 `_extract_pages` ✓
- Empty text yields 0 chunks → Task 2 `load_nodes` skips empty pages/chunks ✓
- Path resolution order (append `.pdf`, validate under `raw/papers/`) → Task 2 `resolve_source` ✓
- Doc updates (AGENTS.md / README.md / CLI help / MCP tool docstring) → Tasks 3 + 4 ✓
- Manual smoke test with real arXiv paper → Task 5 ✓

**Placeholder scan:** none.

**Type consistency:** `SourceRef(path, rel_path, slug, title)` used consistently in parsers.py; `ingest.py` / `search.py` / `cli.py` / `mcp_server.py` only touch `ref.rel_path` and `ref.title` which are unchanged from current implementation. No signature mismatches.
