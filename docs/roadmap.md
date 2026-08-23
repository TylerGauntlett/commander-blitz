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

## Steamdeck Full Game Support

### Overview
- A high quality mock of what the game could look like at a steam deck resolution can be found in mockups\handheld-board
- This is a full redesign of the UI to best utialize the small space present on a Steam Deck resolution
- This does not add or remove any core functionality present today
- Additionally, this viewport size eliminates the opponent's board. This should only happen when the screen size is so small, it requires it (ie on steam deck but not on desktop)
- the player orb, opponent orb and action panel on the rail have all been updated. the hand/board/game info are rough stand-ins worse than what is shown in the game today
- Due to space constraints, the full card in the top right is compressed
- Preserve the size, arc effect, and on hover moving the card higher in the hand cards as it works today

### Hotkeys
- Because space is so limited, hotkeys will be required to quickly jump around the boards
- Examples of hotkeys would be:
    - a hotkey to show the hovered card full screen (showing the card exactly as it is shown in the top right today with card text overlayed on card art)
        - Note: in general, the various cards and card sizes are fine as is and should be used without alterning (just using the correct sized card at the correct time/location)
    - a hotkey to jump between major component groups with a focus trap inside each group
        - This would allow you to cycle through hand, action panel, opponent orbs, player orb, and battlefield. This could be offered both in a forwarded/backwards approach as well as a radial dial that lets you quickly jump to a specific one
        - Additionally, you could sensible move focus for the player automatically as the stages progress to that most likely needed (for example, moving to combat would move focus into the action panel so users can pick selectors)
        - The opponent orbs should also be selectable. When selected, it should show that opponents board state instead of your own. This allows users to have full visual of the board states across all players while in a small screen

## Task
- Mesh together the mockups and the existing code
- Ensure the desktop experience is not comprimised by still rendering based on avalible screen space
- Ensure the steam deck experience looks and feels as much like a dedicated game as possible. Limit the use of scroll bars, and keep all important information on screen without bleeding over
- Ensure full test coverage for both desktop and handheld flows via storybook and playwright. All new code should be well tested
- Assess any visual issues and resolve as needed
- This is a very large effort re-write of the entire game state UI. use /goal is needed to ensure the model does not stop until this is fully completed