#!/usr/bin/env bash
# Stop llama-server processes started by start-llama-servers.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

stop_one() {
    local name="$1"
    local pidfile="logs/${name}.pid"
    if [[ -f "$pidfile" ]]; then
        local pid
        pid="$(cat "$pidfile")"
        if kill -0 "$pid" 2>/dev/null; then
            echo "[$name] stopping pid=$pid"
            kill "$pid"
            for _ in {1..20}; do
                sleep 0.2
                kill -0 "$pid" 2>/dev/null || break
            done
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$pidfile"
    else
        echo "[$name] no pid file"
    fi
}

stop_one embed
stop_one rerank
