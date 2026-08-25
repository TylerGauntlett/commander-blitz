# Tech Debt Audit

**Commit audited:** `0161573` (`main`)
**Date:** 2026-08-25
**Scope:** audit only — no source file was modified.

Every line number below is true *at this commit*. Evidence cells are re-derivable by
running one command or opening one `file:line`.

## The three riskiest areas

**1. The controller / focus input layer — the least covered code and the most defective.**
Ten of the fourteen defects reported from live play during this audit are
controller-focus failures. The layer's core modules carry **zero tests**: `CardHold.tsx`,
`useHandLift.ts`, `GroupDial.tsx`, `ChoiceCombo.tsx`, `GameRoute.tsx` (`CG-02`). One
root cause is proven and mechanical — the combat confirm button carries no `data-stop`,
so the ring can never land on it (`FB-11`) — and the e2e cases that assert exactly that
button (`action-panel.spec.ts:107-121`) are among the ones that never run (`CG-01`).
The whole handheld surface is gated by **22 tests over 5 of 37 story files** (`CG-03`).

**2. Combat — a failing test, a permanently skipped suite, and four field defects.**
`acceptance.spec.ts:132` fails outright (`FT-03`), and every attacker/blocker e2e case
is gated behind `test.skip(!(await reachDecision(page, "attackers")))` with **fixed
seeds**, so those specs skip identically on every run and have never executed
(`CG-01`). Combat is simultaneously the least-exercised path and the source of
`FB-02`, `FB-06`, `FB-09` and `FB-11`. The suite reports green while testing nothing.

**3. `sessions.py:432` — every unseeded game is byte-identical.**
`seed=0 if seed is None else int(seed)` means a game dealt without a typed seed always
uses seed **0** (`FB-05`). One line, trivially fixed, but it silently destroys the
variety of every playtest — and every judgement made from playtesting since it landed
was made against one deterministic game.

## Disclosure: the only repo change made

The audit was authorised to install one dev dependency so frontend coverage could be
measured rather than guessed:

```
cd frontend && npm i -D @vitest/coverage-v8@3.2.7
```

Diff — `frontend/package.json` (+1 line), `frontend/package-lock.json` (+702 lines):

```
+    "@vitest/coverage-v8": "^3.2.7",
```

The unpinned form (`@vitest/coverage-v8`) **fails to install**: it resolves to 4.1.11,
whose peer is `vitest@4.1.11`, while this project pins `vitest@^3.2.7`. Pinning to
3.2.7 installs cleanly. No other file was touched.

Two further files appeared as untracked when the audit began. They were **pre-existing,
not mine** — see `LP-01`.

## ⚠ The working tree changed during this audit

This audit was taken against a clean tree at `0161573`. **`HEAD` never moved**, but by
the time the report was written a concurrent session had modified **16 tracked source
files** and added two new ones:

```
 M frontend/src/components/game/{CardPreview,CommandZone,PlayerOrb,Table,Table.stories}.tsx
 M frontend/src/components/lobby/{DeckCatalog,DeckCatalog.stories,DeckDossier,InviteDialog}.tsx
 M frontend/src/input/pad.ts            (+82)   M frontend/src/logic/verbs.ts       (+10)
 M frontend/src/styles/{board,handheld,reader}.css
 M frontend/tests/{pad,padTyping}.test.ts
 ?? frontend/src/input/useDismiss.ts    ?? frontend/tests/lobbyBack.test.tsx
```

Those edits are **not mine** — this session changed only the two package files above.
They appear to be in-flight fixes for the field defects below (the touched files map
onto `FB-01`, `FB-03`, `FB-07`, `FB-08`, `FB-10`).

**Consequence for this report:** every Python citation and every measured suite result
above is still valid, and the two load-bearing citations were re-checked by hand after
the change and still hold verbatim — `sessions.py:432` (`FB-05`) and
`ActionPanel.tsx:1207-1228` (`FB-11`). **Line numbers in the 16 modified frontend files
may have shifted**, and the frontend suite results in the table were measured *before*
those edits. Re-run before relying on them.

## Commands run, and their results

Each stage was run individually rather than through `scripts/verify.py`, because
`verify.py` stops at the first failure — correct for a gate, useless for an audit.

