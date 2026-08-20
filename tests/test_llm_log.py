import logging
from types import SimpleNamespace

import pytest

from pipeline.llm_log import estimate_cost_usd, log_call


def _response(prompt: int, candidates: int) -> SimpleNamespace:
    return SimpleNamespace(
        usage_metadata=SimpleNamespace(prompt_token_count=prompt, candidates_token_count=candidates)
    )


def test_estimate_cost_uses_per_model_pricing():
    cost = estimate_cost_usd("gemini-2.0-flash", input_tokens=1_000_000, output_tokens=0)
    assert cost == pytest.approx(0.10)


def test_estimate_cost_of_unknown_model_is_zero_not_a_crash():
    assert estimate_cost_usd("some-future-model", 1000, 1000) == 0.0


def test_log_call_records_model_tokens_latency_and_cost(caplog):
    with caplog.at_level(logging.INFO, logger="recall.llm"):
        with log_call("gemini-2.0-flash", "summarize", content_type="listicle") as slot:
            slot.append(_response(15_000, 400))

    record = caplog.records[-1].getMessage()
    assert "model=gemini-2.0-flash" in record
    assert "stage=summarize" in record
    assert "input_tokens=15000" in record
    assert "output_tokens=400" in record
    assert "est_cost_usd=" in record
    assert "latency=" in record
    assert "content_type=listicle" in record


def test_log_call_tolerates_a_response_without_usage(caplog):
    with caplog.at_level(logging.INFO, logger="recall.llm"):
        with log_call("gemini-2.0-flash", "summarize") as slot:
            slot.append(SimpleNamespace())

    assert "input_tokens=0" in caplog.records[-1].getMessage()


def test_log_call_logs_and_reraises_failures(caplog):
    with caplog.at_level(logging.INFO, logger="recall.llm"):
        with pytest.raises(RuntimeError, match="model down"):
            with log_call("gemini-2.0-flash", "summarize"):
                raise RuntimeError("model down")

    record = caplog.records[-1].getMessage()
    assert "status=failed" in record
    assert "model down" in record
