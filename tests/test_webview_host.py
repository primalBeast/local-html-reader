from __future__ import annotations

import socket

import pytest

import inspect

from lhr.cli import main
from lhr import webview_host
from lhr.webview_host import (
    F5_RELOAD_JS,
    WebviewBridge,
    _hit_from_client_point,
    make_view_menu,
    port_listening,
    scale_window_to_monitor,
    wait_for_port,
)


def test_port_listening_false_on_unused_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    assert port_listening("127.0.0.1", port) is False


def test_wait_for_port_times_out_quickly():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    assert wait_for_port("127.0.0.1", port, timeout=0.2) is False


def test_js_api_does_not_hold_a_window_attribute():
    bridge = WebviewBridge()
    assert not hasattr(bridge, "window")
    assert callable(bridge.minimize)
    assert callable(bridge.close_app)
    assert callable(bridge.toggle_fullscreen)
    assert callable(bridge.toggle_maximize)
    assert callable(bridge.start_resize)
    assert callable(bridge.start_drag)


def test_scale_window_to_monitor_is_three_quarters():
    assert scale_window_to_monitor(1920, 1080) == (1440, 810)
    assert scale_window_to_monitor(1280, 720) == (960, 600)


def test_hit_from_client_point_edges():
    assert _hit_from_client_point(0, 50, 400, 300, 10) == 10
    assert _hit_from_client_point(399, 50, 400, 300, 10) == 11
    assert _hit_from_client_point(50, 0, 400, 300, 10) == 12
    assert _hit_from_client_point(50, 299, 400, 300, 10) == 15
    assert _hit_from_client_point(0, 0, 400, 300, 10) == 13
    assert _hit_from_client_point(200, 150, 400, 300, 10) is None
    assert _hit_from_client_point(50, 3, 400, 300, 8, top_border=4) == 12
    assert _hit_from_client_point(50, 6, 400, 300, 8, top_border=4) is None


def test_view_menu_has_reload():
    called = []
    menu = make_view_menu(lambda: called.append(True))
    assert menu[0].title == "View"
    action = menu[0].items[0]
    assert "Reload" in action.title
    assert "F5" in action.title
    action.function()
    assert called == [True]


def test_toggle_maximize_fills_work_area_not_fullscreen():
    src = inspect.getsource(WebviewBridge.toggle_maximize)
    assert "toggle_fullscreen" not in src
    assert "window.maximize" not in src
    impl = inspect.getsource(webview_host._apply_work_area_maximize)
    assert "WorkingArea" in impl
    assert "toggle_fullscreen" not in impl


def test_f5_script_listens_for_f5():
    assert "F5" in F5_RELOAD_JS
    assert "location.reload" in F5_RELOAD_JS
    assert "F11" in F5_RELOAD_JS
    assert "toggle_fullscreen" in F5_RELOAD_JS


def test_native_zoom_is_disabled():
    src = inspect.getsource(webview_host.open_webview)
    assert "zoomable=False" in src
    host = inspect.getsource(webview_host._disable_native_zoom)
    assert "IsZoomControlEnabled = False" in host
    hook = inspect.getsource(webview_host._hook_native_zoom)
    assert "CoreWebView2InitializationCompleted" in hook
    resize = inspect.getsource(webview_host._enable_edge_resize)
    assert "_hook_native_zoom" in resize


def test_open_webview_uses_app_icon_and_closes_splash():
    src = inspect.getsource(webview_host.open_webview)
    assert "icon_path" in src
    assert 'start_kwargs["icon"]' in src
    assert "close_splash" in src
    create = src.split("webview.create_window(", 1)[1].split(")", 1)[0]
    assert "icon" not in create


