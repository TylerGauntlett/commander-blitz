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
```

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

Three more keywords turned out to need no engine work at all:

- **Devoid** is self-implementing — the catalog already reports the card as
  colourless, so the generated card is already right and the line is consumed
  with nothing built.
- **Changeling** is the existing `add_subtype` static.
- **Prowess** is a `spell_cast` trigger filtered to noncreature spells, which
  the DSL has always been able to say.

Still outstanding: **Cycling** (71), **Crew** (74), **Flashback** (75),
**Kicker**, **Convoke** (39), **Ward** (41), and **modal spells** (153).

Modal is the one that looks cheap and is not. `choose_mode` exists, but modes are
chosen *on resolution* while targets are chosen *at cast*, and a card whose first
mode targets a creature and whose second targets a player has nowhere to put
that. It needs engine work, not a template.

**The agent** (`authoring/packet.py`) — the long tail, one self-contained work
packet per card:

```bash
python scripts/author_cards.py --tier agent --limit 20   # hand out work
# ...answers land in data/authoring/answers/<card_id>.json
python scripts/author_cards.py --collect                 # verify, commit survivors
```

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
