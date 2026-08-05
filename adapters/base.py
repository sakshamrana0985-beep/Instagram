"""SourceAdapter interface (CLAUDE.md rule 1).

Every platform-specific fetch lives behind this interface. Nothing downstream
of an adapter may contain platform-specific logic — adding a platform means
adding one file here, nothing else.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Platform = Literal["instagram", "youtube", "other"]


class SourceResult(BaseModel):
    platform: Platform
    status: Literal["ok", "unsupported", "failed"]
    caption: str | None = None
    transcript: str | None = None
    media_url: str | None = None
    creator_handle: str | None = None
    creator_url: str | None = None
    posted_at: datetime | None = None
    thumbnail_url: str | None = None
    duration_sec: int | None = None
    error: str | None = None


class SourceAdapter(ABC):
    """One implementation per platform. See adapters/youtube.py, adapters/generic.py."""

    @abstractmethod
    async def fetch(self, url: str) -> SourceResult:
        ...
