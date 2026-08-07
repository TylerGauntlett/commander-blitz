## Bugs

### Fixed

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
