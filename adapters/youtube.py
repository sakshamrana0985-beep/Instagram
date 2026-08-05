"""YouTube adapter — captions only, zero AI cost when they exist (PRD §8, §9)."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

from adapters.base import SourceAdapter, SourceResult

_VIDEO_ID_RE = re.compile(r"^[0-9A-Za-z_-]{11}$")
_SHORTS_RE = re.compile(r"/shorts/([0-9A-Za-z_-]{11})")


def extract_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if host in ("youtu.be", "www.youtu.be"):
        video_id = parsed.path.lstrip("/").split("/")[0]
        return video_id if _VIDEO_ID_RE.match(video_id) else None

    if "youtube.com" not in host:
        return None

    query_id = parse_qs(parsed.query).get("v", [None])[0]
    if query_id and _VIDEO_ID_RE.match(query_id):
        return query_id

    match = _SHORTS_RE.search(parsed.path)
    if match:
        return match.group(1)

    return None


class YouTubeAdapter(SourceAdapter):
    def __init__(self) -> None:
        self._api = YouTubeTranscriptApi()

    async def fetch(self, url: str) -> SourceResult:
        video_id = extract_video_id(url)
        if video_id is None:
            return SourceResult(
                platform="youtube",
                status="failed",
                error=f"could not extract video id from url: {url}",
            )

        try:
            fetched = self._api.fetch(video_id, languages=("en",))
        except (NoTranscriptFound, TranscriptsDisabled) as exc:
            return SourceResult(
                platform="youtube",
                status="failed",
                error=f"no captions available: {exc}",
                creator_url=url,
            )
        except VideoUnavailable as exc:
            return SourceResult(
                platform="youtube",
                status="failed",
                error=f"video unavailable: {exc}",
            )
        except CouldNotRetrieveTranscript as exc:
            return SourceResult(
                platform="youtube",
                status="failed",
                error=f"could not retrieve transcript: {exc}",
            )

        transcript = " ".join(snippet.text for snippet in fetched.snippets)
        return SourceResult(
            platform="youtube",
            status="ok",
            transcript=transcript,
            creator_url=f"https://www.youtube.com/watch?v={video_id}",
        )
