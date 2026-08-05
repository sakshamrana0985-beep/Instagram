"""Generic fallback adapter — any unsupported link saves as link-only."""
from __future__ import annotations

from adapters.base import SourceAdapter, SourceResult


class GenericAdapter(SourceAdapter):
    async def fetch(self, url: str) -> SourceResult:
        return SourceResult(
            platform="other",
            status="unsupported",
            creator_url=url,
        )
