---
name: extend-dsl
description: Add the engine and DSL support that unblocks cards the card pipeline could not express — a new effect op, cost, keyword, continuous effect, decision kind or event, plus its unit test and any UI work. Use when asked to implement a Magic mechanic (cycling, crew, flashback, convoke, ward, modal spells), to clear an entry in docs/unsupported-cards.md, or to make an unsupported card expressible. The counterpart to /author-cards.
---

# Extending the DSL

`/author-cards` writes cards it can express and records the ones it cannot as gap
records. This skill picks one of those capabilities and builds it, so the next
`/author-cards` run harvests every card that was waiting on it.

**One capability per run.** One mechanic, one `tests/unit/test_<mechanic>.py`, one
reviewable diff. Do not batch mechanics.

## Invocation

```
/extend-dsl cycling      a named capability
/extend-dsl              the top-ranked entry in docs/unsupported-cards.md
```

## 1 · Read the whole gap, not one card

```bash
python scripts/report_gaps.py --top 10
cat docs/unsupported-cards.md
ls data/authoring/gaps/            # the underlying records
```

Read **every** gap record naming your capability, not just the first. Seventy cards
say more about what the mechanic really needs than one does — typecycling and plain
cycling are the same missing cost with different effects, and a design driven by
only one of them gets rebuilt.

Also read `docs/card-dsl.md` (the DSL reference) and `docs/rules-coverage.md`
(what is deliberately not modelled — if your capability is listed there, say so
before building, because that was a decision).

## 2 · Route to a tier, and say which before writing code

The tiers are ordered by cost. **Justify skipping a cheaper one.** The most common
way to over-build here is reaching for a new `DecisionKind` when an existing
`ask_*` helper composes.

> Fact or Fiction needs *an opponent* to split a pile of cards, and it introduced no
> new decision kind. `op_two_piles` composes `ask_objects(...)` from
> `src/automtg/engine/effects/context.py` with the player argument set to the
> opponent, because `ask_objects` always took an arbitrary player. "Somebody else
> decides" was free.

### Tier A — a new op composing existing primitives

The common case, and the whole job for most mechanics.

1. `src/automtg/engine/effects/ops_*.py` — the function, decorated
   `@register("name")`. Make it a **generator** if it needs a decision; `yield` from
   an `ask_*` helper in `effects/context.py`.
2. `src/automtg/cards/loader/effects.py::_validate_effect` — a guard for required sub-keys.
   House style, alongside the existing guards for `create_token`, `add_mana`,
   `delay` and `animate`. Without it a malformed card fails at runtime instead of at
   load time, which is the difference between a test failure and a broken game.
3. `tests/unit/test_<op>.py` — see §3.
4. `docs/card-dsl.md` — a row in the op table, **the "N of them" count above it**,
   and a section for anything non-trivial. `card-dsl.md` is the **current
   reference only**: say what the op, key, cost, trigger or condition *is* — its
   parameters, defaults, constraints, load-time refusals, an example card, and the
   near miss an author might reach for instead — once, in the present tense. When
   you change something already documented, rewrite its entry to describe the new
   behaviour; do not append "it used to…" or "is now…" beside the old text.
