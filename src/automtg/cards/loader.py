"""Compile validated card JSON into immutable engine objects.

Validation happens in three passes:

1. **Shape** -- pydantic models in :mod:`automtg.cards.schema`.
2. **Vocabulary** -- every effect op, selector key, value form, trigger event,
   keyword and type name must be one the engine actually implements.
3. **Constraints** -- static ability filters may only read printed
   characteristics (see :mod:`automtg.engine.characteristics`), and abilities
   flagged as mana abilities must really be mana abilities.

Anything that fails raises :class:`~automtg.engine.errors.DslError` at load time.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from automtg.engine.carddef import Ability, CardDef, Cost, TargetSpec, TriggerSpec, build_type_line
from automtg.engine.effects import known_ops
from automtg.engine.effects.conditions import validate_condition
from automtg.engine.effects.ops_cards import DESTINATIONS, SEARCHABLE
from automtg.engine.effects.selectors import validate_selector
from automtg.engine.effects.values import validate_mana_symbols, validate_value
from automtg.engine.enums import AbilityKind, CardType, Color, Keyword, Supertype, Zone
from automtg.engine.errors import DslError
from automtg.engine.mana import ManaCost, parse_mana_production
from automtg.engine.triggers import TRIGGER_EVENTS
from automtg.engine.turn import DELAY_STEPS

from .schema import AbilityModel, CardModel, CostModel, DeckModel, TargetModel

KNOWN_TYPES = frozenset(t.value for t in CardType)
KNOWN_SUPERTYPES = frozenset(s.value for s in Supertype)
KNOWN_KEYWORDS = frozenset(k.value for k in Keyword)
KNOWN_COLORS = frozenset(c.value for c in Color)

#: Static ability effects the characteristics pipeline understands.
STATIC_EFFECTS = frozenset(
    {
        "buff",
        "grant_keyword",
        "set_pt",
        "add_subtype",
        # "As long as Arixmethes has a slumber counter on it, it's a land."
        # Replaces the printed types rather than adding to them, which is the
        # whole point: the parenthetical says "it's not a creature".
        "set_types",
        "extra_land_drops",
        # Player-wide, like `extra_land_drops`: a fact about the player rather
        # than a characteristic, with no object for it to attach to.
        "no_hand_limit",
        "play_lands_from_graveyard",
        "play_lands_from_library_top",
        # "Play with the top card of your library revealed." Player-wide, and
        # the only static here that changes nothing about the rules: it grants
        # no permission and moves no card, it makes one card public. Read by
        # `serialize`, and by nothing else.
        "reveal_library_top",
        # Parameterised, so it cannot be a keyword: "protection from Wizards"
        # names a quality, and four separate rules (damage, enchant/equip,
        # block, target) ask about it.
        "protection",
        # Ancient Greenwarden.  A fact about the *player*, like the two above:
        # it is read by `triggers.collect` rather than by the characteristics
        # pipeline, and there is no object for it to attach to.
        "double_land_triggers",
        # Vorinclex's two halves.  Both are read at the mana choke point rather
        # than as triggers, because tapping for mana happens inside payment
        # where nothing can go on the stack.
        "double_land_mana",
        "freeze_opponent_lands",
        # "This creature can't be blocked by Humans", and Tromokratis'
        # "can't be blocked unless all creatures defending player controls
        # block it".  Read by `combat`, not by the characteristics pipeline.
        "block_restriction",
        # Murkfiend Liege.  Read by `turn._untap_step`, not by the
        # characteristics pipeline: it is a fact about when a set of
        # permanents untaps, which no characteristic can carry.
        "untap_during_each_untap_step",
        # Stormtide Leviathan.  Read by `combat.can_attack`.  A global
        # prohibition, so unlike every other static here its `affects`
        # routinely names creatures its own controller does not control.
        "cant_attack",
        # Unleash, and the "can't block" printed on aggressive commons. The
        # mirror of `cant_attack`, read by `combat.can_block`, and a static
        # rather than a keyword for the same reason `block_restriction` is: a
        # keyword is a characteristic and this is a permission.
        "cant_block",
        # Marauding Maulhorn.  The obligation to `cant_attack`'s prohibition,
        # read by `combat.attack_required` at the same enforcement point the
        # `must_attack` op uses.  A static rather than that op because a
        # printed "attacks each combat if able" is true again every turn, where
        # the op writes a one-shot flag that is spent on declaration.
        "attacks_if_able",
        # Warden of Evos Isle.  Read by `costs.cost_reduction`, not by the
        # characteristics pipeline: it prices a card that is still in hand, so
        # its filter (`affects_spells`) matches a printed face rather than a
        # permanent, and is a different list from `affects`.
        "spell_cost_reduction",
    }
)

#: Keys a ``spell_cost_reduction`` static's ``affects_spells`` filter may use.
#:
#: Deliberately not `STATIC_FILTER_KEYS`: that list describes *permanents* and
#: carries board state (`tapped`, `attacking`, `attached`) which a card in hand
#: does not have.  These are the printed face plus who is casting it, which is
#: all `characteristics._matches_printed` reads.
SPELL_FILTER_KEYS = frozenset(
    {
        "controller",
        "types",
        "not_types",
        "subtypes",
        "supertypes",
        "colors",
        "keywords",
        "not_keywords",
        "name",
    }
)

#: Keys a *static* ability's filter may use.  Deliberately smaller than the full
#: selector language: static filters are matched against printed characteristics
#: so that no static can depend on another static's output.
STATIC_FILTER_KEYS = frozenset(
    {
        "exclude_self",
        "self_only",
        "controller",
        "types",
        "not_types",
        "subtypes",
        "supertypes",
        "colors",
        "keywords",
        # "Creatures **without** flying or islandwalk can't attack."  The
        # negated form, which the effect-side selector language always had
        # and the static one did not.
        "not_keywords",
        "tapped",
        "is_commander",
        "is_token",
        "attacking",
        "blocking",
        # "Enchanted creature gets +2/+2".  Reads `attached_to`, which is board
        # state rather than a derived characteristic, so it cannot depend on
        # another static's output and belongs in this list rather than outside it.
        "attached",
    }
)


# ----------------------------------------------------------------------
# public API
# ----------------------------------------------------------------------


def load_cards(paths: Iterable[Path]) -> dict[str, CardDef]:
    """Load every card file into a ``{card_id: CardDef}`` mapping."""
    cards: dict[str, CardDef] = {}
    for path in paths:
        for card in load_card_file(path):
            if card.id in cards:
                raise DslError(f"duplicate card id {card.id!r} (second definition in {path})")
            cards[card.id] = card
    return cards


def load_card_file(path: Path) -> list[CardDef]:
    """Load one ``*.cards.json`` file."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = raw["cards"] if isinstance(raw, dict) else raw
    out: list[CardDef] = []
    for entry in entries:
        try:
            model = CardModel.model_validate(entry)
        except Exception as exc:  # pydantic ValidationError
            name = entry.get("id", entry.get("name", "<unknown>")) if isinstance(entry, dict) else "?"
            raise DslError(f"{path.name}: card {name!r} failed validation: {exc}") from exc
        out.append(compile_card(model, source=path.name))
    return out


def load_deck_file(path: Path) -> DeckModel:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        return DeckModel.model_validate(raw)
    except Exception as exc:
        raise DslError(f"{Path(path).name}: deck failed validation: {exc}") from exc


# ----------------------------------------------------------------------
# compilation
# ----------------------------------------------------------------------