| # | Command | Result |
|---|---|---|
| 1 | `python -m ruff check src scripts tests` | **pass** — `All checks passed!` (exit 0) |
| 2 | `python scripts/validate_decks.py` | **pass** — 2426 cards, 4 decks legal |
| 3 | `python scripts/build_card_index.py --check` | **pass** — `index is current (32,827 rows)` |
| 4 | `python -m pytest tests/unit -q -o addopts=` | **pass** — `3460 passed in 18.21s` |
| 5 | `python -m pytest tests/cards -q -o addopts=` | **pass** — `6092 passed, 3958 skipped in 155.12s` |
| 6 | `python -m pytest tests/server -q -o addopts=` | **pass** — `300 passed in 94.70s` |
| 7 | `python -m pytest tests/ai -q -o addopts=` | **pass** — `75 passed in 125.22s` |
| 8 | `cd frontend && npm run build` | **FAIL (exit 2)** — see `FT-01` |
| 9 | `cd frontend && npm run lint` | **FAIL (exit 1)** — 2 errors, 1 warning; see `FT-02`, `LS-01` |
| 10 | `cd frontend && npm run test` | **pass** — `55 files, 1152 passed` |
| 11 | `cd frontend && npm run build-storybook` | **pass** (exit 0) |
| 12 | `cd frontend && npm run test:stories` | **pass** — `37 files, 365 passed` |
| 13 | `cd frontend && npm run test:stories:handheld` | **pass** — `5 passed, 32 skipped (37 files), 22 tests` |
| 14 | `npx playwright test --project=chromium` | **FAIL (exit 1)** — `3 failed, 14 skipped, 107 passed (20.4m)`; see `FT-03`, `FT-04`, `FT-05`, `CG-01` |
| 15 | `npx playwright test --project=handheld` | **pass** — `15 passed (1.1m)` |
| 16 | `python -m pytest tests -q -o addopts= --cov=src/automtg --cov-report=term` | **pass** — `9927 passed, 3958 skipped in 1694.80s (28:14)`; **TOTAL 91%** (14844 statements, 1296 missed) |

`-o addopts=` is required to see counts at all — see `LS-02`.

Playwright and Storybook write to `frontend/test-results/`, `frontend/playwright-report/`,
`frontend/storybook-static/` and `frontend/e2e-shots/`, all gitignored: build output,
not repo changes.

## Findings

