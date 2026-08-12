# Implementing cards, systematically

The engine plays a few hundred cards out of ~32,000. Everything else imports as
an inert *proxy* — right name, art, cost, types and keywords, with the rules text
doing nothing ([deck-import.md](deck-import.md)). That is honest, and it is not a
game: a real imported deck had 41 of its 100 cards doing nothing.

This is the loop that closes the gap without anybody hand-writing 32,000 files.

```bash
python scripts/author_cards.py --report                 # coverage, and what is blocking the rest
python scripts/author_cards.py --tier templates         # write everything the templates can
python scripts/author_cards.py --tier templates --dry-run --limit 200
python scripts/audit_cards.py                           # where the *hand-written* pool falls short
```

The last one is the newest and the least obvious: the gap this page is about is
not only between the engine and the 32,000 cards it has never seen. It is also
inside the pool the engine already plays. See
[Repairing a hand-written card](#repairing-a-hand-written-card).

## The thing that must not go wrong

**`compile_card` validates vocabulary, not meaning.** A generator can emit a card
whose oracle text says "draw two cards" and whose effect is `gain_life`. Every op
exists, every selector parses, it casts and resolves and lands in the graveyard
exactly as a sorcery should — and on the board it just quietly does the wrong
thing. Nothing says so.

`docs/card-dsl.md` is built around refusing to ship "a card that looks
implemented and does nothing". A card that looks implemented and does something
*subtly different* is worse, because the inert one at least fails visibly the
first time somebody counts on it.

So the centre of gravity is the **verifier**, not the generator. Generation is
cheap; trust is expensive.

## The six gates

`src/automtg/cards/authoring/verify.py`. All six, or the card is not written.

| | |
|---|---|
| 1. schema | the JSON is a `CardModel` |
| 2. compile | ops, selectors, triggers, keywords, static constraints |
| 3. residual | the printed text is **fully** represented — nothing left over |
| 4. playable | cast in a real position, resolves, ends in the right zone |
| 5. behaviour | a **non-empty** expectation that actually holds |
| 6. registry | the pool still loads, and it does not shadow a hand-written card |

**Gate 5 is the one that earns its keep.** It separates "the generator believes
this is Divination" from "the engine demonstrably drew two cards", which is why a
card and its expectation are authored together and rejected together. A card with
no expectation is not a verified card, so gate 5 refuses it.

Gate 3 is how a *partially* translated card is caught. Abilities carry the
printed sentence they implement in their `text`, and anything unclaimed is
leftover — the inert-proxy problem one sentence smaller.

Gate 6 exists because a naive merge lets an authored card **replace** a
hand-written one, and every deck referencing that id would silently change.

An expectation may assert `life`, `hand_size`, `library_size`, `graveyard_size`,
`counters`, `tokens`, `battlefield_count`, `opponent_battlefield_count`,
`granted` and `zone` — all things a person can read off a board and check against
the printed card by eye.

`zone` accepts a list when a card's destination is genuinely conditional: Dead
Weight's -2/-2 kills what it enchants, and state-based actions then correctly put
the Aura in the graveyard, so battlefield *and* graveyard are both the card
working. Pinning one would reject a card for behaving properly — and gate 4 makes
the same allowance, because the two harnesses have to agree or a card passes one
and fails the other for the same behaviour.

## What to work on next

`authoring/queue.py`. Order is the most consequential thing in the package,
because there are 32,000 cards and finite effort. Alphabetical spends the first
thousand units of work on cards nobody has played.

1. **Cards from a deck somebody imported** — read from `data/generated/`. Someone
   put those in a real list and then watched them do nothing.
2. **EDHREC rank** — Sol Ring, Command Tower, Arcane Signet. Cards it does not
   rank sort last rather than being dropped.

The queue also records **why** each card failed, which is half its value: "400
cards need a union selector" is a roadmap, and `--report` prints it.

## The tiers

**Templates** (`authoring/templates.py`) — deterministic, exact, free. Magic's
text is templated, and the residual is dominated by a few shapes. Some of it the
DSL has always been able to say; `proxy.py` simply never translated prose into
ops.

Two rules keep it honest. **All or nothing**: a card is produced only when every
residual line is consumed. **Every template carries its own assertion**: a
template knows what its effect does, so it emits the expectation too, and one
that cannot say what to observe does not belong here.

It also takes cards the proxy *already* finishes — a vanilla creature, a plain
dual, a Signet. Those need no translation and are complete; leaving them to be
regenerated as inert proxies for every deck was worth 6× the yield.

**Engine mechanics** — the measured blockers, each unlocking hundreds of cards
for one piece of work. `--report` ranks them by how many cards they hold up.

*Auras and Equipment are done* — the largest block in the catalog at ~1,700
cards, and most of the object model already existed (`attached_to`, the `attach`
op, `CardDef.is_aura`, SBA unattachment). Two things were missing:

- **An Aura enters attached to what its spell targeted.** It has to happen after
  the permanent is placed, because `move_object` calls `reset_permanent_state` on
  the way onto the battlefield and that clears `attached_to` — so an Aura
  attaching itself with the `attach` op arrives enchanting nothing and is binned
  by state-based actions a moment later.
- **A static that reads "the thing I'm attached to"** — `{"attached": true}` in a
  static's `affects`. Checked before `controller` and short-circuiting it,
  because an Aura stapled to an opponent's creature still affects that creature.

Equipment needed no new engine work at all: `Equip {2}` is a sorcery-speed
activated ability whose effect is the existing `attach` op.

Then the sentences those cards actually say, which is where the second batch of
work went — an Equipment that *grants* rather than buffs, and the very common
"gets +1/+2 **and** has vigilance", which is one printed sentence and two
abilities. Without those the all-or-nothing rule kept throwing the cards away
even though the mechanic worked.

*Fetchlands and creature-lands are done* — the two shapes behind the import
report's "some of your lands do nothing" line. They came apart very differently:

- **Fetchlands needed no engine work whatsoever.** `Cost` has always carried
  `tap`, `pay_life` and `sacrifice`, and `search_library` has always taken a
  selector, a `tapped` flag and shuffled on its own. What was missing was a
  template that reads `<cost>: <effect>` at all — every template before this one
  handled bare sentences. `_activation_cost` is deliberately strict: an
  unrecognised clause fails the whole card, because a clause dropped silently
  makes a *cheaper* land than the printed one.
- **Creature-lands needed a new continuous effect**, `animate` — see
  [card-dsl.md](card-dsl.md). `TempEffect` knew pumps and keywords but nothing
  that changes a card's *type* for a turn.

Both are anchored end-to-end on purpose, and what they refuse is as important as
what they take: Fabled Passage's "Then if you control four or more lands, untap
that land" and Raging Ravine's quoted `"Whenever this creature attacks…"` both
fail, so those cards stay honestly unimplemented rather than quietly wrong. 46
cards fell out of the top 12,000 for two sentence patterns.

Three more keywords turned out to need no engine work at all:

- **Devoid** is self-implementing — the catalog already reports the card as
  colourless, so the generated card is already right and the line is consumed
  with nothing built.
- **Changeling** is the existing `add_subtype` static.
- **Prowess** is a `spell_cast` trigger filtered to noncreature spells, which
  the DSL has always been able to say.

*Cycling is done* — 44 cards in one harvest, every cycling land in the catalog.
It needed two things that only work together: `active_zones` honoured on an
*activated* ability, so legality offers it from your hand, and a `discard_self`
cost, because `discard: 1` lets the player pitch something else and keep the
card. The loader now refuses one without the other — an ability activated from
hand whose cost does not remove it from hand is an infinite engine. Typecycling
and "when you cycle this card" are deliberately still refused; see
[card-dsl.md](card-dsl.md).

*The Aesi precon is done, and it is the best evidence this loop has.* The deck
shipped here was never the precon -- it was a hand-curated Simic list built
around what the engine could already say, with five substitutions and five
*invented* cards wearing real cards' ids. Importing the real thing, Commander
Legends' **Reap the Tides**, resolved 100 cards with 19 simplified.

Getting those 19 to zero took fourteen capabilities, and the shape of the work is
the argument for driving the pipeline from a deck somebody else built:

| | |
|---|---|
| Needed no engine work at all | Meteor Golem, Sphinx of Uthuun, Peel from Reality, Verdant Sun's Avatar, Whelming Wave, Scourge of Fleets |
| Needed no engine work *once the packet stopped lying* | Sharktocrab, Compulsive Research |
| Keywords and selectors | `shroud`, `any_types`, `any_of`, landwalk, `not_keywords` on statics |
| Costs | `may.pay`, `return_to_hand`, `evoke`, `emerge` |
| Rules seams | `block_restriction`, `must_attack`, `cant_attack`, untap-on-another-turn, stack triggers, the `kicked` lifetime |

**Three cards were filed as blocked on mechanics that already existed**, and all
three for the same reason: the work packet under-reported the language. It listed
ops, keywords and trigger events, and omitted conditions, value expressions, the
effect-side selector keys, and nine of the fourteen static effects. A worker sees
only its packet, so an omission there reads as an absence -- and a gap record is
read as a build order, so it buys engine work for something that already ships.
Every one of those lists is now derived from what the loader enforces, pinned by
`tests/cards/test_authoring.py`. That is the single highest-leverage fix in the
whole run.

The same failure recurred twice more while the Edgar precon was being finished,
and both times the packet was again the cause rather than the engine:

- **`cost_keys` was missing entirely.** A worker shown `ops` but never the cost
  vocabulary cannot tell a cost from an effect, so every "`<cost>`: `<effect>`"
  card either guesses or files a gap for a cost that already ships. Captivating
  Vampire's new `tap_permanents` would have been unreachable the day it landed.
- **`static_condition_keys` was missing.** A static's "as long as…" clause is a
  *third* language, neither `condition_keys` nor `static_filter_keys`, and a
  worker shown neither in its place has no way to know a static can be
  conditional at all.

Both are now derived from what the loader enforces and pinned by the same test.
The pattern is worth naming: **when a worker files a gap, suspect the packet
before the engine.**

*The Edgar Markov precon is done too, and it is the sharper lesson of the two.*
It shipped with **seven** substitutions — cards whose text the DSL could not say,
each replaced by something in the same colours and each recorded in the deck
file. Clearing them took six capabilities, and the first thing the run found was
that three of the seven needed **nothing at all**:

| | |
|---|---|
| Needed no engine work | Mortify, Bedevil, Anguished Unmaking — `any_types` and `any_of` had shipped for other cards, and nothing re-read the note that said they could not be written |
| Ops and a cost | `gain_control`, the `add_subtype` **op** (distinct from the static of the same name), and a `tap_permanents` cost — all three for Captivating Vampire alone |
| Selectors that describe one object relative to another | `shares_a_type_with`, `exclude_binding` — Shared Animosity |
| A static condition, and a static that changes no rule | `top_of_library` and `reveal_library_top` — Vampire Nocturnus |
| A subsystem `rules-coverage.md` had listed as absent | transforming cards, plus "activate only if…" — Bloodline Keeper |

**A substitution is a claim about the engine, written down once and never
re-checked.** That is what `--check-substitutions` is for, and three stale swaps
in one deck is the argument for running it rather than trusting the note.

The transform work is worth reading for the opposite reason: it was listed as a
missing *subsystem* and turned out to be one boolean and one branch, because
`GameState.card_of` is a single choke point every reader of a card goes through.
"Not implemented" in a coverage doc is a measurement of what was tried, not of
what is hard.

Still outstanding: **Crew** (74), **Convoke** (39), **Ward** (41), and
**modal spells** (153).

Modal is the one that looks cheap and is not. `choose_mode` exists, but modes are
chosen *on resolution* while targets are chosen *at cast*, and a card whose first
mode targets a creature and whose second targets a player has nowhere to put
that. It needs engine work, not a template.

**The agent** (`authoring/packet.py`) — the long tail, one self-contained work
packet per card:

```bash
python scripts/author_cards.py --tier agent --limit 20   # hand out work
python scripts/author_cards.py --tier agent --card "Rhystic Study"   # or one by name
# ...answers land in data/authoring/answers/<card_id>.json
python scripts/author_cards.py --collect                 # verify, commit survivors
```

A reader that *cannot* express a card must not approximate it. It writes a **gap
record** to `data/authoring/gaps/<card_id>.json` instead — the missing capability,
named, with the reason the existing vocabulary falls short. `scripts/report_gaps.py`
collapses those into [unsupported-cards.md](unsupported-cards.md), ranked by how
many cards each one blocks. One refusal is an anecdote; seventy cards waiting on
cycling is a build order.

### Driving it

Two Claude Code skills wrap this loop end to end (`.claude/skills/`):

- **`/author-cards`** — runs the free template tier, hands the residual to one
  concurrent worker per card, collects through the six gates, verifies and commits.
  `/author-cards 100` for bulk, `/author-cards "Rhystic Study"` when a specific card
  is needed now.
- **`/extend-dsl`** — takes one capability off the gap report and builds it: the op
  or continuous effect, its unit test, the docs, and any UI work. Then re-runs the
  template tier to harvest the cards it unblocked.

The division is the same one this document already draws. `/author-cards` never
touches `src/automtg/engine/`; it measures what it cannot do and hands that to
`/extend-dsl`.

A packet is deliberately a **file format** rather than an API call, because the
same packet has to serve a Claude Code session with a person watching *and* an
unattended worker running 10,000 cards. Both read the same JSON and write the
same `{"card": ..., "expectation": ...}`, so the API worker costs no rework once
the session has proved the loop.

It is self-contained — oracle text, what the free tiers already worked out, the
sentences still outstanding, why the template tier gave up, the whole DSL
vocabulary, and worked examples from cards already in the pool. Nothing assumes
the reader has the repository open, because the API worker does not.

### What the gates actually caught, authoring by hand

Both of the first two answers were wrong, and both were mine:

- **Swiftfoot Boots** — I asserted a creature would have haste. Equip is a
  separate sorcery-speed activation the sandbox never performs, so nothing was
  equipped. The card was right; the claim was not.
- **Heroic Intervention** — I asserted 2 permanents would gain the keywords. It
  is "*Permanents* you control", so the answer was 32.

And chasing the second one found a **bug in the harness**: `drive` was walking
the sandbox through combat and into the next turn, crossing the cleanup step —
which wipes every until-end-of-turn effect. Every pump spell and keyword grant
was being measured *after the thing it did had worn off*, so gate 5 passed them
regardless of what they did. That is the exact failure this harness exists to
catch, hiding inside the harness. `drive` now stops at priority, at combat, and
at the turn boundary.

## Where the output lives

```
data/cards/auto/
├── templates.cards.json   the definitions
├── expectations.json      card_id -> the observable outcome that was checked
└── README.md
data/authoring/queue.json  what is done, what failed, and why
```

Committed and first-class: loaded by `default_registry()`, playable by the
server, the trainer and the arena. `tests/cards/test_auto_cards.py` re-runs every
gate over all of them on every test run — a card was accepted because it passed
six gates *at the time*, and an engine change months later can quietly invalidate
that.

**An authored card supersedes its own proxy.** Once a card is implemented, the
stale proxy in somebody's `data/generated/` pool is dropped rather than merged —
the deck goes on referencing the same id and silently picks up the real rules.
Without that the server stops booting the first time the pipeline implements a
card sitting in an imported deck, which is exactly what happened on
`simic_guildgate` the moment 280 cards landed.

## Promoting one to hand-written

Move the object into a file in `data/cards/`, delete it from `auto/`, delete its
expectation. Do that when a card needs nuance the pipeline cannot express but a
person can.

A promoted card joins a pool that is now audited, so it has to record the printed
text verbatim and give each ability the printed line it implements — see
`docs/card-dsl.md`. `tests/cards/test_hand_written_cards.py` will run all six
gates over it like any other.

## Repairing a hand-written card

The reverse direction, and the one the audit exists for.

`data/cards/` predates this pipeline. Those cards never cleared a gate, and two
of the six could not even be asked: while `oracle_text` was a human summary
written *after* whatever was skipped, the residual gate compared a card to a
description of itself. Krosan Tusker recorded `"A large boar."` and shipped with
no cycling; Anticipate is implemented as Preordain.

```bash
python scripts/audit_cards.py                     # what falls short, and how
python scripts/audit_cards.py --check-substitutions  # deck swaps now unnecessary
```

Two things had to change before such a card could be repaired at all, because
**every other part of this package reads "in the registry" as "done"**:

- `Queue.refresh` never queues a card the engine already plays, and
  `author_cards.select` refuses one asked for by name. Both are right about cards
  that are simply *missing*. `--open-deficits` writes a queue entry with
  `gate="fidelity"`, which both now treat as workable — and `_priority` puts them
  ahead of everything else, because a card quietly doing less than it prints in a
  deck somebody is playing is worse than a card that does nothing and says so.
- Gate 6 rejects any card whose id is already in the pool, so every answer for a
  precon card came back `'krosan_tusker' is already in the pool`.
  `--collect --supersede` stands that gate down for an answer that *replaces* an
  incumbent, and deletes the incumbent from `data/cards/`. Deleting is not
  optional: `authored_card_paths()` returns hand-written files before `auto/` and
  `CardRegistry.by_name` is first-wins, so a corrected card left behind its
  predecessor never reaches a game.

```bash
/author-cards "Adanto Vanguard"                   # packet, worker, answer
python scripts/author_cards.py --collect --supersede
python scripts/audit_cards.py --update-baseline   # the list only shrinks
```

`--supersede` is needed exactly once per card, for the handover: afterwards the
card lives in `auto/` and an ordinary `--collect` re-verifies it like any other.
It stays behind a flag so a routine run can never rewrite `data/cards/`.

Most of what the audit finds is not a card-authoring job at all. The precon
shortcuts cluster on mechanics the engine does not have — cycling, flashback,
evolve, threshold, ascend, investigate, skulk, intimidate — so a worker
will correctly refuse them and write a gap record, and they surface through
`scripts/report_gaps.py` as `/extend-dsl` work.

`--open-deficits` also **closes** entries whose deficit is gone, which matters
more than it sounds: a queue entry left `pending` after the card was repaired
makes `--report` claim work that does not exist, and the whole point of the
queue is that its ordering is trusted.
