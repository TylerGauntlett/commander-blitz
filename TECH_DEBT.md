# Tech Debt Audit

**Commit audited:** `7ee6e8a0` (`origin/main`)
**Date:** 2026-09-04
**Scope:** audit only — no source file was modified.
**Supersedes:** the 2026-08-25 audit of `0161573`. Every finding below was re-measured
against `7ee6e8a0`; a finding's original ID is kept so the two reports can be read
side by side.

Every line number below is true *at this commit*. Evidence cells are re-derivable by
running one command or opening one `file:line`.

## What changed between the two audits

107 commits landed on `main` between `0161573` and `7ee6e8a0` (976 files, +236k lines;
53 of them `extend-dsl`, so most of the volume is card data and DSL work). Five are the
ones this report cares about, because they closed findings from the first audit:

| PR / commit | What it closed |
|---|---|
| #15 `6797c35c` — *Back out of one thing, reach the commander, and deal the rematch* | `FB-01`, `FB-14`, plus the 16 mid-audit working-tree edits the first report could not attribute (they were this PR in flight) |
| #16 `318e73c7` — *Every game was dealt from seed zero* | `FB-05` |
| #17 `552f9dba` — *The ring is drawn around the stop, so the stop is what has to move* | `FB-03`, `FB-07` |
| #18 `f1c0f21d` — *fixed buttons* | `FB-11`, `FB-09` |
| #19 `6070e254` — *Streamline the core controller journeys* | `CG-03` narrowed (handheld stories 22 → 35 tests), new press-budget gates, `X` became the commit shortcut |

Also relevant: `4ea7521a` wrote `tests/unit/test_determinism_hygiene.py`, which three
files already cited as existing (it did not — the first audit missed that);
`docs/testing.md` had its frontend counts corrected (its Python counts were not);
`frontend/tests/zzrepro*.test.tsx` (`LP-01`) are gone.