| ID | Category | Path(s) | Evidence | Est. risk of fixing | Blocking dependency |
|---|---|---|---|---|---|
| FT-01 | failing-test | `frontend/tests/zzrepro2.test.tsx` | `npm run build` exits 2: `tests/zzrepro2.test.tsx(3,43): error TS6133: 'expect' is declared but its value is never read.` Blocks the `tsc --noEmit` half of the build, so **`vite build` never runs**. | **RESOLVED** during the audit by another session (see `LP-01`); the file no longer exists | none |
| FT-02 | failing-test | `frontend/tests/zzrepro.test.tsx`, `zzrepro2.test.tsx` | `npm run lint` exits 1: `Found 2 errors.` Both are biome `format` errors on these two files (multi-line `console.log` reflow). | **RESOLVED** during the audit by another session (see `LP-01`) | none |
| FT-03 | failing-test | `frontend/e2e/acceptance.spec.ts:132` | `combat still works through the re-themed controls` — `expect(locator).toHaveClass(expected) failed. Expected pattern: /btn--primary/. Received string: "commit"`. The combat confirm button's class was renamed to `commit` and the assertion never followed. **Same button as `FB-11`.** | **High** — a genuine combat regression, and the assertion is measuring a class that no longer exists | none |
| FT-04 | failing-test | `frontend/e2e/layout.spec.ts:183` | `the viewer's bands do not move as permanents enter and leave play` — `Error: the creatures band moved 17px within the mat; the board is jumping again. Expected: < 6. Received: 17.3675537109375`. A **relationship** assertion, which `docs/testing.md` states is *"a regression, not a baseline"* and must not be re-taken. | **High** — the doc's own rule forbids re-baselining this; the board really is moving | Correlates with `FB-07` (ring misaligns after cards lift) |
| FT-05 | failing-test | `frontend/e2e/pod.spec.ts:592` | `the rail is one row: Lock in and Deal are neighbours` — `expect(received).toBe(expected). Expected: "lock-in". Received: "start-game"`. The pod rail's control order changed and the neighbour invariant broke. | **Medium** | Correlates with `FB-01` (pod/deck-selection focus traps) |
| CG-01 | coverage-gap | `frontend/e2e/action-panel.spec.ts` lines 80, 127, 142, 167, 224, 269, 520, 661 | The completed chromium run reported **14 skipped** of 124. Every combat case is gated on `test.skip(!(await reachDecision(page, "attackers")), "never reached declare attackers")`. Seeds are **fixed** (`seed: 3`, `5`, `7`), so the branch is deterministic: these specs skip on *every* run and have therefore never executed. | **Medium** — needs a seed or scripted state that actually reaches combat | FT-03 (same surface) |
| CG-02 | coverage-gap | 20 modules under `frontend/src/` | Zero references from any `*.test.ts(x)`, `*.spec.ts` or `*.stories.tsx`. Full list in *Untested frontend modules*. Includes `CardHold.tsx`, `useHandLift.ts`, `GroupDial.tsx`, `ChoiceCombo.tsx`, `GameRoute.tsx`. | **Medium** — writing tests is safe; the risk is what they reveal | none |
| CG-03 | coverage-gap | `frontend/src/**/*.stories.tsx` (handheld project) | `npm run test:stories:handheld` runs `5 passed, 32 skipped (37)` — 22 tests. `docs/testing.md` calls this "**the only place the handheld floors are gated by CI**", and it exercises 5 of 37 story files. | **Medium** — un-skipping will surface real floor violations | none |
| CG-05 | coverage-gap | `src/automtg/cards/authoring/` | Python line coverage is **91% overall** (14844 statements, 1296 missed), but the authoring package is the outlier and accounts for **405 of the 1296 missed lines — 31% of all uncovered code in the project**: `fidelity.py` **28%** (116/161 missed), `queue.py` **39%** (62/101), `packet.py` **46%** (51/94), `templates.py` **49%** (176/344). | **Medium** — it is developer tooling, not the engine or the served app, so the blast radius is contained | none |
| CG-06 | coverage-gap | `src/automtg/engine/effects/ops_mana.py` | **73%** (8 of 30 statements missed) — the lowest-covered module in the **rules engine** itself, where everything else clears 84%. Rules code with untested branches is a different class of risk from tooling. | **Medium** | none |
| CG-04 | coverage-gap | `frontend/` | No coverage provider existed at this commit, so no frontend coverage number has ever been produced. Installing `@vitest/coverage-v8@3.2.7` is what made measurement possible. | **Low** | none |
| OF-01 | oversized-file (>600) | 45 files | Full ranked list in *Oversized files*. Worst: `src/automtg/cards/loader.py` **3652**, `frontend/src/components/game/Table.tsx` **1742**, `src/automtg/engine/effects/ops_board.py` **1619**, `src/automtg/engine/characteristics.py` **1583**, `src/automtg/engine/primitives.py` **1470**. | **High** for `loader.py` / `Table.tsx` (central, no per-module coverage floor); **Medium** for the rest | CG-04 for frontend files — no coverage baseline to split against |
| DC-01 | dead-code | 20 symbols in `src/automtg/` | Public (non-underscore), defined exactly once, **zero references** anywhere in `src`, `tests`, `scripts`, `frontend/src`, `frontend/e2e`, `frontend/tests`. Decorated symbols (FastAPI routes) excluded. Full list in *Dead-code candidates*. | **Low** individually | Must be confirmed against the `register()` dynamic dispatch in `src/automtg/engine/effects/__init__.py` — see `UV-02` |
| SD-01 | stale-doc | `docs/testing.md` | Every suite count in its table is wrong. Claimed → measured: unit **395 → 3460**; cards **3513 → 6092 (+3958 skipped)**; server **287 → 300**; frontend **1005 → 1152**; stories **328+18 → 365 desktop / 22 handheld**. Only `tests/ai` (**75**) is correct. | **Low** — documentation only | Re-run suites after FT-01/FT-02 so recorded numbers come from a green tree |
| SD-02 | stale-doc | `.dockerignore` | Excludes `legacy-frontend`, a path that does not exist: `ls legacy-frontend` → no such file; `git ls-files legacy-frontend` → 0 results. | **Low** — dead exclusion line | none |
| LP-01 | leftover-prototype | `frontend/tests/zzrepro.test.tsx`, `zzrepro2.test.tsx` | **RESOLVED DURING THE AUDIT — by another session, not by me.** When measured they were **untracked** (`git status` → `??`), **not gitignored** (`git check-ignore` → no match), mtimes `Aug 24 23:58` / `Aug 25 00:01`, and their bodies were `console.log` traces of deck-catalogue keyboard navigation with **no assertions at all in zzrepro2** — debugging scratch, not tests. They were the sole cause of `FT-01` and `FT-02`. Both files are now gone. | **Resolved** | none |
| LP-02 | leftover-prototype | `frontend/src/components/game/GroupDial.tsx:13` | Comment: *"it was the prototype's name for exactly this control, carried into the…"* — a prototype name surviving into shipped code. | **Low** — rename only | CG-02 (module untested) |
| LP-03 | leftover-prototype | `frontend/src/components/game/OpponentBoard.tsx:18` | Comment: *"this is a temporary overlay that…"* — self-declared temporary code on a shipped surface. | **Medium** — "temporary" with no replacement designed | none |
| LS-01 | lint-suppression | `frontend/src/components/lobby/HomeScreen.tsx:323` | The **only** lint diagnostic in tracked source: `lint/correctness/useExhaustiveDependencies` — *"This hook specifies more dependencies than necessary: sel"* on `useLayoutEffect(() => { refollowCursor(); }, [sel])`. A warning, not an error. Sits in the deck-selection screen, the surface of field bug `FB-01`. | **Medium** — changing effect deps on cursor-following code can move focus behaviour | Diagnose `FB-01` first; the extra dep may be load-bearing |
| LS-02 | lint-suppression | `pyproject.toml` → `addopts = "-q"` | `verify.py` also passes `-q` (`python_stages()`), making `-qq`, which **suppresses pytest's summary line**. The gate's own output never shows how many tests ran. Confirmed: with `-o addopts=` the same run prints `3460 passed`; without it, nothing. | **Low** | none |
| LS-03 | lint-suppression | `src`, `scripts`, `tests` | 22 `# noqa`: 8×`F401`, 8×`E402`, 3×`RUF001`, 3×`E731`. Plus 6 project-wide ruff ignores in `pyproject.toml` (`E501`, `B008`, `RUF012`, `SIM108`, `UP042`, `SIM103`) and 3 `per-file-ignores` blocks. **Every config-level ignore carries a written rationale.** | **Low** — justified; recorded for completeness | none |
| LS-04 | lint-suppression | `frontend/src`, `frontend/e2e`, `frontend/tests` | 19 `biome-ignore` comments across 17 files. Zero `@ts-ignore` / `@ts-expect-error` in the entire frontend. | **Low** | none |

