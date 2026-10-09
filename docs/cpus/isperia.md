# Isperia, Supreme Judge

## Overview & play style

Azorius fliers and control. Isperia is a 6/4 flier that **draws a card for
every creature that attacks you**, so the deck's job is to make attacking you
survivable and then expensive: cheap blockers, a deep counterspell suite, two
wraths, Evacuation, Sunblast Angel and Angel of the Dire Hour for the alpha
strike. While the table bounces off that, the fliers — Serra Angel, Lyra, Air
Elemental, three Sphinxes — end the game in two or three swings.

It plays **slow and reactive**. The deck has no pillowfort (the engine cannot
express "costs more to attack you", see [decks.md](../decks.md#isperia-supreme-judge)),
so the deterrent is the card draw and the answers, not a tax.

## Win conditions

- **The air force.** Empyrean Eagle pumps every other flier; Lyra pumps the
  Angels and gives them lifelink; Archangel of Thune turns that lifelink into
  counters on the whole team.
- **Card advantage.** Consecrated Sphinx, Isperia, Windreader Sphinx and
  Reconnaissance Mission bury a pod in cards; eventually only this seat has
  answers left.
- **Isperia herself.** Six power in the air is 21 commander damage in four
  hits.

## Key cards & combos

| Card | Why it matters |
|---|---|
| Isperia, Supreme Judge | Every attack at you is a card. The pod's aggro deck learns to hit someone else. |
| Bident of Thassa | {1}{U}, {T}: the opponents' creatures **must** attack this turn — and each one that attacks you draws Isperia a card. |
| Consecrated Sphinx | Two cards for every one an opponent draws. Decides the game if it survives a rotation. |
| Wrath of God, Day of Judgment, Evacuation | The reset button, for when the table's board outgrows the counters. |
| Angel of the Dire Hour | Flash: cast mid-combat, it exiles every attacking creature. |
| Counterspell, Absorb, Dissolve, Dismiss, Cancel, Negate, Essence Scatter, Exclude | The suite that keeps the big threats off the table. |

Two **combos** are named in the plan: **Lyra + Archangel of Thune** (Thune
gains lifelink, so every hit puts a counter on the whole team) and **Isperia +
Bident of Thassa** (forced attacks are free cards).

## How the CPU pilots it

The plan lives in [`decks/isperia.py`](../../src/automtg/ai/strategy/decks/isperia.py)
as `IsperiaControl`, a subclass of `Control`.

| Behaviour | Where |
|---|---|
| **Counters a two-drop.** The classic agent saved counterspells for three-mana spells; control spends them from two up. | `Control._cheap_counter` (`counter_floor = 2`, [archetypes.py](../../src/automtg/ai/strategy/archetypes.py)) |
| **Only evasive creatures attack into blockers.** Ground creatures stay home and block. | `Control.attack_value` |
| **Wraths only when they are one-sided.** The classic agent cast Wrath of God whenever nothing scored higher — often with only its own fliers on the table. A sweeper now needs the opponents' creatures to be worth at least 8 more than ours (power plus mana value, a commander counted double). | `IsperiaControl._sweeper_value` (`SWEEP_MARGIN`) |
| **Angel of the Dire Hour is held for the alpha strike.** During an opponent's combat with 5+ power attacking, it is flashed in to exile them all; in our own main phase it waits while the table has two or more creatures that could attack. | `IsperiaControl._dire_hour_value`, `_blowout` |
| **Evacuation mid-combat.** The same blowout rule, for the instant that bounces everything. | `IsperiaControl._sweeper_value` |
| **Bident on their turn, never ours.** Forced attacks only matter on an opponent's turn before combat, only with Isperia out, and only when that player's whole team cannot take half our life. | `IsperiaControl._bident_value` |
| **Isperia, Consecrated Sphinx and the flier anthems first.** | `DeckPlan.key_cards`, read by `DefaultStrategy.priority_value` ([default.py](../../src/automtg/ai/strategy/default.py)) |
| **Wraths and the Dire Hour are the last cards discarded.** | `DeckPlan.protect`, `DefaultStrategy.junk_value` |
| **Isperia does not chump-block** unless the damage is lethal. | `DefaultStrategy.block_value` |

## Strengths

- **Hard to attack.** Counters, sweepers and a commander that draws off every
  attacker make this the least attractive seat at the table.
- **Card advantage.** The deck draws more than anything else in the pod, and
  the CPU spends the cards on answers and fliers rather than wasting them.
- **Evasion.** Nearly every threat flies, so the attack rules find safe swings.

## Weaknesses

- **Counters only with mana left over.** The CPU has no lookahead and casts on
  its own turn whatever scores highest; it does not deliberately keep two
  islands open for Counterspell. Counters fire when the mana happens to be up.
- **Instants at sorcery speed.** Draw spells (Jace's Ingenuity, Inspiration,
  Sphinx's Revelation) are cast in its own main phase, not at the end of an
  opponent's turn.
- **Slow.** A six-mana commander and a reactive plan lose to a fast combo or a
  wide aggro start if the counters miss.
- **The sweeper count is rough.** "Worth" is power plus mana value; a board of
  cheap but dangerous engines (a Rhystic Study creature, a sacrifice outlet)
  reads as small and does not trigger a wrath.
- **Bident is cautious.** The CPU only forces attacks the active player cannot
  kill it with, and does not account for what the other opponents might add.

## Mulligan

The baseline: **two to five lands and at least one play costing three or
less**. With a six-drop commander and a 3.4 average mana value, the hands to
keep are three or four lands with a cantrip, a counter or a cheap flier; the
baseline sends back the six-landers and the hands with nothing to do before
turn four.
