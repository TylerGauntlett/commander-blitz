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

### Cards are art-first everywhere; the mockup's small cards are title-first

The mockup draws its board and hand cards as title → type → art → P/T, and only
its *enlarged* rail card as art → title → type → rules → P/T. The client uses the
enlarged card's arrangement at every size.

This was an explicit product decision: the enlarged card is the readable one, and
the reason is that a fixed art band gives the text below it a contiguous block of
known height instead of whatever a greedy `flex: 1` band leaves over. Applying it
everywhere is what removed the 6px rules text from the hand. See `CardFace.tsx`.

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

`.face__watermark` renders in the art band's slot, at the art band's aspect, until
the image map arrives. The mockup inlines its state and never loads anything.

---

## Open defects

Ranked by severity. None of these block anything; they are the queue.

### 1. The `--playable` rim carries its meaning in colour alone — medium

- **Mockup**: same design, so it inherits the same problem.
- **App**: `.card--playable::after` is a green rim plus glow (`frontend/src/styles/cards.css`).
- **Why it matters**: in the greyscale pass every hand card reads identically. Card
  *type* survives greyscale — that is what the type ring and the luminance ladder in
  `tests/palette.test.ts` are for — but "which of these can I actually play right
  now" has no greyscale-safe channel at all, and it is the more urgent question.
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

### 5. The command-zone card is cramped — medium

- **Mockup**: `.cmdslot { --card-w: clamp(74px, 4.2vw, 100px) }`, matched by the app.
- **App**: at 1600×950 that resolves to ~74px, and with the art band taking `1/1.4`
  of the width the name clips to "Aesi, Tyra…" and the type line to "Legendary
  Creatur…".
- **Why it matters**: the commander is the one card you will cast most often in the
  format, and it is the least legible card on screen.
- **Fix direction**: the command zone has horizontal room the hand does not — give
  it its own larger scale rather than inheriting a hand-sized clamp.

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
