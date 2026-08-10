## Bugs

### Fixed

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

  The two cards that stay silent are **Aesi** and **Horn of Greed**, and neither is a
  landfall card: both read "whenever you *play* a land". Cultivate *puts* a land onto the
  battlefield, which is not playing one, so under MTG rules they correctly do not trigger.
  They remain `land_played` triggers. Changing that is a two-line data edit if the deviation
  is ever wanted.

  Genuinely broken on that path and now fixed: the land drop was counted *after* the ETB
  fired, so a landfall trigger counting drops this turn read a stale value; and
  `op_search_library` / `op_return_from_graveyard` never set `obj.controller`, so any
  cross-player put evaluated `controller: "you"` against the owner instead.
