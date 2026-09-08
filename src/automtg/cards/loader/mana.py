"""Cost compilation and the mana-ability folding.

A mana ability's output is folded to a fixed tuple at load time (rule 605: it
resolves without the stack and may never stop to ask), which is why the
restriction and rider grammar lives here rather than in the engine.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from automtg.engine.carddef import (
    Cost,
)
from automtg.engine.effects.selectors import validate_selector
from automtg.engine.effects.values import (
    validate_value,
)
from automtg.engine.errors import DslError
from automtg.engine.mana import (
    CHOSEN_TYPE,
    ManaRestriction,
    RestrictionGroup,
    parse_mana_production,
)

from .statics import (
    _validate_cost_reduction,
)
from .vocabulary import (
    MANA_AMOUNT_FORBIDDEN,
    MANA_RIDER_OPS,
)


def _compile_cost(model, where: str, *, defines_x: bool = False) -> Cost:
    if model.x_value is not None:
        # "X is the mana value of that card." Two guards, because both failures
        # are silent: `x_value` is read by `costs.ability_mana`, which prices an
        # *activated ability's* cost and nothing else, and what it fills in is
        # the `{X}` symbol in this cost's own mana.
        if not defines_x:
            raise DslError(
                f"{where}.cost: 'x_value' defines the X of an activated ability's "
                f"cost, and this is not one -- nowhere else prices its mana "
                f"through `ability_mana`, so it would load and be ignored"
            )
        if "X" not in str(model.mana or "").upper():
            raise DslError(
                f"{where}.cost: 'x_value' says what the '{{X}}' in this cost is "
                f"worth, and there is no '{{X}}' in {model.mana!r} for it to fill in"
            )
        validate_value(model.x_value, f"{where}.cost.x_value")
    validate_selector(model.sacrifice, f"{where}.cost.sacrifice")
    validate_selector(model.return_to_hand, f"{where}.cost.return_to_hand")
    validate_selector(model.exile_from_graveyard, f"{where}.cost.exile_from_graveyard")
    validate_selector(model.discard_selector, f"{where}.cost.discard_selector")
    exile_hand = dict(model.exile_from_hand) if model.exile_from_hand is not None else None
    if exile_hand is not None:
        if "zone" in exile_hand:
            # The pool is the payer's own hand and nothing else -- see
            # `costs._hand_exile_pool`, which walks that list directly rather
            # than resolving a zone, because the hand is hidden and an
            # opponent's cards must not become fodder. A `zone` written here
            # would read as a knob that works and be overwritten in silence.
            raise DslError(
                f"{where}.cost.exile_from_hand: 'zone' is implied and may not be "
                f"set; this cost always exiles from the paying player's hand"
            )
        exile_hand.pop("count", None)
        validate_selector(exile_hand, f"{where}.cost.exile_from_hand")
    if model.exile_self_from_hand and model.exile_self:
        # One source, two zones. Whichever `can_pay` checked first would decide
        # where the card had to be, and the other half would be dead text.
        raise DslError(
            f"{where}.cost: give 'exile_self' or 'exile_self_from_hand', not both -- "
            f"they are the same card leaving two different zones"
        )
    if model.exile_self_from_hand and model.discard_self:
        # The same card cannot go to two destinations, and which one it reached
        # is the whole difference between cycling and a pitch.
        raise DslError(f"{where}.cost: give 'discard_self' or 'exile_self_from_hand', not both")
    if model.pay_life_x and model.pay_life:
        # Two numbers for one payment. Whichever won would be the card and the
        # other would load clean and never be charged.
        raise DslError(
            f"{where}.cost: 'pay_life_x' is the announced X, so there is no "
            f"'pay_life' amount to give as well (got {model.pay_life!r})"
        )
    if model.mill < 0:
        raise DslError(
            f"{where}.cost: 'mill' is how many cards go from the top of your "
            f"library to your graveyard, so it cannot be negative (got {model.mill})"
        )
    # `total_power` is crew's, and it is a property of the *cost* rather than a
    # test on any one candidate -- a selector cannot say "these together" -- so
    # it is lifted out before the selector language sees it.
    tap_selector = dict(model.tap_permanents) if model.tap_permanents is not None else None
    total_power = tap_selector.pop("total_power", None) if tap_selector is not None else None
    validate_selector(tap_selector, f"{where}.cost.tap_permanents")
    if total_power is not None:
        if not isinstance(total_power, int) or total_power < 1:
            raise DslError(
                f"{where}.cost.tap_permanents.total_power: crew N is a positive "
                f"integer, got {total_power!r}"
            )
        if "count" in (tap_selector or {}):
            # Two different questions -- "how many" and "how much power" -- and
            # a card giving both would be paid by whichever the code checked
            # first, which is not something the printed line ever says.
            raise DslError(f"{where}.cost.tap_permanents: give 'count' or 'total_power', not both")
    if model.mana_reduction is not None:
        if not model.mana:
            # "Costs {3} less" with no mana half to take it off. Clamped at zero,
            # so it would load clean and do nothing at all.
            raise DslError(f"{where}.cost: 'mana_reduction' needs a 'mana' cost to reduce")
        _validate_cost_reduction(model.mana_reduction, f"{where}.cost.mana_reduction")
    if model.discard_selector is not None and not model.discard:
        raise DslError(f"{where}: 'discard_selector' needs a 'discard' count to narrow")
    if model.tap_permanents is not None and "tapped" in model.tap_permanents:
        # The pool forces `tapped: False` -- "untapped" is part of every printed
        # line of this shape, and a cost that could re-tap something already
        # tapped is free. Spelling it in the card would read as a knob that
        # works, so it is refused rather than overridden in silence.
        raise DslError(
            f"{where}.cost.tap_permanents: 'tapped' is implied and may not be set; "
            f"this cost always taps untapped permanents"
        )
    if model.untap_permanents is not None:
        if "tapped" in model.untap_permanents:
            # The mirror guard, for the mirror reason: the pool forces
            # `tapped: True`, "tapped" is in every printed line of this shape,
            # and a cost that could "untap" an untapped creature costs nothing.
            raise DslError(
                f"{where}.cost.untap_permanents: 'tapped' is implied and may not be "
                f"set; this cost always untaps tapped permanents"
            )
        if "total_power" in model.untap_permanents:
            # Crew is `tap_permanents`', and it is a printed sum -- "total power
            # 3 or greater". Nothing printed unbends a board by power, so this
            # is refused rather than accepted and silently ignored.
            raise DslError(
                f"{where}.cost.untap_permanents: 'total_power' is crew's and belongs "
                f"to 'tap_permanents'; give a 'count'"
            )
        validate_selector(model.untap_permanents, f"{where}.cost.untap_permanents")
    # One constructor for both spellings of a cost -- the model here, and the
    # raw mapping an optional effect's `pay` arrives as.  See `Cost.from_spec`.
    cost = Cost.from_spec(model.model_dump())
    assert cost is not None  # model_dump() is never None
    return cost


#: The five colours, as single-symbol production tuples. The static superset a
#: reflecting mana ability advertises before the board narrows it.
_ANY_COLOR_OPTIONS: tuple[tuple[int, ...], ...] = tuple(
    parse_mana_production(f"{{{sym}}}") for sym in ("W", "U", "B", "R", "G")
)


def _split_mana_rider(
    effects: list[dict[str, Any]], where: str
) -> tuple[list[dict[str, Any]], tuple[Mapping[str, Any], ...]]:
    """``(the mana half, the rider)``.

    The rider is the run of effects after the mana, so the printed order is the
    order they happen in. The mana half must come first and must not be empty:
    an "ability" whose every effect is a rider is not a mana ability at all, and
    accepting one would put an ordinary activated ability inside cost payment.
    """
    split = 0
    for effect in effects:
        op = effect.get("op") if isinstance(effect, Mapping) else None
        if op not in ("add_mana", "choose_mode"):
            break
        split += 1
    mana, rider = effects[:split], effects[split:]
    for i, effect in enumerate(rider):
        op = effect.get("op") if isinstance(effect, Mapping) else None
        if op not in MANA_RIDER_OPS:
            raise DslError(
                f"{where}: mana abilities may only contain 'add_mana' (or a single "
                f"'choose_mode' of them), optionally followed by a rider from "
                f"{sorted(MANA_RIDER_OPS)} -- got {op!r} at effects[{split + i}]"
            )
    return mana, tuple(rider)


def _mana_options(effects: list[dict[str, Any]], where: str) -> tuple[tuple[int, ...], ...]:
    """Flatten a mana ability's effects into every 6-tuple it could produce."""
    if len(effects) == 1 and effects[0].get("op") == "choose_mode":
        options = []
        for mode in effects[0].get("modes", []):
            options.append(_sum_mana(mode.get("effects", []), where))
        if not options:
            raise DslError(f"{where}: modal mana ability has no modes")
        return tuple(options)
    return (_sum_mana(effects, where),)


