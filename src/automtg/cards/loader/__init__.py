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

from automtg.engine.carddef import (
    Ability,
    CardDef,
    Cost,
    TargetSpec,
    TriggerSpec,
    build_type_line,
    count_mode_specs,
    prune_cost,
    top_level_mode_spec,
)
from automtg.engine.effects.conditions import validate_condition
from automtg.engine.effects.selectors import validate_selector
from automtg.engine.effects.values import (
    validate_value,
)
from automtg.engine.enums import (
    AbilityKind,
    CardType,
    Zone,
)
from automtg.engine.errors import DslError
from automtg.engine.mana import SYMBOLS as MANA_SYMBOLS
from automtg.engine.mana import ManaCost, ManaRestriction
from automtg.engine.sagas import LORE, SAGA
from automtg.engine.triggers import ORDINAL_FILTER_KEYS, TRIGGER_EVENTS

from ..schema import AbilityModel, CardModel, CostModel, DeckModel
from .effects import (  # noqa: F401
    _refuse_seats_read_as_objects,
    _refuse_targets_inside_a_delay,
    _validate_attacking,
    _validate_delayed_trigger,
    _validate_effect,
    _validate_enchanted_player,
    _validate_player_spec,
    _validate_was_cast_placement,
)
from .linking import (  # noqa: F401
    _derive_color_identity,
    _walk_effects,
    link_faces,
    link_meld_results,
    link_prepared_faces,
    link_second_faces,
    validate_token_references,
)
from .mana import (  # noqa: F401
    _ANY_COLOR_OPTIONS,
    _compile_cost,
    _mana_amount,
    _mana_options,
    _mana_restriction,
    _restriction_groups,
    _restriction_name,
    _split_mana_rider,
    _sum_mana,
    _validate_mana_amount,
)
from .statics import (  # noqa: F401
    _check_reduction_type_names,
    _validate_cost_condition,
    _validate_cost_reduction,
    _validate_reduction_zones,
    _validate_static_condition,
    _validate_static_count_filter,
    _validate_static_value,
)
from .targets import (  # noqa: F401
    _check_mode_targets,
    _check_reflexive_wiring,
    _compile_target,
    _compile_targets,
)

# Re-exported: this package is imported as one module -- `from
# automtg.cards.loader import compile_card, STATIC_EFFECTS, _validate_effect`
# -- by the registry, the proxy, the authoring packet and ~180 tests. The
# split is a move, not a new API; every name keeps its old address.
from .vocabulary import (  # noqa: F401
    _CHOSEN_QUALITY_KEYS,
    _FILTER_PLAYERS,
    ATTACKING_OPS,
    CONTROLLED_TARGET_KINDS,
    COST_CONDITION_HEADS,
    COST_REDUCTION_FILTER_KEYS,
    COST_REDUCTION_KEYS,
    COST_REDUCTION_REFUSED_FILTER_KEYS,
    COST_REDUCTION_ZONES,
    COUNTERS_ON_ARRIVAL_OPS,
    DEFENDING_TRIGGERS,
    DELAYED_TRIGGER_KEYS,
    GRANTABLE_STATIC_EFFECTS,
    KNOWN_COLORS,
    KNOWN_KEYWORDS,
    KNOWN_SUPERTYPES,
    KNOWN_TYPES,
    MANA_AMOUNT_FORBIDDEN,
    MANA_RIDER_OPS,
    NOT_A_CAST_TIME_COST,
    PLAYER_TARGET_KINDS,
    PLAYER_WIDE_STATIC_EFFECTS,
    PLURAL_PLAYER_SPEC_NAMES,
    SOURCE_MOVING_OPS,
    SPELL_FILTER_KEYS,
    STATIC_CONDITION_HEADS,
    STATIC_CONDITION_OPS,
    STATIC_COUNT_FILTER_KEYS,
    STATIC_COUNT_ZONES,
    STATIC_EFFECTS,
    STATIC_FILTER_KEYS,
    STATIC_LIFE_KEYS,
    STATIC_LIFE_PLAYERS,
    STATIC_VALUE_KEYS,
    STATIC_ZONE_FILTER_KEYS,
    TAPPED_PERMANENT_KEYS,
    TOKEN_FILTER_KEYS,
    UNGRANTABLE_STATIC_EFFECTS,
    WAS_CAST_TRIGGERS,
)
from .walk import (  # noqa: F401
    _before,
    _check_counter_kind,
    _check_mana_cost_key,
    _check_owner_key,
    _effects_move_source,
    _mentions,
    _mentions_condition,
    _mentions_gift,
    _mentions_kicked,
    _mentions_pair,
    _refuse_granted_chosen_qualities,
    _walk_effect_specs,
)


def _check_grant_targets(
    model: CardModel, abilities: tuple[Ability, ...], grantable: tuple[Ability, ...], where: str
) -> None:
    """Every ``grant_ability`` on this card points at a grantable that can work.

    Two failures, both silent, and the second only became possible when a static
    was allowed into `grantable_abilities` at all:

    * **Out of range.** `characteristics.abilities_of` and the `grant_ability`
      op both index the list and both skip a miss, so an off-by-one is a card
      that prints "gains flying and …" and hands over nothing.
    * **The op pointing at a static.** The *op* grants for a duration through
      pointers that only `triggers` and `abilities_of`'s callers read as
      abilities; a static handed over that way never reaches
      `_battlefield_statics`, because that walk finds statics on the derived
      list rather than in the grant record. So the one-shot form is refused
      where the continuous form is exactly what the card wants.
    """
    for i, ability in enumerate(grantable):
        if not ability.is_static:
            continue
        if not (ability.static or {}).get("effect"):
            raise DslError(f"{where}.grantable[{i}]: a static needs an 'effect'")

    def check(index: Any, what: str, *, statics_ok: bool) -> None:
        try:
            pos = int(index)
        except (TypeError, ValueError):
            raise DslError(f"{where}: {what} index {index!r} is not a number") from None
        if not 0 <= pos < len(grantable):
            raise DslError(
                f"{where}: {what} names 'grantable_abilities[{pos}]' and this card "
                f"has {len(grantable)} -- a grant nothing answers hands over nothing"
            )
        if grantable[pos].is_static and not statics_ok:
            raise DslError(
                f"{where}: the grant_ability *op* hands over a pointer that the "
                f"characteristics pipeline never reads, so granting the static "
                f"'grantable_abilities[{pos}]' with it would do nothing -- a "
                f"continuous grant is the `grant_ability` **static**"
            )

    for ability in abilities:
        static = ability.static or {}
        if ability.is_static and static.get("effect") == "grant_ability":
            check(static.get("ability", 0), "grant_ability static", statics_ok=True)

    trees: list[Any] = [model.spell_effects]
    trees.extend(a.effects for a in abilities)
    trees.extend(a.effects for a in grantable)
    for tree in trees:
        for effect in _walk_effect_specs(tree):
            if effect.get("op") != "grant_ability":
                continue
            index = effect.get("ability", effect.get("ability_index"))
            check(index, "grant_ability op", statics_ok=False)


def _compile_emblems(model: CardModel, where: str) -> tuple[CardDef, ...]:
    """Each quoted emblem as a ``CardDef`` of its own (114).

    An emblem has abilities and nothing else (114.3), so the definition is its
    abilities plus the three things a display needs: a name in Scryfall's
    "<card> Emblem" form, the type line ``Emblem`` and the quoted text. It
    carries no card types, so no selector, filter or count that asks about
    permanents or cards can ever match one.

    Every ability works **from the command zone** (114.4), and that is written
    by the loader rather than by the author: the default ``active_zones`` is the
    battlefield, where an emblem never is, so an emblem that took the default
    would load clean and never trigger.

    **Triggered abilities only.** That is what `triggers._candidate_abilities`
    already reads from the command zone (Edgar Markov's eminence). A static is
    read by several separate walks -- the characteristic layers, the player
    statics, the cost reductions -- none of which look at the command zone, and
    an activated ability would have to be offered from it; either would load
    and do nothing, so both are refused until one is built.
    """
    out: list[CardDef] = []
    for i, emblem in enumerate(model.emblems):
        here = f"{where}.emblems[{i}]"
        if not emblem.abilities:
            raise DslError(f"{here}: an emblem with no abilities is nothing (114.3)")
        abilities: list[Ability] = []
        for j, ability in enumerate(emblem.abilities):
            if ability.kind != "triggered":
                raise DslError(
                    f"{here}.abilities[{j}]: only triggered abilities work from the "
                    f"command zone so far, not {ability.kind!r} -- a static or "
                    f"activated emblem ability would load and never apply"
                )
            if list(ability.active_zones) not in (["battlefield"], ["command"]):
                raise DslError(
                    f"{here}.abilities[{j}]: an emblem is only ever in the command "
                    f"zone (114.1), so its abilities work there and nowhere else, "
                    f"not in {ability.active_zones}"
                )
            if ability.trigger is not None and ability.trigger.source == "self":
                # "this emblem" is never the subject of an event: nothing moves,
                # taps, damages or targets it.
                raise DslError(
                    f"{here}.abilities[{j}]: an emblem is never the subject of a "
                    f"trigger event, so 'source: self' could never fire"
                )
            commanded = ability.model_copy(update={"active_zones": ["command"]})
            abilities.append(_compile_ability(commanded, j, here))
        out.append(
            CardDef(
                id=f"{model.id}_emblem_{i}",
                name=f"{model.name} Emblem",
                oracle_text="\n".join(a.text for a in abilities),
                abilities=tuple(abilities),
                type_line="Emblem",
            )
        )
    return tuple(out)


