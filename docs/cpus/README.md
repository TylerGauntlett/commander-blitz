# The CPU opponents

Every shipped deck has a CPU that plays it **the way the deck is meant to be
played** — a mill deck mills the shortest library, a Voltron deck suits up its
commander and sends it in, a combo deck casts its second piece when it is holding
the first. One page per deck says how it plays, how it wins, what it is good and
bad at, and exactly which code makes the CPU do each of those things.

The bar is a moderately competent player, not a strong one. The CPU still looks
only at the position in front of it ([why](#what-the-cpu-cannot-do)).

| Deck | Archetype | In one line |
|---|---|---|
| [Aesi, Tyrant of Gyre Strait](aesi_tyrant_of_gyre_strait.md) | Landfall | Every land is a card; ramp first, payoffs after |
| [Atraxa, Praetors' Voice](atraxa_praetors_voice.md) | Superfriends | Planeswalkers out, loyalty up, proliferate toward ultimates |
| [Bard, King of Dale](bard_king_of_dale.md) | Go wide | A wide board of tokens and value, swung when the blockers run out |
| [Blor the Impervious](blor_the_impervious.md) | Voltron | One commander, every equipment on it, aimed at one player |
| [Bruvac the Grandiloquent](bruvac_the_grandiloquent.md) | Mill + combo | Doubled mill at the shortest library; the Isochron Scepter loop |
| [Edgar Markov](edgar_markov.md) | Vampire tribal + drain | Vampires everywhere, lords, a drain on every death |
| [Giada, Font of Hope](giada_font_of_hope.md) | Angels | Giada first, then angels that land bigger than printed |
| [Isperia, Supreme Judge](isperia.md) | Control | Fly over; make attacking this seat the worst option |
| [Sheoldred, the Apocalypse](sheoldred_the_apocalypse.md) | Punisher | Every card the table draws costs it life |
| [The Ur-Dragon](the_ur_dragon.md) | Dragons | Ramp hard, land dragons, let them fly |
| [Vivi Ornitier](vivi_ornitier.md) | Spellslinger | Instants and sorceries first; Vivi turns each into damage |
| [Zurgo Stormrender](zurgo.md) | Aristocrats | Attack every turn, let the tokens die, drain the table |

## How a CPU decides

`HeuristicAgent` ([heuristic_agent.py](../../src/commanderblitz/ai/agents/heuristic_agent.py))
scores every legal action from the current position — a land drop 1000, a
counterspell 500 and up, removal 350 and up, a creature about 300 — and takes the
best one, or passes when nothing scores above zero. That has always been true.
What is new is that **every score now passes through a `Strategy`** before the
agent compares them:

```
legal actions ──> agent's score ──> strategy.priority_value(...) ──> best one
```

The strategy is looked up per seat from the deck it is playing
(`commanderblitz.ai.strategy.strategy_for`):

1. **The deck id.** Each favorite has a module in
   [`strategy/decks/`](../../src/commanderblitz/ai/strategy/decks/), found automatically.
2. **The commander.** A player's own import of Bruvac is still piloted as a mill
   deck, because a plan is really about the commander.
3. **The archetype** a deck file names, one of `ARCHETYPES` in
   `strategy/archetypes.py`. This is how a precon without a module is piloted
   ([ADR 0024](../adr/0024-precon-means-the-product.md)).
4. **`DefaultStrategy`**, the baseline, for everything else.

The hooks (`strategy/base.py`) each take the agent's own answer and return the
one to use, so an archetype changes only what it cares about:

| Hook | Asked for |
|---|---|
| `keep_hand` | the mulligan |
| `defender`, `attack_value`, `block_value` | combat, one declaration at a time |
| `priority_value` | every land, cast and activation |
| `choose` | questions asked while something resolves: a player, a mode, X |
| `junk_value` | what to discard or sacrifice first |

The base `Strategy` returns its input unchanged, which makes it the CPU exactly as
it was before any of this: `heuristic_classic`, kept for benchmarks and for the
seeded browser tests ([testing.md](../testing.md#determinism)).

### The baseline every deck gets

`DefaultStrategy` ([default.py](../../src/commanderblitz/ai/strategy/default.py)) is
the list of mistakes no competent player makes, each one something a playtester
watched the old CPU do:

- **Attacking into an obvious block.** The old agent asked the rules engine
  "could this creature block that attacker?" before the attacker was declared,
  and the engine — correctly — said no to every blocker, so the CPU saw an
  empty board in front of every attack. `board.could_block` asks the same
  questions without the declaration. A creature no longer attacks into a blocker
  that kills it and survives, and a 6/6 no longer trades itself for a 1/1
  deathtoucher.
- **Dying to the crack-back.** An attack that would leave too little home to
  survive the biggest swing back is vetoed.
- **Missing lethal.** When the attackers get through every blocker for the
  defender's life total, everything swings at that player.
- **Harming itself.** "Target player mills / discards / loses life" used to go
  at whichever player came first in the list, often the CPU's own seat. Harm now
  goes at the opponent it hurts most (shortest library, lowest life, biggest
  hand), and help comes home.
- **The first mode, the first player, every time.** Modes are scored by what
  they do against the board in front of them; "choose a player" by the effect's
  intent — including a storm copy's "choose new targets", which arrives as modes
  labelled by seat and used to send Brain Freeze copies back at the caster.
- **Mana rocks after creatures.** The agent calls only a land search "ramp", so
  a Signet or a mana dork came down after every creature. Through turn 8 they
  are cast like ramp.
- **The wrong land.** The land that makes a colour the hand is missing comes
  first; a shock land pays 2 life only when that untapped mana casts something.
- **Bad keeps.** A hand needs its lands *and* an early play.
- **Chump-blocking too late.** It chumps when the unblocked damage is lethal, not
  only below 10 life, and never chumps with its commander otherwise.

### Archetypes

[`archetypes.py`](../../src/commanderblitz/ai/strategy/archetypes.py) builds on the
baseline:

| Archetype | What it changes |
|---|---|
| `Aggro` | Creatures first, early |
| `GoWide` | Token makers first; with a wide enough board, swings past the blockers |
| `Aristocrats` | Tokens are sacrificed first |
| `Voltron` | Equipment and Auras onto the commander; the commander attacks, the rest guard it |
| `Tribal` / `Dragons` | The tribe first; Dragons also ramp hard early |
| `Landfall` | Extra land drops, fetches and ramp first; landfall creatures stay home |
| `Superfriends` | Walkers before creatures; plus abilities by default, minus when it hits something |
| `Mill` | Mill goes at the shortest library, decisively |
| `Spellslinger` | Instants and sorceries outrank creatures, precombat |
| `Control` | Counters cheaper spells; only evasive creatures attack into blockers |
| `Punisher` | The baseline, for a deck module to specialise |

A deck module picks one and fills a `DeckPlan`: key cards and their bonuses,
combos (a big bonus for the last piece, a modest one for a piece whose partner is
already out), win conditions and cards never to discard or sacrifice, the land
range a keepable hand needs, and how aggressive to be. A deck that needs a rule
no archetype has subclasses the archetype in its own module.

## Adding a deck

1. Make the list native and promote it ([decks.md](../decks.md#bringing-your-own)).
2. Add `src/commanderblitz/ai/strategy/decks/<deck_id>.py` exporting `STRATEGY`.
3. Write this page for it: overview, win conditions, key cards and combos, how
   the CPU pilots it (each behaviour named with its hook), strengths, weaknesses,
   mulligan.
4. Add `tests/ai/strategy/decks/test_<deck_id>.py` — a position or two that shows
   the plan doing what makes the deck different.

`tests/ai/strategy/test_registry.py` fails until every favorite has a strategy
and every shipped deck has a module or an archetype, and fails if a plan names a
card that is not in its deck — a typo would otherwise silently switch a bonus
off.

## Measuring it

```bash
python scripts/run_arena.py --agents heuristic,heuristic_classic --decks precons --pods 2,4 --games 60
```

seats the strategy CPU against the classic one across every precon, seats
rotated. `tests/ai/strategy/test_deck_games.py` plays a seeded sample of the
shipped decks through whole four-player games, the day's date unless
`DECK_GAMES_SEED` names one, and checks a seed replays exactly; the full matrix
is the arena's.

## What the CPU cannot do

- **Look ahead.** Game state cannot be cloned ([ADR 0005](../adr/0005-no-state-cloning.md)),
  so the CPU never asks "what happens if". Combos are assembled by noticing the
  pieces, not by planning the line; a counterspell is held only as a rough rule.
- **Read the table.** It does not track who is ahead beyond board power and life,
  remember what an opponent has shown, or make deals. In a pod it attacks
  whoever is softest, not whoever is winning.
- **Bluff, or play around a trick.** It assumes the blockers it can see and the
  damage on the board, nothing in hands.
- **Hold mana open.** Instants other than counterspells and removal are cast in
  its own main phase, and nothing keeps counterspell mana up on purpose.

Gaps worked around in individual deck plans and worth lifting into the baseline
are listed under "Strategy gaps" in [TECH_DEBT.md](../../TECH_DEBT.md).
