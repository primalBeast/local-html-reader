"""Security headers and optional dev CORS.

Implemented as raw ASGI (not BaseHTTPMiddleware) so Server-Sent Event
streams are not buffered until the search finishes.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Receive, Scope, Send


def _is_view_path(path: str) -> bool:
    return path == "/view" or path.startswith("/view/")


def _is_stream_path(path: str) -> bool:
    return path.endswith("/stream") or path.endswith("/events")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path") or "")

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(raw=message.setdefault("headers", []))
                _apply_security_headers(headers, path)
            await send(message)

        await self.app(scope, receive, send_wrapper)


def _apply_security_headers(headers: MutableHeaders, path: str) -> None:
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("Referrer-Policy", "no-referrer")

    if _is_view_path(path):
        headers.setdefault("Content-Security-Policy", "frame-ancestors 'self'")
        headers.setdefault("Cache-Control", "no-store")
        return

    headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-src 'self'; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self'",
    )
    if path.startswith("/assets/"):
        headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
    elif _is_stream_path(path):
        headers["Cache-Control"] = "no-cache, no-store"
        headers["X-Accel-Buffering"] = "no"
    elif path in ("/", "/index.html") or path.endswith(".html") or path == "":
        headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        headers["Pragma"] = "no-cache"
        headers["Expires"] = "0"


def install_cors(app: ASGIApp, enabled: bool) -> None:
    if not enabled:
        return
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(  # type: ignore[attr-defined]
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
