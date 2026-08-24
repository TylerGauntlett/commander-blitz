# Handheld playtest log

Five passes through a real game at 1280×800, driven through Chrome DevTools
against the live engine and client. Each loop has its own angle so coverage
compounds rather than repeats, and each finding names the surface, what
happened, why it is wrong, and what was done about it.

The shape is `docs/playtest-feedback-0N.md`'s, because that shape has repeatedly
turned into real fixes: an entry that carries its reasoning survives being read
six months later, and an entry that is only a complaint does not.

Two rules about the rig, both of which exist because getting them wrong makes
the exercise measure the wrong thing:

- **Narration is not set to `instant`.** `e2e/helpers.ts` forces it so specs do
  not spend their runtime watching beats. Here the animation *is* the subject.
- **Driving is by the keyboard mapping, not by clicking.** `input/buttons.ts`'s
  fallback is the only route into the pad's semantics that automation can reach,
  and it exercises the identical code path a controller does — the ring, the
  trap, the repeat ramp, `stopRoot()`. Clicking would test the mouse path, which
  is the one this work is not changing.

Categories, hunted deliberately so the loops do not all find the same class of
thing: **friction** (presses, dead ends, a ring that will not go where the eye
went), **feedback** (an action with no acknowledgement), **visual** (clipping,
spill, a card at the floor), **legibility** (16px is asserted; "readable on a
7-inch panel" is a different claim), **polish** (a moment that should have
weight and does not).

---

## Loop 1 — Reachability

**Angle.** Can every surface in the plan's preservation table be reached and
dismissed without a mouse? Anything that cannot is a blocker, not a polish item.

_Run at 1280×800, keyboard mapping only, four-seat pod._

### Findings

#### 1.1 The entire lobby was unreachable — **blocker, fixed**

- **Surface**: the front door, the pod lobby, the deck catalogue, the dossier.
- **What happened**: the ring did not exist. `FocusRing` and `useCursorNav` were
  mounted inside `Table`, so a controller could navigate the board and nothing
  else — it could not create a pod, pick a deck, or start a game.
- **Why it matters**: this is a more complete failure than anything on the board
  it was covering. The board work was untestable by controller because you could
  not reach the board.
- **Fix**: both moved to `components/screen/Screen.tsx`, which every route
  renders exactly one of. `Table` keeps `useCursorResolve()` on its own, because
  React only runs layout effects for components that re-render and the board
  re-renders on every engine push without its wrapper doing so.
- **Second half**: the lobby declares no `data-stop` anywhere, so `stopsIn` now
  falls back to native focusables when a surface declares none. That is not a
  shortcut — outside the board every interactive thing already *is* a control,
  and it means a button added to the lobby next year is reachable without
  anybody remembering the input layer exists.

#### 1.2 `A` did nothing outside the board — **blocker, fixed**

- **What happened**: `confirm()` resolved a stop back to a card or a seat and
  called the matching handler, and it was bound in `Table`. On any other screen
  the button was inert.
- **Fix, and it made the code smaller**: `A` is now literally
  `stopElement(cursor).click()`. Not "A does what a click does" — it dispatches
  the click. There is no second routing table to keep in step, no branch per
  stop kind, and no way for a pad to reach an action a pointer cannot. Same
  argument `actionAttrs` makes for stop ids, one level up.

#### 1.3 The ring was invisible on every text field — **blocker, fixed**

- **Surface**: the pod-code field, the seat-name field, the deck search, the
  sort control.
- **What happened**: `outline-width: 3px` with `outline-style: none`. Four
  class-qualified rules in `lobby.css` (`.join__in:focus { outline: none }` and
  three siblings) outrank `[data-cursor]`, which is a single attribute selector.
- **Why it matters**: it is the exact failure mode the ring's own comment warns
  about, and it is invisible in devtools — the declaration shows as applied and
  every property except `outline-style` reads back correctly.
- **Fix**: `:not([data-cursor])` on all four.
- **The guard was wrong too, which is the real finding.**
  `tests/focusOutline.test.ts` banned only the *bare* `:focus`, on the stated
  reasoning that a class-qualified one "cannot silently blank the ring across
  the board". That was exactly backwards: being more specific is what let it
  win. The rule is now "any selector ending in `:focus` that turns an outline
  off must exempt the cursor", and it strips CSS comments first — the previous
  version flagged its own documentation, which is how a guard teaches people to
  delete the explanation rather than fix the code.

#### 1.4 Walking the board is a bad way to ask "can you reach everything"

- **What happened**: three separate hand-driven sweeps reported controls as
  unreachable that were one press away. A fixed sweep explores whatever its own
  order happens to explore, and reports absences it has not established — which
  sends you hunting a bug that is not there. One of the three readings was also
  wrong for a sillier reason: it identified stops by label, and a pod has three
  buttons reading "Add a CPU".
- **Fix**: `unreachableStops()` in `input/nav.ts` answers it properly — build the
  directed graph of every press from every stop, return the stops with no
  inbound edge. Exposed on `window.__AUTOMTG_RING` in dev builds so the driver
  and the CI gate ask the *app's* implementation rather than a re-derivation of
  it, which is how a gate ends up passing against a real defect.

#### 1.5 The cursor could not name a derived stop — fixed

`resolveCursor` read `el.dataset.stop` directly, which is `undefined` for a stop
derived from a native focusable. The ring mounted, resolved to nothing, and the
lobby stayed dark even after 1.1 was fixed.

### Loop 1 result

| Surface | Stops | Unreachable |
|---|---|---|
| Pod lobby | 12 | 0 |
| Deck catalogue (open) | 26 | 0 — and correctly trapped: the board behind it contributes none |
| Handheld board, 4 seats, lands out | 44 | 0 |

Every surface in the plan's preservation table is reachable and dismissable
without a mouse. Four blockers found, four fixed.

---
## Loop 2 — Feel at speed

**Angle.** Default narration speed, four-seat pod, played through to combat.
Where does the board fail to say what happened?

### Findings

#### 2.1 A card you are asked to read was cut off mid-sentence — **fixed**

- **Surface**: `PromptDialog`, discarding to hand size. Also the zone viewer.
- **What happened**: `.opt--card` is 172px, which was sized for 9px rules text.
  With the 16px floor applied to it the rules box held **90px of a 214px
  paragraph** — the sentence stopped mid-word — and the type line above it
  collapsed to 8px and read as struck through.