5. History goes elsewhere. What a capability used to do, the bug you fixed, what
   you renamed or removed, and which card motivated the work go under the matching
   heading in `docs/dsl-changelog.md` (create the heading if it is new; it mirrors
   `card-dsl.md`'s headings). The full write-up — tier, what was built, tests —
   goes in `docs/completed-features.md`; what is and is not modelled goes in
   `docs/rules-coverage.md`.
6. **Server: nothing. Frontend: nothing.** Verified — see §5.

### Tier B — a new continuous effect

Tier A, plus:

- `src/automtg/engine/structs.py` — a `TempEffect.kind` and its fields, and
  `to_dict`.
- `src/automtg/engine/primitives.py` — the primitive. One rules-relevant thing, and
  it asks no questions; deciding is the effect layer's job.
- `src/automtg/engine/characteristics.py::_compute` — where the layer sits, which is
  the whole design question. `animate` had to run *before* every static, because it
  replaces base P/T and anything later would be cancelled by it rather than added
  to it.

### Tier C — a new `DecisionKind`

Only when no `ask_*` helper composes. Say why not.

`engine/enums.py` → `engine/actions.py` (`GENERATOR_DECISIONS`, if a suspended
effect generator drives it) → `engine/legality.py::_choice_actions` →
`engine/game.py::apply` → a new `ask_*` in `engine/effects/context.py` →
**`src/automtg/cards/authoring/verify.py`'s auto-answer table.**

That last one is not optional. The behaviour gate answers decisions automatically;
a kind it cannot answer hangs the verifier, which breaks `/author-cards` for every
card, not just yours.

Optionally one line in `frontend/src/logic/labels.ts` `DECISION_PROMPTS` — the
frontend's `PromptDialog` is generic over the pending decision and already renders
unknown kinds, so this is polish.

### Tier D — a new `EventType`

**The only change that genuinely forces frontend work**, and the only one that will
not fail a test if you skip it.

`src/automtg/engine/events.py`, then both of:

- `frontend/src/logic/labels.ts::describeEvent` — the event as prose in the log
- `frontend/src/logic/events.ts::beatsFor` — timing, sound and visual effects

Both have a `default` fallthrough, so an unnarrated event is silently dropped rather
than crashing. Nothing will tell you. Check it deliberately.

### Tier E — a new API field

Only if the mechanic must reach the UI as data. Four files and a test:
`src/automtg/server/schemas.py` → `src/automtg/server/routes.py` →
`frontend/src/api/types.ts` → the consuming component → `tests/server/test_*.py`.

Note the server needs **no** change for a new op, keyword, counter type, decision
kind or action kind: game state is serialized generically by
`src/automtg/engine/serialize.py`, and `LegalActionDTO.kind` is a bare string the
client echoes back.

## 3 · The test is not optional

`tests/unit/test_<mechanic>.py`, in the house style — read
`tests/unit/test_animate.py` and `tests/unit/test_two_piles.py` first.

For engine work there is no expectation-as-test safety net; an authored card gets
re-verified through six gates on every test run, but a primitive gets exactly the
coverage you write.

The pattern:

- A module docstring that makes the **rules argument** — name the rule, say what
  would be wrong without this, and name the shipped card that is the witness.
  `test_pay_life.py` cites rule 118.4 and Adanto Vanguard.
- A local position helper returning `(game, oid)`, reused across tests.
- Assert on `game.legal_actions()` where the claim is about legality, and on
  `chars(state, oid)` where it is about the characteristic layer.
- `class Test<TheClaim>` — group by claim, not by method.
- Cover the boundary and the wearing-off, not just the happy path.

## 4 · Harvest, then re-report

The point of the change is the cards it unblocks.

```bash
python scripts/author_cards.py --tier templates --retry
```

If the mechanic also needs the importer to *read* the printed sentence, add a
template to `src/automtg/cards/authoring/templates.py`. Templates are all-or-nothing
by design: a card is produced only when every residual line is consumed, and an
unrecognised clause must fail the whole card rather than be dropped silently.
Without a template the cards stay in the agent tier and get picked up by the next
`/author-cards`, which is a fine outcome — just say which happened.

Then retire the gap records this change resolved and regenerate the report:

```bash
rm data/authoring/gaps/<resolved>.json
python scripts/report_gaps.py
```

## 5 · Gate

```bash
python -m ruff check src scripts tests
python -m pytest tests/unit -q
python -m pytest tests/cards -q
python -m pytest tests/server -q
python -m pytest tests/ai -q
```

`tests/cards` is the important one: it re-runs all six authoring gates over every
machine-authored card, so an engine change that quietly invalidated a card written
months ago fails here.

Then, **only if you changed anything under `frontend/`**:

```bash
cd frontend && bun run build && bun run lint && bun run test    # npm if bun is absent
```

A tier A or B change cannot affect the frontend, so running these is noise.

## 6 · Commit

Engine, tests, docs and the harvested cards together — the change and its evidence
belong in one commit. Name the capability and how many cards it unblocked. Never
push.

## Rules

1. **One capability per run.**
2. **Never weaken a gate to make a card pass.** If a card cannot demonstrate its
   behaviour, the card is wrong or the mechanic is incomplete. `verify.py` catching
   your work is the system functioning.
3. **Refuse what you cannot do exactly.** A template that half-reads a sentence
   makes a cheaper card than the printed one. The existing fetchland template fails
   Fabled Passage on purpose rather than dropping its second sentence.
4. If the capability turns out to need a rules subsystem the engine does not have
   (planeswalkers, sagas, transform — see `docs/rules-coverage.md`), stop and report
   the scope rather than starting it inside a card-unblocking run.
