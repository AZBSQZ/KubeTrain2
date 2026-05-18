#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/backend/.env"
EXAMPLE_FILE="$PROJECT_ROOT/backend/.env.example"

DB_NAME="${DB_NAME:-kubetrain2}"
DB_USER="${DB_USER:-kubetrain}"
DB_PASSWORD="${DB_PASSWORD:-}"
MYSQL_ROOT_CMD="${MYSQL_ROOT_CMD:-mysql -u root}"

random_hex() {
    python3 - <<'PY'
import secrets
print('Kt2_' + secrets.token_hex(16))
PY
}

random_urlsafe() {
    python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
}

set_env_value() {
    local key="$1"
    local value="$2"
    local escaped
    escaped="$(printf '%s' "$value" | sed 's/[&/]/\\&/g')"
    if grep -q "^${key}=" "$ENV_FILE"; then
        sed -i "s/^${key}=.*/${key}=${escaped}/" "$ENV_FILE"
    else
        printf '\n%s=%s\n' "$key" "$value" >> "$ENV_FILE"
    fi
}

if [[ ! -f "$EXAMPLE_FILE" ]]; then
    echo "ERROR: env example not found: $EXAMPLE_FILE" >&2
    exit 1
fi

if [[ -z "$DB_PASSWORD" ]]; then
    DB_PASSWORD="$(random_hex)"
fi
SECRET_KEY="${SECRET_KEY:-$(random_urlsafe)}"
JWT_SECRET_KEY="${JWT_SECRET_KEY:-$(random_urlsafe)}"

cd "$PROJECT_ROOT"
MYSQL_ROOT_CMD="$MYSQL_ROOT_CMD" DB_NAME="$DB_NAME" DB_USER="$DB_USER" DB_PASSWORD="$DB_PASSWORD" ./scripts/init_mysql.sh

if [[ ! -f "$ENV_FILE" ]]; then
    cp "$EXAMPLE_FILE" "$ENV_FILE"
fi

set_env_value SECRET_KEY "$SECRET_KEY"
set_env_value JWT_SECRET_KEY "$JWT_SECRET_KEY"
set_env_value DB_HOST "127.0.0.1"
set_env_value DB_PORT "3306"
set_env_value DB_USER "$DB_USER"
set_env_value DB_PASSWORD "$DB_PASSWORD"
set_env_value DB_NAME "$DB_NAME"
set_env_value REDIS_URL "redis://127.0.0.1:6379/0"
set_env_value PORT "8010"
set_env_value HOST "0.0.0.0"
set_env_value FLASK_ENV "production"

echo "backend/.env configured."
echo "DB_NAME=$DB_NAME"
echo "DB_USER=$DB_USER"
echo "DB_PASSWORD=$DB_PASSWORD"
echo "SECRET_KEY and JWT_SECRET_KEY have been generated."
