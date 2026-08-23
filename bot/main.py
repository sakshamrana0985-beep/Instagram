"""Telegram bot (build plan session 8).

Instant acknowledgement is a hard requirement: any link gets "Saved ✓"
back immediately, with the actual pipeline running in a background task
that edits the message once ready. No spinner, no waiting — that's the
whole habit-gap risk from PRD §15.
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys
from uuid import UUID

from google import genai
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import InvalidToken
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

sys.path.insert(0, ".")

from bot.render import render_item, render_search_result_card
from config import Settings, load_settings
from pipeline.analytics import get_admin_stats, get_user_stats
from pipeline.process import process_url
from pipeline.quota import check_quota
from pipeline.search import hybrid_search
from storage import db

logger = logging.getLogger("recall.bot")

_URL_RE = re.compile(r"https?://\S+")


def _extract_first_url(text: str) -> str | None:
    match = _URL_RE.search(text or "")
    return match.group(0) if match else None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Forward or paste a link and I'll save it. Use /search <query> to find "
        "something you saved before, /stats for your numbers."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = _extract_first_url(update.message.text)
    if url is None:
        return

    ack = await update.message.reply_text("Saved ✓")
    context.application.create_task(
        _process_and_edit(context, update.effective_chat.id, ack.message_id, update.effective_user.id, url)
    )


async def _process_and_edit(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, telegram_user_id: int, url: str
) -> None:
    pool = context.application.bot_data["pool"]
    client: genai.Client = context.application.bot_data["gemini_client"]
    apify_token: str = context.application.bot_data["apify_token"]
    groq_api_key: str = context.application.bot_data["groq_api_key"]

    try:
        user = await db.get_or_create_user(pool, telegram_user_id)

        # Checked after the ack, before any paid call: the cap exists to bound
        # cost (PRD §8), and the instant reply is the habit requirement.
        quota = await check_quota(pool, user)
        if not quota.allowed:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=(
                    f"You've hit the free limit of {quota.limit} saves a week. "
                    "It resets as your older saves roll past 7 days — "
                    f"/search still works on everything you already have.\n🔗 {url}"
                ),
            )
            return

        item = await process_url(
            pool, client, url, user.id, apify_token=apify_token, groq_api_key=groq_api_key
        )
        text = render_item(item)
    except Exception:  # noqa: BLE001 — a pipeline failure must never crash the bot
        logger.exception("failed to process url=%s", url)
        text = f"Something went wrong saving this — the link is safe, try /search later.\n🔗 {url}"

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text, parse_mode=ParseMode.MARKDOWN
        )
    except Exception:  # noqa: BLE001 — e.g. markdown parse errors on odd summary text
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pool = context.application.bot_data["pool"]
    client: genai.Client = context.application.bot_data["gemini_client"]

    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Usage: /search <query>")
        return

    user = await db.get_or_create_user(pool, update.effective_user.id)
    results = await hybrid_search(pool, client, user.id, query)
    event_id = await db.log_search_event(pool, user.id, query, len(results))
    context.user_data["last_search_event_id"] = str(event_id)

    if not results:
        await update.message.reply_text("No results yet — save a few things first.")
        return

    text = "\n\n".join(render_search_result_card(r.item, i) for i, r in enumerate(results, start=1))
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"Open #{i}", callback_data=f"open:{r.item.id}")] for i, r in enumerate(results, start=1)]
    )
    await update.message.reply_text(
        text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True, reply_markup=keyboard
    )


async def open_item_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pool = context.application.bot_data["pool"]
    query = update.callback_query
    await query.answer()

    item_id = UUID(query.data.split(":", 1)[1])
    user = await db.get_or_create_user(pool, update.effective_user.id)

    await db.log_item_open(pool, item_id, user.id)
    search_event_id = context.user_data.get("last_search_event_id")
    if search_event_id:
        await db.mark_search_opened(pool, UUID(search_event_id), item_id)

    item = await db.get_item(pool, item_id)
    if item is None:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="That item is gone.")
        return

    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=render_item(item), parse_mode=ParseMode.MARKDOWN
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pool = context.application.bot_data["pool"]
    user = await db.get_or_create_user(pool, update.effective_user.id)
    stats = await get_user_stats(pool, user.id)
    quota = await check_quota(pool, user)
    await update.message.reply_text(
        f"📊 Items saved: {stats.items_saved}\n"
        f"📖 Items opened: {stats.items_opened}\n"
        f"🎟 Saves left this week: {quota.remaining}/{quota.limit}"
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unrestricted for the ~50-person Phase 0 volunteer test (build plan
    session 10). Gate access before a wider launch."""
    pool = context.application.bot_data["pool"]
    stats = await get_admin_stats(pool)
    gate_status = "PASS" if stats.pct_users_searched_week2_plus >= 0.25 else "below target"
    await update.message.reply_text(
        f"👥 Users: {stats.total_users}\n"
        f"💾 Items saved: {stats.items_saved}\n"
        f"🔍 Searches run: {stats.searches_run}\n"
        f"📈 Searched in week 2+: {stats.users_searched_week2_plus}/{stats.total_users} "
        f"({stats.pct_users_searched_week2_plus:.0%})\n"
        f"♻️ Retrieval rate (opened 7+ days later): {stats.retrieval_rate:.0%}\n\n"
        f"Gate (>=25% week-2+ search rate): {gate_status}"
    )


def build_application(settings: Settings, pool, gemini_client: genai.Client) -> Application:
    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data["pool"] = pool
    application.bot_data["gemini_client"] = gemini_client
    application.bot_data["apify_token"] = settings.apify_token
    application.bot_data["groq_api_key"] = settings.groq_api_key

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CallbackQueryHandler(open_item_callback, pattern=r"^open:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    return application


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    try:
        settings = load_settings()
    except RuntimeError as exc:
        # A missing key is a setup mistake, not a bug — say so in one line
        # instead of a traceback.
        print(f"\nCannot start: {exc}\n", file=sys.stderr)
        raise SystemExit(1) from None
    pool = await db.get_pool(settings.supabase_db_url)
    gemini_client = genai.Client(api_key=settings.gemini_api_key)

    application = build_application(settings, pool, gemini_client)
    try:
        async with application:
            await application.start()
            await application.updater.start_polling()
            try:
                await asyncio.Event().wait()
            finally:
                await application.updater.stop()
                await application.stop()
    except InvalidToken:
        # Telegram rejects a malformed or revoked token at startup. That is a
        # configuration mistake, so say which value is wrong rather than
        # printing forty lines of library traceback.
        print(
            "\nTelegram rejected the bot token in TELEGRAM_BOT_TOKEN.\n"
            "It should look like 12345678:AAF... - get it from @BotFather on Telegram.\n"
            "Fix it with:  python scripts/first_run.py\n",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    asyncio.run(_main())
