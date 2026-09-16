from __future__ import annotations

from lhr.branding import (
    APP_USER_MODEL_ID,
    assets_dir,
    icon_path,
    splash_image_path,
    splash_script_path,
)


def test_branding_assets_exist():
    assert assets_dir().is_dir()
    assert icon_path().is_file()
    assert icon_path().read_bytes()[:4] == b"\x00\x00\x01\x00"
    assert splash_image_path().is_file()
    assert splash_script_path().is_file()
    assert "LocalHtmlReader.SplashClose" in splash_script_path().read_text(encoding="utf-8")
    assert APP_USER_MODEL_ID == "primalBeast.LocalHtmlReader"


def test_cmd_serve_starts_splash_before_server():
    import inspect

    from lhr.cli import cmd_serve

    src = inspect.getsource(cmd_serve)
    assert src.index("start_splash") < src.index("create_app")
    assert src.index("start_splash") < src.index("backup_all_projects")
