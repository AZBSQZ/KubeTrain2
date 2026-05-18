#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
LOG_DIR="$PROJECT_ROOT/logs"
PID_DIR="$PROJECT_ROOT/pids"
PID_FILE="$PID_DIR/frontend-dev.pid"
LOG_FILE="$LOG_DIR/frontend-dev.log"
MODE="${1:-build}"
PORT="${FRONTEND_PORT:-5173}"

mkdir -p "$LOG_DIR" "$PID_DIR"

is_running() {
    local pid="${1:-}"
    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
    echo "ERROR: frontend/package.json not found: $FRONTEND_DIR/package.json" >&2
    exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: npm not found. Install Node.js/npm first." >&2
    echo "Ubuntu example:" >&2
    echo "  apt-get update && apt-get install -y nodejs npm" >&2
    echo "or run:" >&2
    echo "  ./scripts/install_ubuntu_deps.sh" >&2
    exit 1
fi

case "$MODE" in
    build|prod|production)
        echo "Installing frontend dependencies..."
        cd "$FRONTEND_DIR"
        npm install
        if [[ -d "$FRONTEND_DIR/node_modules/.bin" ]]; then
            chmod -R u+x "$FRONTEND_DIR/node_modules/.bin" 2>/dev/null || true
        fi
        if [[ -f "$FRONTEND_DIR/node_modules/vite/bin/vite.js" ]]; then
            chmod u+x "$FRONTEND_DIR/node_modules/vite/bin/vite.js" 2>/dev/null || true
        fi
        echo "Building frontend static files..."
        npm run build
        echo "Frontend build completed: $FRONTEND_DIR/dist"
        echo "Use deploy/kubetrain2.nginx.conf to publish this dist directory."
        ;;
    dev|--dev|development)
        if [[ -f "$PID_FILE" ]]; then
            pid="$(cat "$PID_FILE" 2>/dev/null || true)"
            if is_running "$pid"; then
                echo "KubeTrain2 frontend dev server is already running, pid=$pid, port=$PORT"
                exit 0
            fi
            rm -f "$PID_FILE"
        fi
        echo "Starting frontend dev server on port $PORT..."
        (
            cd "$FRONTEND_DIR"
            nohup bash -lc "npm run dev -- --host 0.0.0.0" >> "$LOG_FILE" 2>&1 &
            echo $! > "$PID_FILE"
        )
        sleep 2
        pid="$(cat "$PID_FILE" 2>/dev/null || true)"
        if is_running "$pid"; then
            echo "KubeTrain2 frontend dev server started, pid=$pid"
            echo "URL: http://127.0.0.1:$PORT"
        else
            echo "ERROR: frontend dev server failed to start. Recent log:" >&2
            tail -n 80 "$LOG_FILE" >&2 || true
            rm -f "$PID_FILE"
            exit 1
        fi
        ;;
    *)
        echo "Usage: $0 [build|dev]" >&2
        exit 1
        ;;
esac
