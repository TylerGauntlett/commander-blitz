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

## The change

Three steps, each shippable on its own, and the first is the one every
dependent item needs:

1. **Persist the tape.** `GameSession` writes its description to the
   `generated` volume after every applied action (one small file per game, or
   one SQLite file beside the imported decks), and `SessionRegistry` rehydrates
   every unexpired session on boot by replaying it under each entry's recorded
   settings, exactly as `undo` does. Pods persist the same way. Versions are
   process-local ([ADR 0007](../adr/0007-versioned-long-polling.md)) and a client
   that sees a lower version than it held already refetches from zero, so no
   client change is needed for the state to come back. The sweep's TTLs still
   decide what is worth keeping. The ADR records where sessions live and what
   a rehydrated session promises.
2. **Hand over instead of replace.** Start the new container beside the old
   one, wait for its `/health`, point Caddy at it, then stop the old one. With
   step 1 the old container has nothing to lose, so this is a compose
   `healthcheck` plus a start-first update order, and Caddy's retry settings
   cover the moment of the switch; two `web` services behind one upstream list
   is the fallback if compose's ordering is not enough. The deploy job's
   `docker image inspect` and the public `/health` curl stay as they are.
3. **Tell the client.** `index.html` is already `no-store` and the bundles are
   hashed, so a reload lands on the new build; what is missing is knowing a
   reload is due. `GET /api/config` already carries the app version, and
   `UpdateBanner` already draws one line for the desktop's updater, so the
   hosted client shows the same banner when the version it polls moves and
   defers the reload while a decision is pending, the way the Deck defers its
   restart at the table.

What this does *not* buy is a second worker: two processes answering for one
game still need a shared store, and `--workers 1` stays until matchmaking
needs more than one machine.

## Gate

A server test that applies actions, builds a second app over the same
directory, and continues the same game by `game_id` with the same legal
actions; the desktop's restart-in-place test, since this is also what lets
the Deck update while a game is open; and the deploy job's own `/health`
curl, which after step 2 must succeed without a gap a poll can see.
