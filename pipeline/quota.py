"""Free-tier cap (PRD §8).

"Free tier must be capped" — a user saving 40 items/day costs ~$12/month, and
Phase 0 runs on free credits with 50 volunteers. The cap is per-user and lives
on users.weekly_quota, so raising it for one person is a DB update, not a deploy.

Rolling 7-day window rather than a calendar week: no Monday-midnight cliff, and
nothing to reset on a schedule.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from storage import db
from storage.models import User

WINDOW_DAYS = 7


class QuotaStatus(BaseModel):
    allowed: bool
    used: int
    limit: int

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)


async def check_quota(pool, user: User) -> QuotaStatus:
    since = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    used = await db.count_items_saved_since(pool, user.id, since)
    return QuotaStatus(allowed=used < user.weekly_quota, used=used, limit=user.weekly_quota)
