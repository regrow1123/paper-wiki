"""Runtime configuration loaded from .env / env vars."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llama_server_bin: Path = Field(
        default=Path.home() / "llama.cpp/build/bin/llama-server"
    )
    embed_model_path: Path = Path("models/Qwen3-Embedding-0.6B-Q8_0.gguf")
    rerank_model_path: Path = Path("models/Qwen3-Reranker-0.6B-Q8_0.gguf")

    embed_host: str = "127.0.0.1"
    embed_port: int = 8081
    rerank_host: str = "127.0.0.1"
    rerank_port: int = 8082
    llama_ngl: int = 0

    chroma_dir: Path = Path("storage/chroma")
    chroma_collection: str = "llm_wiki"
    raw_dir: Path = Path("raw")
    wiki_dir: Path = Path("wiki")

    chunk_size: int = 512
    chunk_overlap: int = 64

    top_k_retrieve: int = 30
    top_k_rerank: int = 10

    embed_timeout: float = 120.0
    rerank_timeout: float = 120.0

    @property
    def embed_url(self) -> str:
        return f"http://{self.embed_host}:{self.embed_port}"

    @property
    def rerank_url(self) -> str:
        return f"http://{self.rerank_host}:{self.rerank_port}"

    def resolve(self, p: Path) -> Path:
        """Resolve a possibly-relative path against the project root."""
        p = Path(p)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
