from adapters.generic import GenericAdapter
from adapters.registry import get_adapter
from adapters.youtube import YouTubeAdapter


def test_registry_picks_youtube_adapter():
    assert isinstance(get_adapter("https://www.youtube.com/watch?v=abc"), YouTubeAdapter)
    assert isinstance(get_adapter("https://youtu.be/abc"), YouTubeAdapter)


def test_registry_picks_generic_adapter_for_unknown_platform():
    assert isinstance(get_adapter("https://example.com/article"), GenericAdapter)
