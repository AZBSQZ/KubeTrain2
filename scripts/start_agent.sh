#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENT_FILE="$PROJECT_ROOT/agent/te_agent.py"
LOG_DIR="$PROJECT_ROOT/logs"
PID_DIR="$PROJECT_ROOT/pids"
PID_FILE="$PID_DIR/agent.pid"
LOG_FILE="$LOG_DIR/agent.log"
SERVER_URL="${KUBETRAIN_SERVER:-${SERVER_URL:-${1:-}}}"
AGENT_PORT="${AGENT_PORT:-8005}"
CONDA_ENV="${CONDA_ENV:-bs}"
PYTHON_CMD="${PYTHON_CMD:-}"
WORKER_ID="${WORKER_ID:-}"
POOL_ID="${POOL_ID:-}"
MAX_TASKS="${MAX_TASKS:-2}"
HEARTBEAT="${HEARTBEAT:-30}"
TOKEN="${TOKEN:-}"
LABELS="${LABELS:-}"
CAPABILITIES="${CAPABILITIES:-}"

mkdir -p "$LOG_DIR" "$PID_DIR"

is_running() {
    local pid="${1:-}"
    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

if [[ -z "$SERVER_URL" ]]; then
    echo "Usage: KUBETRAIN_SERVER=http://<server-ip>:8010 $0" >&2
    echo "   or: $0 http://<server-ip>:8010" >&2
    exit 1
fi

if [[ ! -f "$AGENT_FILE" ]]; then
    echo "ERROR: agent file not found: $AGENT_FILE" >&2
    exit 1
fi

if [[ -f "$PID_FILE" ]]; then
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if is_running "$pid"; then
        echo "KubeTrain2 Agent is already running, pid=$pid, port=$AGENT_PORT"
        exit 0
    fi
    rm -f "$PID_FILE"
fi

if [[ -n "$PYTHON_CMD" ]]; then
    PY_RUNNER="$PYTHON_CMD"
elif command -v conda >/dev/null 2>&1; then
    PY_RUNNER="conda run -n $CONDA_ENV python"
elif [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    PY_RUNNER="$PROJECT_ROOT/.venv/bin/python"
else
    PY_RUNNER="python3"
fi

ARGS=("$AGENT_FILE" "--server" "$SERVER_URL" "--agent-port" "$AGENT_PORT" "--max-tasks" "$MAX_TASKS" "--heartbeat" "$HEARTBEAT")
[[ -n "$WORKER_ID" ]] && ARGS+=("--worker-id" "$WORKER_ID")
[[ -n "$POOL_ID" ]] && ARGS+=("--pool-id" "$POOL_ID")
[[ -n "$TOKEN" ]] && ARGS+=("--token" "$TOKEN")
[[ -n "$LABELS" ]] && ARGS+=("--labels" "$LABELS")
if [[ -n "$CAPABILITIES" ]]; then
    read -r -a CAP_ARRAY <<< "$CAPABILITIES"
    ARGS+=("--capabilities" "${CAP_ARRAY[@]}")
fi

printf -v QUOTED_ARGS ' %q' "${ARGS[@]}"

echo "Starting KubeTrain2 Agent..."
echo "Server: $SERVER_URL"
echo "Agent port: $AGENT_PORT"
echo "Log file: $LOG_FILE"
(
    cd "$PROJECT_ROOT"
    export PYTHONUNBUFFERED=1
    nohup bash -lc "$PY_RUNNER$QUOTED_ARGS" >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
)

sleep 2
pid="$(cat "$PID_FILE" 2>/dev/null || true)"
if is_running "$pid"; then
    echo "KubeTrain2 Agent started, pid=$pid"
    echo "Agent health: http://127.0.0.1:$AGENT_PORT/health"
else
    echo "ERROR: Agent failed to start. Recent log:" >&2
    tail -n 80 "$LOG_FILE" >&2 || true
    rm -f "$PID_FILE"
    exit 1
fi
