# Card worker brief

You are implementing **one** Magic: The Gathering card for a rules engine, from a
self-contained work packet. You need no other repository context — everything about
the DSL is in the packet.

Read your packet, then write **exactly one file** and nothing else.

## Step 1 — triage. Do this before writing any card.

Read `oracle_text` and the `todo` list in your packet. For each outstanding
sentence, decide whether it can be said **exactly** with the vocabulary in the
packet's `reference` block — its `ops`, `keywords`, `types`, `trigger_events`,
`static_effects`, `static_filter_keys`.

If every sentence can: go to step 2.

If any sentence cannot: go to step 3. **Do not approximate.** Do not drop a clause,
do not substitute a nearby op, do not invent an op that is not in `reference`.

This is the single most important instruction here. A card that quietly does
something subtly different is worse than one that does nothing, because the inert
one at least fails visibly the first time somebody counts on it. A verification
gate would reject your approximation anyway — but a gap record naming what is
missing is worth far more than a rejection, because it becomes the build order for
the engine.

Borderline cases go to step 3, not step 2. A wrong "can do" costs a rejected card;
a wrong "cannot" costs one entry on a roadmap somebody reads.

## Step 2 — the card is expressible: write an answer

Write `data/authoring/answers/<card_id>.json`, using the `card_id` from your packet
as both filename and the card's `id`:

```json
{
  "card": { "id": "...", "name": "...", "oracle_text": "...", "...": "..." },
  "expectation": { "...": "..." }
}
```

Both halves are required. A card nobody asserted anything about is rejected.

Start from the packet's `starting_point` — keywords, mana ability, enters-tapped,
whatever the free tiers already worked out — and **add** to it. Copy `oracle_text`
verbatim from the packet. Follow the packet's `examples` for shape.

Rules the loader enforces, so getting them wrong is a rejection:

- An instant or sorcery puts its effects in `spell_effects`. A permanent puts them
  in `abilities`.
- **Every ability's `text` must be the printed sentence it implements.** A gate asks
  each ability which line it claims and rejects the card if any printed line is left
  unclaimed. This is also how a half-implemented card gets caught.
- A static ability's filter may only read printed characteristics.
- A mana ability may contain only `add_mana`, or one `choose_mode` whose modes each
  contain only `add_mana`.
- `snapshot` is how a card reads a value after its target has left; there is no
  general last-known-information system.

## The expectation, and the sandbox it is measured in

The expectation is where hand-authoring has historically gone wrong — not the card.
It is checked by casting your card in one fixed position and reading the board.

**The position, exactly. It is identical every run.**

| | |
|---|---|
| You are player 0, at **40 life**; the opponent is player 1, at **40 life** |
| Your battlefield | **32 permanents** — 30 lands (6 each of Plains, Island, Swamp, Mountain, Forest) + 2 creatures |
| Opponent's battlefield | **6 permanents** — a **legendary** creature, a flier, an artifact, an enchantment, a Forest and an Island |
| Your hand | **just the card under test** — so `hand_size` is 0 after you cast it |
| Your library | **40 cards**, all basic lands |
| Opponent's library | 20 cards |
| Your graveyard | **2 creature cards** |
| Phase | your precombat main phase, turn 1, with mana enough to cast anything |

The board props are chosen *by role* from the card pool, so do not assume specific
card names, printed power/toughness, or that the two creatures differ.

The opponent's creature is the position's **one and only legendary permanent**, and
it is theirs rather than yours on purpose: a card whose own enters trigger says
"destroy target legendary permanent" is a legal target for itself, so without a
legendary somewhere else on the board the harness could only point the trigger at
the card under test, which would then lawfully destroy itself and fail gate 4.
Nothing else on either board is legendary, so a card that *counts* legends counts
one.

**The traps, each of which has actually happened:**

1. **Activated abilities are never activated.** The harness casts your card and
   stops. Equip, cycling, sacrifice outlets, `{T}:` abilities — none of them fire.
   Asserting the *effect* of an activated ability is the single most common error.
   For a card whose interesting text is an activated ability, assert
   `{"zone": "battlefield"}`.
2. **"Permanents you control" is 32, not 2.** Count the lands.
3. **`battlefield_count` includes the card itself** — cast a creature and it is 33.
4. **Measurement happens before cleanup**, so "until end of turn" effects are still
   live and `target_pt_delta` and `granted` work. Combat is declined.
5. **A trigger that never fires cannot be asserted.** Nothing in this position makes
   a land enter, a creature die, or a spell get cast after yours. If your card's
   only effect is such a trigger, assert `{"zone": "battlefield"}` — legitimate, but
   it is the weak fallback, not the goal. Prefer a real observation whenever one
   exists.
