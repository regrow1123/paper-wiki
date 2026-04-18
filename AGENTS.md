# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Paper Wiki — 유지보수 규약 (Schema)

이 문서는 Claude Code(또는 호환 에이전트)가 이 저장소를 **학술 논문 위키 유지보수자** 역할로 다룰 때 따라야 할 규칙이다. 사용자는 논문 PDF를 `raw/papers/<slug>.pdf`로 넣고 질문을 던진다. LLM은 `wiki/` 안의 마크다운을 읽고/쓰며, 검색은 MCP 도구(`mcp__paper-wiki__*`)로 수행한다.

## 개발 명령

```bash
# llama-server (embed:8081, rerank:8082) 기동/정지
scripts/start-llama-servers.sh
scripts/stop-llama-servers.sh

# 색인 관리 — shell에서 직접 (MCP와 동일한 로직)
uv run paper-wiki index-build                  # raw/papers/ 전체 재색인
uv run paper-wiki index-add papers/<slug>.pdf  # 단일 논문 upsert
uv run paper-wiki index-remove papers/<slug>.pdf # 단일 논문 제거
uv run paper-wiki reindex                      # index-build alias

# 조회
uv run paper-wiki search "질문" --top-k 10
uv run paper-wiki search "질문" --no-rerank    # 리랭크 스킵
uv run paper-wiki stats                        # 청크 수·소스 수
uv run paper-wiki list-sources                 # 색인된 논문
uv run paper-wiki list-raw                     # raw/papers/에 있는 PDF (색인 여부 무관)

# 포맷/린트 (ruff, line-length=100, py311)
uv run ruff check src/
uv run ruff format src/
```

테스트 스위트는 현재 없음. 기능 검증은 `stats` → `search` 한 쌍으로 수동 확인.

## 코드 아키텍처 (src/paper_wiki/)

CLI (`cli.py`) 과 MCP 서버 (`mcp_server.py`)는 **동일한 내부 함수**(`ingest.*`, `search.search`)를 호출하는 얇은 래퍼다. 두 인터페이스는 기능적으로 동등해야 하며, 새 동작을 추가할 땐 양쪽에 동시 등록한다.

| 모듈 | 역할 |
|---|---|
| `config.py` | pydantic-settings로 `.env` 로딩. `PROJECT_ROOT` 기준 경로 해석. `get_settings()`는 lru_cache. |
| `parsers.py` | `raw/papers/*.pdf`를 스캔해 `SourceRef` 생성. 모든 경로 인자의 정규화 진입점. PyMuPDF로 페이지별 텍스트 추출. |
| `embeddings.py` | llama-server `/v1/embeddings` 호출 (Qwen3-Embedding). LlamaIndex `BaseEmbedding` 구현. |
| `reranker.py` | llama-server `/v1/rerank` 호출 (Qwen3-Reranker). 재정렬 후 score 주입. |
| `dummy_llm.py` | LlamaIndex가 생성형 LLM을 요구하는 경로를 막기 위한 MockLLM. 이 저장소는 순수 검색만 한다. |
| `index.py` | Chroma 컬렉션 핸들·메타데이터 집계 (`collection_stats`). 직접 Chroma를 건드리는 유일한 파일. |
| `ingest.py` | `ingest_one` / `remove_one` / `reindex_all` — chunk → embed → upsert의 단일 출처. |
| `search.py` | vector top-k=30 → rerank → top-k=10 파이프라인. |
| `cli.py` | Typer 앱. 출력은 전부 JSON. |
| `mcp_server.py` | fastmcp 서버. 도구명은 `search`, `rerank`, `get_document`, `index_add`, `index_remove`, `reindex`, `stats`, `list_sources`. |

### 중요한 경로 규약

- **모든 경로 인자는 `raw/` 기준 상대 경로**로 통일한다 (예: `papers/my-paper`). `parsers.resolve_source`가 정규화한다.
- `raw/papers/*.pdf` 파일만 색인 대상. 디렉토리·다른 확장자는 거부된다.
- 경로 인자에 `.pdf` 확장자 생략 가능 (`papers/my-paper` → `papers/my-paper.pdf` 자동 부가).
- Chroma와 `wiki/`는 **dual-write 금지**. 색인은 MCP 도구/CLI로만 수정한다.
- 임베딩 모델을 바꾸면 차원이 달라지므로 `storage/chroma/`를 지우고 `reindex`.

## 구성 요소

| 레이어 | 위치 | 소유자 | 설명 |
|---|---|---|---|
| 원본 | `raw/papers/` | 사용자 | immutable. 논문 PDF 저장소. LLM은 읽기만. |
| 위키 | `wiki/` | LLM | 요약·개념·인물·합성 페이지 (한국어 + 영문 용어). |
| 색인 | `storage/chroma/` | 엔진 | Chroma 영속 벡터 DB. 재생성 가능. |
| 검색 엔진 | llama-server + LlamaIndex | 엔진 | Qwen3-Embedding(`/v1/embeddings`) + Qwen3-Reranker(`/v1/rerank`). |

### 디렉토리

```
raw/
  papers/<slug>.pdf                   # 학술 논문 PDF
  assets/                             # 공용 이미지 등
wiki/
  index.md                            # 콘텐츠 카탈로그 (매 ingest마다 갱신)
  log.md                              # 시간순 기록 (매 ingest/query/lint마다 append)
  sources/<slug>.md                   # 논문 1건당 1페이지 요약
  entities/<slug>.md                  # 인물·기관·시스템·프로젝트
  concepts/<slug>.md                  # 주제·방법론·이론
  synthesis/<slug>.md                 # 비교·종합·thesis
```

