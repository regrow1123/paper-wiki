#!/usr/bin/env bash
# Start embedding and reranker llama.cpp servers in the background.
# Logs to logs/embed.log and logs/rerank.log. PIDs in logs/*.pid.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-$HOME/llama.cpp/build/bin/llama-server}"
EMBED_MODEL_PATH="${EMBED_MODEL_PATH:-models/Qwen3-Embedding-0.6B-Q8_0.gguf}"
RERANK_MODEL_PATH="${RERANK_MODEL_PATH:-models/Qwen3-Reranker-0.6B-Q8_0.gguf}"
EMBED_HOST="${EMBED_HOST:-127.0.0.1}"
EMBED_PORT="${EMBED_PORT:-8081}"
RERANK_HOST="${RERANK_HOST:-127.0.0.1}"
RERANK_PORT="${RERANK_PORT:-8082}"
LLAMA_NGL="${LLAMA_NGL:-0}"

if [[ ! -x "$LLAMA_SERVER_BIN" ]]; then
    echo "llama-server not found at: $LLAMA_SERVER_BIN" >&2
    echo "Set LLAMA_SERVER_BIN in .env." >&2
    exit 1
fi

mkdir -p logs

check_port() {
    local host="$1" port="$2"
    if (echo > "/dev/tcp/$host/$port") 2>/dev/null; then
        echo "Port $host:$port is already in use." >&2
        return 1
    fi
    return 0
}

start_server() {
    local name="$1"; local model="$2"; local host="$3"; local port="$4"; shift 4
    local pidfile="logs/${name}.pid"
    local logfile="logs/${name}.log"

    if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        echo "[$name] already running (pid $(cat "$pidfile"))"
        return 0
    fi
    if [[ ! -f "$model" ]]; then
        echo "[$name] model file not found: $model" >&2
        return 1
    fi
    check_port "$host" "$port" || return 1

    local device_flag=()
    if [[ "$LLAMA_NGL" == "0" ]]; then
        # Force CPU backend entirely (avoids CUDA init / KV cache allocation).
        device_flag=(--device none)
    fi

    echo "[$name] starting on $host:$port (model=$model, ngl=$LLAMA_NGL)"
    nohup "$LLAMA_SERVER_BIN" \
        -m "$model" \
        --host "$host" --port "$port" \
        --n-gpu-layers "$LLAMA_NGL" \
        "${device_flag[@]}" \
        --ctx-size 8192 --parallel 2 \
        --batch-size 2048 --ubatch-size 2048 \
        "$@" \
        > "$logfile" 2>&1 &
    echo $! > "$pidfile"
    echo "[$name] pid=$(cat "$pidfile"), log=$logfile"
}

start_server embed "$EMBED_MODEL_PATH" "$EMBED_HOST" "$EMBED_PORT" \
    --embedding --pooling last

start_server rerank "$RERANK_MODEL_PATH" "$RERANK_HOST" "$RERANK_PORT" \
    --reranking

echo "Waiting for servers to become ready..."
for i in {1..60}; do
    if curl -fsS "http://$EMBED_HOST:$EMBED_PORT/health" >/dev/null 2>&1 \
       && curl -fsS "http://$RERANK_HOST:$RERANK_PORT/health" >/dev/null 2>&1; then
        echo "Both servers are healthy."
        exit 0
    fi
    sleep 1
done

echo "Timed out waiting for servers. Check logs/embed.log and logs/rerank.log." >&2
exit 1