def compile_card(model: CardModel, *, source: str = "") -> CardDef:
    where = f"{source}:{model.id}" if source else model.id

    for t in model.types:
        if t not in KNOWN_TYPES:
            raise DslError(f"{where}: unknown card type {t!r}")
    for s in model.supertypes:
        if s not in KNOWN_SUPERTYPES:
            raise DslError(f"{where}: unknown supertype {s!r}")
    for k in model.keywords:
        if k not in KNOWN_KEYWORDS:
            raise DslError(f"{where}: unknown keyword {k!r} (implemented: {sorted(KNOWN_KEYWORDS)})")

    mana_cost = ManaCost.parse(model.mana_cost)
    kicker = ManaCost.parse(model.kicker) if model.kicker else None
    if kicker is not None:
        if kicker.x_count:
            raise DslError(f"{where}: a kicker cost with X is not implemented")
        if kicker.mana_value() == 0:
            raise DslError(f"{where}: kicker {model.kicker!r} costs nothing")

    if CardType.CREATURE.value in model.types and (model.power is None or model.toughness is None):
        raise DslError(f"{where}: creatures need power and toughness")

    targets = tuple(_compile_target(t, where) for t in model.targets)
    target_ids = {t.id for t in targets}
    for i, effect in enumerate(model.spell_effects):
        _validate_effect(effect, f"{where}.spell_effects[{i}]", target_ids)

    abilities = tuple(
        _compile_ability(a, i, where) for i, a in enumerate(model.abilities)
    )
    grantable = tuple(
        _compile_ability(a, i, f"{where}.grantable")
        for i, a in enumerate(model.grantable_abilities)
    )
    for ability in grantable:
        if not ability.is_triggered:
            # Only triggered abilities can be granted so far. A granted *static*
            # would have to join the characteristics pipeline from an object
            # that is not its source, and a granted *activated* one would need
            # `Action` to carry where it came from before legality could offer
            # it -- so it would be accepted here and then never appear, which is
            # the exact "looks implemented, does nothing" failure this pass
            # exists to refuse. Granting a keyword is what `grant_keyword` is
            # for; `docs/rules-coverage.md` records the rest as not implemented.
            raise DslError(
                f"{where}: only triggered abilities can be granted, not {ability.kind.value}"
            )

    if model.cost_reduction is not None:
        _validate_cost_reduction(model.cost_reduction, f"{where}.cost_reduction")

    suspend = None
    if model.suspend is not None:
        unknown = set(model.suspend) - {"cost", "counters"}
        if unknown:
            raise DslError(f"{where}.suspend: unsupported keys {sorted(unknown)}")
        counters = int(model.suspend.get("counters", 0))
        if counters < 1:
            # Suspend 0 would resolve on the upkeep it was suspended, which is
            # not what any printed card says and would hide a typo.
            raise DslError(f"{where}.suspend: 'counters' must be at least 1")
        suspend = (ManaCost.parse(model.suspend.get("cost")), counters)

    # Kicker is two halves that only mean anything together: the extra cost, and
    # an `if` that reads it.  Half a kicker is the failure this pass exists to
    # catch -- a spell that charges more and does the same thing, or one whose
    # kicked clause can never fire, and nothing on the board would say so.
    # `buyback` reads it too, and not through an effect: the rider in
    # `_place_after_resolution` is what the extra mana buys, so a buyback card
    # has no `kicked` clause anywhere in its effects and is not half a kicker.
    reads_kicked = _mentions_kicked(model) or model.buyback
    if _mentions_kicked(model) and kicker is None:
        raise DslError(f"{where}: reads the 'kicked' condition but has no 'kicker' cost")
    if kicker is not None and not reads_kicked:
        raise DslError(f"{where}: has a 'kicker' cost that no effect reads via 'kicked'")

    # Evoke is two halves the same way, and half of it is the same silent
    # failure: a cheaper cast that never dies, or a sacrifice clause that can
    # never fire.  Both would load cleanly.
    evoke = ManaCost.parse(model.evoke) if model.evoke else None
    emerge = ManaCost.parse(model.emerge) if model.emerge else None
    if emerge is not None and evoke is not None:
        # Checked before either half-a-cost guard below, because a card
        # carrying both trips those first and the message would name the
        # wrong problem.
        raise DslError(f"{where}: a card may not have both 'evoke' and 'emerge'")
    if evoke is not None and evoke.x_count:
        raise DslError(f"{where}: an evoke cost with X is not implemented")
    reads_evoked = _mentions_condition(model, "evoked")
    if reads_evoked and evoke is None:
        raise DslError(f"{where}: reads the 'evoked' condition but has no 'evoke' cost")
    if evoke is not None and not reads_evoked:
        raise DslError(f"{where}: has an 'evoke' cost that no effect reads via 'evoked'")
    if emerge is not None and emerge.x_count:
        raise DslError(f"{where}: an emerge cost with X is not implemented")
    if evoke is not None and evoke.mana_value() >= mana_cost.mana_value():
        # An "alternative" cost no cheaper than the printed one is never taken,
        # so the whole mechanic would be dead weight nobody would notice.
        raise DslError(
            f"{where}: evoke {model.evoke!r} is not cheaper than the printed cost"
        )

    if model.buyback and model.kicker is None:
        # Buyback *is* a kicker with a rider. Without the cost there is nothing
        # to pay and the rider never fires, so the card reads "buyback" and
        # goes to the graveyard like anything else.
        raise DslError(f"{where}: 'buyback' needs a 'kicker' cost to attach to")
    if model.emerge_subtype is not None and model.emerge is None:
        # A narrowing with nothing to narrow. The card would look like an
        # offering card and have no alternative cast line at all.
        raise DslError(
            f"{where}: 'emerge_subtype' needs an 'emerge' cost to narrow"
        )
    alternative_cost = None
    alternative_condition = None
    if model.alternative_cost is not None:
        spec = dict(model.alternative_cost)
        unknown = set(spec) - {"mana", "condition"}
        if unknown:
            raise DslError(
                f"{where}.alternative_cost: unsupported keys {sorted(unknown)}"
            )
        if not spec.get("mana"):
            # It *replaces* the printed cost, so without mana the card would be
            # castable for free whenever the condition happened to hold.
            raise DslError(f"{where}.alternative_cost: needs 'mana'")
        alternative_cost = ManaCost.parse(str(spec["mana"]))
        alternative_condition = spec.get("condition")
        if alternative_condition is None:
            # Unconditional is what `evoke` already is. A card spelling it this
            # way would be offered twice at two prices with nothing to choose
            # between them.
            raise DslError(
                f"{where}.alternative_cost: needs a 'condition' -- an "
                f"unconditional alternative cost is 'evoke'"
            )
        validate_condition(alternative_condition, f"{where}.alternative_cost.condition")

    # `flashback` and `graveyard_cost` are one slot under two names -- the
    # keyword that shipped first, and the mechanic it turned out to be. Escape
    # and jump-start are the same capability with a different price and a
    # different destination, and neither should have to say "flashback".
    if model.flashback is not None and model.graveyard_cost is not None:
        raise DslError(
            f"{where}: give 'graveyard_cost' or 'flashback', not both -- they are "
            f"the same field, and a card with two prices from the graveyard has "
            f"no answer to what it costs from there"
        )
    graveyard_spec = model.graveyard_cost or model.flashback
    flashback = Cost.from_spec(graveyard_spec.model_dump()) if graveyard_spec else None
    if flashback is not None:
        if not flashback.mana.text:
            # The mana half *replaces* the printed cost, so without it the card
            # would be castable from the graveyard for free.
            raise DslError(f"{where}: a graveyard cost needs mana")
        if flashback.mana.x_count:
            raise DslError(f"{where}: a graveyard cost with X is not implemented")
        if model.retrace:
            # Both widen legality to the graveyard and each replaces the other's
            # answer to "what does it cost from there".
            raise DslError(
                f"{where}: a card may not have both a graveyard cost and 'retrace'"
            )
    if graveyard_spec is None and model.graveyard_cast != "exile":
        # A destination with nothing to send there. Silently ignoring it would
        # let a card claim to be an escape card and never be castable at all.
        raise DslError(
            f"{where}: 'graveyard_cast' needs a 'graveyard_cost' to describe"
        )
    # Clash is two halves the same way kicker is, and half of it fails just as
    # silently. Every printed clash card reads "Clash with an opponent. If you
    # win, …", so a `clash` nothing reads is a spell that reveals two cards and
    # does nothing, and a `clash_won` binding with no clash behind it is a
    # clause that reads 0 and can never fire. Both load cleanly.
    clashes = _mentions_pair(model, "op", "clash")
    reads_clash = _mentions_pair(model, "binding", "clash_won")
    if clashes and not reads_clash:
        raise DslError(
            f"{where}: has a 'clash' that no effect reads via "
            f"{{'binding': 'clash_won'}} -- a clash nobody wins is not a card"
        )
    if reads_clash and not clashes:
        raise DslError(
            f"{where}: reads the 'clash_won' binding but never clashes, so it "
            f"would always read 0"
        )

    reads_from_graveyard = _mentions_condition(model, "cast_from_graveyard")
    if reads_from_graveyard and flashback is None:
        raise DslError(
            f"{where}: reads the 'cast_from_graveyard' condition but has no "
            f"'graveyard_cost', so it could never be true"
        )

    colors = (
        frozenset(model.colors)
        if model.colors is not None
        else frozenset(c.value for c in mana_cost.colors)
    )
    for c in colors:
        if c not in KNOWN_COLORS:
            raise DslError(f"{where}: unknown color {c!r}")

    identity = (
        frozenset(model.color_identity)
        if model.color_identity is not None
        else _derive_color_identity(colors, mana_cost, abilities)
    )

    supertypes = frozenset(model.supertypes)
    types = frozenset(model.types)
    subtypes = frozenset(model.subtypes)

    return CardDef(
        id=model.id,
        name=model.name,
        oracle_text=model.oracle_text,
        mana_cost=mana_cost,
        supertypes=supertypes,
        types=types,
        subtypes=subtypes,
        power=model.power,
        toughness=model.toughness,
        keywords=frozenset(model.keywords),
        colors=colors,
        color_identity=identity,
        targets=targets,
        spell_effects=tuple(model.spell_effects),
        replacements=tuple(r.model_dump() for r in model.replacements),
        abilities=abilities,
        grantable_abilities=grantable,
        type_line=build_type_line(supertypes, types, subtypes),
        is_token=model.is_token,
        back_face=model.back_face,
        uncounterable=model.uncounterable,
        split_second=model.split_second,
        buyback=model.buyback,
        kicker_label=model.kicker_label,
        kicker=kicker,
        evoke=evoke,
        emerge=emerge,
        cost_reduction=dict(model.cost_reduction) if model.cost_reduction else None,
        retrace=model.retrace,
        flashback=flashback,
        evoke_label=model.evoke_label,
        pay_generic_with=model.pay_generic_with,
        emerge_subtype=model.emerge_subtype,
        alternative_cost=alternative_cost,
        alternative_condition=alternative_condition,
        graveyard_cast_exiles=model.graveyard_cast == "exile",
        ascend=model.ascend,
        suspend=suspend,
    )


