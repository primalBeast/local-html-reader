from pathlib import Path

from lhr.html_text import html_visible_text


def test_strips_tags_scripts_comments_and_head() -> None:
    raw = """
    <html>
      <head><title>TITLETOKEN</title><meta name="x" content="METATOKEN"></head>
      <body>
        <!-- COMMENTTOKEN -->
        <script>SCRIPTTOKEN</script>
        <style>STATETOKEN { color: red }</style>
        <div class="CLASSTOKEN">visible here</div>
      </body>
    </html>
    """
    text = html_visible_text(raw)
    assert "visible here" in text
    for token in ("TITLETOKEN", "METATOKEN", "COMMENTTOKEN", "SCRIPTTOKEN", "STATETOKEN", "CLASSTOKEN"):
        assert token not in text


def test_skips_inert_hidden_nodes() -> None:
    raw = """
    <body>
      shown
      <div hidden>HIDDENTOKEN</div>
      <div aria-hidden="true">ARIATOKEN</div>
      <input type="hidden" value="INPUTTOKEN">
    </body>
    """
    text = html_visible_text(raw)
    assert "shown" in text
    for token in ("HIDDENTOKEN", "ARIATOKEN", "INPUTTOKEN"):
        assert token not in text


def test_includes_css_collapsed_sections(tmp_path: Path) -> None:
    css = tmp_path / "docs.css"
    css.write_text(".height-container { display: none; }", encoding="utf-8")
    html = tmp_path / "page.html"
    html.write_text(
        """
        <html>
          <head><link rel="stylesheet" href="docs.css"></head>
          <body>
            <p>visible token SHOWNTOKEN</p>
            <div class="height-container">COLLAPSEDTOKEN noURLResponse</div>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    text = html_visible_text(html.read_text(encoding="utf-8"), html_path=html, root=tmp_path)
    assert "SHOWNTOKEN" in text
    assert "COLLAPSEDTOKEN" in text
    assert "noURLResponse" in text
