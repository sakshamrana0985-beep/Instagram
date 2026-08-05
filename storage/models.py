"""Pydantic models matching the Postgres table shapes (migrations/0001_init.sql)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

ContentType = Literal["listicle", "tutorial", "recipe", "explainer", "news", "entertainment"]
ItemStatus = Literal["pending", "processing", "ready", "failed", "unsupported"]
Platform = Literal["instagram", "youtube", "other"]


class User(BaseModel):
    id: UUID
    telegram_id: int | None = None
    created_at: datetime
    tier: str = "free"
    weekly_quota: int = 15
    timezone: str = "Asia/Kolkata"


class Item(BaseModel):
    id: UUID
    user_id: UUID
    url: str
    url_hash: str
    platform: Platform | None = None
    status: ItemStatus = "pending"

    creator_handle: str | None = None
    creator_url: str | None = None
    posted_at: datetime | None = None
    thumbnail_url: str | None = None
    duration_sec: int | None = None

    content_type: ContentType | None = None
    is_informational: bool | None = None
    is_time_sensitive: bool = False
    title: str | None = None
    summary: dict[str, Any] | None = None
    raw_transcript: str | None = None
    topics: list[str] = Field(default_factory=list)

    embedding: list[float] | None = None

    saved_at: datetime
    last_opened_at: datetime | None = None
    open_count: int = 0
    archived: bool = False


class UrlCacheEntry(BaseModel):
    url_hash: str
    payload: dict[str, Any]
    processed_at: datetime


class SearchEvent(BaseModel):
    id: UUID
    user_id: UUID
    query: str
    result_count: int = 0
    opened_item: UUID | None = None
    created_at: datetime


class ItemOpenEvent(BaseModel):
    id: UUID
    item_id: UUID
    user_id: UUID
    days_since_saved: int
    created_at: datetime
