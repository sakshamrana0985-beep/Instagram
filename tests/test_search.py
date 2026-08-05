from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from pipeline import search as search_module
from pipeline.search import SearchResult, _reciprocal_rank_fusion, hybrid_search
from storage.db import upsert_item
from storage.models import Item

from .conftest import requires_postgres

pytestmark = requires_postgres


def _item(item_id, user_id, **overrides) -> Item:
    defaults = dict(
        id=item_id,
        user_id=user_id,
        url=f"https://youtube.com/watch?v={item_id}",
        url_hash=str(item_id),
        platform="youtube",
        status="ready",
        title="untitled",
        summary={},
        topics=[],
        saved_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Item.model_validate(defaults)


def test_rrf_ranks_items_appearing_in_both_lists_highest():
    now = datetime.now(timezone.utc)
    a = _item(uuid4(), uuid4(), title="A")
    b = _item(uuid4(), uuid4(), title="B")
    c = _item(uuid4(), uuid4(), title="C")

    vector_ranked = [a, b, c]
    keyword_ranked = [b, a]

    results = _reciprocal_rank_fusion([vector_ranked, keyword_ranked], now=now)

    assert results[0].item.id == a.id  # rank 1 in vector, rank 2 in keyword
    ids = [r.item.id for r in results]
    assert c.id in ids  # present even though only in one list


async def _make_user(pool) -> "uuid.UUID":
    row = await pool.fetchrow("insert into users (telegram_id) values ($1) returning id", 1)
    return row["id"]


@pytest.mark.asyncio
async def test_hybrid_search_finds_by_exact_keyword_term(pool, monkeypatch):
    """'80CCD' must be findable even if the query embedding lands nowhere
    near the item's embedding — this is why search is hybrid, not vector-only."""
    user_id = await _make_user(pool)
    item = _item(
        uuid4(),
        user_id,
        title="5 tax-saving hacks beyond 80C",
        summary={"headline": "NPS Tier 1 under 80CCD(1B) gives extra deduction"},
        embedding=[0.9] * 768,
    )
    await upsert_item(pool, item)

    monkeypatch.setattr(search_module, "embed_query", AsyncMock(return_value=[0.1] * 768))

    results = await hybrid_search(pool, gemini_client=None, user_id=user_id, query="80CCD")

    assert any(r.item.id == item.id for r in results)


@pytest.mark.asyncio
async def test_hybrid_search_finds_by_semantic_similarity(pool, monkeypatch):
    """'that thing about saving tax' should surface an item via vector
    similarity even without a shared keyword."""
    user_id = await _make_user(pool)
    item = _item(
        uuid4(),
        user_id,
        title="NPS Tier 1 explained",
        summary={"headline": "Extra deduction beyond the usual limit"},
        embedding=[0.5] * 768,
    )
    await upsert_item(pool, item)

    monkeypatch.setattr(search_module, "embed_query", AsyncMock(return_value=[0.5] * 768))

    results = await hybrid_search(
        pool, gemini_client=None, user_id=user_id, query="that thing about saving tax"
    )

    assert any(r.item.id == item.id for r in results)


@pytest.mark.asyncio
async def test_hybrid_search_scoped_to_user(pool, monkeypatch):
    user_id = await _make_user(pool)
    other_user_row = await pool.fetchrow(
        "insert into users (telegram_id) values ($1) returning id", 2
    )
    other_user_id = other_user_row["id"]

    other_item = _item(uuid4(), other_user_id, title="private to other user", embedding=[0.5] * 768)
    await upsert_item(pool, other_item)

    monkeypatch.setattr(search_module, "embed_query", AsyncMock(return_value=[0.5] * 768))

    results = await hybrid_search(pool, gemini_client=None, user_id=user_id, query="private")

    assert results == []
