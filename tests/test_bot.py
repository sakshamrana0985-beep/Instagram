import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from bot import main as bot_main
from bot.main import _extract_first_url
from pipeline.quota import QuotaStatus
from storage.models import Item

from .conftest import requires_postgres

pytestmark = requires_postgres


@pytest.mark.parametrize(
    "text,expected",
    [
        ("check this out https://www.instagram.com/reel/abc123/ so good", "https://www.instagram.com/reel/abc123/"),
        ("https://youtu.be/dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ"),
        ("no link here", None),
        ("", None),
    ],
)
def test_extract_first_url(text, expected):
    assert _extract_first_url(text) == expected


def _make_update(text: str, user_id: int = 42, chat_id: int = 99):
    message = MagicMock()
    message.text = text
    message.reply_text = AsyncMock(return_value=SimpleNamespace(message_id=555))
    return SimpleNamespace(
        message=message,
        effective_chat=SimpleNamespace(id=chat_id),
        effective_user=SimpleNamespace(id=user_id),
    )


def _make_context(pool, gemini_client=None, apify_token=None, args=None):
    """`background_tasks` lets a test await the work handle_link kicked off,
    without making handle_link itself blocking."""
    background_tasks: list[asyncio.Future] = []

    def _create_task(coro):
        task = asyncio.ensure_future(coro)
        background_tasks.append(task)
        return task

    application = SimpleNamespace(
        bot_data={
            "pool": pool,
            "gemini_client": gemini_client,
            "apify_token": apify_token,
            "groq_api_key": None,
        },
        create_task=MagicMock(side_effect=_create_task),
        background_tasks=background_tasks,
    )
    return SimpleNamespace(
        application=application,
        bot=SimpleNamespace(edit_message_text=AsyncMock(), send_message=AsyncMock()),
        args=args or [],
        user_data={},
    )


@pytest.mark.asyncio
async def test_handle_link_acks_instantly_without_waiting_for_pipeline(pool, monkeypatch):
    """The hard requirement from build plan session 8: reply immediately,
    process in the background. If handle_link awaited the pipeline directly,
    this test would hang until the never-resolving mock completes."""
    never_finishes = asyncio.get_event_loop().create_future()
    monkeypatch.setattr(bot_main, "process_url", AsyncMock(return_value=never_finishes))

    update = _make_update("check this out https://youtu.be/abc12345678")
    context = _make_context(pool)

    await asyncio.wait_for(bot_main.handle_link(update, context), timeout=1)

    update.message.reply_text.assert_awaited_once_with("Saved ✓")
    context.application.create_task.assert_called_once()

    never_finishes.cancel()


@pytest.mark.asyncio
async def test_handle_link_ignores_messages_without_a_url(pool):
    update = _make_update("just chatting, no link")
    context = _make_context(pool)

    await bot_main.handle_link(update, context)

    update.message.reply_text.assert_not_called()


async def _make_user(pool, telegram_id: int):
    row = await pool.fetchrow("insert into users (telegram_id) values ($1) returning id", telegram_id)
    return row["id"]


