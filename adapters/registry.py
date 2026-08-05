"""Picks a SourceAdapter by URL pattern. Adding a platform = one entry here."""
from __future__ import annotations

import re

from adapters.base import SourceAdapter
from adapters.generic import GenericAdapter
from adapters.youtube import YouTubeAdapter

_YOUTUBE_RE = re.compile(r"(youtube\.com|youtu\.be)")
_INSTAGRAM_RE = re.compile(r"instagram\.com")

_youtube = YouTubeAdapter()
_generic = GenericAdapter()


def get_adapter(url: str) -> SourceAdapter:
    if _YOUTUBE_RE.search(url):
        return _youtube
    if _INSTAGRAM_RE.search(url):
        from adapters.instagram import InstagramAdapter  # imported lazily, added in session 6

        return InstagramAdapter()
    return _generic
