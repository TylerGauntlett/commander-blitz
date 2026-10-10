#!/usr/bin/env bash
# `install.sh`, end to end, in a scratch directory.
#
# A fake home, a local web server standing in for the releases page, and a
# stub `steamos-add-to-steam` on PATH that records what it was asked and --
# on the first run -- writes a minimal `shortcuts.vdf` the way Steam would,
# with a known app id. Two runs:
#
#   run 1: nothing installed; the stub "adds" the shortcut and Steam has
#          flushed the file, so the artwork is named by the file's app id;
#   run 2: everything already there; the stub must NOT be called again, the
#          AppImage and art are replaced, nothing is duplicated.
#
# ...and a third, in a second fake home where the stub writes nothing, which
# exercises the CRC fallback: the artwork is named by the id Steam should
# assign, computed here independently.
#
# Runs on Linux, in WSL, in `docker run ubuntu:22.04`, and in Git Bash on
# Windows (`PYTHON` names the interpreter when `python3` is not one).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEAM_DIR="$(cd "$HERE/.." && pwd)"
PY="${PYTHON:-python3}"
export PYTHON="$PY"

SCRATCH="$(mktemp -d)"
cleanup() {
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
    # Its working directory is inside the scratch; give it a moment to let go.
    for _ in $(seq 1 20); do kill -0 "$SERVER_PID" 2>/dev/null || break; sleep 0.1; done
  fi
  rm -rf "$SCRATCH" 2>/dev/null || true
}
trap cleanup EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "ok   $*"; }

# -- the fake release -----------------------------------------------------------
SITE="$SCRATCH/site"
mkdir -p "$SITE"
printf 'version: 9.9.9\nfiles:\n  - url: CommanderBlitz-9.9.9.AppImage\npath: CommanderBlitz-9.9.9.AppImage\n' > "$SITE/latest-linux.yml"
printf '#!/bin/sh\necho fake appimage 9.9.9\n' > "$SITE/CommanderBlitz-9.9.9.AppImage"
mkdir -p "$SCRATCH/assets/grid"
for name in portrait header hero logo icon; do
  printf 'PNG-%s' "$name" > "$SCRATCH/assets/grid/$name.png"
done
cp "$STEAM_DIR/commanderblitz.desktop" "$SCRATCH/assets/"
tar czf "$SITE/steam-assets.tar.gz" -C "$SCRATCH/assets" grid commanderblitz.desktop

# Serve it. `-b 127.0.0.1` and a free port, read back from the server's log.
PORT="$("$PY" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')"
(cd "$SITE" && "$PY" -m http.server "$PORT" -b 127.0.0.1 >"$SCRATCH/http.log" 2>&1) &
SERVER_PID=$!
for _ in $(seq 1 50); do
  if curl -fs "http://127.0.0.1:$PORT/latest-linux.yml" >/dev/null 2>&1; then break; fi
  sleep 0.1
done
export COMMANDERBLITZ_RELEASES="http://127.0.0.1:$PORT"

# -- the stub ---------------------------------------------------------------------
# Writes a binary shortcuts.vdf with one entry, exe = the launcher's Exec, when
# STUB_WRITES_VDF is set; always appends its argv to a log.
BIN="$SCRATCH/bin"
mkdir -p "$BIN"
cat > "$BIN/steamos-add-to-steam" <<'EOF'
#!/usr/bin/env bash
echo "$@" >> "$STUB_LOG"
if [[ -n "${STUB_WRITES_VDF:-}" ]]; then
  "$PYTHON" - "$1" "$STUB_WRITES_VDF" "$HOME" <<'PY'
import re, struct, sys
launcher, out, home = sys.argv[1], sys.argv[2], sys.argv[3]
# As Steam does: the executable apart from its arguments.
exe = re.search(r"^Exec=(.*)$", open(launcher).read(), re.M).group(1).split(" --", 1)[0]
name = re.search(r"^Name=(.*)$", open(launcher).read(), re.M).group(1)
def s(k, v): return b"\x01" + k.encode() + b"\x00" + v.encode() + b"\x00"
def i(k, v): return b"\x02" + k.encode() + b"\x00" + struct.pack("<I", v)
entry = b"\x00" + b"0\x00" + i("appid", 2882400001) + s("AppName", name) + s("Exe", f'"{exe}"') + s("StartDir", home) + b"\x08"
data = b"\x00shortcuts\x00" + entry + b"\x08\x08"
import os; os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, "wb").write(data)
PY
fi
EOF
chmod +x "$BIN/steamos-add-to-steam"
export PATH="$BIN:$PATH"

