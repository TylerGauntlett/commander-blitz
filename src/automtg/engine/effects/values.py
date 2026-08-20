"""The value-expression DSL.

Any numeric field in a card definition may be a plain integer or one of these
forms::

    {"const": 3}                      a literal
    {"x": true}                       the X chosen when the spell was cast
    {"count": {selector}}             how many objects match
    {"power_of": {"target": "t1"}}    a characteristic of an object or snapshot
    {"life_of": "you"}                a player quantity
    {"cards_drawn_this_turn": "you"}  a per-turn tally of an event
    {"creatures_died_this_turn": "all"}   the rest of that ledger: morbid,
    {"attacked_this_turn": "you"}          raid, bloodthirst, spectacle,
    {"attackers_this_turn": "you"}         storm and gravestorm -- and how
    {"spells_cast_this_turn": "all"}       many creatures attacked, not seats
    {"permanents_entered_this_turn":  WHICH permanents entered the battlefield
        {"controller": "you",           this turn, by subtype and by
         "subtypes": ["Human"]}}        controller-at-entry
    {"min_life_of": "each_opponent"}  the lowest of them, one player at a time
    {"max_count_of": {"player": …,    how many objects the player with the most
                      "objects": …}}    of them has -- one player at a time
    {"sum": [a, b, ...]}              arithmetic
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..characteristics import chars, min_count, min_life
from ..enums import KEYWORD_COUNTERS
from ..errors import DslError
from ..objects import PLUS_ONE
from .context import EffectContext

#: Every key that may appear at the top level of a value expression.
VALUE_KEYS = frozenset(
    {
        "const",
        "x",
        "count",
        # "…if AN OPPONENT controls more lands than you."  `count` resolves one
        # merged pool, and `controller: "opponent"` means every opponent at once,
        # so it SUMS across the table -- the printed card in a duel and a
        # strictly better one at a pod, where three opponents on two lands each
        # total six and beat your five.  These two ask about ONE player at a time
        # and then aggregate: `max_count_of` is the existential ("an opponent
        # controls more…"), `min_count_of` the universal ("each opponent
        # controls more…").  Exactly the `life_of` / `min_life_of` split above,
        # for exactly the reason recorded there.
        "max_count_of",
        "min_count_of",
        "power_of",
        "toughness_of",
        "mana_value_of",
        "life_of",
        # "…unless an opponent has 10 or less life."  `life_of` SUMS over its
        # player spec, which is the printed card in a duel and a different card
        # at a pod: three opponents at 4 life sum to 12, so a summing test would
        # say nobody is low against a table that is nearly dead.  These two ask
        # about ONE player -- `min_life_of` is the existential ("an opponent
        # has…"), `max_life_of` the universal ("each opponent has…").
        "min_life_of",
        "max_life_of",
        "cards_in_hand",
        # "…for each card you've drawn this turn."  A tally of an event, not a
        # count of objects, and the two stop agreeing the moment anything is
        # played, discarded, or drawn on somebody else's turn.
        "cards_drawn_this_turn",
        # The rest of the per-turn ledger (`structs.TurnLedger`).  All six are
        # values rather than condition leaves, so morbid is an ordinary `cmp`
        # against 1 and nothing new had to be added to the condition language:
        # "did it happen" and "how many times" are the same question asked with
        # a different threshold, and storm needs the number anyway.
        "creatures_died_this_turn",
        "attacked_this_turn",
        # "…if you attacked with **three or more creatures** this turn" --
        # Windbrisk Heights. How many *creatures*, where `attacked_this_turn`
        # above is how many *players*: on a board where you swung with three,
        # that one is 1 and can never reach the printed threshold, and relaxing
        # the comparison to `>= 1` turns a hideaway land into a raid land.
        # Counted off the ledger's oids rather than with `{"count": {...}}` over
        # the battlefield, because an attacker that died in combat still
        # attacked and the board has forgotten it.
        "attackers_this_turn",
        # "…if another **Human** entered the battlefield under **your control**
        # this turn" -- Éowyn, Shieldmaiden. The one ledger read that takes a
        # filter rather than a player spec, because the printed sentence asks
        # *which* permanents entered and not how many did: a bare per-player
        # tally would fire the trigger off a land drop.
        "permanents_entered_this_turn",
        "damage_taken_this_turn",
        "life_lost_this_turn",
        "spells_cast_this_turn",
        "cards_to_graveyard_this_turn",
        # "…if this is the second time this ability has resolved this turn."
        # Keyed by ability rather than by player, and counting the resolution in
        # progress, so it is the one ledger tally read off the effect context
        # rather than off the ledger -- see `structs.TurnLedger`.
        "resolutions_this_turn",
        "creatures_you_control",
        "lands_you_control",
        "sum",
        "minus",
        "times",
        "max",
        "min",
        "loop_value",
        "binding",
        "counters_on",
        # "…if it had no -1/-1 counters on it" -- persist and undying. Not
        # `counters_on`, which reads a live object: this asks about a creature
        # that has just died, and `reset_permanent_state` emptied its counters
        # on the way to the graveyard. Answered from the dies trigger's
        # `had_counters` binding, snapshotted before the wipe.
        "counters_had",
        # "…create a number of Treasure tokens equal to **its power**" on a
        # `dies` trigger (Goldvein Hydra). `power_of {"self": true}` cannot
        # answer it: the object is a graveyard card by then, so `chars()` gives
        # the printed line and a 0/0 Hydra reads 0. The value comes off the
        # death event, which snapshotted it on the way out -- the explicit-LKI
        # pattern `snapshot` established, in the one place an op cannot reach,
        # because an op runs at resolution and the creature has already left.
        "power_had",
        "toughness_had",
        # "…for each basic land type among lands you control" (domain), and
        # "three or more creatures with different powers" (coven). A count of
        # *distinct values* over a pool, which no other leaf can be: `count`
        # counts objects, so five Forests are five and not one.
        "distinct",
        # "…the number of green mana symbols in the mana costs of permanents you
        # control" -- chroma. The one question nothing else asks: every other
        # reader of a cost wants its total or the set of colours in it, and this
        # wants how many times one symbol appears.
        "mana_symbols",
        # "…where X is the number of colors of mana spent to cast this spell" --
        # sunburst and converge. A fact about the *payment*, not the cost: a
        # Sunburst artifact cast for {4} off five different lands enters with
        # five counters, and its printed cost has no coloured pip at all.
        "colors_of_mana_spent",
        #: "…the number of colors in your commanders' color identity". A deck
        #: fact rather than a board one, so it is the same number wherever the
        #: commander currently is.
        "commander_color_identity",
        # "…for each creature sacrificed this way" / "copy it for each time you
        # paid" -- casualty and replicate. How many times the card's additional
        # cost was paid, which nothing else records: the sacrificed creatures are
        # in a graveyard among everything else that died, and the mana is gone.
        "additional_paid",
    }
)

#: What ``{"distinct": {"of": …}}`` may count. Two entries, and both have a card
#: behind them: domain counts basic land types, coven counts powers. A third
#: would be vocabulary with nothing printed asking for it, and a misspelling has
#: to be a load error rather than a silent zero.
DISTINCT_OF = ("power", "basic_land_type")

#: Rule 305.6. The five basic land types, which are the whole of domain.
BASIC_LAND_TYPES = frozenset({"Plains", "Island", "Swamp", "Mountain", "Forest"})

#: The two per-player counting leaves, named together because they are validated
#: together and neither is any use without the other: a card says "an opponent
#: controls more X than you" or "each opponent does", and those are the same
#: measurement read off opposite ends.
PER_PLAYER_COUNT_KEYS = frozenset({"max_count_of", "min_count_of"})

#: Player specs a per-player count may name -- the same list ``min_life_of``
#: allows inside a static, and deliberately the same on both sides. The leaf is
#: reachable from an ``if``, from a trigger's intervening-``if``, from an
#: activated ability's ``condition`` and from a static's ``condition``, and a
#: spec legal in one of those and not the others would make the same printed
#: sentence sayable on one card and not on the next.
PER_PLAYER_COUNT_SPECS = frozenset({"you", "opponent", "each_opponent", "each_player", "all"})

#: The binding a per-player count scopes its pool with.
#:
#: The evaluator injects it rather than asking the card author for it, the way
#: ``for_each_player`` injects ``each_player`` -- a condition is not inside a
#: loop, so a card written here has no binding to name. Reserved: an author who
#: writes ``controller`` or ``player`` inside ``objects`` gets a load error
#: rather than a clause this quietly overwrites.
COUNTED_PLAYER = "counted_player"


def evaluate_value(ctx: EffectContext, expr: Any) -> int:
    """Evaluate a value expression to an integer."""
    if expr is None:
        return 0
    if isinstance(expr, bool):
        return int(expr)
    if isinstance(expr, int):
        return expr
    if isinstance(expr, str):
        # "x" and "all" are accepted as bare strings for readability in card files.
        if expr == "x":
            return ctx.x
        raise DslError(f"unparsable value expression {expr!r}")
    if not isinstance(expr, Mapping):
        raise DslError(f"unparsable value expression {expr!r}")

    if "const" in expr:
        return int(expr["const"])
    if "x" in expr:
        return ctx.x
    if "loop_value" in expr:
        return int(ctx.loop_value or 0)
    if "binding" in expr:
        value = ctx.bindings.get(str(expr["binding"]))
        return int(value) if isinstance(value, int) else 0
    if "count" in expr:
        from .selectors import resolve_pool

        return len(resolve_pool(ctx, expr["count"]))
    if "max_count_of" in expr:
        # "…if an opponent controls more lands than you." The existential, so 0
        # over nobody: no land count of yours is below zero, and the clause has
        # to be false at a table with no opponents left.
        return max(_counts_per_player(ctx, expr["max_count_of"]), default=0)
    if "min_count_of" in expr:
        # "…if each opponent controls more lands than you." The universal, so
        # unreachably large over nobody -- see `NO_PLAYERS_COUNT`.
        return min_count(_counts_per_player(ctx, expr["min_count_of"]))
    if "counters_on" in expr:
        # How many counters of a kind sit on an object -- which is what "double
        # the number of +1/+1 counters on this creature" needs, and the one
        # quantity the value language could not previously reach.
        spec = expr["counters_on"]
        kind = str(spec.get("counter", PLUS_ONE))
        from .selectors import resolve_pool

        pool = resolve_pool(ctx, spec.get("objects") or {"self_only": True})
        return sum(ctx.state.objects[oid].counter(kind) for oid in pool if oid in ctx.state.objects)
    if "additional_paid" in expr:
        # Casualty and replicate. Read off the object being cast, which is what
        # a "when you cast this spell" trigger is sourced to.
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
        return obj.cast_additional if obj is not None else 0
    if "colors_of_mana_spent" in expr:
        # Sunburst and converge. Read off the object that was cast, which for a
        # spell's own `spell_effects` is `source_oid` and for an artifact's
        # enters trigger is the permanent -- the same object either way, because
        # an oid survives the zone change onto the battlefield.
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
        return len(obj.colors_spent) if obj is not None else 0
    if "mana_symbols" in expr:
        # Chroma. Read off the **printed** cost, which is what the keyword says
        # and also what makes it safe inside a static: a mana cost is a pipeline
        # input, and no layer can change one.
        spec = expr["mana_symbols"]
        from .selectors import resolve_pool

        color = str(spec.get("of", ""))
        return sum(
            ctx.state.card_of(obj).mana_cost.symbols_of(color)
            for oid in resolve_pool(ctx, spec.get("objects") or {})
            if (obj := ctx.state.objects.get(oid)) is not None
        )
    if "distinct" in expr:
        # Domain and coven: how many *different* values a pool holds, not how
        # many objects are in it. `count` cannot say it in either direction --
        # five Forests are one basic land type and five objects, and three
        # creatures that are all 2/2 are three objects and one power.
        #
        # Both readings are of **derived** characteristics, deliberately: an
        # anthem changes who counts for coven, and "all lands are Islands"
        # changes what counts for domain. That is also why this leaf is not in
        # the static condition language -- a static reading it would depend on
        # another static's output, which is the one thing layers-lite forbids.
        spec = expr["distinct"]
        from .selectors import resolve_pool

        pool = resolve_pool(ctx, spec.get("objects") or {})
        of = str(spec.get("of", "power"))
        if of == "power":
            return len({chars(ctx.state, oid).power for oid in pool})
        found: set[str] = set()
        for oid in pool:
            found |= BASIC_LAND_TYPES & chars(ctx.state, oid).subtypes
        return len(found)
    if "creatures_you_control" in expr:
        return len(ctx.state.creatures(ctx.controller))
    if "lands_you_control" in expr:
        return sum(
            1
            for o in ctx.state.battlefield_objects(ctx.controller)
            if "Land" in chars(ctx.state, o.oid).types
        )
    if "power_of" in expr:
        return _characteristic(ctx, expr["power_of"], "power")
    if "toughness_of" in expr:
        return _characteristic(ctx, expr["toughness_of"], "toughness")
    if "mana_value_of" in expr:
        return _characteristic(ctx, expr["mana_value_of"], "mana_value")
    if "life_of" in expr:
        pids = _players(ctx, expr["life_of"])
        return sum(ctx.state.players[p].life for p in pids)
    if "commander_color_identity" in expr:
        # "Pay life equal to the number of colors in your commanders' color
        # identity." War Room. The union across a player's commanders, so
        # partners count once between them for a colour they share -- which is
        # what "your commanders' color identity" means, singular.
        #
        # Read off the **printed** identity rather than derived colours: colour
        # identity is a deck-construction fact fixed by the card, and it is the
        # same number whether the commander is in the command zone, on the
        # battlefield, or in a graveyard.
        colors: set[str] = set()
        for pid in _players(ctx, expr["commander_color_identity"]):
            for oid in ctx.state.commanders_of(pid):
                obj = ctx.state.objects.get(oid)
                if obj is not None:
                    colors |= set(ctx.state.card_of(obj).color_identity)
        return len(colors)
    if "min_life_of" in expr:
        pids = _players(ctx, expr["min_life_of"])
        return min_life([ctx.state.players[p].life for p in pids])
    if "max_life_of" in expr:
        pids = _players(ctx, expr["max_life_of"])
        return max([ctx.state.players[p].life for p in pids], default=0)
    if "cards_in_hand" in expr:
        pids = _players(ctx, expr["cards_in_hand"])
        return sum(len(ctx.state.players[p].hand) for p in pids)
    if "counters_had" in expr:
        # The kind, as a bare string: {"counters_had": "-1/-1"}.
        kind = str(expr["counters_had"])
        had = ctx.bindings.get("had_counters")
        return int(had.get(kind, 0)) if isinstance(had, Mapping) else 0
    if "power_had" in expr:
        # No argument: it is always "the creature this trigger is about", the
        # only object the event snapshotted. A trigger that never fired binds
        # nothing and reads 0, which is the same answer `counters_had` gives.
        return int(ctx.bindings.get("had_power") or 0)
    if "toughness_had" in expr:
        return int(ctx.bindings.get("had_toughness") or 0)
    if "cards_drawn_this_turn" in expr:
        pids = _players(ctx, expr["cards_drawn_this_turn"])
        return sum(ctx.state.cards_drawn_this_turn.get(p, 0) for p in pids)
    if "resolutions_this_turn" in expr:
        # "If this is the second time this ability has resolved this turn."
        # Read off the context rather than the ledger: only `resolve_top` knows
        # which ability is resolving, and the count has to include this one.
        return ctx.resolutions
    ledger = ctx.state.turn_ledger
    if "creatures_died_this_turn" in expr:
        # Keyed by who controlled the creature, so `"all"` is morbid's "a
        # creature died this turn" and `"you"` is "a creature you controlled".
        pids = _players(ctx, expr["creatures_died_this_turn"])
        return sum(ledger.creatures_died.get(p, 0) for p in pids)
    if "attacked_this_turn" in expr:
        # How many of the named players attacked, which is 0 or 1 for raid's
        # `"you"` and a headcount for "if two opponents attacked this turn".
        pids = _players(ctx, expr["attacked_this_turn"])
        return sum(1 for p in pids if p in ledger.attacked)
    if "attackers_this_turn" in expr:
        # How many *creatures* the named players attacked with -- the clause
        # above counts seats. A union rather than a sum of lengths: the same
        # creature can be declared under two controllers across two combats of
        # one turn (`gain_control` between them), and "you attacked with three
        # or more creatures" counts creatures, not declarations.
        oids: set[int] = set()
        for p in _players(ctx, expr["attackers_this_turn"]):
            oids |= ledger.creatures_attacked.get(p, set())
        return len(oids)
    if "permanents_entered_this_turn" in expr:
        # How many permanents matching the filter have entered the battlefield
        # this turn. Read off the ledger's snapshots rather than the board,
        # which is the whole point: `{"count": {"zone": "battlefield", …}}` is
        # true of a Human that has been there since turn three and false of one
        # that entered this turn and died, so it is wrong in both directions.
        spec = expr["permanents_entered_this_turn"]
        controllers = _players(ctx, spec.get("controller"))
        # "*Another* Human." Éowyn is herself a Human and may well have entered
        # this turn, which is the case the word exists to exclude -- and the
        # entry is matched by oid, so it also excludes her own arrival rather
        # than merely a permanent that looks like her.
        excluded = ctx.source_oid if spec.get("exclude_self") else None
        return sum(
            1
            for entry in ledger.permanents_entered
            if entry.oid != excluded
            and entry.matches(
                controllers=controllers,
                types=spec.get("types") or (),
                subtypes=spec.get("subtypes") or (),
                colors=spec.get("colors") or (),
            )
        )
    if "damage_taken_this_turn" in expr:
        pids = _players(ctx, expr["damage_taken_this_turn"])
        return sum(ledger.damage_taken.get(p, 0) for p in pids)
    if "life_lost_this_turn" in expr:
        pids = _players(ctx, expr["life_lost_this_turn"])
        return sum(ledger.life_lost.get(p, 0) for p in pids)
    if "spells_cast_this_turn" in expr:
        pids = _players(ctx, expr["spells_cast_this_turn"])
        return sum(ledger.spells_cast.get(p, 0) for p in pids)
    if "cards_to_graveyard_this_turn" in expr:
        # Every graveyard, so it takes no player spec: gravestorm counts cards
        # put into *a* graveyard, not into yours.
        return ledger.cards_to_graveyard
    if "sum" in expr:
        return sum(evaluate_value(ctx, e) for e in expr["sum"])
    if "minus" in expr:
        parts = [evaluate_value(ctx, e) for e in expr["minus"]]
        result = parts[0] if parts else 0
        for p in parts[1:]:
            result -= p
        return result
    if "times" in expr:
        result = 1
        for e in expr["times"]:
            result *= evaluate_value(ctx, e)
        return result
    if "max" in expr:
        return max((evaluate_value(ctx, e) for e in expr["max"]), default=0)
    if "min" in expr:
        return min((evaluate_value(ctx, e) for e in expr["min"]), default=0)

    raise DslError(f"unknown value expression {sorted(expr)}")


def _players(ctx: EffectContext, spec: Any) -> list[int]:
    from .selectors import select_players

    return select_players(ctx, spec)


def _counts_per_player(ctx: EffectContext, spec: Any) -> list[int]:
    """How many objects match ``spec["objects"]``, once per named player.

    One ``resolve_pool`` per player with the pool scoped to that player alone,
    which is the whole content of the leaf: the selector language can filter to
    "not you" (``controller: "opponent"``) but not to "them, separately", so a
    single pool is the sum and no comparison can get at the individual totals.

    The scope is injected here rather than written on the card, because the two
    zone families take it in different words -- the same split
    ``validate_selector`` already spells out. A battlefield or stack pool is
    *shared*, so a player is a ``controller`` filter over it; a hand, library,
    graveyard or exile *belongs* to somebody, so a player chooses which list to
    walk. Writing one where the other is meant is silently a different question,
    which is why neither is left to the card.
    """
    if not isinstance(spec, Mapping):
        raise DslError(f"unparsable per-player count {spec!r}")
    objects = spec.get("objects") or {}
    zone = str(objects.get("zone", "battlefield"))
    shared_zone = zone in ("battlefield", "stack")

    from .selectors import resolve_pool

    previous = ctx.bindings.get(COUNTED_PLAYER)
    counts: list[int] = []
    try:
        for pid in _players(ctx, spec.get("player", "each_opponent")):
            ctx.bindings[COUNTED_PLAYER] = pid
            scoped = (
                {**objects, "controller": {"binding": COUNTED_PLAYER}}
                if shared_zone
                else {**objects, "player": pid}
            )
            counts.append(len(resolve_pool(ctx, scoped)))
    finally:
        if previous is None:
            ctx.bindings.pop(COUNTED_PLAYER, None)
        else:
            ctx.bindings[COUNTED_PLAYER] = previous
    return counts


def _characteristic(ctx: EffectContext, ref: Any, which: str) -> int:
    """Read power/toughness/mana value from a target, binding or snapshot."""
    if isinstance(ref, Mapping) and "var" in ref:
        snap = ctx.bindings.get(str(ref["var"]))
        if isinstance(snap, Mapping):
            return int(snap.get(which, 0))
        if isinstance(snap, int):
            return _from_oid(ctx, snap, which)
        return 0
    if isinstance(ref, Mapping) and "target" in ref:
        oids = ctx.target_oids(str(ref["target"]))
        return sum(_from_oid(ctx, oid, which) for oid in oids)
    if isinstance(ref, Mapping) and "binding" in ref:
        value = ctx.bindings.get(str(ref["binding"]))
        if isinstance(value, Mapping):
            return int(value.get(which, 0))
        if isinstance(value, int):
            return _from_oid(ctx, value, which)
        return 0
    if isinstance(ref, Mapping) and "self" in ref:
        return _from_oid(ctx, ctx.source_oid, which) if ctx.source_oid else 0
    if isinstance(ref, int):
        return _from_oid(ctx, ref, which)
    raise DslError(f"unparsable characteristic reference {ref!r}")


def _from_oid(ctx: EffectContext, oid: int | None, which: str) -> int:
    if oid is None:
        return 0
    obj = ctx.state.objects.get(oid)
    if obj is None:
        return 0
    if which == "mana_value":
        # "…except it's a white Zombie Angel with **no mana cost**." An embalm
        # token's def_id is the original card's, so without this it would still
        # report the printed cost's mana value.
        if obj.copy_overrides and obj.copy_overrides.get("no_mana_cost"):
            return 0
        return ctx.state.card_of(obj).mana_value
    c = chars(ctx.state, oid)
    return c.power if which == "power" else c.toughness


def validate_mana_symbols(spec: Any, where: str, *, validate_objects: Any = None) -> None:
    """Shared by the effect-side and static-side value validators.

    Both languages accept ``mana_symbols`` -- Primalcrux reads it in a `set_pt`
    static and the ability-word cards read it as an amount -- and a leaf added to
    one and not the other loads in a card that then quietly reads 0. They differ
    only in which filter language checks ``objects``, so that is the parameter.
    """
    if not isinstance(spec, Mapping):
        raise DslError(f"{where}: must be an object")
    unknown = set(spec) - {"of", "objects"}
    if unknown:
        raise DslError(f"{where}: unsupported keys {sorted(unknown)}")
    of = spec.get("of")
    if not isinstance(of, str) or of.upper() not in ("W", "U", "B", "R", "G"):
        # Defaulted or misspelled it would count nothing and read 0, which on
        # Primalcrux is a 0/0 that dies to state-based actions on arrival.
        raise DslError(f"{where}.of: must name a colour (W/U/B/R/G), got {of!r}")
    if not spec.get("objects"):
        # An empty selector is every permanent in the game, so chroma would
        # count an opponent's board as well as yours.
        raise DslError(f"{where}: needs 'objects' -- an empty selector is every permanent")
    if validate_objects is None:
        from .selectors import validate_selector as validate_objects
    validate_objects(spec["objects"], f"{where}.objects")


def validate_counter_kind(kind: Any, where: str) -> None:
    """Refuse a counter kind that *nearly* names a keyword (122.1c).

    A counter kind is a free string on purpose -- charge, quest, slumber, lore,
    age -- so there is no vocabulary to check it against, with one exception.
    A **keyword** counter grants its keyword (`enums.KEYWORD_COUNTERS`, read by
    the characteristics pipeline), and the match is exact: `"vigilance"` makes a
    vigilant creature and `"Vigilance"`, `"vigilance counter"` and
    `"first strike"` each make a tally nobody consults, on a card that loads
    clean and reads as printed.

    That is the one failure mode this whole validation pass exists to refuse,
    and unusually it is detectable, because the near miss normalises onto a
    keyword the engine implements. A kind that normalises onto nothing is left
    alone -- it is somebody's charge counter, and guessing at typos in an open
    vocabulary would refuse cards that are correct.

    Here rather than in the loader, where it was written, because
    ``counters_on`` names a kind in **both** value languages and the near-miss
    rule has to be the same one in each: a kind spelled ``"vigilance counter"``
    is an inert tally whether the reader is an effect or a static's magnitude.
    """
    if not isinstance(kind, str) or not kind:
        raise DslError(f"{where}: a counter kind must be a non-empty string, got {kind!r}")
    normalised = kind.strip().lower().replace("-", " ").replace("_", " ")
    for suffix in (" counters", " counter"):
        if normalised.endswith(suffix):
            normalised = normalised[: -len(suffix)]
    normalised = "_".join(normalised.split())
    if normalised != kind and normalised in KEYWORD_COUNTERS:
        raise DslError(
            f"{where}: write a keyword counter as the exact keyword name -- "
            f"{normalised!r}, not {kind!r}. A keyword counter grants its keyword "
            f"(122.1c) and the lookup is exact, so {kind!r} would be an inert tally"
        )


def validate_counters_on(spec: Any, where: str, *, validate_objects: Any = None) -> None:
    """Shared by the effect-side and static-side value validators.

    Both languages accept ``counters_on`` -- "double the number of +1/+1
    counters on this creature" is an amount, and "+1/+1 for each charge counter
    on this artifact" is a static's magnitude -- and they differ only in which
    filter language checks ``objects``, so that is the parameter. Same shape and
    same reason as :func:`validate_mana_symbols`.

    Three refusals, and each of them is a card that would otherwise load clean
    and read a plausible wrong number:

    ``counter`` is **required**. It defaults to ``+1/+1`` in the evaluator, so a
    Door of Destinies that forgot to say ``charge`` would be an anthem sized by
    a counter kind the artifact never receives -- permanently +0/+0.

    ``objects`` is **required**, for the reason chroma and domain require it: an
    empty selector is not "this permanent", it is every permanent the filter
    language defaults to. On the static side that is everything its controller
    has, so the anthem would silently sum charge counters across the board.

    The kind itself goes through :func:`validate_counter_kind`, so a keyword
    near-miss is refused here exactly as it is on ``add_counters``.
    """
    if not isinstance(spec, Mapping):
        raise DslError(f"{where}: must be an object")
    unknown = set(spec) - {"counter", "objects"}
    if unknown:
        raise DslError(f"{where}: unsupported keys {sorted(unknown)}")
    if "counter" not in spec:
        raise DslError(
            f"{where}: needs 'counter' -- the kind being counted, which defaults "
            f"to '{PLUS_ONE}' in the evaluator and so would read 0 for ever on a "
            f"permanent that carries some other kind"
        )
    validate_counter_kind(spec["counter"], f"{where}.counter")
    if not spec.get("objects"):
        raise DslError(
            f"{where}: needs 'objects' -- an empty selector is not "
            f"{{\"self_only\": true}}, it is every permanent the filter defaults to"
        )
    if validate_objects is None:
        from .selectors import validate_selector as validate_objects
    validate_objects(spec["objects"], f"{where}.objects")


def validate_per_player_count(spec: Any, where: str, *, validate_objects: Any = None) -> None:
    """Shared by the effect-side and static-side value validators.

    Both languages take the pair -- Knight of the White Orchid asks in a
    trigger's intervening-``if`` and Verge Rangers in a static's ``condition`` --
    and a leaf validated in one and not the other loads in a card that then
    quietly reads 0. Same shape and same reason as
    :func:`validate_mana_symbols`, so they differ only in which filter language
    checks ``objects``.
    """
    if not isinstance(spec, Mapping):
        raise DslError(f"{where}: must be an object")
    unknown = set(spec) - {"player", "objects"}
    if unknown:
        raise DslError(f"{where}: unsupported keys {sorted(unknown)}")
    who = spec.get("player")
    if not isinstance(who, str) or who not in PER_PLAYER_COUNT_SPECS:
        # Not defaulted. The whole point of the leaf is *which* players are
        # measured separately, and "each_opponent" and "each_player" are
        # different cards -- Knight of the White Orchid looks across the table
        # and a symmetric card includes you. A default would read identically in
        # the card file either way.
        raise DslError(
            f"{where}.player: must name one of {sorted(PER_PLAYER_COUNT_SPECS)}, got {who!r}"
        )
    objects = spec.get("objects")
    if not objects:
        # An empty selector is every permanent that player has, which is a
        # plausible-looking number and never the one printed: "more lands than
        # you" is about lands.
        raise DslError(f"{where}: needs 'objects' -- what is being counted")
    overridden = {"controller", "player"} & set(objects)
    if overridden:
        # The evaluator scopes the pool to one player itself, so a clause written
        # here would be overwritten -- and `controller: "opponent"` is precisely
        # the summing filter this leaf exists to replace, so a card carrying it
        # would look like it had asked for the pooled total and get something
        # else.
        raise DslError(
            f"{where}.objects: {sorted(overridden)} is injected per player; "
            f"say who in {where}.player instead"
        )
    if validate_objects is None:
        from .selectors import validate_selector as validate_objects
    validate_objects(objects, f"{where}.objects")


#: What ``{"permanents_entered_this_turn": {...}}`` may filter on. Every clause
#: is one the snapshot can honestly answer -- `EnteredPermanent` carries exactly
#: these characteristics, taken as the permanent arrived.
ENTERED_FILTER_KEYS = frozenset({"controller", "types", "subtypes", "colors", "exclude_self"})


def validate_entered_filter(spec: Any, where: str) -> None:
    """Load-time check of the enters-this-turn filter.

    Stricter than the selector language it is spelled after, in one place:
    ``controller`` is **required**. An omitted clause in a selector narrows
    nothing and the pool is usually still the printed one, but here the omission
    silently counts *the opponents' arrivals too* -- and every printed sentence
    of this shape says whose battlefield it means ("under your control"). A card
    that dropped the word would fire off the opponent's Human, which is a
    strictly better card and a plausible-looking one. ``"all"`` is how a future
    card says it really does mean anybody's.
    """
    if not isinstance(spec, Mapping):
        raise DslError(f"{where}: must be an object -- the filter on what entered")
    unknown = set(spec) - ENTERED_FILTER_KEYS
    if unknown:
        raise DslError(f"{where}: unsupported keys {sorted(unknown)}")
    from .selectors import PLAYER_SPEC_NAMES

    who = spec.get("controller")
    if not isinstance(who, str) or who not in PLAYER_SPEC_NAMES:
        raise DslError(
            f"{where}.controller: must name one of {sorted(PLAYER_SPEC_NAMES)} "
            f"-- 'under whose control' is part of the printed sentence, got {who!r}"
        )
    for key in ("types", "subtypes", "colors"):
        if key not in spec:
            continue
        names = spec[key]
        if not isinstance(names, (list, tuple)) or not names:
            # An empty list is not "no filter" written out: it reads as a clause
            # the author meant to fill in, and filtering on nothing counts every
            # land drop.
            raise DslError(f"{where}.{key}: takes a non-empty list of names, got {names!r}")
        if not all(isinstance(n, str) and n for n in names):
            raise DslError(f"{where}.{key}: every entry must be a name, got {names!r}")
    if "exclude_self" in spec and not isinstance(spec["exclude_self"], bool):
        # Truthiness would make `"false"` -- a non-empty string -- exclude the
        # source, quietly turning "a Human entered" into "another Human did".
        raise DslError(f"{where}.exclude_self: must be true or false")


def validate_value(expr: Any, where: str) -> None:
    """Load-time check that a value expression uses only known forms."""
    if expr is None or isinstance(expr, (int, bool)):
        return
    if isinstance(expr, str):
        if expr != "x":
            raise DslError(f"{where}: unparsable value {expr!r}")
        return
    if not isinstance(expr, Mapping):
        raise DslError(f"{where}: value must be an int or object, got {type(expr).__name__}")
    unknown = set(expr) - VALUE_KEYS
    if unknown:
        raise DslError(f"{where}: unknown value keys {sorted(unknown)}")
    for key in ("sum", "minus", "times", "max", "min"):
        if key in expr:
            if not isinstance(expr[key], list):
                raise DslError(f"{where}: {key} takes a list")
            for i, sub in enumerate(expr[key]):
                validate_value(sub, f"{where}.{key}[{i}]")
    if "count" in expr:
        from .selectors import validate_selector

        validate_selector(expr["count"], f"{where}.count")
    if "mana_symbols" in expr:
        validate_mana_symbols(expr["mana_symbols"], f"{where}.mana_symbols")
    if "counters_on" in expr:
        validate_counters_on(expr["counters_on"], f"{where}.counters_on")
    if "permanents_entered_this_turn" in expr:
        validate_entered_filter(
            expr["permanents_entered_this_turn"], f"{where}.permanents_entered_this_turn"
        )
    for key in PER_PLAYER_COUNT_KEYS & set(expr):
        validate_per_player_count(expr[key], f"{where}.{key}")
    if "distinct" in expr:
        from .selectors import validate_selector

        spec = expr["distinct"]
        if not isinstance(spec, Mapping):
            raise DslError(f"{where}.distinct: must be an object")
        unknown = set(spec) - {"of", "objects"}
        if unknown:
            raise DslError(f"{where}.distinct: unsupported keys {sorted(unknown)}")
        of = spec.get("of")
        if of not in DISTINCT_OF:
            # Defaulted or misspelled it would count powers when the card meant
            # land types, which is a plausible-looking number on every board.
            raise DslError(
                f"{where}.distinct: 'of' must be one of {list(DISTINCT_OF)}, got {of!r}"
            )
        if not spec.get("objects"):
            # An empty selector is the whole battlefield, so domain would count
            # an opponent's basics and coven would count their creatures.
            raise DslError(
                f"{where}.distinct: needs 'objects' -- an empty selector is "
                f"every permanent in the game, including your opponents'"
            )
        validate_selector(spec["objects"], f"{where}.distinct.objects")
