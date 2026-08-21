import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from pipeline.classify import ClassificationResult, classify


def _mock_client(response_json: dict) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.text = json.dumps(response_json)
    client.aio.models.generate_content = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
async def test_classify_parses_valid_response():
    client = _mock_client(
        {
            "content_type": "listicle",
            "is_informational": True,
            "topics": ["tax", "finance"],
            "confidence": 0.92,
        }
    )

    result = await classify(client, "5 tax-saving hacks beyond 80C")

    assert isinstance(result, ClassificationResult)
    assert result.content_type == "listicle"
    assert result.is_informational is True
    assert result.topics == ["tax", "finance"]
    assert result.confidence == 0.92


@pytest.mark.asyncio
async def test_classify_entertainment_is_not_informational():
    client = _mock_client(
        {
            "content_type": "entertainment",
            "is_informational": False,
            "topics": ["meme"],
            "confidence": 0.88,
        }
    )

    result = await classify(client, "POV: dancing to a trending sound")

    assert result.content_type == "entertainment"
    assert result.is_informational is False


@pytest.mark.asyncio
async def test_classify_passes_text_and_system_prompt_to_model():
    client = _mock_client(
        {"content_type": "recipe", "is_informational": True, "topics": ["cooking"], "confidence": 0.8}
    )

    await classify(client, "15 minute garlic butter shrimp pasta")

    _, kwargs = client.aio.models.generate_content.call_args
    assert kwargs["contents"] == "15 minute garlic butter shrimp pasta"
    assert kwargs["config"].response_mime_type == "application/json"


async def test_classify_logs_model_tokens_and_cost(caplog):
    """CLAUDE.md: every LLM call logs model, tokens, latency, cost estimate."""
    import logging
    from types import SimpleNamespace

    client = _mock_client(
        {"content_type": "listicle", "is_informational": True, "topics": ["tax"], "confidence": 0.9}
    )
    client.aio.models.generate_content.return_value.usage_metadata = SimpleNamespace(
        prompt_token_count=800, candidates_token_count=40
    )

    with caplog.at_level(logging.INFO, logger="recall.llm"):
        await classify(client, "some caption")

    record = caplog.records[-1].getMessage()
    assert "model=gemini-3.5-flash-lite" in record
    assert "input_tokens=800" in record
    assert "est_cost_usd=" in record
