"""Apply proxy headers to every SSE response, including SDK-owned routes."""
from starlette.datastructures import Headers, MutableHeaders


class SSEHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_headers(message):
            if message["type"] == "http.response.start":
                content_type = Headers(raw=message.get("headers", [])).get("content-type", "")
                if content_type.split(";", 1)[0].strip().lower() == "text/event-stream":
                    headers = MutableHeaders(scope=message)
                    cache_control = ", ".join(headers.getlist("cache-control"))
                    directives = {value.strip().lower() for value in cache_control.split(",")}
                    if "no-cache" not in directives:
                        # Preserve no-store/privacy and SDK no-transform directives.
                        headers["Cache-Control"] = "no-cache" + (", " + cache_control if cache_control else "")
                    headers["X-Accel-Buffering"] = "no"
            await send(message)

        # Forward each body chunk immediately; only the response-start is changed.
        await self.app(scope, receive, send_headers)
