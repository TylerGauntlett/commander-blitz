"""PyInstaller's entry point: the frozen ``commanderblitz-server``.

A file of its own rather than ``-m commanderblitz.server.desktop`` because PyInstaller
freezes a script, not a module, and because it is the one place the frozen
build differs from the checkout: ``sys.frozen`` is set, and ``desktop.apply_env``
reads it to point TLS at the bundled certificate store.
"""

from commanderblitz.server.desktop import main

if __name__ == "__main__":
    raise SystemExit(main())
