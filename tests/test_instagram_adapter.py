import asyncio
from datetime import datetime, timezone

import pytest

from adapters.instagram import InstagramAdapter, InstagramProvider, RawInstagramData


class FakeProvider(InstagramProvider):
    def __init__(self, result: RawInstagramData | None = None, error: Exception | None = None, delay: float = 0):
        self._result = result
        self._error = error
        self._delay = delay

    async def fetch(self, url: str) -> RawInstagramData:
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error:
            raise self._error
        return self._result


def _voiceover_reel() -> RawInstagramData:
    return RawInstagramData(
        caption="5 tax-saving hacks beyond 80C #finance",
        media_url="https://cdn.example.com/reel1.mp4",
        creator_handle="financewithsharan",
        creator_url="https://www.instagram.com/financewithsharan/",
        posted_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
        thumbnail_url="https://cdn.example.com/thumb1.jpg",
        duration_sec=45,
    )


def _text_on_screen_reel() -> RawInstagramData:
    return RawInstagramData(
        caption="",
        media_url="https://cdn.example.com/reel2.mp4",
        creator_handle="aitoolsdaily",
        creator_url="https://www.instagram.com/aitoolsdaily/",
        posted_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        thumbnail_url="https://cdn.example.com/thumb2.jpg",
        duration_sec=30,
    )


def _meme_reel() -> RawInstagramData:
    return RawInstagramData(
        caption="lol same",
        media_url="https://cdn.example.com/reel3.mp4",
        creator_handle="memepage",
        creator_url="https://www.instagram.com/memepage/",
        posted_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        thumbnail_url="https://cdn.example.com/thumb3.jpg",
        duration_sec=15,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [_voiceover_reel(), _text_on_screen_reel(), _meme_reel()])
async def test_fetch_returns_ok_result_for_real_reel_shapes(raw):
    adapter = InstagramAdapter(primary=FakeProvider(result=raw))

    result = await adapter.fetch("https://www.instagram.com/reel/abc123/")

    assert result.status == "ok"
    assert result.platform == "instagram"
    assert result.media_url == raw.media_url
    assert result.creator_handle == raw.creator_handle
    assert result.transcript is None  # on-screen text handled downstream via media_url


@pytest.mark.asyncio
async def test_text_on_screen_reel_still_produces_usable_result():
    """The case that separates this from lazy competitors (build plan session 6):
    a reel with no spoken audio must still yield enough to summarize — media_url
    for Gemini video understanding, even though caption/transcript are empty."""
    raw = _text_on_screen_reel()
    adapter = InstagramAdapter(primary=FakeProvider(result=raw))

    result = await adapter.fetch("https://www.instagram.com/reel/xyz789/")

    assert result.status == "ok"
    assert result.media_url is not None
    assert result.transcript is None


@pytest.mark.asyncio
async def test_falls_back_to_second_provider_on_primary_failure():
    raw = _voiceover_reel()
    primary = FakeProvider(error=RuntimeError("Apify actor failed"))
    fallback = FakeProvider(result=raw)

    adapter = InstagramAdapter(primary=primary, fallback=fallback)
    result = await adapter.fetch("https://www.instagram.com/reel/abc123/")

    assert result.status == "ok"
    assert result.creator_handle == raw.creator_handle


@pytest.mark.asyncio
async def test_returns_typed_failure_when_both_providers_fail():
    primary = FakeProvider(error=RuntimeError("primary down"))
    fallback = FakeProvider(error=RuntimeError("fallback down"))

    adapter = InstagramAdapter(primary=primary, fallback=fallback)
    result = await adapter.fetch("https://www.instagram.com/reel/abc123/")

    assert result.status == "failed"
    assert "primary down" in result.error
    assert "fallback down" in result.error


@pytest.mark.asyncio
async def test_primary_timeout_triggers_failover():
    from adapters import instagram as instagram_module

    original_timeout = instagram_module.FETCH_TIMEOUT_SEC
    instagram_module.FETCH_TIMEOUT_SEC = 0.05
    try:
        primary = FakeProvider(delay=1)
        fallback = FakeProvider(result=_voiceover_reel())
        adapter = InstagramAdapter(primary=primary, fallback=fallback)

        result = await adapter.fetch("https://www.instagram.com/reel/abc123/")

        assert result.status == "ok"
    finally:
        instagram_module.FETCH_TIMEOUT_SEC = original_timeout


@pytest.mark.asyncio
async def test_no_token_configured_is_typed_failure_not_exception():
    adapter = InstagramAdapter(apify_token=None, primary=None)
    result = await adapter.fetch("https://www.instagram.com/reel/abc123/")
    assert result.status == "failed"
    assert "no Apify token" in result.error