def test_serve_help_lists_webview(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as exc:
        main(["serve", "--help"])
    assert exc.value.code == 0
    assert "--webview" in capsys.readouterr().out


# --- black window on the work laptop (Nov 18 2026) ---------------------------

import json as _json
import logging as _logging
import threading as _threading
import time as _time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path as _Path

from lhr import cli as _cli


def _serve(status: int, body: bytes):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    _threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_health_ok_needs_status_ok():
    good = _serve(200, _json.dumps({"status": "ok"}).encode())
    bad = _serve(200, b"<html>not the app</html>")
    missing = _serve(404, b"{}")
    try:
        assert webview_host.health_ok("127.0.0.1", good.server_address[1]) is True
        assert webview_host.health_ok("127.0.0.1", bad.server_address[1]) is False
        assert webview_host.health_ok("127.0.0.1", missing.server_address[1]) is False
    finally:
        for s in (good, bad, missing):
            s.shutdown()


def test_health_ok_ignores_proxy_env(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    good = _serve(200, _json.dumps({"status": "ok"}).encode())
    try:
        assert webview_host.health_ok("127.0.0.1", good.server_address[1]) is True
    finally:
        good.shutdown()


def test_health_ok_against_the_real_app():
    from fastapi.testclient import TestClient

    from lhr.app import create_app

    resp = TestClient(create_app()).get("/health")
    assert resp.status_code == 200 and resp.json()["status"] == "ok"


def test_wait_for_health_times_out_quickly():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    start = _time.monotonic()
    assert webview_host.wait_for_health("127.0.0.1", port, timeout=0.3) is False
    assert _time.monotonic() - start < 3


def test_browser_args_disable_gpu_by_default_and_keep_pywebview_flags():
    args = webview_host.webview2_browser_args({}).split()
    assert "--disable-gpu" in args and "--disable-gpu-compositing" in args
    assert "--disable-features=ElasticOverscroll" in args
    assert "--allow-file-access-from-files" in args


def test_browser_args_gpu_switch_and_user_flags():
    args = webview_host.webview2_browser_args(
        {"LHR_WEBVIEW_GPU": "1", "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": "--foo --disable-gpu"}
    ).split()
    assert args[0] == "--foo"
    assert args.count("--disable-gpu") == 1  # user's own flag kept, not duplicated
    assert "--disable-gpu" not in webview_host.webview2_browser_args({"LHR_WEBVIEW_GPU": "1"})


def test_webview_log_path_defaults_next_to_launcher(tmp_path):
    root = _Path(webview_host.__file__).resolve().parents[1]
    assert webview_host.webview_log_path({}) == root / "webview.log"
    assert (root / "start-webview.cmd").is_file()
    custom = tmp_path / "w.log"
    assert webview_host.webview_log_path({"LHR_WEBVIEW_LOG": str(custom)}) == custom


def test_start_webview_log_writes_lhr_and_uvicorn_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(webview_host, "_log_handler", None)
    path = tmp_path / "webview.log"
    root = _logging.getLogger()
    old_level = root.level
    root.setLevel(_logging.INFO)
    try:
        webview_host.start_webview_log(path)
        _logging.getLogger("lhr.test").info("hello from lhr")
        uv_log = _logging.getLogger("uvicorn")
        old_prop = uv_log.propagate
        uv_log.propagate = False
        webview_host.start_webview_log(path)
        uv_log.info("hello from uvicorn")
        uv_log.propagate = old_prop
        text = path.read_text(encoding="utf-8")
        assert "hello from lhr" in text and "hello from uvicorn" in text
    finally:
        handler = webview_host._log_handler
        for name in ("", "uvicorn", "uvicorn.access", "pywebview"):
            if handler in _logging.getLogger(name).handlers:
                _logging.getLogger(name).removeHandler(handler)
        if handler:
            handler.close()
        root.setLevel(old_level)


def test_load_watchdog_fires_only_without_a_load():
    hits = []
    dog = webview_host.LoadWatchdog(0.05, lambda: hits.append(1))
    dog.start().join(2)
    assert hits == [1] and dog.fired

    hits.clear()
    dog = webview_host.LoadWatchdog(0.2, lambda: hits.append(1))
    t = dog.start()
    dog.mark_loaded()
    t.join(2)
    assert hits == [] and not dog.fired

    dog = webview_host.LoadWatchdog(0.2, lambda: hits.append(1))
    t = dog.start()
    dog.stop()
    t.join(2)
    assert hits == []


def test_timeout_message_points_at_start_cmd_and_log():
    msg = webview_host.load_timeout_message("http://127.0.0.1:8766", _Path("C:/app/webview.log"))
    assert "start.cmd" in msg and "http://127.0.0.1:8766" in msg and "webview.log" in msg
    assert "15 seconds" in msg
    assert "start.cmd" in webview_host.server_failed_message("u", _Path("l"))


def test_open_webview_waits_for_the_page_not_the_window():
    src = inspect.getsource(webview_host.open_webview)
    assert 'background_color="#000000"' not in src
    assert "background_color=WINDOW_BG" in src
    shown = src.split("def on_shown", 1)[1].split("window.events", 1)[0]
    assert "close_splash" not in shown
    loaded = src.split("def on_loaded", 1)[1].split("def on_shown", 1)[0]
    assert "close_splash" in loaded and "watchdog.mark_loaded" in loaded
    assert "window.events.loaded += on_loaded" in src
    assert "watchdog.start()" in src
    assert 'os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"]' in src
    assert "WebView2 (edgechromium) failed" in src
    assert webview_host.LOAD_TIMEOUT_S == 15.0


def test_serve_webview_uses_health_check_and_log():
    src = inspect.getsource(_cli.cmd_serve)
    assert "wait_for_health" in src and "wait_for_port" not in src
    assert "start_webview_log" in src and "show_message" in src


def test_start_webview_cmd_sets_the_log_path():
    text = (_Path(webview_host.__file__).resolve().parents[1] / "start-webview.cmd").read_text()
    assert 'set "LHR_WEBVIEW_LOG=%~dp0webview.log"' in text


def test_app_serves_js_and_css_with_real_types(monkeypatch):
    import mimetypes

    from fastapi.testclient import TestClient

    import lhr.app as app_mod

    # Simulate a PC whose registry maps .js and .css to text/plain, then reload the app module.
    import importlib

    mimetypes.add_type("text/plain", ".js")
    mimetypes.add_type("text/plain", ".css")
    assert mimetypes.guess_type("x.js")[0] == "text/plain"

    importlib.reload(app_mod)
    client = TestClient(app_mod.create_app())
    dist = app_mod.frontend_dist() / "assets"
    js = next(dist.glob("*.js")).name
    assert client.get(f"/assets/{js}").headers["content-type"].startswith("text/javascript")
    css = list(dist.glob("*.css"))
    if css:
        assert client.get(f"/assets/{css[0].name}").headers["content-type"].startswith("text/css")
