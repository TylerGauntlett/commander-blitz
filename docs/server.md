# How the server is organised

`commanderblitz.server` is a thin driver over the engine with no rules logic:
it creates games, serves the legal-action list, applies the action a client
echoes back, and drives the AI seats until a human has to decide again. This
page is how the package is laid out and why. The HTTP contract — every path,
body and error code — is owned by [api.md](api.md); running and deploying the
process by [deployment.md](deployment.md).

```
├── app.py           create_app / get_app, CORS, /health, serving the built client
├── routes.py        /api — decks, cards, images, catalog, games; /art
├── pod_routes.py    /api/pods — the lobby
├── lobby.py         Pod, PodRegistry: chairs, codes, tokens, lock-in, long-poll
├── sessions.py      GameSession, SessionRegistry: the tape, undo, the AI pump
├── schemas.py       the pydantic request and response models
├── deckinfo.py      DeckList -> DeckSummary / DeckDetail
├── art.py           ArtStore: owned bytes, the lazy fill, printings
├── settings.py      ServerSettings: hosted or desktop
├── connectivity.py  RemoteProbe: is the hosted server reachable?
└── desktop.py       the sidecar entry point the Electron shell spawns
```

## The app factory

`app.create_app()` builds the FastAPI application and hangs everything the
handlers need off `app.state`: `settings`, `probe`, `sessions`
(`SessionRegistry`), `pods` (`PodRegistry`), `card_index` (the catalog, or
`None`), `art` (`ArtStore`) and `reload`. Handlers reach these through the
request, never through module globals, which is what lets the test suite build
as many independent apps as it likes.

Every argument is optional and every existing caller passes almost none.
`data` pins a `GameData` (a test fixture or a script's curated pool; a pinned
app's `reload()` is a no-op, because replacing a fixture with whatever is on
disk is the opposite of what pinning asked for). `settings` defaults to the
hosted server. `probe` is what `/api/config` means by `online`, injectable so a
test can be offline without unplugging anything. `allow_art_fetch` turns the
lazy fill off for tests that must not touch the network. `serve_client` and
`client_dir` are below.

`get_app()` is the lazily built module-level app for
`uvicorn commanderblitz.server.app:get_app --factory`. It is the entry point a
deployment uses, so it passes `serve_client=True` and `settings_from_env()`.

**The two-layer registry.** `create_app` loads `server_registry()`, not
`default_registry()`. The server is the one caller that should see imported
decks and the generated cards behind them; every test, the trainer, the arena
and the CLI stay on the authored layer, so importing a deck cannot change the
answer any of them gives ([deck-import.md](deck-import.md)). `reload()` is how
an import reaches a running server: it clears the `server_registry` cache,
rebinds `sessions.data` (one attribute assignment, atomic under the GIL) and
tells the art store to adopt the new pool. Games in progress keep their own
reference and are deliberately untouched.

**CORS** admits the Vite dev and preview ports (`LOCAL_ORIGINS`) and any
private-network origin (`LAN_ORIGIN_RE`), by regex rather than `*`, with
`allow_credentials=False`. That last setting is why every credential in this
API — the pod token, the library id — travels in a header rather than a cookie.

### `/health`

