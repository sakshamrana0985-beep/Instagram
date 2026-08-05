from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from storage.db import (
    check_url_cache,
    get_item,
    list_items,
    update_item_status,
    upsert_item,
    vector_search,
    write_url_cache,
)
from storage.models import Item

from .conftest import requires_postgres

pytestmark = requires_postgres


async def _make_user(pool, telegram_id: int = 1) -> UUID:
    row = await pool.fetchrow(
        "insert into users (telegram_id) values ($1) returning id", telegram_id
    )
    return row["id"]


def _new_item(user_id: UUID, url: str = "https://youtube.com/watch?v=abc", **overrides) -> Item:
    defaults = dict(
        id=uuid4(),
        user_id=user_id,
        url=url,
        url_hash=f"hash-{url}",
        platform="youtube",
        status="ready",
        title="5 tax hacks",
        summary={"headline": "5 tax hacks", "items": []},
        topics=["tax", "finance"],
        embedding=[0.1] * 768,
        saved_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Item.model_validate(defaults)


@pytest.mark.asyncio
async def test_upsert_and_get_item(pool):
    user_id = await _make_user(pool)
    item = _new_item(user_id)

    saved = await upsert_item(pool, item)
    assert saved.id == item.id
    assert saved.title == "5 tax hacks"

    fetched = await get_item(pool, item.id)
    assert fetched is not None
    assert fetched.url == item.url
    assert fetched.summary == {"headline": "5 tax hacks", "items": []}


@pytest.mark.asyncio
async def test_upsert_dedupes_by_user_and_url_hash(pool):
    user_id = await _make_user(pool)
    item = _new_item(user_id, url_hash="same-hash")
    await upsert_item(pool, item)

    item2 = _new_item(user_id, url_hash="same-hash", title="updated title")
    await upsert_item(pool, item2)

    items = await list_items(pool, user_id)
    assert len(items) == 1
    assert items[0].title == "updated title"


@pytest.mark.asyncio
async def test_list_items_orders_by_saved_at_desc(pool):
    user_id = await _make_user(pool)
    older = _new_item(user_id, url_hash="a", saved_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    newer = _new_item(user_id, url_hash="b", saved_at=datetime(2024, 6, 1, tzinfo=timezone.utc))
    await upsert_item(pool, older)
    await upsert_item(pool, newer)

    items = await list_items(pool, user_id)
    assert [i.url_hash for i in items] == ["b", "a"]


@pytest.mark.asyncio
async def test_update_item_status(pool):
    user_id = await _make_user(pool)
    item = _new_item(user_id, status="pending")
    await upsert_item(pool, item)

    await update_item_status(pool, item.id, "failed")

    fetched = await get_item(pool, item.id)
    assert fetched.status == "failed"


@pytest.mark.asyncio
async def test_url_cache_roundtrip(pool):
    assert await check_url_cache(pool, "abc123") is None

    await write_url_cache(pool, "abc123", {"title": "cached"})
    entry = await check_url_cache(pool, "abc123")
    assert entry is not None
    assert entry.payload == {"title": "cached"}


@pytest.mark.asyncio
async def test_vector_search_returns_nearest(pool):
    user_id = await _make_user(pool)
    close = _new_item(user_id, url_hash="close", embedding=[0.1] * 768)
    far = _new_item(user_id, url_hash="far", embedding=[0.9] * 768)
    await upsert_item(pool, close)
    await upsert_item(pool, far)

    results = await vector_search(pool, user_id, [0.1] * 768, limit=1)
    assert len(results) == 1
    assert results[0].url_hash == "close"
