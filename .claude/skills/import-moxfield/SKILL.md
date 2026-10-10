---
name: import-moxfield
description: Make every card in a Moxfield deck fully playable, end to end — branch from main, drive /author-cards and /extend-dsl until the deck's last card resolves native, test everything (unit, per-card, import pin, e2e where a UI surface changed), commit throughout, open the pull request, watch CI to green, and write the summary. Use when given a Moxfield deck link ("/import-moxfield https://moxfield.com/decks/..."), or asked to support, implement or fully cover a deck.
---

# Importing a Moxfield deck, to completion

`/author-cards` writes the cards the DSL can say. `/extend-dsl` builds one capability
that unblocks the cards it cannot. This skill is the loop around both, pointed at
one deck, and it does not stop while a card in that deck is still a proxy.

Every card, without exception. PRs #22, #28 and #29 are the precedent — 100/100,
91/91 and 83/83 — and #29 started at 30. "Difficult" is a reason for more
`/extend-dsl` runs, not a reason to leave a card out. The deliverable is a
merge-ready pull request with a green pipeline and a body somebody can read in two
minutes.

```
/import-moxfield https://moxfield.com/decks/Sr3op2p6G0m0Msv1n_jLZw
```

## Hard rules

1. **Everything the two skills forbid stays forbidden.** Only `--collect` writes
   cards, never invent an op, never weaken a gate, one capability per
   `/extend-dsl` run. Read both SKILL.md files before starting; this skill adds a
   loop, it does not relax anything inside it.
2. **One exception to `/extend-dsl` rule 4.** That skill stops at a capability
   needing a rules subsystem (planeswalkers, sagas, transform — see
   `docs/rules-coverage.md`). Here the deck is the deliverable, so build the
   subsystem — as its own sequence of one-capability runs, one commit each, and
   name it in the PR under its own heading. Still say so before starting it.
3. **Native, not `full`.** The finish line is the pin test's claim: every distinct
   card resolves `native` through `importer.import_deck`. A generated `full` proxy
   lives in gitignored `data/generated/` and ships nowhere.
4. **Commit as you go, never squash at the end.** One commit per authoring wave,
   per capability, per test file. The PR history is the review.
5. **Push only from step 9 onward**, only to the feature branch, never `--force`.
   Never merge the PR; that is the user's call.
6. **No card is "close enough".** A card that cannot be written exactly gets a gap
   record and then a capability; it never gets an approximation. A rejected card
   is the pipeline working.

## 0 · Preflight

```bash
git status --short                                   # must be clean
gh auth status                                       # must be logged in
ls data/catalog/cards.sqlite                         # else scripts/build_card_index.py
ls frontend/node_modules >/dev/null                  # else cd frontend && npm ci
```

A dirty tree stops the run: the branch has to be able to commit only its own work.

## 1 · Branch from latest main

```bash
git fetch origin main
git switch -c feat/<commander-slug>-deck-support origin/main
```

Slug from the commander's name (`feat/edgar-markov-deck-support`). If the branch
already exists the user is resuming: `git switch` to it and `git merge origin/main`
instead.

## 2 · Import, and take the baseline

```bash
python .claude/skills/import-moxfield/scripts/deck_status.py <url> --json <scratch>/before.json
python scripts/author_cards.py --report
```

The script runs the same `import_deck` a pasted link does and writes
`data/generated/` — which is what puts every card in this deck at the front of the
authoring queue as `wanted`. It prints the cards that are not yet `native`, each
with the importer's notes saying what was lost. Exit 1 means work remains.

Keep both outputs: the PR body is a delta against them. If the importer fails on
`unknown_cards`, the catalog is stale — `python scripts/build_card_index.py`, then
retry; a name that still fails is a real problem to report, not to skip.

## 3 · Author what the DSL can already say

Run `/author-cards` in **targeted mode** with every not-native name from step 2 —
`--card` is repeatable, so one invocation carries the list. Follow that skill's
loop exactly: templates tier first (free), then packets, then one worker per card
in waves of 6, then `--collect`, repair once, delete or gap what fails twice,
normalize the gap slugs, `report_gaps.py`, its gate, its commit.

Commit each wave as it lands:

```
author 5 cards for the <deck> deck (agent tier, wave 1)
```