# =================================================================================
# Home 1: Steam flushes the file. Two runs.
# =================================================================================
export HOME="$SCRATCH/home1"
mkdir -p "$HOME/.steam/steam/userdata/12345678/config" "$HOME/.steam/steam/userdata/0/config"
export STUB_LOG="$SCRATCH/stub1.log"
export STUB_WRITES_VDF="$HOME/.steam/steam/userdata/12345678/config/shortcuts.vdf"
: > "$STUB_LOG"

echo "== run 1 (fresh)"
bash "$STEAM_DIR/install.sh"

APP="$HOME/Applications/CommanderBlitz.AppImage"
[[ -x "$APP" ]] || fail "AppImage not at the fixed path, or not executable"
grep -q "fake appimage 9.9.9" "$APP" || fail "AppImage content"
[[ ! -e "$APP.part" ]] || fail "a .part file was left behind"
pass "AppImage at $APP"

LAUNCHER="$HOME/.local/share/applications/commanderblitz.desktop"
[[ -f "$LAUNCHER" ]] || fail "no launcher"
# With `--no-sandbox`: Chromium aborts inside an AppImage on SteamOS without it.
grep -q "^Exec=$APP --no-sandbox$" "$LAUNCHER" || fail "launcher Exec is not the AppImage with --no-sandbox"
grep -q "^Name=Commander Blitz$" "$LAUNCHER" || fail "launcher name"
[[ -f "$HOME/.local/share/icons/hicolor/256x256/apps/commanderblitz.png" ]] || fail "no icon"
pass "launcher and icon"

[[ "$(wc -l < "$STUB_LOG")" == "1" ]] || fail "steamos-add-to-steam called $(wc -l < "$STUB_LOG") times, expected 1"
grep -q "commanderblitz.desktop" "$STUB_LOG" || fail "steamos-add-to-steam was not given the launcher"
pass "added to Steam once, via the launcher"

GRID="$HOME/.steam/steam/userdata/12345678/config/grid"
for f in 2882400001p.png 2882400001.png 2882400001_hero.png 2882400001_logo.png 2882400001_icon.png; do
  [[ -f "$GRID/$f" ]] || fail "missing $GRID/$f"
done
[[ "$(cat "$GRID/2882400001p.png")" == "PNG-portrait" ]] || fail "portrait content"
[[ "$(cat "$GRID/2882400001.png")" == "PNG-header" ]] || fail "header content"
[[ ! -d "$HOME/.steam/steam/userdata/0/config/grid" ]] || fail "artwork written for the anonymous user"
pass "artwork named by the app id Steam wrote"

echo "== run 2 (again)"
printf '#!/bin/sh\necho fake appimage 9.9.10\n' > "$SITE/CommanderBlitz-9.9.9.AppImage"
bash "$STEAM_DIR/install.sh"
grep -q "fake appimage 9.9.10" "$APP" || fail "AppImage was not replaced"
[[ "$(wc -l < "$STUB_LOG")" == "1" ]] || fail "steamos-add-to-steam was called again on a re-run"
[[ "$(ls "$GRID" | wc -l)" == "5" ]] || fail "artwork duplicated: $(ls "$GRID")"
pass "re-run replaced the file and added nothing twice"

# =================================================================================
# Home 2: Steam has not flushed the file; the CRC fallback names the art.
# =================================================================================
export HOME="$SCRATCH/home2"
mkdir -p "$HOME/.local/share/Steam/userdata/42/config"
export STUB_LOG="$SCRATCH/stub2.log"
unset STUB_WRITES_VDF
: > "$STUB_LOG"

echo "== run 3 (no shortcuts.vdf yet)"
bash "$STEAM_DIR/install.sh" | tee "$SCRATCH/run3.log"
grep -q "has not written the shortcut yet" "$SCRATCH/run3.log" || fail "the fallback was not announced"

APP="$HOME/Applications/CommanderBlitz.AppImage"
# From the launcher file, as install.sh does: see `read_appid` there for why
# the path is not simply passed as a string.
EXPECTED="$("$PY" -c "import re,sys,zlib; t=open(sys.argv[1]).read(); e=re.search(r'^Exec=(.*)$',t,re.M).group(1).split(' --',1)[0]; print((zlib.crc32(('\"'+e+'\"'+'Commander Blitz').encode())|0x80000000)&0xFFFFFFFF)" "$HOME/.local/share/applications/commanderblitz.desktop")"
GRID="$HOME/.local/share/Steam/userdata/42/config/grid"
[[ -f "$GRID/${EXPECTED}p.png" ]] || fail "fallback art not named $EXPECTED: $(ls "$GRID" 2>/dev/null)"
[[ -f "$GRID/${EXPECTED}_hero.png" ]] || fail "fallback hero"
pass "artwork named by the CRC fallback ($EXPECTED)"

echo "all install.sh checks passed"
