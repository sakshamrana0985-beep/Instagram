from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from pipeline.quota import check_quota
from storage import db
from storage.models import Item, User

from .conftest import requires_postgres

pytestmark = requires_postgres


async def _user(pool, quota: int = 15) -> User:
    user = await db.get_or_create_user(pool, 42)
    await pool.execute("update users set weekly_quota = $1 where id = $2", quota, user.id)
    return User(**{**user.model_dump(), "weekly_quota": quota})


async def _save(pool, user_id, n: int, days_ago: int = 0) -> None:
    saved_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    for i in range(n):
        url = f"https://example.com/{days_ago}-{i}"
        await db.upsert_item(
            pool,
            Item(id=uuid4(), user_id=user_id, url=url, url_hash=url, status="ready", saved_at=saved_at),
        )


async def test_quota_allows_under_the_cap(pool):
    user = await _user(pool, quota=15)
    await _save(pool, user.id, 3)

    status = await check_quota(pool, user)

    assert status.allowed is True
    assert status.used == 3
    assert status.remaining == 12


async def test_quota_blocks_at_the_cap(pool):
    user = await _user(pool, quota=5)
    await _save(pool, user.id, 5)

    status = await check_quota(pool, user)

    assert status.allowed is False
    assert status.remaining == 0


async def test_quota_window_rolls_off_after_seven_days(pool):
    user = await _user(pool, quota=5)
    await _save(pool, user.id, 5, days_ago=8)

    status = await check_quota(pool, user)

    assert status.allowed is True
    assert status.used == 0


async def test_quota_is_per_user(pool):
    user = await _user(pool, quota=2)
    await _save(pool, user.id, 2)
    other = await db.get_or_create_user(pool, 99)

    assert (await check_quota(pool, user)).allowed is False
    assert (await check_quota(pool, other)).allowed is True


async def test_quota_respects_a_raised_per_user_limit(pool):
    user = await _user(pool, quota=100)
    await _save(pool, user.id, 20)

    assert (await check_quota(pool, user)).allowed is True