def _mentions_kicked(model: CardModel) -> bool:
    """Does anything on this card read ``{"kicked": ...}``?"""
    return _mentions_condition(model, "kicked")


def _mentions_condition(model: CardModel, key: str) -> bool:
    """Does anything on this card read the ``key`` condition?"""
    return _mentions(model, lambda node: key in node)


def _mentions_pair(model: CardModel, key: str, value: str) -> bool:
    """Does anything on this card carry ``{key: value}``?

    The ``key in node`` test `_mentions_condition` uses is too coarse for
    ``{"op": "clash"}`` and ``{"binding": "clash_won"}`` — every effect has an
    ``op`` and dozens have a ``binding``, so the key alone matches everything.
    """
    return _mentions(model, lambda node: node.get(key) == value)


def _mentions(model: CardModel, predicate: Any) -> bool:
    def walk(node: Any) -> bool:
        if isinstance(node, Mapping):
            return bool(predicate(node)) or any(walk(v) for v in node.values())
        if isinstance(node, (list, tuple)):
            return any(walk(v) for v in node)
        return False

    if walk(model.spell_effects):
        return True
    return any(
        walk(a.effects) or walk(a.trigger.condition if a.trigger else None)
        for a in model.abilities
    )


def _compile_target(model: TargetModel, where: str) -> TargetSpec:
    validate_selector(model.selector, f"{where}.target[{model.id}]")
    return TargetSpec(
        id=model.id,
        kind=model.kind,
        selector=dict(model.selector),
        count=model.count,
        optional=model.optional,
    )