def _check_emblem_references(
    model: CardModel,
    abilities: tuple[Ability, ...],
    grantable: tuple[Ability, ...],
    emblems: tuple[CardDef, ...],
    where: str,
) -> None:
    """Every ``emblem`` op names an emblem this card writes, and every emblem
    this card writes is given by something.

    Out of range is silent at runtime -- the op would have nothing to hand over
    -- and an emblem no op names is a quoted ability the card prints and never
    delivers.
    """
    trees: list[Any] = [model.spell_effects]
    trees.extend(a.effects for a in abilities)
    trees.extend(a.effects for a in grantable)
    for emblem in emblems:
        trees.extend(a.effects for a in emblem.abilities)
    named: set[int] = set()
    for tree in trees:
        for effect in _walk_effect_specs(tree):
            if effect.get("op") != "emblem":
                continue
            index = effect.get("emblem")
            try:
                pos = int(index)
            except (TypeError, ValueError):
                raise DslError(
                    f"{where}: emblem op needs 'emblem', an index into the card's "
                    f"'emblems', got {index!r}"
                ) from None
            if not 0 <= pos < len(emblems):
                raise DslError(
                    f"{where}: emblem op names 'emblems[{pos}]' and this card has "
                    f"{len(emblems)}"
                )
            named.add(pos)
    for pos in range(len(emblems)):
        if pos not in named:
            raise DslError(
                f"{where}: 'emblems[{pos}]' is written and no emblem op gives it to anybody"
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
            name = (
                entry.get("id", entry.get("name", "<unknown>")) if isinstance(entry, dict) else "?"
            )
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


def _implied_replacements(model: CardModel) -> tuple[dict[str, Any], ...]:
    """A card's replacements, plus the ones the rules put on it.

    Two cards in the game arrive with counters nobody wrote a replacement for,
    and both are the same shape: a number printed on the card that the *rules*
    turn into counters as the permanent enters.

    Loyalty **is** counters (306.5b), so a planeswalker's starting loyalty is an
    enters-with-counters replacement and nothing new runs when one arrives.
    Everything the engine already does with counters -- proliferate, the client's
    badge, `counters_on` -- reads loyalty for free because there is nothing else
    to read.

    A Saga is 714.2b: "as a Saga enters, its controller puts a lore counter on
    it". A **replacement** and not a `self_enters` trigger, and that distinction
    is the first of the four the gap record for Oath of Eorl asked for. Written
    as a trigger the counter lands after the Saga is already on the battlefield
    and after every other enters trigger has looked at a Saga with no counters on
    it -- so chapter I would be a round of priority late, an opponent could
    respond to the Saga before it had started, and anything counting lore
    counters on arrival would read zero.

    Both are written here rather than asked of the card's author for the same
    reason: a planeswalker that entered with no loyalty is binned by the
    zero-loyalty state-based action the instant it resolves, and a Saga that
    entered with no lore counter would simply never start.
    """
    out = [r.model_dump() for r in model.replacements]
    if model.loyalty is not None:
        out.append(
            {
                "event": "self_enters_with_counters",
                "counter": "loyalty",
                "amount": model.loyalty,
                "modify": {},
                "condition": None,
            }
        )
    if any(a.kind == "chapter" for a in model.abilities):
        out.append(
            {
                "event": "self_enters_with_counters",
                "counter": LORE,
                "amount": 1,
                "modify": {},
                "condition": None,
            }
        )
    return tuple(out)


def _final_chapter(model: CardModel, abilities: tuple[Ability, ...], where: str) -> int | None:
    """A Saga's final chapter number (714.4), or ``None`` for a card that is not one.

    Derived from the chapters the card prints unless the author names it, and the
    override is the whole reason the field exists: 704.5s sacrifices a Saga once
    its lore counters *reach* this number, so a Saga whose last chapter the DSL
    could not say would, derived, be sacrificed one chapter early -- quietly a
    better card than the printed one. Named, it sits out its final chapter doing
    nothing, which is the printed card minus a line and is visible.

    The two refusals here are both the "looks implemented, does nothing" shape
    the authoring gates exist to catch, so each fails at load time:

    - a chapter ability on a card with no ``Saga`` subtype. Nothing would ever
      put a lore counter on it, so every chapter would be dead text.
    - a declared ``final_chapter`` below the highest chapter written. The Saga
      would be sacrificed before its last chapter could ever trigger.

    **A ``Saga`` subtype with no chapters is allowed**, and that is not an
    oversight. It is what an inert proxy of a Saga is -- `data/generated/` prints
    the real name, cost, colours and type line with the rules text doing nothing,
    and seven Sagas in the catalog are proxied that way -- so refusing it would
    make those cards unrepresentable rather than unimplemented. Such a card gets
    ``final_chapter is None``, which is what every rule in :mod:`engine.sagas`
    tests: it is given no lore counter, advances nothing and is never sacrificed,
    exactly like the inert enchantment it is. 704.5s agrees, since it asks for "a
    Saga permanent **with one or more chapter abilities**".

    An *authored* Saga cannot slip through the same hole, because its printed
    chapter lines would be unclaimed and the residual gate rejects the card.
    """
    chapters = sorted(a.chapter for a in abilities if a.chapter is not None)

    if chapters and SAGA not in model.subtypes:
        raise DslError(
            f"{where}: chapter abilities need the {SAGA!r} subtype -- "
            f"only a Saga is given a lore counter, so these would never trigger"
        )
    if not chapters:
        return model.final_chapter

    if chapters[0] < 1:
        raise DslError(f"{where}: chapter numbers start at 1, not {chapters[0]}")

    declared = model.final_chapter
    if declared is None:
        return chapters[-1]
    if declared < chapters[-1]:
        raise DslError(
            f"{where}: 'final_chapter' is {declared} but the card prints chapter "
            f"{chapters[-1]}, which could never trigger before the Saga is sacrificed"
        )
    return declared


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
            raise DslError(
                f"{where}: unknown keyword {k!r} (implemented: {sorted(KNOWN_KEYWORDS)})"
            )

    mana_cost = ManaCost.parse(model.mana_cost)
    kicker = ManaCost.parse(model.kicker) if model.kicker else None
    if kicker is not None:
        if kicker.x_count:
            raise DslError(f"{where}: a kicker cost with X is not implemented")
        if kicker.mana_value() == 0:
            raise DslError(f"{where}: kicker {model.kicker!r} costs nothing")

    if CardType.CREATURE.value in model.types and (model.power is None or model.toughness is None):
        raise DslError(f"{where}: creatures need power and toughness")

    # How many modes a mode-owned target may point at, and `None` when there is
    # no single cast-time modal question -- the same test `CardDef` makes for
    # `cast_time_modes`, asked here because the loader has to refuse a `mode`
    # the engine would never get to ask about.
    cast_modes = (
        top_level_mode_spec(model.spell_effects)
        if count_mode_specs(model.spell_effects) == 1
        else None
    )
    mode_count = len(cast_modes.get("modes") or ()) if cast_modes else None
    all_targets = _compile_targets(
        model.targets,
        where,
        on_spell=True,
        mode_count=mode_count,
        # For the one computed count a spell may carry: "each of X targets"
        # needs an {X} to be sized by.
        mana_cost=model.mana_cost,
    )
    targets = tuple(spec for spec in all_targets if spec.mode is None)
    mode_targets: dict[int, tuple[TargetSpec, ...]] = {}
    for spec in all_targets:
        if spec.mode is not None:
            mode_targets[spec.mode] = (*mode_targets.get(spec.mode, ()), spec)
    # Effects still name every spec, mode-owned or not: which bucket a target
    # lives in is about *when it is declared*, not about who may read it.
    target_kinds = {t.id: t.kind for t in all_targets}
    for i, effect in enumerate(model.spell_effects):
        _validate_effect(effect, f"{where}.spell_effects[{i}]", target_kinds)

    for i, replacement in enumerate(model.replacements):
        if replacement.event == "self_enters_prepared" and model.prepared_face is None:
            # The state is a permission to cast one particular spell, so a
            # permanent that enters prepared with no spell to cast has entered
            # with nothing -- a printed line, a reminder paragraph, and no
            # difference to any game.
            raise DslError(
                f"{where}.replacements[{i}]: 'self_enters_prepared' needs a "
                f"'prepared_face' -- there is no spell to cast a copy of"
            )
        if replacement.counter is not None:
            # "…enters with a vigilance counter on it", "…enters with a shield
            # counter on it." Checked here for the reason the condition below
            # is: the kind is only looked at when a permanent actually enters,
            # so a near-miss spelling of a keyword or shield counter would
            # arrive as an inert tally mid-game rather than being refused at
            # load. Diamond City is the case that makes it matter most, because
            # a mis-spelled shield counter is *visible on the board* and the
            # land still dies to the removal it is printed to survive.
            _check_counter_kind(replacement.counter, f"{where}.replacements[{i}].counter")
        # How many, which may be a value expression -- "a +1/+1 counter on it
        # for each other Human you control". Checked for the same reason the
        # condition below is: `zones._enter_battlefield` only evaluates it when
        # a permanent actually enters, so an unknown value key would be a
        # mid-game crash rather than a card that refuses to load.
        validate_value(replacement.amount, f"{where}.replacements[{i}].amount")
        for kind, amount in ((replacement.modify or {}).get("counters") or {}).items():
            # The other spelling of the same clause: `modify: {"counters": {...}}`
            # keyed by kind. `zones._enter_battlefield` reads whichever is there,
            # and evaluates either as a value -- so both are checked as one.
            _check_counter_kind(kind, f"{where}.replacements[{i}].modify.counters")
            validate_value(amount, f"{where}.replacements[{i}].modify.counters.{kind}")
        if replacement.condition is None:
            continue
        # Without this the tree is only checked when a permanent actually
        # enters, which turns a typo in a land into a mid-game crash instead of
        # a card that refuses to load.
        validate_condition(replacement.condition, f"{where}.replacements[{i}].condition")

    abilities = tuple(_compile_ability(a, i, where) for i, a in enumerate(model.abilities))
    _check_threshold_order(abilities, where)
    grantable = tuple(
        _compile_ability(a, i, f"{where}.grantable")
        for i, a in enumerate(model.grantable_abilities)
    )
    if any(ability.threshold is not None for ability in grantable):
        # A granted ability sits after the recipient's printed ones and is
        # addressed through its granter's pool, so neither the suffix argument
        # in `_check_threshold_order` nor `abilities_of`'s filter covers it.
        raise DslError(f"{where}.grantable_abilities: a threshold is a printed striation")
    final_chapter = _final_chapter(model, abilities, where)
    _check_class_levels(model, abilities, where)
    _check_reflexive_wiring(model, abilities, where)

    for ability in grantable:
        if ability.level is not None or ability.becomes_level is not None:
            # A level is a fact about the permanent that *prints* the line (716),
            # and a granted ability sits on some other permanent -- whose level
            # is 1 for ever unless it is a Class, and then it is that Class's
            # own ladder. Either way the line would mean something the granting
            # card never said.
            raise DslError(
                f"{where}.grantable[{ability.index}]: a Class level belongs to the "
                f"card that prints it, so a granted ability cannot carry 'level' "
                f"or be a 'level' line"
            )
        if ability.kind is AbilityKind.TRIGGERED:
            # Tested against `AbilityKind.TRIGGERED` rather than `is_triggered`,
            # which is True for a *chapter* as well (714.1b). A granted chapter
            # ability is not a thing any card prints and would be nonsense
            # anyway: its trigger is a comparison against the lore counters on
            # its own source, so granted to a creature it would wait for a number
            # nothing can ever reach.
            continue
        if ability.is_activated:
            # A granted **activated** ability, mana or not. Urza's Saga: "I —
            # This Saga gains "{T}: Add {C}."" and "II — This Saga gains "{2},
            # {T}: Create a … Construct …"".
            #
            # Offered, indexed and paid for because legality, the payment solver
            # and `game._activate` all read `characteristics.abilities_of`, which
            # appends a grant -- the static's and, since this line opened, the
            # one-shot op's -- to the printed list.
            #
            # This stopped at mana abilities for as long as 605.3a was the only
            # thing keeping a granted ability off `stack.ability_of`, which
            # resolved off the source's *printed* list: a granted ability that
            # used the stack reached it with an index into a list that did not
            # hold it, and resolved as some other ability of the permanent -- on
            # Urza's Saga, chapter II. `stack.push_activated_ability` now records
            # where a granted ability lives (granter, index into its
            # `grantable_abilities`) as it goes on the stack, the pair a granted
            # trigger already carried, so it resolves after the grant has gone
            # with its source (608.2).
            zones = tuple(ability.active_zones or ())
            if zones and zones != (Zone.BATTLEFIELD,):
                # A grant lives on a *permanent*, and `abilities_of` only derives
                # one there. Granted cycling would load clean and never be
                # offered from the hand it is printed to work in.
                raise DslError(
                    f"{where}.grantable[{ability.index}]: a granted activated "
                    f"ability works on the battlefield only, not from "
                    f"{[z.value for z in zones]}"
                )
            continue
        if ability.is_static and ability.static:
            # A granted **static**. Inspiring Leader: "Commander creatures you
            # own have "Creature tokens you control get +2/+2."" -- and the
            # thing that makes it work is that a granted static needs no code of
            # its own. `abilities_of` appends it to the recipient's list and
            # `characteristics._battlefield_statics` walks that list, so the
            # copy arrives already sourced on the recipient: the quoted anthem's
            # "you" is the commander creature's controller, and two commander
            # creatures are two entries, so the tokens get +4/+4 without
            # anything counting them.
            #
            # The near miss -- a `buff` on the Background itself under an
            # `{"exists": {"is_commander": true}}` condition -- is a different
            # card three ways: it does not stack per commander creature, it
            # pumps the *Background controller's* tokens rather than each
            # granted commander's controller's, and it does not travel with a
            # commander that changes hands.
            effect = str(ability.static.get("effect"))
            if effect not in GRANTABLE_STATIC_EFFECTS:
                raise DslError(
                    f"{where}: {effect!r} is read off printed faces "
                    f"(`_ability_statics` or `_active_player_statics`), so a "
                    f"granted one would load clean and never apply; grantable "
                    f"statics are {sorted(GRANTABLE_STATIC_EFFECTS)}"
                )
            for key in ("affects", "blockers"):
                _refuse_granted_chosen_qualities(
                    ability.static.get(key), f"{where}.grantable[{ability.index}].{key}"
                )
            continue
        # A chapter, which is all that is left: its trigger compares the lore
        # counters on its own source, so granted to anything else it would wait
        # for a number nothing reaches. Granting a keyword is what
        # `grant_keyword` is for; `docs/rules-coverage.md` records the rest.
        raise DslError(
            f"{where}: only triggered, activated and static abilities can be granted, "
            f"not {ability.kind.value}"
        )

    _check_grant_targets(model, abilities, grantable, where)
    emblems = _compile_emblems(model, where)
    _check_emblem_references(model, abilities, grantable, emblems, where)

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

    # Gift is two halves the same way kicker is, and half of it fails just as
    # quietly -- more quietly, in fact, because a gift costs nothing, so a card
    # declaring one and reading it nowhere is not even more expensive than the
    # card it pretends to be. It is simply a cast line the player is offered
    # that does exactly what the other line does.
    #
    # Either spelling counts as reading it, because the two halves of the
    # printed mechanic are read by different vocabulary: "if the gift wasn't
    # promised" is the `{"gift_promised": …}` condition, and "**they** create a
    # tapped 1/1 blue Fish" is the `"gift_recipient"` player spec. Parting Gust
    # writes both; a card whose whole gift line is "gift a card (they draw a
    # card)" writes only the second, and refusing it would be refusing the
    # simplest printed shape the mechanic has.
    reads_gift = _mentions_gift(model)
    if reads_gift and model.gift is None:
        raise DslError(
            f"{where}: reads the gift ('gift_promised' or the 'gift_recipient' "
            f"player spec) but has no 'gift' declaration"
        )
    if model.gift is not None:
        if not model.gift.strip():
            # The string is what is promised, and the residual gate compares it
            # against the printed line -- so an empty one cannot claim anything
            # and would put "(gift  to Bob)" on the action.
            raise DslError(f"{where}: 'gift' must name what is promised, e.g. 'a tapped Fish'")
        if not reads_gift:
            raise DslError(
                f"{where}: has a 'gift' promise that nothing reads via "
                f"'gift_promised' or the 'gift_recipient' player spec"
            )

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
    # Bestow (702.103a). An alternative cost like evoke, and the two guards it
    # needs are both about the *type line*: a non-creature with bestow has
    # nothing to "become a creature again" as, and a card that is already an
    # Aura would be one twice over -- the second Aura-ness silently doing
    # nothing while the card looks implemented.
    bestow = ManaCost.parse(model.bestow) if model.bestow else None
    if bestow is not None:
        if "Creature" not in model.types:
            raise DslError(
                f"{where}: 'bestow' is only on creature cards (702.103a) -- there is "
                f"nothing for it to become a creature again as"
            )
        if "Aura" in model.subtypes:
            raise DslError(
                f"{where}: 'bestow' on a card that is already an Aura -- bestow is "
                f"what makes it one, and this card would be an Aura twice"
            )
    # Meld needs both halves of its own sentence: a partner with nothing to
    # become, or a result with no partner to meld with, is a trigger that can
    # never fire and a card that looks implemented.
    if (model.melds_with is None) != (model.melds_into is None):
        raise DslError(
            f"{where}: 'melds_with' and 'melds_into' come as a pair -- one alone is "
            f"a meld that can never happen"
        )
    # Mutate (702.140a). A creature card, for bestow's reason and one more: the
    # merged permanent *is* the top card, so a non-creature on top would make a
    # creature stop being one -- which is a different keyword.
    mutate = ManaCost.parse(model.mutate) if model.mutate else None
    if mutate is not None and "Creature" not in model.types:
        raise DslError(
            f"{where}: 'mutate' is only on creature cards (702.140a) -- the merged "
            f"permanent is the card on top, and this one is not a creature"
        )
    if mutate is not None and bestow is not None:
        # Both are alternative costs that land somewhere other than the
        # battlefield on their own, and no printing has both. Offered together
        # they would be two lines whose targets mean different things.
        raise DslError(f"{where}: a card may not have both 'bestow' and 'mutate'")
    reads_evoked = _mentions_condition(model, "evoked")
    if reads_evoked and evoke is None:
        raise DslError(f"{where}: reads the 'evoked' condition but has no 'evoke' cost")
    if evoke is not None and not reads_evoked:
        raise DslError(f"{where}: has an 'evoke' cost that no effect reads via 'evoked'")
    if emerge is not None and emerge.x_count:
        raise DslError(f"{where}: an emerge cost with X is not implemented")
    if evoke is not None:
        # What no alternative may ever be is *the same price as the printed
        # one*: that is one cast offered twice, and the second line is dead
        # weight nobody would notice however the card labels it.
        if evoke.mana_value() == mana_cost.mana_value():
            raise DslError(
                f"{where}: evoke {model.evoke!r} costs the same as the printed cost -- "
                f"the same cast offered twice, and nobody would take the second"
            )
        # Costlier than printed is dead weight too, but only for evoke *proper*,
        # which buys nothing at all with the price: a Mulldrifter evoked is a
        # Mulldrifter that dies, so paying more for it is a line no player takes.
        # It is not dead weight for **dash**, which is this same mechanism under
        # a different word and where the extra mana buys haste plus the enters
        # trigger for a turn before the body goes back -- Riders of Rohan is
        # printed {3}{R}{W} with dash {4}{R}{W}, and that is a trade players
        # take. `evoke_label` is the card saying which of the two it is, in the
        # action list and on screen, so it is what this guard reads: the default
        # label keeps evoke's discount-only invariant, and a card that has
        # renamed the cost has already said out loud that it is not evoke.
        if evoke.mana_value() > mana_cost.mana_value() and model.evoke_label == "evoked":
            raise DslError(f"{where}: evoke {model.evoke!r} is not cheaper than the printed cost")

    if model.rebound and set(model.types) & {"Creature", "Land", "Artifact", "Enchantment"}:
        # Rebound replaces the *graveyard* a spell would go to, so a permanent
        # spell never reaches the rider -- it enters the battlefield instead.
        # A permanent card carrying it would load, look implemented and never
        # rebound once. No printing has it, either: 702.87 is instants and
        # sorceries only.
        raise DslError(
            f"{where}: 'rebound' only means anything on an instant or sorcery -- "
            f"a permanent spell enters the battlefield and never reaches the rider"
        )
    if model.exiles_itself and set(model.types) & {
        "Creature",
        "Land",
        "Artifact",
        "Enchantment",
    }:
        # Rebound's guard, for rebound's reason: the rider replaces the
        # graveyard, and a permanent spell enters the battlefield instead. A
        # permanent carrying it would load, read as implemented, and never
        # exile itself once.
        raise DslError(
            f"{where}: 'exiles_itself' only means anything on an instant or "
            f"sorcery -- a permanent spell enters the battlefield instead"
        )
    if model.exiles_itself and model.rebound:
        # Both replace the graveyard with exile, and rebound also promises the
        # card back at the next upkeep. Written together, whichever the code
        # read first would decide whether the spell is cast again for free --
        # and no printing says both.
        raise DslError(
            f"{where}: 'exiles_itself' and 'rebound' both send the spell to "
            f"exile, and only one of them hands it back"
        )
    # An additional cost paid at cast time -- casualty, replicate, Deadly
    # Dispute. Unlike kicker it is a full `Cost`, and unlike kicker it need not
    # be read by anything: "sacrifice an artifact" is the whole of Deadly
    # Dispute's cost and no clause reads it back. So there is no half-a-cost
    # guard here; what is guarded is the two modifiers, which mean nothing alone.
    if model.additional_cost is not None and model.additional_cost.mana_reduction:
        # `_cast_variant` folds an additional cost's mana *into* the spell's price
        # with `card.additional_cost.mana.scaled(...)`, so nothing ever prices
        # this node on its own and a reduction here is never read. Refused rather
        # than dropped: it would load clean and cost the player the full amount.
        raise DslError(
            f"{where}.additional_cost: 'mana_reduction' is not read here -- an "
            f"additional cost's mana is folded into the spell's price. Put the "
            f"reduction on the card's 'cost_reduction' instead"
        )
    additional_cost = _compile_cost(model.additional_cost, where) if model.additional_cost else None
    additional_cost_options: tuple = ()
    if model.additional_cost_options:
        if model.additional_cost is not None:
            # Two spellings of one slot; whichever won would be the card and the
            # other would load clean and never be charged.
            raise DslError(
                f"{where}: give 'additional_cost' or 'additional_cost_options', "
                f"not both -- the options list already holds every branch"
            )
        if len(model.additional_cost_options) < 2:
            # One branch is not a choice, and writing it this way hides an
            # ordinary additional cost behind machinery nobody needs to read.
            raise DslError(
                f"{where}: 'additional_cost_options' is a choice between prices, "
                f"so it needs at least two -- use 'additional_cost' for one"
            )
        if model.additional_repeatable:
            # "Discard a card or pay 3 life, any number of times" is not a
            # printed shape, and the two features disagree about what a cast
            # line means: one per branch against one per number of times paid.
            raise DslError(
                f"{where}: 'additional_repeatable' does not compose with 'additional_cost_options'"
            )
        additional_cost_options = tuple(
            _compile_cost(option, f"{where}.additional_cost_options[{i}]")
            for i, option in enumerate(model.additional_cost_options)
        )
    additional_optional = model.additional_optional
    additional_repeatable = model.additional_repeatable

    # Multikicker (702.32b) is the *name* for the shape above, not a new one:
    # "you may pay an additional {1}{W} any number of times" is exactly
    # `additional_cost` + `additional_optional` + `additional_repeatable`, which
    # is replicate's slot, and `Action.additional_times` already carries how
    # many. So this desugars rather than adding machinery -- what it buys is the
    # word, which is what the residual gate and the fidelity audit need in order
    # to say the printed line has a claimant.
    multikicker = ManaCost.parse(model.multikicker) if model.multikicker else None
    if multikicker is not None:
        if multikicker.x_count:
            # Same refusal as kicker's: a repeatable cost with X would have to
            # ask for a number per payment, and no printing does that.
            raise DslError(f"{where}: a multikicker cost with X is not implemented")
        if multikicker.mana_value() == 0:
            # Free and repeatable is an infinite loop of cast lines, capped only
            # by MAX_ADDITIONAL_TIMES -- six free kicks, which is no card.
            raise DslError(f"{where}: multikicker {model.multikicker!r} costs nothing")
        if additional_cost is not None:
            # Two spellings of one slot. Whichever won would be the card, and
            # the other would load clean and never be charged.
            raise DslError(
                f"{where}: give 'multikicker' or 'additional_cost', not both -- "
                f"multikicker *is* a repeatable optional additional cost"
            )
        if model.additional_optional or model.additional_repeatable:
            raise DslError(
                f"{where}: 'multikicker' already implies 'additional_optional' and "
                f"'additional_repeatable' -- do not set them alongside it"
            )
        if not _mentions_condition(model, "additional_paid"):
            # Half a kicker, in the exact sense the guard above catches for
            # `kicker`: a spell that charges more and does the same thing.
            # `additional_cost` has no such guard because "sacrifice an artifact"
            # can be the whole of a cost, but multikicker never is -- "any number
            # of times" only means something to a card that counts the times.
            raise DslError(
                f"{where}: has a 'multikicker' cost that no effect reads via "
                f"'additional_paid' -- counting the kicks is what the mana buys"
            )
        additional_cost = _compile_cost(CostModel(mana=model.multikicker), f"{where}.multikicker")
        additional_optional = True
        additional_repeatable = True

    if additional_cost is None and (model.additional_optional or model.additional_repeatable):
        raise DslError(
            f"{where}: 'additional_optional' and 'additional_repeatable' need an "
            f"'additional_cost' to modify"
        )
    if model.additional_repeatable and not model.additional_optional:
        # "Any number of times" includes zero. A mandatory repeatable cost would
        # be offered from one upwards, which is not a printing and would make
        # every replicate card unplayable without the extra mana.
        raise DslError(
            f"{where}: 'additional_repeatable' needs 'additional_optional' -- "
            f'"any number of times" includes none'
        )
    if _mentions_condition(model, "additional_paid") and additional_cost is None:
        raise DslError(
            f"{where}: reads 'additional_paid' but has no 'additional_cost', so it "
            f"would always read 0"
        )
    # Strive: "This spell costs {1}{W} more to cast for each target beyond the
    # first." A cost *increase* (601.2f) whose size is the number of targets
    # declared at 601.2c, so it only means something beside a target list whose
    # size the caster picks -- and every strive printing is exactly one "any
    # number of target …" spec. Anything else is refused rather than guessed:
    # with a fixed count the surcharge is a constant that belongs in the mana
    # cost, and with two specs "beyond the first" would have to decide which
    # spec's refs count.
    strive = ManaCost.parse(model.strive) if model.strive else None
    if strive is not None:
        if strive.x_count:
            raise DslError(f"{where}: a strive cost with X is not implemented")
        if strive.mana_value() == 0:
            raise DslError(f"{where}: strive {model.strive!r} costs nothing")
        if len(targets) != 1 or targets[0].count != "any" or mode_targets:
            raise DslError(
                f"{where}: 'strive' prices the targets of one 'any number of target' "
                f"spec -- give the card exactly one target spec with count 'any'"
            )
        if model.overload or model.morph or model.bestow or model.mutate:
            # Each of these casts the card with targets the rule supplies (none,
            # or "enchant creature"), so the surcharge would price a list the
            # card never declared. No strive printing has any of them.
            raise DslError(
                f"{where}: 'strive' does not compose with overload, morph, bestow or mutate"
            )
    if model.dredge < 0:
        raise DslError(f"{where}: 'dredge' is how many cards are milled, so it cannot be negative")
    if model.morph_counter and model.morph is None:
        raise DslError(f"{where}: 'morph_counter' is megamorph's rider and needs a 'morph' cost")
    if model.morph is not None and "Creature" not in model.types:
        # 702.37a: only a creature card may be cast face down, because what it
        # becomes is a 2/2 *creature*. A non-creature carrying it would be
        # castable face down and unable to turn up into anything.
        raise DslError(f"{where}: 'morph' is only on creature cards")
    if model.splice is not None and model.targets:
        # A spliced card's effects run inside the *host* spell's context, so a
        # target id written here would either be missing or -- worse -- collide
        # with one of the host's and quietly point somewhere else. Refused
        # rather than resolved: the divergence is recorded in
        # rules-coverage.md, and a card that needs its own target is a card this
        # cannot express yet.
        raise DslError(
            f"{where}: a spliced card may not declare its own targets -- its "
            f"effects run in the host spell's context"
        )
    # Disturb needs both halves, and each is silent alone. Without a
    # `graveyard_cost` there is no cast to arrive transformed; without a
    # `back_face` there is nothing to transform *into*, so the card would be
    # cast for its disturb cost and arrive as its front face -- which is
    # flashback wearing the wrong word.
    if model.graveyard_cast_transformed:
        if model.graveyard_cost is None and model.flashback is None:
            raise DslError(
                f"{where}: 'graveyard_cast_transformed' needs a 'graveyard_cost' -- "
                f"there is no cast for it to transform"
            )
        if model.back_face is None:
            raise DslError(
                f"{where}: 'graveyard_cast_transformed' needs a 'back_face' to "
                f"transform into; without one the card arrives as its front face"
            )
    # A second castable face, and the two ways to write half of one. `adventure`
    # with nothing to adventure *from* is a card that exiles itself on
    # resolution and is never seen again -- which is aftermath, silently, under
    # the wrong word. `second_face_zone` alone is a restriction on a cast nobody
    # offers.
    if model.second_face is None:
        if model.adventure:
            raise DslError(
                f"{where}: 'adventure' needs a 'second_face' -- the Adventure is "
                f"the half that gets cast, and there is nothing here to cast"
            )
        if model.second_face_zone != "hand":
            raise DslError(
                f"{where}: 'second_face_zone' needs a 'second_face' -- there is no "
                f"second cast for it to restrict"
            )
    # Fuse is a *third* line on a split card, so it needs the other two: a card
    # with nothing to fuse to is an ordinary spell that says a word, and fusing
    # onto a graveyard-only half would offer from hand a line that half may not
    # be cast from.
    if model.fuse:
        if model.second_face is None:
            raise DslError(f"{where}: 'fuse' needs a 'second_face' -- there is only one half here")
        if model.second_face_zone != "hand":
            raise DslError(
                f"{where}: 'fuse' is cast from hand (702.102a), and this card's second "
                f"half may only be cast from the {model.second_face_zone}"
            )
        if model.adventure:
            raise DslError(f"{where}: a card may not have both 'adventure' and 'fuse'")
    # 715.1: an adventurer card is a creature card, and the Adventure is an
    # instant or sorcery. Without the first half the front face would resolve
    # straight back to the graveyard from exile and the "cast it later" half of
    # the keyword would be unreachable; both are checked once the pool is known,
    # where the second face can actually be looked up.
    # Overload is two halves like kicker, and half of it fails the same silent
    # way: a cost nobody reads is a more expensive cast that does the same
    # thing, and an `{"overloaded": true}` clause with no cost can never fire.
    overload = ManaCost.parse(model.overload) if model.overload else None
    reads_overloaded = _mentions_condition(model, "overloaded")
    if reads_overloaded and overload is None:
        raise DslError(f"{where}: reads the 'overloaded' condition but has no 'overload' cost")
    if overload is not None and not reads_overloaded:
        raise DslError(
            f"{where}: has an 'overload' cost that no effect reads via 'overloaded' -- "
            f"the text change is what the extra mana buys"
        )
    if overload is not None and any(not t.optional for t in model.targets):
        # An overloaded spell is cast with **no** targets (702.96a replaces every
        # "target" with "each"), so a required target would make the overload
        # line uncastable -- silently, since the printed line is still offered.
        raise DslError(
            f"{where}: an overload card's targets must all be 'optional' -- an "
            f"overloaded spell is cast with no targets at all"
        )
    if model.buyback and model.kicker is None:
        # Buyback *is* a kicker with a rider. Without the cost there is nothing
        # to pay and the rider never fires, so the card reads "buyback" and
        # goes to the graveyard like anything else.
        raise DslError(f"{where}: 'buyback' needs a 'kicker' cost to attach to")
    if model.emerge_subtype is not None and model.emerge is None:
        # A narrowing with nothing to narrow. The card would look like an
        # offering card and have no alternative cast line at all.
        raise DslError(f"{where}: 'emerge_subtype' needs an 'emerge' cost to narrow")
    alternative_cost = None
    alternative_condition = None
    if model.alternative_cost is not None:
        spec = dict(model.alternative_cost)
        # A full cost node plus the gate. `CostModel` is the same vocabulary an
        # activated ability's `cost` uses, so "pay 1 life and exile a blue card
        # from your hand" needs no second spelling and a typo here fails at
        # load exactly where it fails there.
        unknown = set(spec) - {"condition"} - set(CostModel.model_fields)
        if unknown:
            raise DslError(f"{where}.alternative_cost: unsupported keys {sorted(unknown)}")
        # …minus the keys that charge the **source permanent**. The source a
        # cast-time cost is paid with is the *spell*, sitting in hand on its way
        # to the stack -- so these each name something that is not there.
        # `costs.can_pay` fails closed on every one of them, which means a card
        # written this way would load clean and never once be offered the line:
        # exactly the silently inert card `exile_self` on an `active_zones:
        # ["hand"]` ability used to produce.
        misplaced = set(spec) & NOT_A_CAST_TIME_COST
        if misplaced:
            raise DslError(
                f"{where}.alternative_cost: {sorted(misplaced)} charge the source "
                f"permanent, and the source of a cast-time cost is the spell "
                f"itself -- the line would load and never be castable"
            )
        alternative_condition = spec.pop("condition", None)
        try:
            cost_model = CostModel.model_validate(spec)
        except Exception as exc:  # pydantic ValidationError
            raise DslError(f"{where}.alternative_cost: {exc}") from exc
        alternative_cost = _compile_cost(cost_model, f"{where}.alternative_cost")
        if alternative_cost.mana_reduction is not None:
            # "Costs {X} less to cast this way" is flashback's, and only
            # `costs.variant_reduction` reads it -- off the flashback branch
            # alone. Written here it would load clean and never be applied.
            raise DslError(
                f"{where}.alternative_cost: 'mana_reduction' is the graveyard "
                f"cost's rider; nothing prices this branch through "
                f"`variant_reduction`, so it would load and be ignored"
            )
        pays_something = not alternative_cost.charges_nothing()
        if not alternative_cost.mana.text and not pays_something:
            # It *replaces* the printed cost, so with nothing on the node the
            # card would be castable for free whenever the condition held.
            raise DslError(f"{where}.alternative_cost: needs 'mana' or a non-mana payment")
        if alternative_condition is None and not pays_something:
            # Unconditional is what `evoke` already is. A card spelling it this
            # way would be offered twice at two prices with nothing to choose
            # between them.
            #
            # A cost that charges something *other* than mana is exempt: Force
            # of Will's pitch is unconditional and printed, and it is not evoke
            # -- there is no mana price on it at all, and what it takes instead
            # is the reason it is a fair card.
            raise DslError(
                f"{where}.alternative_cost: needs a 'condition' -- an "
                f"unconditional alternative *mana* cost is 'evoke'"
            )
        if alternative_condition is not None:
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
        if flashback.x_value is not None:
            # The refusal above says X from the graveyard is not implemented, and
            # a defined X is still an X: `costs.ability_mana` -- the one reader of
            # `x_value` -- never sees a graveyard cost, which is priced by
            # `costs.variant_reduction` instead.
            raise DslError(
                f"{where}: 'x_value' is an activated ability's, and a graveyard "
                f"cost is not priced through `ability_mana`"
            )
        if flashback.mana_reduction is not None:
            # "…costs {X} less to cast **this way**". The one alternative cost
            # modelled as a full `Cost`, so the one that can carry a variant-
            # scoped rider; read by the flashback branch of
            # `legality._cast_variant` and `game._cast` via
            # `costs.variant_reduction`, and by nothing on the hand-cast path.
            _validate_cost_reduction(
                flashback.mana_reduction, f"{where}.graveyard_cost.mana_reduction"
            )
        if model.retrace:
            # Both widen legality to the graveyard and each replaces the other's
            # answer to "what does it cost from there".
            raise DslError(f"{where}: a card may not have both a graveyard cost and 'retrace'")
    if graveyard_spec is None and model.graveyard_cast != "exile":
        # A destination with nothing to send there. Silently ignoring it would
        # let a card claim to be an escape card and never be castable at all.
        raise DslError(f"{where}: 'graveyard_cast' needs a 'graveyard_cost' to describe")
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
            f"{where}: reads the 'clash_won' binding but never clashes, so it would always read 0"
        )

    # Dice are the same two halves, and fail the same way. A roll is never the
    # effect -- "roll X six-sided dice" on its own does nothing a player can
    # see -- and a `{"rolled": …}` with no roll behind it reads 0 for ever, so
    # Luck Bobblehead would make no Treasures and never win. Both load cleanly.
    rolls_dice = _mentions_pair(model, "op", "roll_dice")
    reads_roll = _mentions_condition(model, "rolled")
    if rolls_dice and not reads_roll:
        raise DslError(
            f"{where}: rolls dice that no effect reads via {{'rolled': …}} -- "
            f"a roll nothing reads changes nothing"
        )
    if reads_roll and not rolls_dice:
        raise DslError(
            f"{where}: reads a roll with {{'rolled': …}} but never rolls any "
            f"dice, so it would always read 0"
        )

    _refuse_seats_read_as_objects(model, where)

    # `of` names a *different* permanent to ask about -- Celes, Rune Knight's
    # "…or was cast from a graveyard", which is about the creature that just
    # entered rather than about Celes. The guard below is about a card asking
    # after **itself**, so a mention carrying `of` is not one of those and does
    # not need a graveyard cost of its own.
    reads_from_graveyard = _mentions(
        model, lambda node: "cast_from_graveyard" in node and "of" not in node
    )
    if reads_from_graveyard and flashback is None:
        raise DslError(
            f"{where}: reads the 'cast_from_graveyard' condition but has no "
            f"'graveyard_cost', so it could never be true"
        )

    _validate_was_cast_placement(model, where)
    _validate_enchanted_player(model, where)

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
        loyalty=model.loyalty,
        final_chapter=final_chapter,
        prepared_face=model.prepared_face,
        keywords=frozenset(model.keywords),
        colors=colors,
        color_identity=identity,
        targets=targets,
        mode_targets=mode_targets,
        spell_effects=tuple(model.spell_effects),
        replacements=_implied_replacements(model),
        abilities=abilities,
        grantable_abilities=grantable,
        emblems=emblems,
        type_line=build_type_line(supertypes, types, subtypes),
        is_token=model.is_token,
        back_face=model.back_face,
        second_face=model.second_face,
        second_face_zone=model.second_face_zone,
        adventure=model.adventure,
        fuse=model.fuse,
        uncounterable=model.uncounterable,
        split_second=model.split_second,
        buyback=model.buyback,
        rebound=model.rebound,
        exiles_itself=model.exiles_itself,
        overload=overload,
        graveyard_cast_transformed=model.graveyard_cast_transformed,
        dredge=model.dredge,
        madness=ManaCost.parse(model.madness) if model.madness else None,
        miracle=ManaCost.parse(model.miracle) if model.miracle else None,
        foretell=ManaCost.parse(model.foretell) if model.foretell else None,
        epic=model.epic,
        morph=ManaCost.parse(model.morph) if model.morph else None,
        morph_counter=model.morph_counter,
        splice=ManaCost.parse(model.splice) if model.splice else None,
        splice_onto=model.splice_onto,
        additional_cost=additional_cost,
        additional_cost_options=additional_cost_options,
        additional_optional=additional_optional,
        additional_repeatable=additional_repeatable,
        kicker_label=model.kicker_label,
        kicker=kicker,
        gift=model.gift,
        multikicker=multikicker,
        strive=strive,
        evoke=evoke,
        bestow=bestow,
        mutate=mutate,
        melds_with=model.melds_with,
        melds_into=model.melds_into,
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


