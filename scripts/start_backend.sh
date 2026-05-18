#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
LOG_DIR="$PROJECT_ROOT/logs"
PID_DIR="$PROJECT_ROOT/pids"
PID_FILE="$PID_DIR/backend.pid"
LOG_FILE="$LOG_DIR/backend.log"
PORT="${PORT:-8010}"
CONDA_ENV="${CONDA_ENV:-bs}"
PYTHON_CMD="${PYTHON_CMD:-}"

mkdir -p "$LOG_DIR" "$PID_DIR"

is_running() {
    local pid="${1:-}"
    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

if [[ -f "$PID_FILE" ]]; then
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if is_running "$pid"; then
        echo "KubeTrain2 backend is already running, pid=$pid, port=$PORT"
        exit 0
    fi
    rm -f "$PID_FILE"
fi

if [[ ! -f "$BACKEND_DIR/run.py" ]]; then
    echo "ERROR: backend/run.py not found: $BACKEND_DIR/run.py" >&2
    exit 1
fi

if [[ ! -f "$BACKEND_DIR/.env" ]]; then
    echo "WARN: backend/.env not found. Copy backend/.env.example to backend/.env before production deployment."
fi

if [[ -n "$PYTHON_CMD" ]]; then
    RUNNER="$PYTHON_CMD run.py"
elif command -v conda >/dev/null 2>&1; then
    RUNNER="conda run -n $CONDA_ENV python run.py"
elif [[ -x "$BACKEND_DIR/venv/bin/python" ]]; then
    RUNNER="$BACKEND_DIR/venv/bin/python run.py"
elif [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    RUNNER="$PROJECT_ROOT/.venv/bin/python run.py"
else
    RUNNER="python3 run.py"
fi

echo "Starting KubeTrain2 backend on port $PORT..."
echo "Log file: $LOG_FILE"
(
    cd "$BACKEND_DIR"
    export PYTHONUNBUFFERED=1
    nohup bash -lc "$RUNNER" >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
)

sleep 2
pid="$(cat "$PID_FILE" 2>/dev/null || true)"
if is_running "$pid"; then
    echo "KubeTrain2 backend started, pid=$pid"
    echo "Health check: http://127.0.0.1:$PORT/api/health"
else
    echo "ERROR: backend failed to start. Recent log:" >&2
    tail -n 80 "$LOG_FILE" >&2 || true
    rm -f "$PID_FILE"
    exit 1
fi
