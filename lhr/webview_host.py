"""Optional WebView2 (Edge) window for the local app. Browser launch is unchanged."""

from __future__ import annotations

import ctypes
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

logger = logging.getLogger("lhr.webview")

# Do not hang a pywebview Window on js_api — JS enumeration of window.native
# (WinForms Form) recurses until it crashes (Empty.Empty… / ModifierKeys.A…).
_active: dict[str, Any] = {"window": None, "url": ""}

F5_RELOAD_JS = """
(function () {
  document.documentElement.setAttribute('data-webview', '1');
  if (window.__lhrReloadBound) return;
  window.__lhrReloadBound = true;
  window.addEventListener('keydown', function (e) {
    if (e.key === 'F5' && !e.ctrlKey && !e.altKey && !e.metaKey) {
      e.preventDefault();
      e.stopPropagation();
      location.reload();
    }
    if (e.key === 'F11' && !e.repeat && !e.ctrlKey && !e.altKey && !e.metaKey) {
      e.preventDefault();
      e.stopPropagation();
      if (window.pywebview && window.pywebview.api && window.pywebview.api.toggle_fullscreen) {
        window.pywebview.api.toggle_fullscreen();
      }
    }
  }, true);
})();
"""


def port_listening(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def wait_for_port(host: str, port: int, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if port_listening(host, port):
            return True
        time.sleep(0.1)
    return False


# Seconds to wait for the first page load before telling the user what to try.
LOAD_TIMEOUT_S = 15.0
# Window colour before the page draws. Not black, so "nothing drew" is not mistaken for a crash.
WINDOW_BG = "#2a2e36"
_WINDOW_BG_RGB = (0x2A, 0x2E, 0x36)
# pywebview passes these itself. WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS replaces them, so keep them.
_PYWEBVIEW_BROWSER_ARGS = ("--disable-features=ElasticOverscroll", "--allow-file-access-from-files")
_LOG_HANDLER_NAME = "lhr-webview-log"
_log_handler: logging.Handler | None = None


def webview_log_path(env: Mapping[str, str] | None = None) -> Path:
    """webview.log next to start-webview.cmd (the repo root), unless LHR_WEBVIEW_LOG is set."""
    env = os.environ if env is None else env
    custom = (env.get("LHR_WEBVIEW_LOG") or "").strip()
    if custom:
        return Path(custom)
    return Path(__file__).resolve().parents[1] / "webview.log"


def _attach_log(name: str) -> None:
    if _log_handler is None:
        return
    lg = logging.getLogger(name)
    if name and lg.propagate:
        return  # the root logger already writes it
    if not any(h.get_name() == _LOG_HANDLER_NAME for h in lg.handlers):
        lg.addHandler(_log_handler)


def start_webview_log(path: Path | None = None) -> Path:
    """Copy lhr, uvicorn and pywebview logs to webview.log. The .vbs launcher hides the console."""
    global _log_handler
    path = path or webview_log_path()
    if _log_handler is None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(path, mode="a", encoding="utf-8")
        except OSError:
            logger.exception("Could not open %s", path)
            return path
        handler.set_name(_LOG_HANDLER_NAME)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        _log_handler = handler
    # uvicorn and pywebview set up their own loggers; call again after they do.
    for name in ("", "uvicorn", "uvicorn.access", "pywebview"):
        _attach_log(name)
    return path


def webview2_browser_args(env: Mapping[str, str] | None = None) -> str:
    """Value for WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS.

    GPU drawing is off unless LHR_WEBVIEW_GPU=1. On managed laptops (EDR, Remote Desktop,
    blocked GPU drivers) WebView2 with the GPU on can show only a black window.
    """
    env = os.environ if env is None else env
    current = (env.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS") or "").split()
    wanted = list(_PYWEBVIEW_BROWSER_ARGS)
    if (env.get("LHR_WEBVIEW_GPU") or "").strip() != "1":
        wanted += ["--disable-gpu", "--disable-gpu-compositing"]
    for flag in wanted:
        if flag not in current:
            current.append(flag)
    return " ".join(current)


def health_ok(host: str, port: int, timeout: float = 1.0) -> bool:
    """True when GET /health answers {"status": "ok"}. A bare open port is not enough."""
    h = f"[{host}]" if ":" in host else host
    # No proxy: a corporate proxy must never see or answer requests for 127.0.0.1.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://{h}:{port}/health", timeout=timeout) as resp:
            if resp.status != 200:
                return False
            data = json.loads(resp.read(4096) or b"{}")
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and data.get("status") == "ok"


def wait_for_health(host: str, port: int, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    tries = 0
    while time.monotonic() < deadline:
        tries += 1
        if health_ok(host, port):
            logger.info("Health check passed on %s:%s after %d tries", host, port, tries)
            return True
        time.sleep(0.2)
    logger.error("Health check failed on %s:%s after %d tries (%.0f s)", host, port, tries, timeout)
    return False


def load_timeout_message(url: str, log_path: Path, seconds: float = LOAD_TIMEOUT_S) -> str:
    return (
        f"The Local HTML Reader window did not finish loading after {int(seconds)} seconds.\n\n"
        f"The app server is at {url}\n\n"
        "Try start.cmd instead. It opens the same app in your web browser.\n\n"
        f"Details are in:\n{log_path}"
    )


def server_failed_message(url: str, log_path: Path) -> str:
    return (
        f"The Local HTML Reader server did not start at {url}\n\n"
        "Run install.cmd again, or try start.cmd.\n\n"
        f"Details are in:\n{log_path}"
    )


def show_message(text: str, title: str = "Local HTML Reader") -> None:
    """Native message box. It works even when WebView2 cannot draw anything."""
    logger.warning("%s", text.replace("\n\n", " ").replace("\n", " "))
    if sys.platform != "win32":
        return
    try:
        # MB_ICONWARNING | MB_SETFOREGROUND | MB_TOPMOST
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x30 | 0x10000 | 0x40000)
    except Exception:
        logger.exception("Could not show a message box")


class LoadWatchdog:
    """Calls on_timeout once if mark_loaded() is not called within timeout seconds."""

    def __init__(self, timeout: float, on_timeout: Callable[[], Any]) -> None:
        self.timeout = timeout
        self.on_timeout = on_timeout
        self._loaded = threading.Event()
        self._stopped = threading.Event()
        self.fired = False

    def mark_loaded(self) -> None:
        self._loaded.set()

    def stop(self) -> None:
        self._stopped.set()
        self._loaded.set()

    def start(self) -> threading.Thread:
        t = threading.Thread(target=self._run, name="lhr-load-watchdog", daemon=True)
        t.start()
        return t

    def _run(self) -> None:
        if self._loaded.wait(self.timeout) or self._stopped.is_set():
            return
        self.fired = True
        try:
            self.on_timeout()
        except Exception:
            logger.exception("Load watchdog callback failed")


def reload_window(window: Any, url: str) -> None:
    """Navigate again so hashed UI assets are picked up (hard refresh)."""
    try:
        window.load_url(url)
        return
    except Exception:
        logger.exception("WebView load_url failed")
    try:
        window.evaluate_js("location.reload()")
    except Exception:
        logger.exception("WebView location.reload failed")


def make_view_menu(on_reload: Callable[[], Any]) -> list[Any]:
    from webview.menu import Menu, MenuAction

    return [Menu("View", [MenuAction("Reload\tF5", on_reload)])]


class WebviewBridge:
    """JS API only. No Window/Form attributes — those crash pywebview's JS bridge."""

    def reload(self) -> None:
        window = _active.get("window")
        url = str(_active.get("url") or "")
        if window is not None:
            reload_window(window, url)

    def toggle_fullscreen(self) -> None:
        now = time.monotonic()
        last = float(_active.get("fs_at") or 0)
        if now - last < 0.45:
            return
        _active["fs_at"] = now
        window = _active.get("window")
        if window is not None:
            window.toggle_fullscreen()

    def minimize(self) -> None:
        window = _active.get("window")
        if window is not None:
            window.minimize()

    def close_app(self) -> None:
        window = _active.get("window")
        if window is not None:
            window.destroy()

    def toggle_maximize(self) -> None:
        window = _active.get("window")
        if window is None:
            return
        try:
            form = window.native
        except Exception:
            logger.exception("toggle_maximize failed")
            return

        def _go() -> None:
            try:
                if _form_is_fullscreen(form):
                    return
                if _active.get("is_maximized"):
                    _apply_restore(form)
                else:
                    _apply_work_area_maximize(form)
            except Exception:
                logger.exception("toggle_maximize failed")

        _run_on_ui(form, _go)

    def start_resize(self, edge: str) -> None:
        """Begin a native Windows resize; must run on the UI thread while the button is down."""
        if _active.get("is_maximized"):
            return
        hit = _resize_hit(str(edge or ""))
        if hit is None:
            return
        _begin_ncl_resize(hit)

    def start_drag(self) -> None:
        """Drag the frameless window (HTCAPTION). Restore first if maximized, like Windows."""
        window = _active.get("window")
        form = getattr(window, "native", None) if window is not None else None

        def _go() -> None:
            if form is not None and _active.get("is_maximized") and not _form_is_fullscreen(form):
                _apply_restore(form)
            _begin_ncl_resize(2)

        if form is not None:
            _run_on_ui(form, _go)
        else:
            _begin_ncl_resize(2)


def _form_is_fullscreen(form: Any) -> bool:
    return bool(getattr(form, "is_fullscreen", False))


def _run_on_ui(form: Any, fn: Callable[[], None]) -> None:
    try:
        from System import Action

        if form.InvokeRequired:
            form.Invoke(Action(fn))
            return
    except Exception:
        pass
    fn()


def _refresh_resize_layout() -> None:
    layout = _active.get("resize_layout")
    if callable(layout):
        try:
            layout()
        except Exception:
            logger.exception("WebView layout after maximize/restore failed")


def _save_restore_bounds(form: Any) -> None:
    try:
        from System.Drawing import Rectangle

        b = form.Bounds
        _active["restore_bounds"] = Rectangle(int(b.X), int(b.Y), int(b.Width), int(b.Height))
    except Exception:
        _active["restore_bounds"] = form.Bounds


def _apply_work_area_maximize(form: Any) -> None:
    """Fill the monitor work area so the taskbar stays visible (not F11 fullscreen).

    pywebview's window.maximize() sets FormWindowState.Maximized. On a frameless
    form that covers the whole monitor, which looks the same as F11 fullscreen.
    """
    from System.Windows.Forms import FormWindowState, Screen

    if _form_is_fullscreen(form):
        return
    if not _active.get("is_maximized"):
        _save_restore_bounds(form)
    if int(form.WindowState) != 0:
        form.WindowState = FormWindowState.Normal
    work = Screen.FromHandle(form.Handle).WorkingArea
    form.Location = work.Location
    form.Size = work.Size
    _active["is_maximized"] = True
    _refresh_resize_layout()


def _apply_restore(form: Any) -> None:
    from System.Windows.Forms import FormWindowState

    if int(form.WindowState) != 0:
        form.WindowState = FormWindowState.Normal
    bounds = _active.get("restore_bounds")
    if bounds is not None:
        try:
            form.Bounds = bounds
        except Exception:
            logger.exception("Could not restore window bounds")
    _active["is_maximized"] = False
    _refresh_resize_layout()


def _resize_hit(edge: str) -> int | None:
    return {
        "left": 10,
        "right": 11,
        "top": 12,
        "top-left": 13,
        "top-right": 14,
        "bottom": 15,
        "bottom-left": 16,
        "bottom-right": 17,
    }.get(edge)


def _begin_ncl_resize(hit: int) -> None:
    window = _active.get("window")
    if window is None:
        return
    try:
        form = window.native
        hwnd = int(form.Handle.ToInt64())
    except Exception:
        return

    def _go() -> None:
        user32 = ctypes.windll.user32
        user32.ReleaseCapture()
        user32.SendMessageW(hwnd, 0x00A1, hit, 0)  # WM_NCLBUTTONDOWN

    try:
        from System import Action

        if form.InvokeRequired:
            form.BeginInvoke(Action(_go))
            return
    except Exception:
        pass
    _go()


def _hit_from_client_point(
    x: int,
    y: int,
    width: int,
    height: int,
    border: int,
    top_border: int | None = None,
    bottom_border: int | None = None,
) -> int | None:
    side = border
    top_b = border if top_border is None else top_border
    bot_b = border if bottom_border is None else bottom_border
    left = x <= side
    right = x >= width - side
    top = y <= top_b
    bottom = y >= height - bot_b
    if top and left:
        return 13
    if top and right:
        return 14
    if bottom and left:
        return 16
    if bottom and right:
        return 17
    if left:
        return 10
    if right:
        return 11
    if top:
        return 12
    if bottom:
        return 15
    return None


def _apply_dark_frame(form: Any, hwnd: int) -> None:
    """Paint resize inset + Win11 DWM caption/border the same dark chrome as the toolbar."""
    try:
        from System.Drawing import Color

        dark = Color.FromArgb(255, 18, 21, 28)  # #12151c
        form.BackColor = dark
    except Exception:
        logger.exception("Could not set form BackColor")
    try:
        dwm = ctypes.windll.dwmapi
        # COLORREF is 0x00BBGGRR for #12151c
        color = ctypes.c_int(0x001C1512)
        dwm.DwmSetWindowAttribute.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_uint,
        ]
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)  # immersive dark
        dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(color), 4)  # border
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), 4)  # caption (top strip)
        dwm.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(ctypes.c_int(2)), 4)  # backdrop
        class _MARGINS(ctypes.Structure):
            _fields_ = [
                ("cxLeftWidth", ctypes.c_int),
                ("cxRightWidth", ctypes.c_int),
                ("cyTopHeight", ctypes.c_int),
                ("cyBottomHeight", ctypes.c_int),
            ]

        # Don't extend a 1px DWM glass caption over the top inset.
        dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(_MARGINS(0, 0, 0, 0)))
    except Exception:
        logger.exception("Could not set dark DWM frame colors")


