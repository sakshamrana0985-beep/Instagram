"""Wires the full path: url -> cache check -> adapter -> classify ->
(stop if not informational) -> summarize -> embed -> store. (PRD §9, §11)

Every stage failure updates item.status and is logged with cost instead of
raising into the caller — a provider or model failure must never crash the
bot handler (CLAUDE.md code conventions).
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import sys
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

from google import genai

from adapters.registry import get_adapter
from pipeline.classify import classify
from pipeline.embed import embed
from pipeline.summarize import summarize
from storage import db
from storage.models import Item

logger = logging.getLogger("recall.pipeline")

_CACHE_EXCLUDED_FIELDS = {
    "id",
    "user_id",
    "url",
    "url_hash",
    "saved_at",
    "last_opened_at",
    "open_count",
    "archived",
}


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode("utf-8")).hexdigest()


def _payload_from_item(item: Item) -> dict:
    data = item.model_dump(mode="json")
    return {k: v for k, v in data.items() if k not in _CACHE_EXCLUDED_FIELDS}


def _log_stage(stage: str, elapsed: float, **fields: object) -> None:
    extra = " ".join(f"{k}={v}" for k, v in fields.items())
    logger.info("stage=%s elapsed=%.2fs %s", stage, elapsed, extra)


async def process_url(
    pool,
    gemini_client: genai.Client,
    url: str,
    user_id: UUID,
    apify_token: str | None = None,
) -> Item:
    h = url_hash(url)
    item_id = uuid4()
    now = datetime.now(timezone.utc)

    t0 = time.monotonic()
    cached = await db.check_url_cache(pool, h)
    if cached is not None:
        _log_stage("cache", time.monotonic() - t0, url_hash=h, hit=True)
        item = Item(id=item_id, user_id=user_id, url=url, url_hash=h, saved_at=now, **cached.payload)
        return await db.upsert_item(pool, item)
    _log_stage("cache", time.monotonic() - t0, url_hash=h, hit=False)

    adapter = get_adapter(url, apify_token=apify_token)
    t0 = time.monotonic()
    source = await adapter.fetch(url)
    _log_stage("resolve", time.monotonic() - t0, platform=source.platform, status=source.status)

    if source.status in ("unsupported", "failed"):
        item = Item(
            id=item_id,
            user_id=user_id,
            url=url,
            url_hash=h,
            platform=source.platform,
            status=source.status,
            saved_at=now,
        )
        return await db.upsert_item(pool, item)

    text = source.transcript or source.caption or ""

    t0 = time.monotonic()
    try:
        classification = await classify(gemini_client, text or "(no transcript or caption; on-screen text only)")
    except Exception as exc:  # noqa: BLE001
        _log_stage("classify", time.monotonic() - t0, status="failed", error=str(exc))
        item = Item(
            id=item_id,
            user_id=user_id,
            url=url,
            url_hash=h,
            platform=source.platform,
            status="failed",
            saved_at=now,
        )
        return await db.upsert_item(pool, item)
    _log_stage(
        "classify",
        time.monotonic() - t0,
        content_type=classification.content_type,
        is_informational=classification.is_informational,
    )

    if not classification.is_informational:
        title = (source.caption or "Saved item").strip()[:60]
        item = Item(
            id=item_id,
            user_id=user_id,
            url=url,
            url_hash=h,
            platform=source.platform,
            status="ready",
            creator_handle=source.creator_handle,
            creator_url=source.creator_url,
            posted_at=source.posted_at,
            thumbnail_url=source.thumbnail_url,
            duration_sec=source.duration_sec,
            content_type=classification.content_type,
            is_informational=False,
            title=title,
            summary={"description": title},
            topics=classification.topics,
            saved_at=now,
        )
        saved = await db.upsert_item(pool, item)
        await db.write_url_cache(pool, h, _payload_from_item(saved))
        return saved

    t0 = time.monotonic()
    try:
        summary_result = await summarize(gemini_client, classification.content_type, text)
        embedding = await embed(gemini_client, summary_result.title, summary_result.content, classification.topics)
    except Exception as exc:  # noqa: BLE001
        _log_stage("summarize_embed", time.monotonic() - t0, status="failed", error=str(exc))
        item = Item(
            id=item_id,
            user_id=user_id,
            url=url,
            url_hash=h,
            platform=source.platform,
            status="failed",
            saved_at=now,
        )
        return await db.upsert_item(pool, item)
    _log_stage("summarize_embed", time.monotonic() - t0, title=summary_result.title)

    item = Item(
        id=item_id,
        user_id=user_id,
        url=url,
        url_hash=h,
        platform=source.platform,
        status="ready",
        creator_handle=source.creator_handle,
        creator_url=source.creator_url,
        posted_at=source.posted_at,
        thumbnail_url=source.thumbnail_url,
        duration_sec=source.duration_sec,
        content_type=classification.content_type,
        is_informational=True,
        is_time_sensitive=summary_result.is_time_sensitive,
        title=summary_result.title,
        summary=summary_result.content,
        raw_transcript=source.transcript,
        topics=classification.topics,
        embedding=embedding,
        saved_at=now,
    )
    saved = await db.upsert_item(pool, item)
    await db.write_url_cache(pool, h, _payload_from_item(saved))
    return saved


async def _main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.path.insert(0, ".")
    from config import load_settings

    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--user", required=True, help="user UUID")
    args = parser.parse_args()

    settings = load_settings()
    pool = await db.get_pool(settings.supabase_db_url)
    client = genai.Client(api_key=settings.gemini_api_key)

    item = await process_url(pool, client, args.url, UUID(args.user), apify_token=settings.apify_token)
    print(item.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
