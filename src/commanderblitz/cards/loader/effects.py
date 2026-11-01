"""Validation of effect specs: one check per op, and the player and delay grammar.

``_validate_effect`` is the loader's largest function -- a check per effect op
-- and the reason this module exists on its own.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from commanderblitz.engine.effects import RECORDING_OPS, known_ops
from commanderblitz.engine.effects.behold import validate_behold_selector
from commanderblitz.engine.effects.conditions import validate_condition
from commanderblitz.engine.effects.ops_cards import (
    DESTINATIONS,
    EXILE_UNTIL_ELSE_DESTINATIONS,
    LOOK_STEP_KEYS,
    REVEAL_UNTIL_MAY_DESTINATIONS,
    SEARCHABLE,
)
from commanderblitz.engine.effects.ops_counters import AMASS_TOKENS
from commanderblitz.engine.effects.ops_player import CASTABLE_ZONES
from commanderblitz.engine.effects.selectors import PLAYER_SPEC_NAMES, validate_selector
from commanderblitz.engine.effects.values import (
    validate_value,
)
from commanderblitz.engine.enums import SUBTYPE_CLASS
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import SYMBOLS as MANA_SYMBOLS
from commanderblitz.engine.mana import ManaCost, compile_restriction
from commanderblitz.engine.objects import PLAYABLE_DURATIONS
from commanderblitz.engine.structs import (
    ATTACK_MARK_DURATIONS,
    ATTACK_RESTRICTION_DURATIONS,
    BLOCK_PROHIBITION_DURATIONS,
    CANT_SACRIFICE_DURATIONS,
    CAST_LOCK_DURATIONS,
    COMBAT_FOG_DURATIONS,
    CONTROL_DURATIONS,
    DAMAGE_REDIRECT_DURATIONS,
    DAMAGE_SHIELD_DURATIONS,
    DELAYED_DURATIONS,
    FLASH_PERMISSION_DURATIONS,
    LIFE_LOCK_DURATIONS,
    PERMANENT_SHIELD_DIRECTIONS,
    PERMANENT_SHIELD_DURATIONS,
    PLAYER_PROTECTION_DURATIONS,
    PROTECTION_SENTINELS,
    UNBLOCKABLE_DURATIONS,
)
from commanderblitz.engine.triggers import (
    OBJECT_SUBJECT_TRIGGERS,
    RECIPIENT_KEYS,
    STATE_TRIGGER,
    TRIGGER_EVENTS,
)
from commanderblitz.engine.turn import DELAY_STEPS

from ..schema import CardModel, CostModel
from .statics import (
    _validate_cost_reduction,
)
from .vocabulary import (
    ATTACKING_OPS,
    CONTROLLED_TARGET_KINDS,
    COUNTERS_ON_ARRIVAL_OPS,
    DELAYED_TRIGGER_KEYS,
    HOST_NAMED_OPS,
    KNOWN_COLORS,
    KNOWN_KEYWORDS,
    KNOWN_SUPERTYPES,
    KNOWN_TYPES,
    PLACED_COUNTER_KIND,
    PLAYER_TARGET_KINDS,
    PLURAL_PLAYER_SPEC_NAMES,
    STATIC_FILTER_KEYS,
    WAS_CAST_TRIGGERS,
    refuse_numbered_grant,
)
from .walk import (
    _check_counter_kind,
    _mentions,
)

#: What `copy_permanent`'s ``except_`` may rewrite -- the copiable values of
#: 707.9b that a printed exception has needed so far. Replacements: ``colors``,
#: ``types``, ``power`` and ``toughness``. Additions: ``add_types``,
#: ``add_subtypes`` and ``add_supertypes``. Removals: ``remove_supertypes``,
#: the only subtraction any printing asks for ("except the token isn't
#: legendary"). And ``no_mana_cost``.
COPY_EXCEPT_KEYS = frozenset(
    {
        "colors",
        "types",
        "power",
        "toughness",
        "add_types",
        "add_subtypes",
        "add_supertypes",
        "remove_supertypes",
        "no_mana_cost",
    }
)


#: The recorders whose `as` binding is a **set of seats** rather than of
#: objects: `may` (the players who said yes) and `draw` (the players who
#: actually drew). Both write a bare list of player ids.
SEAT_RECORDING_OPS = frozenset({"draw", "may"})

#: The counter removals that read `up_to` -- "remove **up to** three counters".
COUNTER_REMOVAL_UP_TO_OPS = ("remove_counters", "remove_counters_from_among")

#: The ops that read `any_kind`: the card names no kind, so the controller
#: picks one counter at a time (`effects.counter_removal`).
ANY_KIND_COUNTER_OPS = ("remove_counters",)


def _validate_any_kind_counters(effect: Mapping[str, Any], op: str, where: str) -> None:
    """``any_kind`` and ``up_to`` on a counter removal: every refusal is a card
    that would load and quietly remove a different number or kind of counters."""
    if "any_kind" in effect:
        if op not in ANY_KIND_COUNTER_OPS:
            raise DslError(
                f"{where}: 'any_kind' only means anything on "
                f"{' or '.join(ANY_KIND_COUNTER_OPS)}, not {op!r}"
            )
        if not isinstance(effect["any_kind"], bool):
            raise DslError(f"{where}: 'any_kind' is a boolean, got {effect['any_kind']!r}")
    any_kind = bool(effect.get("any_kind"))
    if op not in COUNTER_REMOVAL_UP_TO_OPS and op not in ANY_KIND_COUNTER_OPS:
        return
    if op == "remove_counters_from_among":
        # Always any kinds, so it takes neither spelling of a kind; and the
        # number is `amount`, where the cost of the same name says `count`.
        if "counter" in effect:
            raise DslError(
                f"{where}: remove_counters_from_among removes counters of any kind; "
                f"a named 'counter' kind is not read"
            )
        objects = effect.get("objects")
        if not isinstance(objects, Mapping) or not objects:
            raise DslError(
                f"{where}: remove_counters_from_among needs 'objects' naming the "
                f"permanents the counters may come off"
            )
        if "count" in objects or "chooser" in objects:
            raise DslError(
                f"{where}.objects: the permanents are a pool the controller picks "
                f"from one counter at a time; the number is the op's 'amount', not "
                f"a selector 'count' or 'chooser'"
            )
        any_kind = True
    if any_kind and "counter" in effect:
        # One says "this kind", the other "whichever kinds the chooser likes";
        # the op would read `any_kind` and the printed kind would be ignored.
        raise DslError(
            f"{where}: 'any_kind' and a named 'counter' contradict each other -- "
            f"drop 'counter' for counters of any kind"
        )
    if any_kind and not effect.get("objects"):
        raise DslError(f"{where}: {op} needs 'objects' naming the permanents counters come off")
    if effect.get("up_to"):
        if op == "remove_counters" and not any_kind:
            # The named-kind removal takes exactly `amount`; an `up_to` there
            # would load and be ignored.
            raise DslError(
                f"{where}: 'up_to' on remove_counters needs 'any_kind' -- the "
                f"named-kind removal takes exactly 'amount'"
            )
        if "amount" not in effect:
            raise DslError(
                f"{where}: 'up_to' needs an 'amount' to be a ceiling of; with no "
                f"'amount' the removal is already \"any number\""
            )
    if any_kind or effect.get("up_to"):
        amount = effect.get("amount")
        if isinstance(amount, Mapping) and set(amount) == {"const"}:
            amount = amount["const"]
        if isinstance(amount, int) and not isinstance(amount, bool) and amount < 1:
            raise DslError(f"{where}: removing {amount} counters removes none")

#: Every key whose value `resolve_pool` reads as a pool of **objects**. A bare
#: `{"binding": …}` under any other key is a player spec.
_OBJECT_POOL_KEYS = ("count", "exists", "objects", "per", "from", "attacker", "source_object")


def _refuse_seats_read_as_objects(model: CardModel, where: str) -> None:
    """A seat binding read as a pool of objects counts the wrong thing.

    `resolve_pool` reads any bound list as oids, and a seat binding is a list of
    player ids -- small integers that are also the ids of real objects. So
    Cut a Deal written as ``{"count": {"binding": "drew"}}`` loads, resolves,
    and draws one card for every *object* whose id happens to equal a seat that
    drew -- right by accident while those objects exist, and wrong the moment
    one of them leaves the game. The count of a seat set is a
    `for_each_player` over it.
    """
    names: set[str] = set()

    def collect(node: Mapping[str, Any]) -> bool:
        if node.get("op") in SEAT_RECORDING_OPS and isinstance(node.get("as"), str):
            names.add(node["as"])
        return False

    _mentions(model, collect)
    if not names:
        return

    def reads_as_objects(node: Mapping[str, Any]) -> bool:
        if node.get("exclude_binding") in names:
            return True
        return any(
            isinstance(node.get(key), Mapping) and node[key].get("binding") in names
            for key in _OBJECT_POOL_KEYS
        )

    if _mentions(model, reads_as_objects):
        raise DslError(
            f"{where}: reads a binding written by {sorted(SEAT_RECORDING_OPS)} as a pool "
            f"of objects, but it holds players -- name the seats with the "
            f"{{'binding': …}} player spec, and count them with a for_each_player over it"
        )


def _validate_pay_x(effect: Mapping[str, Any], where: str) -> None:
    """``may``'s ``x``: the ceiling on an announced X, and where X is bound.

    ``as`` is required -- without it the payment charges for X and nothing reads
    the number, so the card pays for X cards and draws none.

    ``max`` is **optional**, and its absence is a statement. A printed ceiling
    ("less than or equal to the amount of life you gained" -- Well of Lost
    Dreams) is the rule the card makes, and omitting it there would pay for ten
    cards off a one-life gain. But a great many cards print no ceiling at all --
    Decree of Justice's "you may pay {X}. If you do, create X 1/1 white Soldier
    creature tokens" -- and for those the only bound is 118.3, what the player
    can actually pay. Requiring a number there forced an invented one, and the
    invented number was load-bearing rather than cosmetic: `_announce_x` feeds
    it to `max_affordable_x` as the probe `cap`, so a made-up 20 is a printed
    rule the card does not have.

    This is *not* join forces, which the old docstring conflated it with.
    `op_join_forces` walks every player in turn order asking for `{1}` at a
    time and binds the sum; an unbounded X here is announced once, by one
    player, and no opponent may add to it.
    """
    spec = effect["x"]
    if not isinstance(spec, Mapping):
        raise DslError(f"{where}.x: must be an object with 'as' and an optional 'max'")
    if unknown := set(spec) - {"max", "as", "prompt"}:
        raise DslError(f"{where}.x: unsupported keys {sorted(unknown)} (takes 'max', 'as', 'prompt')")
    if "max" in spec:
        validate_value(spec["max"], f"{where}.x.max")
    if not (isinstance(spec.get("as"), str) and spec["as"]):
        raise DslError(f"{where}.x.as: a binding name for the announced X is required")
    if effect.get("repeat"):
        # Each yes would announce and bind a new X over the last one, and no
        # printed "repeat this process" pays an X.
        raise DslError(f"{where}.x: an announced X cannot be combined with 'repeat'")
    if effect["pay"].get("times") is not None:
        raise DslError(f"{where}.x: an announced X cannot be combined with 'pay.times'")
    if effect["pay"].get("mana_reduction") is not None:
        # The ceiling is priced off the printed mana; a reduction would make the
        # offered X and the charged X disagree.
        raise DslError(f"{where}.x: an announced X cannot be combined with 'pay.mana_reduction'")


def _validate_pay_any_amount(effect: Mapping[str, Any], where: str) -> None:
    """``may``'s ``any_amount``: "you may pay any amount of {R}" -- Leyline Tyrant.

    The ``pay`` is **exactly one coloured (or {C}) symbol and nothing else**,
    because the announced count multiplies it: ``{R}`` at three is
    ``{R}{R}{R}``. A generic ``{1}`` there is "any amount of mana", which is
    ``{X}`` and the ``x`` key; ``{R}{R}`` would charge pairs; a life or
    sacrifice beside it would be multiplied or charged once, and no printing
    says which.

    ``as`` is required -- the count is the whole point of "deals that much
    damage", and without it the payment buys a number nothing reads.

    Refused beside ``x`` (two announcements of one payment), ``repeat`` (each
    yes would rebind the count over the last), ``pay.times`` (a computed
    multiplier on top of a chosen one) and ``pay.mana_reduction`` (the ceiling
    is priced off the printed symbol).
    """
    spec = effect["any_amount"]
    if not isinstance(spec, Mapping):
        raise DslError(f"{where}.any_amount: must be an object with 'as' and an optional 'prompt'")
    if unknown := set(spec) - {"as", "prompt"}:
        raise DslError(
            f"{where}.any_amount: unsupported keys {sorted(unknown)} (takes 'as', 'prompt')"
        )
    if not (isinstance(spec.get("as"), str) and spec["as"]):
        raise DslError(f"{where}.any_amount.as: a binding name for the amount paid is required")
    pay_spec = effect["pay"]
    if extra := {k for k, v in pay_spec.items() if v not in (None, False, 0)} - {"mana"}:
        raise DslError(
            f"{where}.any_amount: the payment is one mana symbol and nothing else; "
            f"'pay' also has {sorted(extra)}"
        )
    mana = ManaCost.parse(pay_spec.get("mana"))
    if mana.generic or mana.x_count or mana.hybrid or sum(mana.colored) != 1:
        raise DslError(
            f"{where}.any_amount: 'pay.mana' must be exactly one coloured or {{C}} symbol "
            f"(\"{{R}}\"), not {pay_spec.get('mana')!r} -- any amount of generic mana is "
            f"'{{X}}' with 'x'"
        )
    if "x" in effect:
        raise DslError(f"{where}.any_amount: cannot be combined with 'x'")
    if effect.get("repeat"):
        raise DslError(f"{where}.any_amount: cannot be combined with 'repeat'")


def _validate_enchanted_player(model: CardModel, where: str) -> None:
    """``"enchanted_player"`` only on a card that can *be* attached to a player.

    The spec resolves to `GameObject.attached_to_player`, which only
    `stack._attach_aura` and the `attach_to_player` primitive ever write, and
    only for an **Aura**. On anything else it resolves to `[]` for the whole
    game -- and an empty player list is the quietest failure in the effect
    layer: a `gain_life` aimed at nobody logs nothing, a `create_token` makes no
    token, and the card reads on screen as though it has an ability.

    "Enchant player" is one of the Aura's enchant clauses (303.4a), so the
    subtype is the whole test. Whether the card also *declares* a player target
    is not checked here: an Aura can be put onto the battlefield attached by an
    effect rather than cast, and the target line is only how a cast one says it.

    Walks the whole card rather than going through `_mentions`, which searches
    effects, targets and trigger conditions. A **static** flattens its
    parameters onto the ability (``effect``, ``affects``, ``power``) and has no
    ``effects`` list at all, so `_mentions` cannot see an ``affects`` filter --
    and ``{"controller": "enchanted_player"}`` inside one is the exact spelling
    this refuses, since `characteristics._matches` would read an unknown
    controller word as matching every permanent on the table.
    """
    if "Aura" in model.subtypes:
        return

    def walk(node: Any) -> bool:
        if isinstance(node, Mapping):
            return "enchanted_player" in node.values() or any(walk(v) for v in node.values())
        if isinstance(node, (list, tuple)):
            return any(walk(v) for v in node)
        return False

    if walk(model.model_dump()):
        raise DslError(
            f"{where}: 'enchanted_player' names the player this **Aura** is "
            f"attached to (303.4a), and only an Aura is ever attached to one -- "
            f"on {model.subtypes or 'this card'} it resolves to nobody, every "
            f"time, and the ability silently does nothing"
        )


def _validate_attach_to_player(model: CardModel, where: str) -> None:
    """``attach`` with ``player`` only on an Aura that enchants a player.

    The op moves the ability's **source** onto a seat, and reads the legal
    hosts off the source's first declared target (303.4a) -- the enchant
    clause. On anything but an Aura whose clause names a player the op could
    never attach, and the ability would read on screen as though it did.
    """

    def walk(node: Any) -> bool:
        if isinstance(node, Mapping):
            if node.get("op") == "attach" and "player" in node:
                return True
            return any(walk(v) for v in node.values())
        if isinstance(node, (list, tuple)):
            return any(walk(v) for v in node)
        return False

    if not walk(model.model_dump()):
        return
    if "Aura" not in model.subtypes or not model.targets or model.targets[0].kind != "player":
        raise DslError(
            f"{where}: attach with 'player' moves this Aura onto a player, so the "
            f"card must be an Aura whose enchant clause -- its first target -- "
            f"is kind 'player' (303.4a)"
        )


def _validate_was_cast_placement(model: CardModel, where: str) -> None:
    """``was_cast`` only on this permanent's own enters trigger (603.6e)."""

    def reads(node: Any) -> bool:
        return isinstance(node, Mapping) and "was_cast" in node

    def walk(node: Any) -> bool:
        if isinstance(node, Mapping):
            return reads(node) or any(walk(v) for v in node.values())
        if isinstance(node, (list, tuple)):
            return any(walk(v) for v in node)
        return False

    stray = walk(model.spell_effects) or walk([t.model_dump() for t in model.targets])
    for ability in model.abilities:
        event = ability.trigger.event if ability.trigger is not None else None
        if event in WAS_CAST_TRIGGERS:
            continue
        stray = (
            stray
            or walk(ability.effects)
            or walk([t.model_dump() for t in ability.targets])
            or walk(ability.trigger.condition if ability.trigger else None)
        )
    if stray:
        raise DslError(
            f"{where}: {{'was_cast': …}} reads how the ability's **own source** "
            f"arrived on the battlefield, so it belongs on a "
            f"{sorted(WAS_CAST_TRIGGERS)} trigger (603.6e) and nowhere else -- "
            f"anywhere else it answers about the wrong object, or about one that "
            f"has not entered at all"
        )


def _refuse_targets_inside_a_delay(effects: Any, where: str) -> None:
    """A ``target`` selector inside a ``delay`` names nothing when it fires.

    "Exile another target creature you control… at the beginning of the next end
    step, return **that card** to the battlefield" -- Gilraen, Dúnedain Protector,
    and the whole Flickerwisp family behind her.  The obvious way to write the
    second half is to point it at the same ``t1`` the first half targeted, and it
    reads correctly, loads correctly, and does nothing at all: ``turn._run_delayed``
    builds the delayed context with ``targets={}``, because the delayed half is a
    separate ability that never chose a target of its own (603.7 -- the delayed
    trigger is created by the resolving ability, it does not inherit its targets),
    and rule 608.2b's re-check has nothing to re-check against.

    Filling the targets in instead would be the wrong repair twice over.  It would
    invent a legality check no rule asks for, and it would not even reach this
    card: a ``target`` selector defaults its zone to the battlefield precisely
    because a target *is* re-checked, and the object a delay is about has by
    construction just changed zones.  The idiom that works is the one
    ``effect_result_binding`` shipped -- ``as`` on the op that moved the card, and
    ``binding`` on the op that brings it back, which is a record rather than a
    reference and so survives the zone change.  So this is a refusal that names it.
    """

    def walk(node: Any, path: str) -> None:
        if isinstance(node, Mapping):
            if "target" in node:
                raise DslError(
                    f"{path}: a 'target' inside a delay resolves to nothing -- the "
                    f"delayed trigger has no targets of its own. Record the object "
                    f"with 'as' on the op that moved it and name it with 'binding'."
                )
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}[{i}]")

    walk(list(effects), where)


def _validate_cast_lock_zones(named: Any, opened: Any, where: str) -> None:
    """Check a cast lock's ``zones`` / ``except_zones`` pair.

    One check for both forms of `cant_cast_spells_from_zones` -- the timed op
    (Avatar's Wrath) and the battlefield static (Drannith Magistrate) -- so the
    two spellings of one sentence cannot drift into accepting different cards.
    """
    if (named is None) == (opened is None):
        # Both, or neither. Neither locks nothing while printing a
        # prohibition; both are two answers to one question, and the
        # positive list would silently win.
        raise DslError(
            f"{where}: cant_cast_spells_from_zones needs exactly one of "
            f"'zones' (the shut ones) or 'except_zones' (the open ones)"
        )
    for zone in named if named is not None else opened:
        if str(zone) not in CASTABLE_ZONES:
            # A misspelled zone in `zones` locks one door fewer than the
            # card says, and in `except_zones` locks one *more*. Both are
            # the wrong card, silently.
            raise DslError(
                f"{where}: unknown zone {zone!r} (implemented: {sorted(CASTABLE_ZONES)})"
            )


def _refuse_protection_sentinels(subtypes: Any, where: str) -> None:
    """Refuse "colorless" or "everything" written as a protection *subtype*.

    Both are qualities stored as sentinel strings in the same flat set the
    subtypes go into, and ``from_subtypes`` is not checked against a subtype
    list -- so ``"from_subtypes": ["colorless"]`` would load and quietly *be*
    protection from colorless without the flag that says so. One spelling per
    quality: ``from_colorless`` / ``from_everything``.
    """
    for i, entry in enumerate(subtypes or ()):
        if entry in PROTECTION_SENTINELS:
            raise DslError(
                f"{where}.from_subtypes[{i}]: {entry!r} is not a subtype -- "
                f"write 'from_{entry}': true"
            )


