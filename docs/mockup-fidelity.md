# Mockup fidelity

Where the running client and `mockups/05-planar-art.html` still differ, and which
of those differences are bugs.

The mockup is the design the client was themed against. It is not the
specification: several differences below are deliberate, made after the mockup
was drawn and for reasons the mockup could not have known about. **An audit that
files those as defects is worse than no audit**, so this file separates the two
and records the reason for every divergence. If you are about to "fix" something
here, check which section it is in first.

## Redoing the sweep

Run the client and the mockup side by side at **both** viewports the mockups were
verified at — 2560×1278 and 1600×950 (`mockups/README.md`, "Notes on fidelity") —
and walk the board region by region: phase ribbon, left rail, opponent mats, own
mat, card faces at each scale, hand fan, command zone, right rail, overlays.

Then repeat the pass in greyscale (`html { filter: grayscale(1) }`). That is the
check the type encoding exists for, and it is the one that finds signals which are
carrying information in colour alone.

Where a visual property reduces to a number, measure it rather than looking at it.
`e2e/layout.spec.ts` explains why: `body { overflow: hidden }` means the page
reports `scrollHeight === clientHeight` while content visibly runs off the bottom,
so a naive overflow check passes through the exact failure it was written for.

---

## Deliberate divergences

Do not "correct" these. Each is a decision made after the mockup.

### The card is a full-bleed illustration, and card type is no longer a colour

Supersedes the earlier "cards are art-first everywhere" note, which described the
arrangement this replaced. `mockups/05-planar-art.html` is no longer the reference
for the card face at all: **`mockups/cards/index.html` direction D, "Art Bleed",
is.** The illustration fills the frame and the text sits on graded scrims at the
top and bottom — head (glyph, name, then the cost on a row of its own), foot (type
line, rules where there is room, then keywords/counters/P-T).

The consequential half of this is what came *out*. Card type used to be encoded as
the colour of the card stock: an eight-step `--stock` luminance ladder plus a
matching `--type-ring` hairline, ~200 lines of `tests/palette.test.ts`, and a
`--type-ring` ladder check in `e2e/greyscale.spec.ts`. All of it is gone.

The reasoning, because this looks like a regression if you only read the old
tests: the ladder existed because a type line renders at 5.6px on a pod board
(docs/playtest-feedback-01.md item 4) and something had to say "creature" from
across the table. A full-bleed illustration says it **better and per card rather
than per category**. Twelve Forests are one recognisable picture; under the ladder
they were twelve copies of "one of the tan ones", which is the same scanning
problem the ladder was built to solve, one level up. Verified in greyscale before
the ladder was removed, not after.

What still carries card type without colour: `.face__glyph` and `.face__type`,
both of which `e2e/greyscale.spec.ts` now asserts render with content and non-zero
width on every face. Colour *identity* is a different fact and it keeps the frame
— the border and the gradient the art sits on, which on the ~4% of cards with no
printing is the whole card. A land's frame narrows to the colour it taps for, and
its produced-mana symbols go large and centre-frame.

What replaced the removed tests, so the surface is not left unguarded:

- `tests/palette.test.ts` — now asserts the art *is* full bleed (the inverse of
  its old "the art window must never cover the whole face" suite), that both
  scrims exist as gradients whose opaque ends clear a darkness floor, that the
  text carries a shadow as a second defence, and that no `.face--type-*` colour
  rule has crept back in.
- `e2e/art.spec.ts` — `the art fills the frame` replaces `the art never covers the
  type ring`; the same measurement, the opposite assertion.
- `e2e/greyscale.spec.ts` — a resolved-scrim-contrast check and a type-line check
  replace the `--type-ring` ladder walk.

Everything else about D was taken as drawn, including the parts that are easy to
skip:

- **Real mana symbols.** Scryfall's published SVGs, vendored to
  `frontend/public/symbols/` by `mockups/cards/fetch_symbols.py` and drawn by
  `ManaSymbol` everywhere mana notation appears. See `docs/frontend.md`.