- **Why it matters**: it is worse than small text, and in a specific way. Small
  text is legibly small; a truncated rule is *silently wrong*. The player was
  choosing what to discard from a card whose ability they could not finish
  reading, with nothing on screen saying so.
- **Fix**: the floor was right and the card was wrong. A prompt is a reading
  surface that owns the whole screen while it is up, so it can afford the
  width: `--card-w: clamp(210px, 24vw, 264px)`, three per row instead of five.
  Measured after: 264px cards, type line back to 20px, zero overflow on every
  card in the prompt.
- **And it degrades honestly now.** `.face__rules` gets `overflow: hidden` with a
  bottom mask, so a card that still cannot fit its text fades rather than
  stopping at a line boundary — a hard cut is indistinguishable from the card
  not having the rest of the sentence.

#### 2.2 The hint bar vanished exactly when it was needed — **fixed**

The bar lives in the foot, which sits under every dialog's backdrop. So the one
moment it was hidden was the one moment a player does not yet know what `A` and
`B` do. Lifted above `--z-modal`. It is not a control, so lifting it cannot make
anything pressable that should not be — a narrower version of the problem
`docs/mockup-fidelity.md` records as open defect #3.

#### 2.3 The action list was 41px holding 197px of content — **fixed**

- **Surface**: the right rail, mid-combat, four seats.
- **What happened**: measured live — preview 272 + stack 71 + commit dock 104 of
  a 514px rail left the action list **41px**. The "Declare attackers" prompt, the
  defender chips and the "All attack" row were inside that 41px, crushed
  together and clipped.
- **This one was self-inflicted**, and worth saying so: moving the stack panel
  into the right rail is what tipped it over. The regression arrived with the
  layout work and would have shipped with it.
- **Fix**: the list gets the slack and everything else is capped — preview to
  176px, stack to 84px and scrolling. The ordering is the point: a preview you
  have to scroll is a mild annoyance; an action list you cannot see is the game
  not being playable. Measured after: rail overflow 0, list 74px with no
  overflow, every row of the decision legible.
- **A second mistake inside the fix, caught by measuring rather than looking.**
  The first attempt wrote `min-height: 0` on `.acts__list` to let it scroll,
  which overrode the 74px floor `board.css` gives it — and the prompt text then
  took all 137px, leaving the list holding the actual choices **2px tall**. The
  floor exists precisely because this list is the first thing a flex parent
  flattens; `e2e/layout.spec.ts` measures it. The help line gives way instead.

#### 2.4 What the board does say, and says well

Recorded because a log of only complaints is a log that reads as a failure:

- The **attacker lean** works and carries the fact the amber rim could not. A
  staged creature holds a step toward the seat it is aimed at
  (`translateX(-4.1px) translateY(-13.4px) scale(1.03) rotate(-1.8deg)`), which
  in a pod is what distinguishes three creatures staged at three different
  players. The combat arrow and the lean agree.
- The **opponent spines** carry a four-seat pod at this size: "1 creature ·
  1 untapped · 8 power · 1 open" answers the two questions worth asking about a
  seat whose board is not drawn.
- **Arrivals** now land with a thump and a flash rather than a silent puff of
  dust.

---
## Loop 3 — Density and legibility

**Angle.** Four seats, full boards, 1280×800. This is where the 16px floor and
the opponent strip either earn their place or do not. Measured with the gate
rather than looked at, for the reason the gate exists.

### The measurement, before and after

| | before | after |
|---|---|---|
| smallest font on anything carrying information | **6.5px** | **16px** |
| elements under the 16px floor | **123** | **0** |
| smallest card the ring can land on | 56px | **96px** |
| controls under the 44px hit floor | **21** | **0** |
| native `title` tooltips | **142** | **0** |
| unreachable stops | 0 | 0 |

### Findings

#### 3.1 The gate was measuring things nobody can see — **fixed first**

Before any of the above meant anything, the gate had to stop lying. It reported
22 cards under the card floor and a pile of text under the font floor, all of it
inside an opponent's lanes — which the handheld layout clips to `height: 0`
because those cards must stay in the document for `FxLayer` to anchor damage
numerals and exit ghosts to.

`getBoundingClientRect` reports an element's own box even when an ancestor has
clipped it out of existence, so `visible()` now walks the ancestor chain and
requires the box to intersect every clipping ancestor. **This is the worst class
of gate failure**: it sends you fixing something that is not wrong, and the
obvious "fix" here would have been to stop clipping the lanes — which would have
broken effect anchoring instead.

#### 3.2 The 16px floor, and what it costs

123 elements were under it, the smallest at 6.5px: zone labels, commander-damage
chips, phase step names, the action panel's own rows. Every one looked fine in a
screenshot, which is the trap the round warns about — a reviewer already knows
what the label says.

Two treatments, and the classification is a judgement about *information*:

- **Raised** — anything carrying a name, a number or a verb.
- **Dropped** — labels whose subject is still on screen: "MANA" over the mana
  row, the plinth's "IN COMMAND" strip, the em dash standing in for an empty
  lane next to that lane's own name.

**Two drops were wrong and were taken back**, which is the most useful thing
this loop produced:

- `.pile__label` — "Lib", "Hand", "GY". Dropped on the argument that the piles
  are in a fixed order with distinct graphics. Looking at the result settled it:
  the orb became the bare row `82 4 5 1`, and nothing distinguishes a library
  count from a graveyard count. A fixed order only helps somebody who already
  knows it.
- `.track__step-label` — dropped on the argument that the live step is the one
  lit. It is, but the pill then read "COMBAT" with an unlabelled bar in it, and
  *which* combat step you are in is the difference between declaring attackers
  and taking damage.

Both are raised to 16px instead, and the space comes from wrapping. The rule
survives with a sharper edge on it: **dropping is for a label whose subject is
still on screen, and a count is not its own name.**

#### 3.3 A transform silently defeated the hit floor

`.mat--compact .piles { transform: scale(0.86) }` — added earlier to buy back
~40px per seat — outranks `[data-handheld] .piles` (two classes against one
attribute), so the 44px targets measured **38×38**: exactly 44 × 0.86. A
transform is invisible to a `min-height`, which is what made it hard to see and
is why it took a numeric gate rather than a look. Removed.

#### 3.4 The 142 tooltips — **removed, and the information kept**

A `title` opens on hover and on nothing else: no keyboard route, no controller
route, no touch route. On a Deck every one of them was information that could
not be reached, and they were carrying real things — which card is revealed on
top of a library, how much commander damage is from whom, what a mode toggle
changes.

