# Blor the Impervious ("Blor")

## Overview & play style

Mono-green Voltron with the **best Voltron body in the format's cheap end**:
Blor is a five-mana 3/3 with trample, hexproof and indestructible. The usual
Voltron problem — you spend four turns building one threat and a single
removal spell undoes it — mostly does not apply. Spot removal cannot target
him, destroy effects do nothing, and every Aura on him is as safe as he is.

So the deck is a **ramp deck that turns into an equip deck**. Elves, Utopia
Sprawl, Wild Growth, Nature's Lore and Three Visits put Blor on the table on
turn three or four; after that every turn is an equip activation and an attack.
The equipment suite is deep — Commander's Plate, Sword of Fire and Ice,
Swordsman's Steel, Bone Sabres, Genji Glove, Inquisitor's Flail, Power Fist —
and the Auras (Strong Back, Bear Umbra, Level Up) stack on top. Blor needs to
connect two or three times; 21 commander damage arrives faster than anyone's
life total runs out.

## Win conditions

- **Commander damage.** The plan, almost always. Trample means chump blocks
  only buy a little, and a 10/10 Blor ends a game in two swings.
- **Doubled double strike.** Genji Glove gives double strike and an extra
  combat; Inquisitor's Flail doubles every hit. Together they are four times
  Blor's power in one turn — with two other equipment, one player is dead.
- **Card advantage from hits.** Sword of Fire and Ice, Mask of Memory, Buster
  Sword, Hunter's Insight and Keen Sense refill the hand, so the deck rarely
  runs out of things to strap on.

## Key cards & combos

| Card | Why it matters |
|---|---|
| Blor the Impervious | Untargetable, unkillable, tramples: the safest place in the game for equipment. |
| Commander's Plate | +3/+3 and protection from every non-green colour, for an equip-commander cost of three. |
| Strong Back | +2/+2 per attachment, and equips onto Blor cost three less. |
| Sword of Fire and Ice | Stats, protection, two damage and a card every hit. |
| Genji Glove + Inquisitor's Flail | The one real combo: double strike, an extra combat, double damage. |
| Bear Umbra | Untaps the lands on attack, so the second main phase can equip again. |
| Berserk | Doubles Blor's power; the "destroy it" clause does nothing to an indestructible creature. |
| Sol Ring, Utopia Sprawl, elves | Blor on turn three is the single best start. |

## How the CPU pilots it

The plan lives in
[`decks/blor_the_impervious.py`](../../src/automtg/ai/strategy/decks/blor_the_impervious.py)
as `BlorVoltron`, a subclass of `Voltron`.

| Behaviour | Where |
|---|---|
| **Equipment goes on Blor**, never moved off him, never onto an elf while he is out. | `Voltron.priority_value`, `equip_bonus` ([archetypes.py](../../src/automtg/ai/strategy/archetypes.py)) |
| **Auras go on Blor**; Utopia Sprawl and Wild Growth still go on our own lands. | `Voltron.priority_value`, `aura_bonus` |
| **Tanuki Transplanter reconfigures onto Blor.** Reconfigure is an attach that is not an equip ability; `Voltron` treats any attach the same way. | `Voltron.priority_value` (`_attaches`) |
| **An equip is spent once a turn, and never onto the creature already wearing it.** Without this guard, found by this deck's smoke games, the CPU re-equipped Staff of Titania onto the same elf until the game stalled. | `Voltron.priority_value` |
| **Ramp and the strongest equipment first** — Sol Ring, land ramp, Plate, the Sword, Strong Back. | `DeckPlan.key_cards`, read by `DefaultStrategy.priority_value` ([default.py](../../src/automtg/ai/strategy/default.py)) |
| **Genji Glove and Inquisitor's Flail** get a combo bonus once the other is in hand or on the table. | `DeckPlan.combos`, `DefaultStrategy.combo_bonus` |
| **Blor attacks the player he has already hurt most**, then whoever can block him least. | `Voltron.defender` |
| **Blor attacks whenever the block cannot kill him** — which, being indestructible, is always. The crack-back veto can still keep him home. | `DefaultStrategy.attack_value` |
| **The rest of the team stays home** unless its attack is free. | `Voltron.attack_value` |
| **Blor blocks.** `Voltron` keeps its commander out of blocks so it lives to swing; an indestructible Blor survives every block and does not tap for it. | `BlorVoltron.block_value` |
| **Berserk on Blor** at the pump window is a priority play. | `DeckPlan.key_cards` |
| **Two-land hands need a dork or Sol Ring.** | `BlorVoltron.keep_hand` |
| **The Plate, Strong Back and the Sword** are the last things discarded. | `DeckPlan.protect`, `DefaultStrategy.junk_value` |

## Strengths

- **Removal-proof.** The usual answers to a Voltron commander — Swords,
  Path, Doom Blade, Beast Within — cannot touch Blor. The table needs a
  sacrifice effect, a wrath that exiles, or a bounce-all.
- **Fast.** Eight one-mana accelerants and land ramp put a five-drop down on
  turn three often enough to matter.
- **Self-refilling.** Hit triggers from the Sword, Mask of Memory and Buster
  Sword mean a connected attack replaces the cards it took to build.
- **Free defence.** An indestructible blocker with a growing body walls
  ground attackers all game.

## Weaknesses

- **Edicts and mass bounce.** Each opponent sacrificing a creature, or
  Cyclonic Rift overloaded, removes or resets Blor; the CPU does not keep a
  second creature around as edict insurance.
- **Chump blockers.** Trample helps, but a wide token deck soaks hits. The
  CPU picks its defender by commander damage dealt, not by who has the
  fewest chump blockers.
- **No sequencing lookahead.** The agent takes the single best-scoring action
  each time, so it may cast an equipment and then lack the mana to equip it,
  or equip before casting a creature. A creature cast still outscores an equip.
- **Combat tricks are blunt.** Berserk, Ram Through and Legolas's Quick
  Reflexes are timed by the agent's generic pump/removal windows, not to
  blocks that matter.
- **Assault Suit is played straight.** Its "you may give the equipped
  creature to that opponent" is a *may*, and the agent says yes to every may
  — so Blor spends opponents' turns attacking each other. Usually fine, never
  chosen.
- **Hideaway and Urza's Saga** run on the engine's defaults; the CPU does not
  plan around Mosswort Bridge's power-ten condition.

## Mulligan

**Two to five lands with an early play**, as the baseline — plus one rule:
**a two-land hand needs a one-mana accelerant** (an elf, Delighted Halfling,
Sol Ring). Blor costs five, and a two-land hand without a dork casts him on
turn five at best. One mulligan in, the CPU keeps two-landers anyway.