def _compile_ability(model: AbilityModel, index: int, card_where: str) -> Ability:
    where = f"{card_where}.abilities[{index}]"
    kind = AbilityKind(model.kind)

    if kind is AbilityKind.STATIC:
        return _compile_static(model, index, where)

    targets = tuple(_compile_target(t, where) for t in model.targets)
    target_ids = {t.id for t in targets}
    for i, effect in enumerate(model.effects):
        _validate_effect(effect, f"{where}.effects[{i}]", target_ids)

    cost = _compile_cost(model.cost, where) if model.cost else None
    trigger = None
    active_zones: tuple[Zone, ...] = (Zone.BATTLEFIELD,)

    if kind is AbilityKind.ACTIVATED:
        if cost is None:
            raise DslError(f"{where}: activated abilities need a cost")
        if model.condition is not None:
            # "Activate only if you control five or more Vampires." The full
            # condition language, not the static one: nothing is being computed
            # here that another condition could come to depend on, so the
            # narrowing that protects the characteristics pipeline buys nothing.
            validate_condition(model.condition, f"{where}.condition")
        active_zones = tuple(Zone(z) for z in model.active_zones)
        # Cycling is an ability you activate *from your hand*, so the zone list
        # has to be read here as well as on the triggered branch -- it was
        # pinned to the battlefield, which silently dropped the schema's own
        # "hand" value.
        #
        # Anywhere but the battlefield, the cost must also *remove the source
        # from that zone*, or the ability is an infinite engine: a card sitting
        # in hand whose ability only costs mana could be activated again and
        # again without ever leaving. Cycling pays for itself by discarding
        # itself, which is exactly the property that makes it safe and is why
        # the two arrived together.
        if model.is_cycling and not cost.discard_self:
            # Rule 702.29: cycling *is* "Discard this card:". Without the
            # discard the `cycle` event would fire for an ability that never
            # cycled anything, and Krosan Tusker would fetch a land every time.
            raise DslError(
                f"{where}: 'is_cycling' needs a cost that discards this card "
                f"(got {cost.describe()!r})"
            )
        # Two costs remove the source from a non-battlefield zone: cycling
        # discards this card from hand, embalm exiles it from the graveyard.
        # Either satisfies the rule; neither is optional.
        removes_source = cost.discard_self or cost.exile_from_graveyard is not None
        if set(active_zones) - {Zone.BATTLEFIELD} and not removes_source:
            raise DslError(
                f"{where}: an activated ability outside the battlefield needs a cost "
                f"that removes its source from that zone (got {cost.describe()!r}); "
                f"otherwise it can be activated repeatedly without ever leaving"
            )
    else:
        if model.trigger is None:
            raise DslError(f"{where}: triggered abilities need a trigger")
        if model.trigger.event not in TRIGGER_EVENTS:
            raise DslError(
                f"{where}: unknown trigger event {model.trigger.event!r} "
                f"(implemented: {sorted(TRIGGER_EVENTS)})"
            )
        validate_selector(model.trigger.filter, f"{where}.trigger.filter")
        validate_condition(model.trigger.condition, f"{where}.trigger.condition")
        if model.trigger.defending is not None and model.trigger.event != "attacks":
            # Silently ignoring it would produce a card that looks like it reads
            # "attacks you" and fires on everything.
            raise DslError(
                f"{where}: 'defending' only means anything on an 'attacks' trigger, "
                f"not on {model.trigger.event!r}"
            )
        # `self_enters` and `permanent_enters` are the same engine event, and
        # what separates them is `source: "self"`. Omitting it on `self_enters`
        # therefore produced a card that fired on *every* permanent entering --
        # silently, and only visibly wrong once a second permanent showed up.
        # The name can only mean one thing, so the loader makes it mean it.
        source = model.trigger.source
        if model.trigger.event == "self_enters":
            source = "self"

        if model.trigger.not_cause is not None and model.trigger.event not in (
            "self_enters",
            "permanent_enters",
        ):
            # Only zone changes carry a cause. Accepting it elsewhere would look
            # like a guard and be one that never fires.
            raise DslError(
                f"{where}: 'not_cause' only means anything on an enters trigger, "
                f"not on {model.trigger.event!r}"
            )

        if model.trigger.counter is not None and model.trigger.event != "counter_placed":
            # Same reasoning as `not_cause` above: only `counter_placed` carries
            # a counter kind, so accepting it elsewhere would look like a filter
            # and be one that never applies.
            raise DslError(
                f"{where}: 'counter' only means anything on a counter_placed trigger, "
                f"not on {model.trigger.event!r}"
            )

        trigger = TriggerSpec(
            event=model.trigger.event,
            controller=model.trigger.controller,
            source=source,
            filter=dict(model.trigger.filter) if model.trigger.filter else None,
            condition=dict(model.trigger.condition) if model.trigger.condition else None,
            defending=model.trigger.defending,
            not_cause=model.trigger.not_cause,
            counter=model.trigger.counter,
        )
        active_zones = tuple(Zone(z) for z in model.active_zones)

    mana_options: tuple[tuple[int, ...], ...] = ()
    mana_amount: Mapping[str, Any] | None = None
    if model.is_mana_ability:
        if kind is not AbilityKind.ACTIVATED:
            raise DslError(f"{where}: only activated abilities can be mana abilities")
        if targets:
            raise DslError(f"{where}: a mana ability cannot have targets")
        mana_options = _mana_options(model.effects, where)
        mana_amount = _mana_amount(model.effects, where)
    if model.mana_restriction is not None:
        if not model.is_mana_ability:
            raise DslError(f"{where}: 'mana_restriction' needs 'is_mana_ability'")
        if model.mana_restriction.title() not in KNOWN_TYPES:
            raise DslError(
                f"{where}: unknown mana restriction {model.mana_restriction!r} "
                f"(a card type, lowercased)"
            )

    return Ability(
        kind=kind,
        index=index,
        text=model.text,
        cost=cost,
        is_mana_ability=model.is_mana_ability,
        mana_options=mana_options,
        mana_amount=mana_amount,
        mana_restriction=model.mana_restriction,
        sorcery_speed_only=model.sorcery_speed_only,
        activation_condition=(
            dict(model.condition) if kind is AbilityKind.ACTIVATED and model.condition else None
        ),
        is_cycling=model.is_cycling,
        trigger=trigger,
        active_zones=active_zones,
        targets=targets,
        effects=tuple(model.effects),
        static=None,
    )


def _compile_static(model: AbilityModel, index: int, where: str) -> Ability:
    if model.effect is None:
        raise DslError(f"{where}: static abilities need an 'effect' name")
    if model.effect not in STATIC_EFFECTS:
        raise DslError(
            f"{where}: unknown static effect {model.effect!r} (implemented: {sorted(STATIC_EFFECTS)})"
        )
    if model.effects:
        raise DslError(f"{where}: static abilities cannot have 'effects'")

    if model.affects is not None:
        unknown = set(model.affects) - STATIC_FILTER_KEYS
        if unknown:
            raise DslError(
                f"{where}: static filters may only read printed characteristics; "
                f"unsupported keys {sorted(unknown)}"
            )
    if model.effect == "block_restriction":
        # Exactly one of the two forms, because they are evaluated at different
        # moments and a static carrying neither is an evasion ability that
        # evades nothing -- which loads clean and shows nothing on the board.
        if (model.blockers is None) == (not model.require_all):
            raise DslError(
                f"{where}: block_restriction needs exactly one of 'blockers' "
                f"(a filter on the would-be blocker) or 'require_all'"
            )
        if model.blockers is not None:
            unknown = set(model.blockers) - STATIC_FILTER_KEYS
            if unknown:
                raise DslError(
                    f"{where}: block_restriction 'blockers' may only read printed "
                    f"characteristics; unsupported keys {sorted(unknown)}"
                )
    elif model.blockers is not None or model.require_all:
        raise DslError(
            f"{where}: 'blockers'/'require_all' only mean anything on a "
            f"block_restriction static, not on {model.effect!r}"
        )
    if model.effect == "spell_cost_reduction":
        # `affects_spells`, not `affects`: this filter is matched against a card
        # in hand while legality prices it, so it may only read the printed
        # face. A static that reduced nothing would load clean and show
        # nothing, so both halves are required.
        if model.affects is not None:
            raise DslError(
                f"{where}: spell_cost_reduction filters spells with "
                f"'affects_spells', not 'affects' (which picks out permanents)"
            )
        if model.affects_spells is None:
            raise DslError(f"{where}: spell_cost_reduction needs 'affects_spells'")
        unknown = set(model.affects_spells) - SPELL_FILTER_KEYS
        if unknown:
            raise DslError(
                f"{where}.affects_spells: a spell has a printed face and a caster "
                f"and no board state; unsupported keys {sorted(unknown)}"
            )
        if model.amount is None:
            raise DslError(
                f"{where}: spell_cost_reduction needs an 'amount' -- a reduction "
                f"of nothing is not a card"
            )
        _validate_static_value(model.amount, f"{where}.amount")
    elif model.affects_spells is not None:
        raise DslError(
            f"{where}: 'affects_spells' only means anything on a "
            f"spell_cost_reduction static, not on {model.effect!r}"
        )
    if model.effect in (
        "extra_land_drops",
        "no_hand_limit",
        "play_lands_from_graveyard",
        "play_lands_from_library_top",
        "reveal_library_top",
        "double_land_triggers",
        "double_land_mana",
        "freeze_opponent_lands",
    ):
        if model.affects_player is None:
            raise DslError(f"{where}: {model.effect} needs 'affects_player'")
    elif model.effect == "spell_cost_reduction":
        # Picks out *spells*, through `affects_spells`, checked above. There are
        # no permanents for `affects` to name.
        pass
    elif model.affects is None:
        raise DslError(f"{where}: static effect {model.effect!r} needs 'affects'")

    for field_name in ("power", "toughness", "amount"):
        value = getattr(model, field_name)
        if value is not None:
            _validate_static_value(value, f"{where}.{field_name}")

    for k in model.keywords:
        if k not in KNOWN_KEYWORDS:
            raise DslError(f"{where}: unknown keyword {k!r}")

    if model.effect == "set_types" and not model.types:
        raise DslError(f"{where}: set_types needs the types it sets")

    qualities = [*model.from_types, *model.from_subtypes, *model.from_colors]
    if model.effect == "protection":
        # A protection static that names nothing protects from nothing -- a card
        # that looks implemented and is not, which is the one failure this pass
        # exists to stop.
        if not qualities:
            raise DslError(f"{where}: protection needs from_types/from_subtypes/from_colors")
        for t in model.from_types:
            if t not in KNOWN_TYPES:
                raise DslError(f"{where}: unknown type {t!r} in from_types")
        for c in model.from_colors:
            if c not in KNOWN_COLORS:
                raise DslError(f"{where}: unknown color {c!r} in from_colors")
    elif qualities:
        raise DslError(f"{where}: from_types/from_subtypes/from_colors need effect 'protection'")

    _validate_static_condition(model.condition, f"{where}.condition")

    static: dict[str, Any] = {"effect": model.effect}
    if model.condition is not None:
        static["condition"] = dict(model.condition)
    if model.affects is not None:
        static["affects"] = dict(model.affects)
    if model.affects_spells is not None:
        static["affects_spells"] = dict(model.affects_spells)
    if model.affects_player is not None:
        static["affects_player"] = model.affects_player
    for field_name in ("power", "toughness", "amount"):
        value = getattr(model, field_name)
        if value is not None:
            static[field_name] = value
    if model.keywords:
        static["keywords"] = list(model.keywords)
    if model.subtypes:
        static["subtypes"] = list(model.subtypes)
    if model.types:
        static["types"] = list(model.types)
    for field_name in ("from_types", "from_subtypes", "from_colors"):
        value = getattr(model, field_name)
        if value:
            static[field_name] = list(value)
    if model.blockers is not None:
        static["blockers"] = dict(model.blockers)
    if model.require_all:
        static["require_all"] = True

    return Ability(kind=AbilityKind.STATIC, index=index, text=model.text, static=static)


