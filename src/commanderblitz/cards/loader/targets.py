"""Target specs: compiling them, and the wiring checks that go with them."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from commanderblitz.engine.carddef import (
    Ability,
    TargetSpec,
)
from commanderblitz.engine.effects.selectors import validate_selector
from commanderblitz.engine.effects.values import (
    validate_value,
)
from commanderblitz.engine.enums import (
    AbilityKind,
)
from commanderblitz.engine.errors import DslError

from ..schema import CardModel, TargetModel
from .effects import (
    _validate_player_spec,
)
from .walk import (
    _before,
)


def _compile_targets(
    models,
    where: str,
    *,
    on_spell: bool = False,
    on_trigger: bool = False,
    mode_count: int | None = None,
    mana_cost: str | None = None,
    has_kicker: bool = False,
    has_gift: bool = False,
) -> tuple[TargetSpec, ...]:
    """Compile a card's or ability's target list, with the one ordering rule.

    At most one spec may be variable-size -- ``count: "any"``, "up to X", or a
    computed count -- and it must come last.  `targeting.filter_legal` splits
    the stored refs spec by spec, and a variable-size spec in the middle leaves
    no way to say where its refs end and the next spec's begin -- so the spell
    would fizzle or keep the wrong targets depending on how many the caster
    chose, which is a bug no board would show.

    ``on_spell`` marks the card's own `targets`, where a **value expression** is
    refused: a spell's targets are chosen as it is cast (601.2c), which legality
    does while enumerating actions -- before the player has chosen X and before
    any additional cost has been paid.  The evaluator would read a zero (or, on
    a card cast twice in a game, the *previous* cast's number), and both are a
    plausible-looking wrong card rather than a crash.  An ability's targets are
    declared when it goes on the stack, by which time its source permanent is
    there to be read, which is why this is a restriction on one of the two
    callers rather than on the form.

    ``on_trigger`` marks a **triggered** ability's targets, which is the other
    place a mode-owned spec has a moment to be declared in: 603.3d puts the
    modes and the targets alike at the instant the ability goes on the stack.

    ``mode_count`` is how many modes the single top-level ``choose_mode``
    offers, or ``None`` when there is no such question to hang a target on.  A
    spec carrying ``mode`` belongs to that mode alone and is declared only if it
    is chosen -- see `carddef.TargetSpec.mode`.
    """
    models = list(models)
    declared = {t.id for t in models}
    # Asked before anything compiles, so the one way a linked target goes wrong
    # that is *not* a typo gets its own sentence rather than the generic "the
    # card does not declare it": naming a sibling that comes later. The
    # combinations are grown in declaration order (601.2c chooses them all at
    # once, but something has to go first), so the answer this spec depends on
    # would not exist yet -- and a spec with no answer offers nothing, which
    # reads on the board as a target that simply cannot be chosen.
    for model in models:
        controller = model.selector.get("controller")
        if not isinstance(controller, Mapping):
            continue
        named = controller.get("target") or controller.get("controller_of_target")
        if isinstance(named, str) and named in declared and named not in _before(models, model.id):
            raise DslError(
                f"{where}.target[{model.id}]: names target {named!r}, which is "
                f"declared after it -- put the target it depends on first"
            )
    seen_ids: dict[str, str] = {}
    compiled: list[TargetSpec] = []
    for model in models:
        compiled.append(_compile_target(model, where, seen_ids))
        seen_ids[model.id] = model.kind
    specs = tuple(compiled)
    # Sibling specs are told apart by id -- `filter_legal` buckets by it and
    # every effect names one -- so two specs sharing an id is one target
    # silently swallowing another's refs. Never possible to notice on a board.
    seen: set[str] = set()
    for spec in specs:
        if spec.id in seen:
            raise DslError(f"{where}: two targets share the id {spec.id!r}")
        seen.add(spec.id)
    for spec in specs:
        # A per-player cap is a constraint on how many of a *variable-size*
        # choice may share a controller. On a fixed-size spec it either changes
        # nothing or makes the spec unsatisfiable, and both are silent.
        if spec.one_per_player and spec.count != "any":
            raise DslError(
                f"{where}: 'one_per_player' needs 'count': 'any' -- "
                f"it caps a variable-size choice, and a fixed one has no room to cap"
            )
        if (
            on_spell
            and not isinstance(spec.count, (int, str))
            and not spec.x_sized
            and not spec.additional_sized
        ):
            raise DslError(
                f"{where}.target[{spec.id}]: a computed 'count' only works on an "
                f"ability's targets -- a spell's are declared while it is being "
                f"cast (601.2c), before any additional cost is paid, so the "
                f"expression would read 0. The exceptions are {{\"x\": true}} and "
                f"{{\"additional_paid\": true}}: 601.2b announces X and how many "
                f"times the additional cost is paid *before* 601.2c chooses targets"
            )
        if on_spell and spec.additional_sized and (
            spec.up_to or spec.optional or spec.count_if_kicked is not None or spec.mode is not None
        ):
            # "Destroy X target nonland permanents" is exactly X: the cast line
            # substitutes the times it pays as a fixed count, and each of these
            # would put a second size or a second moment on the same spec.
            raise DslError(
                f"{where}.target[{spec.id}]: 'count': {{\"additional_paid\": true}} is "
                f"exactly the times the additional cost is paid -- it takes no "
                f"'up_to', 'optional', 'count_if_kicked' or 'mode'"
            )
        if spec.x_sized and on_spell and not (mana_cost or "").count("{X}"):
            # "Each of X targets" on a card with no X to pay is a spec that
            # always sizes to zero -- a spell that says it targets and never
            # does. Refused rather than left to read 0 for ever, which is the
            # silent half of the same mistake the clause above prevents.
            raise DslError(
                f"{where}.target[{spec.id}]: 'count': {{\"x\": true}} needs an "
                f"{{X}} in the card's mana cost -- there is no X to size it by"
            )
    for spec in specs:
        if not spec.selector.get("random"):
            continue
        # "Target … chosen at random" (Power Pack): `stack._random_trigger_targets`
        # draws it as a triggered ability goes on the stack. Nothing else reads
        # the clause -- a spell's or an activated ability's targets are chosen
        # in legality, which offers every tuple -- so anywhere else it would
        # load and be a free choice.
        if not on_trigger:
            raise DslError(
                f"{where}.target[{spec.id}]: 'random' is a triggered ability's "
                f"target -- nothing else draws one at random"
            )
        if len(specs) != 1 or spec.mode is not None:
            raise DslError(
                f"{where}.target[{spec.id}]: a random target must be the ability's "
                f"only target, owned by no mode"
            )
        if not isinstance(spec.count, int) or spec.count < 1 or spec.optional or spec.up_to:
            raise DslError(
                f"{where}.target[{spec.id}]: a random target takes a fixed 'count' "
                f"-- 'optional', 'up_to' and 'any' are choices nobody makes"
            )
    _check_mode_targets(
        specs, where, on_spell=on_spell, on_trigger=on_trigger, mode_count=mode_count
    )
    # The ordering rule is about the refs a *cast* stores, and a mode-owned spec
    # stores its refs after every card-level one -- so it is the card-level list
    # that has to end in the variable-size spec, not the printed list.
    for spec in specs:
        if spec.count_if_kicked is None:
            continue
        # "If this spell was kicked, instead choose any number of target
        # creatures you own." Legal at 601.2c because kicker is announced one
        # step earlier at 601.2b -- but only for a card that *has* a kicker to
        # announce, and only for the card's own targets. A triggered ability's
        # targets are declared when the trigger goes on the stack (603.3d), where
        # there is no cast to have been kicked, so the clause would read as
        # unkicked for ever and the card would quietly be the small half.
        if not on_spell:
            raise DslError(
                f"{where}.{spec.id}: 'count_if_kicked' is about a cast, and a "
                f"triggered ability's targets are declared without one -- it would "
                f"read as unkicked for ever"
            )
        if not has_kicker:
            raise DslError(
                f"{where}.{spec.id}: 'count_if_kicked' on a card with no 'kicker' "
                f"names a choice that can never be made"
            )
    _check_gift_targets(specs, where, on_spell=on_spell, has_gift=has_gift)
    fixed = [spec for spec in specs if spec.mode is None]
    # A gift-gated card declares one of two lists, and the ordering rule is
    # about the refs one cast stores -- so each list has to satisfy it, not
    # the printed union, which no cast ever declares.
    gated = any(spec.gift_promised is not None for spec in fixed)
    for promised in (False, True) if gated else (None,):
        declared = [
            spec
            for spec in fixed
            if promised is None or spec.gift_promised in (None, promised)
        ]
        variable = [i for i, spec in enumerate(declared) if spec.variable_size]
        if len(variable) > 1:
            raise DslError(
                f"{where}: only one target may be variable-size ('any number of', "
                f"'up to', or a computed count) -- "
                f"two variable-size specs cannot be told apart once chosen"
            )
        if variable and variable[0] != len(declared) - 1:
            raise DslError(
                f"{where}: a variable-size target must come last, "
                f"or the targets after it cannot be identified"
            )
    return specs


def _check_gift_targets(
    specs: tuple[TargetSpec, ...], where: str, *, on_spell: bool, has_gift: bool
) -> None:
    """Every restriction on a target's ``gift_promised``, each a card that would
    load wrong.

    Legal at all because 601.2b announces the promise one step before 601.2c
    declares the targets, so a cast already knows which side it is on. Each
    refusal below is a place with no such cast, or a spelling that names a
    choice the card never offers.
    """
    for spec in specs:
        if spec.gift_promised is None:
            continue
        label = f"{where}.target[{spec.id}]"
        if not on_spell:
            # An ability's targets are declared when it is activated or put on
            # the stack, with no cast to have promised anything; the gate would
            # read as unpromised for ever and the card be its small half.
            raise DslError(
                f"{label}: 'gift_promised' is about a cast, and an ability's "
                f"targets are declared without one"
            )
        if not has_gift:
            raise DslError(
                f"{label}: 'gift_promised' on a card with no 'gift' names a "
                f"promise that can never be made"
            )
        if spec.mode is not None:
            # A mode-owned spec is declared after the cast action is chosen,
            # by `Game._ask_mode_targets`; the promise rides on the action, so
            # the two gates would answer at different moments. No printing
            # asks for both.
            raise DslError(
                f"{label}: a mode-owned target cannot also be 'gift_promised' -- "
                f"the mode already decides whether it is declared"
            )
        if spec.count_if_kicked is not None:
            raise DslError(
                f"{label}: 'gift_promised' and 'count_if_kicked' on one target "
                f"are two cast-time choices sizing one spec -- no printing does it"
            )


def _check_mode_targets(
    specs: tuple[TargetSpec, ...],
    where: str,
    *,
    on_spell: bool,
    on_trigger: bool = False,
    mode_count: int | None,
) -> None:
    """Every restriction on ``mode``, each one a card that would load wrong.

    A mode-owned target needs one moment that owns both questions -- the modes
    first (601.2b), the targets they own straight after (601.2c).  A **spell**
    has it inside the cast, between choosing the modes and paying.  A
    **triggered ability** has it when the ability is put on the stack, which
    603.3d says is where both choices happen.

    An **activated** ability had neither for a long time, and this is where it
    was refused: `legality` enumerated one activation per legal target tuple, so
    its targets were fixed before `Game._activate` asked which mode -- the
    reverse of the printed order.  Phoenix Down is what changed it.
    `legality._ability_aims` now offers one activation *per mode*, each carrying
    only the targets that mode owns, so the bullet is part of the action the way
    `kicked` is part of a cast and `Game._activate` reads it off the action
    instead of asking.  A bullet with no legal target is simply not offered,
    which is 601.2b's other half.

    What is still refused is a modal question that is **not** the effect tree's
    single top-level one: that is asked as the thing resolves, by which time
    targets can no longer be declared at all.
    """
    owned = [spec for spec in specs if spec.mode is not None]
    if not owned:
        return
    if mode_count is None:
        raise DslError(
            f"{where}: 'mode' needs the whole effect tree to be one "
            f"top-level 'choose_mode' -- a nested or repeated one is answered "
            f"on resolution, with nothing left to declare a target in"
        )
    for spec in owned:
        label = f"{where}.target[{spec.id}]"
        if not 0 <= spec.mode < mode_count:
            raise DslError(
                f"{label}: mode {spec.mode} does not exist -- the card offers {mode_count}"
            )
        if spec.variable_size:
            raise DslError(
                f"{label}: a mode-owned target must be a fixed number -- "
                f"`filter_legal` splits the stored refs by position and a "
                f"caster-chosen size inside a mode leaves no way to say where "
                f"the next mode's refs begin"
            )
        if spec.optional:
            raise DslError(
                f"{label}: a mode-owned target cannot be 'optional' -- "
                f"declining it is declining the mode, and 601.2b already says "
                f"a mode with no legal target cannot be chosen"
            )
    if any(spec.variable_size for spec in specs if spec.mode is None):
        raise DslError(
            f"{where}: a card-level variable-size target cannot share a card "
            f"with a mode-owned one -- the mode's refs are stored after it, and "
            f"a caster-chosen size in front of them makes the split ambiguous"
        )


def _reads_context(node: Any) -> bool:
    """Does this selector name a sibling target or the announced ``{X}``?"""
    if isinstance(node, Mapping):
        return any(k in ("target", "x") or _reads_context(v) for k, v in node.items())
    if isinstance(node, (list, tuple)):
        return any(_reads_context(v) for v in node)
    return node == "x"


def _check_permanent_selector(model: TargetModel, label: str) -> None:
    """"Target spell or **creature**": the permanent half's own selector.

    Each refusal is a clause that would load and be read nowhere, or read
    somewhere the rest of the targeting layer does not look.
    """
    sub = model.permanent_selector or {}
    if model.kind != "spell_or_permanent":
        # Every other kind has one pool and one selector; a second would be
        # accepted and ignored.
        raise DslError(
            f"{label}: 'permanent_selector' narrows the permanent half of a "
            f"'spell_or_permanent' target, and this one is {model.kind!r}"
        )
    validate_selector(sub, f"{label}.permanent_selector")
    if sub.get("zone") not in (None, "battlefield"):
        raise DslError(
            f"{label}.permanent_selector: a permanent is on the battlefield, "
            f"not in {sub['zone']!r}"
        )
    if _reads_context(sub):
        # The linked-target walk (`targeting._names_a_sibling`) and the X walk
        # (`legality._mentions_x`) read `selector` only; a clause hidden here
        # would be enumerated without the answer it depends on. No printing
        # asks for one.
        raise DslError(
            f"{label}.permanent_selector: names a sibling target or {{X}}, "
            f"which only 'selector' may do"
        )


def _compile_target(
    model: TargetModel, where: str, siblings: Mapping[str, str] | None = None
) -> TargetSpec:
    """One target spec, and the three ways of saying "or fewer" kept apart.

    ``optional`` is "exactly N, or none"; ``count: "any"`` is "any number of",
    zero to the whole board; ``up_to`` is "up to N", zero to N.  Each of the
    refusals below is a card that would otherwise load with two of them
    overlapping, and read as a printing that does not exist.
    """
    label = f"{where}.target[{model.id}]"
    if model.kind == "ability_on_stack":
        # An ability on the stack has no face (113.7a): `_ability_matches`
        # answers `controller` and `ability_kind` and nothing else, so any
        # other clause would load and narrow nothing.
        extra = set(model.selector) - {"controller", "ability_kind"}
        if extra:
            raise DslError(
                f"{label}: an 'ability_on_stack' target reads only 'controller' "
                f"and 'ability_kind', not {sorted(extra)}"
            )
        kind = model.selector.get("ability_kind")
        if kind is not None and kind not in ("triggered", "activated"):
            raise DslError(
                f"{label}.ability_kind: 'triggered' or 'activated', got {kind!r}"
            )
        validate_selector(
            {k: v for k, v in model.selector.items() if k != "ability_kind"}, label
        )
    else:
        validate_selector(model.selector, label)
    controller_clause = model.selector.get("controller")
    if (
        # `"any"` is a *target* word, not a player spec: `_player_allowed`
        # answers it before `select_players` is asked, and `select_players` has
        # no name for "everyone who could be targeted". So it is spelled out
        # here rather than added to `PLAYER_SPEC_NAMES`, where it would start
        # meaning something to every effect's `player` key too.
        controller_clause != "any"
        and "controller" in model.selector
        # A `player` or `any` spec resolves the clause through
        # `_player_allowed`; every other kind resolves it through `matches`,
        # which honours a Mapping here just the same. So a **Mapping** is
        # checked whatever the kind, which is what a linked target is -- Cloak
        # and Dagger's second spec is a `permanent`, and under the old gate its
        # `{"target": "who"}` was never looked at. A bare *string* on a
        # non-player kind stays where it was: `matches` reads those names
        # itself, and they are not player specs.
        and (model.kind in ("player", "any") or isinstance(controller_clause, Mapping))
    ):
        # `targeting._player_allowed` resolves this clause through
        # `select_players`, so it is a full player spec and has to be checked as
        # one. Left unchecked it was the quietest bug in the targeting layer:
        # `validate_selector` accepts any Mapping here, so
        # `{"controller": {"controller_of": "subject"}}` compiled cleanly and
        # was then dropped by a `return True` fallthrough -- a card printed
        # "target player other than its controller" that played as "target any
        # player", strictly wider than the printing, with nothing to say so.
        #
        # Checked against the siblings declared **before** this one -- "choose
        # target opponent and up to one target creature **they** control"
        # (Cloak and Dagger, Entwined), where "they" is the other target. 601.2c
        # chooses every target at once, which is what makes the pair legal
        # together, and `enumerate_target_tuples` grows the combinations in
        # declaration order so a linked spec sees the answer it depends on.
        #
        # Earlier ones only, so a forward reference is refused rather than
        # silently resolving against a spec with no answer yet -- which offers
        # nothing, and reads on the board as a card whose second target can
        # never be chosen.
        _validate_player_spec(
            model.selector["controller"], f"{label}.controller", dict(siblings or {})
        )
    if model.total_mana_value is not None:
        if model.total_mana_value < 1:
            # A cap of zero is a spec that can only ever choose nothing, which
            # is a target line that reads as though it did something.
            raise DslError(
                f"{label}: 'total_mana_value' is a cap on the picks together, "
                f"so {model.total_mana_value} would allow nothing to be chosen"
            )
        if model.kind in ("player", "spell"):
            # A player has no mana value, and a spell's is the one thing about
            # it that is already on the stack -- neither card exists, and the
            # clause would be read against zero for every candidate.
            raise DslError(
                f"{label}: 'total_mana_value' caps the mana value of the objects "
                f"chosen, which a {model.kind!r} target does not have"
            )

    if model.permanent_selector is not None:
        _check_permanent_selector(model, label)

    zone = model.selector.get("zone")
    if model.kind == "permanent" and zone not in (None, "battlefield"):
        # A card in a graveyard, a hand or exile is not a permanent (110.1), and
        # the kind is what the rest of the engine reads the target *by*. Left
        # accepted, `candidates` would happily enumerate the other zone and the
        # card would play correctly while calling the thing it targets something
        # it is not -- which is the state a later reader of either half acts
        # wrongly on. `card_in_graveyard` and `card_in_exile` are the spellings.
        raise DslError(
            f"{label}: a 'permanent' target is on the battlefield, not in {zone!r} "
            f"-- use 'card_in_graveyard' or 'card_in_exile'"
        )
    if model.kind == "card_in_exile" and zone not in (None, "exile"):
        raise DslError(f"{label}: a 'card_in_exile' target is in exile, not in {zone!r}")
    if model.kind == "card_in_graveyard" and zone not in (None, "graveyard"):
        raise DslError(f"{label}: a 'card_in_graveyard' target is in a graveyard, not in {zone!r}")
    if isinstance(model.count, dict):
        validate_value(model.count, f"{label}.count")
    if model.up_to:
        if model.count == "any":
            raise DslError(f"{label}: 'any number of' has no ceiling to be 'up to' -- drop one")
        if model.optional:
            raise DslError(
                f"{label}: 'up_to' already includes choosing none, and 'optional' "
                f"means 'exactly N, or none' -- together they are two answers to "
                f"the same question"
            )
        if isinstance(model.count, int):
            if model.count < 1:
                raise DslError(f"{label}: 'up to {model.count}' is no target at all")
            if model.count == 1:
                # "Up to one target" is min 0 / max 1, which is precisely what
                # `optional` already means -- and it is how every shipped card
                # spells it. Two spellings of one reading is how they drift.
                raise DslError(
                    f"{label}: 'up to one target' is 'optional': true -- "
                    f"'up_to' is for a ceiling above one"
                )
    return TargetSpec(
        id=model.id,
        kind=model.kind,
        selector=dict(model.selector),
        permanent_selector=(
            dict(model.permanent_selector) if model.permanent_selector is not None else None
        ),
        count=dict(model.count) if isinstance(model.count, dict) else model.count,
        count_if_kicked=(
            dict(model.count_if_kicked)
            if isinstance(model.count_if_kicked, dict)
            else model.count_if_kicked
        ),
        up_to=model.up_to,
        one_per_player=model.one_per_player,
        optional=model.optional,
        total_mana_value=model.total_mana_value,
        mode=model.mode,
        gift_promised=model.gift_promised,
    )


def _check_reflexive_wiring(model: CardModel, abilities: tuple[Ability, ...], where: str) -> None:
    """A reflexive ability and the op that fires it must name each other.

    603.11's "when you do" has no event behind it, so the *only* thing that can
    ever put this ability on the stack is a `reflexive_trigger` op somewhere in
    the same card's effects. Both halves of that wire are silent when they go
    wrong and both are the same bug in opposite directions: an ability nothing
    fires is a printed line that never happens, and an op naming an id that is
    not there is a spell whose second sentence is missing. Neither would fail
    any other check -- the ability compiles, the op is a known name -- so this
    is the only place either can be caught.

    Every ability's effects are walked as well as `spell_effects`: the op is
    written wherever the instruction it reflects on is written, which for a
    creature's enters trigger is inside that trigger. Replacement effects have
    no effect list of their own to walk -- they modify an arrival rather than
    doing anything -- so there is nowhere for one to hide there.
    """
    declared = {
        ability.reflex_id: ability for ability in abilities if ability.kind is AbilityKind.REFLEXIVE
    }
    named: set[str] = set()

    def walk(effects: Any) -> None:
        for effect in effects or ():
            if not isinstance(effect, Mapping):
                continue
            if effect.get("op") == "reflexive_trigger":
                named.add(str(effect.get("ability", "")))
            for value in effect.values():
                if isinstance(value, Sequence) and not isinstance(value, str):
                    walk(value)

    walk(model.spell_effects)
    for ability in model.abilities:
        walk(ability.effects)

    for missing in sorted(named - set(declared)):
        raise DslError(
            f"{where}: 'reflexive_trigger' names {missing!r}, "
            f"but no reflexive ability on this card has that id "
            f"(declared: {sorted(declared) or 'none'})"
        )
    for unfired in sorted(set(declared) - named):
        raise DslError(
            f"{where}: reflexive ability {unfired!r} is never fired -- "
            f"nothing on this card writes a 'reflexive_trigger' naming it, "
            f"so the line would never happen"
        )
