"""CLI entrypoint: lhr serve | doctor."""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import webbrowser
from pathlib import Path

from lhr import __version__
from lhr.config import AppConfig, set_config
from lhr.settings import ensure_data_layout, load_settings, patch_settings


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_serve(args: argparse.Namespace) -> int:
    _setup_logging(args.verbose)
    cfg = AppConfig(
        data_dir=Path(args.data_dir) if args.data_dir else AppConfig().data_dir,
        host=args.host,
        port=args.port,
        open_browser=args.open,
        reload=args.reload,
        dev_cors=args.reload or args.dev_cors,
    )
    set_config(cfg)

    if cfg.host not in ("127.0.0.1", "localhost", "::1"):
        logging.getLogger("lhr").warning(
            "Binding to %s — this exposes local files on the network with no auth. "
            "Prefer 127.0.0.1.",
            cfg.host,
        )

    use_webview = bool(getattr(args, "webview", False))
    if use_webview:
        from lhr.branding import apply_app_user_model_id, close_splash, start_splash

        apply_app_user_model_id()
        start_splash()
    url = f"http://{cfg.host}:{cfg.port}"
    if use_webview:
        from lhr.webview_host import open_webview, port_listening

        if port_listening(cfg.host, cfg.port):
            logging.getLogger("lhr").info("Server already running — opening WebView2 at %s", url)
            try:
                open_webview(url)
            except Exception as exc:
                logging.getLogger("lhr").exception("WebView failed")
                print(exc, file=sys.stderr)
                close_splash()
                return 1
            return 0

    ensure_data_layout()
    patch_settings({"window": {"last_host": cfg.host, "last_port": cfg.port}})
    try:
        from lhr.backup import backup_all_projects

        backup_all_projects(force=False)
    except Exception:
        logging.getLogger("lhr").exception("Startup backup check failed")

    def _backup_loop() -> None:
        import time

        log = logging.getLogger("lhr")
        while True:
            time.sleep(3600)
            try:
                from lhr.backup import backup_all_projects

                backup_all_projects(force=False)
            except Exception:
                log.exception("Scheduled backup failed")

    threading.Thread(target=_backup_loop, name="lhr-backup", daemon=True).start()

    import uvicorn

    from lhr.app import create_app

    app = create_app()
    logging.getLogger("lhr").info("Local HTML Reader v%s — %s", __version__, url)
    logging.getLogger("lhr").info("Data directory: %s", cfg.data_dir)
    try:
        from lhr.text_index import start_background_indexer

        start_background_indexer()
    except Exception:
        logging.getLogger("lhr").exception("Text index did not start")

    if use_webview and cfg.open_browser:
        logging.getLogger("lhr").info("Ignoring --open because --webview was set")

    if use_webview:
        from lhr.webview_host import open_webview, wait_for_port

        config = uvicorn.Config(
            app,
            host=cfg.host,
            port=cfg.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, name="lhr-uvicorn", daemon=True)
        thread.start()
        try:
            from lhr.documents import prewarm_search_workers

            prewarm_search_workers()
        except Exception:
            logging.getLogger("lhr").exception("Search workers did not start")
        if not wait_for_port(cfg.host, cfg.port):
            logging.getLogger("lhr").error("Server did not start on %s", url)
            server.should_exit = True
            close_splash()
            return 1
        try:
            open_webview(url)
        except Exception as exc:
            logging.getLogger("lhr").exception("WebView failed")
            print(exc, file=sys.stderr)
            server.should_exit = True
            thread.join(timeout=5)
            close_splash()
            return 1
        finally:
            close_splash()
            server.should_exit = True
            thread.join(timeout=8)
        return 0

    if cfg.open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    uvicorn.run(
        app,
        host=cfg.host,
        port=cfg.port,
        log_level="info",
        reload=False,
    )
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = AppConfig(data_dir=Path(args.data_dir) if args.data_dir else AppConfig().data_dir)
    set_config(cfg)
    print(f"Local HTML Reader v{__version__}")
    print(f"Data dir: {cfg.data_dir} (exists={cfg.data_dir.exists()})")
    from lhr.projects import current_slug, list_projects

    settings = load_settings()
    print(f"Current project: {current_slug() or '(none)'}")
    for proj in list_projects():
        print(f"  project {proj.get('slug')}: {proj.get('name')}")
        folders = proj.get("folders") or []
        if not folders:
            print("    (no folders)")
        for rec in folders:
            flag = "on" if rec.get("enabled", True) else "off"
            print(f"    - [{flag}] {rec.get('id')}: {rec.get('path')}")
    from lhr.app import frontend_dist

    dist = frontend_dist()
    print(f"Frontend dist: {dist} index={(dist / 'index.html').exists()}")

    try:
        import lhr.cli as _cli  # noqa: F401

        print("Import lhr.cli: OK")
    except Exception as e:
        print(f"Import lhr.cli: FAILED — {e}")
        print("Try: uv sync --reinstall --no-editable")
        print(" Or: set PYTHONPATH to the repo root, then: uv run python -m lhr serve --open")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    import multiprocessing

    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(prog="lhr", description="Local HTML Reader")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Override data directory (or set LHR_DATA_DIR)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="Start local server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8766)
    p_serve.add_argument("--open", action="store_true", help="Open browser")
    p_serve.add_argument(
        "--webview",
        action="store_true",
        help="Open a WebView2 window instead of a browser (Windows Edge engine)",
    )
    p_serve.add_argument("--reload", action="store_true", help="Enable dev CORS (Vite)")
    p_serve.add_argument("--dev-cors", action="store_true")
    p_serve.set_defaults(func=cmd_serve)

    p_doc = sub.add_parser("doctor", help="Diagnose installation")
    p_doc.set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
