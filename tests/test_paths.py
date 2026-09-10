"""Path sandbox: never resolve files outside a documents root."""

from __future__ import annotations

from pathlib import Path

import pytest

from lhr.paths import PathEscapeError, is_within, normalize_rel, resolve_under_root


def test_normalize_rel_posix_and_backslash() -> None:
    assert normalize_rel("a\\b\\c.html") == "a/b/c.html"
    assert normalize_rel("a/b/c.html") == "a/b/c.html"


@pytest.mark.parametrize(
    "rel",
    [
        "..",
        "../secret.html",
        "foo/../../secret.html",
        "..\\secret.html",
        "sub/../../../outside.html",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "\\Windows\\win.ini",
        "",
        ".",
        "foo/\x00bar.html",
    ],
)
def test_normalize_rel_rejects_traversal(rel: str) -> None:
    with pytest.raises(PathEscapeError):
        normalize_rel(rel)


def test_resolve_under_root_allows_nested(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    nested = root / "sub"
    nested.mkdir(parents=True)
    target = nested / "page.html"
    target.write_text("<html>ok</html>", encoding="utf-8")
    got = resolve_under_root(root, "sub/page.html")
    assert got == target.resolve()
    assert is_within(root, got)


def test_resolve_under_root_blocks_sibling(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    outside = tmp_path / "outside.html"
    outside.write_text("nope", encoding="utf-8")
    (root / "ok.html").write_text("ok", encoding="utf-8")
    with pytest.raises(PathEscapeError):
        resolve_under_root(root, "../outside.html")