def _compile_threshold(
    model: AbilityModel, kind: AbilityKind, where: str
) -> tuple[str, int] | None:
    """A station symbol's ``{"counter": "charge", "at_least": 12}``, or ``None``.

    Activated abilities only. That is what the two Planets print, and it is
    where the gate is honoured: `abilities_of` leaves the ability out, and
    `legality`, the mana solver and the AI all read that list. A gated static or
    trigger would also have to reach `_ability_statics`, the player statics and
    the trigger collectors, which read printed faces -- so one is refused here
    rather than loading as an ability that is always on.
    """
    spec = model.threshold
    if spec is None:
        return None
    if kind is not AbilityKind.ACTIVATED:
        raise DslError(
            f"{where}.threshold: only an activated ability may be gated on a counter "
            f"count so far, not a {kind.value} one"
        )
    unknown = set(spec) - {"counter", "at_least"}
    if unknown:
        raise DslError(f"{where}.threshold: unsupported keys {sorted(unknown)}")
    counter = spec.get("counter")
    at_least = spec.get("at_least")
    if not isinstance(counter, str) or not counter:
        raise DslError(f"{where}.threshold.counter: a counter kind, got {counter!r}")
    _check_counter_kind(counter, f"{where}.threshold.counter")
    if isinstance(at_least, bool) or not isinstance(at_least, int) or at_least < 1:
        # "0+" would be an ability the permanent always has, which is no gate.
        raise DslError(
            f"{where}.threshold.at_least: a positive number of counters, got {at_least!r}"
        )
    return (counter, at_least)


