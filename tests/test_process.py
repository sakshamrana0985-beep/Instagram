from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from adapters.base import SourceResult
from pipeline.classify import ClassificationResult
from pipeline.media import MediaPayload
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


@pytest.mark.asyncio
async def test_instagram_reel_without_transcript_sends_video_to_summarize(pool, monkeypatch):
    """The reel case the product exists for: no captions to read, information
    lives in on-screen text, so the media must reach the model (PRD §11)."""
    user_id = await _make_user(pool)

    monkeypatch.setattr(
        process,
        "get_adapter",
        lambda url, apify_token=None: _FakeAdapter(
            SourceResult(
                platform="instagram",
                status="ok",
                caption="3 AI tools you need",
                transcript=None,
                media_url="https://cdn.example.com/reel.mp4",
                creator_handle="someone",
            )
        ),
    )
    monkeypatch.setattr(
        process,
        "fetch_media",
        AsyncMock(return_value=MediaPayload(data=b"videobytes", mime_type="video/mp4")),
    )
    monkeypatch.setattr(
        process,
        "classify",
        AsyncMock(
            return_value=ClassificationResult(
                content_type="listicle", is_informational=True, topics=["ai"], confidence=0.9
            )
        ),
    )
    summarize_mock = AsyncMock(
        return_value=SummaryResult(
            title="3 AI tools", is_time_sensitive=False, content={"headline": "3 AI tools", "items": []}
        )
    )
    monkeypatch.setattr(process, "summarize", summarize_mock)
    monkeypatch.setattr(process, "embed", AsyncMock(return_value=[0.1] * 768))

    item = await process.process_url(
        pool, gemini_client=None, url="https://instagram.com/reel/abc", user_id=user_id
    )

    assert item.status == "ready"
    assert summarize_mock.await_args.kwargs["media"].data == b"videobytes"


@pytest.mark.asyncio
async def test_classification_stays_text_only_even_with_media(pool, monkeypatch):
    """Running the cheap gate on video would undo the cost model (PRD §8)."""
    user_id = await _make_user(pool)

    monkeypatch.setattr(
        process,
        "get_adapter",
        lambda url, apify_token=None: _FakeAdapter(
            SourceResult(
                platform="instagram",
                status="ok",
                caption="a caption",
                media_url="https://cdn.example.com/reel.mp4",
            )
        ),
    )
    monkeypatch.setattr(
        process, "fetch_media", AsyncMock(return_value=MediaPayload(data=b"v", mime_type="video/mp4"))
    )
    classify_mock = AsyncMock(
        return_value=ClassificationResult(
            content_type="entertainment", is_informational=False, topics=[], confidence=0.9
        )
    )
    monkeypatch.setattr(process, "classify", classify_mock)

    await process.process_url(pool, gemini_client=None, url="https://instagram.com/reel/x", user_id=user_id)

    assert classify_mock.await_args.args[1] == "a caption"
    assert "media" not in classify_mock.await_args.kwargs


@pytest.mark.asyncio
async def test_no_media_fetch_when_transcript_already_exists(pool, monkeypatch):
    user_id = await _make_user(pool)

    monkeypatch.setattr(
        process,
        "get_adapter",
        lambda url, apify_token=None: _FakeAdapter(
            SourceResult(platform="youtube", status="ok", transcript="a real transcript")
        ),
    )
    fetch_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(process, "fetch_media", fetch_mock)
    monkeypatch.setattr(
        process,
        "classify",
        AsyncMock(
            return_value=ClassificationResult(
                content_type="explainer", is_informational=True, topics=[], confidence=0.9
            )
        ),
    )
    monkeypatch.setattr(
        process,
        "summarize",
        AsyncMock(return_value=SummaryResult(title="t", is_time_sensitive=False, content={})),
    )
    monkeypatch.setattr(process, "embed", AsyncMock(return_value=[0.1] * 768))

    await process.process_url(pool, gemini_client=None, url="https://youtube.com/watch?v=abc", user_id=user_id)

    fetch_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_whisper_fallback_when_video_understanding_fails(pool, monkeypatch):
    user_id = await _make_user(pool)

    monkeypatch.setattr(
        process,
        "get_adapter",
        lambda url, apify_token=None: _FakeAdapter(
            SourceResult(
                platform="instagram",
                status="ok",
                caption="cap",
                media_url="https://cdn.example.com/reel.mp4",
            )
        ),
    )
    monkeypatch.setattr(
        process,
        "fetch_media",
        AsyncMock(return_value=MediaPayload(data=b"videobytes", mime_type="video/mp4")),
    )
    monkeypatch.setattr(
        process,
        "classify",
        AsyncMock(
            return_value=ClassificationResult(
                content_type="listicle", is_informational=True, topics=[], confidence=0.9
            )
        ),
    )
    summarize_mock = AsyncMock(
        side_effect=[
            RuntimeError("video not supported"),
            SummaryResult(title="from audio", is_time_sensitive=False, content={"headline": "h", "items": []}),
        ]
    )
    monkeypatch.setattr(process, "summarize", summarize_mock)
    monkeypatch.setattr(process, "transcribe", AsyncMock(return_value="spoken words"))
    monkeypatch.setattr(process, "embed", AsyncMock(return_value=[0.1] * 768))

    item = await process.process_url(
        pool,
        gemini_client=None,
        url="https://instagram.com/reel/abc",
        user_id=user_id,
        groq_api_key="key",
    )

    assert item.status == "ready"
    assert item.title == "from audio"
    assert item.raw_transcript == "spoken words"
    assert summarize_mock.await_args_list[1].args[2] == "spoken words"


@pytest.mark.asyncio
async def test_item_fails_when_both_video_and_whisper_fail(pool, monkeypatch):
    user_id = await _make_user(pool)

    monkeypatch.setattr(
        process,
        "get_adapter",
        lambda url, apify_token=None: _FakeAdapter(
            SourceResult(
                platform="instagram", status="ok", caption="cap", media_url="https://cdn.example.com/r.mp4"
            )
        ),
    )
    monkeypatch.setattr(
        process, "fetch_media", AsyncMock(return_value=MediaPayload(data=b"v", mime_type="video/mp4"))
    )
    monkeypatch.setattr(
        process,
        "classify",
        AsyncMock(
            return_value=ClassificationResult(
                content_type="listicle", is_informational=True, topics=[], confidence=0.9
            )
        ),
    )
    monkeypatch.setattr(process, "summarize", AsyncMock(side_effect=RuntimeError("model down")))
    monkeypatch.setattr(process, "transcribe", AsyncMock(return_value=None))

    item = await process.process_url(
        pool, gemini_client=None, url="https://instagram.com/reel/abc", user_id=user_id
    )

    assert item.status == "failed"
