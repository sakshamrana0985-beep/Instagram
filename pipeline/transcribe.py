"""Groq Whisper fallback transcription (PRD §8).

Used only when video understanding is unavailable — no captions, and either
no media or a model that couldn't read it. Whisper hears speech but cannot
read on-screen text, so this is strictly the second-best path, never the
default for reels.

Operates on in-memory bytes; nothing is written to disk (CLAUDE.md rule 2).
"""
from __future__ import annotations

import logging

from groq import AsyncGroq

from pipeline.llm_log import log_call
from pipeline.media import MediaPayload

logger = logging.getLogger("recall.transcribe")

MODEL = "whisper-large-v3-turbo"
# Groq's upload ceiling on the free tier; larger media just skips transcription.
MAX_TRANSCRIBE_BYTES = 25 * 1024 * 1024


async def transcribe(api_key: str | None, media: MediaPayload | None) -> str | None:
    """Return a transcript, or None. Never raises — a fallback that fails
    leaves the caller exactly where it was (CLAUDE.md conventions)."""
    if not api_key or media is None:
        return None
    if len(media.data) > MAX_TRANSCRIBE_BYTES:
        logger.info("media too large to transcribe bytes=%d", len(media.data))
        return None

    suffix = "mp4" if media.mime_type.startswith("video/") else "m4a"
    try:
        client = AsyncGroq(api_key=api_key)
        with log_call(MODEL, "transcribe", bytes=len(media.data)):
            response = await client.audio.transcriptions.create(
                file=(f"media.{suffix}", media.data),
                model=MODEL,
                response_format="text",
            )
    except Exception as exc:  # noqa: BLE001 — fallback failures are non-fatal
        logger.info("groq transcription failed error=%s", exc)
        return None

    text = response if isinstance(response, str) else getattr(response, "text", None)
    text = (text or "").strip()
    if not text:
        return None
    return text
