#!/usr/bin/env python3
"""Inline the shared masters into all five mockups.

Every earlier round in mockups/ keeps a readable `_*.js` master and inlines it
into each .html by hand, because a mockup has to open standalone from file://
and file:// blocks the fetch a module import would need. Hand-inlining is also
how five copies of one file quietly stop being the same file, so this round does
it with a script instead.

    python inline.py           re-inline both masters into all five
    python inline.py --check   exit 1 if any file is stale, print which

This round inlines TWO masters, which is the one way it departs from the earlier
rounds and is deliberate. Those rounds were five SKINS, so each file owning all
of its CSS was the point. These five are five CONTROL SCHEMES sharing one skin:
if the card face or the type scale differed between them, a difference on screen
would be a difference in styling rather than in how the pad drives it, which is
the only thing this round is trying to measure. So the look is shared and only
the structure is each file's own.

The markers are load-bearing and must stay exactly as written:

    /* <<< BEGIN _handheld.css >>> */  ...  /* <<< END _handheld.css >>> */
    // <<< BEGIN _handheld.js >>>      ...  // <<< END _handheld.js >>>

Stdlib only, no arguments, no network -- same contract as fetch_art.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent

# (master filename, begin marker, end marker). CSS first so a file that somehow
# lost both marker pairs reports the CSS one first, which is the one nearer the
# top of the document and so the easier one to put back.
MASTERS = [
    ("_handheld.css", "/* <<< BEGIN _handheld.css >>> */", "/* <<< END _handheld.css >>> */"),
    ("_handheld.js", "// <<< BEGIN _handheld.js >>>", "// <<< END _handheld.js >>>"),
    # The gates travel WITH the file rather than beside it. `fetch()` is blocked
    # on file:// -- verified, it throws -- so a page cannot load its own checker
    # off disk. Inlining it means opening any of the five and typing
    # `HANDHELD_ASSERT()` in the console works with no server and no paste.
    ("assert.js", "// <<< BEGIN assert.js >>>", "// <<< END assert.js >>>"),
    # 06 only. See splice(): a file without these markers is skipped, not failed.
    ("_table.js", "// <<< BEGIN _table.js >>>", "// <<< END _table.js >>>"),
]


def splice(html: str, payload: str, begin: str, end: str, name: str) -> str:
    i = html.find(begin)
    j = html.find(end)
    # A FILE GETS THE MASTERS IT DECLARES. Absent markers are not an error --
    # `_table.js` is 06's alone, because the other five are each arguing about
    # one control scheme and do not need the whole application's fixtures, and
    # inlining 20KB of pod seats into a file that never draws a pod would make
    # every one of them harder to read for nothing.
    if i < 0 and j < 0:
        return html
    if i < 0 or j < 0:
        raise SystemExit(f"{name}: has one of {begin!r} / {end!r} but not the other")
    if j < i:
        raise SystemExit(f"{name}: END marker precedes BEGIN")
    if html.find(begin, i + 1) >= 0:
        raise SystemExit(f"{name}: {begin!r} appears more than once")
    return html[: i + len(begin)] + "\n" + payload + "\n" + html[j:]


def main() -> int:
    check = "--check" in sys.argv

    payloads = []
    for filename, begin, end in MASTERS:
        path = HERE / filename
        if not path.exists():
            raise SystemExit(f"missing {path}")
        payloads.append((path.read_text(encoding="utf-8").rstrip("\n"), begin, end))

    files = sorted(HERE.glob("*.html"))
    if not files:
        raise SystemExit("no .html files here yet")

    stale: list[str] = []
    for path in files:
        html = original = path.read_text(encoding="utf-8")
        for payload, begin, end in payloads:
            html = splice(html, payload, begin, end, path.name)
        if html == original:
            continue
        stale.append(path.name)
        if not check:
            path.write_text(html, encoding="utf-8")

    if check:
        if stale:
            print("stale, run `python inline.py`: " + ", ".join(stale))
            return 1
        print(f"{len(files)} files up to date with the masters")
        return 0

    print(f"inlined into {len(stale) or 'no'} of {len(files)} files"
          + (": " + ", ".join(stale) if stale else " (all were current)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
