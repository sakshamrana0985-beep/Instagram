"""Instagram adapter — logged-off, third-party fetch only (CLAUDE.md rule 3).

Provider abstraction underneath: ApifyProvider is primary, with automatic
failover to a second provider on failure or timeout. Global url_cache
dedup (one viral reel processed once) is a pipeline-level concern — see
pipeline/process.py, session 7 — not this adapter's job, so a single
adapter call always does real work.

No transcript is produced here. Instagram reels frequently carry their
information as on-screen text over music, so audio transcription is the
wrong tool; downstream (pipeline/summarize.py) passes media_url straight
to Gemini for video understanding when transcript is empty, per PRD §11.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime

from apify_client import ApifyClientAsync
from pydantic import BaseModel

from adapters.base import SourceAdapter, SourceResult

FETCH_TIMEOUT_SEC = 60
APIFY_ACTOR_ID = "apify/instagram-reel-scraper"


class RawInstagramData(BaseModel):
    caption: str | None = None
    media_url: str | None = None
    creator_handle: str | None = None
    creator_url: str | None = None
    posted_at: datetime | None = None
    thumbnail_url: str | None = None
    duration_sec: int | None = None


class InstagramProvider(ABC):
    @abstractmethod
    async def fetch(self, url: str) -> RawInstagramData:
        """Raise on failure — the adapter decides how to interpret that."""


class ApifyProvider(InstagramProvider):
    def __init__(self, token: str, actor_id: str = APIFY_ACTOR_ID) -> None:
        self._client = ApifyClientAsync(token)
        self._actor_id = actor_id

    async def fetch(self, url: str) -> RawInstagramData:
        run = await self._client.actor(self._actor_id).call(run_input={"directUrls": [url]})
        dataset_id = run["defaultDatasetId"]
        items = []
        async for item in self._client.dataset(dataset_id).iterate_items():
            items.append(item)

        if not items:
            raise ValueError(f"Apify actor returned no items for {url}")

        item = items[0]
        return RawInstagramData(
            caption=item.get("caption"),
            media_url=item.get("videoUrl") or item.get("displayUrl"),
            creator_handle=item.get("ownerUsername"),
            creator_url=(
                f"https://www.instagram.com/{item['ownerUsername']}/"
                if item.get("ownerUsername")
                else None
            ),
            posted_at=item.get("timestamp"),
            thumbnail_url=item.get("displayUrl"),
            duration_sec=item.get("videoDuration"),
        )


class HikerAPIProvider(InstagramProvider):
    """Second provider for failover. Stub — benchmark against Apify (PRD §19
    open decision 3) and implement before this matters for real traffic."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    async def fetch(self, url: str) -> RawInstagramData:
        raise NotImplementedError("HikerAPIProvider is a failover stub — not yet implemented")


class InstagramAdapter(SourceAdapter):
    def __init__(
        self,
        primary: InstagramProvider | None = None,
        fallback: InstagramProvider | None = None,
        apify_token: str | None = None,
    ) -> None:
        self._primary = primary or (ApifyProvider(apify_token) if apify_token else None)
        self._fallback = fallback or HikerAPIProvider()

    async def fetch(self, url: str) -> SourceResult:
        if self._primary is None:
            return SourceResult(platform="instagram", status="failed", error="no Apify token configured")

        raw, error = await self._try_provider(self._primary, url)
        if raw is None:
            raw, fallback_error = await self._try_provider(self._fallback, url)
            if raw is None:
                return SourceResult(
                    platform="instagram",
                    status="failed",
                    error=f"primary failed: {error}; fallback failed: {fallback_error}",
                )

        return SourceResult(
            platform="instagram",
            status="ok",
            caption=raw.caption,
            transcript=None,
            media_url=raw.media_url,
            creator_handle=raw.creator_handle,
            creator_url=raw.creator_url,
            posted_at=raw.posted_at,
            thumbnail_url=raw.thumbnail_url,
            duration_sec=raw.duration_sec,
        )

    async def _try_provider(
        self, provider: InstagramProvider, url: str
    ) -> tuple[RawInstagramData | None, str | None]:
        try:
            raw = await asyncio.wait_for(provider.fetch(url), timeout=FETCH_TIMEOUT_SEC)
            return raw, None
        except asyncio.TimeoutError:
            return None, f"{provider.__class__.__name__} timed out after {FETCH_TIMEOUT_SEC}s"
        except Exception as exc:  # noqa: BLE001 — provider failures must never crash the caller
            return None, f"{provider.__class__.__name__}: {exc}"
