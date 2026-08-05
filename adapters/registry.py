"""Picks a SourceAdapter by URL pattern. Adding a platform = one entry here."""
from __future__ import annotations

import re

from adapters.base import SourceAdapter
from adapters.generic import GenericAdapter
from adapters.instagram import InstagramAdapter
from adapters.youtube import YouTubeAdapter

_YOUTUBE_RE = re.compile(r"(youtube\.com|youtu\.be)")
_INSTAGRAM_RE = re.compile(r"instagram\.com")

_youtube = YouTubeAdapter()
_generic = GenericAdapter()
_instagram_by_token: dict[str | None, InstagramAdapter] = {}


def get_adapter(url: str, apify_token: str | None = None) -> SourceAdapter:
    if _YOUTUBE_RE.search(url):
        return _youtube
    if _INSTAGRAM_RE.search(url):
        if apify_token not in _instagram_by_token:
            _instagram_by_token[apify_token] = InstagramAdapter(apify_token=apify_token)
        return _instagram_by_token[apify_token]
    return _generic