def _fake_item(user_id, **overrides) -> Item:
    from datetime import datetime, timezone

    item_id = uuid4()
    defaults = dict(
        id=item_id,
        user_id=user_id,
        url=f"https://youtube.com/watch?v={item_id}",
        url_hash=str(item_id),
        platform="youtube",
        status="ready",
        title="5 tax hacks",
        summary={"headline": "5 tax hacks", "items": []},
        content_type="listicle",
        topics=["tax"],
        saved_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Item.model_validate(defaults)


@pytest.mark.asyncio
async def test_search_command_reports_no_results_message(pool, monkeypatch):
    telegram_id = 111
    monkeypatch.setattr(bot_main, "hybrid_search", AsyncMock(return_value=[]))

    update = _make_update("", user_id=telegram_id)
    context = _make_context(pool, args=["tax", "hacks"])

    await bot_main.search_command(update, context)

    update.message.reply_text.assert_awaited_once()
    (call_text,), _ = update.message.reply_text.call_args
    assert "No results" in call_text


@pytest.mark.asyncio
async def test_search_command_with_no_query_shows_usage(pool):
    update = _make_update("", user_id=222)
    context = _make_context(pool, args=[])

    await bot_main.search_command(update, context)

    (call_text,), _ = update.message.reply_text.call_args
    assert "Usage" in call_text


@pytest.mark.asyncio
async def test_search_command_shows_results_and_logs_search_event(pool, monkeypatch):
    from pipeline.search import SearchResult

    user_id = await _make_user(pool, 333)
    item = _fake_item(user_id)
    monkeypatch.setattr(
        bot_main, "hybrid_search", AsyncMock(return_value=[SearchResult(item=item, score=1.0)])
    )

    update = _make_update("", user_id=333)
    context = _make_context(pool, args=["tax"])

    await bot_main.search_command(update, context)

    update.message.reply_text.assert_awaited_once()
    _, kwargs = update.message.reply_text.call_args
    assert "reply_markup" in kwargs

    row = await pool.fetchrow("select * from search_events where user_id = $1", user_id)
    assert row["query"] == "tax"
    assert row["result_count"] == 1


@pytest.mark.asyncio
async def test_stats_command_reports_user_counts(pool):
    telegram_id = 444
    user_id = await _make_user(pool, telegram_id)
    from storage.db import upsert_item

    await upsert_item(pool, _fake_item(user_id))

    update = _make_update("", user_id=telegram_id)
    context = _make_context(pool)

    await bot_main.stats_command(update, context)

    (call_text,), _ = update.message.reply_text.call_args
    assert "Items saved: 1" in call_text


@pytest.mark.asyncio
async def test_admin_command_reports_gate_status(pool):
    update = _make_update("", user_id=555)
    context = _make_context(pool)

    await bot_main.admin_command(update, context)

    (call_text,), _ = update.message.reply_text.call_args
    assert "Gate" in call_text


@pytest.mark.asyncio
async def test_open_item_callback_logs_open_and_sends_item(pool):
    from storage.db import upsert_item

    telegram_id = 666
    user_id = await _make_user(pool, telegram_id)
    item = _fake_item(user_id)
    await upsert_item(pool, item)

    callback_query = SimpleNamespace(data=f"open:{item.id}", answer=AsyncMock())
    update = SimpleNamespace(
        callback_query=callback_query,
        effective_user=SimpleNamespace(id=telegram_id),
        effective_chat=SimpleNamespace(id=777),
    )
    context = _make_context(pool)

    await bot_main.open_item_callback(update, context)

    callback_query.answer.assert_awaited_once()
    context.bot.send_message.assert_awaited_once()

    row = await pool.fetchrow("select * from item_open_events where item_id = $1", item.id)
    assert row is not None


@pytest.mark.asyncio
async def test_handle_link_refuses_over_quota_before_any_paid_call(pool, monkeypatch):
    process_mock = AsyncMock()
    monkeypatch.setattr(bot_main, "process_url", process_mock)
    monkeypatch.setattr(
        bot_main,
        "check_quota",
        AsyncMock(return_value=QuotaStatus(allowed=False, used=15, limit=15)),
    )

    update = _make_update("https://instagram.com/reel/abc")
    context = _make_context(pool)
    await bot_main.handle_link(update, context)
    await asyncio.gather(*context.application.background_tasks)

    process_mock.assert_not_awaited()
    text = context.bot.edit_message_text.await_args.kwargs["text"]
    assert "free limit of 15" in text
    assert "/search still works" in text


@pytest.mark.asyncio
async def test_handle_link_processes_when_under_quota(pool, monkeypatch):
    item = Item(
        id=uuid4(),
        user_id=uuid4(),
        url="https://instagram.com/reel/abc",
        url_hash="h",
        status="ready",
        content_type="listicle",
        title="3 AI tools",
        summary={"headline": "3 AI tools", "items": []},
        saved_at=datetime.now(timezone.utc),
    )
    process_mock = AsyncMock(return_value=item)
    monkeypatch.setattr(bot_main, "process_url", process_mock)
    monkeypatch.setattr(
        bot_main, "check_quota", AsyncMock(return_value=QuotaStatus(allowed=True, used=1, limit=15))
    )

    update = _make_update("https://instagram.com/reel/abc")
    context = _make_context(pool)
    await bot_main.handle_link(update, context)
    await asyncio.gather(*context.application.background_tasks)

    process_mock.assert_awaited()
