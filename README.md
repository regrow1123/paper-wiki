# Paper Wiki

학술 논문 전용 개인 지식베이스(personal knowledge base) 엔진.

- `raw/papers/<slug>/`에 논문 tex 소스를 넣고,
- `wiki/`에 LLM이 유지하는 한국어 마크다운 지식 그래프를 쌓으며,
- Claude Code / 호환 에이전트가 **MCP 도구**로 검색·인덱싱·통계 조회를 수행한다.

검색엔진은 LlamaIndex + Chroma, 임베딩/리랭커는 `llama.cpp`의 `llama-server`를 CPU로 띄워 Qwen3-Embedding-0.6B-Q8 / Qwen3-Reranker-0.6B-Q8을 서빙한다. LlamaIndex 자체는 생성형 LLM 없이 `MockLLM`으로 동작시켜 순수 검색 파이프라인으로만 쓴다.

## 빠른 시작

### 1. 선행 조건

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/) ≥ 0.4
- `llama.cpp`가 빌드되어 있어야 함 (`llama-server` 바이너리). 예: `/home/sund4y/llama.cpp/build/bin/llama-server`
- GGUF 모델 파일 (아래 스크립트 또는 수동 배치)

### 2. 설치

```bash
git clone <this-repo> paper-wiki && cd paper-wiki
uv sync
cp .env.example .env       # 필요시 경로·포트 편집
scripts/fetch-models.sh     # models/에 GGUF 다운로드 (airgapped면 수동 복사)
```

### 3. llama-server 기동

```bash
scripts/start-llama-servers.sh   # embed:8081, rerank:8082
scripts/stop-llama-servers.sh    # 종료
```

헬스체크:

```bash
curl -s http://127.0.0.1:8081/health
curl -s http://127.0.0.1:8082/health
```

### 4. 색인 빌드

```bash
uv run paper-wiki index-build    # raw/papers/ 전체 스캔
uv run paper-wiki stats          # 현황
uv run paper-wiki search "질문 예시"
```

### 5. Claude Code 연동

`.mcp.json`이 프로젝트 루트에 이미 있다. Claude Code를 이 디렉토리에서 열면 `paper-wiki` MCP 서버가 자동 등록된다. 도구 이름은 `mcp__paper-wiki__search`, `mcp__paper-wiki__index_add` 등.

`AGENTS.md`(및 symlink `CLAUDE.md`)에 Ingest / Query / Lint 워크플로 규약이 들어있다. 새 세션은 이 파일을 읽고 그대로 따른다.

## 주요 디렉토리

```
raw/                   # 원본 (immutable)
  papers/<slug>/       # 논문 tex 소스
  assets/              # 공용 에셋
wiki/                  # LLM이 쓰는 마크다운
  index.md, log.md
  sources/ entities/ concepts/ synthesis/
storage/chroma/        # 벡터 DB (재생성 가능, gitignore)
models/                # GGUF (gitignore)
logs/                  # llama-server 로그/PID (gitignore)
scripts/               # llama-server 기동·모델 다운로드
src/paper_wiki/        # Python 패키지
```

## 설정

`.env`로 경로·포트·청크 크기·리트리벌 파라미터를 조정한다. 전체 키는 `.env.example` 참고.

## 이식

다른 머신으로 옮길 때:

1. repo 클론 + `uv sync`
2. `models/`에 GGUF 배치 (또는 `scripts/fetch-models.sh`)
3. `.env` 작성 (`LLAMA_SERVER_BIN` 경로만 조정하면 대개 끝)
4. `scripts/start-llama-servers.sh`
5. `uv run paper-wiki reindex` — `raw/papers/`를 읽어 `storage/chroma/`를 재생성

`storage/`와 `logs/`, `models/`는 git 대상이 아니다. `raw/`와 `wiki/`만 버전 관리한다.

## MCP 도구

| 이름 | 용도 |
|---|---|
| `search` | 벡터 검색 + 리랭크 |
| `rerank` | 외부 텍스트 즉석 랭킹 |
| `get_document` | `raw/` 파일 원문 반환 |
| `index_add` | 논문 upsert |
| `index_remove` | 논문 삭제 |
| `reindex` | 전체 재색인 |
| `stats` | 색인 통계 |
| `list_sources` | 색인된 논문 목록 |

자세한 스펙은 `src/paper_wiki/mcp_server.py` 참고.

## 트러블슈팅

- **`llama-server not found`** → `.env`의 `LLAMA_SERVER_BIN`을 조정.
- **`Port X is already in use`** → 기존 서버가 살아있거나 다른 프로세스가 점유. `stop-llama-servers.sh` 또는 포트 변경.
- **CUDA 장비에서도 CPU로 강제**하려면 `.env`의 `LLAMA_NGL=0` 유지.
- **임베딩 차원 불일치** — 모델을 바꾸면 `storage/chroma/`를 지우고 재색인.
- **리랭크 404** — 빌드가 오래된 llama.cpp일 수 있음. `--reranking` 지원 버전으로 업데이트.