def _validate_mana_amount(amount: Any, where: str) -> None:
    validate_value(amount, where)
    if isinstance(amount, str) and amount == "x":
        raise DslError(f"{where}: a mana ability has no X to read")
    if not isinstance(amount, Mapping):
        return
    bad = MANA_AMOUNT_FORBIDDEN & set(amount)
    if bad:
        raise DslError(
            f"{where}: a mana ability is activated during payment, with no X, "
            f"targets, bindings or loop -- {sorted(bad)} would always read 0"
        )


def _sum_mana(effects: list[dict[str, Any]], where: str) -> tuple[int, ...]:
    total = [0] * 6
    for effect in effects:
        if effect.get("op") != "add_mana":
            raise DslError(
                f"{where}: mana abilities may only contain 'add_mana' "
                f"(or a single 'choose_mode' of them), got {effect.get('op')!r}"
            )
        if isinstance(effect.get("mana"), Mapping):
            # `{"chosen_color_of": "self"}` is one symbol whose colour is not
            # known at load time, so it cannot be summed with anything and it
            # cannot be one mode among five -- a mode is a choice made at
            # activation, which is the *any colour* card this spelling exists to
            # refuse. It has to be the whole ability, which the branch in
            # `_build_ability` handles before anything reaches here.
            raise DslError(
                f"{where}: a chosen-colour 'add_mana' must be the mana ability's "
                f"only effect -- it cannot be summed with another symbol or "
                f"offered as one mode among several"
            )
        for i, v in enumerate(parse_mana_production(str(effect.get("mana", "")))):
            total[i] += v
    if not any(total):
        raise DslError(f"{where}: mana ability produces no mana")
    return tuple(total)