### Categories with no findings

- **duplicated-logic** — no confirmable instance. The strongest candidate,
  `frontend/e2e/handheldAssert.ts` (665 lines) versus its stated origin
  `mockups/handheld/assert.js` (212 lines), shares **zero function names**; the port
  diverged rather than duplicating. Reported as checked-and-cleared. See `UV-03`.
- **TODO/FIXME/HACK/XXX markers** — 4 matches, all in
  `src/automtg/cards/authoring/packet.py` (lines 77, 267, 272, 285), and all the
  literal dataclass field name `todo:`. No debt markers anywhere in the codebase.
- **broken documentation links** — every relative link in `README.md`, `docs/*.md`
  and `docs/adr/*.md` resolves to a file that exists. Checked exhaustively.

## Field-reported defects (playtesting during this audit)

**14 defects reported.** 3 root-caused with certainty (`FB-05`, `FB-10`, `FB-11`),
11 traced to a surface but not isolated.

Reported by the user while the audit ran. **None is covered by any passing test** —
which is this audit's central finding. Root cause given only where verified.

| ID | Report | Root cause / status | Evidence |
|---|---|---|---|
| FB-05 | Same opening hand every game — seed isn't random | **ROOT CAUSE CONFIRMED** | `src/automtg/server/sessions.py:432` — `seed=0 if seed is None else int(seed)`. An unseeded game gets the constant **0**. `lobby.py:235` defaults `Pod.seed = None` and `lobby.py:726` passes it straight through, so every game dealt without a typed seed is byte-identical. |
| FB-10 | L2 triggers Steam Deck's native browser right-click | **CONFIRMED binding conflict** | `frontend/src/input/buttons.ts:104` maps `z: "l2"`; `Table.tsx:1133` notes *"`L2` was advertised by the hint bar and bound to nothing"*. On a Deck in gaming mode the shoulder arrives as a **keyboard** event — `buttons.ts:115-116` already special-cases `PageUp`/`PageDown` for exactly this reason — and the stock template's L2 is a right-click. Needs a different button. |
| FB-02 | `400: unknown action id 'a1-play_land'`, then jumps to combat | **Partially traced** | Raised at `sessions.py:276`. Action ids are **positional** — `sessions.py:238`: `f"a{index}-{action.kind.value}"` — rebuilt from scratch on every `_refresh_actions()` and carrying **no version stamp**, so a click against a stale list is indistinguishable from an invalid one. The specific race is not isolated. |
| FB-01 | Trapped in deck selection: entering the Name/Fastest/… dropdown, or moving left off the close button | **Not isolated** | Surface is `DeckCatalog.tsx` + `ChoiceCombo.tsx`. `ChoiceCombo.tsx` has **no test or story** (`CG-02`). `LS-01` is on the same screen. The two untracked scratch files (`LP-01`) show this was already under investigation. |
| FB-04 | L1 fully quits the game | **Not isolated** | `Table.tsx:1087` binds `onPad("l1", () => stepGroup(-1))` — a region step, not a quit. The only quit path is `GameRoute.tsx:51` `navigate("/", { replace: true })`, reached via `Table`'s `onQuit` prop (`Table.tsx:1537`, `:1739`). How L1 reaches it is **not established** — flagged rather than guessed. |
| FB-06 | B during combat closes the game to home | **Not isolated; `Table`'s own handler is innocent** | `Table.tsx:747-796` `back()` is a strict unwind that returns `false` at the bottom and does nothing — its docstring says *"it never quits from the top"*, and the code matches. The quit therefore comes from a handler **outside** `Table`. `GameRoute.tsx` has no test (`CG-02`). |
| FB-03 | Focusing a card in the action panel shows no enlarged preview (hand cards do) | **Not isolated** | `CardHold.tsx` / `CardPreview.tsx`. `CardHold.tsx` has **no dedicated test or story** — it appears only inside `Table.stories.tsx` (`CG-02`). Note `e2e/action-panel.spec.ts:463` *"hovering a row fills the preview"* **passes**, so mouse hover works: the defect is specific to the focus/controller path, which is untested. |
| FB-07 | Hover ring misaligns with hand cards after they lift | **Not isolated** | `frontend/src/state/useHandLift.ts` — **no test, no story** (`CG-02`). Ring geometry lives in `input/cursor.ts`; a lift that moves the card without re-measuring the ring matches the symptom. |
| FB-08 | A/Y does not read cards to full screen on hover | **Not isolated** | `Table.tsx:1090-1120` binds `onPad("y", …)` → `setHeldCard(ref.id)`, guarded by `parseStop(getCursor()).kind === "card"`. Renders through `CardHold.tsx` — untested (`CG-02`). |
| FB-09 | Focus cannot pass the disabled Attack button between "Skip attackers" and "All attackers" | **Same surface as FB-11; mechanism not fully isolated** | `ActionPanel.tsx` (1277 lines, `OF-01`). The button between the two reachable controls is the same stop-less `commit` button as `FB-11`, and it is also `disabled={disabled \|\| staged.length === 0}` (`:1210`). Whether the ring *stops at* it or *fails to route around* it was not determined — flagged rather than guessed. The e2e cases that assert exactly this (`action-panel.spec.ts:107-121`, `combat-confirm` enabled/disabled) are among the permanently skipped ones (`CG-01`). |
| FB-11 | The Attack button cannot be focused even when enabled | **ROOT CAUSE CONFIRMED** | `input/stops.ts:44` — `actionAttrs(id)` returns `{"data-action-id": id, "data-stop": "act:<id>"}`, and `stops.ts:22` states the rule: a control is a ring stop only if it carries `data-stop`. The combat confirm button (`ActionPanel.tsx:1207-1228`) spreads **no `actionAttrs`** and carries **no `data-stop`** — its only identity is `data-testid="combat-confirm"`. Both siblings do carry it: the skip button (`:1234`, `{...actionAttrs(finish.id)}`) and the other commit slab (`:1252`, `{...actionAttrs(commit.id)}`). So the ring never registers "Attack"/"Block" as a stop, enabled or not. Note it legitimately has no *action* id — `onDeclare` submits a whole declaration rather than one server action — so the fix is a `data-stop`, **not** an `actionAttrs` spread. |
| FB-13 | Commander does not flip to "Ready" when its mana becomes available, unless the pointer is over the commander orb | **Not isolated; surface identified** | `CommandZone.tsx:70-71` — `commanderState(card, castable)` returns `{key:"ready"}` **only** when `castable` is true, and `castable` is derived from `playableOids` (`:303`, `:341`: *"only when the server says so — `playableOids` is built…"*). The symptom — correct only while hovering — points at the recompute being driven by a pointer-triggered re-render rather than by the state version. ⚠ `CommandZone.tsx` is one of the **16 files a concurrent session modified mid-audit** (+30 lines), so these line numbers are from the working tree, not from `0161573`. |
| FB-14 | Commander cannot be summoned from the player orb at Steam Deck resolution — focus + A does nothing | **Not isolated; a missing stop is RULED OUT** | Unlike `FB-11`, the plinth **does** register a stop: `CommandZone.tsx:175` — `data-stop={reachable ? stopId.card(card.oid) : undefined}`, with `reachable = card.zone === "command"` (`:151`). It is deliberately `aria-disabled` rather than `disabled` (`:190`) precisely so it stays focusable, and the click is gated by `clickable = castable && !disabled` (`:123`). **Suspect instead:** the region trap in `input/groups.ts` — the `orb` group is the CSS selector `.play__mine .mat__side` (`groups.ts:49`), so if the handheld layout renders the plinth outside that container the ring cannot enter it, and the trap is resolution-specific exactly as reported. **Not confirmed** — flagged for the fix session. Interacts with `FB-13` (same component) and `FB-12` (same trap mechanism). |
| FB-12 | Settings popover (bottom left: "Sound on", "Undo") unreachable by controller focus; mouse works | **Not isolated** | `Table.tsx:1128-1132` binds `onPad("menu", () => setCursor(stopId.tool("settings")))` — the ring is moved to the settings *button*, but the stops **inside** the opened popover are a separate question. `input/stops.ts:15` documents `tool:<name>` for "mute, full control, manual mana, undo, quit". Same class of defect as `FB-01`: a container the ring can enter but not traverse. |

