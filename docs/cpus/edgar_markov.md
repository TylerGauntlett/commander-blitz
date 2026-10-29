# Edgar Markov ("Markov Chains")

## Overview & play style

Mardu Vampires with a commander who **works from the command zone**. Edgar's
eminence makes a 1/1 Vampire whenever the deck casts another Vampire, whether
or not Edgar himself has been cast. So the first turns are cheap Vampires —
Viscera Seer, Cordial Vampire, Bartolomé del Presidio, Legion Lieutenant —
each of which is **two bodies for the price of one**. By the time Edgar costs
six and arrives with haste, the board is already wide, and his attack trigger
puts a +1/+1 counter on all of it.

The second half of the deck is aristocrats: the bodies are **fuel**. Blood
Artist, Cruel Celebrant, Bastion of Remembrance and Vein Ripper drain on every
death; Viscera Seer, Carrion Feeder, Bartolomé del Presidio and Phyrexian Tower
are free sacrifice outlets; Grave Pact and Anowon turn each sacrifice into an
opponent's creature too. It plays **fast and wide**, and wins on drain as
often as on combat damage.

## Win conditions

- **The Conqueror loops.** Bloodthirsty Conqueror gains us life whenever an
  opponent loses life; Vito, Thorn of the Dusk Rose and Marauding Blight
  Priest make an opponent lose life whenever we gain it. Either pair is an
  infinite drain that kills the table in one go.
- **Death triggers.** A sacrifice outlet plus two drain creatures, with
  Bloodletter of Aclazotz doubling life loss on our turn, ends games.
- **Lords and Edgar.** Legion Lieutenant, Stromkirk Captain, Captivating
  Vampire and Edgar's counters make the eminence tokens real attackers;
  Shared Animosity makes a Vampire attack enormous.

## Key cards & combos

| Card | Why it matters |
|---|---|
| Edgar Markov | Eminence doubles every Vampire cast, from the command zone; haste and a team-wide counter when he attacks. |
| Bloodthirsty Conqueror | Half of both infinite combos, and a 5/5 flying deathtoucher on its own. |
| Vito, Thorn of the Dusk Rose / Marauding Blight Priest | The other halves: lifegain into life loss. |
| Blood Artist, Cruel Celebrant, Bastion of Remembrance | Drain on every death; the reason the tokens are worth sacrificing. |
| Grave Pact | Each of our sacrifices is an edict on every opponent. |
| Skullclamp | Two cards per 1/1 token the deck was going to sacrifice anyway. |
| Stromkirk Captain, Legion Lieutenant | Lords: every eminence token becomes a 2/2 first striker. |
| Olivia's Wrath | A one-sided wrath, when the board is the right shape. |

The plan names **two combos**, both 400-point bonuses: **Vito + Bloodthirsty
Conqueror** and **Marauding Blight Priest + Bloodthirsty Conqueror**. Holding
one piece with the other on the table, the CPU casts it ahead of almost
anything; all three pieces are protected from discard and sacrifice.

## How the CPU pilots it

The plan lives in
[`decks/edgar_markov.py`](../../src/commanderblitz/ai/strategy/decks/edgar_markov.py)
as `VampireAristocrats`, a subclass of `Tribal` (which is `GoWide`, which is
`Aggro`).

| Behaviour | Where |
|---|---|
| **Vampires before anything else of the same cost** — each is an eminence token too. | `Tribal.priority_value`, `tribe = "Vampire"` ([archetypes.py](../../src/commanderblitz/ai/strategy/archetypes.py)) |
| **Lords, drain creatures and Grave Pact** carry key-card bonuses. | `DeckPlan.key_cards`, read by `DefaultStrategy.priority_value` ([default.py](../../src/commanderblitz/ai/strategy/default.py)) |
| **The loop is completed on sight.** Vito or Blight Priest with the Conqueror out (or the reverse) gets the combo bonus. | `DeckPlan.combos`, `DefaultStrategy.combo_bonus` |
| **Olivia's Wrath waits until it is one-sided:** at least three more non-Vampire creatures on the other side than ours, and then it is a priority play. | `VampireAristocrats.priority_value`, `wrath_margin` |
| **Skullclamp goes on a 1-toughness token.** | `VampireAristocrats.priority_value` |
| **Tokens are sacrificed and discarded first** — non-Vampire tokens (Bastion of Remembrance's Human Soldier) before Vampires, which the lords pump. | `VampireAristocrats.junk_value` |
| **Combo pieces and drain creatures are sacrificed last.** | `DeckPlan.protect` / `win_cons` / `combos`, `DefaultStrategy.junk_value` |
| **Trades are accepted** (`aggression = 0.7`), and a wide board swings past the blockers. | `DefaultStrategy._attack_worth`, `GoWide.attack_value` |
| **"Target opponent loses life" goes at the opponent nearest death.** | `DefaultStrategy.aim_at_players` |

## Strengths

- **Explosive starts.** A one-drop Vampire is two bodies on turn one, and the
  deck has a dozen Vampires at one or two mana.
- **Reach.** Drain ignores blockers and fliers; a wide board on its way to the
  graveyard still kills.
- **Two infinite combos** that share a piece, both castable off a normal curve.
- **Wrath insurance.** Every creature dying to a wrath drains, Grave Pact
  takes the table's creatures with ours, and Teferi's Protection or Clever
  Concealment dodge the wrath entirely.

## Weaknesses

- **Graveyard and enchantment hate.** Grave Pact and Bastion are the engines;
  an enchantment wipe or Rest in Peace on Bloodghast slows the deck badly.
- **No sacrifice timing.** The CPU activates outlets when they score, once a
  turn per ability, not in response to removal. It does not sacrifice a
  creature that is about to be exiled.
- **Edgar's attack trigger is not foreseen.** The agent judges each attacker
  as it stands; it does not count the +1/+1 counter Edgar's attack will add.
- **Life as a resource.** Necropotence, Black Market Connections, Anguished
  Unmaking and the painlands all cost life the agent only stops paying near
  its chump threshold.
- **Eminence is not valued separately.** The CPU casts Edgar when it can
  rather than waiting; the Vampire bonus is what keeps the cheap ones first.

## Mulligan

The baseline: **two to five lands and at least one play costing three or
less**. Nearly every hand has a cheap Vampire. Three colours make a two-lander
with no fixing worse than it looks, but the baseline keeps it if it has a
one- or two-drop — usually right, since Edgar's eminence is working from turn one.