def _enable_edge_resize(window: Any, border_px: int = 8, top_px: int = 4) -> None:
    """Inset WebView2 and handle Form.MouseDown so edge grabs run on the UI thread."""
    form = getattr(window, "native", None)
    if form is None:
        return
    hwnd = int(form.Handle.ToInt64())
    user32 = ctypes.windll.user32
    user32.GetWindowLongPtrW.restype = ctypes.c_void_p
    user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    style = int(user32.GetWindowLongPtrW(hwnd, -16) or 0)
    user32.SetWindowLongPtrW(hwnd, -16, style | 0x00040000 | 0x00010000)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
    _apply_dark_frame(form, hwnd)

    wv = getattr(form, "webview", None)
    if wv is None:
        browser = getattr(form, "browser", None)
        wv = getattr(browser, "webview", None) if browser is not None else None
    try:
        from System.Drawing import Color as _Color

        if wv is not None and hasattr(wv, "DefaultBackgroundColor"):
            wv.DefaultBackgroundColor = _Color.FromArgb(255, *_WINDOW_BG_RGB)
    except Exception:
        pass

    from System.Windows.Forms import Cursors, DockStyle, MouseButtons

    if wv is not None:
        try:
            wv.Dock = getattr(DockStyle, "None")
        except Exception:
            pass

        def layout(_s: Any = None, _e: Any = None) -> None:
            try:
                maximized = bool(_active.get("is_maximized")) or int(form.WindowState) == 2
                w, h = int(form.ClientSize.Width), int(form.ClientSize.Height)
                if maximized:
                    wv.SetBounds(0, 0, w, h)
                else:
                    wv.SetBounds(
                        border_px,
                        top_px,
                        max(0, w - 2 * border_px),
                        max(0, h - top_px - border_px),
                    )
                _apply_dark_frame(form, hwnd)
            except Exception:
                logger.exception("WebView layout for resize border failed")

        form.Resize += layout
        layout()
        _active["resize_layout"] = layout

    def on_mouse_down(_s: Any, e: Any) -> None:
        try:
            if _active.get("is_maximized") or int(form.WindowState) == 2:
                return
            if e.Button != MouseButtons.Left:
                return
            hit = _hit_from_client_point(
                int(e.X),
                int(e.Y),
                int(form.ClientSize.Width),
                int(form.ClientSize.Height),
                border_px + 2,
                top_border=top_px + 1,
                bottom_border=border_px + 2,
            )
            if hit is None:
                return
            _begin_ncl_resize(hit)
        except Exception:
            logger.exception("Edge resize mouse-down failed")

    def on_mouse_move(_s: Any, e: Any) -> None:
        try:
            if bool(_active.get("is_maximized")) or int(form.WindowState) == 2:
                form.Cursor = Cursors.Default
                return
            hit = _hit_from_client_point(
                int(e.X),
                int(e.Y),
                int(form.ClientSize.Width),
                int(form.ClientSize.Height),
                border_px + 2,
                top_border=top_px + 1,
                bottom_border=border_px + 2,
            )
            cursors = {
                10: Cursors.SizeWE,
                11: Cursors.SizeWE,
                12: Cursors.SizeNS,
                15: Cursors.SizeNS,
                13: Cursors.SizeNWSE,
                17: Cursors.SizeNWSE,
                14: Cursors.SizeNESW,
                16: Cursors.SizeNESW,
            }
            form.Cursor = cursors.get(hit, Cursors.Default)
        except Exception:
            pass

    form.MouseDown += on_mouse_down
    form.MouseMove += on_mouse_move
    _active["resize_mouse"] = on_mouse_down
    _active["resize_move"] = on_mouse_move


