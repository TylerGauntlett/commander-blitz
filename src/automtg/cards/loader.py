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

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from automtg.engine.carddef import Ability, CardDef, Cost, TargetSpec, TriggerSpec, build_type_line
from automtg.engine.effects import known_ops
from automtg.engine.effects.conditions import validate_condition
from automtg.engine.effects.selectors import validate_selector
from automtg.engine.effects.values import validate_value
from automtg.engine.enums import AbilityKind, CardType, Color, Keyword, Supertype, Zone
from automtg.engine.errors import DslError
from automtg.engine.mana import ManaCost, parse_mana_production
from automtg.engine.triggers import TRIGGER_EVENTS
from automtg.engine.turn import DELAY_STEPS

from .schema import AbilityModel, CardModel, DeckModel, TargetModel

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
        # Ancient Greenwarden.  A fact about the *player*, like the two above:
        # it is read by `triggers.collect` rather than by the characteristics
        # pipeline, and there is no object for it to attach to.
        "double_land_triggers",
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

    if model.cost_reduction is not None:
        _validate_cost_reduction(model.cost_reduction, f"{where}.cost_reduction")

    # Kicker is two halves that only mean anything together: the extra cost, and
    # an `if` that reads it.  Half a kicker is the failure this pass exists to
    # catch -- a spell that charges more and does the same thing, or one whose
    # kicked clause can never fire, and nothing on the board would say so.
    reads_kicked = _mentions_kicked(model)
    if reads_kicked and kicker is None:
        raise DslError(f"{where}: reads the 'kicked' condition but has no 'kicker' cost")
    if kicker is not None and not reads_kicked:
        raise DslError(f"{where}: has a 'kicker' cost that no effect reads via 'kicked'")

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
        type_line=build_type_line(supertypes, types, subtypes),
        is_token=model.is_token,
        uncounterable=model.uncounterable,
        kicker=kicker,
        cost_reduction=dict(model.cost_reduction) if model.cost_reduction else None,
    )


def _mentions_kicked(model: CardModel) -> bool:
    """Does anything on this card read ``{"kicked": ...}``?"""

    def walk(node: Any) -> bool:
        if isinstance(node, Mapping):
            return "kicked" in node or any(walk(v) for v in node.values())
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

        trigger = TriggerSpec(
            event=model.trigger.event,
            controller=model.trigger.controller,
            source=source,
            filter=dict(model.trigger.filter) if model.trigger.filter else None,
            condition=dict(model.trigger.condition) if model.trigger.condition else None,
            defending=model.trigger.defending,
        )
        active_zones = tuple(Zone(z) for z in model.active_zones)

    mana_options: tuple[tuple[int, ...], ...] = ()
    if model.is_mana_ability:
        if kind is not AbilityKind.ACTIVATED:
            raise DslError(f"{where}: only activated abilities can be mana abilities")
        if targets:
            raise DslError(f"{where}: a mana ability cannot have targets")
        mana_options = _mana_options(model.effects, where)

    return Ability(
        kind=kind,
        index=index,
        text=model.text,
        cost=cost,
        is_mana_ability=model.is_mana_ability,
        mana_options=mana_options,
        sorcery_speed_only=model.sorcery_speed_only,
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
    if model.effect in (
        "extra_land_drops",
        "no_hand_limit",
        "play_lands_from_graveyard",
        "play_lands_from_library_top",
        "double_land_triggers",
    ):
        if model.affects_player is None:
            raise DslError(f"{where}: {model.effect} needs 'affects_player'")
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
    _validate_static_condition(model.condition, f"{where}.condition")

    static: dict[str, Any] = {"effect": model.effect}
    if model.condition is not None:
        static["condition"] = dict(model.condition)
    if model.affects is not None:
        static["affects"] = dict(model.affects)
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


def _validate_static_condition(condition: Any, where: str) -> None:
    """A static may only ask about counters on its own source.

    Much smaller than the ``if``-effect condition language, and for the same
    reason ``affects`` filters are: anything that reads a *derived*
    characteristic would let one static depend on another's output, and the
    fixed-order pipeline has no way to resolve that.
    """
    if condition is None:
        return
    if not isinstance(condition, Mapping) or set(condition) != {"counters"}:
        raise DslError(f"{where}: a static condition may only be {{'counters': ...}}")
    spec = condition["counters"]
    if not isinstance(spec, Mapping):
        raise DslError(f"{where}.counters: must be an object")
    unknown = set(spec) - {"counter", "amount", "op"}
    if unknown:
        raise DslError(f"{where}.counters: unsupported keys {sorted(unknown)}")
    op = str(spec.get("op", ">="))
    if op not in STATIC_CONDITION_OPS:
        raise DslError(f"{where}.counters: unknown comparison {op!r}")


def _validate_static_value(value: Any, where: str) -> None:
    """Static abilities allow only ``{"const": n}`` and ``{"count": filter}``."""
    if isinstance(value, int):
        return
    if not isinstance(value, Mapping):
        raise DslError(f"{where}: static values must be an int, 'const' or 'count'")
    if set(value) - {"const", "count"}:
        raise DslError(
            f"{where}: static values may only use 'const' or 'count', got {sorted(value)}"
        )
    if "count" in value:
        unknown = set(value["count"]) - STATIC_FILTER_KEYS
        if unknown:
            raise DslError(f"{where}.count: unsupported filter keys {sorted(unknown)}")


def _compile_cost(model, where: str) -> Cost:
    validate_selector(model.sacrifice, f"{where}.cost.sacrifice")
    validate_selector(model.exile_from_graveyard, f"{where}.cost.exile_from_graveyard")
    return Cost(
        mana=ManaCost.parse(model.mana),
        tap=model.tap,
        untap=model.untap,
        sacrifice=dict(model.sacrifice) if model.sacrifice else None,
        discard=model.discard,
        pay_life=model.pay_life,
        remove_counters=dict(model.remove_counters) if model.remove_counters else None,
        exile_from_graveyard=(
            dict(model.exile_from_graveyard) if model.exile_from_graveyard else None
        ),
    )


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

    if op == "create_token" and "token" not in effect:
        raise DslError(f"{where}: create_token needs a 'token' id")
    if op == "add_mana" and "mana" not in effect:
        raise DslError(f"{where}: add_mana needs 'mana'")
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
