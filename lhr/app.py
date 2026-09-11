"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from lhr import __version__
from lhr.api import documents, roots, settings
from lhr.config import get_config
from lhr.middleware import SecurityHeadersMiddleware, install_cors
from lhr.sync import clear_subscribers, run_poller, set_loop

logger = logging.getLogger("lhr.app")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def frontend_dist() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / "frontend" / "dist",
        here.parent / "static",
    ]
    for c in candidates:
        if (c / "index.html").exists():
            return c
    return candidates[0]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    set_loop(asyncio.get_running_loop())
    task = asyncio.create_task(run_poller())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        clear_subscribers()
        set_loop(None)


def create_app() -> FastAPI:
    cfg = get_config()
    app = FastAPI(
        title="Local HTML Reader",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    install_cors(app, enabled=cfg.dev_cors)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    app.include_router(settings.router)
    app.include_router(roots.router)
    app.include_router(documents.router)

    dist = frontend_dist()
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/side-by-side.html")
    @app.get("/side-by-side")
    def side_by_side():
        path = repo_root() / "side-by-side.html"
        if not path.is_file():
            return JSONResponse({"detail": "side-by-side.html missing"}, status_code=404)
        return FileResponse(path, media_type="text/html; charset=utf-8")

    @app.get("/favicon.ico")
    def favicon():
        fav = dist / "favicon.ico"
        if fav.exists():
            return FileResponse(fav)
        return JSONResponse({"detail": "not found"}, status_code=404)

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str, request: Request):
        if full_path.startswith("api") or full_path.startswith("view"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if full_path in ("side-by-side.html", "side-by-side"):
            dual = repo_root() / "side-by-side.html"
            if dual.is_file():
                return FileResponse(dual, media_type="text/html; charset=utf-8")
        candidate = dist / full_path
        if full_path and candidate.is_file():
            try:
                resolved = candidate.resolve()
                if dist.resolve() == resolved or dist.resolve() in resolved.parents:
                    return FileResponse(candidate)
            except OSError:
                pass
        index = dist / "index.html"
        if not index.exists():
            return HTMLResponse(
                "<!doctype html><html><body style='font-family:system-ui;background:#0f1115;color:#e8eaed;padding:2rem'>"
                "<h1>Local HTML Reader</h1>"
                "<p>Frontend build missing. Run <code>cd frontend && npm ci && npm run build</code> "
                "or restore committed <code>frontend/dist</code>.</p>"
                "<p>API is up — try <a href='/health' style='color:#7dd3fc'>/health</a>.</p>"
                "</body></html>",
                status_code=503,
            )
        return FileResponse(index)

    return app