All 43 sites became `data-hint`. The hint bar echoed it off the focused
element for a while and stopped: the string is unbounded and it was the thing
that wrapped that row onto a second line, which grows the foot and moves every
tool button while a decision is open. `tests/noTooltips.test.ts` keeps `title`
at zero regardless. Where `title` had
been supplying an element's accessible name — the zone piles, whose labels the
handheld layout hides — an explicit `aria-label` replaces it.

#### 3.5 The phase ribbon truncated every step at 16px

"Atta", "Dam…", "End …" — a legibility failure the font floor cannot catch,
because the *size* is fine. The live step now takes the width it needs and is
measured un-truncated; the rest keep their words and truncate, which still says
what comes next. An intermediate version blanked them to markers and was
reverted: the ribbon's job is position within the phase, and markers gave up
more than truncation did.

---
## Loop 4 — The unhappy paths, and the gate itself

**Angle.** Reduced motion, mouse users, animations mid-flight, and the states
the first three loops did not reach. Run largely *through* the CI gate, because
by this point the gate is the instrument — and a loop that finds bugs in its own
instrument is worth more than one that trusts it.

### Findings

#### 4.1 The gate demanded a ring from a mouse player — **fixed**

`ring is 3px none` on every board state, because Playwright drives by clicking
and `html[data-input="mouse"]` suppresses the ring **by design**. The gate was
failing the one input method this whole change is careful not to alter. It now
only requires a ring when `data-input` is `pad` or `keyboard`.

#### 4.2 The gate reported arithmetic as a design failure — **fixed**

`smallest focusable card is 96px`, which is not a sentence that can be true.
`--card-w` is a `calc()` over a `clamp()`, so the solver's answer *at* the floor
comes out as 95.9744px. Both the card floor and the hit floor now round before
comparing. A 43.5px box is a 44px box that CSS and the device pixel ratio
disagreed about by half a pixel.

#### 4.3 The gate measured mid-animation — **fixed**

A button measured **44px in a live browser and 43px in the spec, every time**.
Every dialog animates in from `scale: 0.96`, and `getBoundingClientRect` reports
the scaled box — so the hit floor failed on controls that are the right size.
The spec now waits on `document.getAnimations()` before measuring.

And then that wait hung, because the ring's sheen and the commit slab's waiting
pulse loop **forever**: waiting for every animation to stop waits for the tab to
die. It filters to finite iteration counts, which is also the honest set —
entrances and exits are what move a box.

#### 4.4 A gate rule that was simply wrong — **reverted**

The gate failed on duplicate `data-testid`s: the front door's fan of card backs
and every seat's back all render `data-testid="card-back"`, and Playwright's
strict mode does fail a query matching more than one.

The rule it implies is wrong for this codebase, and finding that out is the
useful part. `e2e/pod.spec.ts` writes
`getByTestId("seat-1").getByTestId("card-back")` — scoping to a container first,
which is correct practice and makes a shared id on a repeated component entirely
legitimate. Enforcing uniqueness meant numbering ids in three components and
would have meant editing ten query sites to couple each test to a seat index
twice over.

So the check reports the number and no longer fails on it. **A gate that forces
the codebase to adopt a worse pattern is a gate that is wrong**, and the tell was
that satisfying it made every call site longer and none of them clearer.

#### 4.5 Decoration was inflated to the size of information — **fixed properly**

The card back's repeated "Commander Blitz" watermark is a *pattern*, not a
label: the same words on every face-down seat, at the size a card back's
printing is. Raising it to 16px would have been absurd. It is `aria-hidden`
now, which is true, keeps a screen reader from announcing it four times before
the first real seat, and is the honest way to sit under the floor — the gate
exempts hidden text by design.

---

## Loop 5 — Fresh eyes

**Angle.** The surfaces the earlier loops never opened, checked as somebody who
has not read any of this.

### Findings

#### 5.1 The floor stopped at the board — **fixed**

The first three loops measured the board, because that is where the work was.
Pointing the gate at the front door found `data-handheld` was stamped on
`.table` — so the entire lobby, catalogue and dossier had no floor at all and
were still drawing 9px text.

The attribute moved to `<html>`, beside `data-input`, which is where it belonged
in the first place: the layout is a property of the environment, not of one
component. Storybook's decorator had been stamping it on `documentElement` all
along, so the two had quietly disagreed.

#### 5.2 The real size of the 16px floor

With the whole app in scope, hand-enumerating classes stopped being the right
tool. Extracting every selector in `board.css`, `ui.css` and `lobby.css` with a
font-size literal under 16px found **146 of them**, from 15px down to 6.5px.

The override is generated from that extraction rather than written by hand, and
the comment says so — a list of 144 selectors maintained by care is a list that
rots. Two are deliberately absent because they are *dropped* rather than raised.

16px is a floor, not a size: everything already above it keeps its value, so the
type hierarchy survives compressed at the bottom, which is what a floor does.

### Loop 5 result

The gate passes at every reachable state: the front door, the pod lobby, the
deck catalogue, the mulligan, the main phase, a board with permanents on it, the
zone viewer, the log overlay, and a four-seat pod.

| | value |
|---|---|
| smallest font carrying information | **16px** |
| smallest card the ring can land on | **96px** |
| controls under the 44px hit floor | **0** |
| native `title` tooltips | **0** |
| unreachable stops | **0** |
| duplicate `data-testid` | **0** |

No new blocker- or feedback-class findings, which is the exit criterion.

---

## What the loops cost, and what they were worth

Sixteen findings across five loops. Four were blockers that would have shipped a
controller mode you could not start a game with. Four were bugs in the *gate*,
found only because the gate was pointed at states the work had not visited —
and a gate that has never failed has not been shown to work.

The two most useful entries are the ones where the first fix was wrong:
`.pile__label` and `.track__step-label` were dropped on plausible arguments and
had to be taken back, which sharpened the rule from "drop what does not fit" to
**"dropping is for a label whose subject is still on screen, and a count is not
its own name."**

---

## Final verification

| gate | result |
|---|---|
| `python scripts/verify.py` — **the gate CI runs** | **all 14 stages passed** |
| `npm run lint` (biome) | **0 errors** (2 pre-existing warnings) |
| `npm test` (vitest, jsdom) | **913 passed**, 44 files |
| `npm run test:stories` (real Chromium) | **308 passed**, 34 files |
| `npx playwright test --project=chromium` | **103 passed, 0 failed**, 13 skipped |
| `npx playwright test --project=handheld` | **10 passed** |
| `tsc --noEmit` | clean |

