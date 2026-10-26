---
name: plan-feature
description: Turn a feature idea into a roadmap item the backlog can rank and /extend-roadmap can build — one file under docs/roadmap/ with effort, impact, dependencies and the three sections (Today, The change, Gate) and the Decisions that answer its open questions, checked by scripts/roadmap.py. Use when asked to plan, propose, add, scope, split or re-rank a feature, to "put this on the roadmap", to answer an item's open questions, or when /extend-roadmap discovers a blocker that needs an item of its own. The counterpart to /extend-roadmap.
---

# Planning a feature

The roadmap is a backlog as data. Each item is one file, `docs/roadmap/<id>.md`,
with a front matter the script ranks on and three sections a person can argue
with. `scripts/roadmap.py` validates every item, derives the queue and
regenerates `docs/roadmap.md`. This skill writes an item; `/extend-roadmap`
takes one off the queue and builds it. Nothing here touches code.

**One item per run, and an item is a plan, not a wish.** It names what is true
today with the symbols that make it true, what would change and how, and the
test that would hold it. An item that cannot say what its gate is is not ready
to be ranked.

## Invocation

```
/plan-feature a spectator link for a game in progress        a sentence
/plan-feature <paragraph or pasted brief>                       a longer brief
/plan-feature split official-precons                            an L item that is really several
/plan-feature rerank                                            re-read the properties, nothing else
/plan-feature answer difficulty                                  record the owner's answers to its open questions
```

## 1 · Read what exists

```bash
python scripts/roadmap.py --next          # the queue, and what blocks what
cat docs/roadmap/_intro.md                # the rubric for effort and impact
ls docs/roadmap/                          # every item; read the nearest ones whole
```

Read [docs/README.md](../../../docs/README.md) and follow its "If you are here
to…" routes to the pages the feature touches. An item is grounded in the code
as it is: the module that owns the behaviour today, the ADR that decided it,
the test that holds it. Read [TECH_DEBT.md](../../../TECH_DEBT.md) too: a
feature that is really a debt item is filed there, and a feature that is
blocked by one names it.

**Is it already an item?** Search the titles and bodies before writing. An
idea that extends an existing item is a paragraph in that item, not a new
one. An idea the page lists under "Not planned" needs the ADR it cites
revisited, and that is a conversation to have before an item is written.

## 2 · Decide the properties, in this order

**Depends on.** The ids that have to land first, and only those: a real
dependency is one where the work cannot be built or cannot be tested without
the other item. "Nicer after" is not a dependency; say it in the body
instead. A dependency on something that is not yet an item means writing that
item first, in the same run.

**Effort.** `S` an afternoon, `M` a focused pull request, `L` a multi-PR
effort. An `L` that is really a sequence of independent `M`s should be
split now, each with its own gate, chained by `depends_on`; `/extend-roadmap`
works one pull request at a time and an `L` it cannot phase is an `L` it
cannot deliver. `--continuous` marks an item that is never done, only
advanced one batch at a time (the card roadmap is the example).

**Impact.** Who it reaches and how often. `high` touches every game or every
player of the site; `medium` touches a class of players or removes a weekly
annoyance; `low` is polish somebody would notice and nobody would miss. The
`--why` is one clause that says which, in words a person would check against
their own experience: "every game on the site is at risk on every shipping
merge", not "important".

**ADR.** `--adr` when the item turns on a decision a later change could
reverse by accident: where data lives, what is distributed, a rule the client
or the engine will be built around. `/extend-roadmap` writes the ADR before
the code when it is set.

## 3 · Scaffold, then write the sections

```bash
python scripts/roadmap.py --new <id> --title "<title>" --area <area> \
    --effort <S|M|L> --impact <high|medium|low> --why "<one clause>" \
    [--depends a,b] [--continuous] [--adr]
```

The id is kebab-case and is the file name forever; pick the noun, not the
verb (`art-store`, not `build-an-art-store`). The area is one of `site`,
`brand`, `cards`, `decks`, `play`, `steamdeck`, `cpus`, `matchmaking`.

Then fill the three sections. The script refuses a placeholder, an empty
section, or a section out of order.

