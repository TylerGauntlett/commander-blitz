# The decks

Twelve Commander-legal 100-card decks ship with the game, each named after its
commander, with no substitutions left in any of them. **Every card in all twelve
is implemented and tested** — that is what separates them from an imported deck,
whose unsupported cards are generated with their rules text inert
([deck-import.md](deck-import.md)).

Ten are real Moxfield lists, imported card for card and promoted into
`data/decks/` by `scripts/promote_deck.py`; Isperia and Zurgo are the two
original hand-built precons. **Each one is piloted by a CPU strategy of its own**,
and each has a page in [cpus/](cpus/README.md) on how it plays, how it wins and
how the CPU drives it.

| Deck | Colours | Moxfield list | Plan | CPU |
|---|---|---|---|---|
| Aesi, Tyrant of Gyre Strait | G/U | Lander Commander | Extra land drops, a card per land, a board of landfall payoffs | [landfall](cpus/aesi_tyrant_of_gyre_strait.md) |
| Atraxa, Praetors' Voice | W/U/B/G | Superfriends | Planeswalkers, proliferated toward their ultimates | [superfriends](cpus/atraxa_praetors_voice.md) |
| Bard, King of Dale | W/U | Bard | Tokens and value on a wide board | [go wide](cpus/bard_king_of_dale.md) |
| Blor the Impervious | G | Blor | One commander, suited up and sent in | [voltron](cpus/blor_the_impervious.md) |
| Bruvac the Grandiloquent | U | Millington | Mill, doubled; counter what stops it | [mill + combo](cpus/bruvac_the_grandiloquent.md) |
| Edgar Markov | W/B/R | Markov Chains | Vampire swarm, lords, drain on every death | [vampire tribal + drain](cpus/edgar_markov.md) |
| Giada, Font of Hope | W | Choir Practice | Angels that arrive bigger than they are printed | [angels](cpus/giada_font_of_hope.md) |
| Isperia, Supreme Judge | W/U | — | Fly over, and make attacking you the worst option on the table | [control](cpus/isperia.md) |
| Sheoldred, the Apocalypse | B | Draw Death | Punish every card the table draws | [punisher](cpus/sheoldred_the_apocalypse.md) |
| The Ur-Dragon | W/U/B/R/G | Ur-Dragon | Ramp into dragons, then let them fly | [dragons](cpus/the_ur_dragon.md) |
| Vivi Ornitier | U/R | Vivi | Instants and sorceries, every one of them a trigger | [spellslinger](cpus/vivi_ornitier.md) |
| Zurgo Stormrender | W/B/R | — | Attack, make a token, let it die, turn each death into a card or a drain | [aristocrats](cpus/zurgo.md) |

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

## Test fixtures

The first Edgar and Aesi lists — the Reap the Tides precon and a hand-built
vampire deck — were retired from the catalogue when the Moxfield lists replaced
them, and live on in `data/decks/fixtures/` under their old ids, `aesi` and
`edgar`. Hundreds of seeded Python and Playwright tests were written against
those exact 99s, and re-pinning every one of them would have bought nothing.

- `default_registry()` — tests, the arena, the trainer — always loads them.
- The server loads them **only** with `COMMANDERBLITZ_FIXTURE_DECKS=1`, which the
  Playwright web server and `scripts/verify.py` set. A player never sees them.
- `data/decks/fixtures/seating.json` pins the order a lobby hands decks to CPUs
  (`aesi`, `edgar`, `isperia`, `zurgo`), so a seeded pod deals the opponents its
  test expects even though the new precons sort ahead of `edgar`.

A dev server reused by Playwright needs the same variables
([testing.md](testing.md)). What the two lists were:

### Aesi (Reap the Tides)

> You may play an additional land on each of your turns.
> Landfall — Whenever a land you control enters, you may draw a card.

The deck is built to make that trigger fire as often as possible: 21 ramp effects, two
more sources of extra land drops (Exploration, Azusa), and payoffs that scale with
lands entering — Tatyova, Rampaging Baloths, Zendikar's Roil, Tireless Provisioner,
Avenger of Zendikar. Because Aesi is landfall rather than a land-drop trigger, all 21
of those ramp spells draw too, and Ancient Greenwarden doubles it. Counterspells and
instant-speed removal protect the engine; the top end is large creatures.

### Edgar Markov (the hand-built vampires)

> First strike. Eminence — whenever you cast another Vampire spell, create a 1/1 black
> Vampire token. Whenever Edgar Markov attacks, put a +1/+1 counter on each Vampire
> you control.

Eminence works from the command zone, which the engine supports through an ability's
`active_zones`. 37 of the 62 non-land cards are Vampires, so the token trigger fires
constantly. Legion Lieutenant, Stromkirk Captain and Shared Animosity turn the
swarm lethal; Blood Artist, Cruel Celebrant, Kalastria Highborn and Sanguine Bond mean
that even losing creatures drains the table. Bloodline Keeper is the one card in
the four decks with two faces: five Vampires on the board turns it into Lord of
Lineage, a 5/5 that gives the rest of them +2/+2.

## Substitutions

**None, in any of the twelve** (or the two fixtures). Every card in every one of
them does what it prints.

That is a recent thing and it is the best evidence the
[card pipeline](card-authoring.md) has. `substitutions` is still a field on
`DeckModel`, and the dossier still derives `swaps` and `swap_note` from it, so a
future deck can record one — the mechanism did not go away, the swaps did.

