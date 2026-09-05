"""The "is it done?" gate.

    python scripts/verify.py                # everything
    python scripts/verify.py --quick        # skip the slow simulation stages
    python scripts/verify.py --no-frontend  # Python only
    python scripts/verify.py --coverage     # ...and hold the coverage floors
    python scripts/verify.py --e2e          # ...and the three Playwright projects

Runs every check in dependency order and stops at the first failure, so the first
thing it prints about a broken build is the thing that broke.

``--coverage`` and ``--e2e`` are opt-in because each costs tens of minutes: the
default gate is what runs on every push, and ``verify-slow`` in
``.github/workflows/deploy.yml`` runs the two flags on pull requests.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
PY = sys.executable

#: Every stage's output is decoded as UTF-8 with replacement.
#:
#: Without this Python uses the locale codec, which on Windows is cp1252 -- and
#: `biome` prints box-drawing rules and `pytest` prints arrows. A stage that
#: *failed* is exactly the one with output to decode, so the crash replaced the
#: error message with a UnicodeDecodeError traceback: the gate reported a
#: failure and hid what it was.
DECODE = {"encoding": "utf-8", "errors": "replace"}


class Stage:
    """One named check.

    Either a subprocess command, or a callable for stages that need setup (the
    live-server stage has to start and stop uvicorn around itself).
    """

    def __init__(
        self,
        name: str,
        command: list[str] | None = None,
        *,
        cwd: Path = ROOT,
        slow: bool = False,
        fn=None,
        env: dict[str, str] | None = None,
    ):
        self.name = name
        self.command = command
        self.cwd = cwd
        self.slow = slow
        self.fn = fn
        self.env = env

    def run(self, verbose: bool) -> tuple[bool, float, str]:
        if self.fn is not None:
            return self.fn(verbose)
        assert self.command is not None
        started = time.time()
        result = subprocess.run(
            self.command,
            cwd=self.cwd,
            capture_output=not verbose,
            text=True,
            shell=False,
            env={**os.environ, **self.env} if self.env else None,
            **DECODE,
        )
        elapsed = time.time() - started
        output = "" if verbose else (result.stdout or "") + (result.stderr or "")
        return result.returncode == 0, elapsed, output


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@contextlib.contextmanager
def running_server(port: int):
    """Start a real uvicorn process and wait for it to answer.

    ``tests/server`` already covers the API through FastAPI's TestClient; this
    exercises the actual ASGI server over a real socket, which is what the
    browser client talks to.
    """
    process = subprocess.Popen(
        [
            PY,
            "-m",
            "uvicorn",
            "automtg.server.app:get_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        **DECODE,
    )
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"server exited early:\n{process.stdout.read()[-2000:]}")
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2).read()
                break
            except (urllib.error.URLError, OSError):
                time.sleep(0.5)
        else:
            raise RuntimeError("server did not become healthy within 60s")
        yield
    finally:
        process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=10)


def run_live_server_stage(verbose: bool) -> tuple[bool, float, str]:
    """Play full games at both pod sizes against a real server.

    The third run drives the *lobby*: create a pod, join it twice, lock in, deal,
    and play the whole game with each seat acting only through its own token.
    ``TestClient`` covers the same flow, but this is the one that proves it works
    across a real socket with real headers.
    """
    started = time.time()
    port = free_port()
    output: list[str] = []
    runs = [
        ["--players", "2", "--seed", "2"],
        ["--players", "4", "--seed", "4"],
        ["--pod", "--players", "2", "--seed", "5"],
    ]
    try:
        with running_server(port):
            for run in runs:
                result = subprocess.run(
                    [
                        PY,
                        "scripts/smoke_http.py",
                        "--url",
                        f"http://127.0.0.1:{port}",
                        *run,
                    ],
                    cwd=ROOT,
                    capture_output=not verbose,
                    text=True,
                    **DECODE,
                )
                if not verbose:
                    output.append((result.stdout or "") + (result.stderr or ""))
                if result.returncode != 0:
                    return False, time.time() - started, "\n".join(output)
    except RuntimeError as exc:
        return False, time.time() - started, str(exc)
    return True, time.time() - started, "\n".join(output)


#: The Python coverage floor, held by ``--coverage`` over ALL the suites at
#: once. One number, one stage: each suite alone cannot reach it (``tests/ai``
#: on its own covers a fraction of the engine), which is why the four pytest
#: stages append into one data file and a final stage reads it back.
PYTHON_COVERAGE_FLOOR = 92


def python_stages(quick: bool, coverage: bool = False) -> list[Stage]:
    def pytest(suite: str, *extra: str) -> list[str]:
        command = [PY, "-m", "pytest", suite, *extra]
        if coverage:
            # No per-stage report: the summary comes once, from the floor stage.
            command += ["--cov=src/automtg", "--cov-append", "--cov-report="]
        return command

    stages = [
        Stage("lint", [PY, "-m", "ruff", "check", "src", "scripts", "tests"]),
        Stage("card files and deck legality", [PY, "scripts/validate_decks.py"]),
        # Exits 0 with a printed SKIP on any machine without a Scryfall bulk
        # dump, which is every machine but the one that last refreshed it. It
        # only fails when a dump *is* present and the committed index no longer
        # matches it -- which is the case worth catching before a commit.
        Stage("card index is current", [PY, "scripts/build_card_index.py", "--check"]),
    ]
    if coverage:
        stages.append(Stage("coverage: start fresh", [PY, "-m", "coverage", "erase"]))
    stages += [
        Stage("unit tests", pytest("tests/unit")),
        Stage("every card works", pytest("tests/cards")),
        Stage("HTTP API", pytest("tests/server")),
    ]
    if quick:
        stages.append(Stage("AI (fast)", pytest("tests/ai", "-m", "not slow")))
    else:
        stages.append(Stage("AI", pytest("tests/ai")))
    if coverage:
        stages.append(
            Stage(
                f"coverage: src/automtg holds {PYTHON_COVERAGE_FLOOR}%",
                [PY, "-m", "coverage", "report", f"--fail-under={PYTHON_COVERAGE_FLOOR}"],
            )
        )
    if not quick:
        stages.append(
            Stage(
                "arena: 60 duels + 60 four-player pods",
                [
                    PY,
                    "scripts/run_arena.py",
                    "--games",
                    "60",
                    "--pods",
                    "2,4",
                    "--max-draw-rate",
                    "0.25",
                ],
                slow=True,
            )
        )
    stages.append(
        Stage(
            "live server: full games at 2p, 4p and one pod",
            fn=run_live_server_stage,
            slow=True,
        )
    )
    return stages


def frontend_runner() -> str | None:
    """Full path to bun or npm.

    The full path matters on Windows, where npm is ``npm.cmd`` and a bare "npm"
    is not something CreateProcess can find without a shell.
    """
    for name in ("bun", "npm"):
        found = shutil.which(name)
        if found:
            return found
    return None


def chromium_installed() -> bool:
    """Whether ``npx playwright install chromium`` has been run.

    The Storybook stories run in a real browser, which is the whole point of
    them -- jsdom has no layout engine, so it cannot see the cascade this board
    is built out of. But the binary is a large download that ``npm install``
    does not fetch, so a fresh clone has to *skip* that stage rather than fail
    it, exactly as the frontend as a whole is skipped when node_modules is
    missing. Playwright itself is already a dependency for the e2e suite.
    """
    override = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    roots = (
        [Path(override)]
        if override
        else [
            Path.home() / "AppData" / "Local" / "ms-playwright",
            Path.home() / ".cache" / "ms-playwright",
            Path.home() / "Library" / "Caches" / "ms-playwright",
        ]
    )
    return any(root.is_dir() and any(root.glob("chromium-*")) for root in roots)


#: The three Playwright projects, in the order `playwright.config.ts` lists
#: them. Each is its own stage so a failure names the viewport it happened at.
E2E_PROJECTS = ("chromium", "handheld", "deckfit")


def run_e2e_stage(project: str):
    """One Playwright project, with its verdict sorted into the two kinds.

    The suite's verdict was not reproducible: the same unchanged commit produced
    three different *timeout* failures across two runs and no two runs agreed
    on which test, while the two genuine assertion failures reproduced exactly
    (TECH_DEBT FT-06). Telling the two apart took four extra runs by hand. So
    this stage reads Playwright's JSON report and says, per test, which kind of
    failure it was -- a timeout is a budget problem or a busy machine, an
    assertion is a bug -- and the budgets themselves are scaled by `E2E_SLOW`,
    because this stage runs after two Storybook browsers on the same box.
    """

    def run(verbose: bool) -> tuple[bool, float, str]:
        started = time.time()
        report = FRONTEND / "test-results" / f"e2e-{project}.json"
        report.parent.mkdir(exist_ok=True)
        result = subprocess.run(
            ["npx", "playwright", "test", f"--project={project}", "--reporter=list,json"],
            cwd=FRONTEND,
            capture_output=not verbose,
            text=True,
            shell=True,  # npx is npx.cmd on Windows
            env={
                **os.environ,
                "E2E_SLOW": os.environ.get("E2E_SLOW", "2"),
                "PLAYWRIGHT_JSON_OUTPUT_NAME": str(report),
            },
            **DECODE,
        )
        output = "" if verbose else (result.stdout or "") + (result.stderr or "")
        verdict = e2e_verdict(report)
        if verbose:
            # The stage prints its own output as it goes; the sorted verdict
            # is the one thing worth adding, whether or not the stage passed.
            print(readable(verdict), flush=True)
        output += "\n" + verdict
        return result.returncode == 0, time.time() - started, output

    return run


def e2e_verdict(report: Path) -> str:
    """Timeouts and assertions, counted apart, from a Playwright JSON report."""
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "e2e: no JSON report was written"
    kinds: dict[str, list[str]] = {"timedOut": [], "failed": [], "expected-failure": []}
    counts: dict[str, int] = {}

    def walk(suite, path):
        for spec in suite.get("specs", []):
            title = " > ".join([*path, spec["title"]])
            for test in spec.get("tests", []):
                last = (test.get("results") or [{}])[-1]
                status = last.get("status", "unknown")
                counts[status] = counts.get(status, 0) + 1
                if test.get("expectedStatus") == "failed" and status == "failed":
                    kinds["expected-failure"].append(title)
                elif status in kinds:
                    kinds[status].append(title)
        for child in suite.get("suites", []):
            walk(child, [*path, child.get("title", "")])

    for suite in data.get("suites", []):
        walk(suite, [suite.get("title", "")])
    lines = ["e2e: " + ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))]
    if kinds["timedOut"]:
        lines.append("  TIMED OUT (a budget or a busy machine, not an assertion):")
        lines += [f"    {t}" for t in kinds["timedOut"]]
    if kinds["failed"]:
        lines.append("  FAILED an assertion (reproducible; treat as a bug):")
        lines += [f"    {t}" for t in kinds["failed"]]
    if kinds["expected-failure"]:
        lines.append("  failed as expected (`test.fail()`, a known open finding):")
        lines += [f"    {t}" for t in kinds["expected-failure"]]
    return "\n".join(lines)


def frontend_stages(
    runner: str, quick: bool, coverage: bool = False, e2e: bool = False
) -> list[Stage]:
    # Both runners accept `<runner> run <script>`, and the package's test script
    # goes through vitest, so one spelling works for both.
    stages = [
        Stage("frontend build", [runner, "run", "build"], cwd=FRONTEND),
        Stage("frontend lint", [runner, "run", "lint"], cwd=FRONTEND),
    ]
    if coverage and chromium_installed():
        # Every vitest project in ONE process, so the jsdom run and the two
        # Chromium story runs merge into one report and one set of floors. The
        # story stages below are skipped in this mode: this stage IS them. The
        # include list lives in `vite.config.ts`; without it the provider
        # instruments `storybook-static/` beside `src/` and reports 7%.
        stages.append(
            Stage(
                "frontend tests + stories, holding the coverage floors",
                [runner, "run", "test:coverage"],
                cwd=FRONTEND,
                slow=True,
            )
        )
    elif coverage:
        # Without Chromium only the jsdom project can run, and most of the
        # floors in `vite.config.ts` are only reachable with the stories in
        # the same process -- so this measures and reports, and holds nothing.
        stages.append(
            Stage(
                "frontend tests with coverage (jsdom only; floors not held)",
                [runner, "run", "test:coverage", "--", "--project=unit"],
                cwd=FRONTEND,
                env={"COVERAGE_FLOORS": "off"},
            )
        )
    else:
        # jsdom only. The stories are a separate vitest project and a separate
        # stage below, so this one keeps meaning exactly what it always meant.
        stages.append(Stage("frontend tests", [runner, "run", "test"], cwd=FRONTEND))

    # The static build is pure -- it needs no browser -- so it can always run,
    # and it is what catches a story that no longer compiles.
    if not quick:
        stages.append(
            Stage(
                "storybook builds",
                [runner, "run", "build-storybook"],
                cwd=FRONTEND,
                slow=True,
            )
        )

    if coverage and chromium_installed():
        pass  # the coverage stage above already ran every story project
    elif chromium_installed():
        stages.append(
            Stage(
                "storybook stories",
                [runner, "run", "test:stories"],
                cwd=FRONTEND,
                slow=True,
            )
        )
        # The same stories again at a Steam Deck's 1280x800, which is a separate
        # vitest project for the reason `playwright.config.ts` keeps a separate
        # project: the desktop numbers must never move, and they would move the
        # instant that canvas did.
        #
        # THIS IS THE ONLY PLACE THE HANDHELD FLOORS ARE GATED BY CI. Playwright
        # is not run here, so `e2e/handheldAssert.ts` -- which has asserted the
        # 16/44/96 floors since Loop 3 -- has never actually stopped anything
        # landing. It found `.hand__empty` at 14px the first time it ran.
        stages.append(
            Stage(
                "storybook stories (handheld)",
                [runner, "run", "test:stories:handheld"],
                cwd=FRONTEND,
                slow=True,
            )
        )
    else:
        print("SKIP storybook stories: run `npx playwright install chromium` in frontend/\n")

    if e2e and chromium_installed():
        for project in E2E_PROJECTS:
            stages.append(
                Stage(
                    f"playwright: {project}",
                    fn=run_e2e_stage(project),
                    slow=True,
                )
            )
    elif e2e:
        print("SKIP playwright: run `npx playwright install chromium` in frontend/\n")

    return stages


def readable(text: str) -> str:
    """Whatever the console can actually print.

    The decode side is handled by ``DECODE``; this is the *encode* side, and it
    bites for the same reason. Windows attaches a cp1252 stdout, `biome` prints
    box-drawing rules and a U+240D for every carriage return it objects to, and
    `print` raises rather than dropping a glyph -- so the gate reported a failure
    and then crashed instead of saying what it was.
    """
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="skip the slow stages")
    parser.add_argument("--no-frontend", action="store_true")
    parser.add_argument("--verbose", action="store_true", help="stream each stage's output")
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="measure coverage across the suites and fail under the floors",
    )
    parser.add_argument(
        "--e2e",
        action="store_true",
        help="also run the three Playwright projects (needs Chromium; ~40 minutes)",
    )
    args = parser.parse_args()

    stages = python_stages(args.quick, coverage=args.coverage)
    if not args.no_frontend:
        runner = frontend_runner()
        if runner is None:
            print("SKIP frontend: neither bun nor npm is on PATH\n")
        elif not (FRONTEND / "node_modules").exists():
            print("SKIP frontend: run `bun install` (or `npm install`) in frontend/ first\n")
        else:
            stages += frontend_stages(runner, args.quick, coverage=args.coverage, e2e=args.e2e)

    print(f"Commander Blitz verification - {len(stages)} stages\n")
    total = 0.0
    for index, stage in enumerate(stages, start=1):
        label = f"[{index}/{len(stages)}] {stage.name}"
        print(f"{label} ... ", end="", flush=True)
        ok, elapsed, output = stage.run(args.verbose)
        total += elapsed
        if ok:
            print(f"OK ({elapsed:.1f}s)")
            continue
        print(f"FAIL ({elapsed:.1f}s)\n")
        if output:
            print(readable(output[-4000:]))
        print(f"\nverification failed at: {stage.name}")
        return 1

    print(f"\nAll {len(stages)} stages passed in {total:.1f}s.")
    if args.quick:
        print("(--quick skipped the arena and the training tests)")
    else:
        # Informational, never a failing stage: the suite counts in
        # `docs/testing.md` drifted twice between two audits (TECH_DEBT SD-01).
        # A stale number is a documentation bug; this says so and moves on.
        counts = subprocess.run(
            [PY, "scripts/test_counts.py", "--check", "--no-frontend"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            **DECODE,
        )
        verdict = (counts.stdout or "").strip().splitlines()
        print(readable(verdict[-1]) if verdict else "docs/testing.md: count check gave no output")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
