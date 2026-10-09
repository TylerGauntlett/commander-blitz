# Bruvac the Grandiloquent — "Millington"

## Overview & play style

Mono-blue mill with a commander who **doubles every card an opponent mills**.
Bruvac is a 1/4 for three that does nothing alone and makes everything else
twice as good: Traumatize becomes "mill your whole library", Maddening
Cacophony kicked does the same to the whole table, and the deck's engine — **twenty
copies of Persistent Petitioners** — mills two for one mana each, or twenty-four
when four Advisors tap together.

The rest of the list is blue staples and mill enchantments. Drowned Secrets,
Memory Erosion, Sphinx's Tutelage, Teferi's Tutelage and Altar of the Brood turn
ordinary turns into a few cards off the top; Rhystic Study and Mystic Remora draw
the deck; Cryptic Command, Archmage's Charm and Muddle the Mixture keep the
opponents honest. It plays **slow and grindy**, never attacks, and wins by
emptying libraries rather than life totals.

## Win conditions

- **The Petitioner swarm.** Four Advisors (Bruvac counts) tapped together mill
  twelve, doubled to twenty-four. Two activations a turn end a game quickly.
- **Isochron Scepter + Dramatic Reversal.** Imprint Reversal, tap the
  Advisors to mill, pay {2} to untap everything, repeat. With Sol Ring or
  Gilded Lotus the loop is mana-positive and decks the table in one turn;
  without rocks it is still a second (and third) Petitioner activation.
- **Traumatize and Maddening Cacophony** with Bruvac out: half a library,
  doubled, is the whole library.
- **Brain Freeze** on a busy turn: three cards a copy, six with Bruvac.
- **Thassa's Oracle and Jace, Wielder of Mysteries** as the backup when our own
  library runs short.

## Key cards & combos

| Card | Why it matters |
|---|---|
| Bruvac the Grandiloquent | Doubles every mill. Everything in the deck is half as good without him. |
| Persistent Petitioners | Twenty copies: a mana sink every turn and a twenty-four-card activation with four out. |
| Isochron Scepter | With Dramatic Reversal imprinted, untaps every Advisor and rock for {2}. |
| Traumatize, Maddening Cacophony | The big finishers, held for Bruvac. |
| Drowned Secrets, Memory Erosion | Mill on every spell — ours or theirs. |
| Sphinx's Tutelage, Teferi's Tutelage | Every card we draw mills an opponent. |
| Merchant Scroll, Mystical Tutor | Fetch Dramatic Reversal when a Scepter is waiting for it, a finisher otherwise. |

The plan names one **combo**: **Isochron Scepter + Dramatic Reversal**. Holding
one, the other gets the combo bonus; both are protected from discard.

## How the CPU pilots it

The plan lives in [`decks/bruvac_the_grandiloquent.py`](../../src/automtg/ai/strategy/decks/bruvac_the_grandiloquent.py)
as `Millington`, a subclass of the `Mill` archetype.

| Behaviour | Where |
|---|---|
| **Bruvac first.** His key-card bonus (120) puts him over any other three-drop. | `DeckPlan.key_cards`, read by `DefaultStrategy.priority_value` ([default.py](../../src/automtg/ai/strategy/default.py)) |
| **Mill goes at the shortest library, never at ourselves.** | `Mill.player_score` ([archetypes.py](../../src/automtg/ai/strategy/archetypes.py)), `DefaultStrategy.aim_at_players` |
| **Traumatize and Cacophony wait for Bruvac** while he is in the command zone (until turn 12), then get +150 — +60 more for a kicked Cacophony. | `Millington.priority_value`, `BIG_MILL`, `HOLD_UNTIL` |
| **Petitioners mill rather than attack.** "Tap four Advisors" gets +40 over the one-mana mill; Advisors never attack unless the swing is lethal. | `Millington._petition_value`, `Millington.attack_value` |
| **The Scepter imprints Dramatic Reversal** over Brain Freeze or anything else, and Reversal itself is never cast from hand while a Scepter is waiting for it. | `Millington.choose`, `_scepter_needs` |
| **The Scepter loop runs to the end.** The agent normally uses an ability once a turn; with Reversal imprinted, the Scepter and the Petitioners go again as long as a mill has *resolved* and an Advisor is tapped. That is also what guarantees the loop stops: every pass mills cards and libraries are finite. | `Millington._scepter_value`, `_petition_value`, `_loop_live` |
| **Brain Freeze waits for a storm count of two**, unless the copies already deck the target. Copies go at opponents, never back at us. | `Millington._brain_freeze`, `_copy_target` |
| **Thassa's Oracle only when it wins** — devotion to blue (plus its own two) at least our library. | `Millington.priority_value`, `devotion_to_blue` |
| **Tutors fetch the missing combo piece**, then a finisher. | `Millington.choose`, `TUTOR_ORDER` |
| **Finishers and mill enchantments are the last cards discarded.** | `DeckPlan.win_cons` / `protect` |

## Strengths

- **A one-turn kill from an ordinary board.** Scepter, Reversal, a rock and four
  Advisors — all cheap, all things the deck plays anyway — mill a four-player
  table out.
- **Inevitability.** Twenty Petitioners mean the engine is always in the draw.
- **Mill ignores life.** Lifegain decks, fogs and big blockers do not matter.
- **Bruvac's doubling hits every source**, including the opponents' own
  Memory Erosion triggers.

## Weaknesses

- **Graveyard decks.** Milling a reanimator or a flashback deck feeds it. The
  CPU does not tell those opponents apart.
- **Bruvac dies easily.** A 1/4 with no protection; without him everything mills
  half as much, and the CPU holds Traumatize up to turn 12 hoping he returns.
- **Counters are cast reactively, not held.** The agent counters a spell when it
  has the counterspell and the mana, but it does not keep mana open on purpose —
  it spends main-phase mana on Petitioners first.
- **No lookahead.** The Scepter loop is found one activation at a time; the CPU
  does not plan a turn to assemble it, and it taps mana badly (Gilded Lotus for
  a two-mana spell).
- **Thassa's Oracle is mostly dead.** The deck rarely empties its own library,
  so the Oracle sits in hand; Jace's "win on an empty draw" is never planned for.
- **Symmetric draw.** Folio of Fancies and Mikokoro draw for everyone, and the
  CPU prices both halves of Folio at the agent's flat activation weight. The
  baseline's X rule keeps the draw from decking us, but it can still refill an
  opponent's hand.

## Mulligan

The baseline: **two to five lands and at least one play costing three or
less**. With twenty two-mana Petitioners almost every hand has an early play; a
hand with Scepter and Reversal together is a keep on any reasonable land count.
