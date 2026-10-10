# The Ur-Dragon — "Ur-Dragon"

## Overview & play style

Five-colour dragons, built at a much higher power level than a precon: dual
lands, fetches, Mana Vault, Chrome Mox, Mox Diamond, Demonic Tutor and The One
Ring. The plan is simple and fast — **fast mana first, then dragons, then let
them fly**. The Ur-Dragon's eminence works from the command zone, so every
dragon is a mana cheaper before the commander is ever cast, and once it is on
the battlefield every attack draws a card per attacking dragon and puts a free
permanent onto the battlefield.

What turns big fliers into a kill is the **damage engine**: Terror of the
Peaks, Scourge of Valkas and Dragon Tempest turn each dragon that enters into a
burn spell, Twinflame Tyrant and Neriv double the damage, and Lathliss and
Miirym make more dragons to trigger them.

## Win conditions

- **Combat.** 5/5 and bigger fliers, often with haste (Dragonlord Kolaghan,
  Rhythm of the Wild, Temur Ascendancy, Tannuk).
- **Enter triggers.** With Terror of the Peaks down, each dragon is its own
  power in damage to any target; Scourge and Dragon Tempest add X per dragon.
- **Dracogenesis.** Every dragon after it is free.

## Key cards & combos

| Card | Why it matters |
|---|---|
| The Ur-Dragon | Discount from the command zone; on the battlefield, every attack is card draw and a free permanent. |
| Birds, Hierarchs, Sol Ring, Mana Vault, Arcane Signet | The acceleration. Turn-three dragons are how this deck wins. |
| Terror of the Peaks | Every other creature entering deals its power to any target. |
| Miirym, Sentinel Wyrm | A token copy of each nontoken dragon: two enter triggers per cast. |
| Lathliss, Dragon Queen | A 5/5 dragon token per nontoken dragon. |
| Draconic Visitor | Every artifact token becomes a 5/5 flier — and the deck makes a lot of Treasure. |
| Dracogenesis | Dragons cost nothing. |

The plan names four combos, each a pair that multiplies the other:
**Terror + Miirym**, **Lathliss + Terror**, **Draconic Visitor + Goldspan** and
**Draconic Visitor + Old Gnawbone** (Treasures become dragons).

## How the CPU pilots it

The plan lives in [`decks/the_ur_dragon.py`](../../src/commanderblitz/ai/strategy/decks/the_ur_dragon.py)
as `UrDragon`, a subclass of `Dragons`.

| Behaviour | Where |
|---|---|
| **Rocks and dorks are ramp.** `Dragons` boosts what `classify` calls "ramp", which is land search — and this list runs none. Through turn eight, any nonland permanent that taps for mana scores above a three-drop, falling off each turn. | `UrDragon.priority_value`, `makes_mana` |
| **Dragons over other creatures.** The tribe bonus. | `Tribal.priority_value` ([archetypes.py](../../src/commanderblitz/ai/strategy/archetypes.py)) |
| **Demonic Tutor early.** It searches the library, so `classify` calls it ramp and `Dragons` boosts it through turn twelve. | `Dragons.priority_value` |
| **Enablers before the dragons.** Dragon Tempest, Rhythm of the Wild, Temur Ascendancy and Up the Beanstalk get bonuses that put them ahead of filler, so they are down before the dragons they trigger off. | `DeckPlan.key_cards` |
| **The commander cast as soon as it can be.** | `DeckPlan.key_cards` |
| **Damage engines paired.** With Miirym or Lathliss in hand or on the table, Terror of the Peaks gets the combo bonus, and the reverse. | `DeckPlan.combos`, `DefaultStrategy.combo_bonus` |
| **Fast-mana hands are keeps.** One land with two cheap mana sources is kept; the baseline mulligans it. | `UrDragon.keep_hand` |
| **Attacks trade when the board is even.** `aggression = 0.6`: below the "accept trades" threshold, so it swings where fliers are unblockable and holds back where a blocker eats the attacker. Wide boards (four or more creatures) swing anyway. | `DefaultStrategy.attack_value`, `GoWide.attack_value` |

## Strengths

- **Speed.** Fast mana plus eminence means 5-drop dragons on turn three.
- **Evasion.** Everything that matters flies.
- **Card advantage.** The Ur-Dragon's attack trigger, The One Ring, Up the
  Beanstalk and Temur Ascendancy keep the hand full.
- **Interaction it actually uses.** Swan Song and Stubborn Denial are one-mana
  counters the agent fires at anything costing three or more.

## Weaknesses

- **Long games can stop on the engine's loop guard.** A board of Dragon token
  makers and Ganax, Astral Hunter's Treasure trigger can queue more than 200
  triggers in one step, which the engine stops and the arena scores as a draw.
  It is an engine limit rather than a plan decision, but it is how some of this
  deck's best boards end.
- **The free permanent is the agent's choice, not the plan's.** The Ur-Dragon's
  "put a permanent from your hand onto the battlefield" is answered by the
  generic choice logic, not steered toward the biggest dragon.
- **Fast mana is spent, not sculpted.** Chrome Mox imprints and Mox Diamond
  discards are whatever the agent's discard rule picks; Mana Vault is cast even
  when nothing uses the burst.
- **No lookahead.** It does not hold Teferi's Protection for a wrath or Crux of
  Fate for the right moment, and it cannot see two-turn lines like "Tiamat,
  then Dracogenesis".
- **Life as a resource.** Fetch lands, Mana Confluence, City of Brass and The
  One Ring's burden all cost life the agent barely prices.
- **Five colours.** The land rule plays the colour the hand needs, but a hand
  of off-colour dragons with the wrong duals still stalls.

## Mulligan

**Two to five lands and an early play**, the baseline — plus one exception:
**one land and two mana sources costing two or less is a keep**. Sol Ring and
Birds of Paradise cast the same dragons a second land would, and faster.