The last 21 of the 107 commits (PRs #22 and #25, all card and DSL work) closed no
finding and touched one frontend file. They are why the Python numbers below differ
from a draft of this report taken five days ago at `6ac90652`, and why the frontend
numbers do not: engine coverage, suite counts and file sizes all moved, while every
frontend percentage held to within a tenth of a point.

## Remediation status (2026-09-05, branch `tech-debt`)

Every open finding below was worked on this branch as a **refactor plus coverage
effort with no behaviour change**: no defect was fixed, no visual moved, no API
answered differently. Where a finding was a bug it was pinned as a known-failing
test instead. The oracles for "nothing changed" are `tests/cards/test_golden_pool.py`
(a hash over all 2,622 compiled cards and the op registry, pinned before the first
split and unchanged after the last), the DOM-shape snapshots in
`frontend/tests/tableShape.test.tsx` (every `data-testid`/`data-stop`/`data-action-id`
the table and panel render, across ten positions and both layouts), and the seeded
arena's tables.

| ID | Status | What was done |
|---|---|---|
| FT-03 | **RESOLVED** | `acceptance.spec.ts` asserts the slab's real class and stop, and stages an attacker instead of looking for a kind the panel never emits. |
| FT-04 | **OPEN, annotated** | The band still drifts ~22px. It is a layout change and out of scope; the test carries `test.fail()` so the suite reports it as a known failure and turns red the day the layout is fixed. |
| FT-05 / FT-06 | **RESOLVED** | Every budget scales by `E2E_SLOW` (`verify.py --e2e` sets 2); the opening-hand helper polls instead of sleeping; the 54 symbol images are awaited on `decode()`. `verify.py --e2e` sorts failures into timed-out vs assertion from the JSON report. |
| CG-01 | **RESOLVED** | An offline seed search found `edgar` seed 7 reaches attackers, blockers and a two-defender attack; `reachDeclaration` throws instead of skipping. 0 skipped where 14 were, in action-panel and cycle3. |
| CG-02 | **RESOLVED** | Jsdom tests for every module under 20%: CardHold, GroupDial, OpponentBoard, ControllerPanel, InviteDialog, StackPanel, EventTicker, CardGhost, the fx scheduler and actuators, the API client, sfx, four more routing cases. Merged coverage (unit + both story projects in one process) is **88.5%** statements, floors held per file in `vite.config.ts`. `NewGameScreen.tsx` had no importer and is deleted. |
| CG-03 | **RESOLVED** | 22 of 38 story files carry a `handheld` case (was 7). One new finding: `GameOverScreen`'s subtitle is 14px on the compact layout, under the 16px floor -- recorded in the story, not fixed. |
| CG-04 | **RESOLVED** | `verify.py --coverage` and `npm run test:coverage`; a PR-only CI job (`verify-slow`) runs them with the Playwright projects. |
| CG-05 | **RESOLVED** | `tests/cards/test_authoring_tools.py`: fidelity, packet, queue and templates. |
| CG-06 | **RESOLVED** | `tests/unit/test_ops_mana.py` (all three ops and the chosen-colour helper), plus `values.py`'s refusals and `rng.py`'s round trip. |
| OF-01 | **RESOLVED for the eight named files** | `loader.py` 5,464 → a package of seven modules (largest 1,981); `ops_board.py` 2,110 → four op modules + helpers; `characteristics` 2,146 → 1,483 + `player_statics`; `primitives` 1,890 → 1,379 + `temp_effects`; `legality` 1,791 → 825 + `casting`; `costs` 1,631 → 1,320 + `cost_reduction`; `Table.tsx` 2,030 → 1,286 + six hooks and two children; `ActionPanel.tsx` 1,367 → 640 + seven components. Every move is verbatim with a re-export; every import site in the repo is unchanged. |
| DC-01 | **RESOLVED** | All 19 deleted. |
| SD-01 | **RESOLVED** | `scripts/test_counts.py --write` rewrites the table from the runners; `verify.py` prints `--check`'s verdict as an informational line. |
| SD-02 | **RESOLVED** | `.dockerignore` no longer names `legacy-frontend`. |
| LP-01 | already resolved | -- |
| LP-02 | **RESOLVED** | `GroupDial.tsx`'s header describes the shipped control; six tests and a handheld story. |
| LP-03 | **RESOLVED as a comment, OPEN as a design** | `OpponentBoard.tsx`'s header says what it is (the R2 reader) rather than "temporary"; the missing modal root is pinned as a known-failing test (`it.fails`, named LP-03). Making it a modal is a behaviour change and was not done. |
| LS-01 | **RESOLVED** | The one biome warning carries the `biome-ignore` its comment already justified. 0 warnings. |
| LS-02 | **RESOLVED** | `verify.py` no longer doubles pytest's `-q`. |
| NF-01 | **RESOLVED** | `frontend/tests/setup.ts` stubs canvas, `ResizeObserver` and `requestAnimationFrame`; the unit run prints no stack traces and reports 0 unhandled errors. |
| UV-05 | **RESOLVED** | The arena stage is labelled with what it plays (60 duels + 60 pods), in `verify.py`, `docs/testing.md` and the workflow. |
| UV-08 | **RESOLVED** | The class-scoped fixture is a classmethod. |
| mockups/ | **RESOLVED** | Deleted (108 MB). The rounds' findings and every number the code cited live in `docs/design-record.md`; the 82 citations point there; `docs/mockup-fidelity.md` is retired into its final section. |
| FB-02, FB-08, FB-12, FB-13 | **OPEN by decision** | Code defects, not fixed on a refactor branch. FB-13 is pinned as a known-failing case in `commandZone.test.tsx`; the others are documented at their code. |
| FB-04, FB-06, FB-10 | **CLOSED -- environment** | Reproduced only under a non-standard Steam Input controller template; not app defects. |
| X-button feature | **OPEN** | Out of scope. |

### Re-measured at the branch tip

`python scripts/verify.py --coverage --e2e --verbose` (the full gate plus both
opt-in flags), with the frontend half re-run once after a teardown fix. Column
three is the audit's number at `7ee6e8a0` for comparison.

| Stage | At the branch tip | At `7ee6e8a0` |
|---|---|---|
| lint (ruff) | **pass** | pass |
| card files and deck legality | **pass** — 2622 cards (51 tokens) | pass |
| card index is current | **pass** | pass |
| `tests/unit` | **4630 passed** in 118s | 4581 |
| `tests/cards` | **6610 passed, 4248 skipped** in 804s (under coverage) | 6562 / 4248 |
| `tests/server` | **303 passed** | 303 |
| `tests/ai` | **75 passed** | 75 |
| Python coverage floor (92) | **94%** — 16791 statements, 1065 missed, one number over all four suites | 92% / 16702 / 1340 (measured by hand) |
| arena: 60 duels + 60 pods | **pass** — win/draw/seat tables **byte-identical** to the capture taken before the first engine split | pass |
| live server: 2p, 4p, one pod | **pass** in 6.3s | pass |
| frontend build | **pass** | pass |
| frontend lint | **pass** — 305 files, **0 warnings** | 1 warning |
| frontend tests + stories, one process | **1836 passed** (130 files, 18 story files skipped by tag), **0 unhandled errors**, **88.6%** statements with every per-file floor held | 1277 unit / 381 + 35 stories; 68.3% unit-only, never gated |
| Playwright `chromium` | **121 passed, 3 skipped, 0 failed** in 13.4m; the band-drift case reports as an expected failure | 3 failed, 14 skipped, 107 passed in 24.5m |
| Playwright `handheld` | **24 passed** in 3.3m | 1 failed (timeout), 23 passed in 5.2m |
| Playwright `deckfit` | **8 passed** in 1.9m | 8 passed |
| `docs/testing.md` counts | **current** (`scripts/test_counts.py --check`) | four rows stale |

The three chromium skips are not the combat class this audit was about: two are
`playtest.spec.ts`'s screenshot captures, which skip unless asked for, and one is
`cycle3.spec.ts:233`, which needs a card-choosing prompt to come up on `aesi` seed 7
and reports so. Every `reachDecision` gate is gone.

Sizes after the splits (lines): `loader/__init__.py` 1956, `loader/effects.py` 1485,
`characteristics.py` 1483, `primitives.py` 1379, `costs.py` 1320, `Table.tsx` 1273,
`casting.py` 1019, `legality.py` 825, `player_statics.py` 694, `loader/vocabulary.py`
656, `ActionPanel.tsx` 636, `ops_removal.py` 597, `ops_combat_flags.py` 577,
`ops_counters.py` 565, `temp_effects.py` 522. Nothing over 2,000 remains.

**Left undone, on purpose.** The plan's optional second step for the loader — turning
`_validate_effect`'s ~65 `if op == …:` guards into a dispatch table — was not taken:
the golden pool only pins cards that load, so nothing would have pinned the error
messages invalid cards get, and changing those unpinned is not a pure move.

## The riskiest areas

**1. Combat's e2e coverage is still an illusion — and the one combat test that does run
still fails.** `acceptance.spec.ts:132` still asserts `/btn--primary/` against a button
whose class has been `commit` since before the first audit (`FT-03`), and every
attacker/blocker case in `action-panel.spec.ts` is still gated behind
`test.skip(!(await reachDecision(page, "attackers")))` on fixed seeds, so it skips
identically on every run (`CG-01`). What *has* changed: `journeys-handheld.spec.ts`
(new in #19) reaches attack and block declarations against the live engine, so combat
is no longer entirely unexercised end-to-end — it is exercised by a different file than
the one that claims to.

**2. The controller / focus layer is much better tested than it was, but its remaining
defects are exactly the ones nothing tests.** Of the fourteen field defects, seven are
now fixed with a regression test each (`FB-01`, `FB-03`, `FB-05`, `FB-07`, `FB-09`,
`FB-11`, `FB-14`). The seven still open (`FB-02`, `FB-04`, `FB-06`, `FB-08`, `FB-10`,
`FB-12`, `FB-13`) are all, without exception, in code that no test reaches: `CardHold.tsx`
sits at **17%** unit coverage, `GroupDial.tsx` at **6%**, `OpponentBoard.tsx` at
**14%**, and the commander-ready recompute in `CommandZone.tsx` is untouched since
the first audit. Frontend coverage exists now (`CG-04`, **68.3%** of `src/`), so for the
first time the gap is a number rather than a grep.

**3. The e2e suite's verdict is not reproducible, so nobody can tell a regression from
a busy afternoon.** Running the same unchanged commit twice produced three different
timeout failures across two Playwright projects and one Storybook project, and no two
runs agreed on which test failed (`FT-06`). Every one passed when re-run alone. The
two genuine assertion failures reproduced exactly, both times, which is the only reason
they can be told apart — and that separation took four extra runs to establish rather
than being something the suite reports about itself. A gate that fails differently on
each run trains people to re-run it, and re-running is how `FT-03` survives eleven days
with an assertion that has been wrong the whole time.

**4. `loader.py` grew by 1,812 lines in ten days.** `src/automtg/cards/loader.py` went
from 3,652 to **5,464** lines between the audits — a 50% increase in the largest file
in the repository, with no per-module coverage floor. The 53 `extend-dsl` commits in
the window land here, and four more files are following it: `characteristics.py`
(+563), `ops_board.py` (+491), `primitives.py` (+420) and `legality.py` (+372).
`OF-01` is the finding getting worse fastest, and it is getting worse by design —
the card pipeline's whole cadence writes into these five files.

## Disclosure: the only repo change made

This branch carries one dev dependency, installed for the first audit so frontend
coverage could be measured rather than guessed, and still the only thing it changes:

```
cd frontend && npm i -D @vitest/coverage-v8@3.2.7
```

Diff — `frontend/package.json` (+1 line), `frontend/package-lock.json` (+702 lines):

```
+    "@vitest/coverage-v8": "^3.2.7",
```

The unpinned form (`@vitest/coverage-v8`) **fails to install**: it resolves to 4.1.11,
whose peer is `vitest@4.1.11`, while this project pins `vitest@^3.2.7`. Pinning to
3.2.7 installs cleanly. The rebase onto `7ee6e8a0` was conflict-free; no other file is
touched by this branch.

## Commands run, and their results

Each stage was run individually rather than through `scripts/verify.py`, because
`verify.py` stops at the first failure — correct for a gate, useless for an audit.
Column three carries the 2026-08-25 result for comparison.

| # | Command | Result at `7ee6e8a0` | At `0161573` |
|---|---|---|---|
| 1 | `python -m ruff check src scripts tests` | **pass** — `All checks passed!` | pass |
| 2 | `python scripts/validate_decks.py` | **pass** — 2622 cards (51 tokens), 4 decks legal | pass — 2426 cards |
| 3 | `python scripts/build_card_index.py --check` | **pass** — `index is current (32,827 rows)` | pass |
| 4 | `python -m pytest tests/unit -q -o addopts=` | **pass** — `4581 passed, 1 warning in 56.64s` (the warning: `UV-08`) | 3460 passed |
| 5 | `python -m pytest tests/cards -q -o addopts=` | **pass** — `6562 passed, 4248 skipped, 1 warning in 175.02s` | 6092 passed, 3958 skipped |
| 6 | `python -m pytest tests/server -q -o addopts=` | **pass** — `303 passed, 1 warning in 260.24s` (the warning: `UV-08`) | 300 passed |
| 7 | `python -m pytest tests/ai -q -o addopts=` | **pass** — `75 passed in 189.06s` | 75 passed |
| 8 | `python scripts/run_arena.py --games 60 --pods 2,4 --max-draw-rate 0.25` | **pass** (exit 0) — 60 duels + 60 four-player games, **0 draws** in both, heuristic beats random 76.7% at 2p / 36.7% at 4p, 283.9s. Byte-identical win/draw/seat tables to the run five days ago, which is the seeded arena doing its job | not run (`UV-05`) |
| 9 | `verify.run_live_server_stage` (real uvicorn, 2p + 4p + one pod) | **pass** — `ok=True` in 7.7s: 2p seed 2 finished turn 16, 4p seed 4 finished turn 26 (with `WARN never reached a combat declaration` again), pod `OASIS-8076` 2p seed 5 finished turn 15; hidden information held in all three | not run (`UV-05`) |
| 10 | `cd frontend && npm run build` | **pass** — `tsc` clean, `vite build` 4.0s; one chunk-size warning (595 kB JS) | **FAIL** (`FT-01`) |
| 11 | `cd frontend && npm run lint` | **pass** (exit 0) — 278 files, `Found 1 warning.`; see `LS-01` | **FAIL** (`FT-02`) |
| 12 | `cd frontend && npm run test` | **pass** — `59 files, 1277 passed` | 55 files, 1152 |
| 13 | `cd frontend && npm run build-storybook` | **pass** (exit 0) | pass |
| 14 | `cd frontend && npm run test:stories` | **pass on a quiet machine** — `38 files, 381 passed`. It **failed** when run alongside the other suites: `ManaSymbol.stories.tsx > All Symbols` reported 48 of 54 symbol images undecoded after its 5s `waitFor`, in a test that took 5052ms. All 55 files are present in `frontend/public/symbols` and nothing in the window touched them or the story — see `FT-06` | 37 files, 365 |
| 15 | `cd frontend && npm run test:stories:handheld` | **pass** — `7 passed, 31 skipped (38 files), 35 tests` | 5 of 37 files, 22 tests |
| 16 | `npx playwright test --project=chromium` | **FAIL (exit 1)** — `3 failed, 14 skipped, 107 passed (24.5m)`. Two are the standing assertion failures (`FT-03`, `FT-04`); the third slot was a **timeout**, not an assertion, and it was a different test than five days ago — see `FT-05` and `FT-06` | **FAIL** — 3 failed, 14 skipped, 107 passed |
| 17 | `npx playwright test --project=handheld` | **FAIL (exit 1)** — `1 failed, 23 passed (5.2m)`; re-run alone, **`24 passed (3.3m)`**. The failure is a 120s timeout in `journeys-handheld.spec.ts:321`, not an assertion — see `FT-06` | 15 passed |
| 17b | `npx playwright test --project=deckfit` | **pass** — `8 passed (2.0m)` | not run — neither audit knew the third project existed |
| 18 | `python -m pytest tests -q -o addopts= --cov=src/automtg --cov-report=term` | **pass** — `11521 passed, 4248 skipped, 2 warnings in 2100.17s (35:00)`; **TOTAL 92%** (16702 statements, 1340 missed) | 91% (14844 stmts, 1296 missed) |
| 19 | `npx vitest run --project=unit --coverage --coverage.include='src/**'` | **68.31%** statements, 80.85% branches, 63.61% functions (unit project only — story and e2e runs are not instrumented) | never produced |

`-o addopts=` is required to see counts at all — see `LS-02`. Without
`--coverage.include='src/**'`, stage 19 reports **7.02%** because the provider
instruments the built `storybook-static/` bundles alongside `src/` — a trap worth
recording for whoever adds the coverage flag to CI.

Playwright and Storybook write to `frontend/test-results/`, `frontend/playwright-report/`,
`frontend/storybook-static/` and `frontend/e2e-shots/`, all gitignored: build output,
not repo changes.

## Findings

| ID | Category | Status | Path(s) | Evidence at `7ee6e8a0` | Est. risk of fixing | Blocking dependency |
|---|---|---|---|---|---|---|
| FT-01 | failing-test | **RESOLVED** | `frontend/tests/zzrepro2.test.tsx` | File no longer exists; `npm run build` exits 0. | — | none |
| FT-02 | failing-test | **RESOLVED** | `frontend/tests/zzrepro*.test.tsx` | Files no longer exist; `npm run lint` exits 0. | — | none |
| FT-03 | failing-test | **OPEN, still failing** | `frontend/e2e/acceptance.spec.ts:132` | `await expect(confirm).toHaveClass(/btn--primary/)` is unchanged, and the button it targets (`ActionPanel.tsx:1298`) still has `className="commit"`. Re-run: `Expected pattern: /btn--primary/ · Received string: "commit"`. Identical failure to 2026-08-25. | **High** — the assertion measures a class that no longer exists; the fix is to assert `commit` or `data-empty` | none |
| FT-04 | failing-test | **OPEN, and intermittent** | `frontend/e2e/layout.spec.ts:183` | `the viewer's bands do not move as permanents enter and leave play` — the relationship assertion `docs/testing.md` says must not be re-baselined. Measured 2026-09-07 across repeats of this one spec: **9px, 23px, 41px** — and, on the first CI run that ever executed this suite for real, under the 6px budget, so the case passed. The drift is not a single worsening number; it depends on which twenty actions the game offers. The earlier readings (17.37 → 21.42 → 22.01, read as steady worsening) are three samples of that spread. The `test.fail()` pin is now declared against the number each run measures, so a still-drifting run is an expected failure and a lucky one is a pass — an unconditional pin failed the whole build with “Expected to fail, but passed”. | **High** | `FB-07` was fixed in #17 for the opening hand; the battlefield bands are a separate mechanism |
| FT-05 | flaky-test | **PASSED this run; reclassified** | `frontend/e2e/pod.spec.ts:592` | `the rail is one row: Lock in and Deal are neighbours` **passed** at this tip. Five days ago it failed at `:632` — Up from Lock in landed on `pod-copy` instead of `change-deck` — after a 15s `expect.poll` timeout, and the neighbour half the first audit saw fail had already been fixed by #19. Same spec file, unchanged since `0161573`, two different verdicts. Treat this as `FT-06`, not as a fixed bug: nothing was changed between the two runs. Re-run alone at this tip: `21 passed (1.1m)`. | **Medium** | `FT-06` |
| CG-01 | coverage-gap | **OPEN, unchanged** | `frontend/e2e/action-panel.spec.ts` lines 80, 127, 142, 167, 224, 269, 520, 661 | Same eight `test.skip(!(await reachDecision(page, …)))` gates, same fixed seeds (`seed: 3`, `5`, `7` at lines 79–519). Deterministic, so they skip on every run. Re-run: still exactly **14 skipped** of 124. Note that `journeys-handheld.spec.ts:421` (new) *does* reach a block declaration against the live engine, so the capability exists — the seeds in this file are simply ones that never get there. | **Medium** — reuse the seed or the scripted path `journeys-handheld.spec.ts` uses | `FT-03` (same surface) |
| CG-02 | coverage-gap | **OPEN, narrowed** | 20 modules under `frontend/src/` | The same 20 modules have zero references from any `*.test.ts(x)`, `*.spec.ts` or `*.stories.tsx` (list in the appendix). But unit coverage now shows the grep overstated it: `GameRoute.tsx` is **92%** covered (through `routing.test.tsx`), `ChoiceCombo.tsx` **91%**, `useHandLift.ts` **90%**. The real holes are `GroupDial.tsx` **6%**, `CardHold.tsx` **17%**, `OpponentBoard.tsx` **14%**, `ControllerPanel.tsx` **5%**, `NewGameScreen.tsx` **0%** — and, outside the original list, `OpeningHand.tsx` **4%**, `CardGhost.tsx` **4%**, `InviteDialog.tsx` **5%**, `StackPanel.tsx` **5%**, `EventTicker.tsx` **7%** (all unit-project numbers; several of these are exercised by stories, which are not instrumented). | **Medium** | `CG-04` is resolved, so coverage can now be gated per file |
| CG-03 | coverage-gap | **OPEN, narrowed** | `frontend/src/**/*.stories.tsx` (handheld project) | `npm run test:stories:handheld` now runs `7 passed, 31 skipped (38 files)` — **35 tests**, up from 22 over 5 files. `Journeys.stories.tsx` (#19) added press-budget gates at 1280×800. Still 7 of 38 story files. | **Medium** | none |
| CG-04 | coverage-gap | **RESOLVED** (on this branch) | `frontend/` | `@vitest/coverage-v8@3.2.7` is installed and stage 19 produced the first frontend number: **68.3%** of `src/`. Not yet wired into `verify.py` or `package.json`. | **Low** | none |
| CG-05 | coverage-gap | **OPEN, unchanged in shape** | `src/automtg/cards/authoring/` | Overall Python coverage is **92%** (16702 statements, 1340 missed; was 91% / 14844 / 1296 at the first audit). Four authoring modules are still the outlier and account for **402 of the 1340 missed lines — 30% of all uncovered code in the project** — `fidelity.py` **27%** (118/161 missed), `packet.py` **46%** (54/100), `queue.py` **48%** (54/103), `templates.py` **49%** (176/345). Those four numbers have not moved a line in eleven days while everything around them grew. The fifth authoring module went the other way: `verify.py` is **94%** covered, having gained 340 lines and a test suite with them, which is what the other four look like when someone tests them. | **Medium** — developer tooling, contained blast radius | none |
| CG-06 | coverage-gap | **IMPROVED, still the engine's lowest** | `src/automtg/engine/effects/ops_mana.py` | **80%** (8 of 40 statements missed; 73% and 8 of 30 at the first audit). Still the lowest-covered module in the rules engine — the next lowest are `values.py` and `rng.py` at 89% — but the gap closed rather than widened: the module gained 10 statements and no new misses. Worth re-checking rather than carrying forward as written. | **Medium** | none |
| OF-01 | oversized-file (>600) | **OPEN, worse** | 53 files (was 45; CSS excluded as before) | Full ranked list in the appendix. Worst: `loader.py` **5196** (was 3652), `ops_board.py` **2081** (1619), `characteristics.py` **2043** (1583), `Table.tsx` **2030** (1742), `legality.py` **1752** (1419), `primitives.py` **1730** (1470). Eight new entries crossed 600 in the window, among them `objects.py` (754), `zones.py` (717), `ops_control.py` (693), `targeting.py` (663), `PlayerOrb.tsx` (608). | **High** for `loader.py` / `Table.tsx`; **Medium** for the rest | `CG-04` is resolved for the frontend; Python coverage is per-module already |
| DC-01 | dead-code | **OPEN, 19 of 20** | 19 symbols in `src/automtg/` | `remove_attacker` gained a caller (`combat.py:525`) and drops off the list. The other 19 still have zero references outside their own `def` across `src`, `tests`, `scripts`, `frontend/src`, `frontend/e2e`, `frontend/tests` (compiled `__pycache__` matches excluded). Updated line numbers in the appendix. | **Low** individually | `UV-02` — the `register()` dispatch caveat still applies |
| SD-01 | stale-doc | **OPEN, half-fixed and re-staling** | `docs/testing.md` | #19 corrected the three frontend rows and they have already drifted again: claimed `1272` / `381 + 35` / `118`, measured **1277** / **381 + 35** / 156 across three projects. The four Python rows were never touched and are further off than at the first audit: unit **395 → 4581**, cards **3513 → 6562 (+4248 skipped)**, server **287 → 303**. `tests/ai` (**75**) is still the only correct row in the table. | **Low** | none |
| SD-02 | stale-doc | **OPEN, unchanged** | `.dockerignore:53` | Still excludes `legacy-frontend`; `ls legacy-frontend` → no such file. | **Low** | none |
| LP-01 | leftover-prototype | **RESOLVED** | `frontend/tests/zzrepro*.test.tsx` | Gone. Their subject (`FB-01`) shipped as `lobbyBack.test.tsx` and `padTyping.test.ts` in #15. | — | none |
| LP-02 | leftover-prototype | **OPEN, unchanged** | `frontend/src/components/game/GroupDial.tsx:13` | *"it was the prototype's name for exactly this control, carried into the trap and then not built"* — same comment, same line. `GroupDial.tsx` is at 6% unit coverage. | **Low** — rename only | `CG-02` |
| LP-03 | leftover-prototype | **OPEN, unchanged** | `frontend/src/components/game/OpponentBoard.tsx:18` | *"this is a temporary overlay that owns the screen while it is up"* — same comment, same line. 14% unit coverage. | **Medium** — "temporary" with no replacement designed | none |
| LS-01 | lint-suppression | **OPEN, unchanged** | `frontend/src/components/lobby/HomeScreen.tsx:323` | Still the only lint diagnostic: `useExhaustiveDependencies` — *"more dependencies than necessary: sel"* on `useLayoutEffect(() => { refollowCursor(); }, [sel])`. The comment above it (`:319-322`) now explains why `sel` is there: the ring must be told to watch on selection change even when nothing moved. So this is a documented, deliberate dep the linter cannot see. | **Low** — add a `biome-ignore` with that reason, or leave as is | none |
| LS-02 | lint-suppression | **OPEN, unchanged** | `pyproject.toml:29` → `addopts = "-q"` | `verify.py` still adds its own `-q` (`python_stages()`, lines 181–191), making `-qq`; the gate's output never shows how many tests ran. | **Low** | none |
| LS-03 | lint-suppression | **unchanged** | `src`, `scripts`, `tests` | 22 `# noqa`: 8×`F401`, 8×`E402`, 3×`RUF001`, 3×`E731`. Six project-wide ruff ignores and three `per-file-ignores`, each with a written rationale. | **Low** | none |
| LS-04 | lint-suppression | **unchanged in kind** | `frontend/src`, `frontend/e2e`, `frontend/tests` | 20 `biome-ignore` comments across 15 files (was 19 / 17). Still zero `@ts-ignore` / `@ts-expect-error`. | **Low** | none |
| FT-06 | flaky-test | **NEW** | `frontend/e2e/` (both projects) | **Three different tests failed on timeout across two runs of the same unchanged commit**, and no two runs agreed on which. This session: `orb.spec.ts:225` hit the 180s test timeout inside the `keepOpeningHand` helper (`helpers.ts:171`), and `journeys-handheld.spec.ts:321` hit 120s. Five days ago, on the same specs: both passed and `pod.spec.ts:632` failed a 15s poll instead. Wall clock moved with it — chromium 19.9m → 24.5m, handheld 3.2m → 5.2m — so the trigger is machine load, not code. The two genuine assertion failures (`FT-03`, `FT-04`) reproduced identically in both runs, which is how you can tell the two classes apart. **All four re-ran green in isolation on a quiet machine**: `orb.spec.ts` `14 passed (1.1m)`, `pod.spec.ts` `21 passed (1.1m)`, `journeys-handheld.spec.ts` `6 passed (1.3m)`, and the whole handheld project back to `24 passed (3.3m)` — plus the Storybook case in stage 14, `381 passed`. Nothing was changed between the failing and passing runs. | **Medium** — the fix is per-test budgets that scale, or a serial project; the risk is that raising timeouts hides a real slowdown | none |
| NF-01 | noisy-test | **NEW** | `frontend/src/components/game/ParticleLayer.tsx:142` | `npm run test` prints a jsdom stack trace twice — `Not implemented: HTMLCanvasElement.prototype.getContext` — from `routing.test.tsx`'s two rematch cases, which mount the board and hit the particle canvas. Tests pass; the trace is stderr noise that will hide a real one. | **Low** — guard `getContext` behind a null check, or stub canvas in the jsdom setup | none |

### Categories with no findings

- **duplicated-logic** — no confirmable instance; `UV-03` still stands.
- **TODO/FIXME/HACK/XXX markers** — zero outside the dataclass field name `todo:` in
  `src/automtg/cards/authoring/packet.py` (lines 117, 130, 392, 397, 411).
- **broken documentation links** — every relative link in `README.md`, `docs/*.md`
  and `docs/adr/*.md` resolves (0 broken; checked by script).

## Field-reported defects (playtesting during the first audit)

**14 defects reported on 2026-08-25.** At `7ee6e8a0`: **7 fixed with a regression
test**, **7 open**. Fixed ones name the commit and the test; open ones say what was
looked for and not found.

| ID | Report | Status at `7ee6e8a0` | Evidence |
|---|---|---|---|
| FB-05 | Same opening hand every game | **FIXED** — #16 `318e73c7` | `sessions.py:450` — `seed=new_seed() if seed is None else int(seed)`; `new_seed()` (`:413`) draws from `secrets`. Tests in `tests/server/test_api.py` (+34). |
| FB-11 | The Attack button cannot be focused even when enabled | **FIXED** — #18 `f1c0f21d` | `ActionPanel.tsx:1299` — `data-stop={stopId.commit}` on the confirm slab; both `commit-mark` buttons carry `stopId.commitMark("all")` (`:1249`, `:1279`). `stops.test.tsx:211` asserts `combat-confirm` has `data-stop="commit"`. |
| FB-09 | Focus cannot pass the disabled Attack button | **FIXED by construction** — #18 | Same button as `FB-11`, now a stop; `stops.ts:173-176` documents that a disabled control *is* a stop ("walking onto a greyed-out action to read why it is greyed out is how a player finds out"). No test targets the disabled case specifically. |
| FB-14 | Commander cannot be summoned from the player orb by focus + A | **FIXED** — #15 `6797c35c` | `CommandZone.tsx:151,176` — `data-stop={reachable ? stopId.card(card.oid) : undefined}`; the commit's own words: *"the only control on the board with no `data-stop`"*. Story `HandheldTheCommanderIsReachable` (`Table.stories.tsx`, hardened in `ab7307da`). The first audit's "missing stop is ruled out" was measured against the working tree that already contained this fix. |
| FB-01 | Trapped in deck selection (Sort dropdown, left off close) | **FIXED** — #15 `6797c35c` | The `<select>` no longer swallows left/right/Backspace (`pad.ts`, `padTyping.test.ts` +99) and `B` in the lobby is owned by `useDismiss.ts` (new, 83 lines; `lobbyBack.test.tsx` +192). |
| FB-03 | Focusing a card in the action panel shows no preview | **FIXED** — #17 `552f9dba` | `previewing()`'s `onFocus` was dead because `hoverFor` ran after focus and cleared it. `data-preview-oid` is now written on every previewing row and the plinth (`CommandZone.tsx`), and `cursor.ts` reads it. Story `RowsDeclareWhatTheyPreview`; four cases in `cursor.test.ts`. |
| FB-07 | Hover ring misaligns with hand cards after they lift | **FIXED for the opening hand** — #17 `552f9dba` | `.mull__slot` now carries the lift transform itself (`OpeningHand.tsx`, `opening.css`), so the ring measures the element that moved. Story `TheRingRisesWithTheCard`. The commit notes `HandFan`'s `.hand__slot` already had the fixed/moving parts the right way round, so the in-game hand was not the reporter's surface. `useHandLift.ts` is 90% unit-covered. |
| FB-10 | L2 triggers the Deck's native right-click | **ADDRESSED IN DOCS, binding unchanged** | `buttons.ts:101` still maps `z: "l2"`. `docs/steamdeck.md` §2 now says to set the Steam Input template to *Gamepad* and, for a keyboard layout, to point L2 at `Z` (`:89`). In-app, L2 now jumps to the commit slab (`Table.tsx:1431`). Nothing was changed to survive the stock keyboard template; #15's message attributes the original controller report to that template. |
| FB-02 | `400: unknown action id 'a1-play_land'`, then jumps to combat | **OPEN, unchanged** | `sessions.py:241` — `f"a{index}-{action.kind.value}"`: ids are still positional and unversioned, rebuilt on every `_refresh_actions()` (`:233`). A click against a stale list is still indistinguishable from an invalid one. No commit in the window touched this. |
| FB-04 | L1 fully quits the game | **OPEN, likely the Steam template** | `Table.tsx:1378` still binds L1 to `stepGroup(-1)`; the only quit path is `GameRoute.tsx:68-72`. #15's message says the report it was chasing *"turned out to be a Steam Input template"* — under the keyboard template a shoulder arrives as a browser key, not an L1. Not reproduced with a real gamepad; not closed either, because no test asserts L1 cannot reach `quit`. |
| FB-06 | B during combat closes the game to home | **OPEN, probably the same class as FB-01** | `Table.tsx:781` — `back()` still *"never quits from the top"*. #15 found that an unclaimed `B` fell through to the browser's own back navigation; `useDismiss.ts` now claims it on lobby surfaces. Whether the in-game path was the same fall-through was not established, and `GameRoute.tsx` has no test for it (its 92% unit coverage comes from `routing.test.tsx`, which does not press B). |
| FB-08 | A/Y does not read a card to full screen on hover | **OPEN, unchanged** | `Table.tsx:1388-1394` binds `Y` → `setHeldCard(ref.id)` for a `card` stop, rendered by `CardHold.tsx` — **17%** unit coverage, no story, no e2e (`CG-02`). No commit in the window touched `CardHold.tsx`. |
| FB-13 | Commander only flips to "Ready" while the pointer is over the orb | **OPEN, unchanged** | `CommandZone.tsx:70-71` still returns `ready` only from `castable`, derived from `playableOids` at `:347`. #15 and #17 added stops and preview attributes to this file and did not touch the recompute. |
| FB-12 | Settings popover unreachable by controller focus | **OPEN, mechanism unclear** | Every control inside the popover carries a `tool:` stop (`ActionPanel.tsx:965-1038`: settings, mute, undo, quit) and did at `0161573` too, so the trap is not a missing stop. `closeSettings` (`:230-234`) now returns the ring to the settings button on close. #19's `escapeGroup` relaxed-retry (`stops.ts`) may have changed the traversal; nothing tests entering the popover by pad. |

**Every one of the seven open defects lands in code with no targeted test** —
`CardHold.tsx` (17%), `GroupDial.tsx` (6%), `OpponentBoard.tsx` (14%), the settings
popover traversal, the commander-ready recompute, the positional action ids, and
`GameRoute`'s B/L1 paths. The seven fixed ones each shipped with a test. That is the
whole story of this section: the input layer stopped being the least-tested area
where someone wrote tests, and stayed the most defective everywhere they did not.

## Disposable mockup / prototype candidates

**Nothing was deleted.** Candidates for a human decision, each with the counter-argument.

| Path | Size | Why it looks disposable | Why it may not be |
|---|---|---|---|
| `mockups/` (whole tree) | 391 files, **108 MB** | Static HTML/JS design exploration. No build, test or runtime step consumes it. Already excluded from the Docker build context. | **82 citations across 46 files** in shipped `frontend/src` and `frontend/e2e` name specific mockup paths as the source of a number or decision (up from 47 at the first audit — the habit is growing, not fading). Deleting orphans every one. |
| `mockups/**/shots/` | 158 PNGs | Pure screenshots — most of the 108 MB, least referenced. Regenerable by opening the HTML. | Some READMEs embed them as the record of a design round. |
| `mockups/art/` + `mockups/fetch_art.py` | 67 JPGs + 1 script | Duplicates a subset of `data/art/`; used only by `05-planar-art.html`. | `fetch_art.py` re-downloads them; removal is reversible. |

`frontend/tests/zzrepro*.test.tsx`, the first audit's clearest candidate, are gone.
`frontend/src/testing/scenarios.ts` (1008 lines) is imported by the story suite that
runs 381 passing tests and is **not** a candidate.

## Unverified / ambiguous — flagged rather than guessed

- **UV-01** — RESOLVED as a question, replaced by `FT-06` as a problem. Full runs at
  this tip: chromium `3 failed, 14 skipped, 107 passed (24.5m)`, handheld `1 failed,
  23 passed (5.2m)`, deckfit `8 passed (2.0m)`. 156 cases across three disjoint
  projects — `chromium` ignores `handheld|pad|deckfit.spec.ts`, `handheld` matches
  `handheld|pad` — against `docs/testing.md`'s claim of 118 for `frontend/e2e/`.
  `verify.py` runs none of the three: Playwright is not a verify stage
  (`docs/testing.md`: *"Playwright is not run here"*), so every `FT-` finding in this
  report is invisible to the gate that is supposed to catch them.
- **UV-02** — the 19 `DC-01` candidates are **candidates only**. The engine registers
  effect ops dynamically (`register()` in `engine/effects/__init__.py`), and a grep
  cannot see dispatch through a registry. `remove_attacker` leaving the list because
  a caller appeared is the kind of thing this caveat exists for.
- **UV-03** — duplication between `handheldAssert.ts` and `mockups/*/assert.js` was
  checked by function-name intersection only. Unchanged.
- **UV-04** — `tests/cards` skips **4248** tests. Sampled reasons are per-card
  conditionals, not disabled coverage. Not counted as a gap; not individually reviewed.
- **UV-05** — RESOLVED. Both stages the first audit deferred were run this time
  (stages 8 and 9) and both pass. Two things worth noting from their output: the
  arena stage's *label* in `verify.py:194` ("120 duels + 40 pods") does not match
  what its command plays (60 games at each of two pod sizes), and the 4-player live
  game prints `WARN never reached a combat declaration` — the same shape of gap as
  `CG-01`, in the one smoke test that runs against a real socket.
- **UV-06** — RESOLVED. Frontend unit coverage was produced this time (stage 19). It
  covers the `unit` vitest project only: the two Storybook projects run in a real
  Chromium and are not instrumented, so components whose only tests are stories
  (`OpeningHand.tsx`, `StackPanel.tsx`, `EventTicker.tsx`, `InviteDialog.tsx`) read
  lower than their true exercised fraction.
- **UV-07** — root causes for `FB-02`, `FB-04`, `FB-06`, `FB-08`, `FB-12`, `FB-13`
  are **not** established. `FB-10`'s cause is established and was answered with
  documentation rather than code.
- **UV-08** — RESOLVED, and worth a line each. The two Python warnings (stage 18's
  `2 warnings`) are: `tests/unit/test_shield_counter.py::TestDiamondCity` defines a
  class-scoped fixture as an instance method — `PytestRemovedIn10Warning`, i.e. it
  will be an error on the next pytest major; and `fastapi/testclient.py:1` —
  `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated;
  install httpx2 instead`, which is a dependency's problem, not this repo's.

## Appendices

### Untested frontend modules (CG-02)

Zero references from any `*.test.ts(x)`, `*.spec.ts` or `*.stories.tsx`, with the unit
coverage each one actually gets (stage 19). The grep and the number disagree often
enough that the number is the one to trust:

```
frontend/src/audio/sfx.ts                            11%
frontend/src/components/game/CardHold.tsx            17%   <- FB-08
frontend/src/components/game/ChoiceCombo.tsx         91%
frontend/src/components/game/GroupDial.tsx            6%   <- LP-02
frontend/src/components/game/OpponentBoard.tsx       14%   <- LP-03
frontend/src/components/game/SeatIcon.tsx           100%
frontend/src/components/lobby/Mark.tsx                0%
frontend/src/components/lobby/doorArt.tsx           100%
frontend/src/components/ui/ActionIcon.tsx           100%
frontend/src/components/ui/ControllerPanel.tsx        5%
frontend/src/components/ui/SchemePicker.tsx         100%
frontend/src/motion/springs.ts                      100%
frontend/src/screens/DeckDossierRoute.tsx             —    (not in the report; route-only)
frontend/src/screens/GameRoute.tsx                   92%   <- FB-04, FB-06 (B/L1 paths untested)
frontend/src/screens/HomeRoute.tsx                   44%
frontend/src/screens/NotFound.tsx                   100%
frontend/src/screens/PodRoute.tsx                    64%
frontend/src/state/useHandLift.ts                    90%
frontend/src/state/useHandheld.ts                    89%
frontend/src/state/useImages.ts                     100%
```

Lowest-covered modules **not** in the grep list, because a story or an unrelated test
imports them without exercising them: `NewGameScreen.tsx` 0%, `main.tsx` 0%,
`CardGhost.tsx` 4%, `OpeningHand.tsx` 4%, `InviteDialog.tsx` 5%, `StackPanel.tsx` 5%,
`EventTicker.tsx` 7%, `actuators.ts` 12%, `scheduler.ts` 16%, `ParticleLayer.tsx` 17%,
`CombatArrows.tsx` 17%, `FxLayer.tsx` 17%, `CommanderCard.tsx` 25%.

Per directory: `src/logic` **91%**, `src/input` **87%**, `src/components/lobby` 77%,
`src/screens` 73%, `src/state` 67%, `src/components/game` 62%, `src/components/ui`
61%, `src/fx` 55%, `src/api` 16%, `src/components/menu` 14%, `src/audio` 11%. Every
one of these is within a tenth of a point of the same measurement five days earlier,
and the untested-module list is character-for-character identical — 21 commits of
engine and card work moved the Python numbers and left the frontend exactly where it
was. The one exception is `CardFace.tsx`, which went to **98%** on the back of the
single frontend test those commits added.

### Dead-code candidates (DC-01) — unconfirmed, see UV-02

```
src/automtg/ai/action_space.py:324            decision_kind_of
src/automtg/ai/action_space.py:328            creature_power
src/automtg/cards/authoring/templates.py:958  sentence_patterns
src/automtg/cards/images.py:152               normal_url
src/automtg/engine/actions.py:291             chosen_refs
src/automtg/engine/actions.py:294             chosen_values
src/automtg/engine/carddef.py:1030            color_set
src/automtg/engine/characteristics.py:102     printed_chars
src/automtg/engine/characteristics.py:1228    effective_toughness
src/automtg/engine/effects/selectors.py:1213  sorted_candidates
src/automtg/engine/game.py:1442               hand_size_limit
src/automtg/engine/game.py:1446               target_ref
src/automtg/engine/legality.py:1783           creature_can_attack
src/automtg/engine/mana.py:229                total_required
src/automtg/engine/primitives.py:1889         controlled_by
src/automtg/engine/rng.py:55                  spawn
src/automtg/engine/state.py:372               maybe_obj
src/automtg/engine/state.py:519               objects_in
src/automtg/engine/state.py:759               sorted_oids
```

Dropped since the first audit: `combat.py remove_attacker` — now called at `combat.py:525`.

### Oversized files (OF-01) — >600 lines, shipped code, mockups and CSS excluded

53 files, the same count as five days ago but not the same list — the growth
went into files that were already over. A column of `—` means the file did not exist at
`0161573`; every other row grew. Note the first audit listed `pad.ts` at 912 lines when
`git show 0161573:` gives 855: that table was measured against the dirty working tree it
warned about, not against the commit it named. This column is `git show`.

| Path | Lines | At `0161573` |
|---|---|---|
| `src/automtg/cards/loader.py` | 5464 | 3652 |
| `src/automtg/engine/characteristics.py` | 2146 | 1583 |
| `src/automtg/engine/effects/ops_board.py` | 2110 | 1619 |
| `frontend/src/components/game/Table.tsx` | 2030 | 1742 |
| `src/automtg/engine/primitives.py` | 1890 | 1470 |
| `src/automtg/engine/legality.py` | 1791 | 1419 |
| `src/automtg/engine/costs.py` | 1631 | 1341 |
| `src/automtg/engine/combat.py` | 1559 | 1390 |
| `src/automtg/engine/game.py` | 1447 | 1272 |
| `src/automtg/engine/effects/ops_cards.py` | 1429 | 1080 |
| `src/automtg/engine/triggers.py` | 1383 | 1208 |
| `frontend/src/components/game/ActionPanel.tsx` | 1367 | 1277 |
| `src/automtg/engine/effects/selectors.py` | 1215 | 965 |
| `src/automtg/cards/authoring/verify.py` | 1171 | 831 |
| `src/automtg/engine/carddef.py` | 1161 | 919 |
| `src/automtg/engine/structs.py` | 1139 | 972 |
| `frontend/src/components/game/Table.stories.tsx` | 1024 | 894 |
| `frontend/src/testing/scenarios.ts` | 1008 | 1008 |
| `src/automtg/engine/stack.py` | 984 | 752 |
| `src/automtg/engine/mana.py` | 965 | 819 |
| `src/automtg/cards/authoring/templates.py` | 964 | 959 |
| `src/automtg/cards/schema.py` | 962 | 732 |
| `src/automtg/cards/proxy.py` | 928 | 921 |
| `frontend/src/input/pad.ts` | 927 | 855 |
| `src/automtg/engine/effects/values.py` | 926 | 776 |
| `tests/cards/test_every_card_works.py` | 861 | 699 |
| `frontend/src/logic/events.ts` | 843 | 814 |
| `tests/cards/test_proxy.py` | 823 | 787 |
| `src/automtg/engine/turn.py` | 802 | 762 |
| `src/automtg/server/lobby.py` | 792 | 792 |
| `frontend/e2e/cycle3.spec.ts` | 764 | 764 |
| `src/automtg/engine/state.py` | 761 | 690 |
| `src/automtg/engine/objects.py` | 754 | 561 |
| `frontend/src/input/cursor.ts` | 739 | 677 |
| `src/automtg/engine/zones.py` | 717 | 579 |
| `src/automtg/engine/effects/ops_control.py` | 713 | 558 |
| `frontend/e2e/pad.spec.ts` | 705 | 582 |
| `tests/cards/test_authoring.py` | 700 | 388 |
| `tests/unit/test_saga.py` | 688 | 688 |
| `frontend/tests/components.test.tsx` | 687 | 687 |
| `frontend/e2e/pod.spec.ts` | 681 | 681 |
| `frontend/e2e/action-panel.spec.ts` | 671 | 671 |
| `src/automtg/engine/targeting.py` | 670 | 404 |
| `frontend/src/components/lobby/HomeScreen.tsx` | 665 | 665 |
| `frontend/e2e/handheldAssert.ts` | 665 | 665 |
| `src/automtg/server/routes.py` | 658 | 623 |
| `tests/unit/test_delayed_object_reference.py` | 644 | 644 |
| `tests/unit/test_monarch.py` | 643 | 643 |
| `src/automtg/cards/images.py` | 624 | 569 |
| `tests/unit/test_goad.py` | 621 | 621 |
| `frontend/src/logic/zoomFit.ts` | 608 | 608 |
| `frontend/src/components/game/PlayerOrb.tsx` | 608 | 593 |
| `frontend/src/components/game/FxLayer.tsx` | 605 | 605 |

For the record, the stylesheets excluded above would add seven more: `handheld.css`
2282, `board.css` 2278, `lobby.css` 1756, `ui.css` 1649, `cards.css` 1177, `seat.css`
741, `door.css` 697.

## Out of scope: the feature request from the first audit

The user asked, during the first audit, to **make the `X` button show an opponent's
board, the same as clicking their orb does today**. Not done — and #19 has since bound
`X` to something else: it is now the commit shortcut (`Table.tsx:1368` → `secondary`;
`docs/steamdeck.md` documents it as Pass / All attack / Attack / All defend / Block).
The request is still open but needs a different button.
