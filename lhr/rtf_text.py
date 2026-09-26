"""Turn RTF into plain text without a third-party library."""

from __future__ import annotations

_SKIP_DESTINATIONS = frozenset(
    {
        "fonttbl",
        "colortbl",
        "stylesheet",
        "info",
        "pict",
        "object",
        "objdata",
        "datastore",
        "themedata",
        "xmlnstbl",
        "listtable",
        "listoverridetable",
        "rsidtbl",
        "generator",
        "mmathpr",
        "header",
        "headerl",
        "headerr",
        "footer",
        "footerl",
        "footerr",
        "footnote",
        "annotation",
    }
)


def rtf_to_text(data: bytes) -> str:
    """Visible RTF text. Control words, fonts, and pictures are dropped."""
    raw = data.decode("latin-1", errors="replace")
    out: list[str] = []
    i = 0
    n = len(raw)
    depth = 0
    skip_until = 0

    while i < n:
        ch = raw[i]
        if ch == "{":
            depth += 1
            i += 1
            if skip_until:
                continue
            if i < n and raw[i] == "\\":
                dest, after = _destination_at(raw, i + 1)
                if dest in _SKIP_DESTINATIONS or dest == "*":
                    skip_until = depth
                    i = after
            continue
        if ch == "}":
            if skip_until and depth <= skip_until:
                skip_until = 0
            depth = max(0, depth - 1)
            i += 1
            continue
        if skip_until:
            i += 1
            continue
        if ch == "\\":
            i += 1
            if i >= n:
                break
            nxt = raw[i]
            if nxt in "\\{}":
                out.append(nxt)
                i += 1
                continue
            if nxt == "'":
                hexb = raw[i + 1 : i + 3]
                try:
                    out.append(bytes([int(hexb, 16)]).decode("cp1252"))
                except (ValueError, UnicodeDecodeError):
                    pass
                i += 3
                continue
            if nxt == "u":
                i += 1
                sign = 1
                if i < n and raw[i] == "-":
                    sign = -1
                    i += 1
                start = i
                while i < n and raw[i].isdigit():
                    i += 1
                if i > start:
                    code = int(raw[start:i]) * sign
                    if code < 0:
                        code += 65536
                    if 0 <= code <= 0x10FFFF:
                        out.append(chr(code))
                    i = _skip_unicode_fallback(raw, i)
                continue
            if nxt == "*" or nxt in "\r\n":
                i += 1
                continue
            if nxt.isalpha():
                start = i
                while i < n and raw[i].isalpha():
                    i += 1
                word = raw[start:i].lower()
                if i < n and raw[i] == "-":
                    i += 1
                    while i < n and raw[i].isdigit():
                        i += 1
                elif i < n and raw[i].isdigit():
                    num_start = i
                    while i < n and raw[i].isdigit():
                        i += 1
                    if word == "bin":
                        try:
                            skip = int(raw[num_start:i])
                        except ValueError:
                            skip = 0
                        if i < n and raw[i] == " ":
                            i += 1
                        i = min(n, i + max(0, skip))
                        continue
                if i < n and raw[i] == " ":
                    i += 1
                if word in {"par", "line", "page", "sect", "row"}:
                    out.append("\n")
                elif word == "tab":
                    out.append("\t")
                elif word == "emdash":
                    out.append("\u2014")
                elif word == "endash":
                    out.append("\u2013")
                elif word == "bullet":
                    out.append("\u2022")
                elif word in {"lquote", "rquote"}:
                    out.append("\u2019")
                elif word in {"ldblquote", "rdblquote"}:
                    out.append("\u201c" if word == "ldblquote" else "\u201d")
                continue
            i += 1
            continue
        if ch in "\r\n":
            i += 1
            continue
        out.append(ch)
        i += 1
    text = "".join(out)
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    return "\n".join(lines).strip()


def _destination_at(raw: str, i: int) -> tuple[str, int]:
    """Return (destination name, index just after the name). '*' means ignorable."""
    if i < len(raw) and raw[i] == "*":
        return "*", i + 1
    start = i
    while i < len(raw) and raw[i].isalpha():
        i += 1
    return raw[start:i].lower(), i


def _skip_unicode_fallback(raw: str, i: int) -> int:
    """RTF writes one ANSI stand-in after \\uN. Skip it, including a \\'hh pair."""
    if i < len(raw) and raw[i] == " ":
        return i + 1
    if i + 3 < len(raw) and raw[i] == "\\" and raw[i + 1] == "'":
        return i + 4
    if i < len(raw) and raw[i] not in "\\{}":
        return i + 1
    return i
