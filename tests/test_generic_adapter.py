import pytest

from adapters.generic import GenericAdapter


@pytest.mark.asyncio
async def test_generic_adapter_returns_unsupported():
    adapter = GenericAdapter()
    result = await adapter.fetch("https://example.com/some-article")
    assert result.status == "unsupported"
    assert result.platform == "other"
    assert result.creator_url == "https://example.com/some-article"