def scale_window_to_monitor(
    monitor_w: int, monitor_h: int, fraction: float = 0.75, min_size: tuple[int, int] = (900, 600)
) -> tuple[int, int]:
    return max(min_size[0], int(monitor_w * fraction)), max(min_size[1], int(monitor_h * fraction))


def _startup_window_size() -> tuple[int, int]:
    """Logical pixels: 3/4 of the primary monitor. pywebview applies DPI after this."""
    user32 = ctypes.windll.user32
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass
    try:
        dpi = int(user32.GetDpiForSystem() or 96)
    except Exception:
        dpi = 96
    scale = (dpi / 96.0) if dpi > 0 else 1.0
    cx = int(user32.GetSystemMetrics(0) / scale)
    cy = int(user32.GetSystemMetrics(1) / scale)
    return scale_window_to_monitor(cx, cy)


def open_webview(url: str, title: str = "Local HTML Reader") -> None:
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError(
            "pywebview is not installed. From the repo folder run: uv sync"
        ) from exc

    _attach_log("pywebview")
    log_path = webview_log_path()
    args = webview2_browser_args()
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = args
    logger.info("Opening WebView2 at %s", url)
    logger.info("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=%s", args)
    logger.info("pywebview %s", getattr(webview, "__version__", "?"))

    bridge = WebviewBridge()
    width, height = _startup_window_size()
    from lhr.branding import close_splash, icon_path

    def on_load_timeout() -> None:
        logger.error("Page did not load within %.0f s: %s", LOAD_TIMEOUT_S, url)
        try:
            close_splash()
        except Exception:
            logger.exception("Could not close splash")
        show_message(load_timeout_message(url, log_path))

    watchdog = LoadWatchdog(LOAD_TIMEOUT_S, on_load_timeout)

    ico = icon_path()
    window = webview.create_window(
        title,
        url,
        width=width,
        height=height,
        min_size=(900, 600),
        js_api=bridge,
        background_color=WINDOW_BG,
        frameless=True,
        easy_drag=False,
        shadow=True,
        resizable=True,
    )
    if window is None:
        raise RuntimeError("Could not create the WebView2 window")
    _active["window"] = window
    _active["url"] = url
    _active["is_maximized"] = False
    _active["restore_bounds"] = None

    def on_loaded() -> None:
        watchdog.mark_loaded()
        try:
            logger.info("Page loaded: %s", window.get_current_url())
        except Exception:
            logger.info("Page loaded")
        # Close the splash when the page has drawn, not when the empty window appears.
        try:
            close_splash()
        except Exception:
            logger.exception("Could not close splash")
        try:
            window.evaluate_js(F5_RELOAD_JS)
        except Exception:
            logger.exception("Could not bind F5/F11 in WebView")

    def on_shown() -> None:
        logger.info("Window shown; waiting for the page to load")
        try:
            _enable_edge_resize(window)
        except Exception:
            logger.exception("Could not enable resize frame on the frameless window")

    window.events.loaded += on_loaded
    window.events.shown += on_shown
    start_kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        start_kwargs["gui"] = "edgechromium"
    if ico.is_file():
        start_kwargs["icon"] = str(ico)
    logger.info("Starting pywebview with gui=%s", start_kwargs.get("gui", "default"))
    watchdog.start()
    try:
        webview.start(**start_kwargs)
    except Exception:
        # No retry with the default GUI: that can land on the old IE engine, which cannot
        # run the app's module script and shows the same empty dark window.
        logger.exception("WebView2 (edgechromium) failed")
        raise
    finally:
        watchdog.stop()
        logger.info("WebView window closed")
        try:
            close_splash()
        except Exception:
            pass
        _active["window"] = None
        _active["url"] = ""
        _active["is_maximized"] = False
        _active["restore_bounds"] = None
