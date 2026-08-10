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

## Storybook coverage — **done**

Storybook 10 with `@storybook/addon-vitest`, running every story as an interaction
test in a real Chromium. 246 stories covering every component in `game/`, `lobby/`
and `menu/`. See [frontend.md](frontend.md) ("Storybook") and
[testing.md](testing.md) ("Where the four frontend suites divide").

The browser mattered more than expected. jsdom cannot see the cascade the board is
built out of — no `ResizeObserver`, no `@property`, zeros from every
`getBoundingClientRect` — so the components that are *most* nearly pure geometry
were the ones with the least coverage. Writing the stories turned up four real
defects in the client's own understanding of the server contract:
`commander_damage_taken` is keyed by player and not by commander oid; an event
carries its card id in `data.card`, not `data.card_id`; an enumerated choice needs
`choice` set or the prompt cannot reach the face the server attached; and declining
combat goes through the engine's `finish_declaration` action rather than an empty
declaration.

Not done, and deliberately: `NewGameScreen` has no stories, because nothing imports
it. It should be deleted.

---

## URL routing

### Overview
- The application currently functions as an SPA without any URL changes
- This makes the application feel weird as it has to use things like query params to share rooms

### Task
- Using a React routing library, add proper support for page routing

C:\Users\tyler\.claude\plans\url-routing-clever-meteor.md

Done. react-router v7, declarative. Pods, games and decks have addresses shaped
like the API resources behind them — `/pods/:code` beside `/api/pods/{code}` —
and the server's `invite_link` points at the pod rather than smuggling a code
through `?join=`, which keeps working for links already shared.

This reverses a decision `App.tsx` argued for at length, so it has its own
record: `docs/adr/0008-url-routing.md`. The objection was real — a pod that has
dealt cannot be re-entered, so Back must not offer to — and it is answered by
`replace` on the one-way transitions rather than by refusing to have URLs. The
history stack after a full session is `["/", "/games/G"]`.

The URL carries the place; `sessionStorage` still carries the identity, because
an invite link is something people paste into a group chat. That split is what
makes **reloading at the table return you to your seat**, which had never worked
before, while a cold link to a pod you are not in still goes through the join
flow. `get_app()` now serves `frontend/dist` with a catch-all so a deep link
resolves on a deployment the way Vite already resolves it in development.

See `docs/frontend.md` ("The URL"), `docs/api.md` and `docs/testing.md`.

---
