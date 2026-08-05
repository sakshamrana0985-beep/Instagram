import os

import asyncpg
import pytest
import pytest_asyncio

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://recall_test:recall_test@localhost:5432/recall_test"
)


def _pg_available() -> bool:
    import socket

    s = socket.socket()
    try:
        s.settimeout(0.5)
        return s.connect_ex(("localhost", 5432)) == 0
    finally:
        s.close()


requires_postgres = pytest.mark.skipif(
    not _pg_available(), reason="local Postgres with pgvector not running"
)


@pytest_asyncio.fixture
async def pool():
    from storage.db import close_pool, get_pool

    p = await get_pool(TEST_DSN)
    yield p
    async with p.acquire() as conn:
        await conn.execute("truncate item_open_events, search_events, items, url_cache, users cascade")
    await close_pool()
