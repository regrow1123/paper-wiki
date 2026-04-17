#!/usr/bin/env bash
# Download the Qwen3 embedding + reranker GGUF models into models/.
# On airgapped machines, copy the files manually into models/ with these filenames.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p models

EMBED_REPO="Qwen/Qwen3-Embedding-0.6B-GGUF"
EMBED_REMOTE="Qwen3-Embedding-0.6B-Q8_0.gguf"
EMBED_LOCAL="Qwen3-Embedding-0.6B-Q8_0.gguf"

RERANK_REPO="ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF"
RERANK_REMOTE="qwen3-reranker-0.6b-q8_0.gguf"
RERANK_LOCAL="Qwen3-Reranker-0.6B-Q8_0.gguf"

fetch() {
    local repo="$1" remote="$2" local_name="$3"
    local dest="models/$local_name"
    if [[ -f "$dest" ]]; then
        echo "[skip] $dest exists"
        return 0
    fi
    local url="https://huggingface.co/$repo/resolve/main/$remote"
    echo "[download] $url"
    if command -v curl >/dev/null 2>&1; then
        curl -L --fail -o "$dest" "$url"
    else
        wget -O "$dest" "$url"
    fi
}

fetch "$EMBED_REPO" "$EMBED_REMOTE" "$EMBED_LOCAL"
fetch "$RERANK_REPO" "$RERANK_REMOTE" "$RERANK_LOCAL"

echo "Models in models/:"
ls -lh models/
