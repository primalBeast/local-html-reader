"""Loopback and browser-origin checks.

The server has no accounts. A page on another site must not be able to call it,
and a document opened in the viewer must not be treated as the app itself.
DNS rebinding is rejected by allowing only loopback Host values.
"""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

CLIENT_HEADER = "x-lhr-client"
CLIENT_HEADER_VALUE = "1"
_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_SAFE_FETCH_SITE = frozenset({"", "none", "same-origin", "same-site"})


def hostname_from_host_header(value: str) -> str:
    text = (value or "").strip().strip('"')
    if not text:
        return ""
    if text.startswith("["):
        end = text.find("]")
        name = text[1:end] if end != -1 else text
    elif text.count(":") == 1:
        name = text.rsplit(":", 1)[0]
    else:
        name = text
    return name.lower().rstrip(".")


def _header(headers: Headers, name: str) -> str:
    return (headers.get(name) or "").strip()


def host_allowed(host_header: str, *, peer: str | None) -> bool:
    name = hostname_from_host_header(host_header)
    if not name:
        return False
    if peer == "testclient" and name == "testserver":
        return True
    return name in _LOOPBACK


def origin_allowed(origin: str) -> bool:
    """Empty Origin is fine. A non-empty Origin must be a loopback URL."""
    text = (origin or "").strip()
    if not text or text.lower() == "null":
        return not text
    lowered = text.lower()
    if lowered in {"null"}:
        return False
    for prefix in ("http://127.0.0.1", "http://localhost", "http://[::1]"):
        if lowered == prefix or lowered.startswith(prefix + ":"):
            return True
    return False


def request_allowed(
    *,
    method: str,
    headers: Headers,
    peer: str | None,
) -> str | None:
    """Return an error string, or None when the request may proceed."""
    if not host_allowed(_header(headers, "host"), peer=peer):
        return "host is not loopback"
    fetch_site = _header(headers, "sec-fetch-site").lower()
    if fetch_site and fetch_site not in _SAFE_FETCH_SITE:
        return "cross-site request blocked"
    if not origin_allowed(_header(headers, "origin")):
        return "origin is not loopback"
    if method.upper() in _SAFE_METHODS:
        return None
    if peer == "testclient":
        return None
    if _header(headers, CLIENT_HEADER) != CLIENT_HEADER_VALUE:
        return "missing client header"
    return None


class LocalOnlyMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        peer = None
        client = scope.get("client")
        if isinstance(client, (list, tuple)) and client:
            peer = str(client[0])
        headers = Headers(scope=scope)
        reason = request_allowed(method=str(scope.get("method") or "GET"), headers=headers, peer=peer)
        if reason is None:
            await self.app(scope, receive, send)
            return
        response = JSONResponse({"detail": reason}, status_code=403)
        await response(scope, receive, send)
