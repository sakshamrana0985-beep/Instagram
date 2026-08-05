"""Instrumentation the week-4 gate depends on (build plan session 10):

    >=25% of users run a search in week 2 or later

Make that number impossible to misread — it's computed here by one
function, named for exactly what it measures, not buried in ad-hoc SQL
scattered across the bot.
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from pydantic import BaseModel


class AdminStats(BaseModel):
    total_users: int
    items_saved: int
    searches_run: int
    users_searched_week2_plus: int
    pct_users_searched_week2_plus: float
    retrieval_rate: float  # % of saved items opened again after 7+ days — the north star


class UserStats(BaseModel):
    items_saved: int
    items_opened: int


async def get_admin_stats(pool: asyncpg.Pool) -> AdminStats:
    total_users = await pool.fetchval("select count(*) from users") or 0
    items_saved = await pool.fetchval("select count(*) from items") or 0
    searches_run = await pool.fetchval("select count(*) from search_events") or 0

    users_searched_week2_plus = (
        await pool.fetchval(
            """
            select count(distinct se.user_id)
            from search_events se
            join users u on u.id = se.user_id
            where se.created_at >= u.created_at + interval '7 days'
            """
        )
        or 0
    )
    pct_users_searched_week2_plus = (
        users_searched_week2_plus / total_users if total_users else 0.0
    )

    items_opened_after_7_days = (
        await pool.fetchval(
            "select count(distinct item_id) from item_open_events where days_since_saved >= 7"
        )
        or 0
    )
    retrieval_rate = items_opened_after_7_days / items_saved if items_saved else 0.0

    return AdminStats(
        total_users=total_users,
        items_saved=items_saved,
        searches_run=searches_run,
        users_searched_week2_plus=users_searched_week2_plus,
        pct_users_searched_week2_plus=pct_users_searched_week2_plus,
        retrieval_rate=retrieval_rate,
    )


async def get_user_stats(pool: asyncpg.Pool, user_id: UUID) -> UserStats:
    items_saved = await pool.fetchval("select count(*) from items where user_id = $1", user_id) or 0
    items_opened = (
        await pool.fetchval(
            "select count(distinct item_id) from item_open_events where user_id = $1", user_id
        )
        or 0
    )
    return UserStats(items_saved=items_saved, items_opened=items_opened)