**Six** of the fourteen field-reported bugs (`FB-01`, `FB-03`, `FB-04`, `FB-06`, `FB-07`,
`FB-08`) land in modules with **zero test coverage** (`CG-02`); two more (`FB-09`,
`FB-11`) land on the one surface whose e2e tests are permanently skipped (`CG-01`).
**Ten of the fourteen are controller/focus defects** — the input layer is the least
covered and most defective area of the codebase.

## Disposable mockup / prototype candidates

**Nothing was deleted.** Candidates for a human decision, each with the counter-argument.

| Path | Size | Why it looks disposable | Why it may not be |
|---|---|---|---|
| `mockups/` (whole tree) | 390 files, **108 MB** | Static HTML/JS design exploration. No build, test or runtime step consumes it. Already excluded from the Docker build context. | **47 comments in shipped `frontend/src` and `frontend/e2e` code cite specific mockup files as the source of a number or decision** (e.g. `ActionPanel.tsx:151`, `CardFace.tsx:6`, `CardPreview.tsx:61`, `HandFan.tsx:195`, `orb.spec.ts:2`, `layout.spec.ts:7`, `handheldAssert.ts:4`). Deleting orphans all 47. |
| `mockups/**/shots/` | 153 PNGs | Pure screenshots — most of the 108 MB, least referenced. Regenerable by opening the HTML. | Some READMEs embed them as the record of a design round. |
| `mockups/art/` + `mockups/fetch_art.py` | 67 JPGs + 1 script | Duplicates a subset of `data/art/`; used only by `05-planar-art.html`. | `fetch_art.py` re-downloads them; removal is reversible. |
| `frontend/tests/zzrepro.test.tsx`, `zzrepro2.test.tsx` | 2 files | **Clearest disposal candidate.** Untracked, assertion-free `console.log` traces that break two CI gates. See `LP-01`. | They are an in-flight investigation of `FB-01`. Confirm with their author first. |