#: Ways a card may say how much less it costs.  ``count`` is "{1} less for each
#: X"; ``total_power`` is Ghalta's "the total power of creatures you control".
COST_REDUCTION_KEYS = frozenset({"count", "total_power"})


def _validate_cost_reduction(spec: Any, where: str) -> None:
    if not isinstance(spec, Mapping) or len(spec) != 1:
        raise DslError(f"{where}: must name exactly one of {sorted(COST_REDUCTION_KEYS)}")
    key = next(iter(spec))
    if key not in COST_REDUCTION_KEYS:
        raise DslError(f"{where}: unknown reduction {key!r} (implemented: {sorted(COST_REDUCTION_KEYS)})")
    unknown = set(spec[key]) - STATIC_FILTER_KEYS
    if unknown:
        # Same restriction as a static filter, for the same reason: this is
        # evaluated while deciding what is castable, before anything is on the
        # stack, so it may only read printed characteristics of the board.
        raise DslError(f"{where}.{key}: unsupported filter keys {sorted(unknown)}")


#: Comparisons a static's "as long as..." clause may use.
STATIC_CONDITION_OPS = frozenset({">=", "<=", ">", "<", "=", "==", "!="})

#: The forms a static's condition may take, one per node.
STATIC_CONDITION_HEADS = (
    "counters", "all", "any", "not", "exists", "is_your_turn",
    "has_city_s_blessing", "cmp",
    # "Attached permanents with reconfigure aren't creatures" (702.151d).
    # `attached_to` is a field the `attach` primitive writes, so it is a
    # pipeline input like a counter and no layer can change it. Distinct from
    # the `attached` *filter* key, which points the other way -- at the
    # permanent this one is attached to.
    "is_attached",
    # "As long as the top card of your library is black". A pipeline *input*
    # for the same reason a zone count is -- nothing in the characteristics
    # pipeline can change what is on top of a library -- but a strictly
    # sharper question than `exists` over the library, which asks whether any
    # black card is anywhere in ninety-nine and is nearly always true.
    "top_of_library",
)

#: Zones a static's *counting* filter may name.  The stack is absent: a static
#: is read while the pipeline computes characteristics, including for objects
#: that are themselves resolving, and "how many spells are on the stack" would
#: change under a card mid-resolution.
STATIC_COUNT_ZONES = frozenset({"battlefield", "graveyard", "hand", "exile", "library", "command"})

#: Keys a static's *counting* filter may use -- the selection keys, plus the
#: zone.  ``affects`` and ``blockers`` deliberately do not get ``zone``: they
#: pick out permanents the static applies to, and there are no permanents
#: outside the battlefield, so a zone there would load and match nothing.
#: ``name`` is here and deliberately *not* in ``STATIC_FILTER_KEYS``. "…unless
#: you control a creature named Advocate of the Beast" is a question the
#: condition asks about the board; "each creature named X gets +1/+1" is not a
#: card, so `affects` has no use for it and allowing it there would only invite
#: one.
STATIC_COUNT_FILTER_KEYS = STATIC_FILTER_KEYS | {"zone", "name"}

#: ...and once it names a zone other than the battlefield, only these.  A card
#: in a graveyard has a printed face and an owner; it is not tapped, attacking,
#: attached to anything or a token, so those keys are refused here rather than
#: loading and silently matching nothing.
STATIC_ZONE_FILTER_KEYS = frozenset(
    {
        "zone",
        "controller",
        # A card in a graveyard has no board state, but it does have a name.
        "name",
        "types",
        "not_types",
        "subtypes",
        "supertypes",
        "colors",
        "keywords",
        "not_keywords",
    }
)


def _validate_static_count_filter(spec: Any, where: str) -> None:
    """A filter in a *counting* position -- ``{"count": ...}`` or ``exists``."""
    if not isinstance(spec, Mapping):
        raise DslError(f"{where}: must be an object")
    zone = str(spec.get("zone", "battlefield"))
    if zone not in STATIC_COUNT_ZONES:
        raise DslError(f"{where}.zone: unknown zone {zone!r} (countable: {sorted(STATIC_COUNT_ZONES)})")
    if zone == "battlefield":
        unknown = set(spec) - STATIC_COUNT_FILTER_KEYS
        if unknown:
            raise DslError(f"{where}: unsupported filter keys {sorted(unknown)}")
        return
    unknown = set(spec) - STATIC_ZONE_FILTER_KEYS
    if unknown:
        raise DslError(
            f"{where}: a card in {zone} has a printed face and an owner and nothing else; "
            f"unsupported keys {sorted(unknown)}"
        )
    controller = spec.get("controller", "you")
    if controller not in ("you", "opponent", "any"):
        raise DslError(f"{where}.controller: must be 'you', 'opponent' or 'any', got {controller!r}")


