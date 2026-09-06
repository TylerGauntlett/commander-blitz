## Bugs

### Fixed

- **After keeping an opening hand, the board sometimes could not be clicked.**
  The opening hand stayed in the DOM, invisible, at the modal z-index with
  `inset: 0`, over a game that had gone on without it. `AnimatePresence`
  removes a child only once every `exit` inside it reports complete, and an
  opacity exit that started while the entrance was still in flight -- which
  is when a hand is kept -- was measured never to: the seven cards' first
  (`e2e/orb.spec.ts`, about one keep in two on a four-player pod), and the
  stage's own once the cards were out of the way. The stage and the prompt
  dialog now carry no `exit` at all: each `animate`s toward its closed look
  and calls `safeToRemove` on a timer, through a ref keyed on presence alone,
  because `safeToRemove` is rebuilt on every state push and a timer restarted
  on each of them never fired while the AI pump was running. `StaticCard`
  takes `onSurface` so a card on a fading surface registers no exit of its
  own. Both surfaces mark themselves `data-closing` for the exit window, which
  `stopRoot` and the e2e prompt-clearing helper already read.

- **A pod game stalled until somebody reloaded, and the reload replayed the game.**
  Four faults in one twenty-five-line block of `useGame`. The long poll was a
  one-shot effect rather than a loop: a poll that times out comes back with
  the *same* version, `absorb` was skipped, nothing it depended on changed and
  it never ran again -- so an opponent who thought for longer than the 25 s
  ceiling left the waiting tab deaf, silently, until it was reloaded. It sent
  `?since=0` on every poll, so the one poll that did land after a reload got
  the whole event log back, appended it to the log a second time and narrated
  the entire game as beats; `event_cursor` had never been read. `GameRoute`
  passed a fresh session literal every render, so the effect was torn down and
  re-issued on every re-render with no `AbortController`, each abandoned poll
  parking a server thread for the full ceiling. And with two people at a table
  and an AI on the clock, both pumped it: each reply carried only its own
  call's events -- the POST routes read their `since` cursor *outside* the
  session lock -- so each screen missed the other's slices, and the
  wait-for-narration gate on one screen was defeated by the other's pump.

  The listener is now the same self-rescheduling loop as `usePod`, carries both
  cursors from the last response it absorbed, aborts on unmount, waits for
  narration to drain rather than re-issuing, and gives up on a 403 or 404
  instead of retrying forever. `absorb` trims a response against the cursor,
  so a reply that overlaps something already seen narrates nothing twice. The
  lowest human seat pumps an AI and everyone else listens; a listener whose
  poll times out takes over. The four POST routes read their cursor under the
  lock. `tests/useGame.test.tsx` pins the loop; `TestConcurrentMutations`
  pins the cursor.

- **A spell could pay its own mandatory additional cost by discarding itself.**
  601.2a moves a spell to the stack before any of its costs are paid, so a card
  can never be fodder for its own "discard a card". Legality priced the cost
  while the card was still in hand, though, so it counted itself: Bitter Triumph
  ("discard a card **or** pay 3 life") could eat the very spell being cast,
  which then never resolved, and a card whose hand held nothing else had the
  cost charge silently *nothing* -- a free Laughing Mad. `costs._discard_pool`
  now takes `source_oid` and excludes it. Cycling is unaffected (`discard_self`
  is its own flag) and an activated ability's source is on the battlefield, so
  excluding it from a hand pool is a no-op there.

  The knock-on was the bigger half: with the fix, a sandbox hand holding only
  the card under test leaves every mandatory discard unpayable, so
  `verify.build_sandbox` now deals a spare **land** beside it. A land and not a
  spell -- a castable card in hand keeps the player on priority while the card
  under test is on the stack, and 169 cards then fail with "never left the
  stack". Every authored `hand_size` counts the spare, which is why they read
  one higher than the printed card suggests.


