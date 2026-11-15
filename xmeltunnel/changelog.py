"""What changed, read by the app itself (the «What's new» window after an update).

The same CHANGELOG.md the GitHub release notes come from is packed into the build: after an update the
user sees what changed without a browser, and without a network if that is what is broken.
Sections are «## <version>»; updates are not taken every version, so «since» gathers all skipped ones.
"""
from __future__ import annotations

import os
import re
import sys

from xmeltunnel import updater

FILENAME = "CHANGELOG.md"
_HEADING = re.compile(r"^##\s+v?(\d\S*)\s*$", re.MULTILINE)


def path() -> str:
    packed = os.path.join(getattr(sys, "_MEIPASS", ""), "assets", FILENAME)
    if getattr(sys, "_MEIPASS", None) and os.path.isfile(packed):
        return packed
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), FILENAME)


def parse(text: str) -> list[tuple[str, str]]:
    """[(version, notes)] in file order."""
    heads = list(_HEADING.finditer(text))
    out = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out.append((h.group(1), text[h.end():end].strip()))
    return out


def _text() -> str:
    try:
        with open(path(), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def section(version: str, text: str | None = None) -> str:
    """Notes of one version ('' if none): the release notes on GitHub come from here too."""
    base = version.split("-", 1)[0]  # a test build (0.3.0-rc.1) is described by its release's section
    entries = dict(parse(_text() if text is None else text))
    return entries.get(version) or entries.get(base) or ""


def since(seen: str, current: str, text: str | None = None) -> list[tuple[str, str]]:
    """Versions after `seen` up to `current`, newest first. seen='' gives the whole history."""
    entries = [(v, n) for v, n in parse(_text() if text is None else text) if n]
    base = current.split("-", 1)[0]
    out = [(v, n) for v, n in entries
           if (v in (current, base) or updater.is_newer(current, v)) and (not seen or updater.is_newer(v, seen))]
    out.sort(key=lambda e: updater.parse_version(e[0]), reverse=True)
    return out


def should_show(seen: str, current: str, first_run: bool) -> bool:
    """Once after an update. A first run has nothing to compare with (and the welcome window matters more);
    an empty mark on a later run means an update from a version that did not keep it yet: show."""
    return seen != current and not first_run