def _validate_static_condition(condition: Any, where: str) -> None:
    """A static may ask about pipeline *inputs* only.

    Much smaller than the ``if``-effect condition language, and for the same
    reason ``affects`` filters are: anything that reads a *derived*
    characteristic would let one static depend on another's output, and the
    fixed-order pipeline has no way to resolve that.  Counters on the source,
    printed characteristics of the board, the contents of a zone and whose turn
    it is are all inputs, so all four are safe; every one of them is settled
    before the first layer applies.
    """
    if condition is None or isinstance(condition, bool):
        return
    if not isinstance(condition, Mapping):
        raise DslError(f"{where}: a static condition must be an object")
    heads = [k for k in STATIC_CONDITION_HEADS if k in condition]
    if len(heads) != 1:
        raise DslError(
            f"{where}: a static condition names exactly one of "
            f"{list(STATIC_CONDITION_HEADS)}, got {sorted(condition)}"
        )
    head = heads[0]
    extra = set(condition) - {head} - ({"left", "right"} if head == "cmp" else set())
    if extra:
        raise DslError(f"{where}: unsupported keys {sorted(extra)} beside {head!r}")

    if head == "counters":
        spec = condition["counters"]
        if not isinstance(spec, Mapping):
            raise DslError(f"{where}.counters: must be an object")
        unknown = set(spec) - {"counter", "amount", "op"}
        if unknown:
            raise DslError(f"{where}.counters: unsupported keys {sorted(unknown)}")
        op = str(spec.get("op", ">="))
        if op not in STATIC_CONDITION_OPS:
            raise DslError(f"{where}.counters: unknown comparison {op!r}")
    elif head in ("all", "any"):
        if not isinstance(condition[head], list) or not condition[head]:
            raise DslError(f"{where}.{head}: takes a non-empty list of conditions")
        for i, sub in enumerate(condition[head]):
            _validate_static_condition(sub, f"{where}.{head}[{i}]")
    elif head == "not":
        _validate_static_condition(condition["not"], f"{where}.not")
    elif head == "exists":
        _validate_static_count_filter(condition["exists"], f"{where}.exists")
    elif head == "is_your_turn":
        if not isinstance(condition["is_your_turn"], bool):
            raise DslError(f"{where}.is_your_turn: must be true or false")
    elif head == "is_attached":
        # Not defaulted: `{"is_attached": false}` is the other half of
        # reconfigure ("it is a creature while unattached"), and a bare
        # truthiness test would read a typo'd string as `true`.
        if not isinstance(condition["is_attached"], bool):
            raise DslError(f"{where}.is_attached: must be true or false")
    elif head == "top_of_library":
        spec = condition["top_of_library"]
        if not isinstance(spec, Mapping):
            raise DslError(f"{where}.top_of_library: must be an object")
        # The same printed-face-and-owner rule every off-battlefield filter
        # follows: the top card of a library is not tapped, attacking or
        # attached to anything, and a key that loads and matches nothing is
        # how a card comes to do less than it prints.
        unknown = set(spec) - (STATIC_ZONE_FILTER_KEYS - {"zone"})
        if unknown:
            raise DslError(
                f"{where}.top_of_library: a card in a library has a printed face and "
                f"an owner and nothing else; unsupported keys {sorted(unknown)}"
            )
        controller = spec.get("controller", "you")
        if controller not in ("you", "opponent", "any"):
            raise DslError(
                f"{where}.top_of_library.controller: must be 'you', 'opponent' or "
                f"'any', got {controller!r}"
            )
    elif head == "has_city_s_blessing":
        who = condition["has_city_s_blessing"]
        if not isinstance(who, str) or who not in STATIC_LIFE_PLAYERS:
            raise DslError(
                f"{where}.has_city_s_blessing: must name one of "
                f"{sorted(STATIC_LIFE_PLAYERS)}, got {who!r}"
            )
    elif head == "cmp":
        op = str(condition["cmp"])
        if op not in STATIC_CONDITION_OPS:
            raise DslError(f"{where}.cmp: unknown comparison {op!r}")
        for side in ("left", "right"):
            if side not in condition:
                raise DslError(f"{where}: a 'cmp' condition needs both 'left' and 'right'")
            _validate_static_value(condition[side], f"{where}.{side}")


#: Player specs a static's per-player life leaf may name.  Smaller than the
#: effect-side list: `active_player` and the binding forms read something that
#: is not settled while characteristics are being computed.
STATIC_LIFE_PLAYERS = frozenset({"you", "opponent", "each_opponent", "each_player", "all"})

#: The per-player life leaves.  Safe inside a static for the same reason a zone
#: count is: a life total is a pipeline *input*, and nothing in the fixed-order
#: characteristics pipeline can change one.
STATIC_LIFE_KEYS = frozenset({"min_life_of", "max_life_of"})


def _validate_static_value(value: Any, where: str) -> None:
    """Static abilities allow ``const``, ``count`` and the per-player life leaves."""
    allowed = {"const", "count", "mana_symbols"} | STATIC_LIFE_KEYS
    if isinstance(value, int):
        return
    if not isinstance(value, Mapping):
        raise DslError(f"{where}: static values must be an int, 'const' or 'count'")
    if set(value) - allowed:
        raise DslError(
            f"{where}: static values may only use {sorted(allowed)}, got {sorted(value)}"
        )
    if "count" in value:
        _validate_static_count_filter(value["count"], f"{where}.count")
    if "mana_symbols" in value:
        # Chroma, and Primalcrux is the reason it is here as well as in the
        # effect language: "its power and toughness are each equal to the number
        # of green mana symbols in the mana costs of permanents you control" is
        # a `set_pt` static. Safe for the reason a zone count is -- a *printed*
        # mana cost is a pipeline input, and no layer can change one.
        validate_mana_symbols(
            value["mana_symbols"],
            f"{where}.mana_symbols",
            validate_objects=_validate_static_count_filter,
        )
    for key in STATIC_LIFE_KEYS & set(value):
        who = value[key]
        if not isinstance(who, str) or who not in STATIC_LIFE_PLAYERS:
            raise DslError(
                f"{where}.{key}: must name one of {sorted(STATIC_LIFE_PLAYERS)}, got {who!r}"
            )


def _compile_cost(model, where: str) -> Cost:
    validate_selector(model.sacrifice, f"{where}.cost.sacrifice")
    validate_selector(model.return_to_hand, f"{where}.cost.return_to_hand")
    validate_selector(model.exile_from_graveyard, f"{where}.cost.exile_from_graveyard")
    validate_selector(model.discard_selector, f"{where}.cost.discard_selector")
    validate_selector(model.tap_permanents, f"{where}.cost.tap_permanents")
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
    # One constructor for both spellings of a cost -- the model here, and the
    # raw mapping an optional effect's `pay` arrives as.  See `Cost.from_spec`.
    cost = Cost.from_spec(model.model_dump())
    assert cost is not None  # model_dump() is never None
    return cost


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


#: Value forms a mana ability's ``amount`` may NOT use.
#:
#: A mana ability is activated inside cost payment, with nothing on the stack:
#: there is no X, no target, no trigger binding and no enclosing loop. Each of
#: these would evaluate to 0 and make a card that silently produces no mana, so
#: they are refused at load rather than at the table.
MANA_AMOUNT_FORBIDDEN = frozenset({"x", "target", "binding", "loop_value"})


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


