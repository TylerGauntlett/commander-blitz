# The desktop shell

An Electron window around the game's own server, built for a Steam Deck. The
player-facing page is [docs/steamdeck.md](../docs/steamdeck.md); the reasons are
[ADR 0009](../docs/adr/0009-offline-first-desktop.md); releasing is in
[docs/deployment.md](../docs/deployment.md#desktop-releases). This page is how
to work on it.

## What is where

| | |
|---|---|
| `src/sidecar.ts` | starts `commanderblitz-server`, waits for its `READY` line and `/health`, stops it (SIGTERM, then SIGKILL) |
| `src/content.ts` | content packages on disk: `content/<version>/`, `state.json`, install/activate/rollback/prune |
| `src/updater.ts` | reads `content-latest.json`, downloads and installs a newer package |
| `src/orchestrator.ts` | `restartInPlace`: stop, swap, start, wait, reload — or roll back. **Never restarts Electron** |
| `src/connectivity.ts` | probes the hosted site every half-minute, announces changes |
| `src/main.ts`, `src/preload.ts`, `src/shellUpdater.ts` | the Electron wiring, thin |
| `../frontend/src/desktop/bridge.ts` | `window.commanderblitz`: the contract the preload implements and the client compiles against |
| `sidecar/` | PyInstaller spec, `build.sh` (in a container, for glibc) and `smoke.sh` for the frozen server |
| `scripts/assemble-content.mjs` | puts `build/content/{manifest.json, server, client, data}` together, optionally as a tarball |
| `steam/` | `install.sh`, the launcher, the library artwork, and the installer's test |

Everything under `src/` that decides something takes its process, filesystem
and network calls as options; `test/` hands it fakes and runs under plain Node.
`npm test` needs no Electron, no Python and no browser.

## Running it on a checkout

```bash
cd desktop && npm ci
npm run dev            # type-check, bundle, write dev-content/, launch Electron
```

With no content package on disk the shell needs to be told where the pieces
are. Set these first (the repo's venv has the package installed):

| variable | what |
|---|---|
| `COMMANDERBLITZ_SIDECAR_PYTHON` | the interpreter to run `-m commanderblitz.server.desktop` with (`../.venv/Scripts/python.exe` on Windows) |
| `COMMANDERBLITZ_DATA_DIR` | `../data` |
| `COMMANDERBLITZ_CLIENT_DIR` | `../frontend/dist` (`npm run build` in `frontend/` first) |
| `COMMANDERBLITZ_HOME` | somewhere scratch, so nothing lands in your real per-user directory |
| `COMMANDERBLITZ_REMOTE` | another hosted origin, if not `https://commanderblitz.com` |
| `COMMANDERBLITZ_RELEASES` | another release feed, e.g. a local `http.server` with a `content-latest.json` in it, to try an update |

`npm run smoke` (`electron . --smoke`) does everything but open a window: boot
the sidecar, read `/api/config`, print it, exit. It is what the release workflow
runs against the packaged AppImage, under xvfb.

> **If Electron runs as plain Node** (`app.getVersion is not a function`): the
> environment has `ELECTRON_RUN_AS_NODE=1`, which IDE-spawned shells often do.
> `env -u ELECTRON_RUN_AS_NODE npm run dev`.

## The packaged layout, locally

```bash
# 1. freeze the server (native: for this machine; no flag: in a container, for SteamOS)
desktop/sidecar/build.sh --native
PYTHON=../../.venv/Scripts/python.exe desktop/sidecar/smoke.sh    # READY, /health, /api/config, a whole game, SIGTERM

# 2. assemble the content package, and try the shell against it
cd desktop
node scripts/assemble-content.mjs --server sidecar/build/server/commanderblitz-server \
  --client ../frontend/dist --data ../data --tar
COMMANDERBLITZ_CONTENT=$PWD/build/content npm run smoke

# 3. the AppImage (Linux only; in WSL use --appimage-extract-and-run, there is no FUSE)
npm run package
```

An update, end to end, with nothing published: assemble a second package with a
higher `--version`, serve `build/` with `python -m http.server`, point
`COMMANDERBLITZ_RELEASES` at it, run the shell against the first package, and
watch `shell.log` in `COMMANDERBLITZ_HOME/logs/`: the check, the download, the
banner, and on Restart the swap. Corrupt the second package's server binary to
see the rollback.

## The install script

```bash
PYTHON=../.venv/Scripts/python.exe bash desktop/steam/test/install.test.sh
```

Runs `install.sh` three times in a scratch home against a stub
`steamos-add-to-steam` and a local web server standing in for the release page.
The same test is a job in the pull-request gate.

## Not verified without a Deck

Recorded here so nobody mistakes "tested" for "tested on the device":

- the non-Steam shortcut's app id: `install.sh` prefers what Steam wrote into
  `shortcuts.vdf` and falls back to the CRC community tools use;
- Chromium under gamescope: `--no-sandbox` and `--ozone-platform-hint=auto` are
  set inside an AppImage; a `flags` file in the per-user directory adds more;
- which Steam Input template a non-browser executable receives (the script and
  the page both say how to change it);
- the frozen server's glibc: built on Debian bookworm (2.36), older than
  SteamOS 3.6's.
