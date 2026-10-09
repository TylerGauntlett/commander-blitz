# Bard, King of Dale ("Bard")

## Overview & play style

Azorius tokens built around a commander who **doubles two things at once**.
Bard turns every token the deck makes into two, and every card drawn past the
first in the draw step into two. Both halves feed each other: the deck is full
of "whenever you draw your second card each turn" creatures — Prince Imrahil,
Mischievous Mystic, Emrakul's Messenger, Detective of the Month, Alandra,
Thopter Fabricator — so a one-mana cantrip is a card *and* a pair of bodies.

The game plan is **rocks, cantrips, then a crowd**. Signets, Talismans, Sol
Ring and Thran Dynamo get six mana together for Bard by turn four or five.
Before that, the cheap payoffs and the cantrip package make tokens on their
own. Once Bard lands, Raise the Alarm is four Soldiers and Caretaker's Talent
copies twice. The finish is an anthem on a board that is already wide:
Cathars' Crusade, Elesh Norn, Moonshaker Cavalry, Makindi Stampede.

It plays more like a value engine than an aggro deck; the attacks come late
and all at once.

## Win conditions

- **Moonshaker Cavalry.** Every creature flies and gets +X/+X where X is the
  number of creatures. On a board of ten, that is a kill.
- **Elesh Norn, Grand Cenobite.** +2/+2 to the tokens, -2/-2 to every
  opponent's 1/1s and 2/2s.
- **Cathars' Crusade.** Each token pair entering grows the whole board twice.
- **A wide swing.** Adeline, Makindi Stampede and Luminarch Ascension's Angels
  make an ordinary attack lethal through a few blockers.

## Key cards & combos

| Card | Why it matters |
|---|---|
| Bard, King of Dale | Doubles the tokens and the draws; the commander the deck exists for. |
| Skullclamp | On a 1/1 token it is two cards for one mana — four under Bard. |
| Prince Imrahil, Mischievous Mystic, Emrakul's Messenger | A body for every second draw; Opt becomes a creature spell. |
| Smothering Tithe | The table's draws become Treasure: six mana for Bard much sooner. |
| Caretaker's Talent | A card per token batch, a copy of a token, then +2/+2 to all of them. |
| Lightning Greaves | Shroud and haste for Bard; protection the deck otherwise lacks. |
| Cathars' Crusade, Elesh Norn, Moonshaker Cavalry | The finishers: make a crowd of 1/1s a clock. |

There is **no infinite combo** in the list. Skullclamp on token makers is the
closest thing to an engine, and the CPU plays it as one.

## How the CPU pilots it

The plan lives in
[`decks/bard_king_of_dale.py`](../../src/automtg/ai/strategy/decks/bard_king_of_dale.py)
as `BardGoWide`, a subclass of `GoWide` (which is `Aggro`).

| Behaviour | Where |
|---|---|
| **Rocks and Bard first.** Sol Ring, Signets, Talismans and Bard himself carry key-card bonuses. | `DeckPlan.key_cards`, read by `DefaultStrategy.priority_value` ([default.py](../../src/automtg/ai/strategy/default.py)) |
| **Cantrips outrank a cheap creature once a draw payoff is out.** With Prince Imrahil, Mystic, Bard or another "second card" payoff on the battlefield, a draw spell gets +150. | `BardGoWide.priority_value`, `DRAW_PAYOFFS`, `draw_bonus` |
| **Lightning Greaves goes on Bard** and is never moved off him. | `BardGoWide._equip_value` |
| **Skullclamp goes on a 1-toughness token**, which dies on the spot and draws. | `BardGoWide._equip_value` |
| **Makindi Stampede waits for the swing:** cast only precombat with three or more creatures ready to attack. | `BardGoWide.priority_value`, `stampede_attackers` |
| **Perch Protection is never cast with its gift.** Giving an opponent an extra turn is a timing play the agent cannot judge; the four Birds are the play. | `BardGoWide.priority_value` |
| **Token makers and creatures early.** | `Aggro.priority_value`, `GoWide.priority_value` ([archetypes.py](../../src/automtg/ai/strategy/archetypes.py)) |
| **A wide board swings past the blockers**, small bodies accepted as losses. | `GoWide.attack_value` |
| **Attacks are careful otherwise** (`aggression = 0.5`): no walking into a block that eats an attacker, no swinging into the crack-back. | `DefaultStrategy.attack_value` |
| **Tithe, Skullclamp and Greaves** are the last things discarded. | `DeckPlan.protect`, `DefaultStrategy.junk_value` |

## Strengths

- **Card flow.** Every cantrip, Mind Stone and Shorikai activation is two
  cards with Bard out, and most of them make a token too.
- **Recovery after a wipe.** The engines are enchantments and artifacts; a
  wrath kills the tokens, not the things that make them.
- **Cheap interaction.** Swords, Path, Cyclonic Rift, Generous Gift and Sink
  into Stupor handle the one threat that matters.
- **Flash bodies.** Raise the Alarm and Sicarian Infiltrator make blockers on
  the opponent's turn.

## Weaknesses

- **Bard costs six.** Without rocks the deck is a pile of small payoffs
  waiting for its commander, and a removed Bard is another six.
- **No lookahead on the draw count.** The "second card this turn" bonus is
  given whenever a payoff is out; the agent does not check whether this draw is
  actually the second. In practice the draw step has already drawn one, so a
  main-phase cantrip usually is.
- **Ashnod's Altar and Austere Command are played generically.** The agent
  does not sacrifice in response to removal, and picks Austere Command's modes
  by board presence, which can wipe its own tokens.
- **Life-paid mana.** Ancient Tomb, the painlands and Talismans tick down life
  the agent does not price until it is near its chump threshold.
- **Draw-matters triggers on other turns.** The Council of Four and Trouble in
  Pairs work on autopilot; the CPU does not hold mana for them.

## Mulligan

The baseline: **two to five lands and at least one play costing three or
less**. The list has plenty of one- and two-mana plays, so most hands
qualify. A hand with a rock and three lands is the ideal keep.
