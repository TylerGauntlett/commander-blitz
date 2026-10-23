"""``commanderblitz.server.desktop``: the contract between the sidecar and the shell.

The shell spawns this, reads one ``READY {...}`` line from stdout, and from
then on talks HTTP.  These tests hold both ends of that: what the arguments
turn into, what ``--check`` prints, and -- once, over a real socket -- that
the process announces a port that is already listening and stops on
``terminate``.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import pytest

from commanderblitz.cards.registry import DEFAULT_DATA_DIR
from commanderblitz.server import desktop
from commanderblitz.server.desktop import ENV_VARS, READY_PREFIX, apply_env, parse_args

ROOT = Path(__file__).resolve().parents[2]
TEST_ONLY = ("COMMANDERBLITZ_CPU", "COMMANDERBLITZ_FIXTURE_DECKS")


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
            "COMMANDERBLITZ_MODE": "desktop",
            "COMMANDERBLITZ_EAGER_ART": "1",
            "COMMANDERBLITZ_DATA_DIR": "/content/data",
            "COMMANDERBLITZ_CLIENT_DIR": "/content/client",
            "COMMANDERBLITZ_GENERATED_DIR": "/home/deck/.local/share/commanderblitz/generated",
            "COMMANDERBLITZ_REMOTE_ORIGIN": "https://commanderblitz.com",
            "COMMANDERBLITZ_CONTENT_VERSION": "1.2.3",
        }
        assert set(env) <= set(ENV_VARS)

    def test_the_test_switches_are_never_set(self):
        # `COMMANDERBLITZ_CPU=classic` is the old AI and `COMMANDERBLITZ_FIXTURE_DECKS` puts
        # retired lists in the catalogue.  Both are for the test servers.
        env: dict[str, str] = {}
        apply_env(parse_args([]), env)
        assert not (set(env) & set(TEST_ONLY))
        assert not (set(ENV_VARS) & set(TEST_ONLY))

    def test_an_absent_flag_leaves_the_variable_alone(self):
        env = {"COMMANDERBLITZ_DATA_DIR": "/already"}
        apply_env(parse_args([]), env)
        assert env["COMMANDERBLITZ_DATA_DIR"] == "/already"

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


class TestParentWatch:
    """Steam's force-close kills the shell and nothing else; the server has
    to notice on its own."""

    class Server:
        should_exit = False

    def test_a_parent_that_changes_stops_the_server(self):
        server = self.Server()
        pids = iter([100, 100, 100, 1])  # the shell, then reparented to init
        thread = desktop.watch_parent(server, getppid=lambda: next(pids), interval=0.001)
        thread.join(timeout=2)
        assert server.should_exit is True
        assert not thread.is_alive()

    def test_a_parent_that_stays_leaves_it_alone(self):
        server = self.Server()
        thread = desktop.watch_parent(server, getppid=lambda: 100, interval=0.001)
        time.sleep(0.05)
        assert server.should_exit is False
        assert thread.daemon, "must never keep the process alive by itself"
        server.should_exit = True  # the normal stop; the watcher stands down
        thread.join(timeout=2)
        assert not thread.is_alive()


class TestCheck:
    def test_it_prints_one_json_line_and_exits_zero(self, tmp_path, capsys, monkeypatch):
        for name in TEST_ONLY:
            monkeypatch.delenv(name, raising=False)
        # `main` writes its flags into the real `os.environ`; without the patch
        # COMMANDERBLITZ_GENERATED_DIR outlives the test and every later import
        # in the same process writes to this test's tmp_path.
        with mock.patch.dict(os.environ):
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
                sys.executable, "-m", "commanderblitz.server.desktop",
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


class TestAnImportIsCompleteOnTheDevice:
    """ADR 0022, over real sockets: the sidecar imports through a stub site
    with every other host refused, and a deck it could not finish is finished
    on the next launch."""

    DECK_ID = "mox_vvdybwvgc0imbolw63fltg"
    URL = "https://moxfield.com/decks/vVdybWVgC0imBOlW63FlTg"

    @pytest.fixture
    def site(self, tmp_path):
        port = _free_port()
        process = subprocess.Popen(
            [
                sys.executable, "-m", "tests.server.stub_site",
                "--port", str(port), "--generated-dir", str(tmp_path / "site"),
            ],
            cwd=ROOT,
            env={k: v for k, v in os.environ.items() if k not in TEST_ONLY},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        origin = f"http://127.0.0.1:{port}"
        try:
            _get(f"{origin}/__stub/stats", deadline=90)
            yield origin
        finally:
            process.terminate()
            process.wait(timeout=10)

    @pytest.fixture
    def content(self, tmp_path):
        """The Deck's data directory: what the content package carries, which
        is ``data/`` without the art store (ADR 0021) -- so the art a deck
        names has to come from the site, and the site is the stub."""
        root = tmp_path / "content"
        root.mkdir()
        for child in DEFAULT_DATA_DIR.iterdir():
            if child.name in ("art_store", "generated"):
                continue
            try:
                (root / child.name).symlink_to(child, target_is_directory=child.is_dir())
            except OSError:  # pragma: no cover - Windows without symlink rights
                pytest.skip("symlinks are unavailable on this machine")
        return root

    def launch(self, content, generated, origin):
        """The sidecar as the shell starts it, with every host but the stub
        refused through a proxy that answers nobody."""
        env = {k: v for k, v in os.environ.items() if k not in TEST_ONLY}
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            env[name] = "http://127.0.0.1:1"
        env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost"
        process = subprocess.Popen(
            [
                sys.executable, "-m", "commanderblitz.server.desktop",
                "--port", "0",
                "--data-dir", str(content),
                "--generated-dir", str(generated),
                "--remote-origin", origin,
                "--content-version", "e2e",
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
        deadline = time.time() + 120
        while time.time() < deadline:
            line = process.stdout.readline()
            if line.startswith(READY_PREFIX):
                return process, f"http://127.0.0.1:{json.loads(line[len(READY_PREFIX):])['port']}"
            assert process.poll() is None, "the sidecar exited before READY"
        process.kill()
        pytest.fail("no READY line within 120s")

    def test_an_import_lands_whole_and_an_interrupted_one_finishes(
        self, site, content, tmp_path
    ):
        # One Deck imports, and everything it names is on disk.
        generated = tmp_path / "first"
        process, local = self.launch(content, generated, site)
        try:
            body = _post(f"{local}/api/decks/import", {"url": self.URL})
            assert body["deck"]["id"] == self.DECK_ID
            assert body["art_prefetch"]["complete"] is True, body["art_prefetch"]
            assert body["art_prefetch"]["missing"] == []
            decks = {d["id"]: d for d in json.loads(_get(f"{local}/api/decks"))}
            assert decks[self.DECK_ID]["complete"] is True
        finally:
            process.terminate()
            process.wait(timeout=10)
        served = _stats(site)["art"]
        assert served, "the deck's art came from the site"
        # One file per download, named for the card or for the printing.
        assert len(list((generated / "art").glob("*.jpg"))) == len(served)
        deck = json.loads((generated / "decks" / f"{self.DECK_ID}.deck.json").read_text("utf-8"))
        assert deck["complete"] is True

        # A second Deck is stopped halfway through the same import...
        generated = tmp_path / "second"
        half = len(served) // 2
        _post(f"{site}/__stub/state", {"hang_after": len(served) + half})
        process, local = self.launch(content, generated, site)
        caught: list[BaseException] = []
        importing = threading.Thread(
            target=lambda: _swallow(caught, _post, f"{local}/api/decks/import", {"url": self.URL}),
            daemon=True,
        )
        importing.start()
        deadline = time.time() + 120
        while len(_stats(site)["art"]) < len(served) + half:
            assert time.time() < deadline, "the import never reached halfway"
            time.sleep(0.1)
        # Every later request is held at the stub, so the sidecar is quiet once
        # the files it was sent are written; a moment lets the last of those land.
        time.sleep(1.0)
        process.kill()
        process.wait(timeout=10)
        importing.join(timeout=30)
        _post(f"{site}/__stub/state", {"hang_after": None})
        before = _stats(site)["art"][len(served):]
        deck = json.loads((generated / "decks" / f"{self.DECK_ID}.deck.json").read_text("utf-8"))
        assert deck["complete"] is False, "an interrupted import says so in its file"

        # ...and the next launch with a connection finishes it.
        process, local = self.launch(content, generated, site)
        try:
            listed = {d["id"]: d for d in json.loads(_get(f"{local}/api/decks"))}
            assert listed[self.DECK_ID]["complete"] is False
            done = _post(f"{local}/api/decks/complete", None)
            assert done == [
                {"deck_id": self.DECK_ID, "fetched": done[0]["fetched"],
                 "complete": True, "missing": []}
            ]
            assert _post(f"{local}/api/decks/complete", None) == []
        finally:
            process.terminate()
            process.wait(timeout=10)
        after = _stats(site)["art"][len(served) + len(before):]
        assert after, "the relaunch fetched what was missing"
        # Exactly the downloads the uninterrupted Deck made, split across two
        # launches: nothing is fetched twice, and nothing is left out.
        assert len(before) + len(after) == len(served)
        assert sorted(before + after) == sorted(served)
        assert len(list((generated / "art").glob("*.jpg"))) == len(served)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _post(url: str, body: dict | None):
    request = urllib.request.Request(
        url,
        data=json.dumps(body or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        raw = response.read()
    return json.loads(raw) if raw else None


def _stats(origin: str) -> dict:
    return json.loads(_get(f"{origin}/__stub/stats"))


def _swallow(caught: list[BaseException], call, *args) -> None:
    try:
        call(*args)
    except (urllib.error.URLError, OSError) as exc:
        caught.append(exc)


def _get(url: str, *, deadline: float = 30) -> str:
    deadline = time.time() + deadline
    while True:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.read().decode("utf-8")
        except OSError:
            if time.time() > deadline:
                raise
            time.sleep(0.2)
