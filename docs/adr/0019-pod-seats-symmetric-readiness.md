# ADR 0019 — A pod is seats with symmetric readiness; a CPU differs only by deck

**Status:** accepted

[ADR 0007](0007-versioned-long-polling.md) covers how a lobby hears about a
change and [ADR 0008](0008-url-routing.md) where a pod lives. This ADR is what a
pod *is*.

## Context

The new-game screen was configuration: an opponent count, an AI toggle that
leaked agent names, a seed, and a deck list rendered as words in a box. Nothing
said where a deck came from, and only the *other* player ever locked in — the
host pressed Play and that was that.

The menu round's one surviving idea was that **a seat is the unit**: a seat has
a kind, and the screen is the table before the table. The flow round found the
holes that left — no front door, creating a pod was not an act, and readiness
was one-sided — and drew setup as four people committing one after another.

Two honesty problems were found on the way and shaped the rest. A difficulty
ladder of four tiers mapped onto two agents, so two of the tiers would have been
labels for the same opponent. And a catalogue of decks the engine could not deal
carried editorial ratings and a curve for a list that did not exist, which would
have been the single invented number on the screen.

## Decision

**A pod is a list of seats. Every seat has a kind, every occupied seat locks in,
and Start is the pod being complete.**

- **A seat has a kind**: `SeatKind` in `src/commanderblitz/server/lobby.py` is
  `empty`, `cpu`, `open` or `human`. `empty` is no chair at all — a smaller pod
  is a legal pod. `open` is a chair holding an invite that nobody has taken, and
  is never ready. There is no single-player/multiplayer fork; a CPU or an
  invitation fills a chair the same way.
- **Readiness is symmetric.** The host locks in like everybody else. A CPU is
  ready the moment it is seated, because the host chose its deck; a human is
  ready when locked in with a deck (`Seat.ready`). Start is enabled when the pod
  is complete and the player asking is locked in. `canStart` and `whyNot` in
  `frontend/src/logic/lobby.ts` answer the same question and
  `frontend/tests/lobby.test.ts` asserts them together in every case, because a
  button and its explanation disagreeing is worse than having neither.
- **Lock-in is louder than unlock.** Committing is a stamp; reconsidering is
  quieter (`.lock` against `.lock--on` in `frontend/src/styles/lobby.css`),
  because committing should feel heavier when three people are waiting on it.
- **A face-down card is one object for three facts**: an empty chair, a player
  who has not chosen, a player whose list is sealed. `CardBack` says "you do not
  get to know this yet" once.
- **A CPU differs only by its deck.** There is no difficulty ladder. What a CPU
  seat can honestly differ in is its deck and its agent, and the agent is not a
  player-facing choice while two tiers would map to one agent.
- **The server lists only decks it can deal.** There is no preview state; a deck
  in the catalogue is a deck a seat can take. An import that dropped unsupported
  cards is `partial`, with the count shown.
- **Never show an invented number.** A deck's curve and land count are derived
  from the list (`src/commanderblitz/server/deckinfo.py`); a stat that cannot be
  derived is absent, not estimated.
- **Your name lives on your seat plate**, the one editable field on any plate,
  committed on blur. The front door does not ask for it: a name is something you
  say to a table, and at the door there is not one yet.

## Consequences

- The host's own seat is a seat. There is no host-only path through the lobby
  apart from the seed field, kept because reproducible games are what the
  full-game and playtest specs run on.
- A CPU's strength is set by choosing its deck. Making the CPU stronger is engine
  work on the agent, not a lobby control.
- The catalogue cannot advertise a commander the engine cannot run. A deck
  reaches the list by being dealable, and reaches a chair by being chosen for it.
- The lobby opens on each decision it is asking you for and nudges only on a
  transition, never on state, because the pod re-renders on every poll return.
  Taking a deck moves the cursor nowhere: lock-in is the last step, not the next
  one, and only the player knows when the pod is the shape they want.
- `open` seats and long-polling are what make a shared invite work; a tab with
  no token for the pod is sent through the join flow rather than seated by the
  link.

## Rejected

- **A difficulty ladder.** Tiers that resolve to the same agent are dishonest UI.
  If a third agent ships, it is a third choice with a true name, not a rung.
- **Host presses Play.** One-sided readiness is how the old screen dealt a game
  under a player still reading their list.
- **A single-player mode switch.** Every pod is the same object; a pod of one
  human and three CPUs is not a different screen.
- **Preview decks** the engine cannot deal, with authored ratings and an
  invented curve, to make the catalogue look fuller.
- **Difficulty lamps** lighting a cumulative prefix of capabilities. They
  described agents that did not exist.