Note that `scripts/verify.py` — what `.github/workflows/deploy.yml` actually
invokes — does **not** run the Playwright suites. Both are green regardless, but
the stage that would have failed CI was `frontend lint`, which was red on this
branch before any of this work with 77 formatting errors.

### The five pre-existing desktop failures, and what they turned out to be

All five failed identically with the changes stashed, so none was caused by this
work — but "pre-existing" is not "acceptable", and CI has to be green. Every one
was a **test** defect rather than an app defect, and each is worth recording
because the failure never named its own cause:

- **`art.spec.ts` — the illustrator credit.** Failed as `locator.hover: Test
  timeout`, which reads like a rendering problem and is not one.
  `buildABoard` spends its step budget and can return with a *discard-to-hand-size
  modal still open*; `.prompt-backdrop` is `position: fixed; inset: 0`, so every
  later hover waited out the full timeout against a card it could never reach.
  `buildABoard` now answers any open prompt before returning.

- **`cycle3.spec.ts` — mana notation.** Hovered "the first hand card" and
  required *that* card's rules to contain a mana symbol. With this seed it
  landed on Harmonize — "Draw three cards." — so the pip assertions ran against
  an empty set. It now hovers through the hand until it finds a card that
  actually renders one.

- **`cycle3.spec.ts` — the spend forecast.** Asserted `data-spending === "0"`
  as a baseline, in a state reached by *clicking action rows*. A clicked button
  keeps DOM focus, and `ActionPanel.previewing()` deliberately wires focus to
  the same `hover()` the mouse uses — a documented feature. The test now clears
  focus before asserting nothing is hovered.

