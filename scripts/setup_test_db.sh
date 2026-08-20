#!/usr/bin/env bash
# Bring up the local Postgres+pgvector database the DB-backed tests need.
#
#   ./scripts/setup_test_db.sh            # docker if available, else a local server
#   RECALL_TEST_DB_MODE=native ...        # force the locally-installed Postgres
#   RECALL_TEST_DB_MODE=docker ...        # force the docker container
#
# Idempotent: safe to re-run. Migrations are applied by the test suite itself,
# so this only has to produce an empty database with the right role.
set -euo pipefail

DB_NAME="${DB_NAME:-recall_test}"
DB_USER="${DB_USER:-recall_test}"
DB_PASS="${DB_PASS:-recall_test}"
DB_PORT="${DB_PORT:-5432}"
MODE="${RECALL_TEST_DB_MODE:-auto}"

if [ "$MODE" = "auto" ]; then
  if docker info >/dev/null 2>&1; then MODE=docker; else MODE=native; fi
fi

setup_docker() {
  echo "==> Using docker (pgvector/pgvector:pg16)"
  if [ -z "$(docker ps -aq -f name=^recall-test-db$)" ]; then
    docker run -d --name recall-test-db \
      -e POSTGRES_USER="$DB_USER" \
      -e POSTGRES_PASSWORD="$DB_PASS" \
      -e POSTGRES_DB="$DB_NAME" \
      -p "$DB_PORT":5432 \
      pgvector/pgvector:pg16 >/dev/null
  else
    docker start recall-test-db >/dev/null
  fi
  for _ in $(seq 1 30); do
    if docker exec recall-test-db pg_isready -U "$DB_USER" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  echo "postgres container did not become ready" >&2
  exit 1
}

setup_native() {
  echo "==> Using the locally-installed PostgreSQL server"
  if ! command -v psql >/dev/null 2>&1; then
    echo "psql not found. Install PostgreSQL 16 and the pgvector extension:" >&2
    echo "  Debian/Ubuntu: sudo apt-get install -y postgresql-16 postgresql-16-pgvector" >&2
    echo "  macOS:         brew install postgresql@16 pgvector" >&2
    exit 1
  fi
  # The vector extension must exist on disk; `create extension` in the
  # migrations does the rest.
  if command -v pg_config >/dev/null 2>&1 &&
     ! ls "$(pg_config --sharedir)"/extension/vector.control >/dev/null 2>&1; then
    echo "pgvector is not installed for this server (no vector.control)." >&2
    echo "  Debian/Ubuntu: sudo apt-get install -y postgresql-16-pgvector" >&2
    exit 1
  fi

  if command -v pg_ctlcluster >/dev/null 2>&1; then
    pg_isready -q || sudo_maybe pg_ctlcluster 16 main start || true
  elif command -v brew >/dev/null 2>&1; then
    pg_isready -q || brew services start postgresql@16 || true
  fi
  pg_isready -q || { echo "could not reach a running PostgreSQL server" >&2; exit 1; }

  if [ "$(as_superuser_query "select 1 from pg_roles where rolname='${DB_USER}'")" != "1" ]; then
    as_superuser "create role ${DB_USER} login password '${DB_PASS}' superuser"
  fi
  if [ "$(as_superuser_query "select 1 from pg_database where datname='${DB_NAME}'")" != "1" ]; then
    as_superuser "create database ${DB_NAME} owner ${DB_USER}"
  fi
}

sudo_maybe() {
  if [ "$(id -u)" = "0" ]; then "$@"; else sudo "$@"; fi
}

# Superuser access: as root, go through the postgres OS user; otherwise assume
# the current user can already reach the server (brew, Postgres.app, peer auth).
# SQL goes in on stdin so nothing in it is re-parsed by an intermediate shell.
as_superuser() {
  if [ "$(id -u)" = "0" ]; then
    printf '%s;\n' "$1" | su postgres -c "psql -v ON_ERROR_STOP=1 -q -d postgres -f -"
  else
    printf '%s;\n' "$1" | psql -v ON_ERROR_STOP=1 -q -d postgres -f -
  fi
}

as_superuser_query() {
  if [ "$(id -u)" = "0" ]; then
    printf '%s;\n' "$1" | su postgres -c "psql -tA -d postgres -f -"
  else
    printf '%s;\n' "$1" | psql -tA -d postgres -f -
  fi
}

case "$MODE" in
  docker) setup_docker ;;
  native) setup_native ;;
  *) echo "unknown RECALL_TEST_DB_MODE: $MODE (expected auto|docker|native)" >&2; exit 1 ;;
esac

DSN="postgresql://${DB_USER}:${DB_PASS}@localhost:${DB_PORT}/${DB_NAME}"
echo "==> Test database ready"
echo "    TEST_DATABASE_URL=${DSN}"
echo "    run: python -m pytest"
