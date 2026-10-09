# Atraxa, Praetors' Voice — "Superfriends"

## Overview & play style

Four-colour superfriends: **thirty-odd planeswalkers** and a commander who
proliferates at every end step. Each walker that survives a turn cycle gains a
loyalty from its own plus and another from Atraxa, so the deck lands walkers as
early as it can, plusses them every turn, and lets proliferate carry them to
their ultimates. Doubling Season, Inexorable Tide, Flux Channeler, Tekuthal and
Deepglow Skate multiply that growth; Oath of Gideon and Oath of Ajani make every
walker arrive bigger or cheaper.

Atraxa herself is a 4/4 flying, vigilant, deathtouch, lifelink body — a fine
blocker for walkers and a fine attacker. The rest is answers: Swords, Mortify,
Putrefy, Anguished Unmaking, Cyclonic Rift, Day of Judgment and Teferi's
Protection. It plays **slow and controlling**, winning through whichever
ultimate the table fails to stop.

## Win conditions

- **Ultimates.** Vraska the Unseen's assassins, Elspeth's anthem emblem,
  Ajani, Sleeper Agent's poison emblem, Vraska, Relic Seeker setting a life
  total to one, Sorin's vampire army, Kiora's krakens.
- **Jace, Memory Adept's −7** at opponents with twenty or fewer cards left: they
  draw out and lose.
- **Gideon of the Trials' emblem** — while we control a Gideon, we cannot lose.
- **The Chain Veil + Teferi, Temporal Archmage**: Teferi's −1 untaps the Veil and
  three lands, and the Veil lets every walker activate again.
- **Plain value.** Token-making walkers (Elspeth, Liliana, Vraska) and removal
  minuses win a long game without an ultimate.

## Key cards & combos

| Card | Why it matters |
|---|---|
| Atraxa, Praetors' Voice | A free proliferate every turn, on an evasive lifelinking body. |
| Doubling Season | Every walker enters with double loyalty — several can ultimate on arrival. |
| Inexorable Tide, Flux Channeler | A proliferate on every spell. |
| Tekuthal, Inquiry Dominus | Every proliferate happens twice. |
| Oath of Gideon, Oath of Ajani | One extra loyalty on each walker; walkers cost one less. |
| Call the Gatewatch, Deploy the Gatewatch | Walker tutors — Deploy puts two straight onto the battlefield. |
| Teferi's Protection | The answer to a board wipe or an alpha strike at our walkers. |

The plan names one **combo**: **The Chain Veil + Teferi, Temporal Archmage**.
Holding one, the other gets the combo bonus; both are protected from discard.

## How the CPU pilots it

The plan lives in [`decks/atraxa_praetors_voice.py`](../../src/automtg/ai/strategy/decks/atraxa_praetors_voice.py)
as `Proliferate`, a subclass of the `Superfriends` archetype.

| Behaviour | Where |
|---|---|
| **Walkers before creatures.** The archetype's +120 alone loses to a creature of the same cost (the agent scores creatures from 300), so this deck adds another 150: Oko comes down before Eternal Witness. | `Superfriends.priority_value` ([archetypes.py](../../src/automtg/ai/strategy/archetypes.py)), `Proliferate.walker_bonus` |
| **Plus first; a minus only when it hits something of theirs or is the ultimate.** A walker is never minused to death. | `Superfriends._loyalty_value` |
| **Engines are better with walkers out** — Doubling Season, Tide, Channeler, Tekuthal and Brokers Ascendancy get +25 per walker we control. | `Proliferate.priority_value`, `ENGINES` |
| **Proliferate is priced by what it grows.** Contentious Plan gets +15 per permanent with counters (and per poisoned opponent); Karn's Bastion and Viral Drake are not activated at all when nothing would grow. | `Proliferate.priority_value`, `growing` |
| **Proliferate picks our walkers and their −1/−1 or poison counters**, never the reverse. | the agent's `proliferate` choice ([heuristic_agent.py](../../src/automtg/ai/agents/heuristic_agent.py)) |
| **Jace, Memory Adept's −7 only at opponents it decks.** Never with ourselves among the targets, never at a library deeper than twenty; more decked opponents is better. | `Proliferate._jace_ultimate` |
| **Creatures block for walkers** that are being attacked. | `Superfriends.block_value` |
| **Teferi's Protection waits for the lethal swing.** The agent would cast it at sorcery speed for nothing; this holds it until unblocked damage would kill us, then casts it before damage. | `Proliferate.priority_value`, `PROTECTION` |
| **Walker tutors and Doubling Season get key-card bonuses**; finishers and engines are discarded last. | `DeckPlan.key_cards`, `win_cons`, `protect` |

## Strengths

- **Inevitability.** Every turn the walkers survive, they grow; the table has to
  spend attacks on them or face an ultimate.
- **Removal everywhere.** Half the walkers' minuses are removal, on top of a
  full suite of instants and two wraths.
- **Resilient threats.** Losing one walker is losing one of thirty; Atraxa
  returns from the command zone.
- **Doubling Season turns** where two walkers ultimate on arrival end games out
  of nowhere.

## Weaknesses

- **Wide aggro.** Walkers are soft to a swarm. The CPU blocks for them but has
  no notion of keeping blockers home *for* them before the attack comes.
- **The Chain Veil loop is not executed.** The combo is encoded for its bonus
  and protection, but the agent activates each loyalty ability once a turn and
  cannot see the untap-and-reactivate line.
- **Deepglow Skate's targets** are chosen by the agent's generic target pick,
  not steered to our walkers.
- **No lookahead.** The CPU does not count loyalty toward next turn's ultimate
  or hold a walker back until Doubling Season lands.
- **Four colours, many taplands.** Slow starts happen; the baseline land pick
  helps with colours but not with tempo.
- **Teferi's Protection answers combat only.** The CPU saves it for a swing
  that would kill us; it cannot see an opposing wrath on the stack as a reason
  to phase the walkers out.

## Mulligan

**Three to five lands** (`keep_lands = (3, 5)`) and an early play. Four
colours and a curve that starts at three need the lands; a hand of walkers with
two lands goes back.