Then re-run `deck_status.py`. Whatever remains is now a set of gap records naming
capabilities, and that set is step 4's work list.

## 4 · Build the capabilities, one at a time

```bash
python scripts/report_gaps.py --top 20
```

Rank the capabilities by **how many of this deck's cards they block**, then by the
catalog count `report_gaps.py` shows. For each, in that order:

1. `/extend-dsl <slug>` — one capability, its `tests/unit/<area>/test_<mechanic>.py`, its
   doc rows, its commit (`extend-dsl: <what it says, in words>`).
2. `/author-cards "<card>" "<card>"` for the cards that were waiting on it. Often a
   card waits on two capabilities; it comes back as a fresh gap naming the second
   one, and that is fine — it moves down the list, it does not get dropped.
3. `deck_status.py` again.

Two things #29 learned that save days here:

- **Most gaps are documentation gaps.** Before building, check whether the engine
  already has the field and the packet simply did not name it. Nine of that run's
  "missing capabilities" were fixed by deriving a list in `packet.py` from the
  model. The fix is in the packet, not the engine, and it is still its own commit.
- **A card with two faces is two cards' worth of work.** The worker brief covers
  `back_face`; a gap filed against a back face is as real as one against a front.

Loop 3 → 4 until `deck_status.py` exits 0. Do not start step 5 with a card
outstanding, and do not reach for the "Not done" paragraph in the PR template while
a capability remains buildable.

## 5 · Tests the gates cannot reach

`/extend-dsl` already wrote one unit test per capability. Three more layers:

**The import pin** — `tests/cards/test_<slug>_import.py`, modelled on
`tests/cards/test_lucy_maclean_import.py`. `deck_status.py <url> --pin-list` prints
the `DECK` tuple. It asserts the whole claim of the PR — total, distinct count,
zero `partial`, zero notes, `lands_inert == 0` — so a card dropping out of the pool
later fails here rather than in a game. Commit: `test: pin the <deck> import at
N/N native`.

**Per-card behaviour** — `tests/cards/test_<slug>_deck.py`, modelled on
`tests/cards/test_vivi_deck.py`. Gate 5 casts a card once in a fixed sandbox and
reads the board; it **never activates an ability** and **cannot assert a trigger
that never fires**. So one class per card whose printed sentence the gate could not
reach: activated abilities, triggers on later events, statics that change a later
spell's price, replacement effects. Assert the near miss too — the sentence that
would be wrong if the card were mis-written. #29's commander test found a real
engine bug this way. Commit per group of cards, and if a test finds a bug, fix it
in the same commit with the test that proves it and say so in the message.

**Frontend** — only for what the branch touched. A tier C decision kind gets its
`DECISION_PROMPTS` label and a vitest case; a tier D event gets `describeEvent` and
`beatsFor` cases in `frontend/src/**/*.test.ts`; a tier E field gets its component
test and `tests/server/test_*.py`.

**Playwright, deliberately narrow.** An e2e test costs minutes per run and the CI
runner draws ~11 fps under tracing, so the layer earns exactly one kind of test:
a *critical flow this branch changed* that no lower layer can see — a new decision
kind reaching `PromptDialog` and being answerable, a new event's beat rendering,
an import-screen change. Add a case to the closest existing spec
(`frontend/e2e/deck-import.spec.ts`, `full-game.spec.ts`) rather than a new file,
and run only that spec, **alone**, with nothing else on the machine:

```bash
cd frontend && npx playwright test e2e/<spec>.spec.ts --project=chromium
```

Engine-only branches (tier A/B, the common case) add **no** e2e test. The existing
three Playwright projects run in CI on every PR and are the e2e coverage for a
branch that changed no UI surface; a card behaving correctly is a Python fact and
is proven at the Python layer.

## 6 · Coverage

CI holds `src/commanderblitz` at 92% overall (`verify.py --coverage`), but a branch can
lower a file it created while the total still passes. So measure the files this
branch added or changed:

```bash
python -m pytest tests/unit tests/cards tests/server -q --cov=src/commanderblitz --cov-report=
python -m coverage report --include="$(git diff --name-only origin/main -- src | tr '\n' ',')"
```

