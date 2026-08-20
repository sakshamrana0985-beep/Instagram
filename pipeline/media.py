"""Transient media fetch for video understanding (PRD §11).

Bytes are held in memory for the duration of one model call and never
written to disk, never persisted, never re-served. CLAUDE.md rule 2 —
"never store video files" — is a legal constraint about server-side
storage; nothing here creates a file or a row containing media.

Platform-agnostic on purpose: it takes whatever `media_url` a
SourceAdapter returned and knows nothing about which platform produced it
(CLAUDE.md rule 1).
"""
from __future__ import annotations

import logging

import httpx
from pydantic import BaseModel

logger = logging.getLogger("recall.media")

# Gemini inline-data ceiling for a single request is 20MB; stay under it.
MAX_MEDIA_BYTES = 18 * 1024 * 1024
FETCH_TIMEOUT_SEC = 45


class MediaPayload(BaseModel):
    """In-memory media handed to a model. Never serialized to storage."""

    data: bytes
    mime_type: str = "video/mp4"


async def fetch_media(url: str | None, max_bytes: int = MAX_MEDIA_BYTES) -> MediaPayload | None:
    """Download media into memory, or return None.

    Returns None rather than raising for every failure mode — a CDN 404 or an
    oversized reel must degrade to caption-only summarization, not fail the save.
    """
    if not url:
        return None

    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SEC, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()

                declared = response.headers.get("content-length")
                if declared is not None and int(declared) > max_bytes:
                    logger.info("media too large declared_bytes=%s cap=%s", declared, max_bytes)
                    return None

                mime_type = (response.headers.get("content-type") or "video/mp4").split(";")[0].strip()
                if not mime_type.startswith(("video/", "audio/")):
                    logger.info("media is not video/audio content_type=%s", mime_type)
                    return None

                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        logger.info("media exceeded cap while streaming cap=%s", max_bytes)
                        return None
                    chunks.append(chunk)
    except Exception as exc:  # noqa: BLE001 — a media fetch failure is never fatal
        logger.info("media fetch failed url=%s error=%s", url, exc)
        return None

    if not chunks:
        return None

    payload = MediaPayload(data=b"".join(chunks), mime_type=mime_type)
    logger.info("media fetched bytes=%d mime=%s", len(payload.data), payload.mime_type)
    return payload
