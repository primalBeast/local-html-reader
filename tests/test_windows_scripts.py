"""Static checks for the Windows entrypoints. They cannot run cmd.exe on Linux,
so they pin the rules that broke install.cmd on Nov 18 2026."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CMD_FILES = ["install.cmd", "start.cmd", "start-webview.cmd", "scripts/find-uv.cmd"]


def _text(name: str) -> str:
    return (ROOT / name).read_bytes().decode("utf-8")


def _code_lines(name: str) -> list[str]:
    lines = []
    for raw in _text(name).splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("rem ") or line.lower() == "rem" or line.startswith("::"):
            continue
        lines.append(line)
    return lines


def test_gitattributes_forces_crlf_for_batch_files():
    attrs = (ROOT / ".gitattributes").read_text()
    assert "*.cmd text eol=crlf" in attrs
    assert "*.vbs text eol=crlf" in attrs


@pytest.mark.parametrize("name", CMD_FILES)
def test_batch_file_uses_crlf_in_checkout(name):
    data = (ROOT / name).read_bytes()
    assert b"\r\n" in data
    assert data.count(b"\n") == data.count(b"\r\n"), f"{name} has bare LF line endings"


@pytest.mark.parametrize("name", CMD_FILES)
def test_every_called_label_exists(name):
    text = _text(name)
    labels = {m.group(1).lower() for m in re.finditer(r"(?m)^:([A-Za-z_][\w]*)", text)}
    defined = [m.group(1).lower() for m in re.finditer(r"(?m)^:([A-Za-z_][\w]*)", text)]
    assert len(defined) == len(set(defined)), f"{name}: duplicate labels"
    labels.add("eof")
    for m in re.finditer(r"(?i)\b(?:call|goto)\s+:([A-Za-z_]\w*)", "\n".join(_code_lines(name))):
        assert m.group(1).lower() in labels, f"{name}: missing label :{m.group(1)}"


@pytest.mark.parametrize("name", CMD_FILES)
def test_parentheses_balance_outside_quotes(name):
    depth = 0
    for line in _code_lines(name):
        line = re.sub(r"(?i)\becho\(", "echo ", line)  # echo( prints a line; it opens no block
        in_quote = False
        prev = ""
        for ch in line:
            if ch == '"':
                in_quote = not in_quote
            elif not in_quote and prev != "^":
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    assert depth >= 0, f"{name}: stray ) in {line!r}"
            prev = ch
        assert not in_quote, f"{name}: unbalanced quote in {line!r}"
    assert depth == 0, f"{name}: unclosed ( block"


@pytest.mark.parametrize("name", CMD_FILES)
def test_no_where_for_pass_fail(name):
    # `where` fails when PATHEXT or PATH is damaged, even though the file exists.
    for line in _code_lines(name):
        assert not re.search(r"(?i)(^|[\s(&])where(\.exe)?\s", line), f"{name}: uses where: {line!r}"


def test_install_never_needs_powershell_scripts():
    # Group Policy blocked -ExecutionPolicy Bypass, so script modules and .ps1 installers fail.
    code = "\n".join(_code_lines("install.cmd"))
    for banned in ("Expand-Archive", "install.ps1", "| iex", "irm ", "-ExecutionPolicy Bypass"):
        assert banned not in code, banned


def test_install_unpacks_with_tar_then_dotnet():
    code = _text("install.cmd")
    tar = code.index(r'"%SystemRoot%\System32\tar.exe" -xf')
    dotnet = code.index("[IO.Compression.ZipFile]::ExtractToDirectory")
    assert tar < dotnet


def test_install_checks_download_is_a_real_zip():
    code = _text("install.cmd")
    assert "1048576" in code
    assert '"!UV_ZIP_HEAD:~0,2!"=="PK"' in code
    assert "proxy or security software" in code


def test_install_writes_log_and_downloads_into_tools():
    code = _text("install.cmd")
    assert 'set "LOG=%LHR_HERE%install.log"' in code
    assert 'set "TOOLS_UV=%LHR_HERE%.tools\\uv"' in code
    ignore = (ROOT / ".gitignore").read_text().splitlines()
    assert ".tools/" in ignore and "install.log" in ignore


def test_find_uv_search_order():
    text = _text("scripts/find-uv.cmd")
    order = [
        r"\.tools\uv\uv.exe",
        "%%~$PATH:I",
        r"%USERPROFILE%\.local\bin\uv.exe",
        r"%USERPROFILE%\.cargo\bin\uv.exe",
        r"%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe",
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\astral-sh.uv*",
        'call :try_dir "%%~D"',
        r'dir /s /b "%%~fD\uv.exe"',
    ]
    positions = [text.index(item) for item in order]
    assert positions == sorted(positions)
    code = [line.lower() for line in _code_lines("scripts/find-uv.cmd")]
    assert not any(line.startswith("setlocal") for line in code), "find-uv.cmd must hand UV_EXE back"


@pytest.mark.parametrize("name", ["install.cmd", "start.cmd", "start-webview.cmd"])
def test_uv_is_called_by_full_path(name):
    code = _code_lines(name)
    assert any(re.search(r'call "%(~dp0|LHR_HERE%)scripts\\find-uv.cmd"', line) for line in code)
    for line in code:
        if line.startswith("echo") or "call :say" in line:
            continue
        assert not re.match(r"(?i)^uv\s", line), f"{name}: bare uv call: {line!r}"
    assert any('"%UV_EXE%" ' in line for line in code)


@pytest.mark.parametrize("name", ["install.cmd", "start.cmd", "start-webview.cmd"])
def test_pathext_gets_a_default(name):
    assert 'if not defined PATHEXT set "PATHEXT=.COM;.EXE;.BAT;.CMD"' in _text(name)


def test_find_uv_never_rebuilds_path_from_registry():
    # 4974879 added `call set "PATH=%%B;%PATH%"` from reg query; after it `where` missed curl and winget.
    code = "\n".join(_code_lines("scripts/find-uv.cmd") + _code_lines("install.cmd"))
    assert not re.search(r'(?i)set "PATH=[^"]*(USER_PATH|%%B)', code)
    assert not re.search(r'(?i)call set "(LHR_USER_PATH|PATH)=', code)
    assert 'call :try_dir "%%~D"' in code  # each saved folder is checked on its own
