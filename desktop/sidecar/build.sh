#!/usr/bin/env bash
# Freeze the server for Linux, in a container, so the result runs on SteamOS.
#
#   desktop/sidecar/build.sh            # -> desktop/sidecar/build/server/commanderblitz-server/
#   desktop/sidecar/build.sh --native   # on this machine's Python, for a local check
#
# A container rather than the host because a PyInstaller build links against
# the glibc it was built on and runs on anything newer. Debian bookworm's
# 2.36 is older than SteamOS 3.6's, and it is what `python:3.13-slim` ships,
# which is also the Docker image's base -- one less thing to keep in step.
#
# `--native` skips Docker and uses whatever `python` is on PATH (the repo's
# venv, on a developer's machine). That build runs only on this machine, but it
# exercises the spec, which is the part that goes wrong.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="$HERE/build"

if [[ "${1:-}" == "--native" ]]; then
  PY="${PYTHON:-python}"
  "$PY" -m pip install --quiet -c "$ROOT/constraints.txt" "$ROOT[desktop]"
  (cd "$HERE" && "$PY" -m PyInstaller --clean --noconfirm \
      --distpath "$OUT/server" --workpath "$OUT/work" commanderblitz-server.spec)
else
  docker run --rm \
    -v "$ROOT:/w" -w /w/desktop/sidecar \
    -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
    python:3.13-slim-bookworm bash -euo pipefail -c '
      apt-get update -qq && apt-get install -y -qq --no-install-recommends binutils >/dev/null
      pip install --quiet -c /w/constraints.txt "/w[desktop]"
      python -m PyInstaller --clean --noconfirm \
        --distpath build/server --workpath build/work commanderblitz-server.spec
      # `sed -n 1p`, not `head -1`: head closes the pipe after one line, ldd
      # takes SIGPIPE, and under pipefail that is exit 141 after a build that
      # had already succeeded. sed reads to the end.
      ldd --version | sed -n 1p > build/server/glibc.txt
      # The container runs as root; hand the tree back to whoever called.
      chown -R "$(stat -c %u:%g /w/desktop)" build
    '
fi

echo "frozen: $OUT/server/commanderblitz-server/"
du -sh "$OUT/server/commanderblitz-server" | cut -f1
