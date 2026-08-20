"""One place to log every LLM call: model, tokens, latency, cost estimate
(CLAUDE.md code conventions).

Phase 0 runs on free tiers, so these numbers are not a bill — they are the
early-warning signal for what the bill becomes at 50 users, and the evidence
behind the ~$0.01/item figure in PRD §8.

Prices are USD per million tokens, correct for the models pinned in this
repo. They are estimates, logged as estimates; when a price moves, update the
table here rather than hunting for arithmetic spread across call sites.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass

logger = logging.getLogger("recall.llm")


@dataclass(frozen=True)
class Price:
    input_per_m: float
    output_per_m: float


PRICES: dict[str, Price] = {
    "gemini-2.0-flash-lite": Price(input_per_m=0.075, output_per_m=0.30),
    "gemini-2.0-flash": Price(input_per_m=0.10, output_per_m=0.40),
    "gemini-embedding-001": Price(input_per_m=0.15, output_per_m=0.0),
    "whisper-large-v3-turbo": Price(input_per_m=0.0, output_per_m=0.0),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price = PRICES.get(model)
    if price is None:
        return 0.0
    return (input_tokens * price.input_per_m + output_tokens * price.output_per_m) / 1_000_000


def _usage_from_response(response: object) -> tuple[int, int]:
    """Reads the google-genai usage block, tolerating a missing one — a mocked
    or future response shape must never break a call that already succeeded."""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return 0, 0
    prompt = getattr(usage, "prompt_token_count", 0) or 0
    candidates = getattr(usage, "candidates_token_count", 0) or 0
    return int(prompt), int(candidates)


@contextmanager
def log_call(model: str, stage: str, **fields: object):
    """Wraps one model call. Yields a one-slot list — put the response in it
    and the token counts come from there; leave it empty and only latency and
    the failure are logged.

        with log_call(MODEL, "classify") as slot:
            response = await client.aio.models.generate_content(...)
            slot.append(response)
    """
    slot: list = []
    started = time.monotonic()
    extra = " ".join(f"{k}={v}" for k, v in fields.items())
    try:
        yield slot
    except Exception as exc:  # noqa: BLE001 — log and re-raise, never swallow
        logger.info(
            "llm_call model=%s stage=%s status=failed latency=%.2fs error=%s %s",
            model,
            stage,
            time.monotonic() - started,
            exc,
            extra,
        )
        raise

    latency = time.monotonic() - started
    input_tokens, output_tokens = _usage_from_response(slot[0]) if slot else (0, 0)
    logger.info(
        "llm_call model=%s stage=%s status=ok latency=%.2fs input_tokens=%d "
        "output_tokens=%d est_cost_usd=%.6f %s",
        model,
        stage,
        latency,
        input_tokens,
        output_tokens,
        estimate_cost_usd(model, input_tokens, output_tokens),
        extra,
    )
