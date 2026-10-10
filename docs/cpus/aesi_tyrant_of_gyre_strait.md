# Aesi, Tyrant of Gyre Strait — "Lander Commander"

## Overview & play style

Simic landfall. The deck's spells are its lands: **Exploration, Azusa, Oracle
of Mul Daya and Dryad of the Ilysian Grove multiply the land drops**, Aesi
draws a card off every one of them, and the payoffs — Rampaging Baloths,
Greensleeves, Scute Swarm, Zendikar's Roil, Avenger of Zendikar — turn each
drop into a creature. Ancient Greenwarden doubles every one of those
triggers.

The first several turns look like a ramp deck doing nothing. Then a turn comes
with three land drops and four payoffs on the table, the board is twelve
creatures wide, and Craterhoof Behemoth ends it. **The deck wins by not
attacking until it attacks once.**

## Win conditions

- **Craterhoof Behemoth** or **Overwhelming Stampede** over a wide board: one
  trampling alpha strike.
- **Avenger of Zendikar** plus a few land drops: a 0/1 plant per land, growing
  with every land after.
- **Card advantage.** Aesi and Tatyova draw a card a land; Rhystic Study
  taxes the table. A long game is a game this deck is ahead in.

## Key cards & combos

| Card | Why it matters |
|---|---|
| Aesi | An extra land drop and a card per land: the engine is the commander. |
| Exploration, Azusa, Oracle, Dryad | Each is one or two more land drops a turn, and so one or two more triggers. |
| Lotus Cobra | Mana per land, so the drops pay for the payoffs. |
| Tatyova | A second Aesi: a card and a life per land. |
| Ancient Greenwarden | Every landfall trigger twice, and lands back from the graveyard. |
| Avenger of Zendikar | A plant army, then a counter on each plant per land. |
| Craterhoof Behemoth | +X/+X and trample for the team, X being the team. The finisher. |

The plan names two combos: **Avenger + Craterhoof** (the army and the reason
to have one) and **Greenwarden + Avenger** (double counters on every plant per
land).

## How the CPU pilots it

The plan lives in [`decks/aesi_tyrant_of_gyre_strait.py`](../../src/commanderblitz/ai/strategy/decks/aesi_tyrant_of_gyre_strait.py)
as `LanderCommander`, a subclass of `Landfall`.

| Behaviour | Where |
|---|---|
| **Ramp spells first.** Cultivate, Kodama's Reach, Growth Spiral and anything that searches for or puts a land into play get a bonus. | `Landfall.priority_value` ([archetypes.py](../../src/commanderblitz/ai/strategy/archetypes.py)) |
| **Extra land drops early.** A permanent with an extra-land-drop static (Exploration, Azusa, Oracle, Dryad) gets a large bonus: the archetype's bonus only sees spell effects, and these are statics. | `LanderCommander.priority_value`, `extra_drops` |
| **The payoff before the land.** If a landfall payoff is affordable without this turn's land, the land drop waits: Lotus Cobra pays for itself, Tatyova draws, Baloths makes a 4/4. The classic agent always played the land first. | `LanderCommander._land_value`, `landfall_payoff` |
| **Overruns saved for a board.** Overwhelming Stampede is cast only precombat with four or more creatures; Craterhoof gets a big bonus on that board and a penalty without one (it is still a hasty 5/5 late). | `LanderCommander._overrun_value` |
| **Ground creatures stay home** unless nothing can block them — they grow on our turn and block on theirs. | `Landfall.attack_value`, `aggression = 0.4` |
| **Six-land hands are keeps.** | `DeckPlan.keep_lands = (2, 6)` |
| **Engines and fast mana.** Sol Ring, Simic Signet, Rhystic Study and Burgeoning score above their "other" floor; Aesi herself gets a cast bonus. | `DeckPlan.key_cards` |
| **Protected cards.** Tatyova, Greenwarden and the win conditions are the last to be discarded or sacrificed. | `DeckPlan.protect`, `DefaultStrategy.junk_value` |

## Strengths

- **Card flow.** With Aesi down the CPU draws two or three cards a turn
  without trying.
- **Interaction.** Counterspell, Arcane Denial, Negate, Pongify, Beast Within
  and Cyclonic Rift — the agent already counters anything costing three or more.
- **Resilience to spot removal.** The value is spread across many landfall
  permanents; losing one payoff is not losing the engine.

## Weaknesses

- **Slow.** Nothing threatening happens before turn five or six, and Propaganda
  is the only thing slowing an aggro opponent down.
- **"Castable" is approximate.** The land-hold rule compares a payoff's mana
  value to the mana on the table; it does not check colours. When the payoff
  is not really castable, the land is still the best action, so the cost is at
  worst one reshuffled decision.
- **No real turn planning.** The CPU does not count how many land drops it has
  left before deciding to cast Craterhoof, nor play out Burgeoning, Coral Atoll
  or Simic Growth Chamber bounce for extra triggers on purpose.
- **Fetch lands crack whenever the agent gets to them**, not deliberately with
  a payoff on the table.
- **Finale of Devastation** is scored as a generic X spell, not as "find
  Craterhoof".

## Mulligan

**Two to six lands and one play costing three or less.** Six lands is a keep
here because the deck turns lands into cards: six lands and Exploration is a
fine opener, where the baseline would send it back. A one-lander goes back
even with ramp, because the ramp is green sorceries that need the lands.