def _check_threshold_order(abilities: tuple[Ability, ...], where: str) -> None:
    """Gated abilities come last, in rising order, on one counter.

    Not tidiness: `Action.ability_index`, `StackItem.ability_index` and the
    ledger address an ability by position in `abilities_of`, and resolution reads
    the printed list at that position. Leaving out a gated ability from the
    *middle* would shift every ability after it, so a resolving "{T}: Add {W}"
    could run the Planet's 12+ line instead. Kept as a suffix, and rising, an
    ability that is missing only ever takes the ones after it with it, and every
    index that is still offered means what it printed. Station cards print their
    striations exactly this way.
    """
    gated_seen = False
    last: tuple[str, int] | None = None
    for i, ability in enumerate(abilities):
        if ability.threshold is None:
            if gated_seen:
                raise DslError(
                    f"{where}.abilities[{i}]: an ungated ability after a threshold "
                    f"ability; gated abilities come last"
                )
            continue
        gated_seen = True
        if last is not None and (
            ability.threshold[0] != last[0] or ability.threshold[1] < last[1]
        ):
            raise DslError(
                f"{where}.abilities[{i}].threshold: gated abilities count one counter "
                f"in rising order, got {ability.threshold} after {last}"
            )
        last = ability.threshold


#: The only keys a Class's level line may set. 716.2a says everything else the
#: ability is -- its timing, its restriction and its effect -- so a line that
#: writes any of those is a line the loader would have to either ignore or
#: believe over the rule.
_LEVEL_LINE_KEYS = frozenset({"kind", "text", "level", "cost", "sorcery_speed_only"})


