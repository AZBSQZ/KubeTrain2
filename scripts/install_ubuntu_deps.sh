#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if ! command -v apt-get >/dev/null 2>&1; then
    echo "ERROR: this helper script only supports Ubuntu/Debian with apt-get." >&2
    exit 1
fi

if [[ "$(id -u)" -eq 0 ]]; then
    SUDO=""
else
    SUDO="sudo"
fi

echo "Installing system dependencies..."
$SUDO apt-get update
DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y \
    python3 python3-venv python3-pip \
    nodejs npm \
    nginx \
    mysql-server mysql-client \
    redis-server \
    curl git build-essential lsof

echo "Enabling services..."
$SUDO systemctl enable --now mysql || true
$SUDO systemctl enable --now redis-server || true
$SUDO systemctl enable --now nginx || true

echo "Preparing Python virtual environment..."
cd "$PROJECT_ROOT"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r backend/requirements.txt

echo "Checking frontend toolchain..."
node --version
npm --version

echo ""
echo "KubeTrain2 Ubuntu dependencies are ready."
echo "Next steps:"
echo "  1. Create/import MySQL database."
echo "  2. Copy backend/.env.example to backend/.env and edit DB/secrets."
echo "  3. Run: ./scripts/start_frontend.sh build"
echo "  4. Install Nginx config and run: ./scripts/start_backend.sh"
