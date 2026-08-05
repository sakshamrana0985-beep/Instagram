"""Renders a stored Item as a Telegram message, per content_type
(PRD §11/§14 rendering rules): listicle as a list, tutorial as numbered
steps, etc. Always shows creator handle + original post date + source
link, with a staleness warning on time-sensitive content.
"""
from __future__ import annotations

from storage.models import Item

MAX_TELEGRAM_MESSAGE_LEN = 4096


def _attribution(item: Item) -> str:
    lines = []
    if item.creator_handle:
        lines.append(f"👤 @{item.creator_handle}")
    if item.posted_at:
        lines.append(f"📅 {item.posted_at.strftime('%Y-%m-%d')}")
    link = item.creator_url or item.url
    lines.append(f"🔗 {link}")
    return "\n".join(lines)


def _render_body(item: Item) -> str:
    summary = item.summary or {}

    if item.content_type == "listicle":
        headline = summary.get("headline", item.title)
        lines = [f"*{headline}*", ""]
        for i, entry in enumerate(summary.get("items", []), start=1):
            point = entry.get("point", "")
            detail = entry.get("detail", "")
            lines.append(f"{i}. *{point}*" + (f" — {detail}" if detail else ""))
        return "\n".join(lines)

    if item.content_type == "tutorial":
        goal = summary.get("goal", item.title)
        lines = [f"*{goal}*", ""]
        for i, step in enumerate(summary.get("steps", []), start=1):
            lines.append(f"{i}. {step}")
        tools = summary.get("tools_needed") or []
        if tools:
            lines.append("")
            lines.append("🧰 Tools: " + ", ".join(tools))
        return "\n".join(lines)

    if item.content_type == "recipe":
        lines = [f"*{item.title}*", "", "*Ingredients:*"]
        for ing in summary.get("ingredients", []):
            lines.append(f"• {ing}")
        lines.append("")
        lines.append("*Method:*")
        for i, step in enumerate(summary.get("method", []), start=1):
            lines.append(f"{i}. {step}")
        time_min = summary.get("time_min")
        if time_min:
            lines.append("")
            lines.append(f"⏱ {time_min} min")
        return "\n".join(lines)

    if item.content_type == "explainer":
        question = summary.get("question", item.title)
        answer = summary.get("answer", "")
        lines = [f"*{question}*", "", answer]
        key_points = summary.get("key_points") or []
        if key_points:
            lines.append("")
            lines.extend(f"• {p}" for p in key_points)
        return "\n".join(lines)

    if item.content_type == "news":
        headline = summary.get("headline", item.title)
        lines = [f"*{headline}*", "", summary.get("summary", "")]
        key_facts = summary.get("key_facts") or []
        if key_facts:
            lines.append("")
            lines.extend(f"• {f}" for f in key_facts)
        return "\n".join(lines)

    # entertainment, or any content_type without a full template
    description = summary.get("description") or item.title or "Saved."
    return f"*{item.title or 'Saved'}*\n\n{description}"


def render_item(item: Item) -> str:
    if item.status == "unsupported":
        return f"Saved as a link (couldn't process this platform yet).\n🔗 {item.url}"
    if item.status == "failed":
        return f"Couldn't process this one — saved the link anyway.\n🔗 {item.url}"
    if item.status in ("pending", "processing"):
        return "Still processing…"

    parts = [_render_body(item)]
    if item.is_time_sensitive:
        parts.append("\n⚠️ This may be outdated — verify before acting on it.")
    parts.append("")
    parts.append(_attribution(item))

    text = "\n".join(parts)
    return text[:MAX_TELEGRAM_MESSAGE_LEN]


def render_search_result_card(item: Item, rank: int) -> str:
    handle = f"@{item.creator_handle}" if item.creator_handle else "unknown"
    saved = item.saved_at.strftime("%Y-%m-%d")
    return f"{rank}. *{item.title or 'Untitled'}*\n   {handle} · saved {saved}\n   🔗 {item.url}"
