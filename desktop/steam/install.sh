#!/usr/bin/env bash
# Install Commander Blitz on a Steam Deck, from Desktop Mode, in one go.
#
#   curl -fsSL https://github.com/TylerGauntlett/commander-blitz/releases/latest/download/install.sh | bash
#
# What it does, in order:
#   1. downloads the latest AppImage to ~/Applications/CommanderBlitz.AppImage
#      (a FIXED name: the Steam shortcut points at it and the app updates
#      itself in place, so a versioned name would break both);
#   2. writes a launcher (.desktop file) and an icon, so Desktop Mode has it;
#   3. adds it to Steam with `steamos-add-to-steam`, once -- re-running the
#      script updates the file and the art and does not add a second entry;
#   4. copies the library artwork into Steam's grid directory, named by the
#      shortcut's app id, so Game Mode shows a real capsule, hero and logo;
#   5. says what is left to do by hand (switch to Game Mode; and, if the
#      controller arrives as a keyboard, the one template to change).
#
# Re-runnable, and every step that could not happen says so rather than
# failing the rest: a Deck without Steam running still gets the AppImage and
# the launcher, and the next run finishes the job.
#
# Testable: `COMMANDERBLITZ_RELEASES` points it at any server, `HOME` is
# wherever it is, `PYTHON` names the interpreter for the VDF parsing, and
# `steamos-add-to-steam` is whatever is first on PATH. `test/install.test.sh`
# runs the whole thing against a stub in a scratch directory.
set -euo pipefail