def _mana_amount(effects: list[dict[str, Any]], where: str) -> Mapping[str, Any] | None:
    """The ``amount`` on a variable mana ability -- "Add {G} for each ...".

    Deliberately narrow. The amount scales *one* symbol tuple, so a card that
    carried one would be ambiguous if it also summed several `add_mana`s or
    offered modes: "for each counter" would have no single thing to multiply.
    One `add_mana`, or no amount at all.
    """
    carriers = [e for e in effects if isinstance(e, Mapping) and "amount" in e]
    if not carriers:
        return None
    if len(effects) != 1:
        raise DslError(
            f"{where}: a mana ability with an 'amount' must be a single 'add_mana' "
            f"-- there is otherwise no one symbol for the amount to scale"
        )
    amount = carriers[0]["amount"]
    _validate_mana_amount(amount, f"{where}.amount")
    return dict(amount) if isinstance(amount, Mapping) else amount


def _mana_restriction(spec: Any, where: str) -> ManaRestriction:
    """ "Spend this mana only to cast …" compiled to a :class:`ManaRestriction`.

    A bare string or list is the **cast** half alone, which is what every card
    printed before Secluded Courtyard says and why the old spelling still means
    exactly what it meant:

    - ``"creature"`` -- one name, Ancient Ziggurat.
    - ``["Vampire", "Cleric", "Demon"]`` -- the printed "and/or", which is an
      any-of: one matching name is enough (Master of Dark Rites).

    An **object** names the halves separately, because the printed sentence
    does: "…only to cast a creature spell of the chosen type **or activate an
    ability of** a creature source of the chosen type" gives them different
    subjects, and a card that says nothing about activating abilities must not
    permit it.

    ```jsonc
    "mana_restriction": {
      "cast":     [["creature", {"chosen_type_of": "self"}]],
      "activate": [["creature", {"chosen_type_of": "self"}]]
    }
    ```

    A nested list is an **all-of**, and this card needs it: "a creature spell
    **of** the chosen type" is a conjunction, and flattening it into the any-of
    above would offer the mana for every creature ever printed -- a strictly
    better card than the printed one.

    ``{"chosen_type_of": "self"}`` is the one entry that is not a literal name.
    It compiles to `mana.CHOSEN_TYPE` and is substituted per permanent by
    `costs.resolve_mana_restriction`, because the type does not exist until the
    permanent is on the battlefield. Spelled the same way `subtypes` filters
    already spell it (Vanquisher's Banner, Door of Destinies) rather than as a
    new key meaning the same thing.
    """
    if isinstance(spec, Mapping):
        unknown = sorted(set(spec) - {"cast", "activate"})
        if unknown:
            raise DslError(
                f"{where}: 'mana_restriction' names {unknown}; mana is only ever spent "
                f"to 'cast' a spell or 'activate' an ability"
            )
        restriction = ManaRestriction(
            cast=_restriction_groups(spec.get("cast"), f"{where}.cast"),
            activate=_restriction_groups(spec.get("activate"), f"{where}.activate"),
        )
        if not restriction.cast and not restriction.activate:
            raise DslError(
                f"{where}: 'mana_restriction' permits nothing at all; omit it for ordinary mana"
            )
        return restriction
    return ManaRestriction(cast=_restriction_groups(spec, where))


