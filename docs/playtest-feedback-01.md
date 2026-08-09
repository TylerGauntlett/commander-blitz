# Playtest feedback — cycle 1

Written after playing full games through the rewritten client in a real browser
(`frontend/e2e/playtest.spec.ts` captures the screenshots; `full-game.spec.ts` drives a
2-player game to a result and a 4-player pod through the UI).

Cycle 1 delivered: card frames with real rules text, spring physics on drag and hover,
`layoutId` zone flights, identical-permanent stacking, combat arrows, a narration layer
with floating damage numerals and banners, the AI pump (`?ai_steps=1`) so opponents can
be watched instead of arriving pre-collapsed, a generic dialog covering every decision
kind, and keyboard shortcuts.

**Status of this list:** items marked *fixed in cycle 1* were found during the playtest
and fixed before shipping, because they blocked ordinary play. Everything else is input
for cycle 2, ranked by how much it costs the player.

> **Resolved.** Every cycle-2 item below has since been addressed, except the
> `NewGameScreen` deck-picker note in item 9, which this doc already deferred until
> more than two decks exist. See [playtest-feedback-02.md](playtest-feedback-02.md)
> for what each one turned into and where the design deviated from the suggestion
> here — notably item 8's arrow anchoring, and the combat-panel half of item 1,
> which turned out to be load-bearing rather than redundant.

---

## Fixed during cycle 1

These were found by playing and fixed immediately — recorded here so the next cycle does
not rediscover them.

1. **The mulligan dialog blacked out the hand it was asking about.** A flat
   `rgb(2 8 6 / 0.72)` backdrop plus a blur over the whole viewport left the seven cards
   you are deciding on barely legible. The backdrop is now a gradient that fades to near
   transparent over the hand, with no blur.
2. **Every legal action rendered twice.** `ActionBar` and `PromptDialog` both drew
   buttons for the same decision, so a modal decision produced duplicate
   `data-action-id`s and a row of unclickable buttons behind the backdrop. The bar now
   stands down when `isModalDecision(state)` is true.
3. **"Instant" speed still gated input.** A zero-hold beat still costs a React tick, so a
   200-event batch held the board busy — buttons flickering between enabled and disabled
   — for several hundred milliseconds. Instant now skips the queue entirely.
4. **Hand cards ran off the bottom edge at 720px.** The fan is now scaled by viewport
   height rather than clipped.
5. **The phase track was unreadable.** Future steps were `#3d4f46` on near-black felt;
   the only indicator of where you are in a 13-step turn was invisible. Contrast raised.
6. **The log said "You draws a card".** On every draw, which is most of the log.
   `describeEvent` now takes the viewer's seat and conjugates.
7. **Vite bound IPv6-only.** Vite's default `host: "localhost"` resolves to `::1` on
   Node 17+, so anything asking for `127.0.0.1` — Playwright's health check, curl, the
   engine's own CORS origin list — got connection refused against a running server.
   Pinned to `127.0.0.1`.

---

## Cycle 2 — ranked by impact

### 1. The board is mostly empty space, and the hand is the smallest thing on screen

At a 1600×950 viewport, roughly the middle third of the table is unused felt while the
hand — the zone you interact with most — is squeezed into the bottom strip and shares it
with a 420px action bar. The opponent's mat is a small box in the top-left with a wide
blank area beside it.

**Try:** give the play area a real horizontal centre (opponents' battlefields centred
rather than left-packed), let the hand span the full width, and move the action bar to a
right-hand rail or a compact strip so the hand is not competing with it.

### 2. There is no feedback for *why* a card is unplayable

Unplayable hand cards are dimmed (`filter: saturate(0.55) brightness(0.82)`) and that is
all. The player cannot tell "not enough mana" from "sorcery, and it is not your main
phase" from "no legal target". This is the single biggest clarity gap for someone
learning the format.

**Try:** the engine already knows — `costs.available_mana` and `can_pay_mana` exist. A
small "needs {2}{G}, you have {1}{G}" line on hover, plus a mana-available pip row near
the player orb, would close it. This likely wants a small server addition to expose
available mana per player in `player_view`.

### 3. Mana is invisible

`player_view` sends `mana_pool`, and nothing renders it. Lands tap during auto-payment
with no indication of what was spent. The player has no running sense of how much mana
they have or what a spell will cost them.

**Try:** a pip row on the player orb showing available mana (untapped sources by colour),
and flashing the specific lands that pay when a spell is cast — the `mana_spent` and
`tapped` events are already emitted and currently classed as silent noise in
`logic/events.ts`.

### 4. Card type is not encoded visually — only colour identity is, and only as a hairline

*Prompted by Yu-Gi-Oh! Eternal Duelist Soul (GBA), which colours the whole card stock by
type — yellow normal monster, orange effect, green spell, purple trap. A large-area fill,
legible across an entire field at 240×160, with no text involved.*

