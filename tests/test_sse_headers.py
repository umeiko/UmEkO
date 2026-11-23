import asyncio

import pytest
from starlette.datastructures import Headers

from umeko.server.sse import SSEHeadersMiddleware


@pytest.mark.parametrize("cache_headers,expected", [
    ([], {"no-cache"}),
    ([(b"cache-control", b"no-store")], {"no-cache", "no-store"}),
    ([(b"cache-control", b"no-cache, no-transform")], {"no-cache", "no-transform"}),
    ([(b"cache-control", b"private"), (b"cache-control", b"no-store")], {"no-cache", "private", "no-store"}),
])
def test_sse_headers_preserve_privacy_cookies_and_immediate_chunks(cache_headers, expected):
    sent = []
    cookies = [(b"set-cookie", b"first=one"), (b"set-cookie", b"second=two")]

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [
            (b"content-type", b"text/event-stream; charset=utf-8"),
            (b"x-accel-buffering", b"yes"), *cache_headers, *cookies]})
        await send({"type": "http.response.body", "body": b"data: first\n\n", "more_body": True})
        assert sent[-1]["body"] == b"data: first\n\n"  # Already forwarded before producing the next event.
        await send({"type": "http.response.body", "body": b"data: second\n\n", "more_body": False})

    async def send(message):
        sent.append(message)

    asyncio.run(SSEHeadersMiddleware(app)({"type": "http"}, None, send))
    headers = Headers(raw=sent[0]["headers"])
    assert headers["content-type"] == "text/event-stream; charset=utf-8"
    assert set(headers["cache-control"].split(", ")) == expected
    assert headers["x-accel-buffering"] == "no"
    assert headers.getlist("set-cookie") == ["first=one", "second=two"]
    assert [message["body"] for message in sent[1:]] == [b"data: first\n\n", b"data: second\n\n"]


@pytest.mark.parametrize("scope_type", ["http", "lifespan", "websocket"])
def test_other_responses_and_protocols_are_forwarded_unchanged(scope_type):
    message = ({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"application/json"), (b"cache-control", b"private, no-store")]}
               if scope_type == "http" else {"type": "lifespan.startup.complete" if scope_type == "lifespan" else "websocket.accept"})
    received = []

    async def app(scope, receive, send):
        await send(message)

    async def send(value):
        received.append(value)

    asyncio.run(SSEHeadersMiddleware(app)({"type": scope_type}, None, send))
    assert received == [message]
    if scope_type == "http":
        assert Headers(raw=received[0]["headers"])["cache-control"] == "private, no-store"
        assert "x-accel-buffering" not in Headers(raw=received[0]["headers"])