def _validate_player_spec(who: Any, where: str, target_kinds: Mapping[str, str]) -> None:
    """Check one *player* spec -- an effect's ``player``, or a side of one.

    Every way of writing this wrong is silent, and one of them was a shipped
    card doing the opposite of what it printed.

    A misspelled **name** (``"each_oponent"``) raises only once the ability
    resolves. A **target id the card never declared** resolves to nobody:
    Hellrider's ``{"target": "defender"}`` named a trigger *binding*, which
    `select_players` never reads, so the card dealt no damage at all and every
    board it was on looked like a board where nothing had happened.

    And the case this validator was written for: ``{"target": "t1"}`` pointed at
    a **spell** target. `ctx.target_players` keeps only refs of kind
    ``"player"`` and a spell's ref is kind ``"stack"``, so it returns ``[]`` --
    and `op_may` reads "nobody" as "me" (``chooser = ctx.controller``) and bills
    the *counterspell's* controller. "Counter target spell unless its controller
    pays {3}" became "unless **you** pay {3}", which is a legal-looking card
    that plays as its own opposite. `controller_of_target` is the key that says
    it, and this refuses the near miss by name rather than letting it load.
    """
    if isinstance(who, str) and who not in PLAYER_SPEC_NAMES:
        raise DslError(
            f"{where}: unknown player spec {who!r} "
            f"(implemented: {sorted(PLAYER_SPEC_NAMES)}, or a target)"
        )
    if not isinstance(who, Mapping):
        return
    if "except" in who:
        # "each **opponent** who discarded their hand this way" -- Snort. An
        # inclusive spec narrowed by a seat, which `not` cannot do: `not` is the
        # complement over the whole table, and the set a binding holds includes
        # you whenever you took the same option. Both halves are validated in
        # their own right, and the rest of the mapping has to be a real spec --
        # a bare `{"except": "you"}` names everyone the long way round.
        _validate_player_spec(who["except"], f"{where}.except", target_kinds)
        rest = {k: v for k, v in who.items() if k != "except"}
        if not rest:
            raise DslError(
                f"{where}: 'except' narrows another spec, so there has to be one "
                f"to narrow -- use {{'not': ...}} for a bare complement"
            )
        _validate_player_spec(rest, where, target_kinds)
        return
    if "attacked_by" in who:
        # "Each player this creature attacked this turn" -- Angel of Destiny.
        # "self" is the only subject a card prints, and anything else would
        # load and resolve to nobody, which on a card that ends games is the
        # quiet failure.
        if who["attacked_by"] != "self" or len(who) > 1:
            raise DslError(
                f"{where}: 'attacked_by' takes 'self' and stands alone "
                f'({{"attacked_by": "self"}}), got {dict(who)!r}'
            )
        return
    if "dealt_combat_damage_by" in who:
        # "…whose controller was dealt combat damage by this creature this
        # turn" -- Steel Hellkite. The same shape as `attacked_by` and refused
        # for the same reason: any subject but "self" would load and resolve to
        # nobody, and a card that destroys nothing looks like a quiet board.
        if who["dealt_combat_damage_by"] != "self" or len(who) > 1:
            raise DslError(
                f"{where}: 'dealt_combat_damage_by' takes 'self' and stands alone "
                f'({{"dealt_combat_damage_by": "self"}}), got {dict(who)!r}'
            )
        return
    if "not" in who:
        # "target player **other than** its controller." The complement of a
        # spec, so whatever it wraps has to be a legal spec in its own right --
        # otherwise `{"not": {"target": "t9"}}` names an undeclared target and
        # excludes nobody, which reads as "target any player".
        _validate_player_spec(who["not"], f"{where}.not", target_kinds)
        if len(who) > 1:
            raise DslError(
                f"{where}: 'not' is the whole spec -- it cannot be combined with "
                f"{sorted(set(who) - {'not'})}"
            )
        return
    for key in ("target", "controller_of_target"):
        if key not in who:
            continue
        tid = str(who[key])
        if tid not in target_kinds:
            raise DslError(f"{where}: references target {tid!r} which the card does not declare")
        kind = target_kinds[tid]
        if key == "target" and kind not in PLAYER_TARGET_KINDS:
            raise DslError(
                f"{where}: target {tid!r} is a {kind!r}, which is never a player -- "
                f"use {{'controller_of_target': {tid!r}}} to bill the one who controls it"
            )
        if key == "controller_of_target" and kind not in CONTROLLED_TARGET_KINDS:
            raise DslError(
                f"{where}: target {tid!r} is a {kind!r}, which has no controller -- "
                f"use {{'target': {tid!r}}} to name the player it chose"
            )


def _validate_nested_player_refs(node: Any, where: str, target_kinds: Mapping[str, str]) -> None:
    """Check every player spec a selector or value carries *inside* it.

    "Create X tokens, where X is the number of creatures **those opponents**
    control" is ``{"count": {"types": ["Creature"], "controller": {"target":
    "t1"}}}`` -- a player spec two levels down, in a value's selector. The
    top-level keys an effect names a player with (``player``, ``chooser``,
    ``controller``) were validated; one nested in a selector was not, so
    ``{"target": "t9"}`` there loaded clean and counted nobody, and so did a
    ``{"target": …}`` aimed at a `permanent` target, whose refs are never
    players. Every failure here is a zero, which on a board looks like a card
    that happened to find nothing.

    Walked rather than read off known paths, because selectors nest -- inside
    `any_of`, inside `max_count_of`, inside `sum` -- and it is the same check
    wherever the clause sits. Only the two keys a selector spells a seat with
    are read, and only in their mapping form: the words are checked by
    `validate_selector` already.
    """
    if isinstance(node, Mapping):
        for key, value in node.items():
            path = f"{where}.{key}"
            if key in ("controller", "player") and isinstance(value, Mapping):
                _validate_player_spec(value, path, target_kinds)
            else:
                _validate_nested_player_refs(value, path, target_kinds)
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            _validate_nested_player_refs(value, f"{where}[{i}]", target_kinds)


def _validate_attacking(who: Any, where: str, target_kinds: Mapping[str, str]) -> None:
    """Check an ``attacking`` clause: the boolean, or a player spec.

    ``true`` is the original and much the commonest spelling -- "wherever the
    source is already pointed" -- and it is checked here only so that the *other*
    forms can be. A player spec says "attacking **that player**", which the
    boolean cannot: Ainok Strike Leader points one token at each opponent, and
    Combat Calligrapher points one at a defender while never attacking itself.

    Both failures this refuses are silent at runtime. A plural spec has no
    single answer -- a creature attacks exactly one player -- and picking one
    would make a card that reads "each opponent" and hits one seat. A bare
    number would be a *seat*, which no printed card names, and ``0`` is
    indistinguishable from ``false``.
    """
    if isinstance(who, bool):
        return
    if isinstance(who, str) and who in PLURAL_PLAYER_SPEC_NAMES:
        raise DslError(
            f"{where}: {who!r} can name several players and a creature attacks one -- "
            f"name the seat ({{'binding': 'each_player'}} inside a for_each_player, "
            f"a trigger binding, or a target)"
        )
    if not isinstance(who, str | Mapping):
        raise DslError(f"{where}: must be true/false or a player spec, got {who!r}")
    _validate_player_spec(who, where, target_kinds)


def _validate_delayed_trigger(effect: Mapping[str, Any], where: str) -> None:
    """Check the ``trigger`` half of a ``delayed_trigger`` op.

    A misnamed event here fails in exactly the way `delay`'s misspelled step
    does -- the subscription is installed, nothing ever satisfies it, and the
    card reads as printed while doing nothing at all.
    """
    trigger = effect.get("trigger")
    if not isinstance(trigger, Mapping) or not trigger.get("event"):
        raise DslError(
            f"{where}: delayed_trigger needs a 'trigger' naming the event it "
            f"watches (implemented: {sorted(TRIGGER_EVENTS)})"
        )
    event = str(trigger["event"])
    if event not in TRIGGER_EVENTS:
        raise DslError(
            f"{where}: unknown trigger event {event!r} (implemented: {sorted(TRIGGER_EVENTS)})"
        )
    if event == STATE_TRIGGER:
        # Nothing is ever emitted under this name: a state trigger is found by
        # `triggers.check_state_triggers` walking the battlefield's printed
        # abilities, so a delayed one would be installed and never fire.
        raise DslError(
            f"{where}: a delayed_trigger watches an event, and {STATE_TRIGGER!r} "
            f"is a printed state trigger's, not one"
        )
    unsupported = sorted(set(trigger) - DELAYED_TRIGGER_KEYS)
    if unsupported:
        raise DslError(
            f"{where}.trigger: {unsupported[0]!r} is not supported on a delayed "
            f"trigger -- it is read off the permanent hosting the ability, and a "
            f"delayed one has none. Supported: {sorted(DELAYED_TRIGGER_KEYS)}"
        )
    controller = str(trigger.get("controller", "you"))
    if controller not in ("you", "opponent", "any"):
        raise DslError(f"{where}.trigger: unknown controller {controller!r}")
    if (subject := trigger.get("subject")) is not None:
        # "Whenever **that creature** deals combat damage…" -- Hunter's
        # Insight. The one object this subscription is about, named the way a
        # resolving effect names an object it already has in hand.
        if not isinstance(subject, Mapping) or not (set(subject) & {"target", "binding"}):
            raise DslError(
                f"{where}.trigger.subject: names one object the delayed ability "
                f"already has -- a {{'target': ...}} or a {{'binding': ...}}"
            )
        validate_selector(subject, f"{where}.trigger.subject")

        if event not in OBJECT_SUBJECT_TRIGGERS:
            # Scoped to an object against an event that has none, the clause is
            # compared with nothing and the subscription never fires -- the card
            # reads as printed and does nothing, which is the failure this whole
            # pass exists to refuse.
            raise DslError(
                f"{where}.trigger: {event!r} has no object subject for a "
                f"'subject' to scope against (events that do: "
                f"{sorted(OBJECT_SUBJECT_TRIGGERS)})"
            )
    if (recipient := trigger.get("recipient")) is not None:
        # "…deals combat damage **to Vraska**" -- the permanent being hit.
        # Only on an event whose recipient is a permanent the event names apart
        # from its subject; anywhere else it would be compared with nothing and
        # the subscription would never fire.
        if not isinstance(recipient, Mapping) or not (
            set(recipient) & {"target", "binding", "self_only"}
        ):
            raise DslError(
                f"{where}.trigger.recipient: names the permanent being hit -- a "
                f"{{'target': ...}}, a {{'binding': ...}} or {{'self_only': true}}"
            )
        validate_selector(recipient, f"{where}.trigger.recipient")
        if event not in RECIPIENT_KEYS:
            raise DslError(
                f"{where}.trigger: {event!r} names no recipient for a 'recipient' "
                f"to scope against (events that do: {sorted(RECIPIENT_KEYS)})"
            )
    validate_condition(trigger.get("condition"), f"{where}.trigger.condition")
    # How long the subscription lasts, and what firing does to it. A misspelled
    # value would fall through to the `this_turn` default and quietly retime the
    # card: Palace Jailer's exile would end at cleanup instead of when the crown
    # moves, which is a materially weaker card that reads identically.
    duration = str(effect.get("duration", "this_turn"))
    if duration not in DELAYED_DURATIONS:
        raise DslError(
            f"{where}: unknown delayed_trigger duration {duration!r} "
            f"(implemented: {sorted(DELAYED_DURATIONS)})"
        )
    if not effect.get("effects"):
        raise DslError(f"{where}: delayed_trigger needs 'effects' to schedule")
    # The same refusal `delay` carries, and for the same reason: 603.7 says the
    # resolving ability *creates* the delayed one, so what it creates never
    # chose a target -- `triggers.run_armed_delays` builds its context with
    # `targets={}` exactly as `turn._run_delayed` does.
    _refuse_targets_inside_a_delay(effect.get("effects") or (), f"{where}.effects")


def _reads_announced_x(node: Any) -> bool:
    """Does this value expression read the X announced as the spell was cast?"""
    if node == "x":
        return True
    if isinstance(node, Mapping):
        return "x" in node or any(_reads_announced_x(v) for v in node.values())
    if isinstance(node, (list, tuple)):
        return any(_reads_announced_x(v) for v in node)
    return False


