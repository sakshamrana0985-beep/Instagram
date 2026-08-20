"""Shared test fixtures.

DB-backed tests run against a local Postgres+pgvector instance, not Supabase.
Point them somewhere else with TEST_DATABASE_URL. Bring one up with
`scripts/setup_test_db.sh` (see README "Running the tests"). If no database is
reachable, those tests skip instead of failing so the pure-logic suite still runs.
"""
import os
import socket
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
import pytest
import pytest_asyncio

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://recall_test:recall_test@localhost:5432/recall_test"
)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _pg_available() -> bool:
    parsed = urlparse(TEST_DSN)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    s = socket.socket()
    try:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0
    except socket.gaierror:
        return False
    finally:
        s.close()


_PG_UP = _pg_available()
_REQUIRE_DB = os.environ.get("RECALL_REQUIRE_DB") == "1"

if _REQUIRE_DB and not _PG_UP:
    raise RuntimeError(
        f"RECALL_REQUIRE_DB=1 but no Postgres is reachable at {TEST_DSN}. "
        "Run scripts/setup_test_db.sh, or unset RECALL_REQUIRE_DB to let the "
        "DB-backed tests skip."
    )

requires_postgres = pytest.mark.skipif(
    not _PG_UP,
    reason=f"no Postgres with pgvector at {TEST_DSN} — run scripts/setup_test_db.sh",
)


@pytest_asyncio.fixture(scope="session")
async def migrated_db() -> str:
    """Apply every migration once per session, so a blank database is usable."""
    conn = await asyncpg.connect(TEST_DSN)
    try:
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            await conn.execute(path.read_text())
    finally:
        await conn.close()
    return TEST_DSN


@pytest_asyncio.fixture
async def pool(migrated_db):
    from storage.db import close_pool, get_pool

    p = await get_pool(migrated_db)
    yield p
    async with p.acquire() as conn:
        await conn.execute("truncate item_open_events, search_events, items, url_cache, users cascade")
    await close_pool()
