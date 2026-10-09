# Vivi Ornitier — "Vivi"

## Overview & play style

Izzet spellslinger with a commander that is both the engine and the mana.
**Every noncreature spell puts a +1/+1 counter on Vivi and deals 1 damage to
each opponent**, and once a turn her {0} ability adds mana equal to her power.
So each cantrip makes the next one cheaper, and a Vivi with six counters is a
Sol Ring that also pings the table.

The list is built around that loop: a dozen one- and two-mana cantrips and
burn spells, counters for the turns Vivi needs to survive, magecraft creatures
that draw or ping again (Archmage Emeritus, Archmage of Runes, Exalted Flamer,
Caldera Pyremaw, Storm-Kiln Artist), and two **trigger doublers**. Harmonic
Prodigy doubles Vivi's own trigger because Vivi is a Wizard; Veyran doubles
every cast trigger an instant or sorcery causes. It is a **fast, fragile,
high-skill deck**: everything runs through a 0/3.

## Win conditions

- **The ping.** Vivi plus Exalted Flamer, Pyremaw and Urabrask is three or four
  damage to each opponent per spell. Over a long turn, that is the game.
- **Aetherflux Reservoir.** A storm turn gains enough to pay 50 life and point
  50 damage at one opponent.
- **Chandra's Ignition off a huge Vivi.** Vivi's power to every other creature
  and every opponent.
- **Crackle with Power.** The X spell that converts a big mana turn into
  fifteen damage at one or more targets.

## Key cards & combos

| Card | Why it matters |
|---|---|
| Vivi Ornitier | Engine, mana source and win condition. Out on turn three, always. |
| Curiosity, Ophidian Eye | Vivi's ping is damage to an opponent: with one on her, **every noncreature spell draws a card per opponent**. |
| Harmonic Prodigy, Veyran | Two counters and two damage per spell; with both, four. |
| Winged Boots | Ward 4 is the deck's only real protection for its engine. |
| Rhystic Study, Archmage Emeritus, Archmage of Runes | The card flow that keeps the spells coming. |
| Aetherflux Reservoir | The finisher a dozen cheap spells pays for. |

The plan names four **combos**: Vivi + Curiosity, Vivi + Ophidian Eye, Vivi +
Harmonic Prodigy and Vivi + Veyran. None is infinite; each turns Vivi from a
mana engine into a card or damage engine, and each partner is cast with a big
bonus while Vivi is in hand, in the command zone or on the battlefield.

## How the CPU pilots it

The plan lives in [`decks/vivi_ornitier.py`](../../src/automtg/ai/strategy/decks/vivi_ornitier.py)
as `ViviSpellslinger`, a subclass of `Spellslinger`.

| Behaviour | Where |
|---|---|
| **Vivi first.** Her key-card bonus (120) puts her over any other three-drop or a mana rock. | `DeckPlan.key_cards`, read by `DefaultStrategy.priority_value` ([default.py](../../src/automtg/ai/strategy/default.py)) |
| **Instants and sorceries outrank other spells**, a little more precombat. | `Spellslinger.priority_value` ([archetypes.py](../../src/automtg/ai/strategy/archetypes.py)) |
| **With Vivi out, every noncreature spell is worth more** — artifacts and enchantments trigger her too, which plain `Spellslinger` does not know. | `ViviSpellslinger._cast_value` (`VIVI_TRIGGER`) |
| **Curiosity and Ophidian Eye go on Vivi or nowhere.** The classic agent put them on whatever creature came first, often an opponent's. Without Vivi on the battlefield they wait in hand. | `ViviSpellslinger._cast_value` (`PINGER_AURAS`) |
| **Winged Boots equip Vivi and stay there.** | `ViviSpellslinger._equip_value` |
| **Burn and bounce never hit our own permanents.** Removal was already vetoed at our board; Lightning Bolt, Ice Magic and friends classify as "other" spells and were not. Spells that *ask* for our creature (Chandra's Ignition) are exempt. | `_hurts_own` |
| **Chandra's Ignition only off a 4-power creature**, scored by that power. | `ViviSpellslinger._cast_value` (`IGNITION_FLOOR`) |
| **Aetherflux Reservoir fires the moment it can** — at an opponent, never at a creature. | `ViviSpellslinger.priority_value` |
| **Combo partners first, and never discarded.** | `DeckPlan.combos`, `DefaultStrategy.combo_bonus`, `junk_value` |
| **Vivi attacks only when nothing can eat her**; she is a mana engine, not a beater. | `DefaultStrategy.attack_value`, `aggression = 0.4` |

## Strengths

- **Inevitability.** Every spell grows Vivi and chips the table, so the clock
  runs even on turns where nothing else happens.
- **Cheap interaction.** Pongify, Reality Shift, Lightning Bolt and Arcane
  Denial come out at the costs the agent likes, and removal goes at the biggest
  threat.
- **Card flow.** Cantrips, Rhystic Study and Curiosity mean the CPU rarely runs
  out of things to do.

## Weaknesses

- **Vivi is a 0/3.** A single removal spell resets the engine and her counters.
  The CPU does not hold a counterspell up to protect her: it casts on its own
  turn whatever scores highest, and only counters with mana left over.
- **No storm turn.** The deck wants to chain spells off Vivi's mana in one
  turn; the CPU plays spells one at a time as they score, and Vivi's mana
  ability is just another mana source to it. It has no notion of "go off now".
- **Modal spells pick their targets after the mode.** Abrade, Flame of Anor and
  other "choose one" spells are scored before their targets exist, so the
  own-permanent veto cannot see them; the mode and target choices fall back to
  the baseline.
- **Copy and graveyard tricks are played generically.** Mizzix's Mastery,
  Expansion // Explosion, Kitsa's copy and Lier's flashback get no special
  sequencing; they are cast when they score.
- **Instants at sorcery speed.** Outside counterspells, the agent casts its
  instants in its own main phase, so Brainstorm and Frantic Search lose their
  end-of-turn value.

## Mulligan

The baseline: **two to five lands and at least one play costing three or
less** — which in this deck is nearly every hand, since Vivi herself costs three
and the cantrips cost one. Hands of six lands or one land go back.