`frontend/src/testing/scenarios.ts` (1008 lines) was assessed and is **not** a disposal
candidate: it is imported by the story suite that runs 365 passing tests.

## Unverified / ambiguous — flagged rather than guessed

- **UV-01** — RESOLVED. Both Playwright projects completed: chromium `3 failed,
  14 skipped, 107 passed (20.4m)`; handheld `15 passed (1.1m)`. Note the handheld
  project runs only **15** tests against `docs/testing.md`'s claim of 112 e2e tests
  overall, and it is the project the docs call the only CI gate on the handheld floors.
- **UV-02** — the 20 `DC-01` dead-code candidates are **candidates only**. The engine
  registers effect ops dynamically (`register()` in `engine/effects/__init__.py`, which
  `pyproject.toml` grants an `E402` exemption for). A grep-based reference count cannot
  see dispatch through a registry. Each needs hand-confirmation.
- **UV-03** — duplication between `handheldAssert.ts` and the `mockups/*/assert.js`
  files was checked by function-name intersection only (result: empty). Semantic
  duplication of the 16/44/96 pixel floors across e2e, CSS and Storybook config is
  plausible but **not** confirmed.
- **UV-04** — `tests/cards` skips **3958** tests. Sampled skip reasons are per-card
  conditionals (`"zodiac_ox produces no mana"`, `"… has no activated abilities"`) —
  correct conditional sub-tests, not disabled coverage. Not counted as a coverage gap.
  The full 3958 were not individually reviewed.