Aesi got there first, when the hand-curated Simic list was replaced by Commander
Legends' Reap the Tides.

Edgar Markov was the last, and it took seven cards and six capabilities:

| Card | What it was waiting on |
|---|---|
| Mortify, Bedevil, Anguished Unmaking | **nothing** — `any_types` and `any_of` had shipped for other cards, so the note claiming "selectors cannot express *creature or enchantment*" was stale rather than true |
| Captivating Vampire | `gain_control`, the `add_subtype` **op**, and a `tap_permanents` cost |
| Shared Animosity | `shares_a_type_with` and `exclude_binding` — selectors describing one object relative to another |
| Vampire Nocturnus | `reveal_library_top` and a `top_of_library` static condition |
| Bloodline Keeper | transforming double-faced cards, and "activate only if…" |

The three cards that needed nothing are the useful half of that table. A
substitution is a claim about the engine written down at a moment in time, and
nothing re-checks it — which is exactly what
`python scripts/audit_cards.py --check-substitutions` is for, and why it prints
"0 substitution(s) the engine has outgrown" rather than nothing at all.

## Where the cards live

```
data/cards/basics.cards.json    5 basic lands
data/cards/tokens.cards.json    87 token definitions
data/cards/core.cards.json      colourless staples shared by every deck
data/cards/aesi.cards.json      the Simic half, shared with Isperia
data/cards/edgar.cards.json     Edgar's Mardu vampires
data/cards/isperia.cards.json   the Azorius deck
data/cards/zurgo.cards.json     Zurgo's token half
data/decks/*.deck.json          the twelve 100-card lists
data/decks/fixtures/            the retired Edgar and Aesi lists, for tests
```

The ten Moxfield decks need no card file of their own: every card in them was
authored by the [card pipeline](card-authoring.md) into `data/cards/auto/` while
making the import native, which is the precondition `promote_deck.py` enforces.

A card id is defined **once** and referenced by any number of decks. Zurgo's list
is mostly ids that live in `edgar.cards.json`, and Isperia's borrows the blue
half of `aesi.cards.json` — which is why 81 new definitions were enough for two
whole decks. `CardRegistry.from_paths` raises on a duplicate id, so the only way
to share a card is to share it.

Test-only cards live in `tests/data/testing.cards.json` and are never loaded by a real
game — the test registry adds them, the shipped registry does not.

## How a deck describes itself

The lobby's deck catalogue and dossier are fed from two halves, kept deliberately
separate.

**Authored**, in the deck file, and only for the shipped decks:

```json
"tags": ["Ramp", "Landfall", "Card draw"],
"ratings": {"speed": 2, "complexity": 3, "interaction": 2, "resilience": 3, "pilot": 2},
"strategy": "The first four turns are spent almost entirely on mana: ...",
"signature": [
  { "card_id": "tatyova_benthic_druid", "why": "A second Aesi. Every land is a card and a life." }
]
```

Nothing in a card list tells you a deck is hard to pilot, so these are editorial and
hand-written. Every field is optional: `DeckModel` is `extra="forbid"`, so a *required*
field here would have broken every deck file that predates it, and an imported deck has
none of this and must still load. The catalogue draws that empty state honestly rather
than inventing numbers.

Editorial copy that nothing else reads is exactly the sort of thing that rots, so
`tests/cards/test_deck_metadata.py` is the gate: every `signature` card must resolve in
the registry **and actually be in the deck**, and every rating must be 1–4. A signature
card renamed or cut fails there rather than rendering a blank frame six months later.

**Derived**, at request time, from the list itself:

| Field | From |
|---|---|
| `curve` | Seven buckets — mana values 1..6 and 7+ — of non-land cards, weighted by quantity. Lands are excluded; 37 of them would swamp the first bucket and tell you nothing |
| `lands` | Entries whose type line includes `Land` |
| `swaps`, `swap_note` | `substitutions`, above — already in every deck file and, until the dossier, never sent to the client |

Derived rather than authored so they cannot drift: change the list and the numbers
change with it. `GET /api/decks` returns the light summary the catalogue tiles need;
`GET /api/decks/{id}` adds the dossier's half, so a screen showing 24 tiles does not
pay for 24 strategy essays.

## Checking a deck

```bash
python scripts/validate_decks.py
```

verifies every card file parses, every card id referenced exists, every deck
(fixtures included) has exactly 100 cards, singleton is respected outside basics, every card sits inside its
commander's colour identity, and no tokens have leaked into a deck list.

It checks the **authored** decks only, deliberately: `scripts/verify.py` has to
give the same answer on a fresh clone as on a machine with twenty imported decks.

## Bringing your own

Any public Moxfield deck can be imported and played — see
[deck-import.md](deck-import.md). The decks above are different in kind, not
just in provenance: **every card in them is implemented and tested**, whereas an
imported deck's unsupported cards are generated with their rules text inert.

To make an imported list a shipped precon, the whole list has to be native
first (`/import-moxfield`), then:

```bash
python scripts/promote_deck.py data/generated/decks/mox_<id>.deck.json \
    --id <commander_card_id> --url https://moxfield.com/decks/<id>
```

It refuses a list the authored layer cannot play. The editorial fields and a CPU
strategy ([cpus/README.md](cpus/README.md#adding-a-deck)) come after. The import
report and the deck tile both say how many, because that difference decides
whether a game makes sense.
