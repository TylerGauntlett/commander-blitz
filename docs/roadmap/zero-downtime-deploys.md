---
id: zero-downtime-deploys
title: Zero-downtime deployments
area: site
effort: L
impact: high
why: every game on the site is at risk on every shipping merge, and the site ships on most merges
depends_on: []
status: proposed
adr: true
---

## Today

Every pod and every game lives in one uvicorn worker's memory
([server.md](../server.md#in-process-memory)); the deploy job replaces the
container ([ci-cd.md](../ci-cd.md#build-and-deploy)), so every game in progress
is dropped on every shipping merge, and the site ships on most merges
([ADR 0010](../adr/0010-release-every-main-build.md)). The desktop has the same
constraint in a politer form: its content updater refuses to restart the
server while the player is at a table ([ADR 0009](../adr/0009-offline-first-desktop.md)).

**The lever is already in the design.** A game is fully determined by its seed
and its action tape ([ADR 0005](../adr/0005-no-state-cloning.md)); undo rebuilds
the whole `Game` from them today. A session is therefore small and
serialisable: the seat configuration, the seed, every `TapeEntry`, the token
map and the per-seat settings. A pod is smaller still. Nothing about the
engine has to change for a session to survive a process.

Three things the design does not yet offer. `Action` and `TargetRef` have a
`to_dict` and no way back, so a tape can be written but not read.
`GameSession.last_seen` is `time.monotonic()`, which means nothing to another
process, so the sweep's TTLs cannot be applied to a session read off disk
without a wall-clock stamp beside it. And `docker compose up -d` always stops
the old container before it starts the new one: a start-first update order
exists only under Swarm, so the handover cannot be one compose setting.

## The change

Three steps, one pull request with a commit per step; the first is the one
every dependent item needs:

1. **Persist the tape.** `GameSession` writes its description, one JSON file
   per game under `data/generated/sessions/` on the `generated` volume, after
   every mutation, atomically (a temporary file renamed over the old one).
   `Action` and `TargetRef` gain the inverse of `to_dict`, and the file carries
   a wall-clock stamp for the sweep and the session's `version`, so versions
   stay monotonic across processes and a click read off the old process is
   still recognised as stale ([ADR 0007](../adr/0007-versioned-long-polling.md)).
   `SessionRegistry.get` loads a game from disk on a cache miss, and reloads
   one whose file is newer than the copy in memory, by replaying the tape
   under each entry's recorded settings exactly as `undo` does. A tape that
   does not replay in full is not restored at all: the game is dropped, the
   reason logged, and the client gets the "game not found" it already handles;
   a shortened game would rewind a table that has already watched it move on.
   Pods persist the same way, one file per pod. The sweep's TTLs still decide
   what is worth keeping and delete the file with the session. The ADR
   records where sessions live and what a rehydrated session promises.
2. **Hand over instead of replace.** Blue/green: `web_blue` and `web_green`
   services, each with a compose `healthcheck` on `/health`, behind one Caddy
   `reverse_proxy` with `lb_policy first`, active health checks and a retry
   window, so exactly one backend answers at any instant and a request that
   lands in the switch is retried rather than dropped. The deploy script
   brings up the idle colour on the new tag, waits for it to be healthy, then
   stops the other. Because games load from disk on a miss and reload when
   the file is newer, whichever side answers next sees the last action the
   other side wrote. The deploy job's `docker image inspect` and the public
   `/health` curl stay as they are.
3. **Tell the client.** `index.html` is already `no-store` and the bundles are
   hashed, so a reload lands on the new build; what is missing is knowing a
   reload is due. `GET /api/config` already carries the app version, and
   `UpdateBanner` already draws one line for the desktop's updater, so the
   hosted client shows the same banner when the version it polls moves and
   defers the reload while a decision is pending, the way the Deck defers its
   restart at the table.

What this does *not* buy is a second worker: two processes answering for one
game at once still need a shared store with locking, and `--workers 1` stays
until matchmaking needs more than one machine. Blue/green never has two
processes answering at once; it has one, then the other.

## Gate

A server test that applies actions, builds a second app over the same
directory, and continues the same game by `game_id` with the same legal
actions; the desktop's restart-in-place test, since this is also what lets
the Deck update while a game is open; and the deploy job's own `/health`
curl, which after step 2 must succeed without a gap a poll can see.