- **UV-05** — the 160-game arena stage and the live-uvicorn stage from `verify.py` were
  **not** run. They were deferred to keep CPU contention off the timing-sensitive
  Playwright run, and by the time it finished the working tree was no longer the tree
  being audited (see the concurrency warning above), so running them would have
  measured different code. Their status at `0161573` is unknown.
- **UV-06** — RESOLVED for Python: full-suite coverage completed at **91%** (see `CG-05`,
  `CG-06`). **Frontend coverage was still not produced.** `@vitest/coverage-v8` is now
  installed and `npx vitest run --project=unit --coverage` will work, but it was not run
  — by the time the slot was free the working tree was no longer the tree being audited
  (see the concurrency warning above), so any number would describe different code.
  `CG-02`'s frontend gaps are therefore structural (no referencing test file), not
  percentage-based.
- **UV-07** — root causes for `FB-01`, `FB-02`, `FB-03`, `FB-04`, `FB-06`, `FB-07`,
  `FB-08`, `FB-09`, `FB-12`, `FB-13`, `FB-14` are **not** established. `FB-05`, `FB-10` and
  `FB-11` are confirmed.

## Appendices

### Untested frontend modules (CG-02)

Zero references from any `*.test.ts(x)`, `*.spec.ts` or `*.stories.tsx`:

```
frontend/src/audio/sfx.ts
frontend/src/components/game/CardHold.tsx          <- FB-03, FB-08
frontend/src/components/game/ChoiceCombo.tsx       <- FB-01
frontend/src/components/game/GroupDial.tsx         <- FB-04
frontend/src/components/game/OpponentBoard.tsx     <- LP-03
frontend/src/components/game/SeatIcon.tsx
frontend/src/components/lobby/Mark.tsx
frontend/src/components/lobby/doorArt.tsx
frontend/src/components/ui/ActionIcon.tsx
frontend/src/components/ui/ControllerPanel.tsx
frontend/src/components/ui/SchemePicker.tsx
frontend/src/motion/springs.ts
frontend/src/screens/DeckDossierRoute.tsx
frontend/src/screens/GameRoute.tsx                 <- FB-04, FB-06
frontend/src/screens/HomeRoute.tsx
frontend/src/screens/NotFound.tsx
frontend/src/screens/PodRoute.tsx
frontend/src/state/useHandLift.ts                  <- FB-07
frontend/src/state/useHandheld.ts
frontend/src/state/useImages.ts
```

`CardHold.tsx` appears only indirectly, inside `Table.stories.tsx`.

### Dead-code candidates (DC-01) — unconfirmed, see UV-02

