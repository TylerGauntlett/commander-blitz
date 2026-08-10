# Rules coverage

This is the honest artifact. It says what the engine does, where it takes a shortcut,
and what it refuses to model at all. If you want to know whether this engine can
handle your card, read this page.

The short version: **everything the two shipped decks need is implemented and tested.**
The simplifications below were chosen so that removing them later is additive work,
not a rewrite.

## Implemented

| Area | Detail |
|---|---|
| **Turn structure** | All 13 steps, turn-based actions, correct priority windows, cleanup repeating per rule 514.3a |
| **Priority** | APNAP order, retaining priority after acting, auto-pass when passing is the only option |
| **The stack** | LIFO resolution, responses, countering, fizzling when every target became illegal |
| **Casting** | Timing restrictions (sorcery speed vs instant vs flash), targets chosen at cast time and re-checked on resolution |
| **Mana** | Cost parsing, mana pools emptying per step, automatic payment with a backtracking solver, `X` costs |
| **Combat** | Attacker/blocker declaration, evasion, damage assignment order, simultaneous damage, first and double strike as separate sub-steps |
| **Keywords** | flying, reach, trample, deathtouch, lifelink, vigilance, haste, menace, first strike, double strike, defender, hexproof, indestructible, flash. `partner` is accepted but inert — see below |
| **Triggers** | ETB, dies, leaves-the-battlefield, landfall, land-played, spell-cast, attacks, blocks, combat damage to a player, upkeep, draw step, begin combat, end step, life gain, counters placed. Intervening-if clauses re-checked on resolution. Delayed triggers ("at the beginning of the next end step, …") via the `delay` op |
| **Command zone** | Abilities that work from the command zone (Edgar Markov's eminence), commander tax, commander damage, the zone-change replacement |
| **Static abilities** | Anthems, keyword grants, P/T setting (including `*/*` read off the board), subtype grants, type replacement, "as long as" conditions on counters, and the player-wide ones: extra land drops, no hand limit, playing lands from the graveyard or the top of the library, doubling land triggers, doubling land *mana*, and freezing the lands an opponent taps |
| **State-based actions** | All nine listed in [engine-rules.md](engine-rules.md) |
| **Multiplayer** | N players, turn order that skips eliminated players, elimination mid-combat and mid-resolution, per-source commander damage |
| **Mulligans** | London mulligan with the bottoming step |
| **Costs** | Mana, tap, untap, sacrifice, discard, pay life, remove counters, exile from graveyard |
| **Kicker** | The additional cost, offered as a second way to cast the same card, and the `kicked` condition its text reads |
| **Cost reduction** | "This spell costs {X} less to cast", read off the board by both legality and payment |
| **Ability locks** | "Its activated abilities can't be activated this turn", covering mana abilities |
| **Monstrosity** | The counters, the one-way flag, and the "becomes monstrous" trigger |
| **Conditional statics** | "As long as this has a slumber counter on it, it's a land" — including type *replacement*, not just grants |
| **Trigger doubling** | Ancient Greenwarden's "that ability triggers an additional time", for lands entering |
| **Hybrid mana** | `{W/U}` and `{2/W}` parsed, paid and counted towards colour identity |
| **Restricted mana** | "Spend this mana only to cast a creature spell", by filtering sources before the solver |
| **Token copies** | "A token that's a copy of target creature", copying the printed card and nothing accumulated on it |
| **Protection** | From a type, subtype or colour, across all four of damage, enchant/equip, block and target |
| **Granted abilities** | "…and 'Whenever this creature deals combat damage to a player, draw a card'", until end of turn. Triggered abilities only |
| **Retrace** | Casting from the graveyard by discarding a land |
| **Suspend** | The special action, the upkeep tick, the free cast, and haste on what arrives |
| **Splitting into piles** | Fact or Fiction: an opponent splits, the caster chooses |

## Simplified

Each of these is a deliberate trade. The rationale matters more than the rule.

| Simplification | What it means | Why |
|---|---|---|
| **No layers system** | Continuous effects apply in a fixed order; static filters read printed characteristics only, enforced at load time | The full layer system with timestamps and dependency analysis is a large subsystem that would change no outcome for any card in these decks |
| **Automatic mana payment** | You cannot choose which land to tap. The solver picks, preferring to spend abundant colours so scarce ones stay open. A land doubled by Vorinclex doubles what it produced rather than offering a free choice of type, because a mana ability may never stop to ask | Removes an enormous branching factor for the RL agent and the worst tedium from the UI. `Action` reserves a `payment` field for a manual mode later |
| **Automatic damage assignment order** | Blockers are ordered by effective toughness ascending; the attacker is never asked | One more decision point per combat for a choice that is nearly always forced |
| **Automatic trigger ordering** | Simultaneous triggers you control resolve in a fixed order rather than one you choose | Matters only for a handful of interactions, none of them in these decks |
| **Modes chosen on resolution** | A modal spell picks its mode as it resolves, not as it is cast | Keeps the action space flat. Only observable when an opponent would respond differently per mode |
| **Object identity survives zone changes** | The `oid` is preserved where the rules would create a new object; permanent state is reset instead | Simpler and equivalent for everything except effects that track "the new object" |
| **Last-known information is explicit** | A card that needs a value after its target has left declares a `snapshot` op (see Swords to Plowshares) | A global LKI system for two cards is not worth it; the explicit form is also easier to read |
| **Commander replacement is automatic** | A commander always returns to the command zone rather than being asked | It is what players choose in practice, and it keeps zone changes out of the decision system |
| **Legend rule keeps the newest** | Duplicated legends are resolved without asking the controller | The choice is nearly always irrelevant |
| **Target options capped at 12** | A spell offers at most 12 target combinations | Only bites on very wide boards; without it a single "target creature" can flood the action space |
| **Turn cap** | 30 turns per player (60 in a duel, 120 in a pod), then a draw | Self-play must terminate. Draws are counted and reported |
| **Trigger loop guard** | More than 200 triggers in one step raises `RulesLoopError`, scored as a draw | One pathological board must not abort a 10,000-game run |
| **Delayed triggers resolve off the stack** | "At the beginning of the next upkeep, draw a card" runs as the step begins rather than being put on the stack | Same trade as modes and trigger ordering: only observable when somebody would respond differently to the delayed half than to the spell that scheduled it |

### Simplifications *inside* a hand-written card

Everything above is a deliberate, engine-wide trade. There is a second kind that
was never decided and never written down: individual precon cards that implement
less than they print.

`data/decks/*.deck.json` records `substitutions` — Scute Swarm swapped for
Tireless Provisioner because copy effects did not exist. That mechanism only ever
covered swapping one card for another. It has nothing to say about Tireless
Provisioner itself dropping the Food-or-Treasure choice, Krosan Tusker shipping
as a vanilla 6/5 with no cycling, or Anticipate being implemented as Preordain.

Those cards predate the authoring pipeline and never cleared its gates. The
current count is in `tests/cards/precon_deficits.json`, which is generated, and
the whole picture is `python scripts/audit_cards.py`. They are not new bugs —
they are the cost of building the precons before the gates existed, measured for
the first time. Repair one with `/author-cards <name>`; the mechanics they are
waiting on (cycling, flashback, evolve, threshold, ascend, investigate, shroud,
skulk, intimidate — none of the 15 keywords in `engine/enums.py` covers them) are
`/extend-dsl` jobs.

## Imported cards, which are simplified further

Everything above describes a **hand-written** card. A deck imported from Moxfield
is mostly cards nobody wrote rules for, generated by `src/automtg/cards/proxy.py`,
and those carry a second, much larger set of simplifications. Each is recorded on
the card and shown at import; the full list is in
[deck-import.md](deck-import.md). The ones that change how a game plays:

| Simplification | What it means |
|---|---|
| **Non-keyword rules text is inert** | The card is a real permanent with the right name, cost, types and stats. Its printed abilities do nothing |
| **Front faces only** | A transform or modal DFC generates as its front face. An MDFC land loses the land half |
| **Phyrexian and snow costs are rewritten** | `{W/P}` becomes `{W}`, `{S}` becomes `{1}`. Mana value is always preserved. Ordinary hybrid (`{W/U}`, `{2/W}`) is now kept exactly as printed |
| **No loyalty, no defence** | Planeswalkers and Battles enter play and then sit there |
| **One mana per activation** | Scryfall records *which* mana a permanent makes, not how much. A generated Sol Ring taps for one |
| **Taplands are unconditional** | "Enters tapped unless…" enters tapped. Generating the upgrade would hand every imported deck a better mana base than it was built with |
| **`*` power reads as 0** | The characteristic-defining ability behind it is not modelled |
| **Some lands do nothing** | A land whose whole ability the generator cannot express — a bounce land's "return an Island you control" — arrives as an inert permanent. The import report counts those separately from the ones that simply make no mana, because a fetchland makes no mana *by design*. Fetchlands and creature-lands themselves are now [authored](card-authoring.md) rather than generated |

## Not implemented

These are absent, and the curated decks avoid them. Adding any one is additive.

**Card types and mechanics**
Planeswalkers · battles · sagas · modal double-faced cards · split and adventure cards ·
transforming cards · companions · vehicles.  **Partner** is accepted as an inert
keyword: it is a deck-construction rule, and the engine is handed a finished deck

**Costs and casting**
Alternative costs in general · phyrexian and snow mana · convoke and similar ·
flashback and other graveyard casting (retrace is implemented) · overload

**Effects**
Copying a permanent as anything but a token · gaining control of a permanent ·
damage prevention or redirection other than protection · regeneration · shroud and
ward · "unless that player pays" · granting a *static* or *activated* ability to
another permanent (triggered ones work) · general replacement effects (only four are
whitelisted: enters tapped, enters with counters, the commander zone change, and
tokens ceasing to exist)

**Combat**
Attacking planeswalkers or battles · banding · "must be blocked" · manual damage
division · attacking with creatures you do not control

**Structural**
Multiplayer politics (voting, goad) · sideboards and companions · the monarch,
initiative, day/night, and other designated-player mechanics

## How this is enforced

None of the above is a promise in prose — it is checked:

- The card loader validates every op name, selector key, value form, keyword, type and
  trigger event against the registries. An unknown one raises `DslError` at load time,
  which fails `pytest`, not a game.
- The "statics may not read statics" constraint is a load-time check on every static
  ability's filter.
- `tests/cards/test_every_card_works.py` plays every shipped card in a rigged sandbox
  and asserts it resolves into the right zone, with per-card outcome expectations from
  `tests/cards/expectations.json`.
- `tests/cards/test_hand_written_cards.py` runs all six authoring gates over every
  hand-written card, and separately checks that each card's `oracle_text` is what the
  catalog says it prints — the check that stops a card from being verified against a
  summary of itself. Cards that do not pass yet are listed, with reasons, in the
  generated `tests/cards/precon_deficits.json`; that list can only shrink.
- `tests/cards/test_auto_cards.py` does the same for every machine-authored card.
- Deck legality, colour identity and singleton rules are tested per deck.

If a card in this repo does not work, one of those tests fails.