- **Type sizes clamped at both ends.** The mockup names this file's predecessor
  for getting it wrong — "a floor alone is what the client does, and it is why
  the preview card looks like a zoomed board card rather than a designed one".
  `.face` now carries the mockup's `--fs-*` scale; `.face--big` restates it in
  pixels because its `--card-w` is a fiction.
- **A 1.4% frame, not 3.2%.** The old border was thick enough to read as a fourth
  band on a card meant to be an illustration. The 2px floor stays and is what
  `e2e/greyscale.spec.ts` actually measures.
- **The commander is a crown inside the name**, not a `CMD` badge in a corner. At
  pod size the badge rendered at under 3px, which is not a word.
- **Supertypes come off at board size** (`shortType`): "Legendary Creature — Hu…"
  spent the whole line on the least useful word on it. The rail keeps the full
  line.
- **No hatched plate.** A card with no printing is its colour-identity gradient
  with a quiet `NO ART`, so it reads as a grey card rather than a damaged one.
- **Keywords are a chip**, not a loose run of type over an illustration.
- **A land that taps for no colour gets a neutral mark** — Terramorphic Expanse
  was the one land on the board with no centre symbol at all.

Two size-driven rules are scoped to `.mat--compact`, which is the client's
equivalent of the mockup's 60px column:

- The name clamps to **one** line. At a three-opponent pod cards are ~51px, the
  name is held at its floor, and a wrapped second line left "Indulgent
  Aristocrat" with 4px of illustration between the two scrims.
- The mana cost is **dropped entirely**. This is the mockup's strongest argument:
  a permanent on an opponent's board has already been paid for, so its cost is
  the one line on the card that cannot change a decision you are about to make —
  and at 51px it is competing for a row against the name and the type. Your own
  battlefield and your hand keep theirs, and hovering restores it either way.

Not taken: the mockup's 60px column also reduces the type line to the bare
subtype and drops it entirely when it repeats the name. `e2e/greyscale.spec.ts`
asserts every face carries a type line, because with the type-colour ladder gone
it and the glyph are the non-colour channels — so that one stays open rather than
being quietly traded away.

### No rules text on board or hand cards

### No rules text on board or hand cards

The mockup does the same, so this is not a divergence from it — but it *is* a
divergence from `docs/frontend.md`'s earlier "cards are text-only" position, and
it is worth stating plainly: at hand size a rules box renders at 6–8px, which is
not text. The rules live on the rail card, which is now big enough to hold them.

### A life dial and zone piles, not a number and chips

The mockup shows life as a plain numeral with a row of mana dots, and the zones as
text chips (`Lib 84`, `Hand 4`, `GY 6`). The client uses a brass dial and stacked
piles. Predates this sweep; `e2e/acceptance.spec.ts` asserts both.

### `Auto-pass` keeps a word where the mockup uses a glyph

The mockup's tool row is bare glyphs (`⏩ ↺ ✕`). Mute, skip, undo and quit follow
it. Full control does not: it changes whether the engine stops at every priority
window, and an unlabelled icon for a mode with that consequence is a puzzle, not a
saving in space.

### An art-loading state the mockup has no concept of

A land draws its produced-mana symbols centre-frame whether or not the image map
has arrived — `.face__watermark` before, `.watermark-row` after, styled
identically because on a bleed face neither one reserves any layout. The mockup
inlines its state and never loads anything.

### The commander is a plinth in the info panel, not a card beside the hand

The mockup draws the command zone as a small card face in its own box. The client
draws a banner-cropped portrait with a name and a state strip, inside the player's
info panel, for every seat. This is the fix for defect #5 below, which is where the
reasoning lives — read that before restoring anything card-shaped here.

---

## Open defects

Ranked by severity. None of these block anything; they are the queue.

### 1. The `--playable` rim carries its meaning in colour alone — medium