Registered in `app.py` because it reports on `app.state` as a whole: version,
cards and decks loaded, live game and pod counts, the catalog bundle the index
came from, how much art is cached, known and artless, and under `art.store`
how far the art crawl has got and how many lazy fills this process attempted
([card-catalog.md](card-catalog.md#the-art-store)). Playwright's
`webServer` waits on it; the desktop probe polls it.

### Serving the built client

`_serve_client` registers a catch-all `GET /{client_path:path}` **last**, after
every router, so it only ever sees a path nothing else claimed. The client is a
single page with real addresses (`/pods/GYRE-8412`, `/games/abc`) and nothing on
disk sits at those paths, so: a real file inside `dist` is served as itself;
anything else is `index.html`, and react-router picks the screen. Three guards
keep the catch-all from being too greedy; `tests/server/test_client_serving.py`
pins each:

- A first segment in `SERVER_PREFIXES` (`api`, `art`, `health`, the OpenAPI
  paths) is a 404 the client can read, never an HTML document it will try to
  `JSON.parse`.
- `Path.is_relative_to` is the traversal guard: a `..` resolves out of `dist`
  and stops being a candidate before it is opened.
- `index.html` goes out with `Cache-Control: no-store`, because its whole job is
  to name the current hashed bundles.

Opt-in (`serve_client=True`) rather than "on whenever `dist` exists", because a
route table that depends on whether somebody ran `npm run build` behaves
differently on two machines. The directory is `client_dir`, then
`COMMANDERBLITZ_CLIENT_DIR`, then the checkout's `frontend/dist`.

### `/debug`

`GET /api/games/{id}/debug` returns `serialize.full_view`, libraries and every
hand included. Its docstring says development only, and `tests/server/test_api.py`
asserts that it really does reveal what `player_view` hides. **Nothing in the
code gates it**: no setting, mode or environment check, so on any server it is
reachable by anyone holding a `game_id`. The perimeter is the whole app's.

## Why `routes.py` and `pod_routes.py` are split

The two halves share nothing but `app.state` and have genuinely different
rules: a pod authorises every request by token and blocks on a condition until
something changes; a game route does neither by default. Each file keeps its
own error table (`_IMPORT_STATUS`, `_POD_STATUS`) beside the handlers that
raise it. Both routers mount under `/api`; `art_router` mounts `/art` at the
root so card images read as static assets to the browser and any cache.

## Every handler is a sync `def`

There is not an `async def` in the package. Starlette runs sync handlers in a
thread pool, and that choice carries three consequences. A long poll parks a
pool thread rather than an event loop, which makes the `MAX_POLL_SECONDS`
block affordable at pod scale and lets `TestClient` drive everything without
an async fixture. Two guests claiming the last chair, or two humans acting on
one game, are **genuinely concurrent** — preempted anywhere, not interleaved
at `await` points — so every mutable object has a lock (`Pod._lock`,
`GameSession._lock`, the registries' own), every check that guards a mutation
runs inside the same `with` block as the mutation, and
`tests/server/test_pod_races.py` fires N requests from N threads and asserts
on the *set* of outcomes. And a handler that reads a cursor, mutates and
replies does all three under the session lock (`apply_action` in `routes.py`),
or a second client's events could land in between and be reported as its own.

## `lobby.py` — the pre-game world

The pod model it implements is
[adr/0019-pod-seats-symmetric-readiness.md](adr/0019-pod-seats-symmetric-readiness.md).

Everything that happens before `SessionRegistry.create`. One `Pod` is four
chairs (`POD_SEATS`), a code, a map of `PodPlayer`s, a status
(`open`, `starting`, `in_game`, `closed`) and a version counter. `PodRegistry`
holds every live pod in the process and is the analogue of `SessionRegistry`.

**Codes** are `WORD-NNNN` (`make_code`): a word from `POD_WORDS`, unambiguous
read aloud, and a number, drawn from `secrets` rather than the engine's seeded
RNG because a code is not part of a reproducible game. `normalise_code`
forgives case, whitespace and a missing hyphen.

**Chairs** are `PodSeat`s of kind `empty`, `open` (held for a human who has not
arrived; a new arrival takes one of these first), `cpu` or `human`. A human
seat is `ready` when it has a deck and is `locked`; a CPU is ready the moment
it is seated. The host administers chairs that are not a human's
(`admin_seat`); not even the host reaches into another person's chair.
`_free_deck` picks a CPU's deck deterministically, by *commander* rather
than deck id so two lists sharing a commander never sit at one table, with
`GameData.seating` first when the fixture decks pin it
([decks.md](decks.md#test-fixtures)); `_dedupe_cpu_decks` moves a CPU off a
commander a person has taken.

**Tokens.** `PodPlayer.token` is a bearer credential returned exactly once, at
create or join (`PodCredentials`), and never rendered into any view; rejoining
with one you already hold is idempotent, which is the whole reconnect story.
`Pod.view_for(player_id)` is the only way a pod reaches the wire, exactly as
`player_view` is for a game: another human's deck is hidden until they lock
in, another human's `player_id` is never sent, a CPU is always visible.

**Lock-in** is a commitment to a deck; renaming is deliberately not gated on
it, dealing is refused while any filled chair is not ready. `start` re-checks
every precondition under the lock, promotes any `open` chair to a CPU, compacts
the filled chairs into `SeatConfig`s, builds the `player_token -> seat` map
and hands both to `SessionRegistry.create`; if creation raises the pod goes
back to `open` rather than wedging in `starting`.

**The opportunistic sweep.** `PodRegistry.sweep` runs from `create` and `join`,
not from a reaper thread: the only moment anybody cares whether a chair is
stale is the moment somebody tries to take one. It evicts players idle past
`PLAYER_TTL_SECONDS` (their chair reverts to `open`, the host role passes to
the next human, a pod with no humans closes), drops pods idle past
`POD_TTL_SECONDS` or closed longer than `CLOSED_LINGER_SECONDS` — a closed pod
lingers so a poll in flight is told it *closed* rather than that it never
existed — and then calls `SessionRegistry.sweep`.

**Versioning.** Every mutation ends in `pod._bump()`, which increments
`version` and notifies a `threading.Condition` built on the pod's own lock.
`PodRegistry.wait(pod, since, timeout)` blocks until `version > since` or the
poll ages out; `since=0` returns at once. `Condition.wait_for` releases the lock
while it blocks, the one rule that keeps a waiter from deadlocking a mutator.
Design and alternatives: [adr/0007-versioned-long-polling.md](adr/0007-versioned-long-polling.md).

## `sessions.py` — a game in progress

`GameSession` owns one `Game`, the agents in its AI seats, the per-seat
`full_control` and `manual_mana` settings, the `tokens` map a pod wrote (empty
for the CLI, the smoke script and single-player, which keeps those callers on
the bounds-check-only authorisation), a `version`, and **the tape**.

**The action tape.** Every applied action — human or AI — is appended as a
`TapeEntry(action, seat, human, full_control, manual_mana)`. The two settings
ride on each entry because both change what `legality` offers, so a tape
replayed under today's value could find a recorded Pass or tap illegal.

**Action ids** are positional, `a{index}-{kind}`, minted by `_refresh_actions`
whenever the list changes and served by `actions_for(seat)` only when it is
that seat's decision. `actions_version` records the first version whose state
response carried the current list; `apply_action_id` checks the client's
`version` against it *before* looking the id up, and raises `StaleActionError`
(a `409 stale_action`) for a click on a list the game has since replaced. The
fingerprint includes the tape length, so an identical `a0-pass` after a move is
still a new list and a double-tapped Pass cannot skip a main phase.

**Pumping CPU seats.** `drive_ai(max_steps)` loops: while the game is not over
and the pending decision belongs to an agent, ask the agent, apply, record.
`None` runs to the next human decision (bounded by `MAX_AI_STEPS`), which is
what a script wants; a client that animates the opponents passes `?ai_steps=1`
through `POST /actions`, `/declare`, `/choose` or `/advance` and polls. Human
seats get `auto_pass` and `offer_all_abilities` at `start`; AI seats keep every
priority window so training and the golden tests are unaffected. `declare` and
`choose` take a whole set and loop the engine's increments server-side,
validating the request's shape before anything is applied.

**Undo by replay.** `undo` finds the last human entry, rebuilds the game from
its seed with `_start_locked`, and re-applies the tape up to that entry under
each entry's recorded settings. Replay rather than a snapshot because the
engine never clones state, so replay is the only representation that cannot
silently miss a field — [adr/0005-no-state-cloning.md](adr/0005-no-state-cloning.md).
It is refused in a multi-human session: replay builds a new `Game`, and a
second player already holding the rewound events has no way to reconcile them.

`SessionRegistry` maps `game_id` to session, mints seeds with `new_seed` (from
`secrets`, as pod codes are) and sweeps sessions idle past
`SESSION_TTL_SECONDS` when the pod registry asks.

## `schemas.py` and `deckinfo.py`

`schemas.py` holds every pydantic model that crosses the wire. The one with a
design idea in it is `LegalActionDTO`: an opaque, server-generated `id` the
client echoes back, plus display-only fields, so the client can never invent an
action the engine did not offer ([api.md](api.md#the-key-design-call)).

A deck has two renderings, split by cost. `DeckSummary` backs every tile in
the catalogue and every seat in a pod, so it is fetched dozens of times and
stays light. `DeckDetail` extends it with the dossier — ratings, strategy,
signature cards, and the curve, land count and swap note that are *derived
from the list* at request time so they cannot drift. `deckinfo.py` builds
both, and is its own module because the lobby needs a summary as much as the
deck routes do; a pod importing a private helper out of `routes` would be the
wrong direction of dependency. The `simplified` count reads the importer's
coverage file per request, since an import writes it and a cached map would
misreport the deck somebody just imported.

## `art.py` — the browser never talks to Scryfall

The decision this module implements is
[adr/0012-art-fetched-once-served-locally.md](adr/0012-art-fetched-once-served-locally.md).

The client is only ever given `/art/{card_id}.jpg`, optionally with
`?p={scryfall_id}` for a seat's chosen printing; behind that path is a local
file either way, so a game keeps rendering when Scryfall is down or blocked.

`ArtStore` resolves two directories. `art_dir()` holds the bytes the repository
owns — committed, baked into the image, never written at runtime.
`art_cache_dir()` holds what the lazy fill downloaded, per-deployment state on
a volume. **Owned wins**: `path_for` returns the committed file whenever one
exists, because a cached file is only what some earlier boot believed the
printing to be.

**The path guard.** `CARD_ID` is a tight whitelist over the characters the
loader's slugs use, and `SCRYFALL_ID` (imported from `cards.schema`, so a deck
file's printing ids validate against the same pattern) is the only other shape
accepted. Both are checked in `resolve` before anything reaches the filesystem,
which is what makes `..` and separators unrepresentable.

**The lazy fill.** A card with no file yet — a catalog search result, a future
deck — is fetched once by `_fill`, written atomically, and served; from then on
it is a local file like any other. The store lock covers only the bookkeeping;
the download runs under a per-key gate in `_inflight`, so two requests for the
same card produce one download and different cards never wait on each other.
A failed fetch goes into `_missing`, one lookup per process rather than one
per re-render. `prefetch` runs the same resolution over a whole deck in a
thread pool; the desktop calls it from the import route under `eager_art`.
`missing` is the verdict afterwards: the requests with no file on disk that
have a printing anywhere, so a card with no art at all never holds a deck
back. `forget_misses` empties the negative set before a deliberate retry,
which is what `POST /api/decks/complete` makes.

`_resolve_images` builds the `card_id -> CardArt` map from the committed
`registry_images.json` and overlays the importer's `pool.images.json` with
`setdefault`: the authored layer wins, as it does in `load_game_data`. Which
printing a card draws, the pin file, and the serving rules are owned by
[card-catalog.md](card-catalog.md#how-a-card-finds-its-art).

## Hosted or desktop: `settings.py`, `connectivity.py`, `desktop.py`

The same package serves the site and runs inside the desktop build, where it
is a sidecar on `127.0.0.1` that the Electron shell starts on every launch.
`ServerSettings` lists exactly how the two differ: `mode`, `remote_origin`
(where the hosted server is from the desktop's point of view; `None` on the
site itself), `content_version` and `eager_art`. `settings_from_env` reads them
once at boot; the Docker image sets none and gets the hosted default. The
client learns all of this from `GET /api/config`, never from its origin — a
desktop that lost its connection is still on `127.0.0.1`.

`RemoteProbe` answers `online`: a plain `GET /health` against the remote
origin, remembered for `PROBE_TTL` seconds and bounded by `PROBE_TIMEOUT`, so
a client refetching `/api/config` on a cadence costs one outbound request per
interval. It never raises — being offline is a normal state — and with no
remote origin it is online by definition.

`upstream.py` is the sidecar's other conversation with the remote origin: an
import asked of the site and fetched back as a bundle. A refusal the site gives
with an importer code is raised as that refusal; anything else is
`SiteUnavailable`, and the import route reads Moxfield itself
([ADR 0022](adr/0022-deck-imports-through-the-site.md)).

`desktop.py` is the sidecar entry point (`python -m commanderblitz.server.desktop`,
or the frozen `commanderblitz-server` the AppImage carries). Its contract with
the shell is small and all in one place:

- Arguments (`--data-dir`, `--client-dir`, `--generated-dir`,
  `--remote-origin`, `--content-version`) say where everything is. `apply_env`
  turns them into the `COMMANDERBLITZ_*` variables the package already reads
  (`ENV_VARS` lists exactly which) and forces `COMMANDERBLITZ_MODE=desktop` and
  `COMMANDERBLITZ_EAGER_ART=1`. Arguments at the shell's end because an argv is
  visible in a process list; variables at this end because that is what
  `registry.data_dir()` and friends read. The two test switches,
  `COMMANDERBLITZ_CPU` and `COMMANDERBLITZ_FIXTURE_DECKS`, are deliberately not
  among them ([scripts.md](scripts.md#environment-variables)).
- **The socket is bound before READY is printed.** The shell asks for port `0`;
  `main` binds, listens, and only then prints one line to stdout —
  `READY {"port": ..., "pid": ...}` (`READY_PREFIX`); uvicorn's logging goes to
  stderr. READY also comes *after* `create_app` has compiled the registry, the
  slow part of a launch, so the shell shows a splash until the line arrives.
- `watch_parent` polls `os.getppid()` and sets uvicorn's `should_exit` when
  the shell is gone: Steam's force-close kills the shell and nothing else, and
  an orphaned server holding its port looked like a game still running.

Why the desktop runs its own server, and goes to the site only for friends:
[adr/0009-offline-first-desktop.md](adr/0009-offline-first-desktop.md). Running
it: [steamdeck.md](steamdeck.md).

## In-process memory

Every pod and every game lives in this process: no database, no shared store,
one uvicorn worker. The consequences — a redeploy drops games, a second worker
would answer for games it never heard of — are owned by
[deployment.md](deployment.md#things-to-know).
