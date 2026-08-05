"""Hybrid search (PRD §12): vector search handles "that thing about saving
tax", keyword search handles "80CCD" — vector alone fails the second one.
Merge with reciprocal rank fusion, boost recently-saved items on ties.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from google import genai
from pydantic import BaseModel

from pipeline.embed import embed_query
from storage import db
from storage.models import Item

RRF_K = 60
FETCH_LIMIT_PER_METHOD = 20


class SearchResult(BaseModel):
    item: Item
    score: float


def _recency_boost(item: Item, now: datetime) -> float:
    age_days = max((now - item.saved_at).days, 0)
    return 1.0 / (1.0 + age_days)


def _reciprocal_rank_fusion(
    ranked_lists: list[list[Item]], now: datetime, k: int = RRF_K
) -> list[SearchResult]:
    scores: dict[UUID, float] = {}
    items_by_id: dict[UUID, Item] = {}

    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            items_by_id[item.id] = item
            scores[item.id] = scores.get(item.id, 0.0) + 1.0 / (k + rank)

    # tiny recency nudge to break ties without letting it dominate real relevance
    for item_id, item in items_by_id.items():
        scores[item_id] += _recency_boost(item, now) * 1e-6

    ordered = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    return [SearchResult(item=items_by_id[item_id], score=score) for item_id, score in ordered]


async def hybrid_search(
    pool,
    gemini_client: genai.Client,
    user_id: UUID,
    query: str,
    limit: int = 10,
) -> list[SearchResult]:
    query_embedding = await embed_query(gemini_client, query)

    vector_results = await db.vector_search(pool, user_id, query_embedding, limit=FETCH_LIMIT_PER_METHOD)
    keyword_results = await db.keyword_search(pool, user_id, query, limit=FETCH_LIMIT_PER_METHOD)

    merged = _reciprocal_rank_fusion([vector_results, keyword_results], now=datetime.now(timezone.utc))
    return merged[:limit]