6. **`tokens` requires the token to already exist** in the engine's token pool. If
   your card makes a token nobody has defined, that is step 3.

**What an expectation may assert** — only these keys:

| key | shape | notes |
|---|---|---|
| `life` | `{"0": 42}` | per player id |
| `hand_size` | `{"0": 2}` | |
| `library_size` | `{"0": 38}` | starts at 40 |
| `graveyard_size` | `{"0": 3}` | starts at 2 |
| `counters` | `{"kind": "+1/+1", "amount": 2}` | on **your card**, not any object |
| `tokens` | `{"id": "plant_0_1_g", "count": 3}` | yours only |
| `battlefield_count` | `33` | yours; starts at 32 |
| `opponent_battlefield_count` | `5` | starts at 6 |
| `zone` | `"graveyard"` or `["battlefield", "graveyard"]` | a list means "any of" |
| `granted` | `{"keywords": ["hexproof"], "count": 32}` | your permanents having **all** those keywords |
| `target_pt_delta` | `{"power": 3, "toughness": 3}` | on the spell's own target; only if it targeted |

`zone` by card type: instant or sorcery → `"graveyard"`; any permanent →
`"battlefield"`; an Aura whose effect may kill what it enchants →
`["battlefield", "graveyard"]`.

Assert what the card *does*, not merely that it resolved. Two or three keys are
better than one when the card supports them.

### Two worked answers

Heroic Intervention — "Permanents you control gain hexproof and indestructible
until end of turn." The count is 32 because that is how many permanents you have:

```json
{
  "card": {
    "id": "heroic_intervention", "name": "Heroic Intervention",
    "oracle_text": "Permanents you control gain hexproof and indestructible until end of turn.",
    "mana_cost": "{1}{G}", "types": ["Instant"],
    "colors": ["G"], "color_identity": ["G"],
    "spell_effects": [{
      "op": "grant_keyword", "keywords": ["hexproof", "indestructible"],
      "objects": {"zone": "battlefield", "controller": "you", "count": "all"}
    }]
  },
  "expectation": {"granted": {"keywords": ["hexproof", "indestructible"], "count": 32}}
}
```

Fact or Fiction — five cards leave a 40-card library, so `library_size` is 35, and
the instant itself ends in the graveyard:

```json
{
  "card": {
    "id": "fact_or_fiction", "name": "Fact or Fiction",
    "oracle_text": "Reveal the top five cards of your library. An opponent separates those cards into two piles. Put one pile into your hand and the other into your graveyard.",
    "mana_cost": "{3}{U}", "types": ["Instant"],
    "colors": ["U"], "color_identity": ["U"],
    "spell_effects": [{"op": "two_piles", "amount": {"const": 5}, "to": "hand", "other": "graveyard"}]
  },
  "expectation": {"zone": "graveyard", "library_size": {"0": 35}}
}
```

## Step 3 — the card is not expressible: write a gap record

Write `data/authoring/gaps/<card_id>.json` and **no answer file**:

```json
{
  "card_id": "krosan_tusker",
  "name": "Krosan Tusker",
  "oracle_text": "<verbatim from the packet>",
  "blocked_sentences": ["Cycling {2}{G} ({2}{G}, Discard this card: Draw a card.)"],
  "needs": [{
    "capability": "cycling",
    "kind": "cost",
    "what": "an activated ability playable from hand whose cost discards the card itself",
    "why_existing_wont_do": "Cost carries tap, pay_life and sacrifice but nothing that discards the source from hand, and abilities only activate from the battlefield"
  }],
  "closest_existing": ["retrace"],
  "confidence": "high"
}
```

- `capability` — a short lowercase slug, the name of the mechanic. This is the
  grouping key across thousands of cards, so use the Magic keyword where one exists
  (`cycling`, `crew`, `flashback`, `convoke`, `ward`), not a description.
- `kind` — one of `op`, `cost`, `trigger_event`, `keyword`, `static_effect`,
  `selector`, `value`, `replacement`, `decision`, `engine`.
- `what` — **be specific.** "Needs a new op" is worthless. "Needs an activated
  ability playable from hand whose cost discards the source" is a work item
  somebody can build from.
- `why_existing_wont_do` — name the closest thing in `reference` and say why it
  falls short. This is what stops the same dead end being explored twice.
- `confidence` — `"high"` if you are sure, `"low"` if you suspect you may have
  missed a way to express it.

If a card is *partly* expressible, it still goes here: record only the sentences
that are blocked, and do not write a partial answer.

## Do not

- Write to `data/cards/`, `src/`, `tests/`, or any file other than your one output.
- Write both an answer and a gap record.
- Use an op, keyword, type or trigger event that is not in your packet's
  `reference` block.
- Guess at an expectation you cannot justify from the position above.