- **Clicking Mind Stone sacrificed it.**
  Mind Stone reads "{T}: Add {C}" and "{1}, {T}, Sacrifice this artifact: Draw a
  card", and the panel showed one option. `legality._activate_actions` withholds
  a *tap-only* mana ability because the payment solver taps it automatically —
  correct for a Forest, wrong here, because it left the artifact with a single
  action, and `Table.onBoardCard` submits when a permanent has exactly one
  untargeted activation. The gesture that means "what can this do?" therefore
  spent the card. The suppression is now conditional: a permanent that offers
  something *besides* its tap-only mana ability offers both
  (`legality._offers_something_else`, gated on the new
  `PlayerState.offer_all_abilities`, which `GameSession` sets for human seats
  only — the heuristic agent scores every activation alike and would tap its
  rocks for nothing). A permanent whose only offer is the mana ability, or whose
  other ability is unaffordable, still belongs to the solver alone, so a board of
  lands grows no rows. `game._only_pass_or_mana` is deliberately *not* wired to
  the new flag: it already counts extra mana activations as nothing to
  accomplish, and hooking it in the way `manual_mana` is would stop every human
  at all thirteen steps of every turn.

- **The Auto/Manual mana and Full control toggles did nothing until the next
  action.** `GameSession.set_manual_mana` and `set_full_control` mutated the seat
  flag and called `_bump()`, but never `_refresh_actions()` — and `actions_for`
  serves the cached `_action_ids`. `POST /options` therefore answered with the
  action list from *before* the toggle, so a player who turned Manual mana on to
  see a rock's mana ability got the same list back and their next click did the
  same thing it would have done. Both setters refresh now.

- **Twenty-seven cards could never be activated at all.**
  `costs.mana_sources` collects only `Cost.is_tap_only()` abilities, and
  `legality._activate_actions` skipped *every* mana ability on the grounds the
  solver would handle it. A mana ability with any other cost therefore had no
  code path in the engine that could reach it: every Signet, Cabal Coffers,
  Magus of the Coffers, Prophetic Prism, Arcum's Astrolabe, Apprentice Wizard,
  the filter lands and the Vivid lands were permanents with dead text. Only
  `arcane_signet` is tap-only, so the four precons were unaffected and no test
  covered it; any imported Moxfield deck got inert rocks.
  `costs.offerable_mana_ability` is now the complement of the solver's own test,
  so the two cannot drift, and `legality` offers what the solver cannot use.

- **The kicked cast was unreachable by any gesture.**
  `legality._cast_options` emits unkicked first, and `Table.onBoardCard` took
  the *first* action matching the clicked target. Clicking a creature with Into
  the Roil selected therefore always cast it unkicked, silently spending the
  player's kicker decision for them. It was reachable only as one more row in
  the panel. Clicking now narrows the selection to every action that still
  matches and lets the panel ask the rest (`uiStore.narrowTargeting`).

- **X was never the player's choice.**
  `legality._cast_variant` stamped `mana.max_affordable_x` onto the action, so a
  Fireball was always cast for everything the board could pay. X is now a
  `choose_x` decision raised before the cost is paid, and legality's ceiling is
  only a gate on whether the spell appears.

- **A taxed `{X}` commander vanished from the legal list.**
  `max_affordable_x` was computed before commander tax and cost reduction were
  folded into the generic, so it returned a maximum the subsequent
  `solve_payment` then rejected — at every X including 0. It now takes
  `extra_generic`.

- **The foot rendered a second copy of every action id.**
  `Table`'s `choice-list` drew a `data-action-id` button per remaining action
  while `ActionPanel.playRows` drew the same ids, and `standDown` is only true
  for `isModalDecision`. Two controls, one id — exactly what the panel's
  invariant forbids. It escaped CI because no shipped card could reach the
  branch (`action-panel.spec.ts` also scopes its check to `[data-action-kind]`,
  which those buttons lacked) and manual mana reaches it immediately. The foot
  now only ever says what the click is for.

### Known, not fixed