We do the opposite. [`frameTone()`](../frontend/src/logic/cardStyle.ts#L15-L25) maps
**colour identity** — not type — onto a 2px `border-color`, and every card shares one
`--stock` gradient body. Type appears only in `face__type`, sized
`calc(var(--card-w) * 0.068)`. Against the real card widths in
[Table.tsx:37-38](../frontend/src/components/game/Table.tsx#L37-L38) and
[HandFan.tsx:19](../frontend/src/components/game/HandFan.tsx#L19) that is 9.9px in hand,
7.1px on your own battlefield, and **5.6px on an opponent's**. So on a 4-player pod board —
exactly where scanning matters most — the only encoding of "creature vs land vs
enchantment" is a sub-6px string.

**Where the analogy breaks, and what to take anyway.** Yu-Gi-Oh gets away with one colour
channel because it has one axis: a trap is a trap, and nothing is a subtype of anything.
Magic has two axes that both matter at a glance — colour identity (can I cast it, what
does it trade with) and card type (what does it do, when am I allowed to play it). Porting
the scheme literally means spending the frame colour on type and losing colour identity,
which is the worse trade: that border has meant colour to every Magic player for thirty
years. Don't replace the channel — add one.

**Channel allocation.** Note the outer rim is already fully spoken for by
`--playable` / `--targetable` / `--staged` / `--attacking` / `--blocking`
([cards.css:238-278](../frontend/src/styles/cards.css#L238-L278)), so type cannot go there.

| Channel | Carries | Status |
| --- | --- | --- |
| Body / stock fill (largest area) | **Card type** | unused today — this is the EDS channel |
| Border | Colour identity | exists; too thin to survive 82px, thicken it |
| Outer glow | Interaction state | exists; do not touch |
| Corner glyph | Card type, redundantly | new |

**Try:** a `typeTone(card)` beside `frameTone` and a `face--type-*` class. `cardStyle.ts`
is pure by design and `CardFace` already composes its class list from it, so this is a
small change in three files with unit-testable logic. Pick the type palette *against the
five rim colours*, not just against each other — a green creature body inside a green
playable rim is precisely the ambiguity worth avoiding.

**Pair it with a glyph, not just a hue.** A small type mark in the title bar does a job a
fill cannot: it stays legible when the card is 82px and half-covered inside a `CardStack`
ply, where the fill is mostly occluded. Check it on a pod board, not on a hand card — the
pod is where a fill runs out first.

**Subtype shading: recommend against.** The second axis in Yu-Gi-Oh is small and closed.
Magic creature subtypes number in the hundreds and rarely change what you may do this
turn. Shading yields maybe three distinguishable steps and would spend a channel on the
least decision-relevant fact on the card. Spend it instead on the short list that does
change your options: legendary, token (dashed border, already there), commander (gold,
already there), attached/enchanted, aura vs static enchantment. That is a supertype-and-
state channel, not a subtype one.

**Watch the dim rule.** `.card--dimmed .face` is `filter: saturate(0.55) brightness(0.82)`
over the whole face. A saturated body fill makes dimming read much more strongly — good —
but the same filter will desaturate a land toward looking like some other type. Dimming
probably wants to become a frame overlay rather than a filter on the face.

This also partly serves item 2: a distinct instant body vs sorcery body answers "why can't
I play this right now" for one of the two common causes without any server work.

### 5. Triggered abilities are invisible

`ability_triggered` produces a ticker line and nothing else. In Commander, triggers are
most of what happens, and a trigger going on the stack is the moment the player most
needs to notice. The stack panel shows it, but the stack panel is a small left-rail list.

**Try:** promote triggers to a spotlight beat like `spell_cast` already gets, and flash
the source permanent.

### 6. Combat arrows are measured on a `requestAnimationFrame` loop

`CombatArrows` re-measures every anchor every frame while combat is live. It is correct
and it is simple, but it is a full DOM query plus `getBoundingClientRect` per arrow per
frame. On a wide pod board this will be the first thing to drop frames.

**Try:** measure on layout-settle instead — a `ResizeObserver` plus a listener on
framer's `onLayoutAnimationComplete`, falling back to rAF only while a spring is running.

### 7. Nothing shows what the opponent is *doing* while they think

The pump advances the AI one decision at a time and narrates the resulting events, but
between decisions the only signal is a pulsing dot labelled "Opponent thinking". A
decision that produces no events (passing priority) is completely silent, so several
seconds can go by with no visible reason.

**Try:** surface the opponent's current step from `state.step` in the thinking indicator
("Edgar — declare blockers"), and give priority passes a faint beat.

### 8. The stack is a text list, not a stack

`StackPanel` renders name + controller + targets as rows in the left rail. For a format
where responding to the stack is the skill, it should look like cards piled up, with the
targeting relationship drawn.

**Try:** render stack items as small `StaticCard`s in an overlapping pile, and extend
`CombatArrows` to draw spell→target lines as well as combat ones.

### 9. Smaller things

- The card face wastes vertical space: the rules box is bottom-aligned against the P/T
  row, leaving a gap under the type line on cards with little text.
- Tapped cards rotate but keep their layout footprint, so a tapped land overlaps its
  neighbour rather than the lane reflowing.
- `ZonePeek` has no keyboard route — `Esc` closes it, but nothing opens it.
- Graveyard and exile are only reachable through small chips on the orb; after a long
  game the graveyard matters and it is a 6px-tall target.
- The commander tax is in `player_view` and never shown. Casting a commander for the
  fourth time silently costs six extra mana.
- `NewGameScreen` only ever offers the two shipped decks against each other; with one
  opponent you always face Edgar. Fine now, worth revisiting if more decks land.
- No sound. A card thump and a damage hit would carry a lot of the Balatro feel cheaply.

---

## What the tests will and will not catch

`full-game.spec.ts` fails if any decision kind reaches the player with no rendered
action, which is the class of bug that makes the game unplayable. It cannot see any of
the above: every item here is a game that is playable but unclear. Screenshot review is
the only thing that found them, so the capture spec is worth keeping.
