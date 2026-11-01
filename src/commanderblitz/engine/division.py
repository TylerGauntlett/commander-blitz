"""Damage divided among targets (601.2d) -- the amount, and the cap it puts on them.

    "Pyrokinesis deals 4 damage divided as you choose among any number of
     target creatures."

A spell's ``damage`` effect with ``divided`` names one target spec, and the
spell's controller announces how the amount is split among that spec's objects
**as the spell is cast**, after the targets and before the cost (601.2d). Three
places need the same two readings, so they live here:

- legality, which may not offer a line with more targets than there is damage
  to give them -- "each target must receive at least one" -- through
  `casting._cast_variant`;
- the deferred "any number of targets" pick, `Game._ask_deferred_targets`,
  whose ceiling the amount lowers;
- the announcement itself, `Game._ask_damage_division`.

The amount is read **once, at announcement**, with the spell's controller and
the spell as the source, and the shares ride on the stack item as
``bindings["distribution"]`` -- the key `distribute_counters` already uses, in
the same shape. 601.2d needs the number before it can be divided, so a divided
amount is always the number as the spell was cast: Monstrous Onslaught's
"greatest power among creatures you control **as you cast this spell**" is the
printed form of what every divided amount is. Nothing is re-read on
resolution, and a target that became illegal loses its share (608.2b).

**An announced X** reaches here as ``x``. Only the X of an additional
``pay_life_x`` cost (Fire Covenant) may be divided: `Game._cast` announces it
before the targets are declared (601.2b, then 601.2c), so the "any number" pick
is capped by it. Legality, which has no X yet, caps a line at the most X the
caster could announce. A mana {X} is announced after the targets on this
engine's cast line, and the loader refuses dividing it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from .effects.context import EffectContext
from .effects.values import evaluate_value
from .targeting import declared_by_spec

if TYPE_CHECKING:  # pragma: no cover
    from .carddef import CardDef, TargetSpec
    from .state import GameState
    from .structs import TargetRef


def divided_damage(card: CardDef) -> list[Mapping[str, Any]]:
    """The spell's top-level divided damage effects -- where the loader keeps them."""
    return [
        effect
        for effect in card.spell_effects
        if isinstance(effect, Mapping) and effect.get("op") == "damage" and "divided" in effect
    ]


def division_amount(
    state: GameState,
    controller: int,
    source_oid: int,
    effect: Mapping[str, Any],
    *,
    x: int = 0,
) -> int:
    """The damage to divide, read now -- which is as the spell is cast."""
    ctx = EffectContext(state=state, controller=controller, source_oid=source_oid, x=x)
    return max(0, evaluate_value(ctx, effect.get("amount", 1)))


def division_caps(
    state: GameState, controller: int, source_oid: int, card: CardDef, *, x: int = 0
) -> dict[str, int]:
    """The most targets each divided spec may take: one per point of damage."""
    return {
        str(effect["divided"]): division_amount(state, controller, source_oid, effect, x=x)
        for effect in divided_damage(card)
    }


def fits_division(
    state: GameState,
    controller: int,
    source_oid: int,
    card: CardDef,
    specs: Sequence[TargetSpec],
    targets: Sequence[TargetRef],
    *,
    x: int = 0,
) -> bool:
    """Can every divided spec's declared targets each be dealt at least one?"""
    caps = division_caps(state, controller, source_oid, card, x=x)
    if not caps:
        return True
    declared = declared_by_spec(specs, targets)
    return all(len(declared.get(spec_id, ())) <= cap for spec_id, cap in caps.items())
