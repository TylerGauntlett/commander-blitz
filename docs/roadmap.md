# Backlog

*(Controller support is done -- see `docs/frontend.md`, "Playing with a
controller". The client is playable end to end on a gamepad at a Steam Deck's
1280x800, with the legibility floors asserted in CI.)*

# Features

## CPU Improvements

### Overview
- The AI had minmal training data and preforms very poorly
- This results in almost entirely random decisions that almost always lose the game without it being challenging
- Via this method, that app can offer difficulty levels for the CPU at the main menu that acutally influence the play style
- This is a uniquely hard problem as there are so many different ways to play MTG and variables involved
- Instead of trying to teach the model optimal play through pure machine learning, there is likely more deterministic the system could include at the various skill levels
- Basic concepts like blocking when safe to do so or attacking when safe to do so can be applied at the easiest levels
- From there, more complex decisions can be made to better stear the CPU into the correct choices based on the selected difficulty
- These could be written in the form of subagents writing persona documents for each supported difficulty
- These personas should document general strategies, expected behavior, etc
- This can then be turned into requirements and ultimately code

### Task
- Make the CPU opponents better at various levels using a combination of ML and deterministic conditoinals

<local-plans>\cpu-improvements-majestic-storm.md

---

## The opening hand — shipped

the mulligan round's 01 'The Deal' (`docs/design-record.md#mulligan`) is meshed into the client as `OpeningHand`. See
`docs/frontend.md` ("The first decision of every game has its own screen") for what it is
and the mulligan round (`docs/design-record.md#mulligan`) for why it looks that way.

The first decision of every game was a centred rectangle with two identical grey buttons,
drawn on top of a 73.6px hand whose rules text resolved to 8.5px and was dropped. It is now
a full screen of seven cards you can read.

Measured at 1280x800 against the mockup's own numbers:

| | mockup | shipped |
|---|---|---|
| card | 296 x 414 | 296 x 414 |
| pitch | 144 | 144 |
| row top | 100 | 100 |
| margin, ink to bezel | 27 | 27 |
| rules text | 16px | 16px |
| open rules boxes | 1 | 1 |

- **`--mu` is exactly 1 on a Deck**, 1.19 at 1600x950 and 0.94 at 1200x800, and the arch
  holds still through a walk of the whole row at all three.
- **Both halves of a London mulligan** are answered on it. The bottoming step is told apart
  from every other `choose_objects` by a `purpose` tag the engine now stamps, not by its
  prompt string.
- **`mulligans_taken` is on the wire** for the first time, as the lamps.
- **`A` keeps from a card, `B` mulligans**, and `verbs.ts` says so in the hint bar.

### Deliberately not done

**The other four directions.** the mulligan round (`docs/design-record.md#mulligan`) drew five and this ports one. 02's read
panel is the one most worth revisiting — it answers "should I keep this" better than any
card's rules text does — but it is a different screen rather than an addition to this one.

**A deeper read.** The mockup round's 02-05 all raise a card to 296px over the room on `Y`;
this direction does not need one, because the card you are on is already at that width.
`Y` still opens `CardHold` app-wide and is left alone.

## Steamdeck Full Game Support — shipped

the handheld-board round (`docs/design-record.md#handheld-board`) is meshed into the client. See `docs/frontend.md`
("Where things sit on screen", "What the compact layout gives up", "Jumping
around the board") for what the board is now, and `docs/testing.md` for the
gates that hold it.

What landed, and the measured numbers at 1280x800 against the mockup's:

| | mockup | shipped |
|---|---|---|
| rail height | 748 | 740 |
| reader | 236 | 236 |
| action list | 363-398 | 392 |
| board column | 1017 | 1017 |
| opponent seat | 332x96 | 96 tall, capped 420 wide |

- **The rail runs the full height at every size.** The foot moved inside the
  board's column, and the left rail is retired — the log is an overlay on
  `View` and the stack floats over the top-left of the board.
- **An opponent is an `OpponentSeat`**, at every size, so a desktop and a
  handheld are not two designs for one fact. Their *lanes* are what a handheld
  gives up, clipped rather than removed so `FxLayer` keeps its anchors.
- **The reader is a landscape window**, not a small card.
- **Pressing a seat stands you at it**; `R2` held is still the glance.
- **`L1`/`R1` step between five regions**, `L2` held opens a dial, `Y` reads the
  focused card full screen, and the ring moves itself when the decision changes.
  All three of the buttons the hint bar had been advertising unbound are bound.
- **The floors are in CI for the first time**, as a second Storybook project at
  1280x800.

### Deliberately not done

**Lane overlap.** the handheld-board round (`docs/design-record.md#handheld-board`) lays a lane out with a measured
`--step` so cards overlap by exactly as much as they must; the client still
wraps. Adopting it inverts `useZoomFit`, which is `flex-wrap` arithmetic end to
end — with one card per lane the height budget stops binding and the constraint
becomes width, which is a rewrite of `logic/zoomFit.ts` rather than an addition.
It also collides with `CardStack`, which already overlaps, and the 96px floor is
already met without it. `data-fan` and the `fanOverflow` gate are the
down-payment: the gate exists before the feature.