def _compile_ability(model: AbilityModel, index: int, card_where: str) -> Ability:
    """One printed ability, with a Class's level read off it (716).

    ``kind: "level"`` is compiled as the activated ability 716.2a says it is.
    ``level`` on anything else is checked here and stamped on the ability the
    ordinary compiler builds, so no branch below has to know Classes exist.
    """
    import dataclasses

    where = f"{card_where}.abilities[{index}]"
    if model.kind == "level":
        return _compile_level_line(model, index, card_where, where)
    if model.level is None:
        return _compile_printed_ability(model, index, card_where)
    if model.level < 2:
        # Level 1 is 716.2c's "always there", which is what omitting the key
        # says. Written out it reads as a gate and gates nothing; below 1 there
        # is no level a Class can be.
        raise DslError(
            f"{where}: 'level' is the level band an ability is printed under, from 2 "
            f"up; a level-1 ability is always present and omits the key (got {model.level})"
        )
    if model.kind in ("chapter", "reflexive"):
        # A chapter is a Saga's, and a Saga is not a Class. A reflexive ability
        # is fired by the op above it, which is the thing to gate.
        raise DslError(f"{where}: 'level' does not mean anything on a {model.kind} ability")
    if list(model.active_zones) != ["battlefield"]:
        # A level is a property of a permanent. A card in a graveyard has none
        # to be at, so a gate there is either always shut or always open, and
        # neither is what "Level 2" printed on the card means.
        raise DslError(
            f"{where}: a level-gated ability only exists on the battlefield, "
            f"not in {model.active_zones}"
        )
    ability = _compile_printed_ability(model, index, card_where)
    return dataclasses.replace(ability, level=model.level)


def _compile_level_line(
    model: AbilityModel, index: int, card_where: str, where: str
) -> Ability:
    """ "{W}: Level 2" -- 716.2a, which is a whole activated ability in four words.

    "[Cost]: This Class's level becomes N. Activate only if this Class is level
    N-1 and only as a sorcery." The card prints only the cost and the N, so
    those are all a card writes; the loader supplies the timing, the
    `become_level` effect, and `Ability.becomes_level` for legality's
    restriction. The same reasoning a chapter's trigger is supplied on: every
    Class in print would otherwise write the same three things, and any one of
    them could write one wrong.
    """
    import dataclasses

    if model.level is None or model.level < 2:
        raise DslError(
            f"{where}: a level line needs the 'level' it gains, 2 or more "
            f"(\"{{W}}: Level 2\" is level 2; every Class starts at 1)"
        )
    if model.cost is None:
        raise DslError(f"{where}: a level line needs the 'cost' printed before \"Level\"")
    extra = set(model.model_fields_set) - _LEVEL_LINE_KEYS
    if extra or (model.sorcery_speed_only is False and "sorcery_speed_only" in model.model_fields_set):
        raise DslError(
            f"{where}: a level line is its cost and its level; rule 716.2a supplies "
            f"the rest, so it cannot also set {sorted(extra) or ['sorcery_speed_only: false']}"
        )
    activated = model.model_copy(
        update={"kind": "activated", "level": None, "sorcery_speed_only": True}
    )
    ability = _compile_printed_ability(activated, index, card_where)
    return dataclasses.replace(
        ability,
        effects=({"op": "become_level", "level": model.level},),
        becomes_level=model.level,
    )


def _check_class_levels(model: CardModel, abilities: tuple[Ability, ...], where: str) -> None:
    """The card-level half of 716: the ladder has to be a ladder.

    Refused, each because it loads clean and plays as a different card:

    - level lines or level-gated abilities on a card with no ``Class`` subtype,
      the Saga refusal's reason: the words are the mechanic's, and a card that is
      not a Class is not one.
    - two lines for one level, or a gap in the ladder. 716.2a lets level N be
      bought only at level N-1, so a Class whose lines are 2 and 4 can never
      reach 4, and a second "Level 2" is a second price for one level.
    - an ability printed under a level no line reaches. It could never be
      present, which is a printed line the card claims and never does.

    A ``Class`` with no levels at all is accepted and inert, for the reason a
    ``Saga`` with no chapters is: it is what an unimplemented one looks like.
    """
    lines = sorted(a.becomes_level for a in abilities if a.becomes_level is not None)
    gated = sorted({a.level for a in abilities if a.level is not None})
    waits = any(a.trigger is not None and a.trigger.event == "becomes_level" for a in abilities)
    if not lines and not gated and not waits:
        return
    if "Class" not in model.subtypes:
        raise DslError(
            f"{where}: level lines and level-gated abilities need the 'Class' subtype (716)"
        )
    if lines != list(range(2, len(lines) + 2)):
        raise DslError(
            f"{where}: a Class's level lines must be one each for 2, 3, ... with no gap "
            f"(got {lines}); 716.2a only lets level N be gained from level N-1"
        )
    top = lines[-1] if lines else 1
    for ability in abilities:
        spec = ability.trigger
        if spec is None or spec.event != "becomes_level" or spec.level is None:
            continue
        # "When this Class becomes level 3" on a Class whose lines stop at 2
        # waits for a level nothing can reach; printed under level 3 on a
        # "becomes level 2" trigger, it is not on the Class at the moment it
        # would fire.
        if spec.level > top:
            raise DslError(
                f"{where}: abilities[{ability.index}] waits for level {spec.level} "
                f"but the level lines only reach {top}"
            )
        if ability.level is not None and ability.level > spec.level:
            raise DslError(
                f"{where}: abilities[{ability.index}] is printed under level "
                f"{ability.level}, so it is not there when the Class becomes level "
                f"{spec.level}"
            )
    if gated and gated[-1] > top:
        raise DslError(
            f"{where}: an ability is printed under level {gated[-1]} but the level "
            f"lines only reach {top}, so it could never be present"
        )