```
src/automtg/ai/action_space.py:324          decision_kind_of
src/automtg/ai/action_space.py:328          creature_power
src/automtg/cards/authoring/templates.py:953 sentence_patterns
src/automtg/cards/images.py:128             normal_url
src/automtg/engine/actions.py:241           chosen_refs
src/automtg/engine/actions.py:244           chosen_values
src/automtg/engine/carddef.py:788           color_set
src/automtg/engine/characteristics.py:102   printed_chars
src/automtg/engine/characteristics.py:976   effective_toughness
src/automtg/engine/combat.py:420            remove_attacker
src/automtg/engine/effects/selectors.py:963 sorted_candidates
src/automtg/engine/game.py:1267             hand_size_limit
src/automtg/engine/game.py:1271             target_ref
src/automtg/engine/legality.py:1411         creature_can_attack
src/automtg/engine/mana.py:174              total_required
src/automtg/engine/primitives.py:1469       controlled_by
src/automtg/engine/rng.py:55                spawn
src/automtg/engine/state.py:337             maybe_obj
src/automtg/engine/state.py:471             objects_in
src/automtg/engine/state.py:688             sorted_oids
```

### Oversized files (OF-01) — >600 lines, shipped code, mockups excluded

| Path | Lines |
|---|---|
| `src/automtg/cards/loader.py` | 3652 |
| `frontend/src/components/game/Table.tsx` | 1742 |
| `src/automtg/engine/effects/ops_board.py` | 1619 |
| `src/automtg/engine/characteristics.py` | 1583 |
| `src/automtg/engine/primitives.py` | 1470 |
| `src/automtg/engine/legality.py` | 1419 |
| `src/automtg/engine/combat.py` | 1390 |
| `src/automtg/engine/costs.py` | 1341 |
| `frontend/src/components/game/ActionPanel.tsx` | 1277 |
| `src/automtg/engine/game.py` | 1272 |
| `src/automtg/engine/triggers.py` | 1208 |
| `src/automtg/engine/effects/ops_cards.py` | 1080 |
| `frontend/src/testing/scenarios.ts` | 1008 |
| `src/automtg/engine/structs.py` | 972 |
| `src/automtg/engine/effects/selectors.py` | 965 |
| `src/automtg/cards/authoring/templates.py` | 959 |
| `src/automtg/cards/proxy.py` | 921 |
| `src/automtg/engine/carddef.py` | 919 |
| `frontend/src/input/pad.ts` | 912 |
| `frontend/src/components/game/Table.stories.tsx` | 894 |
| `src/automtg/cards/authoring/verify.py` | 831 |
| `src/automtg/engine/mana.py` | 819 |
| `frontend/src/logic/events.ts` | 814 |
| `src/automtg/server/lobby.py` | 792 |
| `tests/cards/test_proxy.py` | 787 |
| `src/automtg/engine/effects/values.py` | 776 |
| `frontend/e2e/cycle3.spec.ts` | 764 |
| `src/automtg/engine/turn.py` | 762 |
| `src/automtg/engine/stack.py` | 752 |
| `src/automtg/cards/schema.py` | 732 |
| `tests/cards/test_every_card_works.py` | 699 |
| `src/automtg/engine/state.py` | 690 |
| `tests/unit/test_saga.py` | 688 |
| `frontend/tests/components.test.tsx` | 687 |
| `frontend/e2e/pod.spec.ts` | 681 |
| `frontend/src/input/cursor.ts` | 677 |
| `frontend/e2e/action-panel.spec.ts` | 671 |
| `frontend/src/components/lobby/HomeScreen.tsx` | 665 |
| `frontend/e2e/handheldAssert.ts` | 665 |
| `tests/unit/test_delayed_object_reference.py` | 644 |
| `tests/unit/test_monarch.py` | 643 |
| `src/automtg/server/routes.py` | 623 |
| `tests/unit/test_goad.py` | 621 |
| `frontend/src/logic/zoomFit.ts` | 608 |
| `frontend/src/components/game/FxLayer.tsx` | 605 |

## Out of scope: one feature request received

During the audit the user also asked to **make the `X` button show an opponent's board,
the same as clicking their orb does today**. That is a change request, not debt, and
this audit made no source changes — recorded here so it is not lost.
