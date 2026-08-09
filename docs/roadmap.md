# Backlog
- Multiplayer online support using a basic system of rooms and room codes

# Features

## All Card Support

### Overview
- The application was written to support just 2 precon decks
- Because of this, only cards in these 2 pre-cons are supported to display
- The import command needs to be extended to include all possible cards (art work and basic information)
- This information will be used to support the 2 additional precons planned in the new redesign
- In addition, this should offer general support for moxfield deck looking up so that users can choose their own custom deck when starting a game

### Task
- Add support for all cards, 2 additional precons (Isperia, Supreme Judge and zurgo stormrender), and custom decks via Moxfield deck import

---

## Progressive Zoom

### Overview
- The game typically starts with very few cards and ends with very many
- This leads to poor use of screen real estate early in the game as the benifit of being able to show the game state end game
- Instead, the board zooms (both user and CPU) + cards in hand could use a more intelligent zoom system that tries to maximize readability at all stages of the game

### Task
- Impelement a system that automatically scales cards/board areas up and down depending on the number of cards present

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

---

## Standardize Card Placement — done

### Overview
- The board used to render four full-width rows in the same order on every mat,
  with the lands furthest from the player who controls them
- That is the opposite of how the game is physically played: your mana sits in
  the row nearest you, and creatures go out front
- Creatures and enchantments were also split into separate rows, when on a table
  they sit side by side

### What shipped
- **Two bands per mat.** Creatures (with planeswalkers) beside the global
  artifacts and enchantments across the front, split 2:1 because that is where
  the cards accumulate; lands in the band behind them. They remain two separate
  drop targets — only the row is shared.
- **Lands nearest their controller.** `LANES` in
  `frontend/src/logic/zoneGrouping.ts` is now declared front to back, so the
  array is the layout.
- **Opponent mats are mirrored** (`PlayerMat`'s `mirrored` prop). Their lands sit
  against their own edge of the screen, which puts the two creature bands either
  side of the table's midline and makes combat read as a line.
- **Auras and equipment are tucked under their host**, not loose in the
  enchantment zone. `attachmentsFor` pulls anything attached to a permanent on
  the same mat out of the lanes and `CardStack` draws it peeking out from
  underneath, still individually hoverable and clickable. An attachment whose
  host is on somebody else's board stays a loose card rather than vanishing.
- **Your own board holds still.** All three of the viewer's lanes render at a
  full card's height whether or not they hold anything, and the orb's mana row
  has a reserved slot. Before this, playing your first creature shoved the land
  row down by a whole card, killing it shoved the row back up, and tapping mana
  did it again several times a turn. The cost is one card height of empty slot
  on a mat that fills anyway.

### Known limit
Opponent mats are still content-sized, so an opponent's board growing can still
translate your board down the screen. Reserving their lanes too was tried and
measured, and it made things worse: a compact mat has about 158px of lane width
against a 51px card, so an always-present global lane wrapped their creatures
onto an extra row, grew the opponents row 20px and clipped the viewer's lands in
a four-player pod. Fixing this properly means giving compact mats a fixed lane
height and letting them scroll internally — the fade affordance on
`.mat--compact .mat__lanes` already exists for it — rather than reserving width
they do not have.

### Deliberate divergence from the reference layout
The reference diagram puts library / graveyard / exile in a strip beside the
lands. They stay in the orb column instead: graveyard and exile are consulted
rarely enough that the width is better spent on the board, and the orb already
gives each one a labelled pile.

Guarded by two cases in `frontend/e2e/layout.spec.ts`: "lands sit nearest the
player who controls them" and "the viewer's bands do not move as permanents
enter and leave play". Both band orders render perfectly well and a jumping
board renders perfectly well, so only a measurement notices a regression.

---

## Build redesigned main page

### Overview

- Mockups were made for a new main page, in [mockups/menu/](../mockups/menu/README.md).
  All five are interactive: pick a deck, open a dossier, set difficulty, import
  from Moxfield, open a chair to another player, press `g` for greyscale.
- Combine together elements of the mocks:
    - Mock 1 — **Command Table**: the board's own three-column anatomy, and the
      *seat strip* — opponents are chairs you fill, each showing the deck that AI
      holds and how well it plays. Recommended as the base.
    - Mock 2 — **Deck Rack**: precons as physical boxes with an art window and
      back-of-box copy; the custom deck is a *dashed gap in the rack*; the
      dossier *expands in place* instead of opening a modal; difficulty is the
      shipped brass life dial as a four-detent switch.
    - Mock 3 — **Pod Lobby**: *difficulty as opponents* — one named persona per
      seat with its capability lamps, so a pod can be one Apprentice and one
      Archmage. The direction multiplayer costs nothing to add to.
    - Mock 4 — **Ink & Dossier**: the *comparison matrix* — all decks rated on
      one scale so choosing is a comparison, not four readings. Hue spent only on
      mana; its greyscale twin is identical to the original.
    - Mock 5 — **Planar Gate**: the screen takes the selected deck's colour.
      Beautiful, and its greyscale twin is the honest argument against it.

### Task

### Remaining gaps

The board is built against `mockups/05-planar-art.html`. The phase ribbon, the card
layout, the enlarged rail card and the unified action panel have landed. What is
still outstanding is enumerated, with severity and a fix direction, in
[mockup-fidelity.md](mockup-fidelity.md) — read its "Deliberate divergences"
section before changing anything to match a mockup.

The two worth doing first are both greyscale failures, and neither is cosmetic:
the "you can play this" rim and the combat arrows each carry their whole meaning in
hue, so a player who cannot use colour loses the most urgent fact on screen.

---

## Controller support for Windows with XBox controller

### Overview
- 