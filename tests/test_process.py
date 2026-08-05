from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from adapters.base import SourceResult
from pipeline.classify import ClassificationResult
from pipeline.summarize import SummaryResult
from pipeline import process

from .conftest import requires_postgres

pytestmark = requires_postgres


async def _make_user(pool) -> "uuid.UUID":
    row = await pool.fetchrow("insert into users (telegram_id) values ($1) returning id", 1)
    return row["id"]


@pytest.mark.asyncio
async def test_process_url_full_informational_path(pool, monkeypatch):
    user_id = await _make_user(pool)

    monkeypatch.setattr(
        process,
        "get_adapter",
        lambda url, apify_token=None: _FakeAdapter(
            SourceResult(
                platform="youtube",
                status="ok",
                transcript="5 tax-saving hacks beyond 80C, NPS Tier 1 under 80CCD(1B)",
                creator_url="https://youtube.com/watch?v=abc",
            )
        ),
    )
    monkeypatch.setattr(
        process,
        "classify",
        AsyncMock(
            return_value=ClassificationResult(
                content_type="listicle", is_informational=True, topics=["tax", "finance"], confidence=0.9
            )
        ),
    )
    monkeypatch.setattr(
        process,
        "summarize",
        AsyncMock(
            return_value=SummaryResult(
                title="5 tax-saving hacks beyond 80C",
                is_time_sensitive=True,
                content={"headline": "5 tax-saving hacks", "items": []},
            )
        ),
    )
    monkeypatch.setattr(process, "embed", AsyncMock(return_value=[0.1] * 768))

    item = await process.process_url(pool, gemini_client=None, url="https://youtube.com/watch?v=abc", user_id=user_id)

    assert item.status == "ready"
    assert item.is_informational is True
    assert item.title == "5 tax-saving hacks beyond 80C"
    assert item.embedding is not None

    cached = await process.db.check_url_cache(pool, process.url_hash("https://youtube.com/watch?v=abc"))
    assert cached is not None
    assert cached.payload["title"] == "5 tax-saving hacks beyond 80C"


@pytest.mark.asyncio
async def test_process_url_non_informational_skips_summarize_and_embed(pool, monkeypatch):
    user_id = await _make_user(pool)

    monkeypatch.setattr(
        process,
        "get_adapter",
        lambda url, apify_token=None: _FakeAdapter(
            SourceResult(platform="instagram", status="ok", caption="lol same energy")
        ),
    )
    monkeypatch.setattr(
        process,
        "classify",
        AsyncMock(
            return_value=ClassificationResult(
                content_type="entertainment", is_informational=False, topics=["meme"], confidence=0.9
            )
        ),
    )
    summarize_mock = AsyncMock()
    embed_mock = AsyncMock()
    monkeypatch.setattr(process, "summarize", summarize_mock)
    monkeypatch.setattr(process, "embed", embed_mock)

    item = await process.process_url(
        pool, gemini_client=None, url="https://instagram.com/reel/xyz", user_id=user_id
    )

    assert item.status == "ready"
    assert item.is_informational is False
    summarize_mock.assert_not_called()
    embed_mock.assert_not_called()


@pytest.mark.asyncio
async def test_process_url_unsupported_source(pool, monkeypatch):
    user_id = await _make_user(pool)
    monkeypatch.setattr(
        process,
        "get_adapter",
        lambda url, apify_token=None: _FakeAdapter(SourceResult(platform="other", status="unsupported")),
    )

    item = await process.process_url(pool, gemini_client=None, url="https://example.com/x", user_id=user_id)

    assert item.status == "unsupported"


@pytest.mark.asyncio
async def test_process_url_classify_failure_marks_item_failed(pool, monkeypatch):
    user_id = await _make_user(pool)
    monkeypatch.setattr(
        process,
        "get_adapter",
        lambda url, apify_token=None: _FakeAdapter(
            SourceResult(platform="youtube", status="ok", transcript="some text")
        ),
    )
    monkeypatch.setattr(process, "classify", AsyncMock(side_effect=RuntimeError("gemini down")))

    item = await process.process_url(pool, gemini_client=None, url="https://youtube.com/watch?v=fail", user_id=user_id)

    assert item.status == "failed"


@pytest.mark.asyncio
async def test_process_url_cache_hit_skips_adapter_and_ai_calls(pool, monkeypatch):
    user_id = await _make_user(pool)
    url = "https://youtube.com/watch?v=cached"
    h = process.url_hash(url)

    await process.db.write_url_cache(
        pool,
        h,
        {
            "platform": "youtube",
            "status": "ready",
            "content_type": "listicle",
            "is_informational": True,
            "is_time_sensitive": False,
            "title": "Cached title",
            "summary": {"headline": "Cached title", "items": []},
            "topics": ["tax"],
            "embedding": [0.2] * 768,
            "creator_handle": None,
            "creator_url": None,
            "posted_at": None,
            "thumbnail_url": None,
            "duration_sec": None,
            "raw_transcript": None,
        },
    )

    adapter_mock = AsyncMock()
    monkeypatch.setattr(process, "get_adapter", lambda url, apify_token=None: _RaisingAdapter())
    monkeypatch.setattr(process, "classify", AsyncMock(side_effect=AssertionError("should not be called")))

    item = await process.process_url(pool, gemini_client=None, url=url, user_id=user_id)

    assert item.title == "Cached title"
    assert item.status == "ready"


class _FakeAdapter:
    def __init__(self, result: SourceResult):
        self._result = result

    async def fetch(self, url: str) -> SourceResult:
        return self._result


class _RaisingAdapter:
    async def fetch(self, url: str) -> SourceResult:
        raise AssertionError("adapter should not be called on cache hit")
