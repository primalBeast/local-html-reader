"""Windows OneDrive data-dir resolution and AppData migration."""

from __future__ import annotations

from pathlib import Path

import pytest

from lhr import config


def test_onedrive_root_prefers_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    od = tmp_path / "OneDrive"
    od.mkdir()
    monkeypatch.setenv("OneDrive", str(od))
    monkeypatch.delenv("OneDriveConsumer", raising=False)
    monkeypatch.delenv("OneDriveCommercial", raising=False)
    assert config.onedrive_root() == od


def test_default_windows_dir_is_onedrive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    od = tmp_path / "OneDrive"
    od.mkdir()
    monkeypatch.setenv("OneDrive", str(od))
    monkeypatch.delenv("LHR_DATA_DIR", raising=False)
    monkeypatch.setattr(config.platform, "system", lambda: "Windows")
    got = config.default_data_dir()
    assert got == od / "Local HTML Reader"


def test_lhr_data_dir_still_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custom = tmp_path / "custom"
    custom.mkdir()
    monkeypatch.setenv("LHR_DATA_DIR", str(custom))
    monkeypatch.setattr(config.platform, "system", lambda: "Windows")
    assert config.default_data_dir() == custom.resolve()


def test_migrate_copies_then_removes_legacy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    appdata = tmp_path / "AppData"
    onedrive = tmp_path / "OneDrive"
    appdata.mkdir()
    onedrive.mkdir()
    legacy = appdata / "LocalHtmlReader"
    dest = onedrive / "Local HTML Reader"
    legacy.mkdir(parents=True)
    (legacy / "settings.json").write_text('{"roots":[]}', encoding="utf-8")
    (legacy / ".data.lock").write_text("old", encoding="utf-8")

    monkeypatch.setenv("APPDATA", str(appdata))
    config.migrate_windows_appdata_to_onedrive(dest)

    assert (dest / "settings.json").read_text(encoding="utf-8") == '{"roots":[]}'
    assert not (dest / ".data.lock").exists()
    assert not legacy.exists()


def test_migrate_skips_when_dest_already_has_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    appdata = tmp_path / "AppData"
    dest = tmp_path / "OneDrive" / "Local HTML Reader"
    dest.mkdir(parents=True)
    (dest / "settings.json").write_text('{"roots":[{"id":"keep"}]}', encoding="utf-8")
    legacy = appdata / "LocalHtmlReader"
    legacy.mkdir(parents=True)
    (legacy / "settings.json").write_text('{"roots":[]}', encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(appdata))

    config.migrate_windows_appdata_to_onedrive(dest)

    assert (dest / "settings.json").read_text(encoding="utf-8") == '{"roots":[{"id":"keep"}]}'
    assert (legacy / "settings.json").is_file()


def test_fallback_appdata_when_no_onedrive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    appdata = tmp_path / "Roaming"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.delenv("LHR_DATA_DIR", raising=False)
    monkeypatch.delenv("OneDrive", raising=False)
    monkeypatch.delenv("OneDriveConsumer", raising=False)
    monkeypatch.delenv("OneDriveCommercial", raising=False)
    monkeypatch.setattr(config.platform, "system", lambda: "Windows")
    monkeypatch.setattr(config, "onedrive_root", lambda: None)
    assert config.default_data_dir() == appdata / "LocalHtmlReader"