- **Mockup**: same design, so it inherits the same problem.
- **App**: `.card--playable::after` is a green rim plus glow (`frontend/src/styles/cards.css`).
- **Why it matters**: in the greyscale pass every hand card reads identically. A
  card's *identity* survives greyscale — the illustration, the name, the type glyph
  and the type line all do — but "which of these can I actually play right now" has
  no greyscale-safe channel at all, and it is the more urgent question.
- **Partly mitigated**: castable cards are now also rows in the action panel, which
  is a second channel. The rim itself is still colour-only.
- **Fix direction**: a shape as well as a hue — the rim could carry a corner mark, or
  the dimming applied to unplayable cards could be strengthened so the distinction
  is luminance rather than hue.

### 2. Combat arrows vanish in greyscale — medium

- **App**: `CombatArrows.tsx` draws `--attacking` red lines over the board.
- **Why it matters**: same failure as above. Who is attacking whom is not
  recoverable from a greyscale capture, and it is the single most important fact on
  screen during combat.
- **Fix direction**: stroke width or dash pattern, not only colour.

### 3. The tools are visible but unreachable while a dialog is open — medium

- **App**: `.prompt-backdrop` is `position: fixed; inset: 0` at `--z-modal`
  (`frontend/src/styles/ui.css`), so it swallows clicks aimed at the tools footer
  underneath it.
- **Why it matters**: the speed control is most wanted exactly when narration is
  running into a decision, and that is precisely when it cannot be pressed. The
  panel keeps rendering the footer, which makes it look available.
- **Note**: pre-existing — the old `.bar` was equally covered. The mockup has no
  modal at all, so it does not address this. `e2e/action-panel.spec.ts` works around
  it by answering the mulligan first, with a comment pointing here.
- **Fix direction**: either lift the tools above the backdrop, or dim them while a
  modal owns the screen so they stop advertising themselves.

### 4. The preview can pin itself to a stale card — medium

- **App**: `CardPreview` renders through `AnimatePresence mode="wait"` keyed on the
  hovered oid, and `hoveredOid` is only ever cleared by an element's own
  `onMouseLeave` / motion `onHoverEnd`.
- **Symptom**: the rail arrives at a decision still showing a card from earlier in
  the turn, and in that state hovering something new does not swap it — where from
  an *empty* rail the same hover works first time. Reproduced repeatedly while
  wiring hover into the action panel: hovering a blocker group header reads the
  right creature when the rail is idle and does nothing when it is not.
- **Why it matters**: the rail is the only place rules text lives now, so a rail
  showing the wrong card is worse than one showing none. It also means "point at a
  row to read it" is unreliable exactly when you have been reading other cards.
- **Suspected cause**: `hoveredOid` outliving the element that set it — a hand card
  hovered and then cast unmounts without ever firing a leave — combined with
  `mode="wait"`, which will not mount the incoming card until the outgoing one has
  finished exiting.
- **Fix direction**: clear `hoveredOid` when the element that owns it unmounts, and
  re-check whether `mode="wait"` is still earning its place; a card-to-card swap
  does not obviously need the outgoing one to finish first.
- **Test status**: `e2e/action-panel.spec.ts` asserts the panel's hover wiring
  structurally for the blocker list rather than behaviourally, with a comment
  pointing here. The play-mode hover is asserted end to end and passes.

### 5. The command-zone card is cramped — **resolved**, by not drawing a card

- **Was**: `.cmdslot { --card-w: clamp(74px, 4.2vw, 100px) }`, matched by the app. At
  1600×950 that resolved to ~74px, and with the art band taking `1/1.4` of the width
  the name clipped to "Aesi, Tyra…" and the type line to "Legendary Creatur…". The
  commander is the card you cast most often in the format and it was the least
  legible thing on screen.
- **Fix**: the mockup's own direction — "give it a larger scale" — could not work.
  A card face has six things to fit and the column that holds it is a hard 190px, so
  every pixel of extra width is a pixel of extra height in a column that also has to
  carry a life dial, a mana row and five zone piles.
  So it stopped being a card. `CommandZone` now renders a **plinth** inside the
  player's info panel (`docs/roadmap.md`, "Improve Commander Placement"): a 2:1
  banner crop of the art, the name on its own line at the full column width, and a
  state strip. Rules text and the type line were never legible at this size anyway
  and are one hover away in the preview rail, which is the surface rebuilt to hold
  them.