### 파일 frontmatter

모든 `wiki/` 페이지는 YAML frontmatter로 시작한다.

```yaml
---
type: source | entity | concept | synthesis
title: "Title in Korean (English term if applicable)"
slug: my-slug
tags: [tag1, tag2]
sources:
  - raw/papers/<slug>.pdf
created: 2026-04-17
updated: 2026-04-17
---
```

- `slug`는 파일명과 일치.
- `sources`는 `raw/` 기준 상대 경로 리스트 (`source` 타입은 1개, 그 외 다수 가능).
- `tags`는 kebab-case 영어 권장.

## 언어·스타일 규칙

- 본문은 **한국어**로 작성한다.
- 핵심 용어는 **괄호 안에 영문을 병기**한다. 예: "검색 증강 생성(RAG)", "어텐션(attention)".
- 원문 인용·수식·코드·고유명사는 영문 그대로 둔다.
- 페이지 간 연결은 Obsidian `[[wiki-link]]` 문법을 사용한다 (예: `[[entities/smith-john]]`).

## 워크플로우

### Ingest (새 논문 추가)

사용자가 `raw/papers/<slug>.pdf`로 새 논문을 추가하면 다음을 순서대로 수행:

1. **색인 추가**: `mcp__paper-wiki__index_add(path)` 호출. 반환된 `added_chunks`를 확인.
2. **원문 읽기**: PDF 원문은 `search` 결과의 청크로 확인하고, 필요하면 외부 뷰어(또는 `get_document`로 바이너리) 사용.
3. **사용자와 핵심 요약 논의** (1~3문장 takeaway).
4. **sources 페이지 작성**: `wiki/sources/<slug>.md` 새로 만들거나 갱신. 최소 섹션:
   - Summary (3~7줄)
   - Key Takeaways (불릿 3~5개)
   - Entities / Concepts (링크)
   - Raw (`sources` frontmatter에 원문 경로)
5. **entities / concepts 업데이트**: 논문에서 언급된 인물·기관·개념 각각을 해당 페이지에 `### Sources` 섹션으로 역링크 추가. 새 개념이면 새 페이지 생성.
6. **index.md 갱신**: 새 페이지들을 알맞은 카테고리 아래 1줄 요약과 함께 등재.
7. **log.md 추가** (append):
   ```
   ## [2026-04-17] ingest | <title>
   - source: raw/papers/<slug>.pdf
   - pages touched: wiki/sources/..., wiki/entities/..., wiki/concepts/...
   ```
8. **커밋** (사용자가 허용하면): `ingest: add <title>`.

### Query (질문·합성)

1. `mcp__paper-wiki__search(query, top_k=10)` 호출.
2. 상위 청크의 `path` → 해당 `wiki/sources/<slug>.md` 존재 확인 (없으면 lint 대상으로 기록).
3. 답변을 합성하되 **`wiki/` 페이지를 1차 근거**로, 원문은 2차로 참조. 각 주장마다 `source: raw/...` 또는 `wiki/...` 인용.
4. 가치 있는 결과는 `wiki/synthesis/<slug>.md`로 저장 (비교표, 요약 보고서, 차트 등).
5. `log.md`에 항목 추가:
   ```
   ## [2026-04-17] query | <short description>
   - top sources: [...]
   - saved: wiki/synthesis/...
   ```

### Lint (헬스 체크)

- `mcp__paper-wiki__stats` / `mcp__paper-wiki__list_sources`로 색인 상태 조회.
- `wiki/sources/`와 대조:
  - 색인에는 있는데 `wiki/sources/` 페이지가 없는 논문 → 요약 누락 (ingest 재실행).
  - `wiki/sources/`에는 있는데 색인에 없는 논문 → `index_add` 재실행.
- 고아 페이지(인바운드 링크 없음)·모순(`source` 메타가 동일한데 페이지별 결론 상이) 탐지.
- `log.md`에 결과 append.

## 도구 호출 규칙

- **경로 인자는 항상 `raw/` 기준 상대 경로**를 사용한다 (예: `papers/my-paper`).
- 새 wiki 페이지를 만들기 전에 기존 동일 `slug` 페이지 존재 여부를 확인한다.

## 커밋 컨벤션 (영문 conventional commits)

- `ingest: add <title>` — 새 논문 요약 포함한 커밋
- `wiki: update <page>` — 기존 페이지 수정
- `wiki: add <page>` — 신규 entity/concept/synthesis
- `lint: <fix description>` — 정리 작업
- `infra: <change>` — 스크립트/설정 변경

## 검색 엔진 현황

- **임베딩**: `Qwen/Qwen3-Embedding-0.6B-GGUF` (Q8_0), llama-server `/v1/embeddings`.
- **리랭커**: `ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF`, llama-server `/v1/rerank`.
- 리트리벌: vector top-k=30 → rerank → 반환 top-k=10 (기본값, `.env`로 조정 가능).
- 검색/인덱싱은 **MCP 도구**를 경유한다. 직접 Chroma를 건드리지 않는다.

## 추가 원칙

- `raw/`는 수정하지 않는다. 교정·리포맷은 별도 wiki 페이지로.
- 색인 관리는 단일 출처(MCP 도구)로만 수행해 `wiki/`와 Chroma가 dual-write 되는 일이 없도록 한다.
- 위키 본문에 긴 원문 인용이 필요하면 `> 블록`으로 표시하고 반드시 출처 경로를 명시한다.