def _validate_effect(effect: Any, where: str, target_kinds: Mapping[str, str]) -> None:
    """Recursively validate one effect dict."""
    if not isinstance(effect, Mapping):
        raise DslError(f"{where}: effect must be an object")
    op = effect.get("op")
    if op is None:
        raise DslError(f"{where}: effect is missing 'op'")
    if op not in known_ops():
        raise DslError(f"{where}: unknown effect op {op!r} (implemented: {sorted(known_ops())})")
    if op == "become_level":
        # 716.2a's effect, supplied by the loader on a `kind: "level"` line and
        # only there -- where the "only if level N-1, only as a sorcery"
        # restriction comes with it. Written by hand anywhere else it is a level
        # bought at instant speed, twice, or out of order.
        raise DslError(
            f"{where}: 'become_level' is written by the loader for a level line; "
            f'write {{"kind": "level", "level": N, "cost": ...}} instead'
        )

    for key in ("objects", "per", "selector", "affects"):
        if key in effect:
            validate_selector(effect[key], f"{where}.{key}")
    for key in ("amount", "count", "power", "toughness"):
        if key in effect:
            validate_value(effect[key], f"{where}.{key}")
    if "condition" in effect:
        validate_condition(effect["condition"], f"{where}.condition")
    # Every op that names a counter kind spells it `counter` -- `add_counters`,
    # `remove_counters`, `move_counters` -- so this is checked once here rather
    # than per op, and the next op to grow one is covered before it is written.
    if "counter" in effect and isinstance(effect["counter"], Mapping):
        # "The same number and kind of counters": the kind the triggering
        # placement put, read off the bindings. Only `add_counters` reads the
        # mapping, and only this one; that it sits on a `counter_placed`
        # trigger is checked where the trigger is in view (`reads_placed_kind`).
        if op != "add_counters" or dict(effect["counter"]) != PLACED_COUNTER_KIND:
            raise DslError(
                f"{where}.counter: a counter kind is a string, or "
                f"{PLACED_COUNTER_KIND} on add_counters for the kind a "
                f"counter_placed trigger's placement put; got {effect['counter']!r} "
                f"on {op!r}"
            )
    elif "counter" in effect:
        _check_counter_kind(effect["counter"], f"{where}.counter")
    # `return_from_graveyard`'s "return it with a lifelink counter on it" spells
    # the same thing as a kind-keyed map, so both spellings are covered.
    if isinstance(effect.get("counters"), Mapping):
        for kind in effect["counters"]:
            _check_counter_kind(kind, f"{where}.counters")
        # And the map has to be written on an op that reads it. Only the two
        # ops that *move a card onto the battlefield* do -- "with a vigilance
        # counter and a lifelink counter on it" is a clause about arriving --
        # and anywhere else it is accepted, ignored, and the card silently
        # comes back bare. That is the failure this whole pass exists to stop,
        # and it is the one shape of it a keyword counter makes invisible: the
        # creature simply does not have vigilance, and nothing says why.
        if op not in COUNTERS_ON_ARRIVAL_OPS:
            raise DslError(
                f"{where}: 'counters' is what a permanent arrives with and only "
                f"{sorted(COUNTERS_ON_ARRIVAL_OPS)} read it, not {op!r} "
                f"(use a separate add_counters)"
            )

    # "…to the battlefield **attached to that token**": the effect names the
    # Aura's host itself, with a following `attach`, so 303.4f's choice is not
    # asked. Only the two ops that put a card onto the battlefield and are
    # followed by such an `attach` read it, and only beside the battlefield.
    if "host_named" in effect:
        if op not in HOST_NAMED_OPS or not isinstance(effect["host_named"], bool):
            raise DslError(
                f"{where}: 'host_named' is a boolean read by {sorted(HOST_NAMED_OPS)}, "
                f"not {op!r}"
            )
        if op == "return_from_graveyard" and effect.get("destination") != "battlefield":
            raise DslError(
                f"{where}: 'host_named' needs destination 'battlefield'; an Aura "
                f"enchants nothing anywhere else"
            )

    # "…put onto the battlefield with this Aura" (Animate Dead): `link` on a
    # return is written on the creature as it arrives, so anywhere but the
    # battlefield it would load and link nothing -- the Aura's "that creature's
    # controller sacrifices it" then finding no creature at all.
    if op == "return_from_graveyard" and "link" in effect and (
        not isinstance(effect["link"], bool)
        or (effect["link"] and effect.get("destination") != "battlefield")
    ):
        raise DslError(
            f"{where}: return_from_graveyard 'link' is a boolean and needs "
            f"destination 'battlefield'"
        )

    if "target" in effect and str(effect["target"]) not in target_kinds:
        raise DslError(
            f"{where}: references target {effect['target']!r} which the card does not declare"
        )
    for key in ("objects", "per", "selector", "affects", "amount", "count", "power", "toughness"):
        if key in effect:
            _validate_nested_player_refs(effect[key], f"{where}.{key}", target_kinds)
    for key in ("objects", "per", "selector"):
        sub = effect.get(key)
        if isinstance(sub, Mapping) and "target" in sub and str(sub["target"]) not in target_kinds:
            raise DslError(
                f"{where}.{key}: references target {sub['target']!r} which the card does not declare"
            )
    if op == "return_spell_to_hand":
        # "Return target **spell** to its owner's hand." The op reads
        # `ctx.target_sids`, which keeps only refs of kind `"stack"` -- so aimed
        # at a `permanent` or `player` target it returns nothing, silently, and
        # the card resolves having done exactly half of what it says. Both
        # halves of that are checked: the target has to exist, and it has to be
        # the kind that can *be* a spell.
        tid = str(effect.get("target", "t1"))
        if tid not in target_kinds:
            raise DslError(
                f"{where}: return_spell_to_hand references target {tid!r} "
                f"which the card does not declare"
            )
        if target_kinds[tid] not in ("spell", "spell_or_permanent"):
            raise DslError(
                f"{where}: return_spell_to_hand needs a target of kind 'spell' or "
                f"'spell_or_permanent', and {tid!r} is {target_kinds[tid]!r} "
                f"(a permanent alone goes back with return_to_hand)"
            )
        if "objects" in effect:
            # The obvious thing to write, copied off `return_to_hand`, and it is
            # accepted and ignored: a spell is named by the target it was cast
            # at, not by a selector over a zone. Refused rather than dropped,
            # because "return every spell on the stack" is a different card.
            raise DslError(
                f"{where}: return_spell_to_hand reads no 'objects' -- it takes "
                f"the spell its 'target' names"
            )
    if op == "grant_graveyard_cast":
        # The spec IS a `cast_from_graveyard` static, so the two things that
        # static must always carry are required here too, and for the same
        # reasons the static's own loader gives them.
        if not effect.get("affects_spells"):
            # An empty filter frees the whole graveyard, so a missing one has to
            # be a load error rather than a default -- `graveyard_cast_allows`
            # returns False on an absent filter precisely so a compile bug hands
            # over nothing instead of everything, and that is a floor, not a
            # spelling.
            raise DslError(
                f"{where}: grant_graveyard_cast needs 'affects_spells' -- "
                f"without it the permission names no cards"
            )
        if not effect.get("max_per_turn") and not effect.get("grants_flashback"):
            # A permission that neither meters nor exiles recasts one card every
            # turn for ever. `grants_flashback` IS the rate limit for the cards
            # that print no cap -- the spent card is the brake -- which is the
            # argument the static's loader makes in the same words.
            raise DslError(
                f"{where}: grant_graveyard_cast needs 'max_per_turn' or "
                f"'grants_flashback' -- an unmetered permission is an engine, "
                f"not a printed line"
            )
    if op in ("grant_rebound", "grant_plot"):
        # The same two checks `return_spell_to_hand` makes, for the same reason
        # and with the same failure mode: the op reads one stack object, and a
        # `target` that names a permanent or a player finds no spell, sets
        # nothing and leaves a card that says "it gains rebound" and does not.
        if "target" in effect:
            tid = str(effect["target"])
            if tid not in target_kinds:
                raise DslError(
                    f"{where}: {op} references target {tid!r} "
                    f"which the card does not declare"
                )
            if target_kinds[tid] != "spell":
                raise DslError(
                    f"{where}: {op} needs a target of kind 'spell', "
                    f"and {tid!r} is {target_kinds[tid]!r}"
                )
        if "objects" in effect:
            # Refused rather than dropped, exactly as above: a spell is named
            # by the target it was cast at or by the trigger that saw it, never
            # by a selector over a zone, and "every spell on the stack gains
            # rebound" is a card nobody has printed.
            raise DslError(
                f"{where}: {op} reads no 'objects' -- it takes the "
                f"spell its trigger bound, or the one its 'target' names"
            )
    # Every op that names a player spells it `player` and every one of them
    # feeds `select_players`, so this is checked once here rather than per op --
    # the way `counter` is. `become_monarch`, `goad` and `cant_attack_player`
    # each grew their own copy of this check because there was no general one;
    # they now call the same validator, and the next op to take a player is
    # covered before it is written.
    if "player" in effect:
        _validate_player_spec(effect["player"], f"{where}.player", target_kinds)
    if effect.get("op") == "choose_mode" and "chooser" in effect:
        # "Target player adds one mana of any color" -- the player adding picks
        # the colour. An ordinary player spec, so "target" reaches the targeted
        # seat and the usual vocabulary is available.
        _validate_player_spec(effect["chooser"], f"{where}.chooser", target_kinds)

    if op == "repeat_while":
        # Both halves are load-bearing and each has a distinct silent failure.
        # Without `condition` the loop runs to its hundred-iteration guard every
        # time; without `effects` it is a hundred passes of nothing. Neither
        # crashes, and both read on the card as the printed sentence.
        validate_condition(effect.get("condition"), f"{where}.condition")
        if effect.get("condition") is None:
            raise DslError(
                f"{where}: repeat_while needs a 'condition' -- it is re-read after "
                f"each pass, and without one the loop only ever stops at the guard"
            )
        if not effect.get("effects"):
            raise DslError(f"{where}: repeat_while needs 'effects' to repeat")
        reset = effect.get("reset")
        if reset is not None and (
            not isinstance(reset, list) or not all(isinstance(n, str) for n in reset)
        ):
            raise DslError(
                f"{where}.reset: a list of binding names to clear before each pass"
            )

    if op == "behold":
        validate_behold_selector(effect.get("objects"), f"{where}.objects")
        if "optional" in effect and not isinstance(effect["optional"], bool):
            raise DslError(f"{where}: behold's 'optional' is a boolean (the printed 'may')")
        if not effect.get("effects") and not effect.get("else") and "as" not in effect:
            # A behold nothing reads is a reveal for no reason: the card loads,
            # shows a Dragon, and the "if you do" it was written for is gone.
            raise DslError(
                f"{where}: behold needs 'effects' (the 'if you do'), 'else', or an "
                f"'as' something later reads"
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
        if "any_amount" in effect:
            _validate_pay_any_amount(effect, where)
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
        if effect["pay"].get("mana_reduction") is not None:
            # Read: an optional `pay` is charged through `pay`, which prices its
            # mana half with `ability_mana` like any other cost node. Validated
            # here for the same reason an ability's is -- a malformed reduction
            # should be a load error, not a mid-resolution crash.
            _validate_cost_reduction(effect["pay"]["mana_reduction"], f"{where}.pay.mana_reduction")
        if effect["pay"].get("x_value") is not None:
            # `x_value` fills in the `{X}` of an *activated ability's* cost, and
            # an optional `pay` is not one: nothing announces X for it either,
            # so `{"mana": "{X}"}` here is already a cost of nothing. Refused
            # rather than quietly honoured, because no printed "you may pay"
            # names an X the card computes, and a field that works in a place
            # nothing tested it is a price nobody checked.
            raise DslError(
                f"{where}.pay: 'x_value' belongs to an activated ability's cost, "
                f"not to an optional payment"
            )
        x_symbols = ManaCost.parse(effect["pay"].get("mana")).x_count
        if x_symbols and "x" not in effect:
            # Nothing announces an X for an optional payment unless the effect
            # says how, so `{X}` here would charge {0} and run the "if you do"
            # branch for free -- the silent reading of Well of Lost Dreams.
            raise DslError(
                f"{where}.pay: an optional {{X}} payment needs 'x' -- its ceiling "
                f"('max') and the binding the announced X is read back from ('as')"
            )
        if "x" in effect and not x_symbols:
            raise DslError(f"{where}: 'x' announces the {{X}} of 'pay', and its mana has none")
        if "x" in effect:
            _validate_pay_x(effect, where)
        if isinstance(life := effect["pay"].get("pay_life"), dict):
            # "You may pay that much life" -- Niv-Mizzet, Ghost Counsel. A value
            # expression read when the `may` resolves, with the trigger's
            # bindings in hand; validated here so a misspelt expression is a
            # load error rather than a price of 0 and a free "if you do".
            validate_value(life, f"{where}.pay.pay_life")
        if (times := effect["pay"].get("times")) is not None:
            # Cumulative upkeep's multiplier. It scales the *mana* half and
            # nothing else, so a `times` beside a cost with no mana would load
            # and multiply nothing -- a card that reads "for each age counter"
            # and charges a flat price.
            validate_value(times, f"{where}.pay.times")
            if not effect["pay"].get("mana"):
                raise DslError(f"{where}.pay: 'times' multiplies the mana cost, and there is none")
    if "any_amount" in effect and (op != "may" or "pay" not in effect):
        # Every other op ignores the key, so the card would load and pay nothing.
        raise DslError(
            f"{where}: 'any_amount' counts how many times a may's 'pay' is paid, "
            f"and {op!r} has no 'pay' to count"
        )
    if "x" in effect and (op != "may" or "pay" not in effect):
        # `may` without a `pay` has no {X} to announce, and every other op
        # ignores the key -- the card would load and draw 0.
        raise DslError(f"{where}: 'x' announces the {{X}} of a may's 'pay', not of {op!r}")
    if op in ("win_game", "lose_game") and "condition" in effect:
        # "**If you rolled 6 exactly seven times**, you win the game" (Luck
        # Bobblehead). A top-level `condition` is read by `if` and by `may` and
        # by nobody else, so written on this op it is accepted,
        # ignored, and the card wins the game unconditionally -- the single worst
        # silent misread in the whole vocabulary, and the *first* way anybody
        # will try to write the printed sentence, since the condition is where
        # the card's entire cost lives. Wrapped in an `if` it is one more line
        # and it means what it says.
        raise DslError(
            f"{where}: {op} reads no 'condition' -- wrap it in an "
            f"{{'op': 'if', 'condition': …, 'then': [{{'op': {op!r}}}]}}"
        )
    if "from_top" in effect:
        # "…into its owner's library second from the top." The depth is the whole
        # of the difference between Hinder and a plain tuck, and both ways of
        # getting it wrong are silent: written on an op that does not read it the
        # card is a strictly better one than printed (the permanent comes back
        # next turn), and a zero or a negative ordinal is not a position on a
        # library at all -- `put_on_top` clamps it, but a card that says it meant
        # something the engine had to correct is a card that was authored wrong.
        if op != "put_on_top":
            raise DslError(
                f"{where}: 'from_top' is a library depth and only put_on_top reads it, not {op!r}"
            )
        validate_value(effect["from_top"], f"{where}.from_top")
        depth = effect["from_top"]
        if isinstance(depth, Mapping) and "const" in depth:
            depth = depth["const"]
        if isinstance(depth, int) and not isinstance(depth, bool) and depth < 1:
            raise DslError(
                f"{where}.from_top: depth counts from 1 (1 is the top card); got {depth}"
            )
    if "any_order" in effect:
        # "…on the bottom of their library **in any order**" (Teferi's Puzzle
        # Box, 401.4). Only `put_on_top` reads it; on another op it would load
        # and leave the order to the pool, which is the misreading it exists to
        # stop.
        if op != "put_on_top":
            raise DslError(
                f"{where}: 'any_order' arranges cards put into a library, and only "
                f"put_on_top reads it, not {op!r}"
            )
        if not isinstance(effect["any_order"], bool):
            raise DslError(f"{where}: 'any_order' is true or false")
        if effect["any_order"] and "from_top" in effect:
            # An ordinal is one position in the library; several cards arranged
            # "in any order" are a run of positions, and nothing printed says
            # both.
            raise DslError(f"{where}: 'any_order' cannot be combined with 'from_top'")
        if effect["any_order"] and effect.get("owner_chooses"):
            # "Its owner puts it on their choice of the top or bottom" is one
            # card and one question per card; a run arranged together has to
            # go to one end, so the two sentences cannot share an effect.
            raise DslError(f"{where}: 'any_order' cannot be combined with 'owner_chooses'")
    if "cast_free" in effect and op not in ("look_at_top", "exile_until"):
        # "…without paying its mana cost" is free, and every other op that could
        # plausibly be written with it (`exile`, `search_library`, `reveal`)
        # ignores unknown keys -- so the card would load, resolve, and quietly
        # charge full price for a spell the printing gives away.
        raise DslError(
            f"{where}: 'cast_free' is a look_at_top key (or an exile_until one) and "
            f"only it reads the free cast, not {op!r} (see `play_exiled` for a "
            f"free cast from exile)"
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
            raise DslError(f"{where}: cannot search {unknown} (searchable: {list(SEARCHABLE)})")
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
    if "share_subtype" in effect:
        # "…for up to two basic land cards **that share a land type**" (Myriad
        # Landscape). A constraint between the picks, staged inside the search
        # rather than expressed as a selector clause -- so it only means anything
        # on the two ops that do the staging, and only when more than one card is
        # being taken. Written on anything else it would read as a promise the op
        # never keeps, and the card would fetch a Forest and a Swamp.
        if op not in ("search_library", "search_zones"):
            raise DslError(
                f"{where}: 'share_subtype' only applies to search_library and "
                f"search_zones, not {op!r}"
            )
        if not isinstance(effect["share_subtype"], bool):
            raise DslError(
                f"{where}: 'share_subtype' is a boolean, got {effect['share_subtype']!r}"
            )
        count = effect.get("count", 1)
        if isinstance(count, dict) and "const" in count:
            count = count["const"]
        if isinstance(count, int) and not isinstance(count, bool) and count < 2:
            # One card shares a type with itself vacuously, so the clause would
            # be decoration on a card that reads as if it constrained something.
            raise DslError(f"{where}: 'share_subtype' needs a 'count' above 1; got {count}")
    if "distinct_names" in effect:
        # "…for up to five Dragon cards **that each have different names**"
        # (Tiamat). The mirror of `share_subtype` above, and guarded the same
        # way for the same reason: it is staged inside the search, so it means
        # nothing anywhere else, and a card written with it elsewhere would read
        # as a promise the op never keeps and fetch five copies of one Dragon.
        if op not in ("search_library", "search_zones"):
            raise DslError(
                f"{where}: 'distinct_names' only applies to search_library and "
                f"search_zones, not {op!r}"
            )
        if not isinstance(effect["distinct_names"], bool):
            raise DslError(
                f"{where}: 'distinct_names' is a boolean, got {effect['distinct_names']!r}"
            )
        # The two stage the pool differently -- sharing narrows once, against
        # the lead card's subtypes; distinctness narrows after every pick,
        # against the names already taken. Whichever ran would silently drop the
        # other half of the sentence, so a card asking for both is refused
        # rather than given one of them.
        if effect.get("share_subtype"):
            raise DslError(
                f"{where}: 'distinct_names' and 'share_subtype' are two different "
                f"stagings of one search; a card cannot ask for both"
            )
        count = effect.get("count", 1)
        if isinstance(count, dict) and "const" in count:
            count = count["const"]
        if isinstance(count, int) and not isinstance(count, bool) and count < 2:
            # One card differs from nothing, so the clause would be decoration
            # on a card that reads as if it constrained something.
            raise DslError(f"{where}: 'distinct_names' needs a 'count' above 1; got {count}")
    if "attachment" in effect:
        # "…you may attach **it** to a creature you control" (Vault 101:
        # Birthday Party). Which permanent is doing the attaching, as against
        # `objects`, which is the host it lands on. Only `attach` reads it, and
        # this is the one guard that has to exist: written on `put_onto_battle-
        # field` -- the first place anybody will try it, since that is the op
        # that just put the Equipment down -- it is accepted, ignored, and the
        # Equipment arrives equipping nobody. Nothing on screen says so; the
        # card simply grants no bonus.
        if op != "attach":
            raise DslError(
                f"{where}: 'attachment' names the permanent being attached and "
                f"only attach reads it, not {op!r}"
            )
        validate_selector(effect["attachment"], f"{where}.attachment")
        sub = effect["attachment"]
        if isinstance(sub, Mapping) and "target" in sub and str(sub["target"]) not in target_kinds:
            raise DslError(
                f"{where}.attachment: references target {sub['target']!r} "
                f"which the card does not declare"
            )
    if op == "attach" and "player" in effect:
        # "…attach this Aura to **that player**" (Archnemesis). The host is a
        # seat, so `objects` beside it would be a second host (303.4: an Aura
        # is attached to one thing), and the mover is the source Aura whose
        # enchant clause the op checks -- `attachment` would move something
        # whose clause nothing here has seen. A spec naming several seats would
        # need a choice the printed line never offers, and the op would attach
        # to nobody.
        for key in ("objects", "attachment"):
            if key in effect:
                raise DslError(
                    f"{where}: attach with 'player' moves this Aura onto that seat; "
                    f"it takes no {key!r}"
                )
        if effect["player"] in ("opponent", "each_opponent", "each_player", "all"):
            raise DslError(
                f"{where}.player: an Aura is attached to one player, and "
                f"{effect['player']!r} can name several -- name the one seat, "
                f'e.g. {{"binding": "event_player"}}'
            )
    if "new_targets" in effect:
        # "You may choose new targets for the copy" (Jin-Gitaxias). Opt-in on the
        # two copy ops: the choice is a decision per copy, and storm, replicate,
        # conspire and gravestorm all go through `copy_spell` without wanting nine
        # prompts. Written anywhere else it would read as a promise nothing keeps.
        #
        # `copy_ability` carries it for the same printed clause on a different
        # kind of object -- Peter Parker's Camera and Lithoform Engine both say
        # it -- and offers the pool from the **ability's** own specs rather than
        # the card's, which is the whole reason it is a separate op.
        if op not in ("copy_spell", "copy_ability"):
            raise DslError(
                f"{where}: 'new_targets' only applies to copy_spell and "
                f"copy_ability, not {op!r}"
            )
        if not isinstance(effect["new_targets"], bool):
            raise DslError(f"{where}: 'new_targets' is a boolean, got {effect['new_targets']!r}")
    if op == "copy_spell" and "controller" in effect:
        # Demonstrate's "choose an opponent to **also** copy it". A full player
        # spec, so it is checked as one: until the op read this key it loaded
        # clean and was dropped on the floor, which made every copy the
        # resolving player's and turned the half of demonstrate that balances
        # it into no clause at all.
        _validate_player_spec(effect["controller"], f"{where}.controller", target_kinds)
    if op == "choose_card_name":
        # The name exists only as its binding, read by a selector's
        # `{"name": {"binding": …}}` -- without 'as' it is a prompt whose
        # answer is thrown away and the selector matches nothing.
        if not effect.get("as"):
            raise DslError(
                f"{where}: choose_card_name needs an 'as' -- the chosen name is "
                f"only reachable through the binding it is stored under"
            )
        for key in ("types", "not_types"):
            names = effect.get(key)
            if names is None:
                continue
            if not isinstance(names, (list, tuple)) or not names:
                raise DslError(f"{where}: choose_card_name '{key}' takes a list of card types")
            for name in names:
                if name not in KNOWN_TYPES:
                    raise DslError(f"{where}: unknown card type {name!r} in {key!r}")
    if op == "choose_player":
        # The chosen seat exists only as the binding it is written to -- nothing
        # else on the card can reach it -- so an omitted 'as' is a prompt whose
        # answer is thrown away, and two of them sharing a default name would
        # silently overwrite each other on a card that chose twice.
        if not effect.get("as"):
            raise DslError(
                f"{where}: choose_player needs an 'as' -- the chosen player is "
                f"only reachable through the binding it is stored under"
            )
        if "players" in effect:
            _validate_player_spec(effect["players"], f"{where}.players", target_kinds)
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
        # `cast_free` sends what was picked to the **stack**; `destination`,
        # `tapped` and `playable_this_turn` all describe a card arriving in a
        # zone and are read only on the branch `cast_free` replaces. Written
        # together they load clean and one half is silently dropped -- and
        # `playable_this_turn` is the impulse permission, "play it later at its
        # printed cost", which is the opposite card from "cast it now for free".
        if effect.get("cast_free"):
            clashing = [
                key for key in ("destination", "tapped", "playable_this_turn") if key in effect
            ]
            if clashing:
                raise DslError(
                    f"{where}: look_at_top 'cast_free' takes no {sorted(clashing)} -- "
                    f"the picked card goes to the stack, not to a zone"
                )
        # "Exile the top card of your library **face down**." Only exile can be
        # face down: `_move_found` writes the privacy on the way into that zone
        # and reads it nowhere else, so `face_down` beside any other destination
        # loads clean, prints the words and does nothing at all -- which is the
        # failure this whole pass exists to stop. `cast_free` is refused with it
        # for the same reason the three keys above are: it replaces the branch
        # that would honour it.
        # "Put one into your hand, one on the bottom and exile one" (Expressive
        # Iteration); "a creature card and/or a land card" (Kiora, Master of the
        # Depths). A step's `to` is a zone the op can reach, its `selector` a
        # real selector and `up_to` a flag -- misspelt, each loads clean and the
        # step silently takes any card, or insists on one the card says "may".
        for i, step in enumerate(effect.get("destinations") or ()):
            here = f"{where}.destinations[{i}]"
            if not isinstance(step, Mapping):
                raise DslError(f"{here}: each destination is an object")
            unknown = set(step) - LOOK_STEP_KEYS
            if unknown:
                raise DslError(f"{here}: unknown keys {sorted(unknown)}")
            if str(step.get("to", "hand")) not in DESTINATIONS:
                raise DslError(f"{here}: unknown destination {step.get('to')!r}")
            if "up_to" in step and not isinstance(step["up_to"], bool):
                raise DslError(f"{here}: 'up_to' is a boolean")
            if "selector" in step:
                validate_selector(step["selector"], f"{here}.selector")
        # "…it enters with three additional +1/+1 counters on it" (Turntimber
        # Symbiosis). Read only on a battlefield arrival, so beside any other
        # destination -- or `cast_free`, which replaces the arrival with a cast
        # -- the counters would load and never be put anywhere. A `counters_if`
        # with no counters is a condition guarding nothing.
        if "counters" in effect:
            counters = effect["counters"]
            if (
                not isinstance(counters, Mapping)
                or not counters
                or not all(
                    isinstance(n, int) and not isinstance(n, bool) and n > 0
                    for n in counters.values()
                )
            ):
                raise DslError(
                    f"{where}: look_at_top 'counters' maps a counter kind to a "
                    f"positive amount, e.g. {{'+1/+1': 3}}"
                )
            if destination != "battlefield" or effect.get("cast_free"):
                raise DslError(
                    f"{where}: look_at_top 'counters' are what a card enters the "
                    f"battlefield with and need destination 'battlefield'; got "
                    f"{'cast_free' if effect.get('cast_free') else repr(destination)}"
                )
        if "counters_if" in effect:
            if "counters" not in effect:
                raise DslError(f"{where}: look_at_top 'counters_if' guards nothing without 'counters'")
            validate_selector(effect["counters_if"], f"{where}.counters_if")
        if effect.get("face_down") and (destination != "exile" or effect.get("cast_free")):
            raise DslError(
                f"{where}: look_at_top 'face_down' needs destination 'exile' "
                f"(a card is only face down in exile); got {destination!r}"
            )
        # `link` records "exiled with <this>"; anywhere but exile it would load
        # and link nothing -- a later "exiled with" selector finding no cards.
        if "link" in effect and (
            not isinstance(effect["link"], bool) or (effect["link"] and destination != "exile")
        ):
            raise DslError(
                f"{where}: look_at_top 'link' is a boolean and needs destination 'exile'"
            )
    if op == "reveal_until":
        # The selector *is* the "until", so an omitted one is not a smaller
        # version of the card -- an empty selector matches the very first card
        # revealed, and "reveal until you reveal a creature card that shares a
        # type" would quietly become "put the top card into your hand".
        selector = effect.get("objects") or effect.get("selector")
        if not isinstance(selector, Mapping) or not selector:
            raise DslError(
                f"{where}: reveal_until needs a non-empty 'objects' -- "
                f"the selector is the card it stops at"
            )
        # `amount` is how many *matches* end the scan ("until you reveal that
        # many creature cards"), validated as a value with every other
        # `amount`; the depth stays the library's.
        # "Shuffle the rest into your library" and "put the rest on the bottom
        # in a random order" are two different actions, and a card prints one.
        if "shuffle_rest" in effect:
            if not isinstance(effect["shuffle_rest"], bool):
                raise DslError(f"{where}: reveal_until 'shuffle_rest' is a boolean")
            if effect["shuffle_rest"] and effect.get("rest_to_bottom"):
                raise DslError(
                    f"{where}: reveal_until 'shuffle_rest' and 'rest_to_bottom' are "
                    f"two dispositions of the rest; a card prints one"
                )
        destination = str(effect.get("destination", "hand"))
        if destination not in DESTINATIONS:
            raise DslError(
                f"{where}: unknown reveal_until destination {destination!r} "
                f"(implemented: {sorted(DESTINATIONS)})"
            )
        # "You may put that card onto the battlefield. If you don't, put it
        # into your hand." The may is the battlefield and the fallback is
        # `destination`; a may to where the card would go anyway asks nothing,
        # and "that card" is one card, so an `amount` would ask about a group
        # the sentence never names.
        may_destination = effect.get("may_destination")
        if "may_destination" in effect:
            if may_destination not in REVEAL_UNTIL_MAY_DESTINATIONS:
                raise DslError(
                    f"{where}: unknown reveal_until may_destination {may_destination!r} "
                    f"(implemented: {sorted(REVEAL_UNTIL_MAY_DESTINATIONS)})"
                )
            if destination == may_destination:
                raise DslError(
                    f"{where}: reveal_until 'may_destination' needs a 'destination' "
                    f"other than {may_destination!r} -- the fallback if you don't"
                )
            if "amount" in effect:
                raise DslError(
                    f"{where}: reveal_until 'may_destination' asks about one card "
                    f"and takes no 'amount'"
                )
        arrival = may_destination or destination
        # "Put that card onto the battlefield tapped." Anywhere else a card is
        # never tapped, so the key would load and say nothing.
        if "tapped" in effect and (
            not isinstance(effect["tapped"], bool) or arrival != "battlefield"
        ):
            raise DslError(
                f"{where}: reveal_until 'tapped' is a boolean and needs "
                f"destination or may_destination 'battlefield'"
            )
        # "You put that card onto the battlefield **under your control**."
        # The only value is "you": every other seat a match could enter under is
        # the scanned library's, which is the default. Anywhere but the
        # battlefield a card has no controller to set, so the key would say
        # nothing.
        if "controller" in effect and (
            effect["controller"] != "you" or arrival != "battlefield"
        ):
            raise DslError(
                f"{where}: reveal_until 'controller' is \"you\" and needs "
                f"destination or may_destination 'battlefield'"
            )
    # Same argument as look_at_top, and the printed keyword is *named* for the
    # number -- "hideaway 4". Defaulted it would look at one card, and the
    # ability that later plays it would still work, so nothing downstream would
    # ever complain.
    if op == "hideaway" and "amount" not in effect:
        raise DslError(f"{where}: hideaway needs an 'amount' -- hideaway N")
    # "Discover N" is named for its number too, and here an omitted one is
    # worse than hideaway's: evaluated as 0 it stops only at a mana-value-0
    # nonland card, so most scans would exile the whole library and find nothing.
    if op == "discover" and "amount" not in effect:
        raise DslError(f"{where}: discover needs an 'amount' -- discover N")
    if op == "exile_until":
        # reveal_until's argument: the selector is the "until", and an empty
        # one stops at the first card exiled.
        selector = effect.get("objects")
        if not isinstance(selector, Mapping) or not selector:
            raise DslError(
                f"{where}: exile_until needs a non-empty 'objects' -- "
                f"the selector is the card it stops at"
            )
        if "amount" in effect:
            raise DslError(
                f"{where}: exile_until takes no 'amount' -- the scan is unbounded"
            )
        # A condition on a cast nobody offers would load and gate nothing.
        if "cast_free_if" in effect:
            if not effect.get("cast_free"):
                raise DslError(f"{where}: exile_until 'cast_free_if' needs 'cast_free'")
            validate_selector(effect["cast_free_if"], f"{where}.cast_free_if")
        if "else_destination" in effect:
            if not effect.get("cast_free"):
                # Without a cast every hit would take the "else" -- that is a
                # plain destination, and no printed card says it this way.
                raise DslError(f"{where}: exile_until 'else_destination' needs 'cast_free'")
            if effect["else_destination"] not in EXILE_UNTIL_ELSE_DESTINATIONS:
                raise DslError(
                    f"{where}: unknown exile_until else_destination "
                    f"{effect['else_destination']!r} "
                    f"(implemented: {sorted(EXILE_UNTIL_ELSE_DESTINATIONS)})"
                )
    if op == "suspend":
        # Both are the card: which card is suspended, and for how many upkeeps.
        # An omitted count would evaluate to zero and suspend nothing, and an
        # omitted selector would exile nothing -- a trigger that loads and does
        # nothing, with no test of its own to notice. `amount` rather than
        # `counters`, which is the kind-keyed map a permanent arrives with.
        if not effect.get("objects"):
            raise DslError(f"{where}: suspend needs 'objects' -- the card to suspend")
        if "amount" not in effect:
            raise DslError(
                f"{where}: suspend needs an 'amount' -- \"with N time counters on it\""
            )
    if op == "cant_attack_player":
        # All three keys are required, and each omission is silent in its own
        # way. Without `attacker`/`defender` the spec defaults to the controller
        # on both sides, which `restrict_attack` refuses as a self-restriction --
        # the card would load, resolve, log nothing and prohibit nothing. And the
        # two durations are not a long and a short version of one restriction:
        # `this_turn` read for `this_combat` blanks the extra combat a Relentless
        # Assault bought, `this_combat` read for `this_turn` gives it away free.
        # `objects` is the creature-scoped form ("each of those creatures
        # can't attack you ... for as long as it has a vow counter on it"),
        # and it replaces `attacker` rather than narrowing it: a line naming
        # both would say two different things about who is stopped.
        if "objects" in effect:
            if "attacker" in effect:
                raise DslError(
                    f"{where}: cant_attack_player takes 'objects' (the creatures "
                    f"stopped) or 'attacker' (the player stopped), not both"
                )
            if not effect.get("objects"):
                raise DslError(f"{where}: cant_attack_player 'objects' names no creatures")
            if "defender" not in effect:
                raise DslError(
                    f"{where}: cant_attack_player needs 'defender' -- the player "
                    f"those creatures may not attack"
                )
            _validate_player_spec(effect["defender"], f"{where}.defender", target_kinds)
            # The one clock the creature form has. A creature-scoped line on a
            # turn clock is a different sentence nobody has printed yet, and
            # guessing its storage would be a card nobody can check.
            if effect.get("duration") != "while_counter":
                raise DslError(
                    f"{where}: cant_attack_player with 'objects' needs "
                    f"'duration': 'while_counter' (\"for as long as it has a "
                    f"<kind> counter on it\"), not {effect.get('duration')!r}"
                )
            counter = effect.get("counter")
            if not isinstance(counter, str) or not counter:
                raise DslError(
                    f"{where}: cant_attack_player 'while_counter' needs 'counter' "
                    f"naming the counter kind"
                )
            if "planeswalkers_matching" in effect:
                raise DslError(
                    f"{where}: cant_attack_player with 'objects' takes "
                    f"'planeswalkers' but not 'planeswalkers_matching'"
                )
            if "planeswalkers" in effect and not isinstance(effect["planeswalkers"], bool):
                raise DslError(f"{where}.planeswalkers: must be true or false")
        elif "counter" in effect or effect.get("duration") == "while_counter":
            raise DslError(
                f"{where}: cant_attack_player's 'while_counter' clock is a fact "
                f"about creatures; name them in 'objects'"
            )
        else:
            for side in ("attacker", "defender"):
                if side not in effect:
                    raise DslError(
                        f"{where}: cant_attack_player needs '{side}' -- "
                        f"the restriction names both players"
                    )
                _validate_player_spec(effect[side], f"{where}.{side}", target_kinds)
            if "duration" not in effect:
                raise DslError(
                    f"{where}: cant_attack_player needs a 'duration' "
                    f"(implemented: {list(ATTACK_RESTRICTION_DURATIONS)})"
                )
            if str(effect["duration"]) not in ATTACK_RESTRICTION_DURATIONS:
                raise DslError(
                    f"{where}: unknown cant_attack_player duration {effect['duration']!r} "
                    f"(implemented: {sorted(ATTACK_RESTRICTION_DURATIONS)})"
                )
            # `planeswalkers` decides whether the prohibition reaches 506.2's third
            # attack target, and it is checked for the reason `no_monarch` and
            # `was_cast` are: `"false"` is a non-empty string and would read as
            # `true`, turning "you can't attack that player" into a line strictly
            # stronger than the printing -- invisibly, since no board shows a
            # prohibition that was never tested.
            if "planeswalkers" in effect and not isinstance(effect["planeswalkers"], bool):
                raise DslError(
                    f"{where}.planeswalkers: must be true or false -- true is for the "
                    f"sentence naming no defender at all ('creatures can't attack this "
                    f"combat'), false for every line that names a seat (506.2)"
                )
            # `planeswalkers_matching` keeps the seat open and closes only the
            # defender's walkers of the named subtypes ("can't attack Jaces you
            # control"). Each refusal below is a card that would load as a different
            # one: beside `planeswalkers: true` it would close the seat it promises
            # to leave open; an empty or unknown filter would close nothing (or, read
            # loosely, everything); and a creature subtype names no planeswalker, so
            # the line would prohibit nothing.
            if "planeswalkers_matching" in effect:
                matching = effect["planeswalkers_matching"]
                subtypes = matching.get("subtypes") if isinstance(matching, dict) else None
                if (
                    not isinstance(matching, dict)
                    or set(matching) != {"subtypes"}
                    or not isinstance(subtypes, list)
                    or not subtypes
                    or not all(isinstance(t, str) for t in subtypes)
                ):
                    raise DslError(
                        f"{where}.planeswalkers_matching: must be {{'subtypes': [...]}} "
                        f"naming at least one planeswalker subtype"
                    )
                for sub in subtypes:
                    if SUBTYPE_CLASS.get(sub) != "Planeswalker":
                        raise DslError(
                            f"{where}.planeswalkers_matching: {sub!r} is not a "
                            f"planeswalker subtype"
                        )
                if effect.get("planeswalkers") is True:
                    raise DslError(
                        f"{where}: cant_attack_player takes 'planeswalkers_matching' or "
                        f"'planeswalkers: true', not both -- one closes only some walkers "
                        f"and leaves the seat open, the other closes the seat and every walker"
                    )
    if op == "goad":
        # A goad with no selector goads nobody: the spell resolves, the log says
        # nothing, and every creature attacks exactly as it pleases. Detain's
        # guard, for detain's reason.
        if not effect.get("objects"):
            raise DslError(f"{where}: goad needs 'objects' naming the creatures goaded")
        # One `duration` only, and its absence is the default rather than an
        # omission: 701.38a's clock ("until your next turn") is keyed to the
        # goading *player*, not to a turn number. The one other printed clock is
        # "for the rest of the game" (Dack Fayden, Helping Hand), `permanent`.
        # Accepting any other duration would invite `this_turn` -- which is
        # `must_attack`, a strictly weaker card that looks identical in a
        # one-turn test.
        if "duration" in effect and effect["duration"] != "permanent":
            raise DslError(
                f"{where}: goad takes no 'duration' but 'permanent' (\"for the rest "
                f"of the game\") -- otherwise it lasts until the goading player's "
                f"next turn (701.38a), which is a player and not a number. "
                f"Use must_attack for a one-combat requirement"
            )
        # The goader defaults to the effect's controller, which is every printed
        # goad; when a card does spell it out it must be a player the engine can
        # resolve -- which the general `player` check above now does for every
        # op, goad included.
    if op == "must_attack_player":
        # All three are the card. Without `objects` nobody is compelled;
        # without `defender` there is no "that player" to attack, and guessing
        # one (the controller, every opponent) compels a seat the printed line
        # never named; and the clock is required for `cant_attack_player`'s
        # reason -- a requirement with a guessed lifetime is a different card.
        if not effect.get("objects"):
            raise DslError(
                f"{where}: must_attack_player needs 'objects' naming the creatures "
                f"that must attack"
            )
        if effect.get("defender") is None:
            raise DslError(
                f"{where}: must_attack_player needs 'defender' -- the player they "
                f"must attack ({{\"binding\": \"defender\"}} for 'that player')"
            )
        _validate_player_spec(effect["defender"], f"{where}.defender", target_kinds)
        if str(effect.get("duration", "")) not in ATTACK_MARK_DURATIONS:
            raise DslError(
                f"{where}: must_attack_player needs a 'duration' "
                f"(implemented: {list(ATTACK_MARK_DURATIONS)}), not "
                f"{effect.get('duration')!r}"
            )
    if op == "must_attack_planeswalker":
        # Both required. Without `objects` there is no walker to attack and the
        # line does nothing; without `player`, defaulting to anybody would
        # compel the wrong seat, and defaulting to the controller is a sentence
        # that cannot bite (you cannot attack your own planeswalker).
        if not effect.get("objects"):
            raise DslError(
                f"{where}: must_attack_planeswalker needs 'objects' naming the "
                f"planeswalker to be attacked ({{\"self_only\": true}} for Gideon Jura)"
            )
        if effect.get("player") is None:
            raise DslError(
                f"{where}: must_attack_planeswalker needs 'player' -- whose "
                f"creatures must attack, during that player's next turn"
            )
        if "duration" in effect:
            raise DslError(
                f"{where}: must_attack_planeswalker takes no 'duration' -- it is "
                f"always the named player's next turn"
            )
    if op == "cant_block":
        # Two keys, and every way of getting them wrong loads cleanly and plays
        # a different card.
        #
        # Exactly one of `objects` and `all_creatures`, because the two are not
        # a general and a special case: a `cant_block` with neither would have
        # to guess, and both guesses are bad -- "nobody" makes the ability do
        # nothing, "everybody" turns Aragorn's *targeted* half into a one-sided
        # Falter. Both together is a card that says two things at once.
        #
        # And the duration is required for the reason `cant_attack_player`'s is:
        # `this_turn` read for `until_your_next_turn` gives the blockers back a
        # turn early, and the reverse keeps them away for a whole turn cycle.
        has_objects = "objects" in effect
        has_all = bool(effect.get("all_creatures"))
        if has_objects == has_all:
            raise DslError(
                f"{where}: cant_block needs exactly one of 'objects' "
                f"(the creatures chosen when it resolves) and 'all_creatures': true "
                f"(every creature, including ones that enter later)"
            )
        if "duration" not in effect:
            raise DslError(
                f"{where}: cant_block needs a 'duration' "
                f"(implemented: {sorted(BLOCK_PROHIBITION_DURATIONS)})"
            )
        if str(effect["duration"]) not in BLOCK_PROHIBITION_DURATIONS:
            raise DslError(
                f"{where}: unknown cant_block duration {effect['duration']!r} "
                f"(implemented: {sorted(BLOCK_PROHIBITION_DURATIONS)})"
            )
    if op == "unblockable":
        # `objects` is required and there is no wildcard shorthand, which is the
        # one difference from `cant_block` above. Defaulting an absent `objects`
        # to "every creature" there would be a one-sided Falter; here it would be
        # a one-sided *unblockable board*, which is worse, and no printed card
        # says it -- so the omission is a mistake and is refused as one.
        if not effect.get("objects"):
            raise DslError(
                f"{where}: unblockable needs 'objects' (the creatures that "
                f"can't be blocked, chosen when it resolves)"
            )
        # And the duration is required for the reason `cant_block`'s is: an
        # evasion read a turn long when it was a turn cycle, or the reverse, is a
        # different card both ways round.
        if "duration" not in effect:
            raise DslError(
                f"{where}: unblockable needs a 'duration' "
                f"(implemented: {sorted(UNBLOCKABLE_DURATIONS)})"
            )
        if str(effect["duration"]) not in UNBLOCKABLE_DURATIONS:
            raise DslError(
                f"{where}: unknown unblockable duration {effect['duration']!r} "
                f"(implemented: {sorted(UNBLOCKABLE_DURATIONS)})"
            )
        # "…except by creatures with haste": a filter on the *blocker*, matched
        # by `combat.unblockable` the way `block_restriction`'s `blockers` is,
        # so it speaks that static filter language and no other. An empty one
        # would exempt every blocker -- a line that does nothing -- and a key
        # the static matcher does not read would be ignored, exempting blockers
        # the printed line does not; both are refused rather than loaded.
        if "except_blockers" in effect:
            exempt = effect["except_blockers"]
            if not isinstance(exempt, Mapping) or not exempt:
                raise DslError(
                    f"{where}: unblockable 'except_blockers' is a non-empty static "
                    f"filter on the blocker, got {exempt!r}"
                )
            # "…except by artifact creatures and/or red creatures" is a union,
            # `any_of`, whose branches are checked as the filter itself is.
            branches = exempt.get("any_of")
            if branches is not None and (
                not isinstance(branches, list)
                or not branches
                or not all(isinstance(b, Mapping) and b for b in branches)
            ):
                raise DslError(
                    f"{where}: unblockable 'except_blockers.any_of' is a non-empty "
                    f"list of non-empty filters, got {branches!r}"
                )
            parts = [{k: v for k, v in exempt.items() if k != "any_of"}, *(branches or [])]
            for part in parts:
                unknown = set(part) - STATIC_FILTER_KEYS
                if unknown:
                    raise DslError(
                        f"{where}: unblockable 'except_blockers' may only use static "
                        f"filter keys; unsupported keys {sorted(unknown)}"
                    )
                refused = {"self_only", "exclude_self", "controller", "owner"} & set(part)
                if refused:
                    raise DslError(
                        f"{where}: unblockable 'except_blockers' describes what the "
                        f"blocker is, not whose it is; drop {sorted(refused)}"
                    )
    if op == "cant_sacrifice":
        # `objects` is required and there is no wildcard shorthand, for the
        # reason `unblockable`'s is and harder: an absent `objects` read as
        # "every permanent" would be a one-sided Sigarda for the turn, and read
        # as "nothing" would be a card that silently does not protect what it
        # says it protects. Both readings are wrong, so the omission is a
        # mistake and is refused as one.
        if not effect.get("objects"):
            raise DslError(
                f"{where}: cant_sacrifice needs 'objects' (the permanents that "
                f"can't be sacrificed, chosen when it resolves)"
            )
        # And the duration is required for the reason the three above it are.
        # A longer word read as a shorter one, or the reverse, is a different
        # card, so the implemented words are enumerated in
        # `CANT_SACRIFICE_DURATIONS` rather than defaulted to here.
        if "duration" not in effect:
            raise DslError(
                f"{where}: cant_sacrifice needs a 'duration' "
                f"(implemented: {sorted(CANT_SACRIFICE_DURATIONS)})"
            )
        if str(effect["duration"]) not in CANT_SACRIFICE_DURATIONS:
            raise DslError(
                f"{where}: unknown cant_sacrifice duration {effect['duration']!r} "
                f"(implemented: {sorted(CANT_SACRIFICE_DURATIONS)})"
            )
    if op == "prevent_damage":
        # The op, not the `static_effects` entry of the same name. That one is
        # absorb N and is guarded further up (line ~1183, "'prevent_damage' needs
        # an 'amount'"); this one is the player shield and refuses the very key
        # that one requires, which is the whole distinction between them.
        #
        # `amount` is refused rather than read, and this is the guard that
        # matters. The shield prevents *all* damage for the turn; a card written
        # `{"op": "prevent_damage", "amount": 3}` for Healing Salve would load
        # clean and prevent everything -- a strictly better card, silently, and
        # the exact failure this whole validation pass exists to catch. Absorb-N
        # over a player has a pool that drains and a target that may be a
        # creature instead, so it is a different effect and not a parameter of
        # this one; see `docs/rules-coverage.md`.
        if "amount" in effect:
            raise DslError(
                f"{where}: the 'prevent_damage' op prevents ALL damage to a player "
                f"for the turn and takes no 'amount' -- absorb N is the "
                f"'prevent_damage' *static effect* (a permanent or a seat), and "
                f'"prevent the next N damage" over a player is not implemented'
            )
        # Required for the reason `cant_block`'s is: a prevention read as lasting
        # longer than it does is a fog that never ends, and there is no safe
        # guess for an omitted one.
        if "duration" not in effect:
            raise DslError(
                f"{where}: prevent_damage needs a 'duration' "
                f"(implemented: {sorted(DAMAGE_SHIELD_DURATIONS)})"
            )
        if str(effect["duration"]) not in DAMAGE_SHIELD_DURATIONS:
            raise DslError(
                f"{where}: unknown prevent_damage duration {effect['duration']!r} "
                f"(implemented: {sorted(DAMAGE_SHIELD_DURATIONS)})"
            )
        # `objects` would look like "prevent all damage that would be dealt to
        # the creatures you control", which this op does not do -- the shield is
        # keyed to a seat. Accepted and ignored it would be a card that shields
        # nothing it claims to.
        if "objects" in effect:
            raise DslError(
                f"{where}: prevent_damage shields a *player* and takes no 'objects' "
                f"-- a one-shot prevention over permanents is the "
                f"'prevent_damage_permanent' op, and a continuous one the "
                f"'prevent_damage' static effect or 'protection'"
            )
    if op == "prevent_damage" and "effects" in effect:
        # "If damage is prevented this way…" (615.5): the rider the op installs
        # as a delayed ability beside its shield. An empty list is a rider that
        # does nothing, and a `target` inside one names nothing when it fires --
        # the delayed half resolves with no targets of its own, as `delay`'s does.
        if not isinstance(effect["effects"], list) or not effect["effects"]:
            raise DslError(
                f"{where}: prevent_damage's 'effects' is the non-empty list of "
                f"effects run each time this shield prevents damage"
            )
        _refuse_targets_inside_a_delay(effect["effects"], f"{where}.effects")
    if op == "prevent_damage_permanent" and "effects" in effect:
        # Accepted, it would be validated and never run: the rider is linked to
        # the player shield only.
        raise DslError(
            f"{where}: a 'prevented this way' rider ('effects') is implemented on "
            f"the 'prevent_damage' player shield only, not on {op!r}"
        )
    if op in ("prevent_damage", "prevent_damage_permanent") and not isinstance(
        effect.get("combat_only", False), bool
    ):
        # "Prevent all combat damage..." is a yes or no. A string "false" would
        # be truthy at resolution and narrow a shield the card meant to be total.
        raise DslError(
            f"{where}: {op}'s 'combat_only' is true or false "
            f"(got {effect.get('combat_only')!r})"
        )
    if op == "prevent_damage_permanent":
        # All three keys required, and every omission loads clean and plays a
        # different card: no `objects` shields nothing, a guessed `dealt` swaps a
        # fog for a pacifism, and a guessed `duration` is a prevention lasting a
        # turn cycle when the card said a turn (or the reverse).
        if not effect.get("objects"):
            raise DslError(
                f"{where}: prevent_damage_permanent needs 'objects' (the permanents "
                f"shielded, chosen when it resolves -- {{\"self_only\": true}} for "
                f"'him', {{\"target\": \"t1\"}} for 'target permanent')"
            )
        if str(effect.get("dealt")) not in PERMANENT_SHIELD_DIRECTIONS:
            raise DslError(
                f"{where}: prevent_damage_permanent needs 'dealt' -- 'to' for "
                f"damage that would be dealt to it, 'by' for damage it would deal, "
                f"'to_and_by' for both (got {effect.get('dealt')!r})"
            )
        if str(effect.get("duration")) not in PERMANENT_SHIELD_DURATIONS:
            raise DslError(
                f"{where}: prevent_damage_permanent needs a 'duration' "
                f"(implemented: {sorted(PERMANENT_SHIELD_DURATIONS)}; "
                f"got {effect.get('duration')!r})"
            )
        if "amount" in effect:
            raise DslError(
                f"{where}: prevent_damage_permanent prevents ALL the damage and "
                f"takes no 'amount'"
            )
    if op == "prevent_combat_damage":
        if str(effect.get("duration")) not in COMBAT_FOG_DURATIONS:
            raise DslError(
                f"{where}: prevent_combat_damage needs a 'duration' "
                f"(implemented: {sorted(COMBAT_FOG_DURATIONS)}; got {effect.get('duration')!r})"
            )
        if "amount" in effect:
            raise DslError(
                f"{where}: prevent_combat_damage prevents ALL of it and takes no 'amount'"
            )
        by = effect.get("by")
        if by is not None:
            # A selector over the creature dealing the damage, asked as the
            # damage would be dealt -- so about the battlefield, with no target,
            # binding or count, none of which exists at that moment.
            if not isinstance(by, Mapping) or not by:
                raise DslError(f"{where}.by: a non-empty filter over the damage's source")
            validate_selector(by, f"{where}.by")
            asked_now = {"target", "binding", "count", "zone", "optional", "as"} & set(by)
            if asked_now:
                raise DslError(
                    f"{where}.by: names the creature dealing the damage when it is "
                    f"dealt; {sorted(asked_now)} mean nothing there"
                )
    if op == "redirect_damage":
        # Every omission loads clean and plays another card: no `to` sends the
        # damage nowhere, a guessed duration outlives the turn, and with neither
        # `player` nor `permanents` the spell redirects nothing at all.
        if str(effect.get("duration")) not in DAMAGE_REDIRECT_DURATIONS:
            raise DslError(
                f"{where}: redirect_damage needs a 'duration' "
                f"(implemented: {sorted(DAMAGE_REDIRECT_DURATIONS)}; got {effect.get('duration')!r})"
            )
        to = effect.get("to")
        if not isinstance(to, Mapping) or not to:
            raise DslError(
                f"{where}: redirect_damage needs 'to', the permanent that is dealt "
                f"the damage instead ({{\"target\": \"t1\"}} for 'the chosen creature')"
            )
        validate_selector(to, f"{where}.to")
        if "target" in to and str(to["target"]) not in target_kinds:
            raise DslError(
                f"{where}.to: references target {to['target']!r} which the card does not declare"
            )
        if "player" not in effect and "permanents" not in effect:
            raise DslError(
                f"{where}: redirect_damage needs 'player', 'permanents' or both "
                f"-- whose damage is dealt to 'to' instead"
            )
        permanents = effect.get("permanents")
        if permanents is not None:
            # Asked as the damage would be dealt, `prevent_combat_damage.by`'s
            # reading, so the same keys mean nothing there.
            if not isinstance(permanents, Mapping) or not permanents:
                raise DslError(f"{where}.permanents: a non-empty filter over the damaged permanent")
            validate_selector(permanents, f"{where}.permanents")
            asked_now = {"target", "binding", "count", "zone", "optional", "as"} & set(permanents)
            if asked_now:
                raise DslError(
                    f"{where}.permanents: names the permanent being dealt damage "
                    f"when it is dealt; {sorted(asked_now)} mean nothing there"
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
    if (
        op == "exile"
        and (effect.get("until_leaves") or effect.get("link"))
        and "objects" not in effect
    ):
        key = "until_leaves" if effect.get("until_leaves") else "link"
        raise DslError(f"{where}: {key!r} needs 'objects' -- there is nothing to link")
    # The phasing twin of the link above, and the same silent failure: the link
    # is written on the permanent that phased out, so with nothing selected
    # there is nothing to write it on and the "until this leaves" clause is
    # dropped -- leaving a card that phases a creature out for one turn.
    if (
        op == "phase_out"
        and (effect.get("until_leaves") or effect.get("link"))
        and "objects" not in effect
    ):
        key = "until_leaves" if effect.get("until_leaves") else "link"
        raise DslError(f"{where}: {key!r} needs 'objects' -- there is nothing to link")
    # Same shape as the link above: the permission is written on the exiled
    # card, so with nothing selected there is no card to write it on and the
    # key is silently doing nothing.
    # The state is a casting permission, so a permanent given it with no spell
    # to cast is a printed line that does nothing at all.
    if op == "become_prepared" and "objects" not in effect:
        raise DslError(f"{where}: 'become_prepared' needs 'objects' -- there is nothing to prepare")
    # Which face it comes back as. Defaulted to "turn it over" the op reads
    # correctly on a card's front and silently wrongly on its back, where the
    # same sentence turns it the other way -- and both faces of the Dominant
    # cycle print one.
    if op == "exile_and_return":
        if "objects" not in effect:
            raise DslError(
                f"{where}: 'exile_and_return' needs 'objects' -- there is nothing to exile"
            )
        face = effect.get("face")
        if face not in ("front", "back"):
            raise DslError(
                f"{where}: 'exile_and_return' needs a 'face' of 'front' or 'back' (got {face!r})"
            )
    # The op reads each card's recorded origin and moves it; with nothing
    # selected it is a return that returns nothing.
    if op == "return_to_origin" and "objects" not in effect:
        raise DslError(f"{where}: 'return_to_origin' needs 'objects' -- there is nothing to return")
    # Same argument, and one degree more dangerous: `choose_objects` over an
    # omitted selector resolves to nothing, so the op is a *silent* no-op --
    # Hellkite Courser's delayed return would fire, move no permanent, and leave
    # a commander on the battlefield for ever with nothing to say so. The
    # printed line always names what comes back ("return **it**"), so the key is
    # required rather than defaulted.
    if op == "return_to_command_zone" and "objects" not in effect:
        raise DslError(
            f"{where}: 'return_to_command_zone' needs 'objects' -- there is nothing to return"
        )
    # "When you do" has to say which do. Without the key the op names the empty
    # id, no ability matches it, and the second half of the card never happens.
    if op == "reflexive_trigger" and not effect.get("ability"):
        raise DslError(
            f"{where}: 'reflexive_trigger' needs an 'ability' -- "
            f"the id of the reflexive ability it fires"
        )
    # `grant_playable` writes the permission on the cards it selects and does
    # nothing else, so with no selection it is a line that reads as a grant and
    # grants nothing.
    if op == "grant_playable" and "objects" not in effect:
        raise DslError(
            f"{where}: 'grant_playable' needs 'objects' -- there is nothing to grant permission on"
        )
    if op == "exile" and effect.get("playable_this_turn") and "objects" not in effect:
        raise DslError(
            f"{where}: 'playable_this_turn' needs 'objects' -- "
            f"there is nothing to grant permission on"
        )
    if "any_color" in effect:
        # "…you may spend mana as though it were mana of any color to cast it"
        # is a rider on a "you may play it" permission and means nothing
        # without one: written on a bare exile it would load, print its
        # sentence and relax nothing. And it is a narrower sentence than
        # `any_type` (``{C}`` still wants colourless mana), so the two together
        # say two different things about one spell.
        grants = op == "grant_playable" or (
            op in ("exile", "look_at_top")
            and ("playable" in effect or effect.get("playable_this_turn"))
        )
        if not grants:
            raise DslError(
                f"{where}: 'any_color' relaxes the cast a 'playable' permission "
                f"grants, so it needs one (exile / look_at_top with 'playable', "
                f"or grant_playable)"
            )
        if effect.get("any_type"):
            raise DslError(
                f"{where}: 'any_color' and 'any_type' are different printed "
                f"sentences -- write the one the card says"
            )
    if "any_type" in effect and op != "add_mana":
        # "Mana of any type can be spent to cast a spell this way" (Klaw,
        # Master of Sound; 609.4b) is a rider on a "you may play it" permission,
        # as `any_color` is, and broader than it: "any type" names colourless
        # too, so coloured mana pays ``{C}``. On a bare exile it would load,
        # print its sentence and relax nothing. `add_mana`'s key of the same
        # name is a different sentence about what a land produces.
        grants = op == "grant_playable" or (
            op in ("exile", "look_at_top")
            and ("playable" in effect or effect.get("playable_this_turn"))
        )
        if not grants:
            raise DslError(
                f"{where}: 'any_type' relaxes the cast a 'playable' permission "
                f"grants, so it needs one (exile / look_at_top with 'playable', "
                f"or grant_playable)"
            )
        if effect["any_type"] is not True:
            raise DslError(f"{where}.any_type: the only value is true")
    if "playable_free" in effect:
        # "You may play them **without paying their mana costs**" is a rider on
        # a "you may play it" permission, as `any_color` is: on a bare exile it
        # would load, print its sentence and make nothing free.
        grants = op == "grant_playable" or (
            op in ("exile", "look_at_top")
            and ("playable" in effect or effect.get("playable_this_turn"))
        )
        if not grants:
            raise DslError(
                f"{where}: 'playable_free' prices the cast a 'playable' permission "
                f"grants, so it needs one (exile / look_at_top with 'playable', "
                f"or grant_playable)"
            )
        if effect.get("any_color") or effect.get("any_type"):
            # Nothing is paid, so a relaxation of what may be spent is a
            # sentence no card prints beside this one.
            raise DslError(
                f"{where}: 'playable_free' leaves no mana to spend, so "
                f"'any_color'/'any_type' beside it relaxes nothing"
            )
    if "playable" in effect or "playable_this_turn" in effect:
        # Two spellings of one key: `playable_this_turn: true` is what every
        # card written before durations existed says, and `playable:
        # "<duration>"` is the general form. Written together they would need a
        # precedence rule nobody can read off the card, so they are refused
        # together instead.
        if "playable" in effect and "playable_this_turn" in effect:
            raise DslError(
                f"{where}: 'playable' and 'playable_this_turn' are two spellings of "
                f"one key -- write 'playable': \"this_turn\" or the boolean, not both"
            )
        if op not in ("exile", "look_at_top", "grant_playable"):
            raise DslError(
                f"{where}: {op!r} grants no 'you may play it' permission, so "
                f"'playable' means nothing on it"
            )
        if (duration := effect.get("playable")) is not None and duration not in PLAYABLE_DURATIONS:
            # A typo here would fall through `playable_duration_of` as None and
            # grant no permission at all -- a card that says "you may play it"
            # and does not, silently. The same reason the mana restriction's
            # entry guard exists.
            raise DslError(
                f"{where}: unknown 'playable' duration {duration!r} "
                f"(implemented: {sorted(PLAYABLE_DURATIONS)})"
            )
        if duration in ("while_exiled", "until_next_exile_by_source"):
            # "For as long as they remain exiled" ends when the card leaves
            # exile, which is the zone-change reset -- so it is only the printed
            # duration on a card that is *in* exile. On a graveyard or a hand
            # card the same reset would read "for as long as it remains
            # there", which is a different sentence and a silent one.
            # "Until you exile another card with this creature" is a card the
            # creature exiled, so the same zone-change reset is its other end.
            objects = effect.get("objects")
            in_exile = (
                op == "exile"
                or (op == "look_at_top" and effect.get("destination") == "exile")
                or (
                    op == "grant_playable"
                    and isinstance(objects, Mapping)
                    and objects.get("zone") == "exile"
                )
            )
            if not in_exile:
                raise DslError(
                    f"{where}: 'playable': {duration!r} lasts at most while the card is in "
                    f"exile, so it needs cards being exiled or already there "
                    f"(exile, look_at_top to exile, grant_playable over zone exile)"
                )
    if op == "copy_permanent" and (overrides := effect.get("except_") or effect.get("except")):
        # "…except it's a white Zombie Angel with no mana cost." A misspelled
        # key here would be silently dropped, and the token would come back a
        # plain copy -- which is a different card and looks identical until
        # somebody reads its colour.
        if not isinstance(overrides, Mapping):
            raise DslError(f"{where}: 'except_' must be an object")
        unknown = set(overrides) - COPY_EXCEPT_KEYS
        if unknown:
            raise DslError(
                f"{where}.except_: unsupported keys {sorted(unknown)} "
                f"(implemented: {sorted(COPY_EXCEPT_KEYS)})"
            )
        for color in overrides.get("colors") or ():
            if color not in KNOWN_COLORS:
                raise DslError(f"{where}.except_.colors: unknown colour {color!r}")
        if "types" in overrides:
            # A **replacement**, unlike `add_subtypes` beside it -- "it's an
            # artifact and it loses all other card types". So an empty list is a
            # copy with no card type at all, which no printing says and which
            # nothing downstream is written to survive.
            if not overrides["types"]:
                raise DslError(
                    f"{where}.except_.types: replaces the copy's card types, "
                    f"so an empty list is a permanent with none"
                )
            for t in overrides["types"]:
                if t not in KNOWN_TYPES:
                    raise DslError(f"{where}.except_.types: unknown card type {t!r}")
        if "types" in overrides and "add_types" in overrides:
            # One replaces and one adds, so together they say two different
            # printed lines at once -- the order would be a guess.
            raise DslError(
                f"{where}.except_: 'types' replaces the card types and 'add_types' "
                f"adds to them -- write the one the printed clause says"
            )
        for key, known, noun in (
            ("add_types", KNOWN_TYPES, "card type"),
            ("add_supertypes", KNOWN_SUPERTYPES, "supertype"),
            ("remove_supertypes", KNOWN_SUPERTYPES, "supertype"),
        ):
            if key not in overrides:
                continue
            added = overrides[key]
            if not isinstance(added, list) or not added:
                # A clause naming nothing is a clause that does nothing, and
                # "except it's legendary" dropped is a copy the legend rule
                # never sees -- "except it isn't legendary" dropped is one the
                # legend rule bins, which is worse.
                raise DslError(f"{where}.except_.{key}: must be a non-empty list")
            for name in added:
                if name not in known:
                    raise DslError(f"{where}.except_.{key}: unknown {noun} {name!r}")
        if both := set(overrides.get("add_supertypes") or ()) & set(
            overrides.get("remove_supertypes") or ()
        ):
            # One printed clause cannot both grant and strip the same supertype,
            # and whichever way `chars` happened to order the two would decide a
            # card's behaviour by accident.
            raise DslError(
                f"{where}.except_: {sorted(both)} is both added and removed -- "
                f"write the one the printed clause says"
            )
        for key in ("power", "toughness"):
            # "...except it's a 4/4" (eternalize). The base size, so a number and
            # never an expression: 707.9b makes it a copiable value, fixed when
            # the copy is made, not something re-read as the game goes on.
            if key in overrides:
                value = overrides[key]
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise DslError(
                        f"{where}.except_.{key}: must be a non-negative integer, got {value!r}"
                    )
        if ("power" in overrides) != ("toughness" in overrides):
            # Every printed exception names a size as "N/N"; half of one is a
            # typo that would leave the copied card's other half standing.
            raise DslError(f"{where}.except_: 'power' and 'toughness' come as a pair")
    if op == "add_subtype":
        # An op that names no subtype is a printed sentence that does nothing,
        # and it would load and resolve exactly like one that works.
        if not effect.get("subtypes"):
            raise DslError(f"{where}: add_subtype needs 'subtypes'")
        for index, entry in enumerate(effect.get("subtypes") or ()):
            # Literal names only, and `{"chosen_type_of": "self"}` most of all.
            #
            # The static of the same name *does* take it -- "this creature is
            # the chosen type in addition to its other types" -- and the op
            # cannot, because the op writes a fixed word onto the permanent and
            # walks away (`primitives.add_subtypes`). A choice re-made, or a
            # `change_text` moving it, would never reach a type granted this
            # way, so the same JSON in the two places would mean two different
            # cards while reading identically.
            #
            # This guard is the load-time half of closing a real trap: the op
            # used to coerce every entry with `str()`, so this spec compiled
            # clean and the permanent gained the literal subtype
            # "{'chosen_type_of': 'self'}" -- a card that loads, resolves,
            # passes a zone assertion and is of no creature type at all.
            if not isinstance(entry, str):
                raise DslError(
                    f"{where}.subtypes[{index}]: the add_subtype *op* takes literal "
                    f"subtype names, not {entry!r}; a one-shot freezes the word it "
                    f"writes, so 'of the chosen type' is the add_subtype static"
                )
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
        # "**Until end of turn**, Sarkhan becomes a Dragon…" A misspelled clock
        # would otherwise read as no clock at all, and a Dragon for the turn
        # would stay one for good.
        if effect.get("duration", "permanent") not in (
            "permanent",
            "until_end_of_turn",
            "until_your_next_turn",
        ):
            raise DslError(
                f"{where}: unknown add_subtype duration {effect['duration']!r} "
                f"(use 'until_end_of_turn', 'until_your_next_turn', or omit it for "
                f"a type change with no duration)"
            )
    if op == "gain_control":
        # "Gain control of" with nothing named is a card that reads like removal
        # and does nothing at all.
        if "objects" not in effect:
            raise DslError(f"{where}: gain_control needs 'objects' -- there is nothing to take")
        # Both forms exist now, and the guard stays for the reason it was
        # written: a `duration` nobody checked would be read as "until end of
        # turn" by whoever wrote it and ignored by the engine, which turns Act
        # of Treason into a strictly better card than the printed one. What
        # changed is that `until_end_of_turn` is now implemented rather than
        # refused -- every other spelling is still a load error, exactly as
        # `grant_keyword`'s is below.
        if "duration" in effect and str(effect["duration"]) not in CONTROL_DURATIONS:
            raise DslError(
                f"{where}: unknown gain_control duration {effect['duration']!r} "
                f"(use one of {list(CONTROL_DURATIONS)})"
            )
    if op == "rotate_control":
        # Aminatou's -6. Without a pool the op rotates nothing and the card
        # reads as a board swap that never happens; a misspelt direction would
        # silently fall through to "right".
        if "objects" not in effect:
            raise DslError(f"{where}: rotate_control needs 'objects' -- what passes around the table")
        if "direction" in effect and effect["direction"] not in ("left", "right"):
            raise DslError(
                f"{where}: rotate_control direction is 'left' or 'right', not {effect['direction']!r}"
            )
    # Dack Fayden's split. Without a pool the op hands out nothing and the
    # card reads as a gift that never arrives.
    if op == "distribute_control_among_opponents" and "objects" not in effect:
        raise DslError(
            f"{where}: distribute_control_among_opponents needs 'objects' -- "
            f"the permanents handed out, one to each chosen opponent"
        )
    if op == "exchange_control":
        # 701.12: two permanents, each named. Without either half the op does
        # nothing at all, which reads like the card and is not it.
        for key in ("first", "second"):
            sub = effect.get(key)
            if not isinstance(sub, Mapping):
                raise DslError(
                    f"{where}: exchange_control needs '{key}', a selector naming one "
                    f"of the two permanents to swap"
                )
            validate_selector(sub, f"{where}.{key}")
            _validate_nested_player_refs(sub, f"{where}.{key}", target_kinds)
            if "target" in sub and str(sub["target"]) not in target_kinds:
                raise DslError(
                    f"{where}.{key}: references target {sub['target']!r} which the "
                    f"card does not declare"
                )
        if "duration" in effect:
            # Every printed exchange is indefinite (701.12a). A duration nobody
            # reads would be believed by whoever wrote it.
            raise DslError(f"{where}: exchange_control is permanent and takes no 'duration'")
    if op == "discard":
        if "up_to" in effect and not isinstance(effect["up_to"], bool):
            raise DslError(f"{where}: discard's 'up_to' is a boolean")
        if effect.get("up_to") and effect.get("random"):
            # Nobody is choosing, so there is no floor to relax -- and a card
            # that printed both would be saying two different things about who
            # decides.
            raise DslError(
                f"{where}: discard cannot be both 'random' and 'up_to' -- "
                f"a random discard has no choice to make"
            )
        if "as" in effect and not isinstance(effect["as"], str):
            raise DslError(f"{where}: discard's 'as' is a binding name")
    if op == "redirect_attack" and not effect.get("objects"):
        # Without it the pool is empty and the op silently moves nothing -- a
        # Misleading Signpost whose reselection never happens.
        raise DslError(
            f"{where}: 'redirect_attack' needs 'objects' naming the attacking "
            f"creature to reselect for, normally {{'target': 't1'}}"
        )
    if op == "choose_permanents" and "as" not in effect:
        # It changes nothing on the board, so a choice nobody reads back is a
        # question put to the player for no reason -- and a card written that
        # way would load, prompt, and do nothing with the answer.
        raise DslError(
            f"{where}: 'choose_permanents' only marks permanents, so it needs an "
            f"'as' for something later to read"
        )
    if op == "create_token" and "token" not in effect:
        raise DslError(f"{where}: create_token needs a 'token' id")
    if op == "create_token" and ("power" in effect) != ("toughness" in effect):
        # "Create an X/X …" prints both numbers. One alone would leave the
        # other at the X/X token's written 0, and a 3/0 Shark dies to 704.5f
        # the moment it is made. Which tokens take the pair at all is
        # `linking.validate_token_references`' check, since only it sees the pool.
        raise DslError(
            f"{where}: create_token's 'power' and 'toughness' go together -- "
            f"an X/X token prints both"
        )
    if op == "amass":
        # "Amass Orcs 2" prints both halves. A missing N would amass one, and a
        # missing or misspelled subtype has no token to create -- an Orc card
        # quietly making Zombies is a different card in every tribal deck.
        if "amount" not in effect:
            raise DslError(f"{where}: amass needs an 'amount', the N of 'Amass Zombies N'")
        if effect.get("subtype") not in AMASS_TOKENS:
            raise DslError(
                f"{where}: amass needs a 'subtype', one of {sorted(AMASS_TOKENS)}, "
                f"got {effect.get('subtype')!r}"
            )
    if op == "incubate" and "amount" not in effect:
        # "Incubate N" always prints its N. Defaulted, a card missing the key
        # would load and make a 1/1 where it prints a 3/3 -- or, for Sunfall,
        # one counter where it counts the creatures it exiled.
        raise DslError(f"{where}: incubate needs an 'amount', the N of 'Incubate N'")
    if op == "empower" and "amount" not in effect:
        # "Empower Jace N" always prints its N. Defaulted, a card missing the
        # key would load and empower by one -- Mindseeker Oculus putting one
        # counter where it prints four.
        raise DslError(f"{where}: empower needs an 'amount', the N of 'Empower Jace N'")
    if "destination_if" in effect:
        # "Put it onto the battlefield tapped if it's a land card. Otherwise,
        # put it into your hand." Only the two search ops read it; anywhere else
        # it would load and be ignored, and the card would send every card it
        # found to one place -- which is the printed line with half its sentence
        # missing.
        if op not in ("search_library", "search_zones"):
            raise DslError(
                f"{where}: 'destination_if' is read only by search_library "
                f"and search_zones"
            )
        branches = effect["destination_if"]
        if not isinstance(branches, list) or not branches:
            raise DslError(
                f"{where}.destination_if: a non-empty list of "
                f"{{'selector': …, 'to': …}} branches"
            )
        for i, branch in enumerate(branches):
            at = f"{where}.destination_if[{i}]"
            if not isinstance(branch, dict) or "selector" not in branch:
                raise DslError(f"{at}: needs a 'selector' saying which cards it catches")
            validate_selector(branch["selector"], f"{at}.selector")
            to = branch.get("to", "hand")
            if to not in DESTINATIONS:
                raise DslError(f"{at}.to: unknown destination {to!r}")
    # Three axes, one op: a creature type (the default), a permanent type or a
    # card type. A near-miss word here would fall through to the creature-type
    # branch and ask the wrong question -- a card printing "choose a permanent
    # type" that offers Vampire.
    if (
        op == "choose_type"
        and "of" in effect
        and effect["of"] not in ("creature_type", "permanent_type", "card_type")
    ):
        raise DslError(
            f"{where}: choose_type's 'of' is 'creature_type', 'permanent_type' "
            f"or 'card_type', not {effect['of']!r}"
        )
    if op == "fight":
        # Both halves, or it is not a fight. With one missing the op resolves to
        # nothing and the card silently does half of what it prints -- and the
        # half it would drop is the one that hits *your* creature, so the card
        # would be strictly better than printed rather than merely weaker.
        for key in ("objects", "other"):
            if key not in effect:
                raise DslError(
                    f"{where}: fight needs both 'objects' and 'other' -- the two "
                    f"creatures that deal damage to each other (701.12a)"
                )
            validate_selector(effect[key], f"{where}.{key}")
    if "attached_to" in effect:
        # "Create a Wicked Role token attached to it." Only `create_token` reads
        # the key; on any other op it would load and attach nothing. That the
        # token is an Aura is checked by `validate_token_references`, which is
        # where token ids resolve.
        if op != "create_token":
            raise DslError(f"{where}: 'attached_to' is read only by create_token")
        validate_selector(effect["attached_to"], f"{where}.attached_to")
    if op == "create_token" and "controller" in effect:
        # Whose tokens these are, as a full player spec -- `op_create_token`
        # loops `select_players` over it. Unchecked until gift needed to aim one
        # at a promised opponent, and a misspelling here is the quietest error
        # the op has: `select_players` raises `DslError` mid-resolution for a
        # bad *string*, which is a crash in the middle of a game rather than a
        # refusal at load, and every mapping form fails silently by resolving to
        # nobody -- a card that prints "they create a token" and creates none.
        _validate_player_spec(effect["controller"], f"{where}.controller", target_kinds)
    if op in ATTACKING_OPS and "attacking" in effect:
        _validate_attacking(effect["attacking"], f"{where}.attacking", target_kinds)
    if op in ATTACKING_OPS and "or_planeswalker" in effect:
        # "…attacking that player or a planeswalker they control." A widening of
        # `attacking`, so it means nothing without one: beside no `attacking`
        # (or `false`) it would load and the token would attack nobody, which
        # reads as the printed card and drops the whole clause. A string such
        # as "true" is refused for the same reason -- it is not the flag.
        if not isinstance(effect["or_planeswalker"], bool):
            raise DslError(f"{where}.or_planeswalker: must be true or false")
        if effect["or_planeswalker"] and effect.get("attacking") in (None, False):
            raise DslError(
                f"{where}.or_planeswalker: widens `attacking` to 'that player or a "
                f"planeswalker they control' and needs an `attacking` to widen"
            )
    # "Another target creature you control gains toxic 1" (Skrelv, Defector
    # Mite) has a number a granted word cannot carry.
    if op == "grant_keyword":
        refuse_numbered_grant(
            list(effect.get("keywords") or ()) + ([effect["keyword"]] if "keyword" in effect else []),
            where,
        )
    # A misspelled duration would silently fall back to until-end-of-turn,
    # which is the *wrong half* of riot rather than a smaller version of it.
    if op == "grant_keyword" and effect.get("duration", "until_end_of_turn") not in (
        "until_end_of_turn",
        "until_your_next_turn",
        "permanent",
    ):
        raise DslError(
            f"{where}: unknown grant_keyword duration {effect['duration']!r} "
            f"(use 'until_end_of_turn', 'until_your_next_turn' or 'permanent')"
        )
    # And the same trap on the other three `TempEffect` ops: `duration` was
    # read by none of them, so "gets -2/-1 until your next turn" written with
    # it loaded and quietly wore off at this turn's cleanup -- before the only
    # turns Liliana, the Last Hope's +1 is printed for.
    # (`animate` is guarded with the rest of its keys below: it also takes Oko's
    # `permanent`, which neither of the other two has.)
    if op in ("pump", "lock_abilities") and effect.get(
        "duration", "until_end_of_turn"
    ) not in ("until_end_of_turn", "until_your_next_turn"):
        raise DslError(
            f"{where}: unknown {op} duration {effect['duration']!r} "
            f"(use 'until_end_of_turn' or 'until_your_next_turn')"
        )
    if op == "lose_keyword":
        # "…lose hexproof and shroud **and can't have** hexproof or shroud."
        # The op is that prohibition and nothing weaker, so the clause is
        # written out: a bare "loses flying until end of turn" is a removal a
        # later grant survives (613.7), and loading it here would be a
        # stronger card that reads the same.
        if effect.get("cant_have") is not True:
            raise DslError(
                f"{where}: lose_keyword is \"lose X and can't have X\" and needs "
                f"'cant_have': true; a plain \"loses X until end of turn\" is not "
                f"implemented"
            )
        if not effect.get("objects"):
            # An absent selector would choose nothing, and a printed hoser
            # would resolve doing nothing.
            raise DslError(
                f"{where}: lose_keyword needs 'objects' (the permanents that lose "
                f"the keywords, chosen as it resolves)"
            )
        words = effect.get("keywords")
        if not isinstance(words, list) or not words:
            raise DslError(
                f"{where}: lose_keyword needs 'keywords', a non-empty list of the "
                f"keywords it removes"
            )
        for k in words:
            if k not in KNOWN_KEYWORDS:
                raise DslError(f"{where}: unknown keyword {k!r}")
        # Until end of turn, the one clock printed. Any other word would load
        # and quietly wear off at this turn's cleanup.
        if str(effect.get("duration", "until_end_of_turn")) != "until_end_of_turn":
            raise DslError(
                f"{where}: unknown lose_keyword duration {effect['duration']!r} "
                f"(implemented: 'until_end_of_turn')"
            )
    if op == "grant_flash_permission":
        # Without a duration the permission would have no clock to end on, and a
        # misspelt type would narrow it to nothing -- the +1 doing nothing.
        if effect.get("duration") not in FLASH_PERMISSION_DURATIONS:
            raise DslError(
                f"{where}: grant_flash_permission needs a 'duration' in "
                f"{list(FLASH_PERMISSION_DURATIONS)}"
            )
        for t in effect.get("types") or ():
            if t not in KNOWN_TYPES:
                raise DslError(f"{where}: unknown card type {t!r}")
        # Creature types only (205.3m), because that is all the reader matches:
        # an "Equipment" here would narrow the permission to nothing. And the
        # one dynamic entry spelled exactly, or "of the chosen type" resolves
        # to no type and the Icon's ability does nothing, for ever.
        for index, entry in enumerate(effect.get("subtypes") or ()):
            if isinstance(entry, Mapping):
                if dict(entry) != {"chosen_type_of": "self"}:
                    raise DslError(
                        f"{where}.subtypes[{index}]: the only subtype that is not a "
                        f'literal name is {{"chosen_type_of": "self"}}, not {dict(entry)!r}'
                    )
            elif not isinstance(entry, str) or SUBTYPE_CLASS.get(entry, "Creature") != "Creature":
                raise DslError(
                    f"{where}.subtypes[{index}]: grant_flash_permission narrows by "
                    f"creature type, and {entry!r} is not one"
                )
        if not isinstance(effect.get("next_spell", False), bool):
            raise DslError(f"{where}: grant_flash_permission's 'next_spell' is true or false")
    if op in ("add_poison", "add_energy") and "amount" in effect:
        validate_value(effect["amount"], f"{where}.amount")
    if op == "lose_all_player_counters":
        # "Each opponent loses all counters" always names who; without a
        # `player` the op would have to guess whose. And it takes every kind,
        # so a narrowing key would be silently ignored -- "loses all poison
        # counters" (Leeches) is a different sentence this op does not write.
        if "player" not in effect:
            raise DslError(
                f"{where}: lose_all_player_counters needs 'player' naming who "
                f"loses their counters, e.g. 'each_opponent'"
            )
        for key in ("counter", "kinds", "amount"):
            if key in effect:
                raise DslError(
                    f"{where}: lose_all_player_counters removes every kind of "
                    f"counter from the player, so it takes no {key!r}"
                )
    if op == "proliferate" and "objects" in effect:
        # The retired simplification's narrowing key. 701.27a is a free choice
        # over every permanent and player with a counter, which the op now asks;
        # a selector would silently decide it for the player instead.
        raise DslError(
            f"{where}: proliferate takes no 'objects' -- the controller chooses "
            f"what to proliferate as it resolves (701.27a)"
        )
    if op == "detain" and not effect.get("objects"):
        # Detain with no selector restricts nobody: the card resolves, the log
        # says nothing, and the creature attacks anyway.
        raise DslError(f"{where}: detain needs 'objects' naming what is detained")
    if op == "extra_combat":
        # "…followed by an additional main phase" is half of what Relentless
        # Assault and Resurgence print, and a misspelled key here drops it
        # silently -- leaving a four-mana sorcery that grants a bare extra
        # combat, which is a different and worse card. So the flag is checked by
        # name and by type.
        if "extra_main" in effect and not isinstance(effect["extra_main"], bool):
            raise DslError(
                f"{where}: extra_combat's 'extra_main' is a flag (true/false), "
                f"got {effect['extra_main']!r}"
            )
        # A phase belongs to the *turn*, not to a player: an extra combat granted
        # during somebody else's turn is theirs (Seize the Day). Accepting a
        # `player` and ignoring it would read as "your extra combat" and be
        # neither.
        for key in ("player", "controller"):
            if key in effect:
                raise DslError(
                    f"{where}: extra_combat takes no {key!r} -- an extra phase belongs "
                    f"to the turn in progress, whoever's turn that is"
                )
    if op == "extra_turn" and "controller" in effect:
        # Whose turn it is goes in `player`, the key every player-naming op
        # uses. `controller` is the near miss worth refusing by name: it is what
        # Parting Gust's gift reward is aimed with, so a Perch Protection copied
        # from it would load, ignore the key, and hand the promised turn to the
        # *caster* -- a gift spell that pays its own controller instead.
        raise DslError(
            f"{where}: extra_turn names who takes the turn with 'player', "
            f"not 'controller' (e.g. \"player\": \"gift_recipient\")"
        )
    if op == "no_maximum_hand_size":
        # The op's one lifetime is in its name: the rest of the game. A
        # `duration` would load, be ignored, and turn Enter the Infinite's
        # "until your next turn" into a permanent upgrade; `objects` and
        # `controller` are the near misses copied from `set_flag` and
        # `extra_turn`'s neighbours, and ignoring either names the caster by
        # default -- the wrong seat for any "target player" version.
        for key in ("duration", "objects", "controller"):
            if key in effect:
                raise DslError(
                    f"{where}: no_maximum_hand_size takes no {key!r} -- it lasts "
                    f"the rest of the game, and names who with 'player'"
                )
    if op == "set_flag" and not effect.get("flag"):
        # A flag with no name writes nothing, so renown's once-only guard never
        # closes and the creature grows on every combat damage for ever.
        raise DslError(f"{where}: set_flag needs a 'flag' to write")
    if op == "set_turn_flag":
        if not effect.get("flag"):
            # Same failure as `set_flag` above with a worse tell: the guard that
            # reads it back never bites, so Combat Celebrant offers its exert on
            # every attack of the turn and the card that prints a once-per-turn
            # clause plays as though it does not.
            raise DslError(f"{where}: set_turn_flag needs a 'flag' to write")
        if "duration" in effect:
            # There is exactly one duration here, and it is in the name. A card
            # asking for another one is asking for `set_flag`, whose word is
            # permanent -- accepting and ignoring the key would give whichever
            # of the two the author did not want.
            raise DslError(
                f"{where}: set_turn_flag takes no 'duration' -- it lasts the turn "
                f"(use set_flag for a word that never wears off)"
            )
    _validate_any_kind_counters(effect, op, where)
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
    if op == "distribute_counters":
        # "Distribute three +1/+1 counters among up to three target creatures"
        # (601.2d). The division is announced as the ability is activated, over
        # the targets just declared, so the op must name one target spec and a
        # number printed on the card -- a computed total could not be divided
        # before it is known.
        objects = effect.get("objects")
        if not (isinstance(objects, Mapping) and set(objects) == {"target"}):
            raise DslError(
                f"{where}: distribute_counters needs 'objects': {{\"target\": <id>}} -- "
                f"the counters are divided among that target spec's choices"
            )
        amount = effect.get("amount")
        if isinstance(amount, Mapping) and set(amount) == {"const"}:
            amount = amount["const"]
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 1:
            raise DslError(
                f"{where}: distribute_counters needs a printed 'amount' of 1 or more "
                f"(an int or {{\"const\": n}}); the division is announced before "
                f"anything could be computed"
            )
    if op == "double_counters" and not effect.get("objects"):
        # Without `objects` the pool is empty and nothing doubles: a Deepglow
        # Skate that loads clean and does nothing.
        raise DslError(
            f"{where}: double_counters needs 'objects' naming the permanents "
            f"whose counters are doubled"
        )
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
    if "all_if" in effect:
        # Entwine. Only `choose_mode` has modes to take all of, so anywhere else
        # the key would load, be ignored, and leave a card that reads "choose
        # both" and chooses one.
        if op != "choose_mode":
            raise DslError(f"{where}: 'all_if' only means anything on choose_mode, not {op!r}")
        validate_condition(effect["all_if"], f"{where}.all_if")
    if "up_to" in effect:
        # "Choose up to two --" (Call Damage Control). The unconditional ceiling
        # with no floor, which `count` (exact), `all_if` (every mode) and
        # `up_to_if` (conditional, floor of one) between them could not say. The
        # name is `TargetSpec`'s, where it has meant the same thing since "up to
        # X target creatures".
        if op not in ("choose_mode", "discard", *COUNTER_REMOVAL_UP_TO_OPS):
            raise DslError(
                f"{where}: 'up_to' only means anything on choose_mode, discard or "
                f"{' or '.join(COUNTER_REMOVAL_UP_TO_OPS)}, not {op!r}"
            )
        if not isinstance(effect["up_to"], bool):
            raise DslError(f"{where}: 'up_to' is a boolean, got {effect['up_to']!r}")
        if op in COUNTER_REMOVAL_UP_TO_OPS:
            # "Remove up to three counters" -- `amount` becomes a ceiling and the
            # floor drops to zero. Which removals may carry it is the op's own
            # guard (`_validate_any_kind_counters`).
            pass
        elif op == "discard":
            # "Discard up to two cards" -- the same word doing the same job one
            # op over: `amount` becomes a ceiling and the floor drops to zero.
            # The mode-count checks below are `choose_mode`'s own and read
            # `count`, which a discard does not have.
            return
        else:
            count = effect.get("count", 1)
            if isinstance(count, dict) and "const" in count:
                count = count["const"]
            if isinstance(count, int) and not isinstance(count, bool) and count < 1:
                # "Up to zero modes" is a card that does nothing.
                raise DslError(f"{where}: 'up_to' needs a 'count' of at least 1; got {count}")
    if "or_more" in effect:
        # "Choose one or more --" (Black Market Connections). A floor and a
        # ceiling at once: `count` stays the minimum and every mode is on offer.
        if op != "choose_mode":
            raise DslError(f"{where}: 'or_more' only means anything on choose_mode, not {op!r}")
        if not isinstance(effect["or_more"], bool):
            raise DslError(f"{where}: 'or_more' is a boolean, got {effect['or_more']!r}")
        if effect.get("up_to"):
            # One says "you must take at least `count`" and the other says "you
            # may take none". A card printing both is a card saying two things,
            # and `modal_bounds` would silently let `up_to` win.
            raise DslError(
                f"{where}: 'or_more' and 'up_to' contradict each other -- "
                f"one keeps a floor, the other removes it"
            )
        modes = effect.get("modes") or []
        count = effect.get("count", 1)
        if isinstance(count, dict) and "const" in count:
            count = count["const"]
        if isinstance(count, int) and not isinstance(count, bool) and count >= len(modes):
            # "Choose two or more" of two modes is "choose both", written the
            # long way -- and it would load, offering a question with one answer.
            raise DslError(
                f"{where}: 'or_more' needs a 'count' below the number of modes; "
                f"got {count} of {len(modes)}"
            )
    if "up_to_if" in effect:
        # The same guard for entwine's mirror image, and it was missing -- which
        # is how a card carrying `up_to_if` compiled, played and cleared every
        # gate while its first printed sentence did nothing at all.
        if op != "choose_mode":
            raise DslError(f"{where}: 'up_to_if' only means anything on choose_mode, not {op!r}")
        more = effect["up_to_if"]
        if not isinstance(more, Mapping) or "condition" not in more:
            raise DslError(
                f"{where}: 'up_to_if' takes a 'condition' saying when the extra "
                f"modes are offered, and optionally a 'count'"
            )
        validate_condition(more["condition"], f"{where}.up_to_if.condition")
        if "count" in more:
            validate_value(more["count"], f"{where}.up_to_if.count")
    if op == "choose_mode" and "optional" in effect:
        # "You may choose two" (Shadrix Silverquill): none, or exactly `count`.
        # Every other clause that reshapes the count would either contradict it
        # or be silently ignored by `modes.ask_none_or_exactly`, which asks the
        # exact number and nothing else.
        if not isinstance(effect["optional"], bool):
            raise DslError(f"{where}: 'optional' is a boolean, got {effect['optional']!r}")
        if effect["optional"]:
            clash = [
                key
                for key in (
                    "up_to", "up_to_if", "or_more", "all_if", "budget", "random",
                    "chooser", "once_each",
                )
                if effect.get(key) not in (None, False)
            ]
            if clash:
                raise DslError(
                    f"{where}: an 'optional' choose_mode is none or exactly 'count' "
                    f"modes, so {clash} cannot apply to it"
                )
            count = effect.get("count", 1)
            if isinstance(count, dict) and "const" in count:
                count = count["const"]
            modes = effect.get("modes") or []
            if not isinstance(count, int) or isinstance(count, bool) or count < 2:
                # "You may choose one" is `up_to` with a count of one, and a
                # computed count has no load-time answer to check.
                raise DslError(
                    f"{where}: 'optional' needs a fixed 'count' of at least 2 "
                    f"(\"you may choose one\" is 'up_to'); got {count!r}"
                )
            if count > len(modes):
                raise DslError(
                    f"{where}: 'optional' asks for {count} modes of {len(modes)}, "
                    f"which can never be chosen"
                )
            if ".spell_effects[" in where:
                # A spell's modes are answered at 601.2b by `Game._ask_modes`,
                # which has no "or none"; and a modal spell that chooses no
                # mode at all is not a spell the rules let you cast.
                raise DslError(
                    f"{where}: 'optional' is for a triggered ability's \"you may "
                    f"choose N\", chosen as it goes on the stack (603.3c); a "
                    f"spell chooses its modes as it is cast"
                )
    if op == "choose_mode" and "random" in effect:
        # "Choose one at random" -- the game picks exactly `count` modes off its
        # seeded rng. Every clause that shapes a *player's* answer is
        # meaningless here and would load, be ignored, and leave a card whose
        # printed widening or chooser does nothing.
        if not isinstance(effect["random"], bool):
            raise DslError(f"{where}: 'random' is a boolean, got {effect['random']!r}")
        if effect["random"]:
            clash = [
                key
                for key in (
                    "chooser", "budget", "up_to", "up_to_if", "or_more", "all_if", "optional",
                )
                if effect.get(key) not in (None, False)
            ]
            if clash:
                raise DslError(
                    f"{where}: a 'random' choose_mode picks exactly 'count' modes "
                    f"with nobody choosing, so {clash} cannot apply to it"
                )
    if "choose_instead_if" in effect:
        # "If you discarded a card this turn, you choose one instead" (Typhoid
        # Mary, Fractured). Only a random pick has an "instead" to switch to;
        # anywhere else the key would load and be ignored.
        if op != "choose_mode" or effect.get("random") is not True:
            raise DslError(
                f"{where}: 'choose_instead_if' only means anything on a choose_mode "
                f"with 'random': true"
            )
        validate_condition(effect["choose_instead_if"], f"{where}.choose_instead_if")
        if effect["choose_instead_if"] is None:
            raise DslError(f"{where}: 'choose_instead_if' needs a condition")
    if "as" in effect:
        # `as` names a binding -- `snapshot`'s, and the record `reveal`,
        # `sacrifice`, `exile` and the two token-making ops write of what they
        # consumed or produced. A non-string would be stringified into a name
        # nothing reads back, so the count it feeds would be 0 and amplify would
        # enter with no counters.
        if not (isinstance(effect["as"], str) and effect["as"]):
            raise DslError(f"{where}: 'as' must be a non-empty binding name, got {effect['as']!r}")
        if op not in RECORDING_OPS:
            # And an `as` on an op that writes no binding fails exactly the same
            # way while looking right on the page: "tap all creatures, then
            # draw a card for each tapped this way" would load, resolve, and
            # draw nothing. Only these ops record, so only these may be asked
            # to -- the next op to grow one adds itself here.
            raise DslError(
                f"{where}: {op!r} records no binding, so its 'as' would name one "
                f"nothing writes and every read of it would be 0 "
                f"(ops that record: {sorted(RECORDING_OPS)})"
            )
    if "snapshot" in effect:
        # `sacrifice`'s LKI twin of `as`: the characteristics the chosen
        # permanent had while it was still on the battlefield. Only `sacrifice`
        # reads the key, and an unread key is the silent failure this pass
        # exists to catch -- Entrapment Maneuver would load with `snapshot` on
        # the wrong op, resolve, and make zero tokens because
        # `{"toughness_of": {"binding": …}}` found nothing under that name.
        # (An effect whose *op* is `snapshot` spells its binding `as`, like
        # every other recording op, so it never reaches here.)
        if op != "sacrifice":
            raise DslError(
                f"{where}: 'snapshot' captures what a sacrificed permanent had "
                f"and only sacrifice reads it, not {op!r} "
                f"(use a separate snapshot op)"
            )
        if not (isinstance(effect["snapshot"], str) and effect["snapshot"]):
            raise DslError(
                f"{where}: 'snapshot' must be a non-empty binding name, got {effect['snapshot']!r}"
            )
    if op == "flip_coin":
        # "Flip a coin. If you lose the flip, ..." The branches are the card: a
        # flip with neither is a coin tossed for nothing, and a non-list branch
        # would be read as no effects at all.
        for key in ("effects", "else"):
            if key in effect and not isinstance(effect[key], list):
                raise DslError(f"{where}.{key}: a list of effects")
        if not effect.get("effects") and not effect.get("else"):
            raise DslError(
                f"{where}: flip_coin needs 'effects' (if you win the flip) or "
                f"'else' (if you lose it) -- a flip nothing reads changes nothing"
            )
    if op == "roll_dice":
        # The same refusal `join_forces` carries below, for the same reason: a
        # roll is never the effect, it is what the sentences after it read. A
        # `roll_dice` with no `as` throws dice into a binding nothing can name,
        # and every `{"rolled": …}` on the card answers 0 however they fell.
        if not effect.get("as"):
            raise DslError(
                f"{where}: roll_dice needs an 'as' naming the binding its results "
                f"land in; without it nothing can read what was rolled"
            )
        # "Roll X six-sided dice" -- the *number* of dice is a board count and is
        # a value expression (checked with `count` above), but the die itself is
        # printed on the card and never varies. Written as a value it would be
        # accepted, stringified and silently rolled as a d0.
        sides = effect.get("sides", 6)
        if not isinstance(sides, int) or isinstance(sides, bool) or sides < 2:
            raise DslError(
                f"{where}: 'sides' is the printed size of the die -- a plain "
                f"integer of at least 2, got {sides!r}"
            )
    if op == "join_forces":
        # The total is the card -- "for each mana paid this way" -- so an effect
        # that collects it and names no binding has taxed the whole table for
        # nothing, and would resolve without complaint.
        if not effect.get("as"):
            raise DslError(
                f"{where}: join_forces needs an 'as' naming the binding the total "
                f"lands in; without it nothing can read what was paid"
            )
        if "pay" in effect:
            if not isinstance(effect["pay"], dict):
                raise DslError(f"{where}: 'pay' must be an object")
            try:
                CostModel.model_validate(effect["pay"])
            except Exception as exc:  # pydantic ValidationError
                raise DslError(f"{where}: bad 'pay' cost: {exc}") from exc
            if effect["pay"].get("mana_reduction") is not None:
                _validate_cost_reduction(
                    effect["pay"]["mana_reduction"], f"{where}.pay.mana_reduction"
                )
    if effect.get("no_regeneration") is not None and op != "destroy":
        # "It can't be regenerated." belongs to a destruction, and `op_destroy`
        # is the only op that performs one. Written on anything else -- a
        # `damage` that will kill, a `sacrifice`, a `replace_deaths` -- it is
        # read by nobody, which is precisely how the clause came to be silently
        # dropped by every card that printed it in the first place.
        raise DslError(
            f"{where}: 'no_regeneration' only works on 'destroy' -- "
            f"nothing else replaces a destruction, so here it would be ignored"
        )
    if op == "regenerate" and not effect.get("objects"):
        # A shield with nothing to put it on. The ability would cost mana, log
        # nothing and save nobody -- and "Regenerate this creature" is three
        # words away from being right.
        raise DslError(
            f"{where}: regenerate needs 'objects' naming what is shielded "
            f'(use {{"self_only": true}} for "regenerate this creature")'
        )
    if op == "phase_out" and not effect.get("objects"):
        # The same trap as `regenerate` below. `choose_objects` with no selector
        # finds nothing, so the spell would resolve, log nothing and phase
        # nobody out -- and "this permanent phases out" is three words away.
        raise DslError(
            f"{where}: phase_out needs 'objects' naming what phases out "
            f'(use {{"self_only": true}} for "this permanent phases out")'
        )
    if op == "phase_in" and not effect.get("objects"):
        # A phased-out permanent is out of `state.battlefield`, so an absent
        # selector does not merely find the wrong thing -- it finds nothing at
        # all, and the return half of an Oubliette would silently strand the
        # creature phased out forever with its enchantment already gone.
        raise DslError(
            f"{where}: phase_in needs 'objects' naming what phases in "
            f'(use {{"phased_out_with": "self"}} for "the creature this '
            f'card phased out")'
        )
    if op == "unattach" and not effect.get("objects"):
        # Explore's trap once more: "unattach this permanent" is three words on
        # the Equipment that prints it, and a default would silently unattach
        # the spell object on anything that is not a permanent's own ability.
        raise DslError(
            f"{where}: unattach needs 'objects' naming what comes off "
            f'(use {{"self_only": true}} for "unattach this permanent")'
        )
    if op == "explore" and not effect.get("objects"):
        # 701.40a puts the +1/+1 counter on the *exploring* permanent, so the op
        # has to be told which one that is. Defaulted to this permanent it would
        # read correctly on a creature and silently do nothing on a sorcery,
        # whose source is a spell on the stack -- so the card would reveal no
        # card, place no counter, and load perfectly cleanly.
        raise DslError(
            f"{where}: explore needs 'objects' naming what explores "
            f'(use {{"self_only": true}} for "it explores")'
        )
    if op == "connive" and not effect.get("objects"):
        # Same trap as explore, and the same three words fix it: the +1/+1
        # counters go on the *conniving* permanent, so a defaulted `self_only`
        # would be right on "whenever this creature attacks, it connives" and
        # would draw and discard for nobody on "target creature connives".
        raise DslError(
            f"{where}: connive needs 'objects' naming what connives "
            f'(use {{"self_only": true}} for "it connives")'
        )
    # `reflecting` is the one add_mana that names no symbols: "one mana of any
    # color that a land an opponent controls could produce" reads them off the
    # board, so the card names the permanents to ask instead.
    if (
        op == "add_mana"
        and "mana" not in effect
        and "reflecting" not in effect
        and "colors_of" not in effect
        and "each_color_among" not in effect
        and not effect.get("in_commander_identity")
        and not effect.get("split")
        and not effect.get("any_one_color")
    ):
        raise DslError(
            f"{where}: add_mana needs 'mana' (or 'reflecting', or 'colors_of', or "
            f"'each_color_among', or 'in_commander_identity', or 'split', or "
            f"'any_one_color')"
        )
    if "colors_of" in effect:
        # "Add one mana of any of **the exiled card's colors**." Chrome Mox.
        # A selector over cards, read for their printed colours -- so it is one
        # more answer to the question the four keys above answer, and writing it
        # beside any of them would be two answers to one question with only the
        # first read. Silently: a Mox carrying `colors_of` under a `reflecting`
        # would load and tap for whatever the board said instead.
        if op != "add_mana":
            raise DslError(
                f"{where}: 'colors_of' names the colours an add_mana offers, "
                f"and is read by nobody on {op!r}"
            )
        clash = [
            key
            for key in ("mana", "reflecting", "in_commander_identity", "split", "each_color_among")
            if effect.get(key)
        ]
        if clash:
            raise DslError(
                f"{where}: 'colors_of' already says which colours this adds, so it "
                f"cannot be written beside {clash[0]!r} -- that is two answers to "
                f"one question, and only one of them would be read"
            )
        if "amount" in effect:
            # The family this joins is all "one mana of…", and the narrowing in
            # `costs.mana_options_of` hands back one-symbol options. An amount
            # here would load and be dropped, leaving a card that printed "two
            # mana" adding one.
            raise DslError(
                f"{where}: a 'colors_of' add_mana is one mana of one colour; "
                f"'amount' would load and never be read"
            )
    if "each_color_among" in effect:
        # "Vivid -- {T}: For each color among permanents you control, add one
        # mana of that color." Bloom Tender. One more answer to the question
        # 'mana', 'reflecting', 'colors_of', 'in_commander_identity' and 'split'
        # each answer -- which symbols does this ability make -- so writing it
        # beside any of them is two answers and only one gets read.
        if op != "add_mana":
            raise DslError(
                f"{where}: 'each_color_among' names the colours an add_mana makes, "
                f"and is read by nobody on {op!r}"
            )
        clash = [
            key
            for key in ("mana", "reflecting", "colors_of", "in_commander_identity", "split")
            if effect.get(key)
        ]
        if clash:
            raise DslError(
                f"{where}: 'each_color_among' already says which colours this adds, so "
                f"it cannot be written beside {clash[0]!r} -- that is two answers to "
                f"one question, and only one of them would be read"
            )
        if "amount" in effect:
            # `mana_produced` would happily multiply the whole bundle, so this
            # is not a dropped key -- it is a card nobody printed. "One mana of
            # that color" is the sentence, and a doubled bundle should be a
            # second `add_mana` family with its own witness rather than an
            # untested multiplier riding on this one.
            raise DslError(
                f"{where}: an 'each_color_among' add_mana is one mana of each colour "
                f"present; no printed card multiplies that bundle, so 'amount' here "
                f"would be a card the engine invented"
            )
    if op == "add_mana" and "any_type" in effect:
        # "Add one mana of any **type** that a land you control could produce."
        # It widens `reflecting`'s answer from five colours to 106.1b's six
        # types of mana, and it is read nowhere else on an add_mana: written
        # without `reflecting` -- on a fixed `mana` string, on `split`, on
        # `in_commander_identity` -- it would load, be ignored, and leave a card
        # that prints "any type" tapping for whatever the other key said.
        if not effect.get("reflecting"):
            raise DslError(
                f"{where}: 'any_type' widens 'reflecting' from five colours to the "
                f"six types of mana, so it needs one -- a mana ability that is not "
                f"a question about the board already names the types it makes"
            )
        if effect["any_type"] is not True:
            raise DslError(
                f"{where}.any_type: the only value is true -- \"any color\" is the "
                f"default and is spelled by leaving this off"
            )
    if op == "rename" and not str(effect.get("name") or "").strip():
        # A rename to nothing would load, run, and leave the permanent answering
        # to its printed name -- the printed line silently not happening.
        raise DslError(f"{where}: rename needs a 'name' -- what the permanent becomes called")
    if "name" in effect and op != "rename":
        # Every other op that means anything by a name spells it inside a
        # selector (`objects.name`) or a token id. A bare `name` elsewhere is
        # read by nobody.
        raise DslError(
            f"{where}: a bare 'name' is read only by the rename op, not by {op!r}"
        )
    if "persists_until_end_of_turn" in effect:
        # "Until end of turn, you don't lose this mana as steps and phases end."
        # Read only by the two ops that put mana in a pool: anywhere else the
        # printed promise is simply dropped, and the card reads as though the
        # mana lasted when it did not.
        if op not in ("add_mana", "add_mana_per"):
            raise DslError(
                f"{where}: 'persists_until_end_of_turn' is read only by add_mana "
                f"and add_mana_per, not by {op!r}"
            )
        if effect["persists_until_end_of_turn"] is not True:
            raise DslError(
                f"{where}.persists_until_end_of_turn: the only value is true -- "
                f"ordinary mana is the default and says nothing"
            )
    if op == "add_mana" and effect.get("split") is not None:
        # "Add X mana in any combination of {U} and/or {R}" -- Vivi Ornitier,
        # a mana ability; "in any combination of colors" -- Klauth, Unrivaled
        # Ancient, a triggered one. The colours are a list and the size is an
        # `amount`; `mana` says the opposite thing (a fixed production string)
        # and the two together would be two answers to one question.
        if "mana" in effect:
            raise DslError(
                f"{where}: 'split' names the colours a combination may draw on, so it "
                f"replaces 'mana' rather than joining it"
            )
        if not isinstance(effect["split"], list):
            raise DslError(f"{where}.split: expected a list of mana symbols")
        colors = [str(c) for c in effect["split"]]
        if len(colors) < 2:
            raise DslError(
                f"{where}.split: a combination needs two or more colours; one colour "
                f"is an ordinary 'mana' string with an 'amount'"
            )
        if unknown := [c for c in colors if c not in MANA_SYMBOLS]:
            raise DslError(f"{where}.split: unknown mana symbols {unknown}")
        if "amount" not in effect:
            # Without it the split has no size, and `_add_split_mana` would add
            # nothing at all -- a card that prints "add X mana" adding none.
            raise DslError(
                f"{where}: a split add_mana needs an 'amount' -- how much mana is "
                f"being divided. Without it the split has no size"
            )
    if "any_one_color" in effect:
        # "{T}: Add X mana of **any one color**, where X is Helga's power."
        # Sixth answer to the one question this family answers -- which symbols
        # does this ability make -- so beside any of the other five it is two
        # answers with only one read.
        if op != "add_mana":
            raise DslError(
                f"{where}: 'any_one_color' names the colours an add_mana makes, "
                f"and is read by nobody on {op!r}"
            )
        if effect["any_one_color"] is not True:
            raise DslError(
                f'{where}.any_one_color: the only value is true -- "any color" is '
                f"the default and is spelled by leaving this off"
            )
        clash = [
            key
            for key in ("mana", "reflecting", "colors_of", "each_color_among", "split")
            if effect.get(key)
        ]
        if effect.get("in_commander_identity"):
            clash.append("in_commander_identity")
        if clash:
            raise DslError(
                f"{where}: 'any_one_color' already says which colours this adds, so "
                f"it cannot be written beside {clash[0]!r} -- that is two answers to "
                f"one question, and only one of them would be read"
            )
        if "amount" not in effect:
            # Without one this is "add **one** mana of any color", which the
            # engine has always spelled as a `choose_mode` of five `add_mana`s
            # and which every shipped card uses. A second spelling for a
            # sentence that already has one is how the untested one ships: the
            # whole capability here is the *variable* size.
            raise DslError(
                f"{where}: an 'any_one_color' add_mana needs an 'amount' -- how many "
                f"mana of that one colour. \"Add one mana of any color\" is a "
                f"'choose_mode' of five 'add_mana's"
            )
    if "mana_restriction" in effect:
        # "Spend this mana only to cast spells" on mana an **effect** makes --
        # Klauth's attack trigger, where the ability-level `mana_restriction`
        # has no home: that one is compiled onto `Ability` and read at payment
        # time off an untapped source, and this mana is already in the pool.
        if op != "add_mana":
            raise DslError(
                f"{where}: 'mana_restriction' says what the mana this adds may pay "
                f"for, and is read by nobody on {op!r}"
            )
        # Compiled here as well as at resolution, so a malformed restriction
        # fails the test suite rather than a game.
        compile_restriction(effect["mana_restriction"], f"{where}.mana_restriction")
    if op in ("add_mana", "add_mana_per") and isinstance(effect.get("mana"), Mapping):
        # The one non-literal `mana`, and validated as such for the reason
        # `_restriction_name` validates its twin: a near-miss spelling that fell
        # through would be read as "no colour chosen" for ever, and the card
        # would load clean and tap for nothing at the table.
        entry = effect["mana"]
        if op != "add_mana":
            raise DslError(
                f'{where}: \'mana\' may only be {{"chosen_color_of": "self"}} on '
                f"'add_mana' -- there is no chosen colour to scale per object"
            )
        if set(entry) != {"chosen_color_of"} or entry["chosen_color_of"] != "self":
            raise DslError(
                f'{where}: the only dynamic add_mana is {{"chosen_color_of": "self"}}, '
                f"not {dict(entry)!r}"
            )
    if op == "grant_protection":
        # The same leaf, and the same silent failure it would otherwise have:
        # "protection from the color of your choice" that fell through the
        # substitution grants protection from nothing and looks like a card.
        for i, entry in enumerate(effect.get("from_colors") or ()):
            if isinstance(entry, Mapping):
                if set(entry) != {"chosen_color_of"} or entry["chosen_color_of"] != "self":
                    raise DslError(
                        f"{where}.from_colors[{i}]: the only dynamic colour is "
                        f'{{"chosen_color_of": "self"}}, not {dict(entry)!r}'
                    )
            elif entry in ("C", "colorless"):
                # 105.2c: colorless is not a colour, so it is not a letter here.
                raise DslError(
                    f"{where}.from_colors[{i}]: colorless is not a colour -- "
                    f"write 'from_colorless': true"
                )
            elif entry not in KNOWN_COLORS:
                raise DslError(f"{where}.from_colors[{i}]: unknown colour {entry!r}")
        # A grant with no recipient. `objects` alone was once the only shape, so
        # its absence used to be caught by `choose_objects` finding nothing --
        # which is the silent kind of nothing this pass exists to refuse now
        # that the op has a second half.
        if effect.get("player") is None and effect.get("objects") is None:
            raise DslError(
                f"{where}: grant_protection needs 'objects' or 'player' naming who gains it"
            )
        if effect.get("player") is not None:
            _validate_player_spec(effect["player"], f"{where}.player", target_kinds)
        if (
            not effect.get("from_colors")
            and not effect.get("from_types")
            and not effect.get("from_subtypes")
            and not effect.get("from_everything")
            and not effect.get("from_colorless")
        ):
            # Protection *from* nothing. It would install no qualities and read
            # on screen as a spell that resolved and did nothing at all.
            raise DslError(
                f"{where}: grant_protection needs a quality -- 'from_colors', "
                f"'from_types', 'from_subtypes', 'from_colorless' or 'from_everything'"
            )
        for flag in ("from_everything", "from_colorless"):
            if flag in effect and not isinstance(effect[flag], bool):
                raise DslError(f"{where}: {flag!r} is a boolean, got {effect[flag]!r}")
        if effect.get("from_colorless") and effect.get("from_everything"):
            # Everything already contains every colourless source; writing both
            # is a second sentence no card prints, and one of them dead weight.
            raise DslError(
                f"{where}: 'from_everything' already covers colorless -- "
                f"do not also write 'from_colorless'"
            )
        _refuse_protection_sentinels(effect.get("from_subtypes"), where)
        duration = effect.get("duration")
        if duration is not None:
            if effect.get("player") is None:
                # An object's grant is one `TempEffect` on `until_eot`, which
                # the cleanup step sweeps and nothing else does. Reading a
                # duration there and storing it anyway would be a protection
                # that claims to last past the turn and does not.
                raise DslError(
                    f"{where}: 'duration' only means anything on the 'player' "
                    f"half of grant_protection -- an object's grant is until "
                    f"end of turn"
                )
            if duration not in PLAYER_PROTECTION_DURATIONS:
                raise DslError(
                    f"{where}: unknown protection duration {duration!r} "
                    f"(implemented: {sorted(PLAYER_PROTECTION_DURATIONS)})"
                )
    if op == "airbend":
        if "objects" not in effect:
            # "Airbend all other creatures" is a pool, and an airbend with no
            # pool would exile nothing while still printing its sentence.
            raise DslError(f"{where}: airbend needs 'objects' -- there is nothing to exile")
        if "playable" in effect or "playable_this_turn" in effect:
            # The permission *is* airbend. A duration written beside it would
            # read as overriding "while each one is exiled" and would be
            # ignored, which is the silent-wrong-card shape.
            raise DslError(
                f"{where}: airbend grants its own permission ('while each one is "
                f"exiled') -- 'playable' belongs on 'exile', not here"
            )
        if (alt := effect.get("cost")) is not None:
            try:
                ManaCost.parse(str(alt))
            except Exception as exc:  # pragma: no cover - defensive
                raise DslError(f"{where}: airbend cost {alt!r} is not a mana cost") from exc
    if op == "cant_cast_spells_from_zones":
        if effect.get("player") is not None:
            _validate_player_spec(effect["player"], f"{where}.player", target_kinds)
        _validate_cast_lock_zones(effect.get("zones"), effect.get("except_zones"), where)
        duration = str(effect.get("duration", "until_your_next_turn"))
        if duration not in CAST_LOCK_DURATIONS:
            raise DslError(
                f"{where}: unknown cant_cast_spells_from_zones duration {duration!r} "
                f"(implemented: {sorted(CAST_LOCK_DURATIONS)})"
            )
    if op == "cant_cast_spells":
        # Both required: the printed shapes differ in who and for how long
        # ("you … this turn", "your opponents … this turn"), and a default would
        # silently write one as the other -- a lock on the wrong seats.
        if "player" not in effect or "duration" not in effect:
            raise DslError(f"{where}: cant_cast_spells needs 'player' and 'duration'")
        _validate_player_spec(effect["player"], f"{where}.player", target_kinds)
        if str(effect["duration"]) not in CAST_LOCK_DURATIONS:
            raise DslError(
                f"{where}: unknown cant_cast_spells duration {effect['duration']!r} "
                f"(implemented: {sorted(CAST_LOCK_DURATIONS)})"
            )
        if "zones" in effect or "except_zones" in effect:
            # The lock is total. A zone list belongs to
            # `cant_cast_spells_from_zones`, and here it would be ignored.
            raise DslError(
                f"{where}: cant_cast_spells is total -- a zone-filtered lock is "
                f"cant_cast_spells_from_zones"
            )
    if op == "play_exiled" and "exiles" in effect and not isinstance(effect["exiles"], bool):
        # `cast_card`'s rider and its refusal: a string "false" read as truthy
        # would exile a spell the card sends back to the graveyard.
        raise DslError(f"{where}: play_exiled's 'exiles' is true or false")
    if op == "cast_card":
        # "You may cast that card": the pool is the whole of what may be cast,
        # and without one the op offers nothing while still printing its
        # sentence.
        if not isinstance(effect.get("objects"), Mapping):
            raise DslError(f"{where}: cast_card needs an 'objects' selector naming the card")
        validate_selector(effect["objects"], f"{where}.objects")
        if "exiles" in effect and not isinstance(effect["exiles"], bool):
            # "Exile it instead" is a yes or a no; a string "false" read as
            # truthy would exile a spell the card sends back to the graveyard.
            raise DslError(f"{where}: cast_card's 'exiles' is true or false")
        for key in ("free", "selector", "zones", "per_owner"):
            if key in effect:
                # The near misses' keys. `cast_card` charges the mana cost; a
                # free cast is `cast_from_hand`, and a silently ignored `free`
                # would be the opposite card.
                raise DslError(
                    f"{where}: cast_card takes no {key!r} -- it casts the 'objects' "
                    f"pool at its mana cost (a free cast is cast_from_hand)"
                )
    if op == "exchange_life_total":
        # 701.12: the player half is named on every printing ("target
        # opponent's", "your"), and the creature half is always the ability's
        # own source ("this creature's toughness"). A default player would be a
        # guess about whose life total moves, and an `objects` key would be read
        # by nothing -- an exchange with some other creature, silently with this one.
        if effect.get("player") is None:
            raise DslError(
                f"{where}: exchange_life_total needs 'player' -- whose life total "
                f"is exchanged with this creature's toughness"
            )
        _validate_player_spec(effect["player"], f"{where}.player", target_kinds)
        for key in ("objects", "amount", "duration"):
            if key in effect:
                raise DslError(
                    f"{where}: exchange_life_total takes no {key!r} -- the creature "
                    f"is the ability's source and the exchange is indefinite (701.12)"
                )
    if op == "lock_life_total":
        if effect.get("player") is not None:
            _validate_player_spec(effect["player"], f"{where}.player", target_kinds)
        duration = str(effect.get("duration", "until_your_next_turn"))
        if duration not in LIFE_LOCK_DURATIONS:
            # A misspelled duration would fall back to the default and last a
            # turn longer than the card says, which is the wrong direction for
            # a prohibition: it is a strictly better card, silently.
            raise DslError(
                f"{where}: unknown lock_life_total duration {duration!r} "
                f"(implemented: {sorted(LIFE_LOCK_DURATIONS)})"
            )
        if "amount" in effect:
            # "Your life total can't change" has no magnitude. A number here
            # would read as a shield of that size and be ignored entirely.
            raise DslError(
                f"{where}: lock_life_total takes no 'amount' -- it forbids the "
                f"change rather than sizing it"
            )
    if op == "discard" and effect.get("whole_hand"):
        # "Each player discards their hand." The size is per player and cannot
        # also be an `amount`, which is evaluated once for everybody -- two
        # answers to one question, and the `amount` would silently win for the
        # players it was not computed from.
        if "amount" in effect:
            raise DslError(
                f"{where}: 'whole_hand' is the whole hand, so it replaces 'amount' "
                f"rather than joining it"
            )
        if effect.get("up_to"):
            raise DslError(f"{where}: a whole-hand discard is not optional")

    if op == "damage" and "defender_of" in effect:
        # "…the player or planeswalker **it's** attacking" -- one creature,
        # named by a selector. Anything else would read as a pool and quietly
        # aim at the first attacker found.
        if not isinstance(effect["defender_of"], Mapping):
            raise DslError(
                f"{where}.defender_of: a selector naming the attacking creature, "
                f"e.g. {{'zone': 'battlefield', 'self_only': true}}"
            )
        validate_selector(effect["defender_of"], f"{where}.defender_of")
    if op == "damage" and "excess_to" in effect:
        # "Excess damage is dealt to that creature's controller instead."
        # Only meaningful on the single-target form: `objects` is a pool and
        # there is no one creature whose controller the spill belongs to.
        if effect["excess_to"] != "controller":
            raise DslError(
                f"{where}.excess_to: the only spelling any printed card uses is "
                f"'controller', got {effect['excess_to']!r}"
            )
        if "target" not in effect:
            raise DslError(
                f"{where}: 'excess_to' needs a single 'target' -- a pool of objects has "
                f"no one controller for the excess to reach"
            )
    if op == "damage" and "divided" in effect:
        # "…deals 4 damage divided as you choose among any number of target
        # creatures" (601.2d). `divided` names the one target spec whose objects
        # share the amount, and is the whole of who is dealt damage: a second
        # recipient beside it would take the full amount, which no printed card
        # says. Where the op may sit is `loader._check_division_homes`'s.
        if not isinstance(effect["divided"], str) or not effect["divided"]:
            raise DslError(
                f"{where}.divided: the id of the target spec whose objects share the "
                f"damage, e.g. 't1'"
            )
        others = sorted({"objects", "player", "target", "defender_of"} & set(effect))
        if others:
            raise DslError(
                f"{where}: divided damage goes only to the targets 'divided' names; "
                f"drop {others}"
            )
        if _reads_announced_x(effect.get("amount")):
            # "Any number of targets" is declared before X is announced on this
            # engine's cast line, so a division of X could be asked over more
            # targets than X -- refused rather than half-honoured.
            raise DslError(
                f"{where}: a divided amount may not read the announced X"
            )

    if op == "cast_from_hand":
        # The selector is what may be picked, and it is the whole of the printed
        # restriction -- "an instant or sorcery spell with mana value X or less".
        # A misspelled key would widen it silently into "any card in your hand",
        # which is a strictly better card than the one printed and exactly the
        # failure this validation layer exists to refuse.
        selector = effect.get("selector")
        if selector is not None:
            if not isinstance(selector, Mapping):
                raise DslError(f"{where}: cast_from_hand's 'selector' must be a mapping")
            validate_selector(selector, f"{where}.selector")
        if "player" in effect:
            _validate_player_spec(effect["player"], f"{where}.player", target_kinds)
        if "zones" in effect:
            # Kaya the Inexorable's emblem: hand, graveyard, and cards you own
            # in exile. The three zones a player keeps cards of their own in and
            # can cast out of; the library top is `look_at_top`'s `cast_free`.
            zones = effect["zones"]
            allowed = ("hand", "graveyard", "exile")
            if (
                not isinstance(zones, list)
                or not zones
                or any(z not in allowed for z in zones)
                or len(set(zones)) != len(zones)
            ):
                raise DslError(
                    f"{where}: cast_from_hand's 'zones' is a non-empty list drawn "
                    f"from {list(allowed)}, got {zones!r}"
                )
        if "objects" in effect:
            # The Ur-Sphinx: a named pool (the cards milled this way) instead of
            # the caster's own zones. The two are different pools, so writing
            # both would leave one of them silently ignored.
            if "zones" in effect:
                raise DslError(f"{where}: cast_from_hand takes 'objects' or 'zones', not both")
            if not isinstance(effect["objects"], Mapping):
                raise DslError(f"{where}: cast_from_hand's 'objects' must be a selector mapping")
            validate_selector(effect["objects"], f"{where}.objects")
        if "per_owner" in effect:
            # "For each player, … a card that player milled" splits a named
            # pool; over the caster's own zones every card has one owner and
            # the key would say nothing.
            if not isinstance(effect["per_owner"], bool):
                raise DslError(f"{where}: cast_from_hand's 'per_owner' must be a boolean")
            if effect["per_owner"] and "objects" not in effect:
                raise DslError(f"{where}: cast_from_hand's 'per_owner' needs 'objects'")

    if op == "animate":
        # "Becomes a 4/4 creature" is the whole point, and an animation with no
        # size would silently make a 0/0 that dies to state-based actions the
        # moment it arrives.
        #
        # The one exception is an animation into a *non-creature*, which has
        # no size to name: "target creature becomes a Treasure artifact ... and
        # loses all other card types" (Vraska, Betrayal's Sting). Its base
        # power and toughness are left alone. Both keys or neither, always.
        sized = ("power" in effect, "toughness" in effect)
        becomes_creature = "Creature" in (effect.get("types") or ("Creature",))
        if sized != (True, True) and (becomes_creature or any(sized)):
            raise DslError(
                f"{where}: animate needs 'power' and 'toughness' (only an "
                f"animation into a non-creature may leave out both)"
            )
        keep_colors = effect.get("keep_colors", False)
        if not isinstance(keep_colors, bool):
            raise DslError(f"{where}: animate's 'keep_colors' is true or false")
        if keep_colors and not effect.get("exact", False):
            # A non-exact animation already keeps the colours and adds its own.
            raise DslError(
                f"{where}: 'keep_colors' means anything only on an exact animation "
                f"-- a non-exact one adds its colours to the permanent's own"
            )
        if keep_colors and effect.get("colors"):
            raise DslError(
                f"{where}: 'keep_colors' and 'colors' contradict each other -- "
                f"the colours are either left as they are or replaced"
            )
        for word in effect.get("your_turn_keywords", ()) or ():
            if word not in KNOWN_KEYWORDS:
                raise DslError(
                    f"{where}.your_turn_keywords: unknown keyword {word!r}"
                )
        for t in effect.get("types", ()) or ():
            if t not in KNOWN_TYPES:
                raise DslError(f"{where}: unknown card type {t!r}")
        for k in effect.get("keywords", ()) or ():
            if k not in KNOWN_KEYWORDS:
                raise DslError(f"{where}: unknown keyword {k!r}")
        refuse_numbered_grant(effect.get("keywords"), f"{where}.keywords")
        refuse_numbered_grant(effect.get("your_turn_keywords"), f"{where}.your_turn_keywords")
        for c in effect.get("colors", ()) or ():
            if c not in KNOWN_COLORS:
                raise DslError(f"{where}: unknown colour {c!r}")
        # Oko's "becomes a green Elk creature with base power and toughness
        # 3/3" prints no duration. Enumerated rather than truthy for the reason
        # `gain_control`'s is: a misspelt "until_end_of_turn" read as anything
        # but itself is a permanent animation, the strictly better card.
        # Nissa, Vital Force's land stays a 5/5 "until your next turn".
        duration = effect.get("duration", "until_end_of_turn")
        # Spelled out rather than built from `CONTROL_DURATIONS`: that list
        # also has "end_of_your_next_turn", which no animation implements.
        allowed = ("permanent", "until_end_of_turn", "until_your_next_turn")
        if duration not in allowed:
            raise DslError(
                f"{where}: animate's 'duration' is one of {list(allowed)}, "
                f"got {duration!r}"
            )
        if duration == "permanent" and effect.get("your_turn_keywords"):
            raise DslError(
                f"{where}: your_turn_keywords rides a timed animation only -- "
                f"no printed indefinite animation carries one"
            )
        if not isinstance(effect.get("exact", False), bool):
            raise DslError(
                f"{where}: animate's 'exact' is true or false -- whether the "
                f"colours, card types and creature types named replace the "
                f"permanent's own ('becomes a green Elk creature') rather than "
                f"adding to them ('it's still a land')"
            )
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
        if not isinstance(effect.get("your_turn", False), bool):
            raise DslError(
                f"{where}: delay's 'your_turn' is a flag saying whether the step "
                f"must be its controller's own -- 'at the beginning of *your* "
                f"next end step' -- so it takes true or false, not "
                f"{effect.get('your_turn')!r}"
            )
        _refuse_targets_inside_a_delay(effect.get("effects") or (), f"{where}.effects")
    if op == "change_text":
        # The word being written in. Without it the op has nothing to say and
        # would silently do nothing, which for a text change is invisible --
        # the creature keeps its printed line and the card looks like it fizzled.
        replacement = effect.get("to")
        if not isinstance(replacement, str) or not replacement:
            raise DslError(
                f"{where}: change_text needs a 'to' naming the creature type "
                f"written in ('...with Vampire'), got {replacement!r}"
            )
        # There is no closed list of creature types to check against -- creature
        # is the *default* class in `SUBTYPE_CLASS`, which enumerates only the
        # non-creature subtypes -- so the check that exists is the negative one:
        # a subtype the engine knows belongs to some other class is certainly
        # not a creature type. "Replace all instances of Goblin with Equipment"
        # would otherwise load and put a nonsense word on the type line.
        if SUBTYPE_CLASS.get(replacement) is not None:
            raise DslError(
                f"{where}: change_text 'to' must be a creature type; "
                f"{replacement!r} is a {SUBTYPE_CLASS[replacement]} subtype"
            )
        # Only the creature-type word class is built. The other two the family
        # prints are refused by name rather than accepted and ignored: a colour
        # word (Glamerdye, Mind Bend, and eight more) reaches `colors` filters,
        # protection qualities and mana production, and a basic land type
        # (Magical Hack, Whim of Volrath) reaches landwalk keywords and mana
        # abilities. Each is a surface of its own, and a card written against a
        # key this op ignores would print the words and change nothing.
        word_class = str(effect.get("word_class", "creature_type"))
        if word_class != "creature_type":
            raise DslError(
                f"{where}: change_text only implements 'creature_type'; "
                f"{word_class!r} is not modelled (see docs/unsupported-cards.md)"
            )
        # "…with **another**" -- Artificial Evolution asks for the replacement
        # too. Refused rather than half-built: that card targets a *spell or*
        # permanent, which no selector can say, so accepting the key here would
        # buy a second prompt and still no card.
        if replacement == "choose":
            raise DslError(
                f"{where}: change_text's 'to' is a literal creature type; "
                f"choosing the replacement as well is not modelled"
            )
    if op == "delayed_trigger":
        _validate_delayed_trigger(effect, where)

    # "Target opponent gets an emblem" and "you get an emblem" differ by one
    # player spec, and a default would silently pick one of them. Which emblem is
    # checked against the card's own `emblems` by `_check_emblem_references`.
    if op == "emblem":
        if "player" not in effect:
            raise DslError(f"{where}: emblem needs 'player' -- who gets it")
        if "emblem" not in effect:
            raise DslError(
                f"{where}: emblem needs 'emblem' -- the index into the card's own 'emblems'"
            )

    # A grant naming an ability the card does not have is a silent no-op: the
    # index defaults to 0 and every miss lands on the first grantable, or on
    # nothing at all. Both spellings are accepted by the op, so both are checked.
    if op == "grant_ability" and "ability" not in effect and "ability_index" not in effect:
        raise DslError(
            f"{where}: grant_ability needs 'ability' -- the index into the "
            f"card's own 'grantable_abilities'"
        )

    # A loop with no body is a card that does nothing, and the whole point of
    # this op is the body -- without it the printed "each opponent sacrifices"
    # silently becomes "nobody does".
    if op == "for_each_player" and not effect.get("effects"):
        raise DslError(f"{where}: for_each_player needs 'effects' to run per player")

    # "Choose one that hasn't been chosen" belongs to a permanent's repeated
    # ability, not to a spell. A spell's top-level modes are picked at *cast*
    # time (601.2b, `Game._ask_modes`), which never sees this filter -- so the
    # spent modes would still be offered and the flag written for nothing. And
    # the clause is meaningless there anyway: a spell is a new object each cast,
    # with no record of the last one.
    # Two lifetimes and nothing else: `true` is "hasn't been chosen" for the
    # object's life, `"turn"` is "…this turn". Any other truthy value would be
    # read as the life-long one and run a card out of modes for ever.
    if op == "choose_mode" and effect.get("once_each") not in (None, False, True, "turn"):
        raise DslError(
            f"{where}: 'once_each' is true (\"hasn't been chosen\") or \"turn\" "
            f"(\"hasn't been chosen this turn\"), got {effect.get('once_each')!r}"
        )
    if op == "choose_mode" and effect.get("once_each") and ".spell_effects[" in where:
        raise DslError(
            f"{where}: 'once_each' is for a permanent's repeated modal ability; "
            f"a spell chooses its modes as it is cast and remembers nothing"
        )

    for key in ("then", "else", "effects"):
        if key in effect:
            for i, sub in enumerate(effect[key] or []):
                _validate_effect(sub, f"{where}.{key}[{i}]", target_kinds)
    for i, mode in enumerate(effect.get("modes", []) or []):
        if not isinstance(mode, Mapping):
            raise DslError(f"{where}.modes[{i}]: must be an object")
        for j, sub in enumerate(mode.get("effects", []) or []):
            _validate_effect(sub, f"{where}.modes[{i}].effects[{j}]", target_kinds)
