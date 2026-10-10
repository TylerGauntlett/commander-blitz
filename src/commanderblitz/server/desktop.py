"""The sidecar: this server as the desktop shell starts it.

``python -m commanderblitz.server.desktop`` (or the frozen ``commanderblitz-server``
the AppImage carries) is one process on ``127.0.0.1`` that the Electron shell
spawns on every launch, reads one line from, and talks to over HTTP for the
rest of the session.  The contract with the shell is small and all here:

* **Arguments say where everything is.**  The content package puts the
  data and the built client beside the binary and the per-user generated
  directory somewhere writable; nothing is found by walking up from
  ``__file__``, which lands nowhere inside a frozen build.
* **The socket is bound before READY is printed.**  The shell asks for port
  ``0``, and the port it reads back is already listening -- there is no
  moment where the shell could connect to a port nobody holds.
* **READY comes after the registry is compiled.**  ``create_app`` reads every
  card file; that is the slow part of a launch, and the shell shows a splash
  until the line arrives.  ``stdout`` carries that one line and nothing else,
  so the shell can parse it; uvicorn's own logging goes to ``stderr``.
* **SIGTERM is a clean stop.**  uvicorn installs the handler; the shell sends
  the signal and waits for exit.

``--check`` builds the app and prints what it found, for the packaging smoke
test and for a person wondering why a launch is slow.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
from collections.abc import Callable, Sequence

READY_PREFIX = "READY "


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="commanderblitz-server",
        description="Run the Commander Blitz server as a desktop sidecar.",
    )
    parser.add_argument("--port", type=int, default=0, help="0 picks a free port (default)")
    parser.add_argument("--data-dir", help="the authored cards, decks, catalog and art")
    parser.add_argument("--client-dir", help="the built client to serve at /")
    parser.add_argument("--generated-dir", help="where imports and fetched art are written")
    parser.add_argument("--remote-origin", help="the hosted server, for online play")
    parser.add_argument("--content-version", help="the content package version to report")
    parser.add_argument("--log-level", default="warning")
    parser.add_argument(
        "--check",
        action="store_true",
        help="build the app, print what it loaded as JSON, and exit",
    )
    return parser.parse_args(argv)


#: The variables ``apply_env`` owns.  Listed so a test can hold it to exactly
#: these: ``COMMANDERBLITZ_CPU`` and ``COMMANDERBLITZ_FIXTURE_DECKS`` are test switches that
#: a shipped build must never set.
ENV_VARS = (
    "COMMANDERBLITZ_DATA_DIR",
    "COMMANDERBLITZ_CLIENT_DIR",
    "COMMANDERBLITZ_GENERATED_DIR",
    "COMMANDERBLITZ_MODE",
    "COMMANDERBLITZ_REMOTE_ORIGIN",
    "COMMANDERBLITZ_CONTENT_VERSION",
    "COMMANDERBLITZ_EAGER_ART",
)


def apply_env(args: argparse.Namespace, environ: dict[str, str] | None = None) -> None:
    """Turn the arguments into the environment the package reads.

    Arguments rather than variables at the shell's end because a spawn with
    an argv is visible in a process list and a log, and a variable is not.
    Variables at this end because that is what ``registry.data_dir`` and
    friends already read, and the frozen binary has no other way to reach
    them.
    """
    env = os.environ if environ is None else environ
    env["COMMANDERBLITZ_MODE"] = "desktop"
    env["COMMANDERBLITZ_EAGER_ART"] = "1"
    for flag, name in (
        (args.data_dir, "COMMANDERBLITZ_DATA_DIR"),
        (args.client_dir, "COMMANDERBLITZ_CLIENT_DIR"),
        (args.generated_dir, "COMMANDERBLITZ_GENERATED_DIR"),
        (args.remote_origin, "COMMANDERBLITZ_REMOTE_ORIGIN"),
        (args.content_version, "COMMANDERBLITZ_CONTENT_VERSION"),
    ):
        if flag:
            env[name] = flag
    # A frozen build carries no system certificate store; without this every
    # https fetch -- Moxfield, Scryfall -- fails with a verification error.
    if getattr(sys, "frozen", False) and "SSL_CERT_FILE" not in env:
        try:
            import certifi
        except ImportError:  # pragma: no cover
            pass
        else:
            env["SSL_CERT_FILE"] = certifi.where()


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    apply_env(args)

    # Imported after the environment is set: `settings_from_env` reads it at
    # call time, but the registry module caches `DEFAULT_DATA_DIR` at import.
    import uvicorn

    from commanderblitz.server.app import create_app
    from commanderblitz.server.settings import settings_from_env

    started = time.monotonic()
    app = create_app(serve_client=True, settings=settings_from_env())
    elapsed = time.monotonic() - started

    if args.check:
        sessions = app.state.sessions
        print(
            json.dumps(
                {
                    "cards": len(sessions.data.registry),
                    "decks": len(sessions.data.decks),
                    "catalog": app.state.card_index is not None,
                    "client": any(
                        getattr(r, "path", None) == "/{client_path:path}" for r in app.routes
                    ),
                    "seconds": round(elapsed, 2),
                }
            ),
            flush=True,
        )
        return 0

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", args.port))
    sock.listen(128)
    port = sock.getsockname()[1]
    print(READY_PREFIX + json.dumps({"port": port, "pid": os.getpid()}), flush=True)

    # One worker, as the Docker image insists: sessions live in this process.
    server = uvicorn.Server(uvicorn.Config(app, log_level=args.log_level))
    watch_parent(server)
    server.run(sockets=[sock])
    return 0


#: How often the sidecar checks that the shell is still there.
PARENT_POLL_SECONDS = 2.0


def watch_parent(
    server,
    *,
    getppid: Callable[[], int] = os.getppid,
    interval: float = PARENT_POLL_SECONDS,
) -> threading.Thread:
    """Stop the server when the process that started it is gone.

    Steam's force-close kills the process it launched -- the shell -- and
    nothing else.  The shell's own `before-quit` never runs under SIGKILL, so
    without this the server lived on as an orphan holding its port, and on a
    Deck that was a game Steam showed as still running.  A parent that dies
    reparents this process (to init, or a subreaper), which is the one
    observable fact; polling it costs one syscall every couple of seconds.

    ``server.should_exit`` is uvicorn's own clean stop, the same path SIGTERM
    takes.  Daemon thread, so it never keeps the process alive itself.
    """
    parent = getppid()

    def watch() -> None:
        while not server.should_exit:
            time.sleep(interval)
            if getppid() != parent:
                server.should_exit = True
                return

    thread = threading.Thread(target=watch, name="parent-watch", daemon=True)
    thread.start()
    return thread


if __name__ == "__main__":
    raise SystemExit(main())
