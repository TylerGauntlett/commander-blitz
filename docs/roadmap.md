# Backlog
- Multiplayer online support using a basic system of rooms and room codes

# Features

## Card Designs

## Overview
- Enlarged and small (board cards, hand cards, etc) contain most of the requried information but the layout is sometimes messy (specifically on the board or hand sized smaller variant)
- These could be improved to more closely resemble actual MTG card layouts  while still prioritizing readability/clarity (it should not be a 1:1 mapping of the basic MTG layout)
- Additionally mana costs use custom symboles that are not reconized by the MTG community and could instead be swapped for standard svgs (ie actual icons from the game) 
- A possible example of this layout for enlarged is:

----------------
<title>
<mana costs>
<art work>
<type / subtype>
<description>
<power/toughness>
----------------

- this prevents long names from bleeding wrapping so often while still keeping mana values clear
- Additionally lands are just generally bad looking and should be fully redesigned
- Small variant should show the most critical information while the enlarged version should show essentially all information you'd find on a normal card (format optimized for this fast style gameplace)

### Task
- With this, create 5 prototypes of the small and large card types using a combination of the outline proposed above (that specifically relates to the large versions as not all the information is required at a glance for the small)

---

## Improve Commander Placement
- The commander is currently placed randomly in the left corner
- Given that this is the staple of the whole gamemode, it should instead be promoted to almost game like element when not on the board
- The box containing info like health, decks, etc could be a natrual home for something like that
- Consider intersting ways to incorperate the commander here and visualize when they are ready/ not ready

### Task
- Add the commander to the info panel containing existing core information like health and decks

## Redesign main page

### Overview
- The main page is visually unappealing and does not feel like a game (more like a standard website)
- The theme/layout can be completley reworked but should be visually consistant with the main app
- It should visually support the idea of custom decks (importable via Moxfield) and precons (pre constructed decks offically supplied by MTG)
- The AI vs random selctor doesn't make sense and should be instead show as a cleaver difficultly selector
- Preconds should be clickable to open a details modal where you can read more details like the card art, card details, playstyle, etc
- Only include 2 additional precons (first flight and zurgo stormrender)

### Task
- Create 5 different mockups of this new menu as interactable html

---

## Improved Attackers/Blockers panel
- Attackers version of the panel make it easy to assign attackers with a single click
- Defenders panel is more complicated in that it you have to both pick a defender and pick someone to defend against
- Improve this panel by offering a quick way for blockers to decide of who can be blocked, who should they
- Ensure the menu shows defenders the power/toughness of the potential attacker so they can make informed decisions
- Additionally, this same panel can be used to play cards instead of clicking them from your hand
    - Playable cards can use the same selected highlight color

### Task
- Make selecting attackers to block via the right panel as seemeless as possible
- Card playing experience by showing them in the panel as well

---

## All Card Support

### Overview
- The application was written to support just 2 precon decks
- Because of this, only cards in these 2 pre-cons are supported to display
- The import command needs to be extended to include all possible cards (art work and basic information)
- This information will be used to support the 2 additional precons planned in the new redesign
- In addition, this should offer general support for moxfield deck looking up so that users can choose their own custom deck when starting a game

### Task
- Add support for all cards, 2 additional precons (first flight and zurgo stormrender), and custom decks via Moxfield deck import

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

## Standardize Card Placement

### Overview
- The current board layout puts the lands furthest away from the player
- This is not traditionally the offical way to play MTG as it's almost always cloeset to the player
- Additionally, enchancements and creatures typically appear side by side (but with a gap always breaking them up)

### Task
- Add support for a standard MTG board layout

---

## Build redesigned main page

### Overview

- Mockups were made for a new main page
- Combine together elements of the mocks:
    - Mock 1:
    - Mock 2:
    - Mock 3:
    - Mock 4:
    - Mock 5:

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