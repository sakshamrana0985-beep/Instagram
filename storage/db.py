"""Typed data-access layer over Postgres (Supabase in prod, local pg in tests).

Connects directly via asyncpg using SUPABASE_DB_URL (a standard Postgres
connection string) rather than the PostgREST client, so the same code path
works against Supabase and against a local Postgres+pgvector instance in CI.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg
from pgvector.asyncpg import register_vector

from storage.models import Item, ItemStatus, UrlCacheEntry

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    await register_vector(conn)


async def get_pool(dsn: str) -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn, init=_init_connection, min_size=1, max_size=5)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _row_to_item(row: asyncpg.Record) -> Item:
    data = dict(row)
    if data.get("embedding") is not None:
        data["embedding"] = data["embedding"].to_list()
    if data.get("summary") is not None and isinstance(data["summary"], str):
        data["summary"] = json.loads(data["summary"])
    return Item.model_validate(data)


async def upsert_item(pool: asyncpg.Pool, item: Item) -> Item:
    row = await pool.fetchrow(
        """
        insert into items (
            id, user_id, url, url_hash, platform, status,
            creator_handle, creator_url, posted_at, thumbnail_url, duration_sec,
            content_type, is_informational, is_time_sensitive, title, summary,
            raw_transcript, topics, embedding, saved_at, last_opened_at,
            open_count, archived
        ) values (
            $1, $2, $3, $4, $5, $6,
            $7, $8, $9, $10, $11,
            $12, $13, $14, $15, $16,
            $17, $18, $19, $20, $21,
            $22, $23
        )
        on conflict (user_id, url_hash) do update set
            status = excluded.status,
            platform = excluded.platform,
            creator_handle = excluded.creator_handle,
            creator_url = excluded.creator_url,
            posted_at = excluded.posted_at,
            thumbnail_url = excluded.thumbnail_url,
            duration_sec = excluded.duration_sec,
            content_type = excluded.content_type,
            is_informational = excluded.is_informational,
            is_time_sensitive = excluded.is_time_sensitive,
            title = excluded.title,
            summary = excluded.summary,
            raw_transcript = excluded.raw_transcript,
            topics = excluded.topics,
            embedding = excluded.embedding
        returning *
        """,
        item.id,
        item.user_id,
        item.url,
        item.url_hash,
        item.platform,
        item.status,
        item.creator_handle,
        item.creator_url,
        item.posted_at,
        item.thumbnail_url,
        item.duration_sec,
        item.content_type,
        item.is_informational,
        item.is_time_sensitive,
        item.title,
        json.dumps(item.summary) if item.summary is not None else None,
        item.raw_transcript,
        item.topics,
        item.embedding,
        item.saved_at,
        item.last_opened_at,
        item.open_count,
        item.archived,
    )
    return _row_to_item(row)


async def get_item(pool: asyncpg.Pool, item_id: UUID) -> Item | None:
    row = await pool.fetchrow("select * from items where id = $1", item_id)
    return _row_to_item(row) if row else None


async def list_items(pool: asyncpg.Pool, user_id: UUID, limit: int = 50) -> list[Item]:
    rows = await pool.fetch(
        "select * from items where user_id = $1 order by saved_at desc limit $2",
        user_id,
        limit,
    )
    return [_row_to_item(r) for r in rows]


async def update_item_status(
    pool: asyncpg.Pool, item_id: UUID, status: ItemStatus
) -> None:
    await pool.execute("update items set status = $1 where id = $2", status, item_id)


async def check_url_cache(pool: asyncpg.Pool, url_hash: str) -> UrlCacheEntry | None:
    row = await pool.fetchrow("select * from url_cache where url_hash = $1", url_hash)
    if row is None:
        return None
    data = dict(row)
    if isinstance(data["payload"], str):
        data["payload"] = json.loads(data["payload"])
    return UrlCacheEntry.model_validate(data)


async def write_url_cache(pool: asyncpg.Pool, url_hash: str, payload: dict[str, Any]) -> None:
    await pool.execute(
        """
        insert into url_cache (url_hash, payload, processed_at)
        values ($1, $2, $3)
        on conflict (url_hash) do update set payload = excluded.payload, processed_at = excluded.processed_at
        """,
        url_hash,
        json.dumps(payload),
        datetime.now(timezone.utc),
    )


async def vector_search(
    pool: asyncpg.Pool, user_id: UUID, embedding: list[float], limit: int = 10
) -> list[Item]:
    rows = await pool.fetch(
        """
        select * from items
        where user_id = $1 and embedding is not null
        order by embedding <=> $2
        limit $3
        """,
        user_id,
        embedding,
        limit,
    )
    return [_row_to_item(r) for r in rows]
