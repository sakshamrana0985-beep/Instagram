from unittest.mock import AsyncMock, MagicMock

import pytest

from pipeline import transcribe as transcribe_module
from pipeline.media import MediaPayload
from pipeline.transcribe import MAX_TRANSCRIBE_BYTES, transcribe

MEDIA = MediaPayload(data=b"videobytes", mime_type="video/mp4")


def _mock_groq(monkeypatch, result) -> MagicMock:
    client = MagicMock()
    if isinstance(result, Exception):
        client.audio.transcriptions.create = AsyncMock(side_effect=result)
    else:
        client.audio.transcriptions.create = AsyncMock(return_value=result)
    monkeypatch.setattr(transcribe_module, "AsyncGroq", MagicMock(return_value=client))
    return client


async def test_transcribe_returns_text(monkeypatch):
    client = _mock_groq(monkeypatch, "  five tax hacks beyond 80C  ")

    assert await transcribe("key", MEDIA) == "five tax hacks beyond 80C"
    assert client.audio.transcriptions.create.await_args.kwargs["file"][0] == "media.mp4"


async def test_transcribe_reads_text_attribute(monkeypatch):
    response = MagicMock()
    response.text = "spoken words"
    _mock_groq(monkeypatch, response)

    assert await transcribe("key", MEDIA) == "spoken words"


async def test_transcribe_without_key_or_media_returns_none(monkeypatch):
    assert await transcribe(None, MEDIA) is None
    assert await transcribe("key", None) is None


async def test_transcribe_skips_oversized_media(monkeypatch):
    _mock_groq(monkeypatch, "unused")
    big = MediaPayload(data=b"x" * (MAX_TRANSCRIBE_BYTES + 1), mime_type="video/mp4")

    assert await transcribe("key", big) is None


async def test_transcribe_swallows_provider_failure(monkeypatch):
    _mock_groq(monkeypatch, RuntimeError("groq is down"))

    assert await transcribe("key", MEDIA) is None


async def test_transcribe_treats_empty_result_as_none(monkeypatch):
    _mock_groq(monkeypatch, "   ")

    assert await transcribe("key", MEDIA) is None
