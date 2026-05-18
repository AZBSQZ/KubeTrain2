#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${DB_NAME:-kubetrain2}"
DB_USER="${DB_USER:-kubetrain}"
DB_PASSWORD="${DB_PASSWORD:-}"
SQL_FILE="${SQL_FILE:-kubetrain2.sql}"
MYSQL_ROOT_CMD="${MYSQL_ROOT_CMD:-mysql -u root}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if ! command -v mysql >/dev/null 2>&1; then
    echo "ERROR: mysql client not found. Run ./scripts/install_ubuntu_deps.sh first." >&2
    exit 1
fi

if [[ ! -f "$SQL_FILE" ]]; then
    echo "ERROR: SQL file not found: $PROJECT_ROOT/$SQL_FILE" >&2
    exit 1
fi

if [[ -z "$DB_PASSWORD" ]]; then
    DB_PASSWORD="$(python3 - <<'PY'
import secrets
print('Kt2_' + secrets.token_hex(16))
PY
)"
fi

echo "Initializing MySQL database '$DB_NAME' and user '$DB_USER'..."
$MYSQL_ROOT_CMD <<SQL
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
CREATE USER IF NOT EXISTS '$DB_USER'@'127.0.0.1' IDENTIFIED BY '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost';
GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL

mysql -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" < "$SQL_FILE"

echo "MySQL initialized."
echo "Use these values in backend/.env:"
echo "DB_HOST=127.0.0.1"
echo "DB_PORT=3306"
echo "DB_USER=$DB_USER"
echo "DB_PASSWORD=$DB_PASSWORD"
echo "DB_NAME=$DB_NAME"
