# Zurgo Stormrender

## Overview & play style

Mardu tokens and aristocrats with a commander who **pays you for every token
that dies**. Zurgo has mobilize 1 — each attack makes a 1/1 Warrior, tapped and
attacking, sacrificed at end of turn — and his second ability turns every
creature token that leaves the battlefield into a card (if it was attacking) or
a point of drain from each opponent (if it was not). So the deck wants to
**attack every turn**, and it does not care much whether its tokens survive.

The rest of the list is token makers (Hordeling Outburst, Dragon Fodder,
Increasing Devotion, Grave Titan, Secure the Wastes) and the drain package it
shares with Edgar Markov: Bastion of Remembrance, Zulaport Cutthroat, Cruel
Celebrant, Blood Artist, Falkenrath Noble. Impact Tremors and Hellrider charge
the table for the tokens entering and attacking. It plays **fast and wide**,
and it wins on reach more often than on combat damage.

## Win conditions

- **Death triggers.** With two drain creatures and Bastion out, every token
  that dies is three or four life off each opponent. A turn of attacks plus the
  end-step mobilize sacrifice adds up quickly in a pod.
- **Impact Tremors and Hellrider.** Damage for entering and for attacking, so a
  wide board deals damage before blockers matter.
- **Sanguine Bond and Epicure of Blood.** Every life the drain creatures gain
  becomes another drain.
- **Plain combat.** Intangible Virtue and Chief of the Edge make the tokens
  real attackers.

## Key cards & combos

| Card | Why it matters |
|---|---|
| Zurgo Stormrender | Three mana, a free token each attack, and a card or a drain for each token lost. |
| Bastion of Remembrance | A token on entry, then two life across the table per death. |
| Zulaport Cutthroat, Cruel Celebrant, Blood Artist | The drain on a cheap body the deck is happy to lose. |
| Impact Tremors | Pings for every token, including the mobilize token every attack. |
| Dictate of Erebos | Every death on our side is an edict on theirs. |
| Vampiric Rites, Indulgent Aristocrat, Bloodthrone Vampire | Sacrifice outlets: tokens into cards, counters or damage. |

The plan names one **combo**: **Sanguine Bond + Epicure of Blood**. It is not
a loop, but with a drain creature out each death becomes a drain, a life gained,
a second drain and a third. The pieces are protected from discard.

## How the CPU pilots it

The plan lives in [`decks/zurgo.py`](../../src/automtg/ai/strategy/decks/zurgo.py)
as `ZurgoAristocrats`, a subclass of `Aristocrats` (which is `GoWide`, which is
`Aggro`).

| Behaviour | Where |
|---|---|
| **Zurgo on turn three.** His key-card bonus (120) puts him over any other three-drop. | `DeckPlan.key_cards`, read by `DefaultStrategy.priority_value` ([default.py](../../src/automtg/ai/strategy/default.py)) |
| **Creatures and token makers early.** | `Aggro.priority_value`, `GoWide.priority_value` ([archetypes.py](../../src/automtg/ai/strategy/archetypes.py)) |
| **Even trades are taken.** With `aggression = 0.8` an attacker swings into a blocker of about its own worth; the baseline, at 0.5, holds back. | `DefaultStrategy._attack_worth` |
| **Zurgo swings first when the attack is safe**, so the mobilize token joins whatever follows. He is still kept out of blocks that kill him for free. | `ZurgoAristocrats.attack_value` |
| **Tokens attack into blockers while Zurgo is out.** A blocked-and-killed token is a card off Zurgo plus every death payoff; unblocked, it deals damage. Only the crack-back veto keeps one home. | `ZurgoAristocrats.attack_value` |
| **Wide boards swing past the blockers.** | `GoWide.attack_value` |
| **Sacrifice outlets eat tokens, not cards.** "Sacrifice a creature" activations are skipped while no token is out; "sacrifice this" (Evolving Wilds, Mind Stone) is unaffected. | `ZurgoAristocrats.priority_value`, `_sacrifices_a_creature` |
| **Tokens are sacrificed and discarded first; drain creatures last.** | `Aristocrats.junk_value`, `DeckPlan.win_cons` / `protect` |
| **Drains and "target player loses life" go at the opponent nearest death.** | `DefaultStrategy.aim_at_players` |

## Strengths

- **Fast pressure.** A turn-three commander that attacks immediately, with
  token makers behind it, punishes slow pods.
- **Reach.** Much of the damage is drain, which blockers and fliers do not stop.
- **Card flow from combat.** Mobilize means even a bad attack draws, so the
  deck refuels while it pressures.
- **Cheap removal.** Swords, Path, Terminate, Go for the Throat and Dreadbore
  go at the biggest threat.

## Weaknesses

- **Board wipes.** One wrath clears the tokens and the drain creatures with
  them. The CPU has no lookahead and does not hold back a second wave.
- **No sacrifice timing.** The CPU uses outlets once a turn whenever they
  score, not in response to removal or at the last moment before the mobilize
  token is sacrificed anyway. A sacrificed attacking token does still draw.
- **Mobilize tokens are not declared.** They enter tapped and attacking, so the
  attack rules never see them; the CPU's attack choices are for the creatures
  it already had.
- **Life as a resource.** Night's Whisper, Read the Bones, Phyrexian Arena and
  Adanto Vanguard all cost life; the agent only refuses a life payment near its
  chump-block threshold, so an aggressive pod can catch it low.

## Mulligan

The baseline: **two to five lands and at least one play costing three or
less**. Most hands qualify — the curve is low and Zurgo himself is a three-drop
in the command zone. A two-lander with a one-drop and a token maker is a keep;
six lands goes back.
