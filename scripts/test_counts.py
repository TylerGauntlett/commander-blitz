"""Keep the suite counts in docs/testing.md true.

    python scripts/test_counts.py            # print the measured counts
    python scripts/test_counts.py --write    # rewrite the table's Count column
    python scripts/test_counts.py --check    # exit 1 if the table is stale

The table in ``docs/testing.md`` was typed by hand and drifted twice in two
audits (TECH_DEBT SD-01: 395 claimed for a suite of 4,581). Counting is cheap
-- pytest and vitest can list without running -- so the table is written from
the tools rather than from memory. ``--check`` is informational in
``scripts/verify.py``: a stale number is a doc bug, not a build break.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DOC = ROOT / "docs" / "testing.md"
PY = sys.executable
DECODE = {"encoding": "utf-8", "errors": "replace"}


def run(command: list[str], cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, shell=False, **DECODE)
    return (result.stdout or "") + (result.stderr or "")


def pytest_count(suite: str) -> int:
    """The suite's collected count -- or exit, never a quiet 0.

    A Python that cannot import ``commanderblitz`` collects nothing and prints errors,
    and reading that as "0 tests" made the table look stale in the wrong way.
    """
    out = run([PY, "-m", "pytest", suite, "--collect-only", "-q", "-o", "addopts="], ROOT)
    match = re.search(r"(\d+) tests? collected", out) or re.search(
        r"(\d+)/\d+ tests collected", out
    )
    errors = re.search(r"(\d+) errors?", out)
    if not match or errors:
        tail = "\n".join(out.strip().splitlines()[-15:])
        raise SystemExit(f"could not count {suite}: collection failed under {PY}\n{tail}")
    return int(match.group(1))


def npx() -> str | None:
    return shutil.which("npx")


def vitest_count(project: str) -> int:
    out = run([npx() or "npx", "vitest", "list", f"--project={project}"], FRONTEND)
    # One line per test: `path > describe > name`. Skip vitest's own chatter.
    return sum(1 for line in out.splitlines() if " > " in line)


def playwright_count(project: str) -> int:
    out = run([npx() or "npx", "playwright", "test", "--list", f"--project={project}"], FRONTEND)
    match = re.search(r"Total: (\d+) tests? in", out)
    return int(match.group(1)) if match else 0


def measured(*, frontend: bool = True) -> dict[str, str]:
    counts = {
        "`tests/unit/`": str(pytest_count("tests/unit")),
        "`tests/cards/`": str(pytest_count("tests/cards")),
        "`tests/ai/`": str(pytest_count("tests/ai")),
        "`tests/server/`": str(pytest_count("tests/server")),
    }
    if frontend and npx() and (FRONTEND / "node_modules").exists():
        counts["`frontend/tests/`"] = str(vitest_count("unit"))
        counts["`frontend/src/**/*.stories.tsx`"] = (
            f"{vitest_count('storybook')} + {vitest_count('storybook-handheld')}"
        )
        counts["`frontend/e2e/`"] = str(
            sum(playwright_count(p) for p in ("chromium", "handheld", "deckfit"))
        )
    return counts


ROW = re.compile(r"^\| (`[^`]+`) \| ([^|]+) \|")


def rewrite(doc: str, counts: dict[str, str]) -> tuple[str, list[tuple[str, str, str]]]:
    """The doc with the Count column updated, and every (suite, was, now) that moved."""
    changed: list[tuple[str, str, str]] = []
    out = []
    for line in doc.splitlines(keepends=True):
        match = ROW.match(line)
        if match and match.group(1) in counts:
            was = match.group(2).strip()
            now = counts[match.group(1)]
            if was != now:
                changed.append((match.group(1), was, now))
                line = line.replace(f"| {was} |", f"| {now} |", 1)
        out.append(line)
    return "".join(out), changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="rewrite the Count column")
    parser.add_argument("--check", action="store_true", help="exit 1 if the table is stale")
    parser.add_argument("--no-frontend", action="store_true")
    args = parser.parse_args()

    counts = measured(frontend=not args.no_frontend)
    doc = DOC.read_text(encoding="utf-8")
    updated, changed = rewrite(doc, counts)
    for suite, value in counts.items():
        print(f"{suite:36s} {value}")
    if args.write:
        DOC.write_text(updated, encoding="utf-8", newline="\n")
        print(f"\nwrote {len(changed)} change(s) to {DOC.relative_to(ROOT)}")
        return 0
    if changed:
        print("\nstale rows in docs/testing.md:")
        for suite, was, now in changed:
            print(f"  {suite}: {was} -> {now}")
        return 1 if args.check else 0
    print("\ndocs/testing.md is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
