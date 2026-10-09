# Sheoldred, the Apocalypse — "Draw Death"

## Overview & play style

Mono-black punisher. Sheoldred makes **every card an opponent draws cost two
life** and gives us two for each of ours, and the whole deck is built to make
the table draw: Howling Mine, Font of Mythos, Temple Bell, Otherworld Atlas,
Teferi's Puzzle Box, Seizan, Master of the Feast, Scrawling Crawler. Underworld
Dreams, Fate Unraveler and Ob Nixilis, the Hate-Twisted stack more pain on each
card; Sign in Blood, Blood Pact, Damnable Pact and Peer into the Abyss are draw
spells for us and **kill spells pointed across the table**.

The catch is that every one of those cards is a gift while no punisher is out.
So the deck plays **two speeds**: a normal black midrange game (ramp, removal,
draw for ourselves) until Sheoldred or Underworld Dreams lands, then a flood of
cards for everybody that ends the game in a turn or two. Thirty-six lands and a
pile of rocks make sure Sheoldred lands on time; Lightning Greaves and Swiftfoot
Boots keep her there.

## Win conditions

- **Forced draws under Sheoldred.** Howling Mine plus Sheoldred is two life per
  opponent per turn from a two-mana artifact; Font of Mythos is four; Puzzle Box
  is a whole hand's worth.
- **Pacts at an opponent.** Sign in Blood under Sheoldred is six life; Damnable
  Pact for X is 3X; Peer into the Abyss halves a life total and then charges
  for half a library.
- **Lifegain drains.** Sheoldred gains us two per draw; Sanguine Bond, Vito and
  Marauding Blight Priest turn that gain into more loss across the table.
- **Gray Merchant** for the devotion burst, and a 4/5 deathtouch body in combat.

## Key cards & combos

| Card | Why it matters |
|---|---|
| Sheoldred, the Apocalypse | Two life per opponent draw, two life gained per ours. The engine. |
| Underworld Dreams, Fate Unraveler, Ob Nixilis (Hate-Twisted), Scrawling Crawler | More pain per card — and a backup punisher when Sheoldred dies. |
| Howling Mine, Font of Mythos, Teferi's Puzzle Box, Temple Bell | The forced draws. |
| Sign in Blood, Blood Pact, Damnable Pact, Peer into the Abyss | Draw for us, or a burn spell aimed at an opponent. |
| Lightning Greaves, Swiftfoot Boots | Shroud or hexproof on the one creature that matters. |
| Sanguine Bond, Vito | Turn every life Sheoldred gains us into a drain. |

The plan names three **combos**, none of them a loop (the list has no Exquisite
Blood): **Sheoldred + Sanguine Bond**, **Sheoldred + Vito** and **Sheoldred +
Teferi's Puzzle Box**. Each gets a cast bonus once the other piece is available
and is protected from discard.

## How the CPU pilots it

The plan lives in [`decks/sheoldred_the_apocalypse.py`](../../src/automtg/ai/strategy/decks/sheoldred_the_apocalypse.py)
as `DrawDeath`, a subclass of the `Punisher` archetype. Everything hangs off one
number, **`pain`**: how much life an opponent loses per card drawn, from the
punishers we control right now (Sheoldred 2, each of the others 1).

| Behaviour | Where |
|---|---|
| **Sheoldred first.** Her key-card bonus (120) beats any other four-drop. | `DeckPlan.key_cards`, read by `DefaultStrategy.priority_value` ([default.py](../../src/automtg/ai/strategy/default.py)) |
| **Group draw gets +40 per point of pain.** With Sheoldred out, Howling Mine outranks most creatures. | `DrawDeath.priority_value`, `GROUP_DRAW` |
| **Font of Mythos, Puzzle Box and Dark Deal are held** while pain is zero — they only feed the table. | `DrawDeath.priority_value`, `HELD` |
| **Temple Bell, Mikokoro, Geier Reach and Otherworld Atlas are only activated under a punisher**, and then they are worth 30 per point of pain (Atlas: per charge counter too). | `DrawDeath.priority_value`, `GROUP_DRAW_ABILITIES` |
| **Pacts are aimed by pain.** With no punisher, Sign in Blood and Blood Pact target us (above 10 life); with one, they go at an opponent. A pact that kills is cast at once (+400) at the player it kills. Damnable Pact, Peer and Eldritch Pact are never aimed at us. | `DrawDeath._pact_value`, `_pact_size` |
| **Boots and Greaves go on Sheoldred** and are never moved off her. | `DrawDeath._equip_value` |
| **Sheoldred is not traded in combat.** The baseline holds a commander out of blocks and attacks that kill it for less. | `DefaultStrategy._attack_worth`, `block_value` |
| **Removal at the biggest threat; protected cards discarded last.** | the agent's removal score; `DeckPlan.win_cons` / `protect` |

## Strengths

- **Explosive once set up.** One punisher and one draw engine is a clock on the
  whole table at once, not one opponent at a time.
- **Card advantage either way.** Before Sheoldred the pacts and Arena keep our
  hand full; after her the same cards are reach.
- **Cheap, plentiful interaction.** Infernal Grasp, Snuff Out, Dismember,
  Feed the Swarm, Toxic Deluge, Sheoldred's Edict.
- **Backup punishers.** Losing Sheoldred slows the deck; Underworld Dreams and
  Fate Unraveler keep the group draw from being a pure gift.

## Weaknesses

- **Without a punisher it is a pile of gifts.** The CPU holds the worst
  symmetric cards, but Howling Mine and Seizan still give the table cards.
- **Removal on Sheoldred.** She has no protection until the Boots arrive; the
  CPU equips as soon as it can but cannot hold up an answer for her.
- **Self-damage.** The deck pays life constantly (pacts, Greed, Arena, Snuff
  Out, Toxic Deluge). The CPU guards the pacts with a life floor but has no
  wider life budget.
- **No lookahead.** It does not sequence "Sheoldred this turn, Font next turn" as
  a plan — it simply scores Font higher once Sheoldred is on the table.
- **Triggered targets are not steered.** Bloodgift Demon's upkeep "target
  player draws and loses 1" is answered by the agent's generic target choice,
  not by the pain rule.
- **Puzzle Box and Elder Brain choices** (which cards to bottom, which to cast
  from exile) are the agent's defaults.

## Mulligan

**Three to five lands** (`keep_lands = (3, 5)`) and an early play. The deck is
heavier than most — Sheoldred is a four-drop and the payoffs cost four or five —
so a two-lander goes back — even with a Sol Ring in it, since the baseline
counts lands, not mana. A hand that can cast Sheoldred on turn four is the keep
to look for.
