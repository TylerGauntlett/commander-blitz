---
name: extend-roadmap
description: Take the next roadmap item off the backlog, or a named one, and ship it end to end — brief the person on what the item is and what the run will build, then ask the architecture questions the item leaves open before touching anything, branch from main, write the ADR first where the item asks for one, build the change through the seams the item names, add the gate it specifies, run scripts/verify.py, retire the item with scripts/roadmap.py --done, and open the pull request with /create-pr. Use when asked to work the roadmap, implement a planned feature, "do the next thing", or deliver a specific item id. The counterpart to /plan-feature.
---

# Delivering a feature

`/plan-feature` writes items into `docs/roadmap/`, each with effort, impact,
dependencies and a gate. This skill takes one off the queue and builds it, so
the backlog is worked in the order its own properties impose rather than the
order somebody remembers it in.

**One item per run, one pull request per item**, phased commits inside it when
the item is large. The deliverable is a merge-ready pull request whose gate is
the one the item named, and a backlog that no longer lists the item.

## Invocation

```
/extend-roadmap                 the top of the queue
/extend-roadmap art-store       a named item, which must be ready
/extend-roadmap every-import-native   one batch of a continuous item
```

## 0 · Preflight

```bash
git status --short                         # must be clean
python scripts/roadmap.py --check          # the backlog must be well formed
python scripts/roadmap.py --next           # the queue
```

A dirty tree stops the run. A failing `--check` means the backlog is broken
and that is the first thing to fix, through `/plan-feature`, in its own
commit, before any feature work.

## 1 · Pick the item, and refuse a blocked one

`--next` prints the ready items best first, then the blocked ones with what
blocks them. Take the top ready item, or the named one if it is ready. A named
item that is blocked is refused: say what blocks it and stop. Delivering a
blocked item means building on something that does not exist, and the
dependency was recorded precisely so nobody would.

The one override: the person asking says, in their own words, to deliver it
anyway. Then the blocker is delivered first, in this run, as its own pull
request, and the asked-for item follows on a branch from that one.

```bash
python scripts/roadmap.py --show <id>      # read the whole item
```

Read every document the item links. The item was written against the code as
it was; check each claim in **Today** against the code as it is now, because
a plan can go stale between planning and delivery. A claim that no longer
holds is a reason to re-plan, not to improvise: fix the item through
`/plan-feature` first, commit that, then continue.

## 2 · Brief the work, then ask the architecture questions

An item is a plan written before the work, and every plan leaves decisions
open that only the person who owns the project can close: which of two
shapes the data takes, how far the scope reaches, what the pull request may
and may not touch, what the ADR should decide. Find those **before** the
branch exists, not after the code does.

### The briefing comes first

A question is only answerable by someone who knows what it is about, and the
person who typed `/extend-roadmap` may not have read the item, or may have
named the top of the queue without knowing what is at the top. So before any
question, say plainly what this run is about to build, in one message of
prose and a short list, never a paste of the item:

- **The item**: its id and title, why it was picked (the top ready item, or
  the one named), and its effort, impact and whether it asks for an ADR.
- **The problem**: what is true today, from **Today**, in a sentence or
  two, as checked against the code in §1, including any claim that no
  longer holds.
- **The change**: what a player or contributor gets when it lands, and the
  steps from **The change** in the order you will build them, naming the
  seams (modules, routes, components) the work goes through.
- **The gate**: the tests that will hold it.
- **The shape of the run**: the branch it goes on, whether it is one pull
  request or several, what it will touch and what it deliberately will not,
  and which other skills it will call (`/plan-feature`, `/author-cards`,
  `/extend-dsl`, `/create-pr`).

Write it for someone who has never opened the item: a term the item coins
is explained, not assumed. Then the questions follow, in the same message or
straight after it, each pointing back at the part of the briefing it
decides, so every answer is given with the whole plan in view.

### The questions

Read the item's **The change** and **Gate** sections and the ADR it asks
for, and list every point where you would otherwise choose for the person:

- a storage or placement choice the item leaves open (a volume or an object
  store, a file per game or one database, a new route or a wider one);