def _validate_effect(effect: Any, where: str, target_ids: set[str]) -> None:
    """Recursively validate one effect dict."""
    if not isinstance(effect, Mapping):
        raise DslError(f"{where}: effect must be an object")
    op = effect.get("op")
    if op is None:
        raise DslError(f"{where}: effect is missing 'op'")
    if op not in known_ops():
        raise DslError(f"{where}: unknown effect op {op!r} (implemented: {sorted(known_ops())})")

    for key in ("objects", "per", "selector", "affects"):
        if key in effect:
            validate_selector(effect[key], f"{where}.{key}")
    for key in ("amount", "count", "power", "toughness"):
        if key in effect:
            validate_value(effect[key], f"{where}.{key}")
    if "condition" in effect:
        validate_condition(effect["condition"], f"{where}.condition")

    if "target" in effect and str(effect["target"]) not in target_ids:
        raise DslError(
            f"{where}: references target {effect['target']!r} which the card does not declare"
        )
    for key in ("objects", "per", "selector"):
        sub = effect.get(key)
        if isinstance(sub, Mapping) and "target" in sub and str(sub["target"]) not in target_ids:
            raise DslError(
                f"{where}.{key}: references target {sub['target']!r} which the card does not declare"
            )

    if op == "may" and "pay" in effect:
        # "You may pay {2}. If you do, draw a card." Validated through the same
        # CostModel an activated ability's cost uses, so an unknown key here is a
        # load error rather than a cost quietly dropped -- which would turn a
        # card that draws for {2} into one that draws free.
        if not isinstance(effect["pay"], dict):
            raise DslError(f"{where}: 'pay' must be an object")
        try:
            CostModel.model_validate(effect["pay"])
        except Exception as exc:  # pydantic ValidationError
            raise DslError(f"{where}: bad 'pay' cost: {exc}") from exc
        # A payment has to buy *something*, but there are two things it can buy.
        # "You may pay {2}. If you do, draw a card" buys the `effects`. Rhystic
        # Study's "unless that player pays {1}" buys the **absence** of the
        # `else` -- the payer gets nothing and that is the whole point, because
        # what they are paying for is to stop the other branch happening. So
        # `effects` alone is not the test; having neither branch is.
        if not effect.get("effects") and not effect.get("else"):
            raise DslError(
                f"{where}: 'pay' needs 'effects' or 'else' -- paying for nothing is not a card"
            )
    if op == "look_at_hand" and "player" not in effect:
        # Whose hand is the whole ability. Defaulted, Glasses of Urza would
        # silently pick a player instead of targeting one.
        raise DslError(f"{where}: look_at_hand needs a 'player' -- whose hand")
    if op == "search_zones":
        zones = effect.get("zones")
        # A missing or single-zone list is `search_library` spelled the long way,
        # and the whole point of this op is that the count is over the *union*.
        if not isinstance(zones, (list, tuple)) or len(zones) < 2:
            raise DslError(
                f"{where}: search_zones needs 'zones' with at least two of "
                f"{list(SEARCHABLE)}; use search_library for one"
            )
        unknown = [z for z in zones if z not in SEARCHABLE]
        if unknown:
            raise DslError(
                f"{where}: cannot search {unknown} (searchable: {list(SEARCHABLE)})"
            )
        if len(set(zones)) != len(zones):
            # A repeated zone would put every card in it into the pool twice.
            raise DslError(f"{where}: search_zones lists a zone twice: {list(zones)}")
        # The op builds its pool one zone at a time and tests each half against
        # the zone that half came from, so a `zone` written here is overridden
        # rather than honoured -- a card asking for one would not get it.
        if isinstance(effect.get("selector"), Mapping) and "zone" in effect["selector"]:
            raise DslError(
                f"{where}.selector: drop 'zone' -- search_zones takes its zones "
                f"from 'zones', and each half is matched in its own"
            )
    if op == "look_at_top":
        # The depth is the card. Without an amount the op would look at one
        # card and Through the Forest Gate would silently become a cantrip,
        # so it is required rather than defaulted.
        if "amount" not in effect:
            raise DslError(f"{where}: look_at_top needs an 'amount' -- how deep it looks")
        destination = str(effect.get("destination", "hand"))
        if destination not in DESTINATIONS:
            raise DslError(
                f"{where}: unknown look_at_top destination {destination!r} "
                f"(implemented: {sorted(DESTINATIONS)})"
            )
    if op == "must_attack":
        duration = str(effect.get("duration", "next_combat"))
        if duration not in ("this_turn", "next_combat"):
            # A misspelled duration would set a requirement nothing ever
            # discharges, or one that expires before the combat it names.
            raise DslError(
                f"{where}: unknown must_attack duration {duration!r} "
                f"(implemented: 'this_turn', 'next_combat')"
            )
    # The link is written on the exiled card and points at the source of the
    # ability that exiled it. With nothing to exile there is nothing to link,
    # and the card would load as a permanent exile with no way to say so.
    if op == "exile" and effect.get("until_leaves") and "objects" not in effect:
        raise DslError(
            f"{where}: 'until_leaves' needs 'objects' -- there is nothing to link"
        )
    if op == "copy_permanent" and (overrides := effect.get("except_") or effect.get("except")):
        # "…except it's a white Zombie Angel with no mana cost." A misspelled
        # key here would be silently dropped, and the token would come back a
        # plain copy -- which is a different card and looks identical until
        # somebody reads its colour.
        if not isinstance(overrides, Mapping):
            raise DslError(f"{where}: 'except_' must be an object")
        unknown = set(overrides) - {"colors", "add_subtypes", "no_mana_cost"}
        if unknown:
            raise DslError(
                f"{where}.except_: unsupported keys {sorted(unknown)} "
                f"(implemented: 'colors', 'add_subtypes', 'no_mana_cost')"
            )
        for color in overrides.get("colors") or ():
            if color not in KNOWN_COLORS:
                raise DslError(f"{where}.except_.colors: unknown colour {color!r}")
    if op == "add_subtype":
        # An op that names no subtype is a printed sentence that does nothing,
        # and it would load and resolve exactly like one that works.
        if not effect.get("subtypes"):
            raise DslError(f"{where}: add_subtype needs 'subtypes'")
        if "objects" not in effect:
            raise DslError(f"{where}: add_subtype needs 'objects' -- there is nothing to change")
        if "types" in effect:
            # Only subtypes. "Becomes an artifact in addition to its other
            # types" is a different sentence and would need the type to reach
            # the same places subtypes do; accepting the key and dropping it is
            # how a card silently half-works.
            raise DslError(
                f"{where}: add_subtype changes subtypes only; use 'animate' for card types"
            )
    if op == "gain_control":
        # "Gain control of" with nothing named is a card that reads like removal
        # and does nothing at all.
        if "objects" not in effect:
            raise DslError(f"{where}: gain_control needs 'objects' -- there is nothing to take")
        # Only the permanent form exists. A `duration` would be read as "until
        # end of turn" by whoever wrote it and ignored by the engine, which
        # turns Act of Treason into a strictly better card than the printed one.
        if "duration" in effect:
            raise DslError(
                f"{where}: gain_control has no duration; only a permanent control "
                f"change is implemented (see docs/rules-coverage.md)"
            )
    if op == "create_token" and "token" not in effect:
        raise DslError(f"{where}: create_token needs a 'token' id")
    # A misspelled duration would silently fall back to until-end-of-turn,
    # which is the *wrong half* of riot rather than a smaller version of it.
    if op == "grant_keyword" and effect.get("duration", "until_end_of_turn") not in (
        "until_end_of_turn",
        "permanent",
    ):
        raise DslError(
            f"{where}: unknown grant_keyword duration {effect['duration']!r} "
            f"(use 'until_end_of_turn' or 'permanent')"
        )
    if op == "add_poison" and "amount" in effect:
        validate_value(effect["amount"], f"{where}.amount")
    if op == "detain" and not effect.get("objects"):
        # Detain with no selector restricts nobody: the card resolves, the log
        # says nothing, and the creature attacks anyway.
        raise DslError(f"{where}: detain needs 'objects' naming what is detained")
    if op == "set_flag" and not effect.get("flag"):
        # A flag with no name writes nothing, so renown's once-only guard never
        # closes and the creature grows on every combat damage for ever.
        raise DslError(f"{where}: set_flag needs a 'flag' to write")
    if op == "move_counters":
        # Without a destination the counters come off the source and go
        # nowhere, which is a card that reads "move a +1/+1 counter onto it"
        # and quietly shrinks its own creature.
        if not effect.get("objects"):
            raise DslError(
                f"{where}: move_counters needs 'objects' naming where the counters go "
                f"(the source is 'from', defaulting to this permanent)"
            )
        if "amount" in effect:
            validate_value(effect["amount"], f"{where}.amount")
        if "from" in effect:
            validate_selector(effect["from"], f"{where}.from")
    if op == "must_block" and not effect.get("objects"):
        # Without `objects` the op resolves an empty pool and requires nothing
        # of anybody, which is a provoke that loads clean and does nothing --
        # the failure this whole pass exists to refuse.
        raise DslError(
            f"{where}: must_block needs 'objects' naming who has to block "
            f"(the attacker defaults to the ability's own source)"
        )
    if op == "counter" and "sid" in effect:
        # Ward's "counter it": the victim is named by value, not chosen. A
        # malformed expression here would evaluate to 0, match no stack item and
        # counter nothing -- a ward that reads as printed and never protects
        # anything, which is the failure this whole pass exists to refuse.
        validate_value(effect["sid"], f"{where}.sid")
        if "target" in effect:
            raise DslError(
                f"{where}: counter takes 'sid' or 'target', not both -- one names "
                f"the spell that targeted this permanent, the other lets its "
                f"controller pick a different spell"
            )
    if "as" in effect and not (isinstance(effect["as"], str) and effect["as"]):
        # `as` names a binding -- `snapshot`'s, and the record `reveal` and
        # `sacrifice` write of what they consumed. A non-string would be
        # stringified into a name nothing reads back, so the count it feeds
        # would be 0 and amplify would enter with no counters.
        raise DslError(f"{where}: 'as' must be a non-empty binding name, got {effect['as']!r}")
    if op == "unattach" and not effect.get("objects"):
        # Explore's trap once more: "unattach this permanent" is three words on
        # the Equipment that prints it, and a default would silently unattach
        # the spell object on anything that is not a permanent's own ability.
        raise DslError(
            f"{where}: unattach needs 'objects' naming what comes off "
            f"(use {{\"self_only\": true}} for \"unattach this permanent\")"
        )
    if op == "explore" and not effect.get("objects"):
        # 701.40a puts the +1/+1 counter on the *exploring* permanent, so the op
        # has to be told which one that is. Defaulted to this permanent it would
        # read correctly on a creature and silently do nothing on a sorcery,
        # whose source is a spell on the stack -- so the card would reveal no
        # card, place no counter, and load perfectly cleanly.
        raise DslError(
            f"{where}: explore needs 'objects' naming what explores "
            f"(use {{\"self_only\": true}} for \"it explores\")"
        )
    if op == "connive" and not effect.get("objects"):
        # Same trap as explore, and the same three words fix it: the +1/+1
        # counters go on the *conniving* permanent, so a defaulted `self_only`
        # would be right on "whenever this creature attacks, it connives" and
        # would draw and discard for nobody on "target creature connives".
        raise DslError(
            f"{where}: connive needs 'objects' naming what connives "
            f"(use {{\"self_only\": true}} for \"it connives\")"
        )
    if op == "add_mana" and "mana" not in effect:
        raise DslError(f"{where}: add_mana needs 'mana'")
    if op == "animate":
        # "Becomes a 4/4 creature" is the whole point, and an animation with no
        # size would silently make a 0/0 that dies to state-based actions the
        # moment it arrives.
        if "power" not in effect or "toughness" not in effect:
            raise DslError(f"{where}: animate needs 'power' and 'toughness'")
        for t in effect.get("types", ()) or ():
            if t not in KNOWN_TYPES:
                raise DslError(f"{where}: unknown card type {t!r}")
        for k in effect.get("keywords", ()) or ():
            if k not in KNOWN_KEYWORDS:
                raise DslError(f"{where}: unknown keyword {k!r}")
        for c in effect.get("colors", ()) or ():
            if c not in KNOWN_COLORS:
                raise DslError(f"{where}: unknown colour {c!r}")
    if op == "delay":
        # A misspelled step would schedule something that never comes due -- a
        # card that reads "at the beginning of the next upkeep, draw a card" and
        # silently draws nothing, which is exactly what this pass exists to stop.
        step = str(effect.get("step", "end_step"))
        if step not in DELAY_STEPS:
            raise DslError(
                f"{where}: unknown delay step {step!r} (implemented: {sorted(DELAY_STEPS)})"
            )
        if not effect.get("effects"):
            raise DslError(f"{where}: delay needs 'effects' to schedule")

    for key in ("then", "else", "effects"):
        if key in effect:
            for i, sub in enumerate(effect[key] or []):
                _validate_effect(sub, f"{where}.{key}[{i}]", target_ids)
    for i, mode in enumerate(effect.get("modes", []) or []):
        if not isinstance(mode, Mapping):
            raise DslError(f"{where}.modes[{i}]: must be an object")
        for j, sub in enumerate(mode.get("effects", []) or []):
            _validate_effect(sub, f"{where}.modes[{i}].effects[{j}]", target_ids)


