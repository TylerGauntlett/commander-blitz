# The decks

Two Commander-legal 100-card decks. **Every card in both is implemented and tested** —
`tests/cards/test_every_card_works.py` plays each one and asserts it resolves.

| | Aesi | Edgar Markov |
|---|---|---|
| Commander | Aesi, Tyrant of Gyre Strait | Edgar Markov |
| Colours | Simic (G/U) | Mardu (W/B/R) |
| Plan | Ramp, hit extra land drops, convert each land into cards, close with trample | Flood the board with vampires, buff them with lords, drain on every death and life gain |
| Lands | 37 | 37 |
| Average mana value | ~3.0 | ~2.6 |

## Aesi, Tyrant of Gyre Strait

> Trample. Whenever you play a land, draw a card. You may play an additional land on
> each of your turns.

The deck is built to make that trigger fire as often as possible: 21 ramp effects, two
more sources of extra land drops (Exploration, Azusa), and payoffs that scale with
lands entering — Tatyova, Rampaging Baloths, Zendikar's Roil, Tireless Provisioner,
Avenger of Zendikar. Counterspells and instant-speed removal protect the engine; the
top end is large trampling creatures.

## Edgar Markov

> First strike. Eminence — whenever you cast another Vampire spell, create a 1/1 black
> Vampire token. Whenever Edgar Markov attacks, put a +1/+1 counter on each Vampire
> you control.

Eminence works from the command zone, which the engine supports through an ability's
`active_zones`. 37 of the 62 non-land cards are Vampires, so the token trigger fires
constantly. Legion Lieutenant, Stromkirk Captain and Vanquisher's Banner turn the
swarm lethal; Blood Artist, Cruel Celebrant, Kalastria Highborn and Sanguine Bond mean
that even losing creatures drains the table.

## Substitutions

Where a card's real text is not expressible in the effect DSL, a comparable card in
the same colours took its place. Every swap is recorded in the deck file itself and
repeated here.

### Aesi

| Original | Replacement | Why |
|---|---|---|
| Scute Swarm | Tireless Provisioner | Copy effects are not implemented |
| Rhystic Study | Guardian Project | "Unless that player pays" is not implemented |
| Cyclonic Rift | Whelming Tide | Overload is an alternative cost |
| Ancient Greenwarden | Zendikar's Roil | Needs a general replacement effect |
| Oracle of Mul Daya | Azusa, Lost but Seeking | Playing off the top of the library needs continuous zone permission |

### Edgar Markov

| Original | Replacement | Why |
|---|---|---|
| Captivating Vampire | Sanctum Seeker | Gaining control of a creature is not implemented |
| Vampire Nocturnus | Necropolis Regent | Reading the top of the library needs continuous reveal |
| Bloodline Keeper | Mavren Fein, Dusk Apostle | Transforming double-faced cards are not implemented |
| Shared Animosity | Vanquisher's Banner | A buff counting other attackers needs dependent static effects |
| Anguished Unmaking | Vindicate | Same effect at sorcery speed |
| Mortify | Hero's Downfall | Selectors cannot express "creature **or** enchantment" as one target |
| Bedevil | Dreadbore | Same reason |

Two of these — Mortify and Bedevil — point at a genuine gap rather than a deliberate
omission: the selector language has no union. Adding one would let those cards in
without any other change.

## Where the cards live

```
data/cards/basics.cards.json    5 basic lands
data/cards/tokens.cards.json    11 token definitions
data/cards/core.cards.json      colourless staples shared by both decks
data/cards/aesi.cards.json      the Simic deck
data/cards/edgar.cards.json     the Mardu deck
data/decks/*.deck.json          the two 100-card lists
```

Test-only cards live in `tests/data/testing.cards.json` and are never loaded by a real
game — the test registry adds them, the shipped registry does not.

## Checking a deck

```bash
python scripts/validate_decks.py
```

verifies every card file parses, every card id referenced exists, both decks have
exactly 100 cards, singleton is respected outside basics, every card sits inside its
commander's colour identity, and no tokens have leaked into a deck list.
