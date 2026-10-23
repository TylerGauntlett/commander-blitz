# ADR 0023 — A game outlives the process that dealt it

**Status:** accepted

[ADR 0005](0005-no-state-cloning.md) made a game a seed and a tape: the engine
never clones state, so undo rebuilds the whole `Game` by replaying the tape.
[ADR 0007](0007-versioned-long-polling.md) made the client follow a session by
its version. [ADR 0010](0010-release-every-main-build.md) ships the site on
most merges. This ADR decides where a game lives between processes, what a
game brought back promises, and how one process hands the site to the next.

## Context

Every game and every pod lived in one uvicorn worker's memory, and the deploy
job's `docker compose up -d` stops the old container before it starts the new
one. So every shipping merge dropped every game in progress, and every pod in
its lobby, with nothing on the screen to say why. A start-first update order
would have been one setting, but compose offers it only under Swarm.

Nothing about the engine stood in the way. A session is its seats, its seed,
its tape (each `TapeEntry` with the stops and mana settings it was taken
under), its seat tokens and its version counters; a pod is its chairs, its
players and its version. What was missing was a place on disk, a way to read
an `Action` back, and a handover that never has nobody answering.

## Decision

**A game lives on disk as well as in memory.** `SessionStore` writes one JSON
file per game under `data/generated/sessions/` on the `generated` volume, and
one per pod under `data/generated/sessions/pods/`, after every change, by
writing a temporary file and renaming it over the old one, so a reader sees the
previous description or the next, never half of one. The memory copy is a cache
of the file, not the other way round. A file's modification time is its
wall-clock stamp: the sweep's TTLs delete a file whose game has gone untouched
for as long as they would have dropped it from memory.

**What is written is the input, never the state.** A game's file is what
`undo` already replays from: seats, seed, `max_turns`, tokens, per-seat
settings, the tape, and `version` and `actions_version`. An `Action` is written
by `Action.to_record`, every field that is part of its identity and none that
is display, so a field added to `Action` is written without anyone remembering
to. Writing a snapshot of `GameState` would be the state clone ADR 0005 rules
out, by another name.

**A game comes back whole or not at all.** `SessionRegistry.get` loads a game
it does not hold from its file, and reloads one whose file is newer than the
copy it holds, by dealing from the seed and replaying every entry under the
settings it was taken with. If any entry is not a legal action at its point in
the replay (a card's rules changed between builds, an engine fix moved a
priority window), the game is not restored: the file is deleted, the reason is
logged, and the client gets the "no game" it already handles. A shortened game
would rewind a table that has already watched it move on, and nobody at that
table could tell.

**A game brought back keeps its version.** The restored session carries the
version and the actions version it was written with, so a long poll resumes
where it was, and an action id read off the old process is still checked
against the list it came from. Action ids are positional over a deterministic
legal-action list, so the same state mints the same ids.

**The site is handed over, never replaced.** Two compose services,
`web_blue` and `web_green`, each with a `healthcheck` on `/health`, sit behind
one Caddy `reverse_proxy` with `lb_policy first`, active health checks and a
retry window. The deploy brings up the idle colour on the new tag, waits for it
to be healthy, then stops the other. At any instant exactly one process
answers: blue while it is healthy, else green. A request in flight on the old
side that writes a file after the new side loaded the game is picked up by the
newer-file reload, and a long poll parked on the old side times out and is
retried on the new one.

**The hosted client is told.** When the app version it reads from
`GET /api/config` moves, the client shows the same `UpdateBanner` line the
desktop updater draws and reloads once no decision is pending, so a player is
not pulled out of a choice.

## Consequences

- **One process answers at a time, still.** `--workers 1` stays: two
  processes taking actions on one game at once would need locking across them,
  and nothing here provides it. Blue/green has one process, then the other.
- **A deploy can drop a game on purpose.** A merge that changes what a card
  does can make an old tape illegal; that game ends at the deploy, as every
  game used to. Making replay forgive divergence is the reversal to avoid: it
  would restore games that are not the games that were played.
- **A CPU's choices after a restore can differ** from the choices it would have
  made without one: the tape holds what the CPU did, not the agent's internal
  state, and the agent is dealt fresh. Undo already has this property.
- **Every change rewrites the whole file.** A tape is small beside the card
  pool and a write is one per request, not one per action; an append-only log
  is the change to make if a game's file ever costs more than its request.
- **Writing a file outside `SessionStore`, or writing it before the change it
  records,** breaks the cache rule: a reload would hand back a game behind the
  one on screen. The write is in `_bump`, under the session's lock.
- **A session whose file is replaced in memory wakes its waiters** so a long
  poll on the old object returns at once and the client polls the new one.
- `create_app` persists only when it is given a store. The deployment entry
  points and the desktop pass one; the test suite's apps do not, unless the
  test is about persistence.

## Rejected

- **One SQLite file.** Transactions, but a schema to migrate, one file every
  game shares, and a lock the request threads contend on. A file per game
  needs no dependency and a bad file loses one game.
- **Snapshots of `GameState`.** Faster to load, and exactly the state clone
  ADR 0005 rejected: a field the snapshot forgets is a rule that silently stops
  holding after a deploy.
- **Restoring the longest prefix that still replays.** Keeps more games, and
  every one of them is a game rewound without telling the players.
- **Preloading every game at boot.** The new side would load before the old
  side stopped writing and serve a game a few actions behind. Loading on the
  first request after the switch reads the file as the old side left it.
- **A third-party rollout plugin.** One more thing to install on the droplet
  and keep current, for what two services and Caddy's `first` policy already
  do.
