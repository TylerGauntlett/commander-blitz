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

## Steamdeck Full Game Support — shipped

`mockups/handheld-board/` is meshed into the client. See `docs/frontend.md`
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

**Lane overlap.** `mockups/handheld-board/` lays a lane out with a measured
`--step` so cards overlap by exactly as much as they must; the client still
wraps. Adopting it inverts `useZoomFit`, which is `flex-wrap` arithmetic end to
end — with one card per lane the height budget stops binding and the constraint
becomes width, which is a rewrite of `logic/zoomFit.ts` rather than an addition.
It also collides with `CardStack`, which already overlaps, and the 96px floor is
already met without it. `data-fan` and the `fanOverflow` gate are the
down-payment: the gate exists before the feature.

