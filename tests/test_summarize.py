import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from pipeline.summarize import SummaryResult, summarize


def _mock_client(response_json: dict) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.text = json.dumps(response_json)
    client.aio.models.generate_content = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
async def test_summarize_listicle_preserves_specifics():
    client = _mock_client(
        {
            "title": "5 tax-saving hacks beyond 80C",
            "is_time_sensitive": True,
            "headline": "5 tax-saving hacks beyond 80C",
            "items": [
                {"point": "NPS Tier 1 under 80CCD(1B)", "detail": "Extra 50000 deduction above 1.5L limit"}
            ],
        }
    )

    result = await summarize(client, "listicle", "some transcript")

    assert isinstance(result, SummaryResult)
    assert result.is_time_sensitive is True
    assert result.content["items"][0]["point"] == "NPS Tier 1 under 80CCD(1B)"
    assert "80CCD(1B)" in result.content["items"][0]["point"]


@pytest.mark.asyncio
async def test_summarize_tutorial_schema():
    client = _mock_client(
        {
            "title": "Deadlift form fix",
            "is_time_sensitive": False,
            "goal": "Deadlift with proper form",
            "steps": ["Feet hip-width apart", "Hinge at hips", "Drive through heels"],
            "tools_needed": ["barbell"],
        }
    )

    result = await summarize(client, "tutorial", "transcript")

    assert result.content["goal"] == "Deadlift with proper form"
    assert len(result.content["steps"]) == 3
    assert result.content["tools_needed"] == ["barbell"]


@pytest.mark.asyncio
async def test_summarize_recipe_schema():
    client = _mock_client(
        {
            "title": "15-min garlic shrimp pasta",
            "is_time_sensitive": False,
            "ingredients": ["200g spaghetti", "300g shrimp"],
            "method": ["Boil pasta", "Saute shrimp"],
            "time_min": 15,
        }
    )

    result = await summarize(client, "recipe", "transcript")

    assert result.content["time_min"] == 15
    assert result.content["ingredients"] == ["200g spaghetti", "300g shrimp"]


@pytest.mark.asyncio
async def test_summarize_explainer_schema():
    client = _mock_client(
        {
            "title": "Why the sky turns orange",
            "is_time_sensitive": False,
            "question": "Why does the sky turn orange at sunset?",
            "answer": "Rayleigh scattering removes blue wavelengths at low angles.",
            "key_points": ["Rayleigh scattering", "longer wavelengths reach the eye"],
        }
    )

    result = await summarize(client, "explainer", "transcript")

    assert result.content["question"].startswith("Why does the sky")
    assert "Rayleigh scattering" in result.content["key_points"]


@pytest.mark.asyncio
async def test_summarize_news_schema():
    client = _mock_client(
        {
            "title": "RBI holds repo rate at 6.5%",
            "is_time_sensitive": True,
            "headline": "RBI holds repo rate at 6.5%",
            "summary": "RBI kept rates unchanged citing inflation.",
            "key_facts": ["repo rate 6.5%"],
        }
    )

    result = await summarize(client, "news", "transcript")

    assert result.content["headline"] == "RBI holds repo rate at 6.5%"


@pytest.mark.asyncio
async def test_summarize_entertainment_schema():
    client = _mock_client(
        {
            "title": "Dog in matching outfit dances",
            "is_time_sensitive": False,
            "description": "Person dances with their dog in matching outfits to a trending song.",
        }
    )

    result = await summarize(client, "entertainment", "transcript")

    assert "dog" in result.content["description"]


@pytest.mark.asyncio
async def test_summarize_title_is_widget_safe_length():
    client = _mock_client(
        {
            "title": "Short punchy title",
            "is_time_sensitive": False,
            "description": "desc",
        }
    )

    result = await summarize(client, "entertainment", "transcript")

    assert len(result.title) <= 60


async def test_summarize_sends_video_when_media_present():
    from pipeline.media import MediaPayload

    client = _mock_client(
        {
            "title": "3 AI tools for slides",
            "is_time_sensitive": False,
            "headline": "3 AI tools for slides",
            "items": [{"point": "Gamma", "detail": "shown on screen at 0:14"}],
        }
    )

    result = await summarize(
        client,
        "listicle",
        "caption text",
        media=MediaPayload(data=b"videobytes", mime_type="video/mp4"),
    )

    assert result.content["items"][0]["point"] == "Gamma"
    contents = client.aio.models.generate_content.await_args.kwargs["contents"]
    parts = contents[0].parts
    assert parts[0].inline_data.data == b"videobytes"
    assert parts[0].inline_data.mime_type == "video/mp4"
    assert "caption text" in parts[1].text


async def test_summarize_without_media_sends_text_only():
    client = _mock_client(
        {"title": "t", "is_time_sensitive": False, "headline": "h", "items": []}
    )

    await summarize(client, "listicle", "just a transcript")

    contents = client.aio.models.generate_content.await_args.kwargs["contents"]
    parts = contents[0].parts
    assert parts[0].inline_data is None
    assert parts[0].text == "just a transcript"