- **`cycle3.spec.ts` — the four-player pod.** Two faults at once. Its deck
  pinning intercepted `/api/decks`, which stopped matching anything when the pod
  lobby replaced `NewGameScreen` — a CPU seat is filled by
  `POST /pods/{code}/seat` with the *server* choosing — so it had been silently
  measuring a random scenario. And its assertion ("a mat hides less than one
  card row") was written for content-sized mats, where overflow meant wrapping.
  `--pod-lanes-h` shipped afterwards and made the lanes a **fixed box that
  scrolls**, so hidden content grows without bound by design. The dead
  interception is gone and the assertion now checks what the design actually
  guarantees: nothing becomes unreachable.

- **`layout.spec.ts:183` — the band drift.** Sampled band offsets the instant
  `takeAction` returned, catching `.mat` and its bands *mid layout animation*,
  where `getBoundingClientRect` reports an in-flight box neither ever settles
  at. That was the entire 9px "drift": with a settle in front of the sample,
  across the same twenty actions, it is **exactly zero**.

**One genuinely new failure appeared and was fixed**: `layout.spec.ts:382`, "an
opponent's board filling up does not move the viewer's board". The opponent
spine wrapped to a second line as a board filled — growing the compact mat,
growing the `align-items: stretch` row, and moving the viewer's whole board down
**35px**, drop targets and all. That is the exact failure `--pod-lanes-h` was
introduced to end, arriving again through a new door, and it is why that test
exists. The spine is a fixed single line now.

### A correction worth recording

An earlier draft of this file claimed `npm run lint` was red because "21 files
carry committed CRLF". That was wrong twice over. The committed blobs are LF —
checked with `git cat-file`, which was the check that should have been run in
the first place. The CRLF was **self-inflicted**: `pathlib.Path.write_text` on
Windows translates `
` to `
` unless told otherwise, so every file edited
through a Python helper during this work came out CRLF and Biome rejected it.

Lint *was* genuinely red before this work — 77 formatting errors on the clean
tree — but for ordinary drift, not line endings. It is now zero errors.

---

## Loop 6 — It did not fit

**Angle.** Loops 1-5 measured whether things were big enough to read. This one
asks the question none of them asked: **is all of it on screen at once?**

That is not a refinement of the earlier rounds, it is the thing they missed. A
Steam Deck is held at one angle in two hands; there is no second position and no
scroll wheel. A board you have to scroll is a board whose bottom half does not
exist. Every gate in the suite passed on a layout where the viewer's own
graveyard count was below the fold.

_Run against the live engine and client at **1200x800** as well as 1280x800. The
narrower width is not a duplicate: it is the same height with ~36px less right
rail, and several findings below appear at one width and not the other._

### The measurement, before and after

| | before | after |
|---|---|---|
| opponent seat, **empty board** | **220px** | 96px (1-2 seats), 84px (3-4) |
| viewer's mat | 301px, **overflowing its row by 104px** | 429px, overflow **0** |
| action list, mid-combat | **74px** holding 144px of choices | 129-190px, overflow 0 |
| the commit slab | **264 x 65**, in the rail | 111 x 44, in the foot |
| right rail | 264px — **22% of the screen** | 228px |
| the tools strip | **101px** of a 252px panel | 44px, in the foot |
| phase steps truncated | **5 of 6** | **0** |
| regions scrolling at Deck size | `.play__mine`, `.mat__side`, `.acts` | **none** |

### Findings

#### 6.1 The compact layout deleted the cap that made it fit — the big one

`board.css` caps the opponents' row at `fit-content(58%)` and says why in four
paragraphs: *"every pixel of height in this column is a pixel taken off the
viewer's own board."* `handheld.css` replaced it with a bare `auto`, reasoning
that *"with no lanes there is nothing for a percentage cap to protect against"*.

That is exactly backwards. The lanes are clipped to zero here, so **the orb IS
the seat** — and it took 220px of an 800px screen for a player with nothing in
play. All 220 came out of the viewer's own mat, which then overflowed by 104px
and scrolled its graveyard off the bottom.

Fixed with `--pod-seat-h`, registered in `theme.css` beside `--pod-lanes-h` and
for the same reason. `fit-content(var(--pod-seat-h))` on the row *and* a matching
`max-height` on the mat: the row cap alone does nothing, because a grid row
never shrinks below its content's min-content, and the mat's own cap is what
makes that min-content small enough for the row cap to bite.

#### 6.2 An opponent was a column layout given a row's width

Of that 220px, 144 was `.orb__foot` — a mana plate, a commander-damage plate and
a row of piles, each on its own line, each with a plate's padding, in a column
**776px wide** holding a handful of glyphs. The block's own comment says
*"Nothing is dropped -- this is a re-flow, not a cut"*; it had re-flowed the
portrait and left the foot stacked.

Three columns instead of three rows costs the height of the tallest rather than
their sum. Two more things had to give with it, both invisible until measured:

- **The portrait was 107px against a 46px cap.** `.cmdplinth__frame` caps the
  *banner*; a commander still in the command zone renders a name and an "In
  command" strip beneath it in normal flow, which a capped banner does nothing
  about. That is the trap the frame rule's own comment warns of, one level out.
- **The library pile was 75px.** `pileLeaves` draws one leaf per nine cards, so
  a 91-card library is ten of them — taller than the 44px target it sits inside.

#### 6.3 Density changes the arrangement, and four seats is a different layout

The one-line strip is right for one or two opponents and **cannot** be made to
fit three. At four seats a mat gets 309px, and portrait + name + threat line +
mana + commander damage + four 44px pile targets needs about 420. What it drew
was a portrait, a clipped "LIB", half of "HAND", and **115px of everything else
hidden under the cap** — no seat name, no threat line, no graveyard.

A cap that hides content instead of re-arranging it is not a cap, it is a crop.
So the arrangement is keyed on the seat count with `:has()`, and at three or
more the name and threat line share a row, the piles get the one below, and the
commander's **name** is dropped — the one real cut in this layout. The art
stays: the illustration is still recognisably that commander, the seat is still
named, and R2 draws the whole mat. Losing a label is recoverable in one press.

**And a fifth pile exists.** Exile appears the moment anything is exiled, and
five 44px targets plus gaps need 236px of the 291 a four-seat mat has. At a 52px
art column the row came to 233 and the fifth pile wrapped, putting the seat 47px
over its cap with a count hidden under it. Found by `deckfit.spec.ts` on a pod
that had reached turn six — exactly the state a fixed four-pile assumption
survives to.

#### 6.4 A wrapped label defeated the fit solver — the subtlest one

`logic/zoomFit.ts` models a lane heading as `LANE_CHROME.labelAboveH: 23`, one
line, and solves the board's card width against that model. The 16px floor from
Loop 3 pushed "GLOBAL ARTIFACTS & ENCHANTMENTS" from 10px to 16px, where it no
longer fitted the 239px lane it sat over — so it wrapped to **42px**. The solver
went on believing 23, targeted a board 21px shorter than the one it was drawing,
and left `--card-w` at 103px when 96 would have fitted.

**This is Loop 3's fix causing Loop 6's bug, through a file Loop 3 never
touched**, and it is invisible to every gate in the suite: nothing was too small,
nothing had collapsed, and the only symptom was a scrollbar.

It is fixed twice over, because the headings turned out not to be worth keeping
at all — see 6.7 — but the lesson stands on its own: **a layout constant that
models rendered text is a constant a font change can falsify.**

#### 6.5 The rail was spending its height on things that were not the turn

Two controls in the right rail outweighed the panel where the turn happens, and
in both cases the codebase already believed they had moved:

- **The commit slab.** `handheld.css` said *"The foot carries the hand, the
  hints and the commit slab together"*, styled a `.foot__slab`, and `useZoomFit`
  reserved `HANDHELD_FOOT_EXTRA = 56` for *"the commit slab portalled beside
  it"*. `createPortal` appeared nowhere in `src/`. So the hand paid 56px for a
  slab that was not there while the slab went on taking 65px of the rail and the
  full width of it. It is portalled now — the same node, not a copy, so every
  `data-action-id`, testid and ring stop travels with it.
- **The tools.** Five 44px utility controls in a 200px column wrap to three
  rows: **101px of a 252px panel**, pinned, for mute / auto-pass / auto-mana /
  undo / quit. That is the 44px floor working correctly in a column that is the
  wrong shape for it. In the foot they are one line.

Between them the action list went from its 74px floor to 129-190px, and
`.acts__hint` from **8px holding 45px** — a sliver of a sentence — to the whole
of "Click a creature to send it."

**The slab spans both foot rows**, in the ~130px gutter the centred hand fan was
never using, so the foot did not grow at all. Its own row cost 44px, and the
foot's height comes straight off the board.

#### 6.6 A raised hand card covered the hint bar, and could not be put down

`.hand__slot` is a fixed rectangle extended upward by the hover lift — the fix
for a jitter where raising a card moved its hit box out from under the pointer.
At a 46px lift the slot's top edge sat at **y=580** against a hint bar spanning
**583-610**. So a raised card drew over "Read" and "Back", and worse: *the slot's
catchment covered the bar*, so moving the pointer up off the hand never fired
`mouseleave` and the card stayed raised for the rest of the game.

The lift is a token now (`--hand-lift`), read by `HandFan` through
`state/useHandLift.ts`, because three places have to agree on it and only one of
them is CSS.

**The first fix was wrong and is worth recording.** Padding `.hand` to contain
the lift looked obvious and cost 7px of overflow: the box is `border-box`, so
24px of top padding came straight out of the `calc(var(--card-w) * 1.4 + 44px)`
that reserves room for the arc's droop and the outermost cards' rotation. The
right answer was to put the hint strip **below** the hand, where the overhang
goes up into the board's padding exactly as it does on a desktop — free, and the
strip reads better at the bottom edge anyway.

#### 6.7 The lane headings were naming things that were already on screen

"CREATURES", "GLOBAL ARTIFACTS & ENCHANTMENTS", "LANDS" — three headings over
three rows of the things they name, on the screen with the least room to spare.
This is the drop rule Loop 3 settled on — *dropping is for a label whose subject
is still on screen* — applied to the one place it had not been. Nowhere is a
subject more on screen than the cards directly beneath its own heading.

Worth more than the words: the front band gives up `labelAboveH` of height and
the lands band gives up `labelBesideW` — a **74px column**, on the row that holds
the most cards.

**`useZoomFit` passes `labels: false` to match, and it has to.** Hiding them in
CSS alone would leave the solver reserving room for both, and the board would go
on sizing its cards for a box smaller than the one it has. `COMPACT_MAT` has
always carried that switch for the opponents; the viewer's mat now uses it too.

#### 6.8 The zone counts were 16px numbers in 16px boxes

`.pile__stack` is 28px wide and the compact orb narrows it to 16 — fine when the
count on the top leaf was 10px, and not fine the moment Loop 3's floor raised it
to 16. A two-digit library count is ~20px of glyph in a 16px box, so **"90"
rendered clipped and off-centre** and three digits had nowhere to go. No gate saw
it: the font size was correct and the box it overflowed was decorative.

The resolution is the one Loop 3 reached for the 142 native tooltips — **drop the
word, keep the mark, put the name one input away.** On an opponent's strip the
top leaf becomes the whole chip: zone colour, one number, room for three digits,
inside a 44px target. The name comes back as a popover on `:hover` for a pointer
and on `[data-cursor]` for the ring, from `attr(aria-label)` so the visible name
and the accessible one cannot drift apart.

**And the marks had to be told apart first.** `PILE_KIND` mapped *hand* to
`lib`, so the two most-read counts on a seat rendered as the same purple stack —
with the words gone, the only thing distinguishing "89 cards left in their deck"
from "5 cards in their hand" was which came first. That is precisely the argument
Loop 3 used to take `.pile__label` back. The hand has its own kind and its own
colour now.

#### 6.9 The controller was never detected, and nothing could say why

`input/pad.ts` stopped its own rAF loop on any frame with no pad, no held key and
no frame subscriber — which is *every* frame on a fresh page, because Chrome
reports four nulls from `getGamepads()` until the pad's first gesture. So
`startPad()` ran one frame, saw nothing, and died, leaving `gamepadconnected` as
the only way back: one event, dispatched once, and if it landed before `Screen`
mounted its listener the controller was never seen again.

`mockups/handheld/06-one-thumb.html` binds that same listener **with an empty
body on purpose** and polls unconditionally. The port inverted it and made the
decorative listener load-bearing. The loop now idles at 10Hz instead of stopping,
and re-arms on `focus` and `visibilitychange` — Chrome does not report gamepad
state to a background document.

**`window.__AUTOMTG_RING.pad()` is the more useful half of this fix.** There was
no way to tell "the loop is dead" from "the browser never saw a gamepad" from
"the pad is seen and the ring is suppressed because the mode is still mouse",
and those three want three different answers. One call reports all of them.

**The test that should have caught it passed, and then the test written to catch
it also passed.** `pad.spec.ts` installs its fake in `addInitScript`, so a pad is
live on frame 1 — the one path a real controller never takes. The replacement
still passed at 1280x800, because `Table` registers a frame subscriber for the R2
board-peek **only when the layout is handheld**, and that subscriber held the
loop open. It runs at 1600x950 now, where nothing does, and it fails against the
old loop — verified by putting the old loop back rather than assumed.

#### 6.10 A hovered card stayed hovered after the mouse took over

Driving by keyboard puts `hoveredOid` on whatever the ring lands on. Touching the
mouse flips `data-input` to `mouse` — and nothing cleared it, because no
`mouseleave` can fire for a card the pointer was never over. The preview rail
stayed pinned to a card nobody was pointing at, permanently.

`hoverFor()` already refuses to *write* in mouse mode, which is the right rule
and is not enough: the write that has to be undone happened before the mode
changed. `cursor.ts` subscribes to the input mode now and clears both the hover
and the pending `RAIL_SETTLE` timer, which could otherwise re-pin the rail ~110ms
*after* the mouse had taken over.

Two more writers of the same global were wrong in the same way:

- **`HandFan` tracked the raised card by INDEX.** Cast the third card and index 2
  is a different card: the wrong slot stays raised. It is keyed by `oid` now,
  which removes the class with no effect to run — the card leaves the hand,
  `findIndex` returns -1, and the fan renders unraised on the same commit.
- **`Card` and the slot both wrote it**, two nested enter/leave pairs on one
  scalar with no defined order across a slot boundary. `Card` takes
  `ownsHover={false}` inside the fan, and carries the unmount guard `CommandZone`
  already had — framer's `onHoverEnd` is a `pointerleave` gesture and does not
  fire when a `layoutId` node is moved or unmounted, which is exactly what
  casting a hovered card does.

#### 6.11 The gate could not see any of this, and that is the finding

`spilled[]` looks only at `.play__mine .card`, measured against `.play__mine` —
which is itself the scroll container, so a card clipped by the *grid row* is
inside its limit by definition. It never looks at band labels, the orb, or the
pile counts, which is everything that actually went missing. `collapsed[]` asks
only `height < 8`.

Neither can catch "this fits, and it should not have been allowed to". Two checks
were added **before** any layout was touched:

- **`overflowing[]`** — `scrollHeight > clientHeight` on the containers
  themselves, with an explicit allowlist of the places where scrolling is the
  design. It does not need to guess which child went missing.
- **`overBudget[]`** — region heights as fractions of the viewport. An opponent
  capped at 14% is the assertion that would have caught 6.1 on the day it
  shipped.

And a new suite, `e2e/deckfit.spec.ts`, asserts the claim the posture actually
depends on: **nothing scrolls**, at 1200x800 and 1280x800, two-player and
four-seat, played in to turn six. It found 6.3's fifth pile and 6.6's 7px.

### Loop 6 result

| | value |
|---|---|
| regions scrolling at 1200x800 | **0** |
| regions scrolling at 1280x800 | **0** |
| four-seat pod, either width | **0** |
| smallest font carrying information | 16px |
| controls under the 44px hit floor | 0 |
| phase steps truncated | 0 |

### What this loop says about the five before it

Loops 1-5 were thorough and their fixes were right. They measured **legibility**
— is this big enough, is it reachable, does it have a name — and every number
they report is still true.

What they never asked is whether the result **fits**, and three of their own
fixes are what stopped it fitting: the 16px floor wrapped a lane label and
falsified the solver's model (6.4), inflated a zone count past the box drawn for
it (6.8), and the 44px floor wrapped a five-control strip to three rows in a
column shaped for two (6.5). Each fix was correct in isolation. None was measured
against the height budget of the screen it was for.

**A floor is a constraint, not a design.** Raising every number to the floor and
checking they are all above it is not the same as checking they still fit
together — and only the second is what a player sees.

---

## Loop 7 — Storybook, where the design is actually reviewed

**Angle.** Loop 6 measured the running game. This one points the same question
at the 308 stories, because that is the surface a designer opens — and in
handheld mode almost all of them were wrong.

The complaint that started it was specific and correct: bloated fonts, buttons
too large, things bleeding out of their boxes, containers in the wrong corner,
and *the Pass button in two different places depending on where you looked*.

_Measured with `npm run audit:stories`, added for this loop._

### The instrument, first

Eyeballing 308 stories is not a method. The sweep opens each one **twice** —
desktop then handheld — and reports only the delta, because the useful question
is not "does this story have findings" but "does turning handheld ON break it".
A single-mode run was tried first and buried the signal: 25 stories had findings
on desktop already and none of the interesting ones were among them.

It looks for two structural things: a box outside the viewport, and
`scrollHeight > clientHeight` on a non-visible overflow. Deliberate truncation
is excluded — an element with `line-clamp` is doing what it was told, and
counting it drowned the real findings on the first pass.

| | stories handheld makes worse |
|---|---|
| before | **112 of 308** |
| after | **31 of 308** — and most of the rest are decorative overflow inside a clipping parent |

### Findings

#### 7.1 One hard-coded track number broke fifty stories

`testing/mounts.tsx` exists to hang a component where the app hangs it, and its
header warns in as many words: *"a right rail that forgot to say `gridColumn: 3`
renders at the left rail's width, silently, looking entirely plausible. That is
the trap this whole file exists to avoid."*

It then wrote `gridColumn: 2` for the board — the board's column on a **desktop**
three-track body. The handheld body has two tracks, so the same literal put the
board **in the right rail**: every Card, Lane, CardStack, CardFace and PlayerMat
story drew a 243px-wide mat with its cards hanging 40px past the edge of the
screen. The trap the file was built to avoid, arriving through the door it was
not watching.

**A track number is a size in disguise**, and this file forbids sizes. So
`board.css` assigns all three tracks by class now — `.table__body > .play` and
its two siblings — `handheld.css` re-states the two that move, and `mounts.tsx`
says nothing about them. That also removes a real fragility from the app: the
board was landing in column 1 there only because the left rail is `display:
none` and a `none` element is not placed at all. It was right by luck.

#### 7.2 The Pass button was in two places at once

Loop 6 portalled the commit slab and the tool strip into the foot, and threaded
the two host nodes from `Table` as props. That worked in the game and made every
`ActionPanel` story wrong: a story renders the panel without a `Table`, gets no
hosts, and draws both back in the rail — an arrangement the handheld app does
not have. Whichever surface you looked at second was lying.

`ActionPanel` finds its own hosts now, by class, scoped to its nearest `.table`.
One mechanism instead of two, no refs threaded through a class-name chain, and
any surface that renders a foot gets the real thing. `mounts.tsx` gained an
`after` stand-in — the mirror of the existing `fill` — so the panel's stories
supply the foot the same way they already supply the preview above them.

#### 7.3 The component and the stylesheet disagreed about what "handheld" means

`useHandheld()` reads `matchMedia`. Storybook's layout toolbar writes
`data-handheld` on `<html>`, because the alternative is asking a reviewer to
resize their browser. `handheld.css` honours **both** — the query re-values the
rail tokens, the attribute drives every structural rule.

So a component consulting only the query rendered the desktop structure inside
the compact stylesheet whenever the toolbar was used. `useHandheldLayout()` is
the signal for anything that moves a *node* rather than a pixel, and it is
`attribute OR query` — the same `or` the stylesheet is written with. `App.tsx`
still stamps the attribute from the query, so in the running app they are one
fact and nothing changed.

This also fixed a story that had been asserting the desktop arrangement as if it
were the invariant: "the commit slab grew out past the left of its rail" now
measures the slab against *its own container*, which is the thing the assertion
was ever about.

#### 7.4 The type line does not fit a card at 16px, anywhere

Loop 3 dropped `.face__type` and `.face__kwline` from board cards and left them
everywhere else. At the 16px floor "Creature — Vampire Soldier" needs about
200px and a card is 96 to 150 wide, so it truncated in the hand, the deck
catalogue, the dossier, the pod seats and the exit ghosts — **40-odd stories,
overflowing by 21 to 74px**. The reasoning that dropped it from the lanes was
never specific to the lanes.

It is dropped from every `.face` now and re-enabled on the three surfaces whose
card is free to grow — the preview, the prompt, the zone viewer — where it also
**wraps** instead of truncating, because none of those is 200px wide either and
re-enabling it without that just moves the truncation somewhere a player was
deliberately sent to read.

Keyed on `.face` and not `.card`: the catalogue and the pod seats render
`CardFace` with no card wrapper, which is where a first pass missed thirty
stories. And not on `.card--big` either — that is a variant, not a width; the
dossier draws one at 214px, and unlike the other three it is aspect-locked, so
wrapping would have pushed its own rules text out of the bottom.

#### 7.5 The discard prompt did not fit the screen

**668px of overflow.** Loop 2.1 widened `.opt--card` to 210-264px so a card's
rules could be read, which is right about one card and wrong about seven: at
264px a dialog fits three per row, so a nine-option discard prompt came to three
rows of 415px inside a 624px scroller. The player scrolls two screens to compare
cards they are being asked to choose between.

That is a worse failure than the one the width was bought to fix. A rule you
cannot finish reading is on the card in front of you; a card you have to scroll
to is not there at all. At 180px a nine-card hand fits in two rows with no
scroll, and the name, cost, type and stats — what a discard decision is actually
made on — are all still at 16px.

#### 7.6 The seat layout failed at exactly two opponents

Loop 6 switched the opponent arrangement on the third seat, because a four-seat
pod is the case that obviously breaks and `deckfit.spec.ts` covers one opponent
and three. **Two fell straight through the gap between them**: each mat gets
~470px, which is not enough for the one-line strip either, so the foot wrapped
and every three-player game sat 16px over its cap with the overflow hidden.

Neither e2e test could see it. A Storybook sweep found it, on an `FxLayer` story
that happens to deal two opponents. The switch is at two seats now, and
`deckfit.spec.ts` has the three-player case it was missing.

**Testing the ends is not testing the range**, and a layout that changes
arrangement by density has a boundary at every step.

### What this loop says about Loop 6

Loop 6's fixes were right and its gate was real, and it still shipped a
two-opponent board that did not fit and an `ActionPanel` that rendered
differently depending on who was asking. Both were invisible to a gate that
plays a game, because one needed a seat count the gate never used and the other
needed a surface the gate never opens.

**The game is not the only place the UI exists.** Storybook renders the same
components through a different set of ancestors, and every difference between
those two is somewhere a layout assumption can hide — which makes it a test
surface, not just a review one.

---

## Loop 8 — Meshing the mockup, and what the new gates found

**Angle.** Loops 1–7 asked whether the *shipped* board could be played on a
Deck. This one asks a different question: `mockups/handheld-board/` measured a
board with more than twice the action list and 1.6× the card, so **what is
actually in the way of having that one?**

The answer turned out to be structural rather than stylistic, and most of the
findings below are things the earlier loops could not have seen because they
were measuring a layout that had not changed shape yet.

_Run against the live engine at 1280×800 and 1200×800, and against the story
suite at both layouts._

### The measurement, before and after

| | before | mockup | after |
|---|---|---|---|
| right rail | 514px | 748 | **740** |
| action list | 172px | 363–398 | **392** |
| card reader | 152px | 236 | **236** |
| board column | 1280 (foot spanned the screen) | 1017 | **1017** |
| opponent, empty board | 84–96px of orb | 96 seat | **96 seat** |
| left rail | 232px, permanent | — | **retired** |
| regions scrolling at Deck size | none | none | **none** |

### Findings

#### 8.1 The ring could land on a card nobody can see — **the big one**

`candidatesIn` dropped only *zero-sized* stops. An opponent's lanes are
`height: 0; overflow: hidden` so their cards stay in the document for `FxLayer`
to anchor to — and **a clipped card still reports its own full box**. So the
ring could walk onto one, and no gate disagreed, because `handheldAssert`'s
`unreachable` calls that very function.

The correct ancestor-clip walk had existed in the gate since Loop 3. It had
never existed in the navigation. **The two being different is what let this
hide for five loops**, and it is the finding worth carrying: if a gate and the
thing it grades cannot share a helper, expect them to drift, and expect the
drift to be invisible in exactly the direction where the gate calls the code.

#### 8.2 The floors were never actually gated

16px of type, 44px of target, 96px of card have been asserted by
`e2e/handheld.spec.ts` since Loop 3 — and **Playwright is not in CI**. Nothing
has ever stopped a change putting a label back under the floor.

They are in the Storybook project now, which `scripts/verify.py` does run. It
found `.hand__empty` at 14px on its first execution: one selector missing from
an alphabetical list of eighty, in a state the e2e suite never reaches because
it never has an empty hand.

#### 8.3 Storybook was never showing the desktop board

The Vitest tester canvas is **1200×900** whatever `vite.config.ts` declares.
`browser.viewport`, `instances[].viewport`, a `--window-size` launch arg and a
`page.viewport()` call from `beforeEach` were each measured and each reset by
Storybook's addon before the play function ran.

Harmless until something branched on the viewport. `HANDHELD_QUERY` is
`(max-width: 1366px)`, so at 1200 **every story matched it** — and the first
component to render a different NODE on that query rendered its compact body in
the project whose entire job is proving the wide board still works.

It surfaced as two failing stories rather than as a silent wrong review only
because `CardPreview` is the first component whose two layouts differ in
markup. Loop 7's conclusion — that Storybook is a test surface and not only a
review one — needed this corollary: **a review surface has to be honest about
what it is showing**. The toolbar is authoritative now; the canvas is not.

#### 8.4 Three advertised buttons did nothing

`HintBar` printed `L1 Zone` and `L2 Menu` from its first draft, and `verbsFor`
returns `Y Read` on every card stop. **Nothing in the app listened for any of
the three.**

An advertised button that does nothing is worse than an unadvertised one: it
teaches the player that the bar is not to be trusted. Nothing in the suite could
see it either, because the bar renders spans and a span cannot fail to work.

The bar renders *from* `NAVIGATION_HINTS` now rather than restating it — which
is how "Zone" survived being renamed to "Region" in the list without changing on
screen — and a story compares what the bar can say against `pad.boundButtons()`.

#### 8.5 A held key put the poll to sleep and the release was never seen

`pad.ts`'s `onKeyUp` did not call `wake()`, and the loop idles after 100ms of
nothing changing. A key held on its own therefore idled the loop, and the
release was never observed: the `R2` opponent reader stayed up after `v` was let
go, and the region dial stayed up after `L2`.

It only ever bit the keyboard fallback, for the same reason the key latch exists
— a real pad **is** the poll, so its buttons cannot change without the loop
being the thing that notices.

#### 8.6 The fan gate was measuring paint, and it was hiding a real bug

`scrollWidth` counts a child's **transformed** box. The hand is an arc, so the
outermost cards are rotated about eight degrees and a 103px card reports a 122px
rect — every hand of six or more read as 26–30px over. The arc is the feature.

Underneath the false positive there was a real one. `HandFan` laid the fan out
against the `HAND_FAN_W` constant while the solver solved against the foot's
real width. The two agreed **by luck** for as long as the foot spanned the
screen, because 1180 was simply under it; the moment the foot moved inside the
board's column they stopped agreeing. The solver was also reading the foot's
`clientWidth`, which includes padding — the room a *scroller* has, not the room
a *fan* has.

`offsetLeft`/`offsetWidth` are untransformed layout values, which is the same
distinction `mockups/handheld-board/_board.js` records about its own
`BOARD.lay()` and the same trap `mockups/seat/assert.js` fell into.

#### 8.7 Two grid children in a three-column grid

The priority pill auto-placed into a **second row**, landing at the far left
under the ribbon, 40px from anything it related to. `.track` is a three-column
grid and the pill was a fourth child.

The floating stack had the mirror of it: every ply is absolutely positioned, so
the container has no intrinsic size on **either** axis — `StackPanel` was
telling it the height and not the width, and the panel clipped the cards to
about a third.

Neither is subtle once seen and neither was visible in any assertion. They were
found by looking at a screenshot, which after seven loops of gates is worth
recording as its own point.

#### 8.8 What the seat could not be squeezed out of

The old compact orb gave up 12px of its cap at four seats
(`--pod-seat-h: 84px`). `OpponentSeat` is a stated 96px design whose four rows
are pixels that add up, so there is nothing in it to take — and
`e2e/deckfit.spec.ts` promptly measured the viewer's mat 11px over on a
four-seat pod played several turns in.

Two levers, both honest. The handheld hand's ceiling comes down 0.34 → 0.28: the
mockup can afford 270px of foot because its board is a *fixture* and nothing on
it ever grows a fourth land row. And the shell's padding comes down 6 → 4 with
the play gap 4 → 2, because shell is the only thing on screen carrying no
information at all.

**A component that states its own size moves the search for pixels somewhere
else.** That is not a cost of this design, it is the point of it — but it means
the budget has to be found before the component ships, not after.

### What this loop says about the seven before it

Loops 1–7 were right about the board they were measuring, and five of the eight
findings above are about the **instruments** rather than the board: a gate that
did not share its helper, a gate that was not in CI, a review surface showing
the wrong layout, a hint bar nothing verified, and a fan gate measuring the
wrong property.

That is the shape of a suite maturing past the thing it was written for. The
board was checked repeatedly and carefully; what nobody had checked was whether
the checks were looking at the board.