- **Bonus**: the plinth's state is carried on a word, the art's luminance, and a
  glyph — three channels, none of them hue. That makes it the first interaction
  affordance on the board that does *not* fail defect #1 below.
- **Guards**: `e2e/cycle3.spec.ts` asserts the name is not clipped
  (`scrollWidth <= clientWidth`); `e2e/greyscale.spec.ts` asserts the word and glyph
  are laid out, not merely present; `tests/playerOrb.test.tsx` covers the state table.

### 6. Card type and keyword lines sit on their pixel floor — low

- **App**: `.face__type` and `.face__kwline` measure exactly 8.5px on opponent mats
  at both viewports, i.e. the `max()` floor is doing the work and the ratio has been
  overridden.
- **Why it matters**: no headroom left. A four-player pod shrinks
  `opponentCardScale` to 0.58 and the floor is already binding at one opponent, so
  the text does not get smaller — the art band gives up height instead, and past
  some point that band stops being worth drawing.
- **Fix direction**: check the 3-opponent layout before shrinking anything else, and
  consider dropping the type line entirely on the smallest scale rather than
  rendering it at the floor.

### 7. Phase step labels are abbreviated where the ribbon now has room — low

- **Mockup**: `Begin · Declare attackers · Blockers · First strike · Damage · End`.
- **App**: `Combat · Attack · Block · 1st Strike · Damage · End Cbt`
  (`STEP_SHORT` in `frontend/src/logic/labels.ts`).
- **Why it matters**: the abbreviations were chosen when the live phase pill was
  content-sized and cramped. It is now a fixed six-column grid roughly 960px wide at
  1600×950, so the full labels would fit and read better.

### 8. The action panel's empty state leaves a large dead area — low

- **App**: `.acts__list` is `flex: 1 1 auto` with a 74px floor, so it fills the panel
  even when it holds one italic line ("Nothing can block.").
- **Why it matters**: cosmetic. The floor is load-bearing — `e2e/layout.spec.ts`
  measures it, because on a short viewport this list is the first thing a flex
  parent flattens to zero — so this is a trade, not simply a bug.

### 9. The viewer's mat side column has more whitespace than the mockup's — low

- **Mockup**: a compact side column — name, life, mana dots, zone chips.
- **App**: the dial and pile bars leave noticeable dead space beneath them at
  1600×950.
- **Why it matters**: purely density. It costs the lanes horizontal room they could
  use.

---

## Closed in this pass

Recorded so the next sweep does not re-derive them. All four came from playtest
feedback against the shipped client.

- **The phase ribbon resized on every phase change.** `.track__steps` had
  `overflow-x: auto` over `flex: 0 0 auto` children, so the live phase's steps grew
  the row past the bar and scrolled the already-played phases out of view;
  `.ph--now` was `flex: 1 1 auto`, so the pill was sized by however many steps its
  phase had. Now a three-column grid with `flex: 1 1 0` on the live pill and a fixed
  six-column step track. Measured: the ribbon is 49px tall and all five phases are
  in view at both viewports.
- **Hand cards rendered rules text at 6–8px.** Cards went art-first, the rules moved
  to the rail, and every remaining line got a pixel floor. Measured: nothing on any
  card renders below 8.5px.
- **The rail preview clipped its rules text.** It scaled the portrait card up, so the
  rules box stayed squeezed by the card's own 1.4 aspect. It is now `.face--big`,
  width-driven and as tall as its text needs. Measured: 286×312 with 12px rules and
  no clipping.
- **Three panels where the mockup has one.** `ActionBar` and `CombatPanel` merged
  into `ActionPanel`; the tools became its footer; the amber wash came off the panel
  and moved onto the selected rows; the commit alternates got a real outline.
  Measured: the right rail has exactly three children, and the panel's background
  matches the stack pane opposite it.