- **Visual fidelity findings against the design rounds** -- the playable rim, the
  combat arrows, the tools under a modal, the stale preview, the ring and a
  descendant transform, and four density notes -- are kept with the rounds they
  came from, in [design-record.md](design-record.md#open-fidelity-findings).

- **A triggered ability with no legal target still resolves.**
  603.3d and 608.2b: a triggered ability that requires targets and can choose
  none is removed from the stack and does nothing.
  `game._choose_trigger_targets` returns `()` instead, and the ability resolves
  with an empty target list -- so every effect in it that does *not* read the
  target runs anyway. Found while authoring Gogo, Mysterious Mime: with the
  "If you do" rider written as a plain sibling of the copy, a lone Gogo with no
  other creature to copy was still asked the question and still got +2/+0,
  haste and attacks-this-turn-if-able, none of which the printed card gives it.

  Gogo works around it at the card level, with an `exists` condition on the
  `may` that gates the whole clause on there being a legal creature to copy.
  That is correct for this card and is not the general fix: any targeted trigger
  whose non-target effects are unconditional has the same hole. Fixing it
  properly means dropping such an ability at resolution, which would change
  behaviour for every targeted trigger in the pool and so wants its own run and
  its own re-collect.

- **The RL policy has never seen an equip action.** `ai/action_space.py` caps
  `ABIL_CAP = 2` and indexes `action.ability_index`, which counts *all*
  abilities including statics and triggers. Twelve cards (eleven Equipment plus
  `nezahal_primal_tide`) carry their activated ability at index 2 or higher, so
  it is silently dropped into `ActionTable.dropped`. Pre-existing and unrelated
  to variable costs; fixing it means indexing activated abilities separately,
  which shifts the action space and invalidates trained checkpoints.

- **Some cards appear several times in the action panel.**
  Six rows reading "Simic Charm / Instant / {G}{U}", and one Herd Heirloom ability listed
  twice. Nothing was duplicated: `legality._cast_variant` and `_activate_actions` emit one
  action per tuple from `enumerate_target_tuples`, so six targetable creatures are six
  legal casts of the one card in hand. The panel then drew each as a row — and for a card
  a row draws the *card* (name, type line, pips) and never the label, so the six ways to
  aim it were six identical rows. The `activate` rows did draw the label, whose only
  differing part is the trailing `-> Target` that `.act__name`'s ellipsis clips off.
  The collapse had to be presentational — deduplicating in `legality` is the Forest bug
  below, and that list is also the RL action space. So `logic/actionMatch.groupPlayActions`
  groups the play rows by `(kind, source, ability index, x, choice, base_label)` and the
  panel renders one row per group with a chip per target, the shape an attacker with
  several legal defenders already used. `base_label` is a new field on `Action` and on
  `LegalActionDTO`: the label without its target suffix, which is what tells a kicked cast
  apart from an unkicked one without parsing strings. The exactly-once id invariant holds
  the same way combat's does — the group row carries no `data-action-id`, its chips carry
  one each.

- **A spell with an optional target could never decline it.**
  `enumerate_target_tuples` honoured `spec.optional` only when there were *no* candidates,
  so the empty tuple was offered exactly when it was useless. Simic Charm's third mode
  gives your permanents hexproof and takes no target, which made that mode unreachable in
  any game with a creature on the battlefield. An optional spec now always contributes the
  empty choice — **last**, because `stack.push_trigger` and `suspend.cast_suspended` ask
  with `limit=1` and take `options[0]`, and a Shipbreaker Kraken whose "tap up to four
  target creatures" defaulted to tapping none is a different card. The cap eats candidates
  rather than the choice to decline, but never the last candidate.

- **When multiple lands are held in the hand at the same time, only the first 2 are playable.**
  `legality._land_actions` deduplicated by *card-definition* id, so a hand of Forests and
  Islands produced exactly two `play_land` actions. The client keys playability by object
  id, so every other copy rendered dimmed and undraggable. Now one action per hand object.
  `_cast_actions` had the same defect and the same fix.

- **The screen jumps significantly when hovering over multiple stacked cards.**
  `CardStack` animated `width` — a layout property — on an in-flow flex item, so opening a
  5-card stack widened it by ~440px, wrapped `.lane__cards` onto new rows, grew the mat and
  flickered its scrollbar, all played out over a spring. The container now keeps a fixed
  footprint and the members fan apart on transforms only, symmetrically about the centre,
  with the spread bounded so it never overflows into the mat's scroll area.

- **Cards are not deselectable when selecting a blocker.**
  Staging already existed and `/declare` already accepted a whole set, but the action bar
  posted each `add_blocker` straight to the server, and there is no inverse action — only
  Undo. (Committing one blocker onto a menace attacker could strand the declaration with no
  legal `finish_declaration` at all.) The bar now stages instead of committing, and
  `finish_declaration` submits the staged set. Attacking is a plain toggle rather than a
  cycle through defenders, clicking an attacker clears the blocks aimed at it, and board
  cards finally receive `selected` so any of it is visible.

- **Combat stages at the top of the page do not progress as turns take place.**
  Nothing to do with step naming — engine and client agree exactly. `.track__marker` was
  `z-index: -1` with no stacking context between it and the root, so the gold pill landed
  in the root's negative layer and painted *behind* the track's own background. The current
  step's label, coloured near-black to sit on that pill, went invisible with it. Fixed by
  isolating `.track__step`.

- **Tap or instant effects are too aggressively paused.**
  The engine auto-passed only when Pass was the *sole* legal action, and 11 of 13 steps
  grant priority with instants legal in all of them — so one instant in hand meant ~11
  forced Pass clicks per turn, on every player's turn. Human seats now stop only where
  passing is a real choice: something on the stack, your own main phase, or declare
  blockers. AI/RL seats are untouched. A **Full control** toggle in the action bar puts
  every window back. Clicks during narration now skip the animation instead of vanishing.

### Fixed, with a rules note

- **Play lands to the battlefield using other cards does not properly trigger landfall.**
  Landfall itself was already right: cards authored as `permanent_enters` + a Land filter
  (Tatyova, Rampaging Baloths, Zendikar's Roil, Tireless Provisioner, Avenger of Zendikar)
  fire on every route to the battlefield, because ramp goes through the same `move_object`
  → ETB. Cultivate gives one trigger, Explosive Vegetation two. That is now covered by
  tests, which it was not before.

  **Aesi was wrongly listed here as correctly silent, and was not.** Its printing is
  "Landfall — Whenever a land you control enters, you may draw a card" — the catalog
  agrees — so it fires off Cultivate like every other landfall card. The card was
  hand-authored from stale text and wired to `land_played`; a later pass refreshed its
  `oracle_text` from Scryfall but left the trigger and a phantom `trample` behind, so it
  printed landfall and behaved like a land drop. It is now `permanent_enters` + a Land
  filter, with the draw wrapped in `may`, and Ancient Greenwarden doubles it as it should.

  The one card that genuinely stays silent is **Horn of Greed**, which really does read
  "whenever a player *plays* a land". Cultivate *puts* a land onto the battlefield, which
  is not playing one, so under MTG rules it correctly does not trigger. It remains a
  `land_played` trigger, and that spelling is still worth keeping distinct.

  Genuinely broken on that path and now fixed: the land drop was counted *after* the ETB
  fired, so a landfall trigger counting drops this turn read a stale value; and
  `op_search_library` / `op_return_from_graveyard` never set `obj.controller`, so any
  cross-player put evaluated `controller: "you"` against the owner instead.

### Open, deferred deliberately

- **The mana row's pips are a hair smaller than every other pip.** `.pip` sizes from
  `var(--pip, 14px)` and `.mana-grp__any` from `var(--pip, 13px)`, and `--pip` is
  declared on `.face`, `.cmdslot`, `.acts__list` and `.deck__colors` — but *not* on
  `.orb`. So the orb's mana row is the one place both fallbacks are live, and the two
  elements in the same row disagree by a pixel.

  Harmonising the fallbacks would hide it rather than fix it. The real answer is to
  declare `--pip` on `.orb` and `.orb--compact` so the mana row sizes with the orb like
  everything else inside it, which is a visible change to a surface that has been tuned,
  so it wants its own pass. Found while auditing ancestor-dependent styling for the
  Storybook mount work; see `docs/frontend.md` ("Mounts").
