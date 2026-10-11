# Importing a deck

Paste a public Moxfield link on the setup screen and you get a playable deck.
The engine plays the cards in `data/cards/` — hand-written, or authored by the
[card pipeline](card-authoring.md); a real Commander deck contains a
hundred, many of which say something nobody has written rules for. So the deal
this feature makes is:

> **Every card is on the board with its real name, art, cost, types and stats.
> Cards nobody implemented keep their printed text but do nothing beyond their
> keywords — and the screen tells you exactly which ones, and what changed.**

That last clause is the whole feature. A silently-inert removal spell costs
somebody a game and an hour working out why.

## The round trip

```
paste  ->  moxfield.py   fetch the list        (names, quantities, printings)
       ->  importer.py   reconcile each name against our catalog
       ->  proxy.py      generate what nobody wrote
       ->  data/generated/                     (gitignored)
       ->  app.state.reload()                  visible without a restart
```

`GET https://api2.moxfield.com/v3/decks/all/{publicId}` is open to a plain
`urllib` client. [ADR 0012](adr/0012-art-fetched-once-served-locally.md) records a Cloudflare 403 against
`api2.moxfield.com` — that was `/v2/cards/search/user`, a different endpoint, and
it is still true of that one.

**What a card *is* comes from us, not from Moxfield**: a card's name, its
quantity and which board it was in are all that identify it, and every
characteristic is read from our own `data/catalog/cards.sqlite`, so an imported
card's id and colour identity agree with what `/api/catalog` already says.
Supporting Archidekt later is an adapter, not a second card pipeline.

**Art is the exception.** Which of a card's printings the author chose is not a
characteristic we can derive — the catalog keeps one printing per card *name*,
so asking it gives everybody the same Sol Ring and the same Forest, and a deck
stops being recognisable as yours. It is a choice, and only the source list
knows it, so the printing's `scryfall_id` is carried through (with `artist`,
`set` and `cn` alongside, for whoever reads the deck file later).

Those land in the deck file as `printings: {card_id: {...}}` and are applied
**per seat**: two players can run the same card and want different
illustrations, so a seat's choice never leaks into the global art map or onto
anybody else's board. See `docs/card-catalog.md` for how the three layers
stack. A deck imported before this existed simply has no `printings` and keeps
the catalog's pick — re-import it to pick up its own art.

## Three outcomes per card

| | What it means |
|---|---|
| **native** | A card the engine already plays — hand-written in `data/cards/` or authored into `data/cards/auto/`. Reused whole: real rules, existing art, and the id every precon already uses. An imported deck's Forests are `forest`. |
| **full** | Generated, and nothing was lost. Vanilla and french-vanilla creatures, basic lands, taplands, duals, Signets. |
| **partial** | Generated, non-keyword rules text inert. Every simplification is listed. |

A name the catalog has never heard of is a **failure**, not a fourth outcome. A
99-card deck is not a deck, and dropping the card silently is how somebody spends
a game wondering where their commander went.

## What the generator does and does not do

`src/commanderblitz/cards/proxy.py`, and it emits a `CardModel` that goes through the
ordinary `compile_card` — so a generator bug is a `DslError` at import time
rather than a mystery mid-game.

**Kept:** name, mana cost, supertypes/types/subtypes, power/toughness, colours,
colour identity, printed oracle text (displayed), the keywords the engine
implements, `{T}: Add` mana abilities, and enters-tapped.

**Not modelled**, each recorded as a note on the card:

- Any rules text that is not a bare keyword line or a mana ability.
- **Back faces.** A transform or modal DFC generates as its front face only.
  Called out loudly for MDFC lands, because the deck loses a land it thought it
  had.
- **The second half of a split or adventure card.**
- **Snow mana**, rewritten to something `ManaCost.parse` accepts — `{S}` to
  `{1}`. Mana value is always preserved. This is not politeness: `parse` *raises*
  on a symbol it does not know and the exception travels out through
  `CardRegistry.from_paths`, so one such card would stop the whole registry
  loading at boot. Hybrid (`{W/U}`, `{2/W}`) and **phyrexian** (`{W/P}`) are no
  longer rewritten at all: both are parsed and paid properly now, and narrowing
  `{U/P}` to `{U}` was worse than a simplification — it deleted the "or 2 life"
  clause that is the whole reason a Gitaxian Probe or a Gut Shot is played.
- **Loyalty and defence.** A planeswalker enters play as an inert permanent. A
  battle is refused outright: 310.3's printed defense is not a column in the
  catalog, and a battle entering with no defense counters would be defeated by
  704.5x as it resolves — so a generated one would vanish rather than be weak.
  It goes in the import report to be hand-written.
- **Mana quantity.** Scryfall's `produced_mana` carries no amount, so a generated
  Sol Ring taps for one.
- **A mana ability whose cost is more than `{T}` and mana** is not generated at
  all — a bounce land's "return an Island you control", a fetchland's "pay 1
  life, sacrifice". The mana half of a cost *is* kept: a Signet is `{1}, {T}`,
  not a free tap. The rule is that **a generated card is never better than the
  printed one**, which is the same rule the conditional taplands follow, and
  getting it wrong silently hands the deck cheaper rocks and drawback-free duals.
  This is a limit of the *generator*, not of the DSL: `Cost` has always carried
  `tap`, `pay_life` and `sacrifice`, which is why the fix for fetchlands was to
  author them rather than to loosen this rule.