Every changed `src/` file at **80% or better**, and every new file above the floor
it will be held to. Below that, the missing lines name the test to write — usually
the boundary or the wearing-off, not another happy path. For frontend files,
`cd frontend && npm run test:coverage -- --project=unit` and read the per-file
table the same way.

## 7 · Gate locally, the way CI will

```bash
python -m ruff check src scripts tests
python scripts/verify.py --verbose                        # the `verify` job, ~20 min
python scripts/verify.py --quick --coverage --no-frontend # the Python half of `verify-slow`
```

Plus, only if `frontend/` changed: `cd frontend && npm run build && npm run lint &&
npm test`, and the one spec from step 5 alone. Do not run the full `--e2e` locally
by default; that is what the PR's `verify-slow` job is for.

Any failure: fix, commit, re-run. Never push red.

## 8 · Re-pin what the branch moved

Adding a card is a change, and two pins say so on purpose:

```bash
COMMANDERBLITZ_UPDATE_GOLDEN=1 python -m pytest tests/cards/test_golden_pool.py   # pool hash + vocabulary
python scripts/build_card_index.py                                          # registry_images.json
```

Read each diff before committing it: `golden_vocabulary.json` should gain exactly
the ops and constants this branch added, and `registry_images.json` exactly the new
cards. Anything else moving means something else changed. Commit the pins on their
own: `re-pin the pool for N new cards`.

## 9 · Push and open the pull request

Follow `/create-pr`, using this title:

```
feat(cards): support every card in the <deck> deck (N/N)
```

Shorten the deck name if the title would go over 72 characters. The body is the same
template every PR uses, through `/create-pr`. `references/pr-body.md` lists only the
deck-specific facts and which section each one goes in. A `feat:` merge deploys the site and cuts a Steam Deck release, which is what a
newly playable deck should do.

## 10 · Watch the pipeline to green

Two jobs run on a PR: `scripts/verify.py` (~20 min) and `coverage floors and
Playwright` (~80 min, starts after the first). Watch in the background and poll:

```bash
gh pr checks <n> --watch --interval 120      # run_in_background; exits when all settle
gh pr checks <n>                              # one snapshot
gh run view <run-id> --log-failed | tail -200 # when one fails
```

On a failure, read the log before doing anything. Then:

- a real failure in this branch's work: fix, commit, push, watch again
- a CI-only Playwright failure: almost always a frame-timing assumption on the
  slow runner, not flake. Reproduce with traces before touching the test; see the
  memory on runner speed. Re-run with `gh run rerun <id> --failed` **at most
  once**, and only when the log shows a timeout unrelated to this diff.
- `main` moved underneath: `git merge origin/main`, re-run step 7, push

The step ends when `gh pr checks <n>` shows every non-skipped check `pass`. The
`build`, `deploy` and `release` jobs show `skipping` on a PR; that is correct.

## 11 · Summary

The PR body is the summary of record; the final message to the user is the short
form of it:

- the PR link and its check status
- deck cards native, before → after; registry size; catalog coverage
- capabilities built, each in one line, with the cards it unblocked
- tests added: unit files, per-card classes, the pin test, any e2e case
- bugs found by the tests, with the commit that fixed each
- changed-file coverage, and the full-suite number from the CI run
- anything not done, why, and what it would take — this list should be empty

## When something is off

| | |
|---|---|
| `import failed (unknown_cards)` | catalog is stale: `python scripts/build_card_index.py`, retry |
| `deck_status.py` shows `full` cards left | the templates tier takes proxies it already finishes: `/author-cards` them by name |
| the same gap keeps coming back under new slugs | step 7 of `/author-cards` — merge the slugs by hand, you are the only one who sees the whole wave |
| `--collect` rejects a card on gate 4 with an unpayable cost | add a prop to the sandbox, never relax the gate (see #28's eleven-card blast radius: make the prop conditional on the card's own cost) |
| a capability needs a rules subsystem | rule 2: say so, then build it as its own commit series |
| `verify-slow` red on a viewport project only | frame timing on the runner; reproduce with `--trace on`, do not loosen the assertion blindly |
| PR checks stay `pending` past 2 h | `gh run list --branch <branch>`; a superseded run was cancelled by the concurrency group, the newest SHA's run is the one to watch |
