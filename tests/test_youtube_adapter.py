"""Unit tests for the YouTube adapter, mocking the transcript API.

Note: this sandbox's network policy blocks outbound calls to youtube.com,
so these can't be live end-to-end calls (the build plan's "5 real URLs" ask).
They cover the same cases with a mocked YouTubeTranscriptApi: multiple real
URL shapes for id-extraction, a captions-available happy path, and the
no-captions failure path returning a typed result instead of raising.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from youtube_transcript_api import FetchedTranscript, FetchedTranscriptSnippet
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

from adapters.youtube import YouTubeAdapter, extract_video_id

REAL_URL_SHAPES = [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
]


@pytest.mark.parametrize("url,expected_id", REAL_URL_SHAPES)
def test_extract_video_id(url: str, expected_id: str):
    assert extract_video_id(url) == expected_id


def test_extract_video_id_returns_none_for_non_youtube_url():
    assert extract_video_id("https://example.com/not-a-video") is None


@pytest.mark.asyncio
async def test_fetch_returns_transcript_when_captions_exist():
    adapter = YouTubeAdapter()
    fetched = FetchedTranscript(
        snippets=[
            FetchedTranscriptSnippet(text="five tax hacks", start=0.0, duration=2.0),
            FetchedTranscriptSnippet(text="beyond 80C", start=2.0, duration=2.0),
        ],
        video_id="dQw4w9WgXcQ",
        language="English",
        language_code="en",
        is_generated=False,
    )
    adapter._api = MagicMock()
    adapter._api.fetch.return_value = fetched

    result = await adapter.fetch("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.status == "ok"
    assert result.transcript == "five tax hacks beyond 80C"
    assert result.platform == "youtube"


@pytest.mark.asyncio
async def test_fetch_returns_typed_failure_when_no_captions():
    adapter = YouTubeAdapter()
    adapter._api = MagicMock()
    adapter._api.fetch.side_effect = TranscriptsDisabled("dQw4w9WgXcQ")

    result = await adapter.fetch("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.status == "failed"
    assert result.error is not None
    assert result.transcript is None


@pytest.mark.asyncio
async def test_fetch_no_transcript_found_is_typed_failure():
    adapter = YouTubeAdapter()
    adapter._api = MagicMock()
    adapter._api.fetch.side_effect = NoTranscriptFound(
        "dQw4w9WgXcQ", requested_language_codes=["en"], transcript_data=MagicMock()
    )

    result = await adapter.fetch("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.status == "failed"


@pytest.mark.asyncio
async def test_fetch_invalid_url_is_typed_failure_not_exception():
    adapter = YouTubeAdapter()
    result = await adapter.fetch("https://example.com/no-video-id-here")
    assert result.status == "failed"
    assert "could not extract video id" in result.error
