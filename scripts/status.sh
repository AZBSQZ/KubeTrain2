#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_DIR="$PROJECT_ROOT/pids"
BACKEND_PORT="${PORT:-8010}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
AGENT_PORT="${AGENT_PORT:-8005}"

is_running_pid_file() {
    local name="$1"
    local file="$2"
    if [[ -f "$file" ]]; then
        local pid
        pid="$(cat "$file" 2>/dev/null || true)"
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            echo "[OK] $name pid=$pid"
            return 0
        fi
    fi
    echo "[--] $name pid file not running"
    return 1
}

check_port() {
    local name="$1"
    local port="$2"
    if command -v ss >/dev/null 2>&1; then
        if ss -ltn "sport = :$port" 2>/dev/null | grep -q ":$port"; then
            echo "[OK] $name port $port is listening"
            return 0
        fi
    elif command -v lsof >/dev/null 2>&1; then
        if lsof -i tcp:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
            echo "[OK] $name port $port is listening"
            return 0
        fi
    fi
    echo "[--] $name port $port is not listening"
    return 1
}

check_http() {
    local name="$1"
    local url="$2"
    if command -v curl >/dev/null 2>&1; then
        if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
            echo "[OK] $name $url"
            return 0
        fi
        echo "[--] $name $url unreachable"
        return 1
    fi
    echo "[--] curl not found, skip $name"
    return 1
}

check_system_service() {
    local service="$1"
    if command -v systemctl >/dev/null 2>&1; then
        if systemctl is-active --quiet "$service" 2>/dev/null; then
            echo "[OK] systemd $service active"
        else
            echo "[--] systemd $service inactive or not installed"
        fi
    fi
}

echo "=== KubeTrain2 status ==="
is_running_pid_file "backend" "$PID_DIR/backend.pid" || true
is_running_pid_file "frontend-dev" "$PID_DIR/frontend-dev.pid" || true
is_running_pid_file "agent" "$PID_DIR/agent.pid" || true
check_port "backend" "$BACKEND_PORT" || true
check_port "frontend-dev" "$FRONTEND_PORT" || true
check_port "agent" "$AGENT_PORT" || true
check_http "backend health" "http://127.0.0.1:$BACKEND_PORT/api/health" || true
check_http "agent health" "http://127.0.0.1:$AGENT_PORT/health" || true
check_system_service "mysql" || true
check_system_service "mysqld" || true
check_system_service "redis-server" || true
check_system_service "redis" || true
check_system_service "nginx" || true
check_system_service "kubetrain2-backend" || true
check_system_service "kubetrain2-agent" || true
