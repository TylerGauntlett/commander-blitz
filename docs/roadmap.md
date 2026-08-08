# Backlog
- Multiplayer online support using a basic system of rooms and room codes

# Features

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
- The theme/layout can be completley reworked
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

### Task
- Make selecting attackers to block via the right panel as seemeless as possible

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

---

## Controller support for Windows with XBox controller

### Overview
- 