- a scope line the item draws loosely ("and the smaller items in the same
  pass") that could double the pull request;
- an `L` that could ship as two pull requests, and whether they want the
  first merged before the second starts;
- a rule the work would bend, and whether the ADR amendment is theirs to
  approve;
- anything in **Today** that no longer matches the code, and whether to
  re-plan or proceed on the new facts.

Ask them all at once, in one message, each with the choice you would make
and why, so one answer settles the run. Use the harness's question tool
where it has one. Then wait. Do not scaffold, branch or write a line until
the answers are in; a run with nobody to answer stops here and says so,
because a feature built on a guess is a pull request that gets rewritten.
An item with genuinely nothing open still gets the briefing, says in one
line that nothing is open, and goes on.

Record the answers in the item itself, through `/plan-feature`, as the
first commit on the branch, so the plan the pull request was built from is
the plan the reviewer reads.

## 3 · Branch and start

```bash
git fetch origin main
git switch -c feat/<id> origin/main
python scripts/roadmap.py --start <id>
python scripts/roadmap.py --write
git add docs/roadmap docs/roadmap.md
git commit -m "docs(roadmap): start <id>"
```

Marking it in progress is what keeps a second run from taking the same item;
if §2 changed the item, commit that through `/plan-feature` first.
The branch type follows the item: `feat/` for something a player gets,
`fix/`, `perf/` or `build/` where the item is one of those, `chore/` for
tooling that reaches no player. `/create-pr` decides the title's type at the
end; the branch name only has to be honest.

## 4 · The ADR first, when the item says so

An item marked `adr: true` turns on a decision a later change could reverse
by accident. Write `docs/adr/<nnnn>-<slug>.md` before any code, in the shape
of its neighbours: context, the decision, consequences, what was rejected and
why. Add its line to the list in `docs/README.md`. Commit it on its own, so
the decision can be reviewed apart from its implementation.

The ADR records the decision the item proposes unless building it shows the
proposal wrong; then the ADR records what was learned and the item is
re-planned before continuing.

## 5 · Build it through the seams the item names

**The change** section is the plan: the shortest sequence of shippable steps,
the seams the work goes through, the rules it keeps. Follow it. Each step is
a commit, or several; a step that is itself shippable is a candidate for its
own pull request when the item is `L` and the person asking wants the branch
mergeable sooner.

Rules that hold throughout, all of them already the repository's:

- **The engine stays pure and the client simulates nothing**
  ([architecture.md](../../../docs/architecture.md)). A feature that needs
  the client to know a rule is a feature that needs the engine to offer an
  action.
- **Every legal action is one control, exactly once**
  ([ADR 0015](../../../docs/adr/0015-every-legal-action-is-one-control.md)),
  and the handheld floors are gates
  ([ADR 0013](../../../docs/adr/0013-handheld-floors-are-ci-gates.md)).
  A new surface ships with its story and its floor assertion.
- **Generated docs are regenerated, never edited**: the table in
  [AGENTS.md](../../../AGENTS.md) says which and with what.
- **Never reformat a file you did not otherwise change**, and never
  rewrite `constraints.txt` by hand.
- **Card and DSL work goes through its own skills.** An item that needs a
  card uses `/author-cards`; one that needs a mechanic uses `/extend-dsl`;
  a continuous card item is one `/import-moxfield` or one `/author-cards`
  batch, in the queue's order, and nothing more.

**A blocker found mid-build** is the common case and has one answer: stop,
write the blocker as its own item with `/plan-feature`, add it to this item's
`depends_on`, set this item back to `proposed`, commit that, and report. Do
not build around it, do not widen the pull request to include it, and do not
leave the branch half-done without the backlog saying why.

## 6 · The gate, as the item wrote it

**Gate** names the tests that hold the feature: a server test of a given
shape, a story per layout mode, an e2e spec. Write exactly those, where the
testing map in [testing.md](../../../docs/testing.md) puts them. A gate the
item named that turns out to be impossible as written is a reason to amend
the item (through `/plan-feature`, committed) with the gate that is possible,
never a reason to ship without one.

Then everything:

```bash
python scripts/verify.py                   # the whole gate, as CI runs it
python scripts/verify.py --e2e             # when a UI surface changed
```

Fix what fails. Never skip, weaken or quarantine a test to get green.

## 7 · Docs, then retire the item

The table "Which doc to touch" in [AGENTS.md](../../../AGENTS.md) says which
page carries each kind of change; update those, and delete any
[TECH_DEBT.md](../../../TECH_DEBT.md) entry the item closed. The docs carry
the result; the item does not become documentation.

```bash
python scripts/roadmap.py --done <id>      # deletes the item, unblocks its dependants
python scripts/roadmap.py --write
python scripts/roadmap.py --next           # say what became ready
git add docs/roadmap docs/roadmap.md
git commit -m "docs(roadmap): deliver <id>"
```

A **continuous** item is never `--done`: leave it on the page, say in the
pull request which batch this was, and if the batch changed what the item
should say next, amend it through `/plan-feature`.

## 8 · Open the pull request

Run `/create-pr`. The title's type decides whether the merge deploys and
releases ([ADR 0010](../../../docs/adr/0010-release-every-main-build.md)):
an item a player gets is `feat`, and a `docs:` title over code is the one
failure to avoid. The body's summary names the roadmap item by id and says
what the queue now has at its top; its details block carries the
`verify.py` result. Then watch CI to green and address review, as that skill
and the repository's PR rules expect.

## Hard rules

1. **Never deliver a blocked item** without the person's explicit word, and
   then only by delivering the blocker first.
2. **Never widen the pull request** beyond the item. Something discovered on
   the way is a new item.
3. **Never retire an item whose gate is not green**, and never retire a
   continuous one.
4. **Never edit `docs/roadmap.md` by hand**; `--write` after every change to
   an item.
5. **Everything the other skills forbid stays forbidden**: only `--collect`
   writes cards, one capability per `/extend-dsl` run, never push to a
   branch you did not create, never merge.