RELEASES="${COMMANDERBLITZ_RELEASES:-https://github.com/TylerGauntlett/commander-blitz/releases/latest/download}"
APPS="$HOME/Applications"
APP="$APPS/CommanderBlitz.AppImage"
LAUNCHER="$HOME/.local/share/applications/commanderblitz.desktop"
ICON="$HOME/.local/share/icons/hicolor/256x256/apps/commanderblitz.png"
PY="${PYTHON:-python3}"
NAME="Commander Blitz"

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
note() { printf '  %s\n' "$*"; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# -- 1. the AppImage ---------------------------------------------------------
say "Downloading Commander Blitz"
curl -fsSL "$RELEASES/latest-linux.yml" -o "$WORK/latest.yml"
FILE="$(sed -n 's/^path: *//p' "$WORK/latest.yml" | head -1 | tr -d '\r')"
[[ -n "$FILE" ]] || { echo "could not read the release's file name from latest-linux.yml" >&2; exit 1; }
VERSION="$(sed -n 's/^version: *//p' "$WORK/latest.yml" | head -1 | tr -d '\r')"
mkdir -p "$APPS"
curl -fL --progress-bar "$RELEASES/$FILE" -o "$APP.part"
mv -f "$APP.part" "$APP"
chmod +x "$APP"
note "$APP (${VERSION:-latest})"

# -- 2. the launcher and the art bundle --------------------------------------
say "Setting up the launcher"
curl -fsSL "$RELEASES/steam-assets.tar.gz" -o "$WORK/assets.tar.gz"
mkdir -p "$WORK/assets"
tar xzf "$WORK/assets.tar.gz" -C "$WORK/assets"
mkdir -p "$(dirname "$LAUNCHER")" "$(dirname "$ICON")"
cp "$WORK/assets/grid/icon.png" "$ICON"
# The launcher's Exec carries `--no-sandbox`, and it has to: inside an
# AppImage Chromium's SUID sandbox helper cannot be set up, and on SteamOS
# Chromium then aborts before the app's own code runs -- which is what the
# first release did, in Game Mode and Desktop Mode alike. The switch must be
# on the command line; the app setting it from inside is too late. Steam
# copies Exec, arguments included, into the shortcut's launch options.
sed "s#__APP__#$APP#" "$WORK/assets/commanderblitz.desktop" > "$LAUNCHER"
chmod +x "$LAUNCHER"
note "$LAUNCHER"

# -- 3. Steam ------------------------------------------------------------------
# Steam's per-user directory. Either spelling, depending on how Steam was
# installed; the first that exists wins.
STEAM=""
for candidate in "$HOME/.steam/steam" "$HOME/.local/share/Steam"; do
  if [[ -d "$candidate/userdata" ]]; then STEAM="$candidate"; break; fi
done

# The shortcut's app id, read from Steam's own `shortcuts.vdf` -- a binary
# key/value file -- by finding the entry whose exe is our AppImage. Printing
# nothing means "not there yet".
#
# The AppImage path is read out of the launcher file rather than passed as a
# string: under Git Bash (where the test runs) MSYS rewrites POSIX-looking
# arguments and environment values into Windows paths before a native
# interpreter sees them, and the string must match what Steam stored byte for
# byte. A path used only to open a file survives the rewrite.
read_appid() {
  "$PY" - "$1" "$LAUNCHER" <<'EOF'
import re, struct, sys
path, launcher = sys.argv[1], sys.argv[2]
exec_line = re.search(r"^Exec=(.*)$", open(launcher, encoding="utf-8").read(), re.M).group(1).strip()
# Steam stores the executable and the arguments apart; match on the path.
app = exec_line.split(" --", 1)[0]
try:
    data = open(path, "rb").read()
except OSError:
    sys.exit(0)

def parse(pos):
    out = {}
    while pos < len(data):
        t = data[pos]; pos += 1
        if t == 0x08:
            return out, pos
        end = data.index(b"\x00", pos); key = data[pos:end].decode("utf-8", "replace").lower(); pos = end + 1
        if t == 0x00:
            value, pos = parse(pos)
        elif t == 0x01:
            end = data.index(b"\x00", pos); value = data[pos:end].decode("utf-8", "replace"); pos = end + 1
        elif t == 0x02:
            value = struct.unpack_from("<I", data, pos)[0]; pos += 4
        else:
            return out, len(data)
        out[key] = value
    return out, pos

root, _ = parse(0)
for entry in root.get("shortcuts", {}).values():
    if isinstance(entry, dict) and app in str(entry.get("exe", "")):
        appid = entry.get("appid")
        if appid:
            print(appid)
            break
EOF
}

# What Steam will compute if it has not flushed the file yet: CRC32 of the
# quoted exe path and the name, high bit set. This is what community tools
# use for grid art and it has been stable for years, but it is a reproduction
# of Steam's behaviour, not Steam's answer -- so the file is preferred and this
# is the fallback, said out loud.
guess_appid() {
  "$PY" - "$LAUNCHER" <<'EOF'
import re, sys, zlib
text = open(sys.argv[1], encoding="utf-8").read()
# The path alone: Steam keeps the arguments as launch options, outside the
# id's input.
exe = re.search(r"^Exec=(.*)$", text, re.M).group(1).strip().split(" --", 1)[0]
name = re.search(r"^Name=(.*)$", text, re.M).group(1).strip()
print((zlib.crc32((f'"{exe}"' + name).encode("utf-8")) | 0x80000000) & 0xFFFFFFFF)
EOF
}

APPID=""
if [[ -n "$STEAM" ]]; then
  for vdf in "$STEAM"/userdata/*/config/shortcuts.vdf; do
    [[ -f "$vdf" ]] || continue
    APPID="$(read_appid "$vdf")"
    [[ -n "$APPID" ]] && break
  done
fi

if [[ -n "$APPID" ]]; then
  say "Already in Steam (app id $APPID)"
elif command -v steamos-add-to-steam >/dev/null 2>&1; then
  say "Adding to Steam"
  # The launcher rather than the AppImage: Steam then names the shortcut from
  # the .desktop file's Name and takes its icon, instead of "CommanderBlitz.AppImage".
  steamos-add-to-steam "$LAUNCHER" || note "steamos-add-to-steam did not succeed; is Steam running?"
  sleep 2
  if [[ -n "$STEAM" ]]; then
    for vdf in "$STEAM"/userdata/*/config/shortcuts.vdf; do
      [[ -f "$vdf" ]] || continue
      APPID="$(read_appid "$vdf")"
      [[ -n "$APPID" ]] && break
    done
  fi
  if [[ -z "$APPID" ]]; then
    APPID="$(guess_appid)"
    note "Steam has not written the shortcut yet; using the id it should assign ($APPID)."
    note "If the artwork does not show, restart Steam and run this script again."
  fi
else
  say "Steam's helper is not here"
  note "Add it by hand: Steam > Games > Add a Non-Steam Game > Browse > $APP"
  note "then Properties > Launch Options: --no-sandbox   (it will not start without it)"
fi

# -- 4. the artwork -----------------------------------------------------------
if [[ -n "$APPID" && -n "$STEAM" ]]; then
  say "Installing the library artwork"
  for userdir in "$STEAM"/userdata/*/; do
    uid="$(basename "$userdir")"
    [[ "$uid" == "0" || "$uid" == "anonymous" ]] && continue
    grid="$userdir/config/grid"
    mkdir -p "$grid"
    cp "$WORK/assets/grid/portrait.png" "$grid/${APPID}p.png"
    cp "$WORK/assets/grid/header.png"   "$grid/${APPID}.png"
    cp "$WORK/assets/grid/hero.png"     "$grid/${APPID}_hero.png"
    cp "$WORK/assets/grid/logo.png"     "$grid/${APPID}_logo.png"
    cp "$WORK/assets/grid/icon.png"     "$grid/${APPID}_icon.png"
    note "$grid/${APPID}*"
  done
elif [[ -z "$STEAM" ]]; then
  note "No Steam user directory found; the artwork was not installed."
fi

# -- 5. what is left ------------------------------------------------------------
say "Done"
note "Switch back to Game Mode: Commander Blitz is in your library."
note "If only the D-pad and A work, the controller is arriving as a keyboard:"
note "  select the game > controller icon > Controller settings > Templates > Gamepad."
