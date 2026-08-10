# Backlog
- Controller support for Windows with XBox controller

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

C:\Users\tyler\.claude\plans\cpu-improvements-majestic-storm.md

---


## Support Online Pod Creation

### Overview
- mockups\flow\02-face-up.html provides a clean and refined approach to allowing for the creation of pods
- This new flow offers the support for creating and sharing lobbies
- Up until now, absolutely no pvp games were possible so all networking requried to support "sessions" is undone
- The mockup also allow for an entirely new deck selection and import process
- The mockups also have a significant number of  sample precons but no new precons need to be added apart from the 4 that exist right now

### Task
- Impelment the new pod creation flow, adding multiplayer support
- Ensure significant unit and integration test coverage for this new backend support as it is highly complex with roubustness required for the lobby to work at all

C:\Users\tyler\.claude\plans\support-online-pod-sequential-penguin.md

Done. Two to four people, each in their own browser against one uvicorn process,
create or join a pod by code, pick decks privately, lock in, and play a real
Commander game together.

The transport is **versioned long-polling** rather than sockets, which is a
decision with consequences and so has its own record:
`docs/adr/0007-versioned-long-polling.md`. Deck secrecy in the lobby is the same
kind of contract `player_view` is for a game — `Pod.view_for` is the only way a
pod reaches the wire — and the event log had to be filtered per seat to close a
leak `player_view` never covered. Undo is refused outright in a multi-human game;
it rebuilds the `Game` by replay and the other player is holding the events being
rewound.

Four new server suites, `test_pod_races.py` being the one that finds the mistakes
in the other three. See `docs/api.md`, `docs/frontend.md` and `docs/testing.md`.

---

## Improve mana indicators

### Overview
- The mana indicators shown on the player orb do not use any actual MTG symbols
- They feel floating the middle of the box

### Task
- Convert colored dots to proper icons
- Add mana to its own panel like subdecks is

C:\Users\tyler\.claude\plans\improve-mana-indicators-lucky-patterson.md

Done. Mana is Scryfall's real symbols, counted per kind (`4{G} 2{U}`) rather than
one mark per mana, on a permanent plate. Commander damage came along, having the
same two problems: its chips name the seat and meter their progress toward 21. Both
plates joined the zone piles in `.orb__foot`, so nothing in the orb floats in the
slack any more. See `docs/frontend.md` and `docs/mockup-fidelity.md`.

---

## Variable Cost Cards

### Overview
- There are MTG cards that offer users multiple options for different costs
- There is currently no way to select which effect you'd like to trigger (example: Commanders Sphere)
- When playing/activating cards, users need to be able to trigger these
- There are also broad catagories of cards (ie kicker cost) that are flexible to how they should be used

### Task
- Add support for users to decide how they want to activate a card/which efffect to trigger. Consider using the existing attacking/defending/play panel on the right

## CI/CD to deply application

### Overview
- Using Github Actions, connect this repo with a cloud provider to enable continious delievery
- Ever new commit to main should start the build/deploy process
- A new droplet in digital ocean can be used to act as the server

### Task
- Build out CI/CD so all main branch commits produce a deployed version via Digital Ocean

---
