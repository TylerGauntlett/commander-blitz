# The decks

Four Commander-legal 100-card decks. **Every card in all four is implemented and
tested** — `tests/cards/test_every_card_works.py` plays each one and asserts it
resolves. That is what separates them from an imported deck, which is mostly
cards generated with their rules text inert ([deck-import.md](deck-import.md)).

| | Aesi | Edgar Markov | Isperia | Zurgo |
|---|---|---|---|---|
| Colours | Simic (G/U) | Mardu (W/B/R) | Azorius (W/U) | Mardu (W/B/R) |
| Avg mana value | 3.31 | 2.68 | 3.37 | 2.73 |
| Plan | Ramp, hit extra land drops, convert each land into cards, close with trample | Flood the board with vampires, buff them with lords, drain on every death and life gain | Fly over, and make attacking you the worst option on the table | Attack, make a token, let it die, turn each death into a card or a drain |

## Isperia, Supreme Judge

> Flying. Whenever a creature attacks you or a planeswalker you control, you may
> draw a card.

The trigger only pays if you survive being attacked more than once, so the deck
is built around the *defence*: twelve creatures that block well, two wraths, a
Sunblast Angel, an Evacuation, and enough counterspells that the alpha strike
never lands. The fliers are how it wins while doing that.

**What it does not have** is a pillowfort. Propaganda, Ghostly Prison and
Windborn Muse are the obvious cards for this commander and none is expressible:
the engine has no "costs more to attack" mechanic, so a card that reads like one
would be an inert enchantment pretending to be a deterrent.

Isperia is also why `defending` exists on the `attacks` trigger. Written the
obvious way — `controller: "opponent"` — she draws a card when one opponent
attacks another, which a duel cannot show you and a pod shows you immediately.

## Zurgo Stormrender

> Mobilize 1. Whenever a creature token you control leaves the battlefield, draw
> a card if it was attacking. Otherwise, each opponent loses 1 life.

Both halves needed new engine vocabulary (see [card-dsl.md](card-dsl.md)):
`attacking` on `create_token` for mobilize, and `was_attacking` on
`leaves_battlefield` for the payoff — last-known information, because by the time
the trigger resolves the token is off the battlefield and out of combat.

The list is eight more token-makers so the engine does not depend on Zurgo
surviving, and a sacrifice/drain suite **shared with Edgar Markov**. That sharing
is deliberate rather than lazy: the two decks have the same colour identity, and
Blood Artist, Cruel Celebrant and Falkenrath Noble are exactly what a deck built
to sacrifice its own creatures wants. The cost is that a chunk of Zurgo's board
is Vampires rather than Warriors, which only Chief of the Edge notices.

## The original two

Both run 37 lands, as do Isperia and Zurgo.

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
data/cards/core.cards.json      colourless staples shared by every deck
data/cards/aesi.cards.json      the Simic deck
data/cards/edgar.cards.json     Edgar's Mardu vampires
data/cards/isperia.cards.json   the Azorius deck
data/cards/zurgo.cards.json     Zurgo's token half
data/decks/*.deck.json          the four 100-card lists
```

A card id is defined **once** and referenced by any number of decks. Zurgo's list
is mostly ids that live in `edgar.cards.json`, and Isperia's borrows the blue
half of `aesi.cards.json` — which is why 81 new definitions were enough for two
whole decks. `CardRegistry.from_paths` raises on a duplicate id, so the only way
to share a card is to share it.

Test-only cards live in `tests/data/testing.cards.json` and are never loaded by a real
game — the test registry adds them, the shipped registry does not.

## Checking a deck

```bash
python scripts/validate_decks.py
```

verifies every card file parses, every card id referenced exists, both decks have
exactly 100 cards, singleton is respected outside basics, every card sits inside its
commander's colour identity, and no tokens have leaked into a deck list.

It checks the **authored** decks only, deliberately: `scripts/verify.py` has to
give the same answer on a fresh clone as on a machine with twenty imported decks.

## Bringing your own

Any public Moxfield deck can be imported and played — see
[deck-import.md](deck-import.md). The two decks above are different in kind, not
just in provenance: **every card in them is implemented and tested**, whereas an
imported deck is mostly cards generated with their rules text inert. The import
report and the deck tile both say how many, because that difference decides
whether a game makes sense.
