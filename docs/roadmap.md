# Roadmap

The core loop is finished: a human, a CPU and a training policy all play the
same engine through one seam, every shipped deck is implemented card for card,
the client runs on a desktop, a Steam Deck and a phone, and the site and the
Deck release themselves from every merge that ships. This page is what comes
after. It is the one page under `docs/` about things that do not exist yet,
and it breaks the house rule against numbers exactly where a target *is* a
number.

How to read it:

- Each item says what it is, what in the current design makes it hard or
  easy, how it would be built, and what gate would hold it. Where an item
  turns on a decision with consequences, the decision gets an ADR before the
  code.
- Sizes are the ones [TECH_DEBT.md](../TECH_DEBT.md) uses: **S** an afternoon,
  **M** a focused pull request, **L** a multi-PR effort.
- An item leaves this page the way a debt item leaves that one: when the work
  lands, delete the entry in the same pull request and let the docs it touched
  carry the result. Nothing here is a changelog.

[Suggested order](#suggested-order) is at the end, because most of the items
depend on one another and the dependencies are the useful part.

## Operating the site

### Zero-downtime deployments — **L**

**Today.** Every pod and every game lives in one uvicorn worker's memory
([server.md](server.md#in-process-memory)); the deploy job replaces the
container ([ci-cd.md](ci-cd.md#build-and-deploy)), so every game in progress
is dropped on every shipping merge, and the site ships on most merges
([ADR 0010](adr/0010-release-every-main-build.md)). The desktop has the same
constraint in a politer form: its content updater refuses to restart the
server while the player is at a table ([ADR 0009](adr/0009-offline-first-desktop.md)).

**The lever is already in the design.** A game is fully determined by its seed
and its action tape ([ADR 0005](adr/0005-no-state-cloning.md)); undo rebuilds
the whole `Game` from them today. A session is therefore small and
serialisable: the seat configuration, the seed, every `TapeEntry`, the token
map and the per-seat settings. A pod is smaller still. Nothing about the
engine has to change for a session to survive a process.

**Build it in three steps, each shippable on its own:**

1. **Persist the tape.** `GameSession` writes its description to the
   `generated` volume after every applied action (one small file per game, or
   one SQLite file beside the imported decks), and `SessionRegistry` rehydrates
   every unexpired session on boot by replaying it under each entry's recorded
   settings, exactly as `undo` does. Pods persist the same way. Versions are
   process-local ([ADR 0007](adr/0007-versioned-long-polling.md)) and a client
   that sees a lower version than it held already refetches from zero, so no
   client change is needed for the state to come back. The sweep's TTLs still
   decide what is worth keeping. Gate: a server test that applies actions,
   builds a second app over the same directory, and continues the same game by
   `game_id` with the same legal actions; and the desktop's restart-in-place
   test, since this is also what lets the Deck update while a game is open.
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
needs more than one machine, which is further down this page.

### Gate the debug endpoint — **S**

`GET /api/games/{id}/debug` reveals every hand on the hosted site to anyone
holding a `game_id`. It is `SV-01` in [TECH_DEBT.md](../TECH_DEBT.md), the
cheapest item there, and it should land before anything that puts more
strangers at one table.

### Outcomes as data — **M**

Several items below want to know what actually happens at the table: how long
games run, which decks win, how often a draw is a `RulesLoopError`, how often
a seat is abandoned. `/health` counts live games and nothing else. One
structured log line per game end (deck ids, seats, turns, outcome and reason,
never a name or a token) and one per abandonment is enough to tune brackets,
matchmaking and the CPU from real play rather than the arena alone. Opt-in
on the desktop, where the player's machine is the server.

## Presentation and branding

### A mark, a wordmark, and the surfaces that carry them — **M**

The door's room art, the Steam capsule and hero and the OG card all exist and
are drawn from the same scene, and the board's look is settled by
[ADR 0011](adr/0011-the-card-is-the-illustration.md): the card is the
illustration, and type is never carried by colour. What is missing is an
identity that holds at every size the project needs: a mark that survives a
favicon and a Steam library icon, a wordmark for the door and the README, and
the rule for how each sits over art it must not fight. Deliverables:

- the mark and wordmark as SVG under `frontend/public/`, with the Steam
  assets regenerated from them rather than drawn again;
- a short `docs/brand.md` naming the type pair, the signal tokens already in
  `theme.css` that the brand may use, and where the mark may and may not sit
  (never over a card face);
- the splash the desktop shell shows until the sidecar prints READY, the
  game-over screen and the not-found screen, which are the three places a
  player looks at nothing but the brand;
- store-page material in the README: screenshots per layout mode and a short
  capture of a turn, since the Steam Deck install is the project's front door
  for a stranger.

### Sound — **S**

`audio/sfx.ts` synthesises its palette. A recorded set, one cue per beat the
narration already names, replaces it without touching the scheduler; the
reduced-motion channel decides whether it plays.

## Cards

### Full engine support for the catalog — **L**, continuous

**Today.** Every shipped deck is native; everything else imports as a proxy
that keeps its keywords and loses its text ([deck-import.md](deck-import.md)).
The loop that closes the gap is in place: the template tier, the agent tier
behind six gates, gap records, and `/extend-dsl` to clear them
([card-authoring.md](card-authoring.md)). The queue is already ordered by what
players have imported and then by EDHREC rank, which is the right order and
stays.

**What "all known cards" runs into, in the order it will be met:**

1. **The validator.** Every new op adds a branch to `_validate_effect`, which
   is already the largest function in the tree (`OF-01`). A per-op validator
   registry, mirroring the engine's `@register`, is the precondition for the
   long tail, not a nicety.
2. **The deliberate simplifications** in
   [rules-coverage.md](rules-coverage.md#simplified). Most of the catalog never
   touches them, but the ones that bite as coverage widens are: layers-lite
   ([ADR 0001](adr/0001-layers-lite.md)) once two statics genuinely depend on
   each other on a board players build; card-level targets chosen before
   modes, which is why modal spells are the oldest open item in the authoring
   doc; and the absence of a general replacement system, which every "instead"
   that is not one of the named hooks runs into. Each of these is an ADR
   amendment, not a card.
3. **The not-implemented list** in the same page: companions, the initiative,
   voting, energy, damage division, redirection. Each is additive and each is
   ordered by how many cards the gap report says it blocks.
4. **Test cost.** `test_every_card_works` and the auto-card gates run over the
   whole pool on every run. At tens of thousands of cards the python slice
   needs sharding by card file, as the e2e slice is sharded today, and the
   golden pool hash needs a per-file variant so a change to one file re-pins
   one hash.
5. **Art.** Every supported card wants its art committed or lazily filled, and
   `data/art/` is Wizards-owned illustration
   ([card-catalog.md](card-catalog.md#a-note-on-the-images)). The note there
   asks for a deliberate decision before the corpus grows; scaling to the
   catalog is that moment. The desktop's content package also carries the art
   it ships, so a size budget for the package belongs in the same decision.

**Working set first.** Full support is open-ended, so the measurable target
is the one the deck roadmap below sets: every card in every deck on the
curated list, native. That set is a few thousand distinct cards and it is the
set players will actually meet; the queue's existing order already favours
it. The proxy generator stays as the honest fallback for everything else.

**Gates:** `author_cards.py --report` for coverage, the generated
[unsupported-cards.md](unsupported-cards.md) for what blocks what, and one
import pin per shipped deck, which is the guarantee behind "paste a link".

## Decks

### A catalogue of the most-played decks — **L**

**Target.** Roughly the hundred most popular commanders, each with a
representative public list, selectable from the shelf the way the twelve
precons are now; the user's brief says a hundred or more, and the number is a
floor to plan the data model around rather than a ceiling.

**Sources.** The catalog index already carries Scryfall's `edhrec_rank`, so a
first cut of "popular commanders" is the legendary creatures ranked by it
with no scraping at all; EDHREC's own commander pages are the sharper source
and the one to prefer when a list is curated by hand. Lists come from
Moxfield through the import path that exists today (`/v3/decks/all/{id}` is
open; Moxfield's search is not, as [deck-import.md](deck-import.md) records),
so the curated input is a manifest, `data/decks/sources.json`: one row per
deck with the commander, the Moxfield URL, the author to credit, and the
EDHREC rank at the time of curation, kept by a script that re-reads the rank
and reports which rows have drifted. Attribution stays on the deck file, as
`promote_deck.py --url` already records it.

**What a shipped deck costs today, and what has to change at a hundred:**

| Requirement now | Held by | At a hundred decks |
|---|---|---|
| Every card native | the import pin test per deck | Unchanged. This is what makes it a precon, and it is what drives the card roadmap in the order players meet cards |
| Tags, ratings, strategy, signature cards | `test_deck_metadata.py` | Two tiers in the catalogue: a **precon** with the full dossier, and a **featured** deck with the honest empty states the dossier already draws. The `source` field grows a third value; the shelf's source filter grows a third segment |
| A CPU strategy module and a page under `docs/cpus/` | `test_registry.py` | A deck file declares an `archetype`, and `strategy_for` falls back deck id, commander, archetype, default. A module and a page stay the mark of a precon; a featured deck gets the archetype's plan and the test asks for one or the other |
| Every precon through a whole four-player game | `test_deck_games.py` | A seeded sample per run rather than every deck, with the full matrix in the arena stage, which is already its own runner |
| Art for every printing the list chose | eager prefetch on the desktop | The content package's size budget, from the card roadmap |

**The shelf at a hundred.** `DeckCatalog` is a grid with search, colour pips,
a source filter and a cycling sort. At this size it needs: a sort by
popularity (the rank from the manifest, carried on `DeckSummary`), an
archetype filter, the bracket filter from the matchmaking section, and a grid
that stays walkable with a pad, which means grouping by archetype or colour
with group headers as regions rather than one long sweep. The floors of
[ADR 0013](adr/0013-handheld-floors-are-ci-gates.md) apply to every tile.

### Viewing a deck's list — **M**

**Today.** The dossier shows the commander, the editorial half, the curve, the
land count and the simplified count. It never shows the list.

**Add a list view**, the way Moxfield's default view reads: every card as a
face, grouped by type with the group counts, sorted by mana value within a
group, with `Y` or hover reading the card in full through the same preview
the board uses. Specifics:

- A new `GET /api/decks/{id}/cards` rather than widening `DeckDetail`, which
  is fetched for every dossier and should stay light; the list is derived at
  request time like the curve, so it cannot drift from the file.
- A **per-card** simplified marker, so an imported deck says which cards are
  inert rather than only how many; the coverage file the importer writes
  already knows.
- Where the source list carries the author's categories, keep them on the
  import and offer "by category" beside "by type"; where it does not, "by
  type" is the only grouping and nothing is invented.
- A stats strip: the curve that exists, colour pips against mana sources,
  type counts, and the bracket signals from the matchmaking section. Charts
  follow the dataviz rules the project already uses for the curve, in both
  themes.
- `StaticCard` for every face, since a second `layoutId` for an oid would
  animate between copies, and group headers as regions so the ring walks a
  hundred cards by group rather than one at a time.

The same view is what a seat opens in the pod to check an opponent's locked
deck, so it has to render for a deck with no dossier at all.

## Play experience

### One selection model — **M**

**The problem, by example.** Pressing a permanent with several abilities asks
which one in a modal (`AbilityMenu`); a Treasure asks which colour the same
way. Proliferate, "any number of target permanents" and the other pick-several
decisions are answered as rows in the action panel with a commit slab
(`PickRows`), and the board's cards toggle those rows. Targets are chosen on
the board. Modes, X and yes-or-no are dialogs. Many options with no card face
are a `ChoiceCombo`. Every one of these was the right call for the decision
it was built for, and together they are five shapes for what a player
experiences as one question: *which of these things do I mean?*

**The rule to converge on:** a choice among things on the table is made on
the table, staged, and committed once; a choice among things that are not on
the table is made in the panel or a dialog; and the panel remains the
universal fallback under which every legal action is one control exactly once
([ADR 0015](adr/0015-every-legal-action-is-one-control.md)). Attack
declaration already follows the rule, and `PickRows` already borrowed its
shape; what is left is to make the board the primary surface for every
object pick and the panel the mirror, with one staged set in `uiStore` and
one commit control (`logic/commit.ts`) rather than a set per surface.

**Do it as an audit before it is done as code.** A table of every
`PendingDecision` kind and purpose against the surface it uses today and the
surface the rule gives it, kept beside `Journeys.stories.tsx` with a press
budget per decision, is the deliverable of the first pull request; the
budgets are what make "unified" measurable and what stop a later surface
from drifting back.

**Smaller items in the same pass:**

- `B` always backs out of a staged set, everywhere, and never discards a set
  the player cannot rebuild in one press.
- The targeting hint says why a card is skipped; the same hint for a card
  that cannot be *cast* (mana, timing, a cast lock) and an ability that cannot
  be activated, read from the engine's own reason where it has one.
- The stack: a response to a response is a stack of three and the panel is
  the only place that reads it in order.
- `UI-02`, the accessibility pass, because every surface this touches is one
  of the ones it lists.

### CPU takeover and reconnection — **M**

A seat whose human stops answering holds the table. The pod sweep already
evicts an idle chair before the deal; after it, the sweep ends the session.
Once sessions persist, the natural rule is that a seat idle past a threshold
is piloted by the strategy CPU for the deck it holds, that the human may
reclaim it with the same token, and that the table is told. This is also the
precondition for matchmaking with strangers, where leaving is normal.

### Replays and sharing — **M**

The seed and the tape are a replay ([ADR 0005](adr/0005-no-state-cloning.md)).
A "share this game" link that serves them to a replay viewer, which steps the
narration beat by beat with the playback controls that already exist, is a
small amount of client work and a large amount of value: every bug report
becomes a tape, every CPU misplay in the next section becomes a position the
arena can be pointed at, and a game worth watching can be watched.

### Difficulty — **S**

Three agents already exist with a clear ordering: `heuristic_classic`,
`heuristic` with its strategies, and `policy`. A per-seat choice in the pod
(easy, normal, hard) is a field on `SeatConfig` and a segment on the CPU
chair, with hard meaning the best checkpoint shipped, and it gives the
advanced-CPU work below a place to land that a player can see.

### Archidekt import — **S**

[deck-import.md](deck-import.md) says an adapter, not a second pipeline. It
is the second most common link a player will paste.

## Advanced CPUs

**Today.** The CPU is reflexive: the heuristic scores every legal action from
the position in front of it and a per-deck `Strategy` adjusts the scores
([cpus/README.md](cpus/README.md)). It cannot look ahead, because state is
never cloned, and it reads the table only as board power and life. The gaps a
playtester notices are the ones [TECH_DEBT.md](../TECH_DEBT.md) lists under
"Strategy gaps" and the ones the CPU page admits: it attacks whoever is
softest rather than whoever is winning, points removal by printed size rather
than by what a permanent is doing, and never holds mana open on purpose.

The trainer exists ([ai-training.md](ai-training.md)): masked PPO over a
structured action space, a per-card embedding, a snapshot pool of opponents,
and an arena that reports win rates with confidence intervals. What it has
not been given is enough experience, and a whole-policy replacement of the
heuristic is a long road for a reward that arrives once per game.

**The shorter road: learn the judgements, keep the plan.** The strategy
hooks are already the seams where the CPU's judgement enters: `defender`,
`attack_value`, `block_value`, `priority_value`, `choose`, `junk_value`. Each
takes the agent's answer and returns the one to use. A learned model can sit
behind any of them, trained from the same environment, while the deck plan
goes on deciding what the deck is trying to do. Three models, in the order
they pay off:

1. **Threat.** Which seat is winning, and which permanent on the table is
   doing the most for its controller. Trained as a value head from self-play
   outcomes and from the outcome log the site will keep: the input is the
   observation the environment already encodes plus the card embeddings, the
   target is who went on to win. It feeds `defender` (attack the seat that is
   ahead, not the one that is low), the removal half of `priority_value`
   (point the Swords at the engine, not the biggest body), and the
   counterspell rule (hold it for the spell that matters).
2. **Tempo.** Whether to spend mana now or keep it up: a classifier over the
   same observation that predicts whether a held instant is used profitably
   before the CPU's next turn. This is the "hold mana open" gap, and it
   changes only the ordering `priority_value` returns.
3. **Combat.** `logic/fight.ts` and `board.could_block` model a fight one
   pair at a time; a learned block and attack valuation over the whole
   declaration is the piece the reflexive agent cannot do by rule.

Each model is a few hundred kilobytes and runs under the same mask, so the
CPU can never pick an illegal action and the structural guarantees of the
single seam are untouched. Each ships as a checkpoint the `policy` agent
already knows how to load, under the difficulty picker above.

**Where lookahead fits.** [ADR 0005](adr/0005-no-state-cloning.md) rules out
cloning in the engine; it does not rule out *replay* as a way to explore a
line offline. A search agent that forks the tape, replays, and scores the
result is affordable for generating training positions, where wall-clock
does not matter, and not for play, where it does. So the search exists to
teach the models, and the models play. This is the one place the no-cloning
decision is worth re-reading before work starts; it does not need amending.

**Measure it the way the repository already measures.** The arena with the
deck held fixed and only the pilot swapped is the sharp test; the threat
model's first gate is that the strategy CPU with it beats the strategy CPU
without it on every precon at a confidence the arena reports, and that the
draw rate does not move. Each of the strategy gaps in the debt page becomes
a seeded position in `tests/ai/strategy/` that the new pilot must get right.
The baseline heuristic stays the opponent `verify.py` gates on until a
checkpoint has beaten it across the board for long enough to be trusted.

## Matchmaking

### Brackets, derived from the list — **M**

The Commander Brackets, one to five, are defined by what a list contains:
Game Changers, mass land denial, chained extra turns, two-card infinite
combos, and tutors, with the thresholds per bracket set by the format's own
rules and revised by its stewards from time to time. Most of it can be read
off a deck at request time, beside the curve, so it cannot drift:

- a hand-kept `data/catalog/game_changers.json`, with the same discipline as
  `art_pins.json`: a named list, a test that every entry resolves in the
  catalog, and a note on where the list comes from;
- counts over the list for extra turns, tutors and land destruction, from
  oracle text and the engine's own vocabulary where a card is native;
- a hand-kept table of two-card combos, from the community's combo database,
  which the arena can go on to verify as the pairs become native.

The derived bracket is a suggestion, because the format defines a bracket as
a conversation, not a measurement, and an editorial `bracket` on a shipped
deck overrides it where the heuristic misreads a list. It is shown on the
tile and in the dossier, filters the shelf, and is what the queue below
matches on.

### A queue — **L**

**Shape.** `POST /api/queue {deck_id, pod_size}` and a long poll on the ticket,
the way pods already work ([ADR 0007](adr/0007-versioned-long-polling.md)).
The server forms a pod when it holds enough compatible tickets, returns the
pod code and a player token, and from there the existing lobby and deal run
unchanged: matchmaking creates pods, it does not replace them. Compatibility
is the deck's bracket within one step, widening as a ticket ages; a ticket
older than a threshold is dealt with CPU seats rather than left waiting. The
whole feature lives on the hosted site, since the desktop already goes there
for anyone who is not on the LAN.

**What it needs first:**

- persisted sessions and CPU takeover, because a stranger who leaves is the
  common case and a queue that produces dropped games teaches players not to
  use it;
- the outcome log, so the bracket thresholds can be tuned from games rather
  than guessed;
- an identity that outlives a pod only if anything is ever rated. Nothing in
  forming a pod needs one. A client-generated id in local storage is enough
  for "do not re-pair me with the seat that just left", and real accounts are
  a separate decision with an ADR of its own, taken only when ratings or a
  history are wanted.

**Scale.** A parked thread per waiting client is the long-poll's cost, and a
queue adds waiters. That is fine at the scale the site is for, and the day it
is not is the day a second worker and a shared store are needed, which is the
real reason the persisted-session work is sequenced first.

## Not planned

Named so that nobody re-litigates them by accident:

- **Colour accessibility** stays out of scope
  ([ADR 0006](adr/0006-no-colour-accessibility-requirement.md)).
- **A progressive web app** and **WebSockets** were each rejected with
  reasons ([ADR 0009](adr/0009-offline-first-desktop.md),
  [ADR 0007](adr/0007-versioned-long-polling.md)); the matchmaking item above
  is the first thing that could revisit the second, and only at a scale the
  site does not yet have.
- **Non-English cards.** The catalog is built from the English bundle on
  purpose ([card-catalog.md](card-catalog.md#why-default_cards)).
- **Undo in a multiplayer game.** Refused by design
  ([api.md](api.md#undo)); a take-back by consent is a different feature and
  nobody has asked for it.

## Suggested order

The dependencies, not the priorities, decide most of this:

1. **Persisted sessions** (the first step of zero-downtime deployments). It
   unblocks the handover deploy, CPU takeover, replays, matchmaking, and the
   Deck updating while a game is open. Gate `/debug` in the same week.
2. **The selection audit, then the unified selection model**, before the
   shelf and the list view add surfaces that would have to be unified later.
3. **The deck data model**: the featured tier, the archetype fallback for
   strategies, the sources manifest, the derived bracket. All of it before
   the first batch of decks, so that the hundredth deck costs what the
   thirteenth did.
4. **Decks and cards together**, in batches: import a batch, drive the card
   loop until every list is native, promote, repeat. The card roadmap is
   continuous and this is what orders it.
5. **The list view**, once there are lists worth looking at.
6. **Advanced CPUs**, starting with the threat model, as soon as the outcome
   log and replays give it positions to learn from; the difficulty picker
   can ship before any model does.
7. **Matchmaking**, last among the large items, because it depends on nearly
   everything above it.

Branding runs beside all of it and blocks none of it.
