"""The "is it done?" gate.

    python scripts/verify.py                # everything
    python scripts/verify.py --quick        # skip the slow simulation stages
    python scripts/verify.py --no-frontend  # Python only

Runs every check in dependency order and stops at the first failure, so the first
thing it prints about a broken build is the thing that broke.
"""

from __future__ import annotations

import argparse
import contextlib
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
    ):
        self.name = name
        self.command = command
        self.cwd = cwd
        self.slow = slow
        self.fn = fn

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
    """Play full games at both pod sizes against a real server."""
    started = time.time()
    port = free_port()
    output: list[str] = []
    try:
        with running_server(port):
            for players in (2, 4):
                result = subprocess.run(
                    [
                        PY,
                        "scripts/smoke_http.py",
                        "--url",
                        f"http://127.0.0.1:{port}",
                        "--players",
                        str(players),
                        "--seed",
                        str(players),
                    ],
                    cwd=ROOT,
                    capture_output=not verbose,
                    text=True,
                )
                if not verbose:
                    output.append((result.stdout or "") + (result.stderr or ""))
                if result.returncode != 0:
                    return False, time.time() - started, "\n".join(output)
    except RuntimeError as exc:
        return False, time.time() - started, str(exc)
    return True, time.time() - started, "\n".join(output)


def python_stages(quick: bool) -> list[Stage]:
    stages = [
        Stage("lint", [PY, "-m", "ruff", "check", "src", "scripts", "tests"]),
        Stage("card files and deck legality", [PY, "scripts/validate_decks.py"]),
        Stage("unit tests", [PY, "-m", "pytest", "tests/unit", "-q"]),
        Stage("every card works", [PY, "-m", "pytest", "tests/cards", "-q"]),
        Stage("HTTP API", [PY, "-m", "pytest", "tests/server", "-q"]),
    ]
    if quick:
        stages.append(
            Stage("AI (fast)", [PY, "-m", "pytest", "tests/ai", "-q", "-m", "not slow"])
        )
    else:
        stages.append(Stage("AI", [PY, "-m", "pytest", "tests/ai", "-q"]))
        stages.append(
            Stage(
                "arena: 120 duels + 40 pods",
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
        Stage("live server: full games at 2p and 4p", fn=run_live_server_stage, slow=True)
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


def frontend_stages(runner: str) -> list[Stage]:
    # Both runners accept `<runner> run <script>`, and the package's test script
    # goes through vitest, so one spelling works for both.
    return [
        Stage("frontend build", [runner, "run", "build"], cwd=FRONTEND),
        Stage("frontend lint", [runner, "run", "lint"], cwd=FRONTEND),
        Stage("frontend tests", [runner, "run", "test"], cwd=FRONTEND),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="skip the slow stages")
    parser.add_argument("--no-frontend", action="store_true")
    parser.add_argument("--verbose", action="store_true", help="stream each stage's output")
    args = parser.parse_args()

    stages = python_stages(args.quick)
    if not args.no_frontend:
        runner = frontend_runner()
        if runner is None:
            print("SKIP frontend: neither bun nor npm is on PATH\n")
        elif not (FRONTEND / "node_modules").exists():
            print("SKIP frontend: run `bun install` (or `npm install`) in frontend/ first\n")
        else:
            stages += frontend_stages(runner)

    print(f"Auto MTG verification - {len(stages)} stages\n")
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
            print(output[-4000:])
        print(f"\nverification failed at: {stage.name}")
        return 1

    print(f"\nAll {len(stages)} stages passed in {total:.1f}s.")
    if args.quick:
        print("(--quick skipped the arena and the training tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
