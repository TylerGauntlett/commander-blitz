#!/usr/bin/env bash
# Does the frozen server work? Start it the way the shell does, play a game
# against it over HTTP, stop it the way the shell does.
#
#   desktop/sidecar/smoke.sh [path/to/commanderblitz-server] [data-dir]
#
# Defaults to the build this directory's build.sh produced and the repo's
# data/. Exits non-zero on the first thing that is not as the shell expects:
# no READY line, a READY line it cannot parse, /health or /api/config wrong,
# the game failing, or a SIGTERM the process does not act on within ten
# seconds.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
BIN="${1:-$HERE/build/server/commanderblitz-server/commanderblitz-server}"
DATA="${2:-$ROOT/data}"
GENERATED="$(mktemp -d)"
trap 'rm -rf "$GENERATED"' EXIT

echo "== --check"
"$BIN" --check --data-dir "$DATA" --generated-dir "$GENERATED" | tee "$GENERATED/check.json"
grep -q '"cards": *[0-9]\{4,\}' "$GENERATED/check.json" || { echo "too few cards"; exit 1; }

echo "== start"
"$BIN" --port 0 --data-dir "$DATA" --generated-dir "$GENERATED" \
  --remote-origin http://127.0.0.1:1 --content-version smoke \
  > "$GENERATED/stdout" 2> "$GENERATED/stderr" &
PID=$!
trap 'kill "$PID" 2>/dev/null; rm -rf "$GENERATED"' EXIT

for _ in $(seq 1 120); do
  if grep -q '^READY ' "$GENERATED/stdout"; then break; fi
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "exited before READY:"; cat "$GENERATED/stderr"; exit 1
  fi
  sleep 0.5
done
READY="$(grep '^READY ' "$GENERATED/stdout" | head -1)"
[[ -n "$READY" ]] || { echo "no READY within 60s"; cat "$GENERATED/stderr"; exit 1; }
PORT="$(sed -E 's/.*"port": *([0-9]+).*/\1/' <<<"$READY")"
echo "$READY"

echo "== health"
curl -fsS "http://127.0.0.1:$PORT/health" | head -c 200; echo
echo "== config"
CONFIG="$(curl -fsS "http://127.0.0.1:$PORT/api/config")"
echo "$CONFIG"
grep -q '"mode":"desktop"' <<<"$CONFIG" || { echo "not desktop"; exit 1; }
grep -q '"online":false' <<<"$CONFIG" || { echo "should be offline"; exit 1; }

echo "== a game"
# `PYTHON` because this runs on Windows too (Git Bash, no `python3`), where
# the repo's venv is the interpreter with `httpx` for the smoke script.
"${PYTHON:-python3}" "$ROOT/scripts/smoke_http.py" --url "http://127.0.0.1:$PORT" \
  --players 2 --seed 2 --deck aesi_tyrant_of_gyre_strait --opponent-deck edgar_markov

echo "== stop"
kill -TERM "$PID"
for _ in $(seq 1 20); do
  kill -0 "$PID" 2>/dev/null || { echo "stopped"; trap 'rm -rf "$GENERATED"' EXIT; exit 0; }
  sleep 0.5
done
echo "did not stop within 10s"; exit 1
