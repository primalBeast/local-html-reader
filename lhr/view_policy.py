"""Content-Security-Policy for documents opened in the viewer.

Raw files cannot run scripts or talk to the API. Pages this app generates
(Markdown, Word, EPUB, and the other rendered formats) may load https images
but still cannot run scripts or call the API.
"""

from __future__ import annotations

_BASE = (
    "default-src 'none'; "
    "style-src 'unsafe-inline'; "
    "font-src 'self' data:; "
    "media-src 'self' data: blob:; "
    "connect-src 'none'; "
    "object-src 'none'; "
    "frame-src 'none'; "
    "worker-src 'none'; "
    "base-uri 'self'; "
    "form-action 'none'; "
    "frame-ancestors 'self'"
)


def document_csp(*, scripts: bool = False, generated: bool = False) -> str:
    images = "img-src 'self' data: blob:"
    if generated and not scripts:
        images += " https:"
    if scripts:
        # Opt-in only. The iframe is sandboxed off the app origin.
        # Loopback hosts let the file load its own scripts and pictures,
        # not the network, and connect-src stays closed so it cannot call the API.
        script = "script-src 'unsafe-inline' http://127.0.0.1:* http://localhost:* http://[::1]:*"
        images = "img-src 'self' data: blob: http://127.0.0.1:* http://localhost:* http://[::1]:*"
    else:
        script = "script-src 'none'"
    return f"{_BASE}; {script}; {images}"


def view_headers(*, scripts: bool = False, generated: bool = False) -> dict[str, str]:
    headers = {
        "Content-Security-Policy": document_csp(scripts=scripts, generated=generated),
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
    }
    if generated and not scripts:
        headers["X-LHR-Reader-Page"] = "generated"
    return headers
