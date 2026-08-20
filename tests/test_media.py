import httpx
import pytest

from pipeline.media import MAX_MEDIA_BYTES, fetch_media


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.fixture
def patched_client(monkeypatch):
    def install(handler):
        real_init = httpx.AsyncClient.__init__

        def init(self, *args, **kwargs):
            kwargs["transport"] = _transport(handler)
            real_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", init)

    return install


async def test_fetch_media_returns_none_without_url():
    assert await fetch_media(None) is None
    assert await fetch_media("") is None


async def test_fetch_media_downloads_video(patched_client):
    patched_client(
        lambda request: httpx.Response(200, content=b"\x00\x01video", headers={"content-type": "video/mp4"})
    )

    payload = await fetch_media("https://cdn.example.com/reel.mp4")

    assert payload is not None
    assert payload.data == b"\x00\x01video"
    assert payload.mime_type == "video/mp4"


async def test_fetch_media_rejects_oversized_declared_length(patched_client):
    patched_client(
        lambda request: httpx.Response(
            200,
            content=b"x" * 10,
            headers={"content-type": "video/mp4", "content-length": str(MAX_MEDIA_BYTES + 1)},
        )
    )

    assert await fetch_media("https://cdn.example.com/huge.mp4") is None


async def test_fetch_media_rejects_oversized_stream(patched_client):
    patched_client(lambda request: httpx.Response(200, content=b"x" * 50, headers={"content-type": "video/mp4"}))

    assert await fetch_media("https://cdn.example.com/huge.mp4", max_bytes=10) is None


async def test_fetch_media_rejects_non_media_content_type(patched_client):
    patched_client(lambda request: httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"}))

    assert await fetch_media("https://cdn.example.com/login") is None


async def test_fetch_media_swallows_http_errors(patched_client):
    patched_client(lambda request: httpx.Response(404))

    assert await fetch_media("https://cdn.example.com/gone.mp4") is None


async def test_fetch_media_swallows_transport_errors(patched_client):
    def boom(request):
        raise httpx.ConnectError("dns fail", request=request)

    patched_client(boom)

    assert await fetch_media("https://cdn.example.com/reel.mp4") is None