def _compile_printed_ability(model: AbilityModel, index: int, card_where: str) -> Ability:
    where = f"{card_where}.abilities[{index}]"
    kind = AbilityKind(model.kind)
    if (model.activate_steps or model.once_each_turn) and kind is not AbilityKind.ACTIVATED:
        # Both are activation restrictions. On a trigger or a static they would
        # load and be ignored, leaving a card that reads "only once each turn"
        # and fires every time. Checked before the static branch returns.
        raise DslError(
            f"{where}: 'activate_steps' and 'once_each_turn' restrict *activating*, "
            f"so they only mean anything on an activated ability"
        )

    threshold = _compile_threshold(model, kind, where)

    if model.chapter is not None and kind is not AbilityKind.CHAPTER:
        # Silently ignored it would produce a card that reads "II --" and fires
        # on whatever its own trigger says, which is the shape of every other
        # misplaced-key refusal in this function.
        raise DslError(
            f"{where}: 'chapter' only means anything on a chapter ability, "
            f"not on a {kind.value} one"
        )

    if model.id is not None and kind is not AbilityKind.REFLEXIVE:
        # The id exists so a `reflexive_trigger` op can name *which* "when you
        # do" it means. On any other kind nothing ever reads it, and a card that
        # writes one is a card whose author believed something was wired up.
        raise DslError(
            f"{where}: 'id' only means anything on a reflexive ability, not on a {kind.value} one"
        )

    if kind is AbilityKind.STATIC:
        return _compile_static(model, index, where)

    # How many modes a mode-owned target may point at, and `None` when there is
    # no single modal question to hang one on -- the same test
    # `Ability.cast_time_modes` makes, asked here because the loader has to
    # refuse a `mode` the engine would never get to ask about.
    ability_modes = (
        top_level_mode_spec(model.effects) if count_mode_specs(model.effects) == 1 else None
    )
    all_targets = _compile_targets(
        model.targets,
        where,
        # 603.3d puts a triggered ability's modes *and* its targets at the one
        # moment it is put on the stack, which is the moment a mode-owned target
        # needs. An activated ability has no such moment -- see
        # `_check_mode_targets`.
        on_trigger=kind in (AbilityKind.TRIGGERED, AbilityKind.CHAPTER),
        mode_count=len(ability_modes.get("modes") or ()) if ability_modes else None,
    )
    targets = tuple(spec for spec in all_targets if spec.mode is None)
    mode_targets: dict[int, tuple[TargetSpec, ...]] = {}
    for spec in all_targets:
        if spec.mode is not None:
            mode_targets[spec.mode] = (*mode_targets.get(spec.mode, ()), spec)
    # Effects still name every spec, mode-owned or not: which bucket a target
    # lives in is about *when it is declared*, not about who may read it.
    target_kinds = {t.id: t.kind for t in all_targets}
    for i, effect in enumerate(model.effects):
        _validate_effect(effect, f"{where}.effects[{i}]", target_kinds)

    cost = (
        _compile_cost(model.cost, where, defines_x=kind is AbilityKind.ACTIVATED)
        if model.cost
        else None
    )
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
        # Three costs remove the source from a non-battlefield zone: cycling
        # discards this card from hand, Simian Spirit Guide exiles it from
        # hand, and embalm exiles it from the graveyard.
        # Unearth is the third shape and pays neither -- its *effect* is what
        # takes the card out ("return this card from your graveyard to the
        # battlefield"), so the property the guard is really after is that the
        # source cannot still be sitting there afterwards, however it left.
        # Forecast is the fourth satisfier and the only one that does not move
        # the card: "activate only during your upkeep, and only once each turn"
        # is not an infinite engine because it may be activated once. Both
        # halves are required -- `once_each_turn` alone would still be a card in
        # hand with a free ability every turn for the whole game, which is what
        # forecast's upkeep window is there to price.
        gated_once = model.once_each_turn and bool(model.activate_steps)
        removes_source = (
            cost.discard_self
            or cost.exile_self
            or cost.exile_self_from_hand
            or cost.exile_from_graveyard is not None
            or _effects_move_source(model.effects)
            or gated_once
        )
        if set(active_zones) - {Zone.BATTLEFIELD} and not removes_source:
            raise DslError(
                f"{where}: an activated ability outside the battlefield needs a cost "
                f"or an unconditional effect that removes its source from that zone "
                f"(got {cost.describe()!r}); "
                f"otherwise it can be activated repeatedly without ever leaving"
            )
    elif kind is AbilityKind.REFLEXIVE:
        # 603.11. The ability is printed on the card and lives in its abilities
        # list -- which is what gets it modes, targets chosen as it is put on
        # the stack, APNAP order and a window to respond in, all for free -- but
        # nothing may ever match it off an *event*. "When you do" names the
        # instruction above it, not something that happens on the board, so the
        # effect that carries out that instruction is the only thing entitled to
        # fire it. Hence no `TriggerSpec` at all: `_candidate_abilities` skips
        # an ability whose `trigger` is None, and `Ability.is_triggered` is
        # False for this kind, so the two independent gates both hold.
        if not model.id:
            raise DslError(
                f"{where}: a reflexive ability needs an 'id' -- "
                f"a 'reflexive_trigger' op has to be able to name it"
            )
        if model.trigger is not None:
            raise DslError(
                f"{where}: a reflexive ability is fired by a 'reflexive_trigger' op, "
                f"so it does not write a trigger of its own"
            )
        if model.cost is not None:
            raise DslError(f"{where}: a reflexive ability is triggered, so it has no cost")
        if not model.effects:
            raise DslError(f"{where}: a reflexive ability with no effects is a blank line")
    elif kind is AbilityKind.CHAPTER:
        # The trigger is **supplied**, not read. There is no word in "II --
        # Create two 2/2 red Human Knight creature tokens" saying when it
        # happens: the whole of the timing is 714.2c, so every Saga in print
        # would otherwise write out the same trigger and any one of them could
        # write it wrong. Same reason the loader supplies `source: "self"` for
        # `self_enters`, and a stronger one -- there is nothing to omit here.
        if model.chapter is None:
            raise DslError(f"{where}: a chapter ability needs a 'chapter' number")
        if model.trigger is not None:
            raise DslError(
                f"{where}: a chapter ability's trigger comes from rule 714.2c, "
                f"so it does not write one"
            )
        if model.cost is not None:
            raise DslError(f"{where}: a chapter ability is triggered, so it has no cost")
        if not model.effects:
            raise DslError(f"{where}: a chapter ability with no effects is a blank line")
        if list(model.active_zones) != ["battlefield"]:
            # 714.2c reads the lore counters on the Saga permanent, and a card in
            # a graveyard has none. The default is right and anything else is a
            # trigger that could never fire.
            raise DslError(
                f"{where}: a chapter ability only works on the battlefield, "
                f"not in {model.active_zones}"
            )
        trigger = TriggerSpec(event="chapter", source="self", chapter=model.chapter)
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
        if model.trigger.defending is not None and model.trigger.event not in DEFENDING_TRIGGERS:
            # Silently ignoring it would produce a card that looks like it reads
            # "attacks you" and fires on everything. The other direction is just
            # as bad and is why the list is a list: `you_attack` carries no
            # defender, so accepting the clause there would load a card that
            # reads "attacks one of your opponents" and fires never.
            raise DslError(
                f"{where}: 'defending' only means anything on "
                f"{' or '.join(repr(e) for e in sorted(DEFENDING_TRIGGERS))}, "
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

        if model.trigger.level is not None and model.trigger.event != "becomes_level":
            # Same reasoning as `counter` below: only BECAME_LEVEL carries a
            # level, so anywhere else this would be a filter that never applies.
            raise DslError(
                f"{where}: 'level' on a trigger only means anything on becomes_level, "
                f"not on {model.trigger.event!r}"
            )
        if model.trigger.event == "becomes_level":
            # "When this Class becomes level 2." Without the number the ability
            # fires at every level, which is the second token copy at level 3
            # the gap record warned about. And it is always *this* Class, so the
            # loader supplies `source: "self"` as it does for `self_enters`.
            if model.trigger.level is None or model.trigger.level < 2:
                raise DslError(
                    f"{where}: a becomes_level trigger needs the 'level' it waits for, "
                    f"2 or more -- every Class enters at 1 and never becomes it"
                )
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
        if model.trigger.counter is not None:
            # "Whenever a vigilance counter is put on this creature." The filter
            # is compared to the kind the primitive was handed, so a near-miss
            # spelling matches nothing and the trigger never fires.
            _check_counter_kind(model.trigger.counter, f"{where}.trigger.counter")

        if model.trigger.mana_ability is not None and model.trigger.event != "ability_activated":
            # Same reasoning as `counter` and `defending` above: only
            # `ability_activated` carries the flag, so accepting it elsewhere
            # would look like the "if it isn't a mana ability" clause and be a
            # restriction that never applies.
            raise DslError(
                f"{where}: 'mana_ability' only means anything on an "
                f"ability_activated trigger, not on {model.trigger.event!r}"
            )

        if model.trigger.nth is not None and model.trigger.event not in ("draw", "spell_cast"):
            # Same reasoning as `counter` and `mana_ability` above: only `draw`
            # and `spell_cast` carry an ordinal, so accepting it elsewhere would
            # look like "your second card each turn" and be a restriction that
            # never matches -- an ability that silently never fires.
            raise DslError(
                f"{where}: 'nth' only means anything on a draw or spell_cast trigger, "
                f"not on {model.trigger.event!r}"
            )
        if model.trigger.nth is not None and model.trigger.nth < 1:
            # Ordinals count from 1. A zeroth or negative card or spell is
            # nothing, so this would silently be an ability that never triggers.
            raise DslError(
                f"{where}: 'nth' is an ordinal from 1; "
                f"no {model.trigger.event} is the {model.trigger.nth}th of a turn"
            )
        if (
            model.trigger.nth is not None
            and model.trigger.event == "spell_cast"
            and model.trigger.filter
            and (unordinal := set(model.trigger.filter) - ORDINAL_FILTER_KEYS)
        ):
            # "Their first noncreature spell" counts the caster's earlier spells
            # this turn against the filter, and those have left the stack: only
            # their printed faces can be asked. A key that reads board state
            # would be checked on this spell and ignored on the ones before it,
            # so the run would be counted against a different filter than the
            # one that fires the ability.
            raise DslError(
                f"{where}: 'nth' on a spell_cast trigger counts earlier spells by "
                f"their printed faces, so its filter cannot use {sorted(unordinal)} "
                f"(allowed: {sorted(ORDINAL_FILTER_KEYS)})"
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
            mana_ability=model.trigger.mana_ability,
            nth=model.trigger.nth,
            max_per_turn=model.trigger.max_per_turn,
            batched=model.trigger.batched,
            level=model.trigger.level,
        )
        if trigger.max_per_turn is not None and trigger.max_per_turn < 1:
            raise DslError(
                f"{where}: 'max_per_turn' is a cap of at least 1; "
                f"an ability that may never trigger is not a card"
            )
        active_zones = tuple(Zone(z) for z in model.active_zones)

    mana_options: tuple[tuple[int, ...], ...] = ()
    mana_amount: Mapping[str, Any] | None = None
    mana_rider: tuple[Mapping[str, Any], ...] = ()
    mana_reflects: Mapping[str, Any] | None = None
    mana_identity = False
    mana_chosen_color = False
    mana_split: tuple[str, ...] = ()
    if model.is_mana_ability:
        if kind is not AbilityKind.ACTIVATED:
            raise DslError(f"{where}: only activated abilities can be mana abilities")
        if targets:
            raise DslError(f"{where}: a mana ability cannot have targets")
        if any(
            isinstance(e, Mapping) and e.get("op") == "choose_mode" and e.get("chooser") is not None
            for e in model.effects or ()
        ):
            # 605.1a/605.3: a mana ability does not use the stack and resolves
            # inside somebody's payment. Stopping there to ask a *different*
            # player a question has no window to happen in, and the cards that
            # look like they want it -- The Warring Triad's "Target player adds
            # one mana of any color" -- target, so they are not mana abilities
            # in the first place.
            raise DslError(
                f"{where}: a mana ability cannot hand its 'choose_mode' to "
                f"another player; it resolves without the stack, inside a payment"
            )
        mana_effects, mana_rider = _split_mana_rider(model.effects, where)
        # "Add one mana of any color that a land an opponent controls could
        # produce." The colours are a question about the board, so the card
        # names the permanents to ask rather than the colours to make.
        reflect = next(
            (
                e.get("reflecting")
                for e in mana_effects
                if isinstance(e, Mapping) and e.get("reflecting")
            ),
            None,
        )
        if reflect is not None:
            if len(mana_effects) != 1:
                raise DslError(
                    f"{where}: a reflecting mana ability is a single 'add_mana' -- "
                    f"there is no second thing for the board's colours to join"
                )
            validate_selector(reflect, f"{where}.reflecting")
            mana_reflects = dict(reflect)
            # The static superset. Load time cannot know which colours the board
            # will offer, and an empty tuple here would make `solver_taps` and
            # `offerable_mana_ability` both decide this is not a mana source at
            # all -- so the ability would never be offered or tapped, whatever
            # the opponent's lands did.
            mana_options = _ANY_COLOR_OPTIONS
            mana_amount = None
        elif any(isinstance(e, Mapping) and e.get("in_commander_identity") for e in mana_effects):
            # "Add one mana of any color in your commander's color identity."
            # Command Tower, Arcane Signet, Path of Ancestry. The same shape as
            # `reflecting` and for the same reason -- the colours are a question
            # about the game, not about the card -- but the question is asked of
            # the command zone rather than of the board.
            if len(mana_effects) != 1:
                raise DslError(
                    f"{where}: a commander-identity mana ability is a single 'add_mana' -- "
                    f"there is no second thing for the identity's colours to join"
                )
            mana_identity = True
            # The static superset, for the same reason `reflecting` needs one:
            # an empty tuple at load time makes `solver_taps` and
            # `offerable_mana_ability` decide this is not a mana source, so the
            # ability would never be offered whatever the commander's colours.
            mana_options = _ANY_COLOR_OPTIONS
            mana_amount = None
        elif any(isinstance(e, Mapping) and e.get("split") for e in mana_effects):
            # "Add X mana in any combination of {U} and/or {R}." Vivi Ornitier.
            # Fourth of the same family: the options depend on X, which reads
            # the board, so load time can only record the colours and the
            # expression.
            if len(mana_effects) != 1:
                raise DslError(
                    f"{where}: a split mana ability is a single 'add_mana' -- there is "
                    f"no second thing for the combination to join"
                )
            effect = mana_effects[0]
            colors = [str(c) for c in effect.get("split") or ()]
            if len(colors) < 2:
                raise DslError(
                    f"{where}.split: a combination needs two or more colours; one colour "
                    f"is an ordinary 'mana' string with an 'amount'"
                )
            unknown = [c for c in colors if c not in MANA_SYMBOLS]
            if unknown:
                raise DslError(f"{where}.split: unknown mana symbols {unknown}")
            if "amount" not in effect:
                raise DslError(
                    f"{where}: a split mana ability needs an 'amount' -- how much mana is "
                    f"being divided. Without it the split has no size"
                )
            mana_split = tuple(colors)
            _validate_mana_amount(effect["amount"], f"{where}.amount")
            mana_amount = effect["amount"]
            # The static superset, for the reason `reflecting` needs one: an
            # empty tuple at load time makes `solver_taps` and
            # `offerable_mana_ability` decide this is not a mana source at all.
            mana_options = _ANY_COLOR_OPTIONS
        elif any(
            isinstance(e, Mapping) and isinstance(e.get("mana"), Mapping) for e in mana_effects
        ):
            # "{T}: Add one mana of **the chosen color**." Heraldic Banner. The
            # third member of the same family, and the question is asked of the
            # permanent's own `chosen_color`.
            if len(mana_effects) != 1:
                raise DslError(
                    f"{where}: a chosen-colour mana ability is a single 'add_mana' -- "
                    f"there is no second thing for the chosen colour to join"
                )
            mana_chosen_color = True
            # The static superset, for the same reason `reflecting` needs one:
            # an empty tuple at load time makes `solver_taps` and
            # `offerable_mana_ability` decide this is not a mana source, so the
            # ability would never be offered whatever colour was chosen.
            mana_options = _ANY_COLOR_OPTIONS
            mana_amount = None
        else:
            mana_options = _mana_options(mana_effects, where)
            mana_amount = _mana_amount(mana_effects, where)
    mana_restriction: ManaRestriction | None = None
    if model.mana_restriction is not None:
        if not model.is_mana_ability:
            raise DslError(f"{where}: 'mana_restriction' needs 'is_mana_ability'")
        mana_restriction = _mana_restriction(model.mana_restriction, where)

    return Ability(
        kind=kind,
        index=index,
        text=model.text,
        reflex_id=model.id or "",
        cost=cost,
        is_mana_ability=model.is_mana_ability,
        mana_options=mana_options,
        mana_amount=mana_amount,
        mana_rider=mana_rider,
        mana_reflects=mana_reflects,
        mana_identity=mana_identity,
        mana_split=mana_split,
        mana_chosen_color=mana_chosen_color,
        mana_restriction=mana_restriction,
        # 606.3: a loyalty ability may be activated "any time they could cast a
        # sorcery". That is the rule speaking, not the card, so it is applied
        # here rather than left to an author to remember -- one omitted flag and
        # the planeswalker ticks up at instant speed on somebody else's turn.
        sorcery_speed_only=model.sorcery_speed_only
        or (cost is not None and cost.loyalty is not None),
        activation_condition=(
            dict(model.condition) if kind is AbilityKind.ACTIVATED and model.condition else None
        ),
        is_cycling=model.is_cycling,
        activate_steps=tuple(model.activate_steps),
        once_each_turn=model.once_each_turn,
        threshold=threshold,
        trigger=trigger,
        active_zones=active_zones,
        targets=targets,
        mode_targets=mode_targets,
        effects=tuple(model.effects),
        static=None,
    )


def _validate_add_mana_on_tap(model: AbilityModel, where: str) -> None:
    """ "Whenever you tap a Swamp for mana, add an additional {B}." Crypt Ghast.

    Both halves are required. Without `tapped_permanent` the static would fire
    off every permanent tapped for mana -- Mana Reflection's reach with Crypt
    Ghast's payload, a much bigger card. Without `add_mana` it adds nothing. And
    `affects`/`amount` are refused rather than ignored: the permanent is named
    by `tapped_permanent` and the amount is printed in `add_mana`.
    """
    from automtg.engine.mana import parse_mana_production

    if model.tapped_permanent is None or not model.add_mana:
        raise DslError(
            f"{where}: add_mana_on_tap needs 'tapped_permanent' (what was tapped, "
            f"e.g. {{'subtypes': ['Swamp']}}) and 'add_mana' (the mana added, e.g. '{{B}}')"
        )
    if model.affects is not None or model.amount is not None:
        raise DslError(
            f"{where}: add_mana_on_tap takes 'affects_player', 'tapped_permanent', "
            f"'add_mana' and an optional 'condition', and no 'affects' or 'amount'"
        )
    tapped = model.tapped_permanent
    unknown = set(tapped) - TAPPED_PERMANENT_KEYS
    if unknown or not tapped:
        raise DslError(
            f"{where}.tapped_permanent: may only name {sorted(TAPPED_PERMANENT_KEYS)} "
            f"and must name at least one, got {sorted(tapped)}"
        )
    for key, known in (("types", KNOWN_TYPES), ("supertypes", KNOWN_SUPERTYPES)):
        values = tapped.get(key, [])
        if not isinstance(values, list) or not all(v in known for v in values):
            raise DslError(f"{where}.tapped_permanent.{key}: unknown value in {values!r}")
    subtypes = tapped.get("subtypes", [])
    if not isinstance(subtypes, list) or not all(isinstance(v, str) and v for v in subtypes):
        raise DslError(f"{where}.tapped_permanent.subtypes: a list of subtype names")
    try:
        produced = parse_mana_production(model.add_mana)
    except Exception as exc:
        raise DslError(f"{where}.add_mana: {exc}") from exc
    if not any(produced):
        raise DslError(f"{where}.add_mana: {model.add_mana!r} adds no mana")


def _compile_static(model: AbilityModel, index: int, where: str) -> Ability:
    if model.effect is None:
        raise DslError(f"{where}: static abilities need an 'effect' name")
    if model.effect == "prevent_damage" and model.amount is None:
        # Absorb 0 prevents nothing. A static that reads as damage prevention
        # and prevents none of it is the failure this whole pass exists to
        # refuse -- it would load, appear in the card's text, and never fire.
        raise DslError(f"{where}: 'prevent_damage' needs an 'amount' -- absorb N")
    if model.effect == "crew_power_bonus" and model.amount is None:
        # "As though its power were 0 greater" is not a printed sentence, and a
        # bonus of nothing would load, print the Pilot's line, and crew exactly
        # as a vanilla 1/1 does -- the token wearing most of a card.
        raise DslError(
            f"{where}: 'crew_power_bonus' needs an 'amount' -- "
            f"crews Vehicles as though its power were N greater"
        )
    if model.effect not in STATIC_EFFECTS:
        raise DslError(
            f"{where}: unknown static effect {model.effect!r} (implemented: {sorted(STATIC_EFFECTS)})"
        )
    if model.effects:
        raise DslError(f"{where}: static abilities cannot have 'effects'")

    for key in ("affects", "blockers", "cause_filter", "affects_spells"):
        _check_mana_cost_key(getattr(model, key, None), f"{where}.{key}")
    if model.affects is not None:
        unknown = set(model.affects) - STATIC_FILTER_KEYS
        if unknown:
            raise DslError(
                f"{where}: static filters may only read printed characteristics; "
                f"unsupported keys {sorted(unknown)}"
            )
        _check_owner_key(model.affects, f"{where}.affects")
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
            _check_owner_key(model.blockers, f"{where}.blockers")
    elif model.blockers is not None or model.require_all:
        raise DslError(
            f"{where}: 'blockers'/'require_all' only mean anything on a "
            f"block_restriction static, not on {model.effect!r}"
        )
    if model.effect == "double_triggers":
        # The cause clause is the half a card may omit, and omitting it means
        # "any cause" -- so a typo in an event name must not read as one.
        from automtg.engine.triggers import TRIGGER_EVENTS

        for name in model.cause_events or ():
            if name not in TRIGGER_EVENTS:
                raise DslError(
                    f"{where}.cause_events: unknown trigger event {name!r} "
                    f"(implemented: {sorted(TRIGGER_EVENTS)})"
                )
        if model.cause_filter is not None:
            unknown = set(model.cause_filter) - STATIC_FILTER_KEYS
            if unknown:
                raise DslError(
                    f"{where}.cause_filter: unknown keys {sorted(unknown)}; a cause "
                    f"is matched against the printed face of the event's subject"
                )
    elif model.cause_events or model.cause_controller or model.cause_filter:
        raise DslError(
            f"{where}: a cause clause only means something to 'double_triggers', "
            f"not to {model.effect!r}"
        )

    if model.effect in ("cant_attack_alone", "cant_block_alone") and model.affects is None:
        # `characteristics._matches` reads a missing filter as "matches
        # nothing", so an "…alone" static without one is a printed restriction
        # that restricts nobody -- it loads clean, shows on the card and never
        # fires. Every printed one of these is self-referential, so what the
        # card wants is `{"self_only": true}`; saying it is the point.
        raise DslError(
            f"{where}: {model.effect} needs an 'affects' filter -- "
            f'{{"self_only": true}} for the creature that carries it'
        )
    if model.effect == "cant_attack_you" and model.affects is None:
        # Same refusal, one step further: a missing filter matches nothing, so a
        # filterless `cant_attack_you` is a wall nobody bounces off. And the
        # filter is the *whole* of what the sentence says -- "**Inklings** can't
        # attack you" -- where the seat it protects is never written down,
        # because it is always the permanent's own controller. Note the printed
        # line names those creatures wherever they are, so what these cards want
        # is `controller: "any"`, exactly as `cant_attack` and `attack_tax` do.
        raise DslError(
            f"{where}: cant_attack_you needs an 'affects' filter naming the "
            f"creatures it stops -- e.g. "
            f'{{"controller": "any", "subtypes": ["Inkling"]}}'
        )
    if model.effect == "cast_from_library_top" and not model.pay_life_instead:
        raise DslError(
            f"{where}: cast_from_library_top needs 'pay_life_instead' -- "
            f"the permission without its price is a different card"
        )
    if model.effect == "cast_from_graveyard":
        # Both halves required, for `spell_cost_reduction`'s reason: a
        # permission that named no card type would let every spell out of the
        # graveyard, and one with no `max_per_turn` would be an unbounded engine
        # rather than the printed "once during each of your turns".
        if model.affects_spells is None:
            raise DslError(
                f"{where}: cast_from_graveyard needs 'affects_spells' naming which "
                f"spells it lets out -- without one it frees the whole graveyard"
            )
        unknown = set(model.affects_spells) - SPELL_FILTER_KEYS
        if unknown:
            raise DslError(
                f"{where}.affects_spells: a card in a graveyard has a printed face "
                f"and an owner and no board state; unsupported keys {sorted(unknown)}"
            )
        if model.affects is not None:
            raise DslError(
                f"{where}: cast_from_graveyard filters spells with "
                f"'affects_spells', not 'affects' (which picks out permanents)"
            )
        if not model.static_max_per_turn and not model.grants_flashback:
            # `grants_flashback` IS the rate limit, and a different one: each
            # card is exiled as it resolves, so the permission spends itself
            # card by card rather than being metered per turn. Lier prints no
            # per-turn cap and needs none -- your graveyard runs out.
            raise DslError(
                f"{where}: cast_from_graveyard needs 'max_per_turn' or "
                f"'grants_flashback' -- "
                f"'once during each of your turns' is the whole rate limit, and "
                f"without it the permission is an unbounded engine"
            )
    elif model.effect == "spell_cost_reduction":
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
    if model.effect == "replace_token_creation":
        # `affects` names permanents on the battlefield; the token this asks
        # about has not been created and there is nothing on the battlefield for
        # that filter to find. Refused rather than ignored, because a Divine
        # Visitation written with `affects` would load clean, replace nothing,
        # and print a line of text it never performs.
        if model.affects is not None:
            raise DslError(
                f"{where}: replace_token_creation filters the token about to be "
                f"made with 'affects_token', not 'affects' (which picks out "
                f"permanents already on the battlefield)"
            )
        if model.affects_token is not None:
            unknown = set(model.affects_token) - TOKEN_FILTER_KEYS
            if unknown:
                raise DslError(
                    f"{where}.affects_token: a token that does not exist yet has a "
                    f"printed face and nothing else; unsupported keys {sorted(unknown)}"
                )
        # Exactly one axis. Both at once is a shape no printed card takes, and
        # neither is a replacement that says nothing about what is made.
        if model.create_instead and model.token_multiplier is not None:
            raise DslError(
                f"{where}: replace_token_creation takes 'create_instead' (which "
                f"tokens) or 'token_multiplier' (how many of those tokens), not both"
            )
        if model.token_multiplier is not None:
            # 1 replaces a creation with itself, and 0 is "no tokens are
            # created" -- a prevention, a different sentence and a much stronger
            # card. The same refusal `replace_life_loss` makes.
            if model.token_multiplier < 2:
                raise DslError(
                    f"{where}.token_multiplier: must be 2 or more; 1 replaces a "
                    f"creation with itself and 0 creates nothing, which is a "
                    f"different effect"
                )
        # A replacement that creates nothing is not this effect. "Instead create
        # one of each" and "that many are created instead" both name what is
        # made; an empty list would silently *delete* every token its filter
        # matched, which is a different and much stronger card.
        elif not model.create_instead:
            raise DslError(
                f"{where}: replace_token_creation needs 'create_instead' -- the "
                f"token ids created instead, one of each per token replaced -- "
                f"or 'token_multiplier' for \"twice that many of those tokens\""
            )
    elif (
        model.affects_token is not None
        or model.create_instead
        or model.token_multiplier is not None
    ):
        raise DslError(
            f"{where}: 'affects_token'/'create_instead'/'token_multiplier' only mean "
            f"anything on a replace_token_creation static, not on {model.effect!r}"
        )

    if model.effect == "replace_life_loss":
        # A multiplier of 1 replaces a loss with an identical loss, and 0 is a
        # *prevention* -- "they lose no life" -- which is a different printed
        # sentence and a strictly stronger card. Both would load clean and
        # neither is what any card says, so both are refused here rather than
        # left to read as a typo nobody notices. Same refusal `ward` makes
        # about ward {0} and `replace_token_creation` about an empty
        # `create_instead`.
        if model.loss_multiplier is None:
            raise DslError(
                f"{where}: replace_life_loss needs 'loss_multiplier' -- what the "
                f"life loss is multiplied by"
            )
        if model.loss_multiplier < 2:
            raise DslError(
                f"{where}.loss_multiplier: must be 2 or more; "
                f"1 replaces a loss with itself and 0 is a prevention, "
                f"which is a different effect"
            )
    elif model.loss_multiplier is not None:
        raise DslError(
            f"{where}: 'loss_multiplier' only means anything on a "
            f"replace_life_loss static, not on {model.effect!r}"
        )
    if model.effect == "add_mana_on_tap":
        _validate_add_mana_on_tap(model, where)
    elif model.tapped_permanent is not None or model.add_mana is not None:
        raise DslError(
            f"{where}: 'tapped_permanent'/'add_mana' only mean anything on an "
            f"add_mana_on_tap static, not on {model.effect!r}"
        )
    if model.effect == "replace_life_gain":
        # The mirror of `replace_life_loss`, refused for its reasons: 1 replaces
        # a gain with an identical gain, and 0 is "you gain no life" -- which
        # is `cant_gain_life`, a different sentence that also stops the
        # life-gain triggers rather than firing them for nothing.
        if model.gain_multiplier is None:
            raise DslError(
                f"{where}: replace_life_gain needs 'gain_multiplier' -- what the "
                f"life gain is multiplied by"
            )
        if model.gain_multiplier < 2:
            raise DslError(
                f"{where}.gain_multiplier: must be 2 or more; "
                f"1 replaces a gain with itself and 0 is \"can't gain life\", "
                f"which is a different effect"
            )
        if model.affects is not None or model.amount is not None:
            # "If you would gain life" names a player, and the size is
            # `gain_multiplier`; nothing reads either key.
            raise DslError(
                f"{where}: replace_life_gain takes 'affects_player', "
                f"'gain_multiplier' and an optional 'condition', and no "
                f"'affects' or 'amount'"
            )
    elif model.gain_multiplier is not None:
        raise DslError(
            f"{where}: 'gain_multiplier' only means anything on a "
            f"replace_life_gain static, not on {model.effect!r}"
        )
    if model.effect == "replace_draw":
        # Same refusals as `loss_multiplier`: 1 replaces a draw with an
        # identical draw and 0 is "draw nothing instead" -- a prevention, which
        # no doubler prints and which would load clean as a lock on the
        # controller's own draws.
        if model.draw_multiplier is None:
            raise DslError(
                f"{where}: replace_draw needs 'draw_multiplier' -- how many "
                f"cards each replaced draw becomes"
            )
        if model.draw_multiplier < 2:
            raise DslError(
                f"{where}.draw_multiplier: must be 2 or more; "
                f"1 replaces a draw with itself and 0 draws nothing, "
                f"which is a different effect"
            )
        if model.affects is not None or model.amount is not None:
            # Nothing reads either key; "if you would draw a card" names a
            # player, and the size is `draw_multiplier`.
            raise DslError(
                f"{where}: replace_draw takes 'affects_player', "
                f"'draw_multiplier', 'except_first_in_draw_step' and an "
                f"optional 'condition', and no 'affects' or 'amount'"
            )
    elif model.draw_multiplier is not None or model.except_first_in_draw_step:
        raise DslError(
            f"{where}: 'draw_multiplier'/'except_first_in_draw_step' only mean "
            f"anything on a replace_draw static, not on {model.effect!r}"
        )
    if model.effect == "replace_mill":
        # `draw_multiplier`'s refusals, for its reasons: 1 replaces a mill with
        # an identical mill, and 0 is "mill nothing instead" -- a prevention,
        # which no doubler prints and which would load clean as a lock on the
        # named player's mills.
        if model.mill_multiplier is None:
            raise DslError(
                f"{where}: replace_mill needs 'mill_multiplier' -- how many "
                f"cards each replaced mill becomes"
            )
        if model.mill_multiplier < 2:
            raise DslError(
                f"{where}.mill_multiplier: must be 2 or more; "
                f"1 replaces a mill with itself and 0 mills nothing, "
                f"which is a different effect"
            )
        if model.affects is not None or model.amount is not None:
            # "If an opponent would mill one or more cards" names a player, and
            # the size is `mill_multiplier`; nothing reads either key.
            raise DslError(
                f"{where}: replace_mill takes 'affects_player', "
                f"'mill_multiplier' and an optional 'condition', "
                f"and no 'affects' or 'amount'"
            )
    elif model.mill_multiplier is not None:
        raise DslError(
            f"{where}: 'mill_multiplier' only means anything on a replace_mill "
            f"static, not on {model.effect!r}"
        )
    if model.effect == "replace_empty_draw" and (
        model.affects is not None or model.amount is not None
    ):
        # The replacement has no size -- it substitutes winning for drawing --
        # so there is nothing for either key to mean, and a key nothing reads
        # would load clean and print a line that promises more than it does.
        raise DslError(
            f"{where}: replace_empty_draw takes 'affects_player' and an "
            f"optional 'condition', and no 'affects' or 'amount'"
        )
    if model.effect in PLAYER_WIDE_STATIC_EFFECTS:
        if model.affects_player is None:
            raise DslError(f"{where}: {model.effect} needs 'affects_player'")
        if model.effect == "cant_gain_life" and (
            model.affects is not None or model.amount is not None
        ):
            # "Your opponents can't gain life" names players and nothing else.
            # Nothing reads either key, and a filter written here ("can't gain
            # life from creatures") would load clean and forbid every gain.
            raise DslError(
                f"{where}: cant_gain_life stops every life gain for the named "
                f"players; it takes 'affects_player' and an optional "
                f"'condition', and no 'affects' or 'amount'"
            )
        if model.effect == "cant_cast_spells" and (
            model.affects is not None or model.amount is not None
        ):
            # Nothing reads either key. "Your opponents can't cast **creature**
            # spells" written with a filter here would load clean and stop every
            # spell -- a strictly stronger lock than the printed card, and one
            # that looks right on screen. Refused until a spell filter is built.
            raise DslError(
                f"{where}: cant_cast_spells stops every spell the named players "
                f"would cast; it takes 'affects_player' and an optional "
                f"'condition', and no 'affects' or 'amount'"
            )
    elif model.effect in (
        "spell_cost_reduction",
        "replace_token_creation",
        # "Spells can't be countered" names no permanent either -- it is about
        # spells on the stack, and its optional `affects_spells` is the only
        # filter it can carry. Lier prints no filter at all: every spell, every
        # player, which is the card's whole reputation.
        "spells_cant_be_countered",
    ):
        # Picks out *spells* or *tokens not yet created*, through
        # `affects_spells` and `affects_token`, both checked above. There are no
        # permanents for `affects` to name.
        pass
    elif model.affects is None:
        raise DslError(f"{where}: static effect {model.effect!r} needs 'affects'")

    if model.effect == "ward":
        # Ward with no cost is ward {0}: a keyword that prints on the card, shows
        # in the log, taxes nothing and can never be declined. The same refusal
        # `prevent_damage` makes about absorb 0.
        if model.cost is None:
            raise DslError(f"{where}: ward needs a 'cost' -- ward that taxes nothing is not a card")
        # Through the same validator an activated ability's cost goes through, so
        # ward inherits every selector check rather than growing its own. The
        # `Cost` is discarded: what the static stores is the raw spec, because
        # `op_may` charges it from a mapping and building it twice is two places
        # for the price to drift.
        _compile_cost(model.cost, where)
    elif model.effect == "attack_tax":
        # Propaganda. A tax with no price is `cant_attack` wearing a costume --
        # an absolute lock that reads as if it could be bought off, which is
        # strictly stronger than what is printed. The same refusal ward makes.
        if model.cost is None:
            raise DslError(
                f"{where}: attack_tax needs a 'cost' -- a tax that prices "
                f"nothing is a prohibition, not a tax"
            )
        # Mana and nothing else. A sacrifice or a discard would have to ask a
        # question *inside* the declare-attackers decision, which would strand
        # it -- and no printed pillowfort asks for one. Refused at load time so
        # the restriction is a rule rather than an assumption `game.py` makes.
        priced = prune_cost(model.cost.model_dump())
        if not str(priced.get("mana") or "").strip():
            raise DslError(f"{where}: attack_tax is paid in mana; give its 'cost' a 'mana'")
        if set(priced) - {"mana"}:
            raise DslError(
                f"{where}: attack_tax is paid in mana only, not "
                f"{sorted(set(priced) - {'mana'})} -- anything else would have "
                f"to ask a question inside the attack declaration"
            )
        _compile_cost(model.cost, where)
    elif model.cost is not None:
        raise DslError(
            f"{where}: a static ability has no cost to pay; 'cost' means "
            f"something only on 'ward' and 'attack_tax' (and on activated abilities)"
        )

    for field_name in ("power", "toughness", "amount"):
        value = getattr(model, field_name)
        if value is not None:
            _validate_static_value(value, f"{where}.{field_name}")

    for k in model.keywords:
        if k not in KNOWN_KEYWORDS:
            raise DslError(f"{where}: unknown keyword {k!r}")

    if model.effect == "set_types" and not model.types:
        raise DslError(f"{where}: set_types needs the types it sets")

    if model.effect == "set_colors":
        # `[]` is colourless and is the point of the effect, so the check is for
        # the field being *absent* -- a `set_colors` with nothing said would
        # silently repaint everything it touches colourless.
        if model.colors is None:
            raise DslError(
                f"{where}: set_colors needs 'colors' -- use [] for colourless, "
                f"which is a statement rather than an omission"
            )
        for color in model.colors:
            if color not in KNOWN_COLORS:
                raise DslError(f"{where}: unknown colour {color!r}")

    if model.effect == "grant_ability" and model.ability is None:
        raise DslError(
            f"{where}: grant_ability needs 'ability' -- the index into this "
            f"card's 'grantable_abilities'"
        )

    qualities = [*model.from_types, *model.from_subtypes, *model.from_colors]
    if model.from_colors_outside_commander_identity:
        # A quality, and the loudest kind of one: it is up to five colours.
        qualities.append("outside commander identity")
    if model.effect == "protection":
        # A protection static that names nothing protects from nothing -- a card
        # that looks implemented and is not, which is the one failure this pass
        # exists to stop.
        if not qualities:
            raise DslError(
                f"{where}: protection needs from_types/from_subtypes/from_colors/"
                f"from_colors_outside_commander_identity"
            )
        if model.from_colors_outside_commander_identity and model.from_colors:
            # The computed set already covers every colour the commander lacks,
            # and a printed colour *inside* the identity is a second sentence no
            # card prints. Written together, one of the two is dead weight or a
            # silent widening, and nothing on the board would say which.
            raise DslError(
                f"{where}: 'from_colors_outside_commander_identity' is the whole "
                f"colour set; do not also list 'from_colors'"
            )
        for t in model.from_types:
            if t not in KNOWN_TYPES:
                raise DslError(f"{where}: unknown type {t!r} in from_types")
        for c in model.from_colors:
            if c not in KNOWN_COLORS:
                raise DslError(f"{where}: unknown color {c!r} in from_colors")
    elif qualities:
        raise DslError(
            f"{where}: from_types/from_subtypes/from_colors/"
            f"from_colors_outside_commander_identity need effect 'protection'"
        )

    _validate_static_condition(model.condition, f"{where}.condition")

    static: dict[str, Any] = {"effect": model.effect}
    if model.condition is not None:
        static["condition"] = dict(model.condition)
    if model.affects is not None:
        static["affects"] = dict(model.affects)
    if model.affects_spells is not None:
        static["affects_spells"] = dict(model.affects_spells)
    if model.affects_token is not None:
        static["affects_token"] = dict(model.affects_token)
    if model.create_instead:
        static["create_instead"] = list(model.create_instead)
    if model.token_multiplier is not None:
        static["token_multiplier"] = model.token_multiplier
    if model.loss_multiplier is not None:
        static["loss_multiplier"] = model.loss_multiplier
    if model.gain_multiplier is not None:
        static["gain_multiplier"] = model.gain_multiplier
    if model.draw_multiplier is not None:
        static["draw_multiplier"] = model.draw_multiplier
    if model.except_first_in_draw_step:
        static["except_first_in_draw_step"] = True
    if model.mill_multiplier is not None:
        static["mill_multiplier"] = model.mill_multiplier
    if model.affects_player is not None:
        static["affects_player"] = model.affects_player
    if model.tapped_permanent is not None:
        static["tapped_permanent"] = dict(model.tapped_permanent)
    if model.add_mana is not None:
        static["add_mana"] = model.add_mana
    # `double_triggers`' cause clause. Copied explicitly like every other field
    # here: this dict is a whitelist, not a dump of the model, so a field the
    # schema accepts and this loop forgets is silently dropped -- the static
    # loads, compiles and applies with the clause simply absent. Veyran doubled
    # an upkeep trigger for exactly that reason before these three lines.
    if model.cause_events is not None:
        static["cause_events"] = list(model.cause_events)
    if model.cause_controller is not None:
        static["cause_controller"] = model.cause_controller
    if model.cause_filter is not None:
        static["cause_filter"] = dict(model.cause_filter)
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
    if model.from_colors_outside_commander_identity:
        static["from_colors_outside_commander_identity"] = True
    if model.blockers is not None:
        static["blockers"] = dict(model.blockers)
    if model.require_all:
        static["require_all"] = True
    if model.effect == "ward":
        # Pruned of the fields the model dump carries unset, because this
        # mapping is also what `carddef.ward_ability` keys its intern table on:
        # two cards writing ward {1} must land on one ability, not two that only
        # differ by a `tap: false` nobody wrote.
        static["cost"] = prune_cost(model.cost.model_dump())
    if model.effect == "attack_tax":
        static["cost"] = prune_cost(model.cost.model_dump())
    if model.effect == "cast_from_library_top":
        static["pay_life_instead"] = True
    if model.effect == "cast_from_graveyard":
        # Carried onto the compiled mapping rather than left on the model, for
        # `grant_ability`'s reason a few lines down: the mapping is all
        # `characteristics` ever sees, and a rate limit left behind would read
        # as no limit at all.
        static["max_per_turn"] = int(model.static_max_per_turn or 1)
        if model.enters_tapped:
            static["enters_tapped"] = True
        if model.arrived_this_turn_from is not None:
            zones = [str(z) for z in model.arrived_this_turn_from]
            if not zones:
                raise DslError(
                    f"{where}: 'arrived_this_turn_from' names no zone at all, so "
                    f"nothing in the graveyard would ever qualify"
                )
            from automtg.engine.effects.selectors import ZONE_NAMES as _ZONES

            known = {z.lstrip("!") for z in zones} - set(_ZONES) - {"any"}
            if known:
                raise DslError(f"{where}.arrived_this_turn_from: unknown zone(s) {sorted(known)}")
            static["arrived_this_turn_from"] = zones
    if model.effect == "grant_ability":
        # Which of the card's `grantable_abilities` is handed over. Carried onto
        # the compiled mapping rather than left on the model, because the
        # mapping is all `characteristics.abilities_of` ever sees: left behind,
        # its `static.get("ability", 0)` read 0 for every card, so one with two
        # grantable abilities silently granted the first whichever it named.
        # Invisible until a card had two, which is what Inspiring Leader's
        # quoted static makes ordinary.
        static["ability"] = int(model.ability or 0)

    # "As long as this card is **in your graveyard** and you control a
    # Mountain..." -- Anger. `active_zones` was read on the activated and
    # triggered branches and dropped here, so every static was pinned to the
    # battlefield default: a static written on Anger switched on the moment it
    # resolved as a 2/2, granting the team haste from play, and switched off
    # when it died -- the exact inverse of the printed card.
    #
    # The zone clause needs no separate condition. Being gathered only while the
    # card sits there *is* "as long as this card is in your graveyard", and
    # `characteristics._active_statics` is what enforces it.
    zones = tuple(Zone(z) for z in model.active_zones)
    unsupported = set(zones) - {Zone.BATTLEFIELD, Zone.GRAVEYARD}
    if unsupported:
        # Only the two the walk actually visits. A static declaring `hand` or
        # `exile` would load clean and never once be collected, which is the
        # inert-card failure this pass exists to refuse.
        raise DslError(
            f"{where}: a static can be active on the battlefield or in a "
            f"graveyard; nothing collects one in {sorted(z.value for z in unsupported)}"
        )
    return Ability(
        kind=AbilityKind.STATIC,
        index=index,
        text=model.text,
        static=static,
        active_zones=zones,
    )