- **Today.** What is true now, with the symbol that makes it true: the module,
  the ADR, the test, the constant. Say what the current design makes easy
  and what it makes hard. A reader should be able to open the files named and
  find each claim. No prescriptions here.
- **The change.** What would exist afterwards and how it would be built, as
  the shortest sequence of shippable steps. Name the seams the work goes
  through (`GameSession`, `strategy_for`, `DeckCatalog`) and the rules it must
  keep (an ADR by number). Say what it deliberately does not do. For an item
  with a dependency, say in one sentence why the dependency is real. For a
  continuous item, say what one batch is.
- **Gate.** The tests that would hold it, named by suite and shape: "a server
  test that…", "a story per layout mode under the floors", "the e2e spec
  that…". A gate is a thing `verify.py` runs, not a sentence about quality.

Then the two optional sections, which are what lets the autopilot build the
item unattended (`/extend-roadmap --auto`,
[ADR 0026](../../../docs/adr/0026-the-roadmap-autopilot-merges-on-green.md)):

- **Decisions.** Every architecture question **The change** leaves open, with
  the owner's answer: where data lives, how far the scope reaches, whether an
  `L` ships as one pull request or several, what the ADR decides, what the
  pull request must not touch. One bullet each, the question then the answer.
  An item with genuinely nothing open says so in one bullet; that is still a
  decision.
- **Open questions.** The questions still waiting, one bullet each with the
  choice you would make and why. Ask the person them now, the way
  `/extend-roadmap` §2 does, and move each answer into **Decisions**; what is
  left unanswered stays here. An item with this section is *awaiting
  decisions*: a person can build it, the autopilot cannot.

Only the person who owns the backlog answers a question. This skill writes
the questions and the recommendations, never the answers on its own.

**Answering** (`/plan-feature answer <id>`) is the same step on an item that
already exists: put its **Open questions** to the person, move each answer
into **Decisions**, delete **Open questions** once it is empty, and commit
with `docs(roadmap): decide <id>`.

Write the way the docs are written ([AGENTS.md](../../../AGENTS.md), "How the
docs are written"): rules over examples, symbols not line numbers, no counts
or dates unless the number *is* the target. Links are relative to
`docs/roadmap/` (`../client.md`, `../adr/0015-….md`, `../../TECH_DEBT.md`);
the script lifts them when it builds the page and refuses one that does not
resolve.

## 4 · Check, generate, commit

```bash
python scripts/roadmap.py --check          # every item, every link, the graph
python scripts/roadmap.py --write          # regenerate docs/roadmap.md
python scripts/roadmap.py --next           # where it landed in the queue
git add docs/roadmap docs/roadmap.md
git commit -m "docs(roadmap): plan <id>"
```

`--check` is also a stage of `scripts/verify.py`, so a malformed item fails the
gate; run it before committing rather than after. Say where the item landed in
the queue and what, if anything, it waits on. If it landed somewhere that
surprises you, the properties are wrong, not the script: re-read §2.

## Splitting and re-ranking

**Split** an `L` into items whose gates are independent: each gets its own
file, the later ones depend on the earlier, and the original either becomes
the first phase (keep its id, narrow its sections) or is retired with
`--drop` once every phase has a file. Never leave two items that promise the
same thing.

**Rank** is the one property that is a preference rather than a fact:
`rank: <n>` puts an item ahead of every unranked item of the same impact,
lowest rank first. The precon items carry it, written by
`python scripts/sync_precons.py --roadmap`, which re-ranks them on every run;
give another item a rank only when the person who owns the backlog asks for
that order.

**Rerank** touches only the front matter. Change a property only with the
reason in the commit message, and never change a dependency to make an item
ready sooner: a dependency is a fact about the build, not a preference about
the order.

## Hard rules

1. **Never edit `docs/roadmap.md`.** It is generated; `--check` fails on a hand
   edit.
2. **Never write code, a test or an ADR from this skill.** The item names them;
   `/extend-roadmap` writes them.
3. **Never retire an item here.** `--done` belongs to the pull request that
   delivers it; `--drop` is a decision for the person who owns the backlog,
   recorded in `_not-planned.md` if it was a real "no".
4. **Never invent a dependency to force an order**, and never omit one to jump
   the queue.
5. **One item per run.** A brief that is really three features is three runs,
   or one item plus a split.
