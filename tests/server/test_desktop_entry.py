"""``automtg.server.desktop``: the contract between the sidecar and the shell.

The shell spawns this, reads one ``READY {...}`` line from stdout, and from
then on talks HTTP.  These tests hold both ends of that: what the arguments
turn into, what ``--check`` prints, and -- once, over a real socket -- that
the process announces a port that is already listening and stops on
``terminate``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from automtg.server import desktop
from automtg.server.desktop import ENV_VARS, READY_PREFIX, apply_env, parse_args

ROOT = Path(__file__).resolve().parents[2]
TEST_ONLY = ("AUTOMTG_CPU", "AUTOMTG_FIXTURE_DECKS")


class TestArguments:
    def test_defaults(self):
        args = parse_args([])
        assert args.port == 0
        assert args.check is False
        assert args.log_level == "warning"
        assert args.data_dir is args.client_dir is args.generated_dir is None

    def test_apply_env_sets_exactly_its_own_variables(self):
        env: dict[str, str] = {}
        apply_env(
            parse_args(
                [
                    "--data-dir", "/content/data",
                    "--client-dir", "/content/client",
                    "--generated-dir", "/home/deck/.local/share/commanderblitz/generated",
                    "--remote-origin", "https://commanderblitz.com",
                    "--content-version", "1.2.3",
                ]
            ),
            env,
        )
        assert env == {
            "AUTOMTG_MODE": "desktop",
            "AUTOMTG_EAGER_ART": "1",
            "AUTOMTG_DATA_DIR": "/content/data",
            "AUTOMTG_CLIENT_DIR": "/content/client",
            "AUTOMTG_GENERATED_DIR": "/home/deck/.local/share/commanderblitz/generated",
            "AUTOMTG_REMOTE_ORIGIN": "https://commanderblitz.com",
            "AUTOMTG_CONTENT_VERSION": "1.2.3",
        }
        assert set(env) <= set(ENV_VARS)

    def test_the_test_switches_are_never_set(self):
        # `AUTOMTG_CPU=classic` is the old AI and `AUTOMTG_FIXTURE_DECKS` puts
        # retired lists in the catalogue.  Both are for the test servers.
        env: dict[str, str] = {}
        apply_env(parse_args([]), env)
        assert not (set(env) & set(TEST_ONLY))
        assert not (set(ENV_VARS) & set(TEST_ONLY))

    def test_an_absent_flag_leaves_the_variable_alone(self):
        env = {"AUTOMTG_DATA_DIR": "/already"}
        apply_env(parse_args([]), env)
        assert env["AUTOMTG_DATA_DIR"] == "/already"

    def test_a_frozen_build_points_ssl_at_its_own_bundle(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        env: dict[str, str] = {}
        apply_env(parse_args([]), env)
        assert Path(env["SSL_CERT_FILE"]).name == "cacert.pem"

    def test_a_frozen_build_respects_an_existing_ssl_setting(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        env = {"SSL_CERT_FILE": "/etc/ssl/mine.pem"}
        apply_env(parse_args([]), env)
        assert env["SSL_CERT_FILE"] == "/etc/ssl/mine.pem"


class TestCheck:
    def test_it_prints_one_json_line_and_exits_zero(self, tmp_path, capsys, monkeypatch):
        for name in TEST_ONLY:
            monkeypatch.delenv(name, raising=False)
        code = desktop.main(["--check", "--generated-dir", str(tmp_path)])
        out, _ = capsys.readouterr()
        assert code == 0
        lines = out.strip().splitlines()
        assert len(lines) == 1, "stdout is the shell's; one line, nothing else"
        report = json.loads(lines[0])
        assert report["cards"] > 3000
        assert report["decks"] >= 12
        assert report["catalog"] is True
        assert isinstance(report["seconds"], float)
        assert isinstance(report["client"], bool)


class TestTheProcess:
    """One real spawn: the shape the shell depends on, end to end."""

    @pytest.fixture
    def server(self, tmp_path):
        env = {k: v for k, v in os.environ.items() if k not in TEST_ONLY}
        process = subprocess.Popen(
            [
                sys.executable, "-m", "automtg.server.desktop",
                "--port", "0",
                "--generated-dir", str(tmp_path / "generated"),
                "--remote-origin", "http://127.0.0.1:1",
                "--content-version", "e2e",
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            ready = None
            deadline = time.time() + 90
            while time.time() < deadline:
                line = process.stdout.readline()
                if not line:
                    assert process.poll() is None, process.stderr.read()[-2000:]
                    continue
                if line.startswith(READY_PREFIX):
                    ready = json.loads(line[len(READY_PREFIX):])
                    break
                pytest.fail(f"unexpected stdout before READY: {line!r}")
            assert ready is not None, "no READY line within 90s"
            yield process, ready
        finally:
            process.terminate()
            process.wait(timeout=10)

    def test_ready_names_a_listening_port_and_the_pid(self, server):
        process, ready = server
        # The pid is the interpreter's own.  On Windows a venv's `python.exe`
        # is a launcher that runs the real interpreter as a child, so it is
        # not `process.pid` there; elsewhere it is.
        assert isinstance(ready["pid"], int) and ready["pid"] > 0
        if sys.platform != "win32":
            assert ready["pid"] == process.pid
        port = ready["port"]
        assert 1024 < port < 65536

        health = json.loads(_get(f"http://127.0.0.1:{port}/health"))
        assert health["status"] == "ok"

        config = json.loads(_get(f"http://127.0.0.1:{port}/api/config"))
        assert config["mode"] == "desktop"
        assert config["online"] is False  # port 1 answers nobody
        assert config["remote_origin"] == "http://127.0.0.1:1"
        assert config["content_version"] == "e2e"

    def test_terminate_stops_it_promptly(self, server):
        process, _ = server
        process.terminate()
        assert process.wait(timeout=10) is not None


def _get(url: str) -> str:
    deadline = time.time() + 30
    while True:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.read().decode("utf-8")
        except OSError:
            if time.time() > deadline:
                raise
            time.sleep(0.2)
