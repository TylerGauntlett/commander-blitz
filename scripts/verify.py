"""The "is it done?" gate.

    python scripts/verify.py                # everything
    python scripts/verify.py --quick        # skip the slow simulation stages
    python scripts/verify.py --no-frontend  # Python only
    python scripts/verify.py --coverage     # ...and hold the coverage floors
    python scripts/verify.py --e2e          # ...and the three Playwright projects

Runs every check in dependency order and stops at the first failure, so the first
thing it prints about a broken build is the thing that broke.

``--coverage`` and ``--e2e`` are opt-in because each costs tens of minutes: the
default gate is what runs locally, and CI passes both.

CI runs this same script, one *slice* per runner, which is what the rest of the
flags are for::

    --only lint,pytest   # the stage groups to run; GROUPS lists them
    --jobs 2             # the pytest suites under xdist, N workers
    --e2e-project X      # one Playwright project rather than all four
    --e2e-shard 2/4      # ...and one shard of it
    --strict             # a stage that skips itself FAILS instead

Those exist so nine runners can share the work the sequential list describes,
without any of them being able to quietly assert nothing: ``--strict`` and the
"no stages selected" check are the two guards, and `.github/workflows/deploy.yml`
is the map of which slice runs where.
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
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DESKTOP = ROOT / "desktop"
PY = sys.executable

#: pyproject's `requires-python` floor, read rather than repeated so the two
#: cannot disagree. Only a `>=X.Y` spec is understood, which is the only kind
#: this project has ever had.
REQUIRES_PYTHON = tuple(
    int(part)
    for part in tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "requires-python"
    ]
    .removeprefix(">=")
    .split(".")
)

#: Every stage's output is decoded as UTF-8 with replacement.
#:
#: Without this Python uses the locale codec, which on Windows is cp1252 -- and
#: `biome` prints box-drawing rules and `pytest` prints arrows. A stage that
#: *failed* is exactly the one with output to decode, so the crash replaced the
#: error message with a UnicodeDecodeError traceback: the gate reported a
#: failure and hid what it was.
DECODE = {"encoding": "utf-8", "errors": "replace"}


#: The stage groups `--only` selects from, which is also how CI fans this gate
#: out across runners: one job per group, plus a matrix over the e2e projects.
#: A local run with no `--only` runs all of them, in this order, as it always has.
GROUPS = ("lint", "pytest", "sim", "frontend", "e2e")


class StrictSkip(RuntimeError):
    """A stage skipped itself while ``--strict`` said every stage must run.

    Three stages skip themselves when their tooling is absent -- no npm/bun, no
    ``node_modules``, no Chromium -- and each one leaves the gate exiting *zero*.
    That is right on a fresh clone and wrong on a runner, where a missing browser
    means the job asserted nothing and said so in a line nobody reads. CI passes
    ``--strict``, which turns all three into this.
    """


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
        group: str = "pytest",
    ):
        self.name = name
        self.command = command
        self.cwd = cwd
        self.slow = slow
        self.fn = fn
        self.env = env
        self.group = group

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
            "commanderblitz.server.app:get_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        # The smoke script plays the fixture decks (`data/decks/fixtures/`).
        env={**os.environ, "COMMANDERBLITZ_FIXTURE_DECKS": "1", "COMMANDERBLITZ_CPU": "classic"},
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

#: Suites that must not be handed to xdist even when `--jobs` asks for it.
#:
#: The escape hatch for `tests/server`, which runs genuine ThreadPoolExecutor
#: races against a TestClient and polls with real sleeps: two workers on a
#: two-core runner halve the CPU each race gets. Its deadlines are generous
#: enough that it should hold, so this starts empty -- but if the HTTP API stage
#: starts flaking under `--jobs`, `frozenset({"tests/server"})` is the fix, and
#: at ~134s serial that suite costs almost nothing to serialize.
SERIAL_SUITES: frozenset[str] = frozenset()


def python_stages(quick: bool, coverage: bool = False, jobs: int = 0) -> list[Stage]:
    def pytest(suite: str, *extra: str) -> list[str]:
        command = [PY, "-m", "pytest", suite, *extra]
        if jobs and suite not in SERIAL_SUITES:
            # `loadfile`, not the default `load`: it keeps a file's tests on one
            # worker, so the module-scoped fixtures (the catalog sample in
            # test_proxy_against_the_catalog, `records` in test_card_index) are
            # built once per file rather than once per worker per file. It also
            # preserves any intra-file ordering assumption for free.
            command += ["-n", str(jobs), "--dist", "loadfile"]
        if coverage:
            # No per-stage report: the summary comes once, from the floor stage.
            command += ["--cov=src/commanderblitz", "--cov-append", "--cov-report="]
        return command

    stages = [
        Stage("lint", [PY, "-m", "ruff", "check", "src", "scripts", "tests"], group="lint"),
        Stage(
            "card files and deck legality",
            [PY, "scripts/validate_decks.py"],
            group="lint",
        ),
        # Exits 0 with a printed SKIP on any machine without a Scryfall bulk
        # dump, which is every machine but the one that last refreshed it. It
        # only fails when a dump *is* present and the committed index no longer
        # matches it -- which is the case worth catching before a commit.
        Stage(
            "card index is current",
            [PY, "scripts/build_card_index.py", "--check"],
            group="lint",
        ),
    ]
    if coverage:
        stages.append(Stage("coverage: start fresh", [PY, "-m", "coverage", "erase"]))
    stages += [
        Stage("unit tests", pytest("tests/unit")),
        Stage("every card works", pytest("tests/cards")),
        Stage("HTTP API", pytest("tests/server")),
    ]
    # Every precon through whole games is simulation, and runs with the sim
    # group below: the Python job's time budget is the tight one.
    deck_games = "tests/ai/strategy/test_deck_games.py"
    if quick:
        stages.append(Stage("AI (fast)", pytest("tests/ai", "-m", "not slow")))
    else:
        stages.append(Stage("AI", pytest("tests/ai", f"--ignore={deck_games}")))
    if coverage:
        stages.append(
            Stage(
                f"coverage: src/commanderblitz holds {PYTHON_COVERAGE_FLOOR}%",
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
                    # The pre-strategy agent: this is a rules canary, and the
                    # deck plans make the same 120 games ~4x slower to play.
                    "--agents",
                    "heuristic_classic,random",
                    "--games",
                    "60",
                    "--pods",
                    "2,4",
                    "--max-draw-rate",
                    "0.25",
                ],
                slow=True,
                group="sim",
            )
        )
        stages.append(
            Stage(
                "every precon, piloted by its own strategy",
                [PY, "-m", "pytest", deck_games, "-q", "-p", "no:cacheprovider"],
                slow=True,
                group="sim",
            )
        )
    stages.append(
        Stage(
            "live server: full games at 2p, 4p and one pod",
            fn=run_live_server_stage,
            slow=True,
            group="sim",
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


#: The Playwright projects, in the order `playwright.config.ts` lists them, then
#: `sidecar` from its own config. Each is its own stage so a failure names the
#: viewport -- or the server -- it happened at.
E2E_PROJECTS = ("chromium", "handheld", "deckfit", "sidecar")

#: The desktop build's project lives in a second config: it needs a different
#: server (the sidecar serving `dist/`, no Vite), and `webServer` is per config.
#: It also needs `dist/` to exist, which the other three never do.
SIDECAR_CONFIG = "playwright.sidecar.config.ts"


def run_e2e_stage(project: str, shard: str | None = None):
    """One Playwright project, with its verdict sorted into the two kinds.

    The suite's verdict was not reproducible: the same unchanged commit produced
    three different *timeout* failures across two runs and no two runs agreed
    on which test, while the two genuine assertion failures reproduced exactly
    (TECH_DEBT FT-06). Telling the two apart took four extra runs by hand. So
    this stage reads Playwright's JSON report and says, per test, which kind of
    failure it was -- a timeout is a budget problem or a busy machine, an
    assertion is a bug -- and the budgets themselves are scaled by `E2E_SLOW`,
    because this stage runs after two Storybook browsers on the same box.

    ``shard`` is Playwright's ``i/n``, which CI uses to spread one project over
    several runners. Sharding is the only parallelism this suite can take:
    `playwright.config.ts` keeps ``workers`` at 1 because the app's motion is
    frame-driven and the runner already draws ~11 fps under tracing, so a second
    worker on the same box produces timeouts rather than speed. A second *box*
    costs nothing, because `--shard` partitions the test list before the run.
    """

    def run(verbose: bool) -> tuple[bool, float, str]:
        started = time.time()
        # "2/4" is not a filename -- and a shard's report must not land on a
        # sibling shard's, or the vacuous-pass check below reads the wrong run.
        suffix = f"-{shard.replace('/', 'of')}" if shard else ""
        report = FRONTEND / "test-results" / f"e2e-{project}{suffix}.json"
        report.parent.mkdir(exist_ok=True)
        # A stale report from an earlier run would otherwise be read as this
        # run's verdict, and the "no report" check below would never fire.
        report.unlink(missing_ok=True)
        # `shutil.which`, and NOT `shell=True` with a list. On Windows a bare
        # "npx" is `npx.cmd`, which CreateProcess cannot find without a shell;
        # but on POSIX `shell=True` hands a *list* to `sh -c`, which runs only
        # its first element -- `npx` alone -- and the rest become `$0`, `$1`...
        # That printed npx's usage, exited zero in 0.3 s, and passed all three
        # Playwright stages on every CI run before this comment was written.
        npx = shutil.which("npx")
        if npx is None:
            return False, time.time() - started, "e2e: npx is not on PATH"
        command = [npx, "playwright", "test", f"--project={project}", "--reporter=list,json"]
        if project == "sidecar":
            # The sidecar serves the built client, so build it first. `npm run
            # build` is `tsc --noEmit && vite build`; a type error fails here,
            # which is right -- the shell would ship it otherwise.
            runner = frontend_runner()
            if runner is None:
                return False, time.time() - started, "e2e: no npm or bun on PATH"
            built = subprocess.run(
                [runner, "run", "build"],
                cwd=FRONTEND,
                capture_output=not verbose,
                text=True,
                shell=False,
                **DECODE,
            )
            if built.returncode != 0:
                output = "" if verbose else (built.stdout or "") + (built.stderr or "")
                return False, time.time() - started, "e2e: the client build failed\n" + output
            command.insert(3, f"--config={SIDECAR_CONFIG}")
        if shard:
            command.append(f"--shard={shard}")
        result = subprocess.run(
            command,
            cwd=FRONTEND,
            capture_output=not verbose,
            text=True,
            shell=False,
            env={
                **os.environ,
                "E2E_SLOW": os.environ.get("E2E_SLOW", "2"),
                "PLAYWRIGHT_JSON_OUTPUT_NAME": str(report),
                # `playwright.config.ts` boots uvicorn with this interpreter,
                # so the suite runs against the same environment as the gate
                # -- CI has no `.venv`, and that path was all the config knew.
                "PYTHON": PY,
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
        # No report means no tests ran, whatever the exit code says. A stage
        # that asserts nothing must not pass. The count is the same check one
        # level down, and it is sharding that makes it worth having: `--shard=5/4`
        # or a `testMatch` that stopped matching writes a perfectly valid report
        # describing zero tests, and exits 0.
        ok = result.returncode == 0 and report.is_file() and sum(e2e_counts(report).values()) > 0
        return ok, time.time() - started, output

    return run


def e2e_results(report: Path) -> tuple[dict[str, int], dict[str, list[str]]] | None:
    """One walk of a Playwright JSON report: per-status counts, and the titles.

    ``None`` when there is no readable report at all, which the two callers
    report differently -- a missing report is a *failed* stage, not an empty one.
    """
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
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
    return counts, kinds


def e2e_counts(report: Path) -> dict[str, int]:
    """How many tests ended in each status. Empty when there is no report."""
    results = e2e_results(report)
    return results[0] if results else {}


def e2e_verdict(report: Path) -> str:
    """Timeouts and assertions, counted apart, from a Playwright JSON report."""
    results = e2e_results(report)
    if results is None:
        return "e2e: no JSON report was written"
    counts, kinds = results
    if not counts:
        return "e2e: the report is empty -- no test ran"
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
    runner: str,
    quick: bool,
    coverage: bool = False,
    e2e: bool = False,
    projects: tuple[str, ...] = E2E_PROJECTS,
    shard: str | None = None,
    strict: bool = False,
    want: frozenset[str] = frozenset(GROUPS),
) -> list[Stage]:
    """The frontend half of the gate.

    ``want`` is the set of groups the caller will actually keep, and it is what
    ``strict`` is measured against: a runner slicing off ``--only e2e`` has no
    Storybook stage to miss, so a missing browser must fail it for *Playwright*
    or not at all. Naming the wrong reason is how a strict mode stops being read.
    """
    # Both runners accept `<runner> run <script>`, and the package's test script
    # goes through vitest, so one spelling works for both.
    stages = [
        Stage("frontend build", [runner, "run", "build"], cwd=FRONTEND, group="frontend"),
        Stage("frontend lint", [runner, "run", "lint"], cwd=FRONTEND, group="frontend"),
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
                group="frontend",
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
                group="frontend",
            )
        )
    else:
        # jsdom only. The stories are a separate vitest project and a separate
        # stage below, so this one keeps meaning exactly what it always meant.
        stages.append(
            Stage("frontend tests", [runner, "run", "test"], cwd=FRONTEND, group="frontend")
        )

    # The desktop shell's own package: its lint, its type-check and its unit
    # tests, which run under Node with no Electron and no browser. Skipped
    # like the frontend is when nothing has installed it, which on a runner
    # `--strict` turns into a failure.
    if (DESKTOP / "node_modules").is_dir():
        stages.append(
            Stage("desktop lint", [runner, "run", "lint"], cwd=DESKTOP, group="frontend")
        )
        stages.append(
            Stage("desktop build", [runner, "run", "build"], cwd=DESKTOP, group="frontend")
        )
        stages.append(
            Stage("desktop tests", [runner, "run", "test"], cwd=DESKTOP, group="frontend")
        )
    elif strict and "frontend" in want:
        raise StrictSkip("the desktop package is not installed: npm ci in desktop/")
    else:
        print("SKIP desktop: run `npm ci` in desktop/\n")

    # The static build is pure -- it needs no browser -- so it can always run,
    # and it is what catches a story that no longer compiles.
    if not quick:
        stages.append(
            Stage(
                "storybook builds",
                [runner, "run", "build-storybook"],
                cwd=FRONTEND,
                slow=True,
                group="frontend",
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
                group="frontend",
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
                group="frontend",
            )
        )
    elif strict and "frontend" in want:
        raise StrictSkip("storybook stories need Chromium: npx playwright install chromium")
    else:
        print("SKIP storybook stories: run `npx playwright install chromium` in frontend/\n")

    if e2e and chromium_installed():
        for project in projects:
            stages.append(
                Stage(
                    # The shard is part of the name so a red CI leg says which
                    # slice it was, and so a developer can re-run just that one.
                    f"playwright: {project}" + (f" (shard {shard})" if shard else ""),
                    fn=run_e2e_stage(project, shard),
                    slow=True,
                    group="e2e",
                )
            )
    elif e2e and strict and "e2e" in want:
        raise StrictSkip("playwright needs Chromium: npx playwright install chromium")
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
    # Raw, so the usage block in the module docstring survives `--help` as the
    # two columns it was written as rather than one reflowed paragraph.
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
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
    parser.add_argument(
        "--only",
        default="",
        metavar="GROUPS",
        help="comma-separated stage groups to run: " + ",".join(GROUPS) + " "
        "(CI fans these out across runners; the default is all of them)",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=0,
        metavar="N",
        help="run the pytest suites under xdist with N workers (default: serial)",
    )
    parser.add_argument(
        "--e2e-project",
        action="append",
        choices=E2E_PROJECTS,
        dest="e2e_projects",
        help="limit --e2e to one Playwright project (repeatable)",
    )
    parser.add_argument(
        "--e2e-shard",
        metavar="I/N",
        help="Playwright --shard for this run; the JSON report is named per shard",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="every SKIP is a failure -- what CI passes, so a runner missing a "
        "browser fails the job instead of passing it vacuously",
    )
    args = parser.parse_args()

    # The gate's verdict is only worth having on the Python CI tests. A 3.11
    # venv passed this script for weeks while pyproject required 3.13 (TECH_DEBT
    # HY-04), and a pass on the wrong interpreter is a pass of something else.
    if sys.version_info < REQUIRES_PYTHON:
        need = ".".join(map(str, REQUIRES_PYTHON))
        print(
            f"verify.py needs Python >= {need} (pyproject's requires-python); "
            f"this is {sys.version.split()[0]} at {PY}. Rebuild the venv: "
            f'py -{need} -m venv .venv && .venv/Scripts/python -m pip install '
            f'-c constraints.txt -e ".[dev]"',
            file=sys.stderr,
        )
        return 2

    want = set(args.only.split(",")) if args.only else set(GROUPS)
    unknown = want - set(GROUPS)
    if unknown:
        # Not a warning. A typo'd group would otherwise silently run nothing,
        # which is the failure mode this whole flag exists to make impossible.
        parser.error(f"unknown stage group(s): {', '.join(sorted(unknown))}")
    # Asking for an e2e slice is asking for e2e; nobody should have to pass both.
    if args.e2e_shard or args.e2e_projects or (args.only and "e2e" in want):
        args.e2e = True

    if args.coverage and sys.version_info >= (3, 12):
        # sys.monitoring rather than the C trace function: the cards suite went
        # 222s -> 933s under the old tracer on a runner. `setdefault`, so
        # COVERAGE_CORE=ctrace still works for anyone bisecting a difference.
        # Set here rather than in the workflow, so a developer running
        # `--coverage` gets the same saving and CI stays this script.
        os.environ.setdefault("COVERAGE_CORE", "sysmon")

    stages = [
        stage
        for stage in python_stages(args.quick, coverage=args.coverage, jobs=args.jobs)
        if stage.group in want
    ]
    # Only when something wanted needs it: the `sim` job has no node_modules and
    # no business probing for them.
    if not args.no_frontend and want & {"frontend", "e2e"}:
        runner = frontend_runner()
        try:
            if runner is None:
                raise StrictSkip("neither bun nor npm is on PATH")
            if not (FRONTEND / "node_modules").exists():
                raise StrictSkip("run `bun install` (or `npm install`) in frontend/ first")
            stages += [
                stage
                for stage in frontend_stages(
                    runner,
                    args.quick,
                    coverage=args.coverage,
                    e2e=args.e2e,
                    projects=tuple(args.e2e_projects or E2E_PROJECTS),
                    shard=args.e2e_shard,
                    strict=args.strict,
                    want=frozenset(want),
                )
                if stage.group in want
            ]
        except StrictSkip as skip:
            if args.strict:
                print(f"STRICT: {skip}")
                return 1
            print(f"SKIP frontend: {skip}\n")

    if not stages:
        # The point of the whole exercise. `--only e2e` on a runner with no
        # Chromium used to print a SKIP and exit zero, having asserted nothing --
        # and one silent job in a fan-out of nine is exactly what nobody notices.
        print("no stages selected -- nothing was verified")
        return 1

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
    elif args.only:
        print(f"(--only {args.only}: this was one slice of the gate, not all of it)")
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
