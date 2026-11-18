---
id: the-ring-tempts-you
title: The Ring tempts you
area: cards
effort: M
impact: high
why: Food and Fellowship's commander and every Ring card in the Lord of the Rings sets wait on it
depends_on: []
status: proposed
---

## Today

The engine has player designations that outlive what granted them: the
monarch is one field, `GameState.monarch`, set through
`primitives.become_monarch`, with its inherent triggers in the turn machine
(`turn._monarch_draw`) and its readers as condition leaves (`is_monarch`)
and a player spec (`monarch`). Emblems exist too: an object in the command
zone whose `emblem` index names one of its card's `emblems`, which
`GameState` resolves to a definition with abilities and nothing else.

Nothing models 701.54. There is no op for "the Ring tempts you", no
Ring-bearer designation on a permanent, no per-player count of how many
times the Ring has tempted them, and no trigger event for "whenever the Ring
tempts you". [rules-coverage.md](../rules-coverage.md#not-implemented) does
not mention the Ring at all. The
[Food and Fellowship batch](precon-ltc-food-and-fellowship.md) found it
through its own commander: `data/authoring/gaps/frodo_adventurous_hobbit.json`
names `the-ring-tempts-you`, and Frodo cannot be authored without it.

## The change

1. Per player, the Ring's level (how many times the Ring has tempted that
   player this game, capped at the four abilities for what is unlocked but
   counted in full, since "two or more times this game" reads the count) and
   the oid of their Ring-bearer, if any. The Ring-bearer is cleared when that
   permanent leaves the battlefield or changes control.
2. A `the_ring_tempts_you` op: the player's count rises by one, then they
   choose a creature they control as Ring-bearer, which may be the one
   already chosen. A player with no creature is still tempted.
3. The Ring's four abilities, unlocked in order, applied to that player's
   Ring-bearer: legendary, and can't be blocked by creatures with greater
   power; whenever it attacks, draw then discard; whenever it becomes
   blocked by a creature, that creature's controller sacrifices it at end of
   combat; whenever it deals combat damage to a player, each opponent loses
   3 life. These are a characteristics layer and inherent triggers, in the
   monarch's shape (no card to hang them on), not abilities granted by a card.
4. The readers: a `ring_tempted_you` trigger event, a `ring_bearer` selector
   key and `is_ring_bearer` condition, a `ring_tempt_count` value, and
   "choose a Ring-bearer" as a decision the client already renders as an
   object choice.
5. Harvest: Frodo, Adventurous Hobbit through `/author-cards`, then one
   wave over the catalog's other Ring cards.

It does not build partner-with (Frodo's other blocked line, which belongs
to the Food and Fellowship batch) and adds no client surface beyond the
existing player readout, where the Ring's level and bearer show beside the
monarch.

## Gate

A unit test under `tests/unit/` for the Ring: tempting raises the count and
asks for a Ring-bearer, a second temptation may move it, each level unlocks
its ability on the bearer and only on the bearer, the bearer is legendary
and evades bigger blockers, losing the bearer (dies, bounced, stolen) clears
it without lowering the count, a player with no creature is still tempted
and the `ring_tempted_you` trigger fires. Frodo's six gates pass, and the
generated DSL reference (`tests/cards/test_dsl_reference.py`) lists the new
op, event, selector key and value.

## Open questions

- **Where the Ring lives.** Fields on `PlayerState` (count and bearer oid),
  or an emblem object in the command zone? Recommended: fields on
  `PlayerState`, the monarch's shape: an emblem object here is one of a
  printed card's `emblems`, and the Ring belongs to no card, so it would need
  a synthetic owner the engine has nowhere else.
- **Inherent triggers on the stack or inline.** The Ring's attack, block and
  damage abilities are triggered abilities that use the stack. Recommended:
  on the stack, sourced from the Ring-bearer for targeting and "its
  controller", because players respond to the loot and the 3 life; inline
  only if the engine has no seam for it, recorded in rules-coverage.md as a
  divergence beside the monarch's draw.
- **The legend rule on the bearer.** "Your Ring-bearer is legendary" can
  make two copies of one creature collide under 704.5j. Recommended: yes,
  through the characteristics layer like any other type-changing effect, so
  the legend rule sees it with no special case.
- **Is it an ADR.** Recommended: yes, a short one, because the choice of
  player fields over an emblem object, and of inherent triggers over
  granted abilities, is a shape later designations (the initiative, rad
  counters) will copy or reverse.