- **An ability a card grants to something else is not taken for itself.**
  Abundant Growth reads `Enchanted land has "{T}: Add one mana of any color."`
  and carries `produced_mana` for all five colours; lifting that would give the
  *Aura* a five-colour mana ability. Same trap as `keywords`.
- **A mana ability's rider** — the sentence after the mana, as on a painland —
  is read only for "deals N damage to you", the shape the painlands print. A
  rider it cannot read ("Put a depletion counter on this land",
  "Spend this mana only to cast a creature spell") means the *whole line* is not
  generated, rather than generated without its drawback. One line short is a
  worse card, which is the safe direction; a painless painland is a better one,
  which is not.
- **Conditional taplands** are read for the three printed shapes that carry the
  cycle — a basic land subtype test, a count of other lands, a count of basic
  lands — so checklands, slowlands, fastlands and battle lands arrive as the
  cards in the deck list. Any other shape enters tapped unconditionally.
  Generating the *upgrade* would quietly hand every imported deck a better mana
  base than it was built with.
- **Variable power/toughness.** `*` reads as 0.
- **Lands that produce nothing** are inert. This is the biggest playability risk
  in an import, so the report has a line for it: *"37 lands, but 3 of them do
  nothing here."* Note what it counts: **lands with no abilities at all**, not
  lands with no mana ability. A fetchland makes no mana and is a perfectly good
  land, so the mana gap would flag a working card forever.

  Fetchlands and creature-lands used to be the whole of this number. They are now
  [authored](card-authoring.md) — the templates tier translates both sentence
  shapes — so an imported deck gets the real cards and the generator is never
  asked. What is left is the genuinely unexpressible: a bounce land's "return an
  Island you control to its owner's hand".

`tests/cards/test_proxy_against_the_catalog.py` is the gate: every row in the
catalog generates without a compile failure. The import report counts the lands
that generate inert.

## Where it goes, and why it is not committed

```
data/generated/          gitignored in full
├── cards/pool.cards.json      one shared pool, not one file per deck
├── cards/pool.images.json     {card_id: {scryfall_id, artist} | null}
├── cards/pool.coverage.json   {card_id: {coverage, notes[]}}
└── decks/mox_<publicId>.deck.json
```

**Two registries, and the split is load-bearing.** `default_registry()` is the
authored layer — `data/cards/` and `data/decks/`, exactly what the repository
ships. `server_registry()` is that plus `data/generated/`. Tests, the trainer and
the arena all use the first.

Three gates assume the authored pool is exactly what the repo ships:
`test_every_card_works` parametrises over all of it, `test_image_resolution`
pins the artless set (`KNOWN_ARTLESS`), and `ai/encoding` builds an embedding
index from `registry.ids()`. If an import could reach those, `pytest` would give
a different answer depending on what somebody imported last week. Gitignoring
`data/generated/` is what makes the split actually hold.

One shared card pool rather than one file per deck, because two decks that both
contain Lightning Bolt would each generate `lightning_bolt` and
`CardRegistry.from_paths` raises `duplicate card id`.

**Ids are derived, never counted.** `slug_for` folds the name to the charset
`server/art.py`'s path guard allows, and a collision appends six hex of the
Scryfall id. A counter would make an id depend on the order things happened to be
imported in — and these ids are art filenames and deck-list keys that must
survive a re-import unchanged. Re-importing the same deck rewrites the same
bytes.

## Shrinking the "simplified" number

A proxy exists because nobody had implemented that card yet, so the way to have
fewer of them is to implement more cards. That is
[card-authoring.md](card-authoring.md) — a batch pipeline that writes card
definitions and refuses to ship any that cannot demonstrate what they do.

Once a card is authored, **the stale proxy is dropped**: the deck goes on
referencing the same id and silently picks up the real rules on the next boot.
Nothing about the deck file changes.

There is no promoting a generated card by hand: it becomes native only by being
authored through the six gates ([card-authoring.md](card-authoring.md)).

## The API

| | |
|---|---|
| `POST /api/decks/import` | `{url, dry_run}` → 201 with the coverage report. `dry_run` reports without writing. |
| `DELETE /api/decks/{id}` | Imported decks only; 400 on a precon. |
| `GET /api/decks` | Carries `source`, `playable`, `simplified`. |

Errors carry a **code** as well as a sentence, because "that deck is private"
and "there is no such deck" send somebody to two different places:

| code | status |
|---|---|
| `bad_url` | 400 |
| `private` | 403 |
| `not_found` | 404 |
| `not_commander`, `bad_size`, `unknown_cards`, `illegal` | 422 |
| `unreachable` | 502 |
| `no_catalog` | 503 |

Once imported, the deck is a `deck_id` like any other: `POST /api/games` takes it
through the same path as `aesi`, with no new code at all. That is the payoff for
persisting rather than holding an ephemeral deck in session state.

## Testing it without a network

`moxfield.fetch_deck` takes its opener as an argument.
`tests/server/test_import.py` passes a fake one backed by
`tests/data/moxfield_deck.json` — a real, trimmed v3 payload, for the same reason
`mini_cards.jsonl` is real: the shapes that break this code are the ones nobody
would think to invent, like the em-dash in `type_line`.
