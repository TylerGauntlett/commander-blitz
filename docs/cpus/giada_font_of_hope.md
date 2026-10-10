# Giada, Font of Hope — "Choir Practice"

## Overview & play style

Mono-white angels, built around one ordering rule. Giada costs two, and **every
Angel that enters after her gets a +1/+1 counter for each Angel already on the
battlefield**. The first Angel after her is a 3/3 for three; the fourth is a
three-drop with three extra counters. An Angel cast *before* Giada is an Angel
her counters never see, so the deck's whole sequencing problem is "Giada first,
then as many angels as the mana allows".

Behind the tribal curve sits a lifegain engine. Lyra Dawnbringer gives every
other Angel lifelink, and the payoffs turn life into stats or cards: Archangel
of Thune and Lyra, Archangel of Dawn put counters on the team, Exemplar of
Light draws, Resplendent Angel and Valkyrie Harbinger make 4/4s. It is a
**midrange deck that flies over everything** and gets harder to race each turn.

## Win conditions

- **Fliers.** Most turns end with a sky full of counters-laden angels and
  nothing on the ground that can block them.
- **Angel of Destiny.** At 55 life (fifteen over the starting 40), every player
  it attacked that turn loses. With Lyra's lifelink this is a real clock, not a
  dream.
- **Anthems.** Cathars' Crusade, Elesh Norn, Angel of Invention and Vanquisher's
  Banner turn a wide board into a lethal one in a single cast.

## Key cards & combos

| Card | Why it matters |
|---|---|
| Giada, Font of Hope | The commander and the reason the order matters. Her mana only casts Angels, which is all the deck wants to cast. |
| Lyra Dawnbringer | +1/+1 and lifelink for every other Angel: each combat is a lifegain event. |
| Archangel of Thune | Each lifegain event is a +1/+1 counter on the whole team. With Lyra, every hit grows the board. |
| Angel of Destiny | The alternate win. Wants Lyra (or Thune's lifelink) to get there. |
| Cathars' Crusade | A counter on everyone for every creature that enters; with Giada's counters already there, absurd. |
| Herald's Horn, Urza's Incubator | Angels cost one or two less for the rest of the game. On turn three, better than a three-drop. |

The two pairs the plan names as combos are **Lyra + Thune** (the team grows
every combat) and **Lyra + Destiny** (the lifelink that reaches 55). Neither is
infinite; both are the hands that win.

## How the CPU pilots it

The plan lives in [`decks/giada_font_of_hope.py`](../../src/commanderblitz/ai/strategy/decks/giada_font_of_hope.py)
as `ChoirPractice`, a small subclass of `Tribal` with `tribe = "Angel"`.

| Behaviour | Where |
|---|---|
| **Giada before any other Angel.** Her key-card bonus (150) puts her well over a three-drop Angel, which the classic agent preferred because it costs more. | `DeckPlan.key_cards`, read by `DefaultStrategy.priority_value` ([default.py](../../src/commanderblitz/ai/strategy/default.py)) |
| **An Angel over a non-Angel.** Every Angel cast gets the tribe bonus, so Youthful Valkyrie goes ahead of Magus of the Moat. | `Tribal.priority_value` ([archetypes.py](../../src/commanderblitz/ai/strategy/archetypes.py)) |
| **Rocks and cost reducers early.** Through turn six, a mana rock or an Angel cost reducer scores above a three-drop: each is an extra Angel per turn for the rest of the game. | `ChoirPractice.priority_value` |
| **Engines over filler.** Cathars' Crusade, Court of Grace and Vanquisher's Banner score as creatures would, not as 100-point "other" spells. | `DeckPlan.key_cards` |
| **Lyra + Thune, Lyra + Destiny.** The second piece is cast with a big bonus once the first is in hand or on the table, and the first is held back from discard. | `DeckPlan.combos`, `DefaultStrategy.combo_bonus` |
| **Attacks that the defender can block profitably are skipped**; a lethal board swings everything; the crack-back veto keeps a defence home. | `DefaultStrategy.attack_value`, `aggression = 0.6` |
| **Wide boards attack anyway.** With five or more creatures and twice the defender's blockers, the small bodies swing. | `GoWide.attack_value` |
| **Protected cards.** Lyra, Herald's Horn, Urza's Incubator and the win conditions are the last things discarded or sacrificed. | `DeckPlan.protect`, `DefaultStrategy.junk_value` |

## Strengths

- **Evasion.** Nearly every creature flies, so the board-aware attack rules
  find free attacks most turns.
- **Snowballing.** Each Angel is bigger than the last, and the lifegain engines
  make racing it a losing proposition.
- **Cheap removal.** Swords, Path, Get Lost and Fateful Absence are one- and
  two-mana answers the agent already fires at the biggest threat.

## Weaknesses

- **Board wipes.** It is a creature deck. Flawless Maneuver, Akroma's Will and
  Clever Concealment are in the list, but **the CPU does not hold mana up for
  them** — it has no lookahead, so it cannot see a wrath coming.
- **No planning across turns.** The CPU does not hold an Angel back so Giada
  can come down first *next* turn; it only orders what it can cast this turn.
- **Angel of Destiny is incidental.** No rule steers life gain toward 55 or
  chooses the attack that wins at end step; when it happens, it happens.
- **Combat tricks.** Akroma's Will is scored as a generic "other" spell, so it
  goes out at sorcery speed if nothing better is castable, not as a finisher.
- **Mono-colour, little card draw.** Inspiring Overseer, Exemplar and Tome of
  Legends are the draw; long games run out of gas.

## Mulligan

The baseline rule: **two to five lands and at least one play costing three or
less**. In practice that means a land-light hand with Giada in the command zone
is fine — she costs two, and the deck's three-drops are the curve. Hands with
six lands or with nothing castable before turn four go back.
