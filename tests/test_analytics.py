from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from pipeline.analytics import get_admin_stats, get_user_stats
from storage.db import log_item_open, log_search_event, upsert_item
from storage.models import Item

from .conftest import requires_postgres

pytestmark = requires_postgres


async def _make_user(pool, telegram_id: int, created_at: datetime):
    row = await pool.fetchrow(
        "insert into users (telegram_id, created_at) values ($1, $2) returning id",
        telegram_id,
        created_at,
    )
    return row["id"]


def _item(user_id, saved_at, **overrides) -> Item:
    item_id = uuid4()
    defaults = dict(
        id=item_id,
        user_id=user_id,
        url=f"https://youtube.com/watch?v={item_id}",
        url_hash=str(item_id),
        platform="youtube",
        status="ready",
        title="t",
        summary={},
        topics=[],
        saved_at=saved_at,
    )
    defaults.update(overrides)
    return Item.model_validate(defaults)


@pytest.mark.asyncio
async def test_admin_stats_counts_week2_plus_searchers_correctly(pool):
    now = datetime.now(timezone.utc)
    old_enough = now - timedelta(days=20)

    # user A: signed up 20 days ago, searched 10 days ago (in week 2+) -> counts
    user_a = await _make_user(pool, 1, old_enough)
    await log_search_event(pool, user_a, "tax hacks", 3)
    await pool.execute(
        "update search_events set created_at = $1 where user_id = $2",
        now - timedelta(days=10),
        user_a,
    )

    # user B: signed up 20 days ago, searched same day (week 1) -> does not count
    user_b = await _make_user(pool, 2, old_enough)
    await log_search_event(pool, user_b, "recipe", 1)
    await pool.execute(
        "update search_events set created_at = $1 where user_id = $2", old_enough, user_b
    )

    # user C: never searched -> does not count
    await _make_user(pool, 3, old_enough)

    stats = await get_admin_stats(pool)

    assert stats.total_users == 3
    assert stats.searches_run == 2
    assert stats.users_searched_week2_plus == 1
    assert stats.pct_users_searched_week2_plus == pytest.approx(1 / 3)


@pytest.mark.asyncio
async def test_retrieval_rate_counts_items_opened_after_7_days(pool):
    now = datetime.now(timezone.utc)
    user_id = await _make_user(pool, 1, now - timedelta(days=30))

    recent_item = _item(user_id, saved_at=now - timedelta(days=10))
    stale_open_item = _item(user_id, saved_at=now - timedelta(days=30))
    never_opened_item = _item(user_id, saved_at=now - timedelta(days=30))

    await upsert_item(pool, recent_item)
    await upsert_item(pool, stale_open_item)
    await upsert_item(pool, never_opened_item)

    # opened within 7 days — does not count toward retrieval
    await pool.execute(
        "insert into item_open_events (item_id, user_id, days_since_saved) values ($1, $2, $3)",
        recent_item.id,
        user_id,
        3,
    )
    # opened after 7+ days — counts
    await log_item_open(pool, stale_open_item.id, user_id)

    stats = await get_admin_stats(pool)

    assert stats.items_saved == 3
    assert stats.retrieval_rate == pytest.approx(1 / 3)


@pytest.mark.asyncio
async def test_log_item_open_updates_open_count_and_last_opened_at(pool):
    now = datetime.now(timezone.utc)
    user_id = await _make_user(pool, 1, now - timedelta(days=30))
    item = _item(user_id, saved_at=now - timedelta(days=15))
    await upsert_item(pool, item)

    days_since_saved = await log_item_open(pool, item.id, user_id)

    assert days_since_saved >= 14

    from storage.db import get_item

    fetched = await get_item(pool, item.id)
    assert fetched.open_count == 1
    assert fetched.last_opened_at is not None


@pytest.mark.asyncio
async def test_user_stats_scoped_to_user(pool):
    now = datetime.now(timezone.utc)
    user_id = await _make_user(pool, 1, now)
    other_id = await _make_user(pool, 2, now)

    item = _item(user_id, saved_at=now - timedelta(days=10))
    other_item = _item(other_id, saved_at=now - timedelta(days=10))
    await upsert_item(pool, item)
    await upsert_item(pool, other_item)
    await log_item_open(pool, item.id, user_id)

    stats = await get_user_stats(pool, user_id)

    assert stats.items_saved == 1
    assert stats.items_opened == 1
