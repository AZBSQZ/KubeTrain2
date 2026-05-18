#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_DIR="$PROJECT_ROOT/pids"
PID_FILE="$PID_DIR/agent.pid"
AGENT_PORT="${AGENT_PORT:-8005}"

is_running() {
    local pid="${1:-}"
    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

terminate_pid() {
    local pid="$1"
    if ! is_running "$pid"; then
        return 0
    fi
    echo "Stopping pid=$pid"
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 10); do
        if ! is_running "$pid"; then
            return 0
        fi
        sleep 1
    done
    echo "Force killing pid=$pid"
    kill -9 "$pid" 2>/dev/null || true
}

if [[ -f "$PID_FILE" ]]; then
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if is_running "$pid"; then
        terminate_pid "$pid"
    fi
    rm -f "$PID_FILE"
fi

port_pids=""
if command -v lsof >/dev/null 2>&1; then
    port_pids="$(lsof -ti tcp:"$AGENT_PORT" 2>/dev/null || true)"
elif command -v fuser >/dev/null 2>&1; then
    port_pids="$(fuser "$AGENT_PORT"/tcp 2>/dev/null || true)"
fi

for pid in $port_pids; do
    if [[ "$pid" != "$$" ]] && is_running "$pid"; then
        terminate_pid "$pid"
    fi
done

echo "KubeTrain2 Agent stopped."
