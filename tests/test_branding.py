from __future__ import annotations

from lhr.branding import (
    APP_USER_MODEL_ID,
    SPLASH_TITLE,
    assets_dir,
    icon_path,
    splash_hta_path,
    splash_image_path,
)


def test_branding_assets_exist():
    assert assets_dir().is_dir()
    assert icon_path().is_file()
    assert icon_path().read_bytes()[:4] == b"\x00\x00\x01\x00"
    assert splash_image_path().is_file()
    hta = splash_hta_path()
    assert hta.is_file()
    text = hta.read_text(encoding="utf-8")
    assert SPLASH_TITLE in text
    assert "splash.png" in text
    assert "lhr-splash.close" in text
    assert APP_USER_MODEL_ID == "primalBeast.LocalHtmlReader"


def test_cmd_serve_starts_splash_before_server():
    import inspect

    from lhr.cli import cmd_serve

    src = inspect.getsource(cmd_serve)
    assert src.index("start_splash") < src.index("create_app")
    assert src.index("start_splash") < src.index("backup_all_projects")
