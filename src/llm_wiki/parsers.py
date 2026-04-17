"""Source discovery and chunking for `.md` memos and `.tex` papers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document, TextNode

from .config import Settings, get_settings

_TEX_COMMENT_RE = re.compile(r"(?<!\\)%.*?$", re.MULTILINE)
_TEX_INPUT_RE = re.compile(r"\\(?:input|include|subfile)\{([^}]+)\}")


@dataclass
class SourceRef:
    path: Path            # absolute path
    rel_path: str         # relative to raw/ (stored in metadata)
    source_type: str      # "memo" | "paper"
    slug: str             # folder name (paper) or basename stem (memo)
    title: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _markdown_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line.lstrip("# ").strip()
    return fallback


def _tex_title(text: str, fallback: str) -> str:
    m = re.search(r"\\title\{([^}]+)\}", text)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    return fallback


def resolve_source(path_input: str | Path) -> SourceRef:
    """Classify a source path relative to raw/ and extract a slug/title."""
    s = get_settings()
    raw_root = s.resolve(s.raw_dir)
    p = Path(path_input)
    if not p.is_absolute():
        p = (raw_root / p).resolve() if not str(p).startswith(str(raw_root)) else p.resolve()
    else:
        p = p.resolve()
    if not str(p).startswith(str(raw_root)):
        raise ValueError(f"Path escapes raw/: {p}")

    rel = p.relative_to(raw_root)
    parts = rel.parts
    if parts and parts[0] == "memos":
        if not p.is_file():
            raise FileNotFoundError(f"Memo file not found: {p}")
        slug = p.stem
        title = _markdown_title(p.read_text(encoding="utf-8"), slug)
        return SourceRef(p, str(rel), "memo", slug, title)

    if parts and parts[0] == "papers":
        # Expect raw/papers/<slug>/... — resolve to the paper folder.
        if len(parts) < 2:
            raise ValueError("Paper path must be under raw/papers/<slug>/")
        slug = parts[1]
        folder = raw_root / "papers" / slug
        if not folder.is_dir():
            raise FileNotFoundError(f"Paper folder not found: {folder}")
        main_tex = _find_main_tex(folder)
        title = _tex_title(_flatten_tex(main_tex), slug) if main_tex else slug
        # Use the folder as the logical source path for upsert identity.
        return SourceRef(folder, f"papers/{slug}", "paper", slug, title)

    raise ValueError(f"Path is neither a memo nor a paper: {rel}")


def _find_main_tex(folder: Path) -> Path | None:
    for candidate in ("main.tex", "paper.tex", "ms.tex"):
        c = folder / candidate
        if c.is_file():
            return c
    # Otherwise pick the .tex file that contains \documentclass.
    for tex in sorted(folder.rglob("*.tex")):
        try:
            if "\\documentclass" in tex.read_text(encoding="utf-8", errors="ignore"):
                return tex
        except OSError:
            continue
    # Fallback to any .tex file.
    for tex in sorted(folder.rglob("*.tex")):
        return tex
    return None


def _flatten_tex(entry: Path, seen: set[Path] | None = None, depth: int = 0) -> str:
    """Inline \\input / \\include / \\subfile references, strip comments."""
    seen = seen if seen is not None else set()
    if depth > 8 or entry in seen or not entry.is_file():
        return ""
    seen.add(entry)
    try:
        text = entry.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    text = _TEX_COMMENT_RE.sub("", text)

    def repl(m: re.Match[str]) -> str:
        ref = m.group(1).strip()
        sub = entry.parent / (ref if ref.endswith(".tex") else f"{ref}.tex")
        return "\n" + _flatten_tex(sub, seen, depth + 1) + "\n"

    return _TEX_INPUT_RE.sub(repl, text)


def _splitter() -> SentenceSplitter:
    s = get_settings()
    return SentenceSplitter(chunk_size=s.chunk_size, chunk_overlap=s.chunk_overlap)


def _make_nodes(text: str, ref: SourceRef) -> List[TextNode]:
    doc = Document(text=text, metadata={"source_path": ref.rel_path, "title": ref.title})
    nodes = _splitter().get_nodes_from_documents([doc])
    indexed_at = _now_iso()
    out: List[TextNode] = []
    for i, n in enumerate(nodes):
        tn = TextNode(
            text=n.get_content(),
            metadata={
                "source_path": ref.rel_path,
                "source_type": ref.source_type,
                "slug": ref.slug,
                "title": ref.title,
                "chunk_id": i,
                "indexed_at": indexed_at,
            },
        )
        out.append(tn)
    return out


def load_nodes(ref: SourceRef) -> List[TextNode]:
    if ref.source_type == "memo":
        text = ref.path.read_text(encoding="utf-8")
    elif ref.source_type == "paper":
        main_tex = _find_main_tex(ref.path)
        if not main_tex:
            raise FileNotFoundError(f"No .tex entrypoint inside {ref.path}")
        text = _flatten_tex(main_tex)
    else:  # pragma: no cover
        raise ValueError(f"Unknown source_type: {ref.source_type}")
    return _make_nodes(text, ref)


def iter_all_sources(source_type: str | None = None) -> Iterable[SourceRef]:
    """Walk raw/ and yield one SourceRef per memo / paper folder."""
    s = get_settings()
    raw_root = s.resolve(s.raw_dir)
    if source_type in (None, "memo"):
        memos_dir = raw_root / "memos"
        if memos_dir.is_dir():
            for f in sorted(memos_dir.rglob("*.md")):
                try:
                    yield resolve_source(f)
                except (ValueError, FileNotFoundError):
                    continue
    if source_type in (None, "paper"):
        papers_dir = raw_root / "papers"
        if papers_dir.is_dir():
            for folder in sorted(p for p in papers_dir.iterdir() if p.is_dir()):
                try:
                    yield resolve_source(folder)
                except (ValueError, FileNotFoundError):
                    continue