def _derive_color_identity(
    colors: frozenset[str], mana_cost: ManaCost, abilities: tuple[Ability, ...]
) -> frozenset[str]:
    """Colour identity = colours in the cost, plus colours in any mana symbol on the card."""
    identity = set(colors)
    for ability in abilities:
        if ability.cost is not None:
            identity.update(c.value for c in ability.cost.mana.colors)
        for option in ability.mana_options:
            for i, amount in enumerate(option[:5]):
                if amount:
                    identity.add(("W", "U", "B", "R", "G")[i])
        for effect in ability.effects:
            if effect.get("op") in ("add_mana", "add_mana_per"):
                for i, amount in enumerate(parse_mana_production(str(effect.get("mana", "")))[:5]):
                    if amount:
                        identity.add(("W", "U", "B", "R", "G")[i])
    return frozenset(identity)


def link_faces(cards: dict[str, CardDef]) -> None:
    """Point every back face at its front, and refuse a half-written link.

    The two faces of a transforming card are two ``CardDef``s and one
    ``GameObject``; ``GameState.card_of`` picks between them. That works only if
    the link is complete in both directions, so the *back* pointer is derived
    here rather than authored -- a card file that named a front face by hand
    could name a different one than the front names, and nothing would say so.

    A back face is never cast, drawn or shuffled into a deck. The guards that
    enforce that all ask ``front_face is not None``, so an unlinked back face
    would quietly become a playable card with no mana cost.
    """
    for card in cards.values():
        if card.back_face is None:
            continue
        back = cards.get(card.back_face)
        if back is None:
            raise DslError(f"{card.id}: back_face references unknown card {card.back_face!r}")
        if back.back_face is not None:
            # Two-faced, not three. A cycle here would make `card_of` a walk
            # rather than a lookup.
            raise DslError(f"{card.id}: back face {back.id!r} may not have a back face of its own")
        if back.front_face is not None and back.front_face != card.id:
            raise DslError(
                f"{back.id}: is the back face of both {back.front_face!r} and {card.id!r}"
            )
        cards[back.id] = dataclasses.replace(back, front_face=card.id)


def validate_token_references(cards: Mapping[str, CardDef]) -> None:
    """Every ``create_token`` must name a card id that exists and is a token."""
    for card in cards.values():
        for effect in _walk_effects(card):
            if effect.get("op") != "create_token":
                continue
            token_id = str(effect.get("token"))
            token = cards.get(token_id)
            if token is None:
                raise DslError(f"{card.id}: create_token references unknown card {token_id!r}")
            if not token.is_token:
                raise DslError(f"{card.id}: {token_id!r} is not marked as a token")


def _walk_effects(card: CardDef):
    def walk(effects):
        for effect in effects:
            yield effect
            for key in ("then", "else", "effects"):
                yield from walk(effect.get(key) or [])
            for mode in effect.get("modes", []) or []:
                yield from walk(mode.get("effects") or [])

    yield from walk(card.spell_effects)
    for ability in card.abilities:
        yield from walk(ability.effects)
