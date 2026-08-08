# Playtest feedback — cycle 2

Written after playing games through the browser at 1600×950, two-player and
four-player, at all three narration speeds. `frontend/e2e/clarity.spec.ts` is new
and pins the surfaces this cycle added; `full-game.spec.ts` and `stacking.spec.ts`
still guard playability.

Cycle 2 closed every item in [cycle 1's list](playtest-feedback-01.md) except the
`NewGameScreen` deck picker, which that doc itself deferred until more than two
decks exist.

---

## What cycle 2 delivered

Ordered as the cycle-1 doc ranked them.

1. **The board has a horizontal centre and the hand owns the foot.** The action
   bar moved out of a fixed 420px column beside the hand and into the right rail
   under the card preview (widened 268 → 304px). The hand now spans the full
   width and its fan cap went 760 → 1180px. Opponents centre rather than
   left-pack, and their mats share the row (`flex: 1 1 0`) instead of each
   demanding 420px — at three opponents that rigid minimum came to 1260px against
   ~1024 available, so the third player used to scroll off the edge of a pod.
   Empty lanes collapse to a 30px strip (`.lane--vacant`) instead of reserving a
   full card height each, which was most of the dead space in the middle.

2. **Unplayable cards say why.** New `legality.unplayable_reason` walks the same
   gates `_priority_actions` walks and names the first one that closes:
   `priority` / `timing` / `land_drop` / `mana` / `targets`. It reaches the client
   as `hand_reasons` on `player_view` (viewer only, and only for cards that are
   actually blocked). Hovering a dimmed hand card now reads
   "Needs {2}{G} — you have {G}" or "Sorcery speed — your main phase only".

   The function necessarily restates logic the generators own, so
   `tests/unit/test_legality_reasons.py` pins the invariant that matters: a reason
   appears *exactly* when no action names the card. That test is what fails if the
   two ever drift.

3. **Mana is visible.** `costs.mana_availability` sends floating mana plus every
   untapped source, and the player orb draws one pip per mana. Payment is no
   longer silent: `tapped` and `mana_spent` were reclassified out of the `SILENT`
   set, so the lands that pay a spell flash as they tap.

   The payload is deliberately *not* a colour histogram. "{T}: Add {G} or {U}"
   and "{T}: Add {G}{U}" produce the same symbol union but differ by a whole
   mana, so each source keeps its own `options` list and an ambiguous one renders
   as a single split pip. `tests/unit/test_mana_availability.py` and
   `frontend/tests/mana.test.ts` both assert the pip count can never exceed what
   the board can actually produce.

4. **Card type is encoded on the largest channel.** `typeTone()` sits beside
   `frameTone()` and drives a `face--type-*` class that overrides the two stops
   the existing `.face` gradient already reads — so the paper changes colour and
   nothing else about the frame moves. Colour identity keeps the border,
   interaction state keeps the outer glow. A single-character glyph (▲ land,
   ◆ creature, ■ artifact, ✦ enchantment, » instant, ● sorcery, ★ planeswalker)
   goes in the title bar as the redundant channel.

   The doc's greyscale check was run: fills flatten to near-identical greys, and
   the glyphs still read. That is the glyph doing its job, and it is the reason
   the encoding is not colour-only.

   Precedence resolves an artifact creature as a *creature* and a creature-land as
   a *land*, matching `frameTone`. `.card--dimmed` became a flat scrim on
   `.face::after` rather than `saturate(0.55)` on the face, because a
   desaturating filter would drag a land's tan toward the neutral of some other
   type — it would corrupt the very channel it sits on.

5. **Triggers are announced.** `ability_triggered` gets the spotlight `spell_cast`
   already had, in blue and labelled TRIGGERED so it does not read as a cast, plus
   a flash on the source permanent. `describeEvent` gained the case it was missing,
   so triggers appear in the log too — previously they were in neither. The engine
   now puts `card` on the event, so it says "Scoured Barrens triggers" rather than
   "An ability triggers", which was the least useful sentence available in a
   format made of triggers.

6. **Combat arrows no longer run a permanent frame loop.** They measure on the
   events that can actually move an anchor — resize, scroll (captured, so inner
   lane scrolls count), and a change to what should be drawn — each firing a
   bounded 700ms rAF burst that outlasts the springs and then stops. An idle
   combat now costs nothing.

7. **The thinking indicator names the seat and the step.** `thinkingLabel(state)`
   reads "Edgar Markov AI — declare blockers" instead of a bare pulsing
   "Opponent thinking".

8. **The stack is a pile of cards.** `StackPanel` renders real `StaticCard` faces
   with each ply peeking out below the one above, and `CombatArrows` gained a
   fourth arrow kind that draws spell → target in violet. Anchors use
   `data-stack-sid`, deliberately not `data-oid`: a triggered ability borrows its
   source permanent's face, and that permanent is already on the battlefield
   carrying the same oid.

9. **Smaller things.** Rules text centres in its box rather than pinning to the
   top. Tapped permanents take a landscape footprint (`.card--tapped` plus a
   matching `CardStack` container), so a lane of tapped lands reflows instead of
   each one lying across its neighbour. `g` / `e` / `c` open the graveyard, exile
   and command zone — `Esc` closed the viewer and nothing opened it. Zone chips
   went from a 6px-tall target to a real button. Commander tax renders as a
   `CMD +N` chip, and the server now sends the computed cost so the client never
   has to know about the ×2. Sound is synthesised with WebAudio — no binary
   assets — behind a mute toggle that defaults to off.

### Found while playing, not on the list

- **Every land wore a "0/0".** On the battlefield the server sends *derived*
  characteristics, and those are `0` rather than `null` for a permanent with no
  P/T, so `statLine`'s null check never fired. It now checks for the Creature
  type.
- **The hand clipped through the bottom edge** at 950px once it had seven cards:
  the fan's droop grows with the square of a card's distance from centre and was
  unbounded. Capped, with matching room in `.hand`.

---

## Cycle 3 — ranked by impact

### 1. Two surfaces still show the same combat decision

During declaration the action bar shows "Done blocking" while `CombatPanel`
shows "No blocks" — the same underlying `finish_declaration`, side by side now
that the bar is in the rail. This is not the duplicate-`data-action-id` bug cycle
1 fixed: the panel's buttons carry no action id, which is exactly why the bar
*must* keep rendering them. [Table.tsx](../frontend/src/components/game/Table.tsx)
guarantees at the top that "the button in the action bar always exists", and
`full-game.spec.ts` fails the moment a decision has no `data-action-id` anywhere.

I tried standing the bar down for combat the way it stands down for modals, and
three e2e specs deadlocked immediately — the honest signal that the bar is
load-bearing, not redundant.

**Try:** give `CombatPanel`'s buttons the real `data-action-id` / `data-action-kind`
and *then* stand the bar down. The skip button already holds `finish.id`; the
confirm button is a composite that posts a staged set to `/declare` and needs a
decision about what identity it claims. That is the piece of design work this
item actually is.

### 2. The type palette is honest but the greyscale fallback is thin

Every body fill sits at roughly the same lightness (L≈88%) by design, so the
greyscale board leans entirely on the glyph. That passes the check the cycle-1
doc set, but it means a monochrome display, a heavily colour-deficient viewer, or
a card half-occluded in a stack ply all reduce to one small character.

**Try:** vary lightness as well as hue across the seven type tones — lands
noticeably darker, instants lighter. The constraint is that the range must stay
clear of `.card--dimmed`'s scrim, or a dark type will read as disabled.

### 3. Opponent mats scroll internally in a four-player pod

Three mats at ~288px each wrap their lands onto several rows and outgrow the row
they sit in, so `.mat--compact .mat__lanes` scrolls. Nothing is lost, but a
permanent can be one scroll away in the zone you most need to survey, and there
is no affordance saying so.

**Try:** scale `OPPONENT_CARD_W` down with the opponent count (82 → ~66 at three
opponents). The type fills and glyphs added in item 4 survive small sizes far
better than the 5.6px type line they replaced, so this is a cheaper trade than it
was before.

### 4. The mana row does not say what a spell will cost

The orb shows what you have and the hover hint shows what a *dimmed* card needs,
but a castable card says nothing about what casting it will leave you with. That
is the interesting question in a turn with two plays in it.

**Try:** dim the pips a hovered card would consume. The engine already solves
payment exactly — `solve_payment` returns which sources it would tap — so this
wants that answer serialized per action rather than a client-side guess. Guessing
here would be the same mistake the `options` payload exists to avoid.

### 5. The spotlight still renders a text box, not a card

`Beat.spotlight` has carried `cardId` and `controller` since cycle 1 and
`FxLayer` still draws only the name. Now that the stack panel proves `StaticCard`
works away from the battlefield, the spotlight could show the real card.

### 6. `Beat.text` is produced and rendered nowhere

`beatsFor` writes a play-by-play line for every beat; `EventTicker` ignores it and
re-derives its own lines from raw events through `describeEvent`. Two independent
switches over the same event types, which is how triggers came to be missing from
both. Cycle 2 added the missing cases to `describeEvent` rather than fixing the
duplication.

**Try:** feed the ticker from the beat queue and delete `describeEvent`, or delete
`Beat.text`. Either is better than keeping both in sync by hand.

### 7. Smaller things

- The card preview panel can take 460px of the right rail, squeezing the action
  bar into the remainder. It should cap its height.
- `mana_spent` narrates as "You pays {2}{G}" — `beatsFor` has no verb agreement,
  unlike `describeEvent`, which grew a `viewerSeat` parameter for exactly this in
  cycle 1. Same duplication as item 6.
- Sound has one voice per event class and no variation, so a five-land turn plays
  the identical click five times. A few cents of random detune would fix it.
- `mana_availability` is recomputed for every player on every request. It is a
  handful of microseconds today, but it walks the whole battlefield per player
  per response and nothing caches it.
- `isWounded` in `cardStyle.ts` is still exported and still unused.
- Turns progress 2x faster than expected as a turn seems to be counted per play (ie i take turn 1, opponent takes turn 2, my next turn shows turn 3. This should be turn 2 as a "turn" is after everyone has preformed an action that turn)
- "All Attack" button to quickly select all monsters. Similar an "All Defend" which picks sensible defenders for each attacking card (ie try to first pair cards that will not die and kill the opponent, then those that will not die but can't kill the opponent, then those that will die but will kill the opponent, and finally those that will die and won't kill the opponent)
- 1x speed becoming .5x speed. 2x speed becoming 1x speed. The game moves too quickly

### 7. Commander Zone
- Commander zone should be more pronouced, showing your commander at all times
- The only way to cast your commander seems to be as a small button in the right sub menu

### 8. Land Colors
- All lands are idential colors. There should be some visual indicator to seperate them (ie islands being blue, mountians red, plains white, etc). These could be full size colored icons in the middle of the card
- Additional formatting are lands would be desirable like dropping the tap text as it provides no value

### 9. Card Select Modals
- Card selection models only show a single button of the card to select based on the name
- There is no way to know what the cards are that you are selecting
- Instead the entire card can be shown

### 10. Tap Costs
- Tap costs are shown as raw text (ie {1}{G}{U}) which isn't readable
- These can instead be shown as colored icons similar to the top card costs

---

## What the tests will and will not catch

`clarity.spec.ts` asserts that mana pips match their own formatted summary, that
a dimmed card produces a sentence rather than a reason code, that type tones and
glyphs are actually rendered, that no two rendered actions share an id across a
whole game, that no hand card hangs below the viewport, and that `g` opens the
graveyard. Those are the regressions that would silently undo cycle 2.

It still cannot see whether any of it *looks* right. The palette, the pip sizes
and the pile offsets were all chosen by taking screenshots and looking at them,
and the greyscale check in particular has no automated form — a `grayscale(1)`
screenshot has to be read by someone. Keep the capture spec.

One process note: the API server does not reload on change. Screenshots taken
against a server started before a `serialize.py` edit will show the old payload —
the stack pile appeared to render a placeholder for a full round of review before
the cause turned out to be a stale process rather than a bug.