def _restriction_groups(spec: Any, where: str) -> tuple[RestrictionGroup, ...]:
    """One half of a restriction: the groups, any of which may be satisfied.

    ``None`` is an omitted half and means "never", which is the whole of how a
    card that says only "to cast" refuses to fund an activation.
    """
    if spec is None:
        return ()
    groups = [spec] if isinstance(spec, str) else list(spec)
    if not groups:
        raise DslError(f"{where}: 'mana_restriction' is empty; omit it for ordinary mana")
    out: list[RestrictionGroup] = []
    for group in groups:
        entries = [group] if isinstance(group, (str, Mapping)) else list(group)
        if not entries:
            raise DslError(
                f"{where}: an empty group in 'mana_restriction' restricts nothing; "
                f"omit it for ordinary mana"
            )
        required: set[str] = set()
        forbidden: set[str] = set()
        for entry in entries:
            if isinstance(entry, Mapping) and "not" in entry:
                if set(entry) != {"not"}:
                    raise DslError(
                        f"{where}: a negated mana restriction takes only 'not', "
                        f"not {dict(entry)!r}"
                    )
                forbidden.add(_restriction_name(entry["not"], where, negated=True))
            else:
                required.add(_restriction_name(entry, where))
        if not required and not forbidden:
            raise DslError(
                f"{where}: an empty group in 'mana_restriction' restricts nothing; "
                f"omit it for ordinary mana"
            )
        # A name on both sides is a group nothing can ever satisfy -- the same
        # permanently-unspendable mana a typo makes, and worth the same refusal.
        if overlap := required & forbidden:
            raise DslError(
                f"{where}: {sorted(overlap)!r} is both required and forbidden in one "
                f"'mana_restriction' group, which nothing can satisfy"
            )
        out.append(RestrictionGroup(frozenset(required), frozenset(forbidden)))
    return tuple(out)


def _restriction_name(entry: Any, where: str, *, negated: bool = False) -> str:
    """One name inside a restriction group: a literal, or the chosen type.

    ``negated`` is the `{"not": …}` half, and it accepts literals only. No card
    prints "spend this only to cast a spell that is *not* the chosen type", and
    the sentinel would have to survive `costs._resolve_groups` for it to mean
    anything -- so it is refused here rather than accepted and half-honoured.
    """
    if negated and isinstance(entry, Mapping):
        raise DslError(
            f"{where}: a negated mana restriction takes a literal type or "
            f"subtype, not {dict(entry)!r}"
        )
    if isinstance(entry, Mapping):
        # Exactly the one dynamic leaf, and validated as such: a near-miss
        # spelling that fell through would freeze into a literal name no card
        # has, producing mana that can never be spent.
        if set(entry) != {"chosen_type_of"} or entry["chosen_type_of"] != "self":
            raise DslError(
                f"{where}: the only dynamic mana restriction is "
                f'{{"chosen_type_of": "self"}}, not {dict(entry)!r}'
            )
        return CHOSEN_TYPE
    # A card type, or a subtype. Subtypes are open-ended in Magic and there is no
    # closed list to check one against, so the guard is the weaker "looks like a
    # word": a typo here produces mana that can never be spent, which is a
    # strictly worse card than the printed one -- the safe direction, but a
    # silent one, so it is worth the shape check.
    if (
        not isinstance(entry, str)
        or not entry
        or not entry.replace("-", "").replace(" ", "").isalpha()
    ):
        raise DslError(
            f"{where}: unparsable mana restriction {entry!r} (a card type or subtype, lowercased)"
        )
    return entry.lower()
