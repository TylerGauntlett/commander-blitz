#!/usr/bin/env bash
# Hand the site from the live colour to the other one (ADR 0023).
#
#   handover.sh <image-tag>
#
# Run in the directory holding docker-compose.yml, the Caddyfile and .env: on
# the droplet that is /opt/automtg, where the deploy job copies all three and
# runs this. The stopped colour is brought up on <image-tag>, waited on until
# its healthcheck passes, and only then is the live colour stopped. Caddy's
# `first` policy sends each request to whichever is up, and every game is on
# the shared volume, so nothing a player can see is dropped.
#
# .env holds BLUE_TAG, GREEN_TAG and LIVE. LIVE moves only once the handover is
# complete, so a deploy that fails half way leaves the old colour live and the
# next one targets the same idle colour again. A droplet from before blue/green
# has only IMAGE_TAG and a single `web` service; that one is handed over to blue,
# and the orphaned `web` is removed at the end.
#
# Environment, all optional:
#   IMAGE_NAME          the repository the tag is in, as the compose file names it
#   HANDOVER_PULL=0     skip `docker compose pull` (the rehearsal, whose image is
#                       local only)
#   PROBE_URL           polled throughout; any failed poll fails the handover,
#                       which is the "no gap a poll can see" gate
#   PROBE_RESOLVE       passed to curl --resolve, so the probe can go through
#                       Caddy on this machine under the public name
set -euo pipefail

tag="${1:?usage: handover.sh <image-tag>}"

read_env() { sed -n "s/^$1=//p" .env 2>/dev/null | tail -n 1; }

live="$(read_env LIVE)"
blue_tag="$(read_env BLUE_TAG)"
green_tag="$(read_env GREEN_TAG)"
legacy_tag="$(read_env IMAGE_TAG)"

case "$live" in
  blue) idle=green ;;
  green) idle=blue ;;
  "") live=legacy; idle=blue ;;
  *) echo "LIVE=$live in .env is neither blue nor green"; exit 1 ;;
esac

if [ "$idle" = blue ]; then
  blue_tag="$tag"
  green_tag="${green_tag:-${legacy_tag:-$tag}}"
else
  green_tag="$tag"
  blue_tag="${blue_tag:-${legacy_tag:-$tag}}"
fi

# With no LIVE line until a handover completes, so a migration that fails half
# way is still read as one from before blue/green next time.
write_env() {
  {
    printf 'BLUE_TAG=%s\nGREEN_TAG=%s\n' "$blue_tag" "$green_tag"
    case "$1" in blue | green) printf 'LIVE=%s\n' "$1" ;; esac
  } > .env.next
  mv .env.next .env
}

# The probe runs from before the new colour starts until after the old one has
# stopped, and records every poll that did not answer ok.
probe_log="$(mktemp)"
probe_pid=""
if [ -n "${PROBE_URL:-}" ]; then
  (
    resolve=()
    [ -n "${PROBE_RESOLVE:-}" ] && resolve=(--resolve "$PROBE_RESOLVE")
    while :; do
      if ! curl -fsS --max-time 5 "${resolve[@]}" "$PROBE_URL" 2>/dev/null \
          | grep -q '"status":"ok"' && [ ! -e "$probe_log.pause" ]; then
        date -u +%H:%M:%S.%N >> "$probe_log"
      fi
      sleep 0.5
    done
  ) &
  probe_pid=$!
fi
stop_probe() {
  if [ -n "$probe_pid" ]; then kill "$probe_pid" 2>/dev/null || true; fi
  rm -f "$probe_log.pause"
}
trap stop_probe EXIT

echo "live: $live, starting $idle on $tag"
write_env "$live"

if [ "${HANDOVER_PULL:-1}" != 0 ]; then
  docker compose pull "web_$idle"
fi
image="${IMAGE_NAME:-ghcr.io/tylergauntlett/commander-blitz}:$tag"
# The check that would have caught a pull that reported success and pulled
# nothing; it cannot itself pass vacuously.
docker image inspect "$image" >/dev/null \
  || { echo "pull reported success but $image is not present"; exit 1; }

docker compose up -d --no-deps --force-recreate "web_$idle"

healthy=""
for _ in $(seq 1 90); do
  status="$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q "web_$idle")" 2>/dev/null || true)"
  if [ "$status" = healthy ]; then healthy=yes; break; fi
  sleep 2
done
if [ -z "$healthy" ]; then
  echo "web_$idle never became healthy; $live stays live"
  docker compose logs --tail=80 "web_$idle"
  docker compose stop "web_$idle"
  exit 1
fi

# Caddy itself, then its configuration: a bind-mounted Caddyfile changing does
# not make compose recreate the container, so an edited one would otherwise be
# copied up and quietly ignored. `reload` is graceful, and is retried because
# a container that just started is not yet listening on its admin API.
docker compose up -d --no-deps caddy
# A file bind mount follows the inode, and a copy that replaces the file rather
# than rewriting it leaves Caddy reading the old one however often it reloads.
# Then only a new container sees the new file. That restart is the one moment
# a handover is allowed to miss a poll, and it happens only on a deploy that
# changed the Caddyfile.
if ! docker compose exec -T caddy cat /etc/caddy/Caddyfile 2>/dev/null | cmp -s - Caddyfile; then
  echo "caddy sees an older Caddyfile; recreating it"
  touch "$probe_log.pause"
  docker compose up -d --no-deps --force-recreate caddy
  for _ in $(seq 1 20); do
    docker compose exec -T caddy caddy version >/dev/null 2>&1 && break
    sleep 1
  done
  sleep 3
  rm -f "$probe_log.pause"
fi
reloaded=""
for _ in $(seq 1 10); do
  if docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
    reloaded=yes
    break
  fi
  sleep 2
done
[ -n "$reloaded" ] || { echo "caddy never reloaded; $live stays live"; exit 1; }

# Two of Caddy's health intervals (`health_interval` in the Caddyfile), so it
# has seen the new colour healthy before the old one goes and does not have to
# discover it from a failed request.
sleep 20

if [ "$live" = legacy ]; then
  # The single `web` service from before blue/green is an orphan now.
  docker compose up -d --no-deps --remove-orphans caddy
else
  docker compose stop "web_$live"
fi
write_env "$idle"

sleep 3
stop_probe
if [ -s "$probe_log" ]; then
  echo "the site did not answer during the handover at:"
  cat "$probe_log"
  exit 1
fi
echo "handover complete: $idle live on $tag"
