"""Cost reduction and the filters that decide what a reduction counts.
Split from ``costs``, which keeps the mana sources and the payment itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .carddef import CardDef, Cost
from .characteristics import (
    chars,
    spell_cost_reduction,
)

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


def cost_reduction(state: GameState, pid: int, card: CardDef) -> int:
    """How much less this card costs its controller right now.

    Generic only, and never below zero: "costs {X} less" does not touch coloured
    pips, which is both what the rules say and the only thing the payment solver
    could act on.  Read from the board rather than stored, because it changes
    every time a creature arrives -- Ghalta is a 12-drop or a 2-drop depending on
    what is already in play.
    """
    # Two sources, added together, and they point in opposite directions.
    # `card.cost_reduction` is Ghalta -- "THIS spell costs {X} less", counting
    # permanents. The statics are Warden of Evos Isle -- "creature spells with
    # flying YOU CAST cost {1} less", discounting a different card, picked out
    # by that card's own printed face.
    total = spell_cost_reduction(state, pid, card)
    return total + reduction_amount(state, pid, card.cost_reduction)


def reduction_amount(
    state: GameState,
    pid: int,
    spec: Mapping[str, Any] | None,
    *,
    source_oid: int | None = None,
) -> int:
    """How much less one *cost node* costs right now, as a plain integer.

    The whole reduction language, in one place, because a cost node is priced
    from three different callers and "costs {N} less" has to mean the same thing
    in all three:

    - a card's own `cost_reduction` -- Ghalta, "**this spell** costs {X} less";
    - an activated ability's `Cost.mana_reduction`, via `ability_mana` --
      Voldaren Estate and Crown of Gondor's equip;
    - a graveyard cast's `Cost.mana_reduction`, via the flashback branch of
      `legality._cast_variant` and `game._cast` -- "costs {X} less to cast
      **this way**".

    Three shapes of arithmetic, exactly one per spec:

    - ``{"amount": 3}`` -- a **flat** number, which is what a conditional
      reduction needs.  Not expressible as `count`: "costs {3} less if you're
      the monarch" would need a filter matching exactly three permanents while
      the crown is yours and none otherwise, and no filter over a board can say
      that.
    - ``{"count": {filter}}`` -- "{1} less for each Vampire you control".
    - ``{"total_power": {filter}}`` -- Ghalta.
    - ``{"greatest_mana_value": {filter}}`` -- Visions of Glory, "where X is the
      greatest mana value of a commander you own".  A **maximum**, which is why
      it is a fourth shape rather than a filter on `count`: the other two sum,
      and a player with two partner commanders would have their mana values
      added rather than the greater one taken -- a different and larger number,
      quietly, on a card that reads as though it were right.

    ``condition`` gates the whole thing: false, the reduction is zero, and the
    printed price stands.  It is an ordinary condition from the condition DSL,
    so `is_monarch`, `is_your_turn`, `exists` and `cmp` all come for free -- but
    the loader restricts it to the heads that can be *answered at pricing time*,
    because nothing is on the stack yet.

    A condition rather than a second cost line, for the reason the Crown of
    Gondor gap record gives: splitting "Equip {4}, {3} less if you're the
    monarch" into two equip abilities leaves nothing able to switch the cheap
    one off.
    """
    if not spec:
        return 0
    # The gate first, so a false condition costs one condition evaluation rather
    # than a walk of the battlefield.
    cond = spec.get("condition")
    if cond is not None:
        from .effects.conditions import evaluate_condition

        if not evaluate_condition(state, cond, controller=pid, source=source_oid):
            return 0
    if "amount" in spec:
        return max(0, int(spec["amount"]))
    if "count" in spec:
        return sum(1 for _ in _reduction_matches(state, pid, spec["count"], source_oid))
    if "total_power" in spec:
        return sum(
            max(0, chars(state, oid).power)
            for oid in _reduction_matches(state, pid, spec["total_power"], source_oid)
        )
    if "greatest_mana_value" in spec:
        # The **printed** mana value, off the card rather than the object, and
        # `default=0` because nothing matching is a real answer: a player whose
        # commander has been exiled, or who has none at all, gets no discount
        # and pays the price the card prints.
        return max(
            (
                state.card(oid).mana_value
                for oid in _reduction_matches(state, pid, spec["greatest_mana_value"], source_oid)
            ),
            default=0,
        )
    return 0


def variant_reduction(state: GameState, pid: int, cost: Cost | None, source_oid: int | None) -> int:
    """ "This spell costs {X} less to cast **this way**."

    The discount that belongs to one cast *variant* rather than to the card.
    Visions of Glory's flashback line carries one and its printed hand cast must
    not: a card-level `cost_reduction` is variant-blind, applied by
    `_cast_variant` to whichever price it just picked, so putting the rider
    there would quietly discount the cast the card never mentions.

    It is `Cost.mana_reduction` on the variant's own cost node -- the same key
    an activated ability's cost uses -- and not a new field, because it is the
    same question asked of a different cost: "how much less does *this* cost
    node cost".  A second key meaning the same thing is a key that gets written
    in the wrong slot and silently ignored.

    Only `flashback`/`graveyard_cost` can carry one today, and that is a fact
    about the schema rather than about this function: `evoke`, `emerge`,
    `overload`, `bestow`, `foretell` and `mutate` are bare mana strings with no
    node to hang a rider on, and the loader says so rather than accepting one.

    `alternative_cost` is the second full `Cost` -- Force of Will's pitch needs
    somewhere to put a payment that is not mana -- but it is deliberately *not*
    read here. A discount belongs to the branch that priced the line, and no
    printed prowl or pitch cost says "costs {X} less to cast this way"; the
    loader refuses `mana_reduction` on it rather than leaving a key that loads
    and is ignored.
    """
    if cost is None:
        return 0
    return reduction_amount(state, pid, cost.mana_reduction, source_oid=source_oid)


#: Zones a cost reduction's filter may count, and where each one's objects live.
#:
#: The battlefield and the command zone, and no others.  Both are **public** and
#: both are readable before anything is on the stack, which is the whole
#: requirement -- but the command zone had to be added on its own merits: it is
#: where a commander sits for most of a game, so a reduction written about "a
#: commander you own" and evaluated over the battlefield alone would read zero
#: at exactly the moment the printed card is about it.
#: The graveyard joined them on the same test: it is public, and it is readable
#: before anything is on the stack. Cyan, Vengeful Samurai -- "This spell costs
#: {1} less to cast for each creature card in your graveyard" -- is the card
#: that wanted it, and there was no third place a spell's own price could be
#: lowered from: the battlefield `spell_cost_reduction` static discounts a
#: *different* card and its `count` is filtered by `static_filter_keys`, which
#: has no `zone` key at all.
REDUCTION_ZONES = frozenset({"battlefield", "command", "graveyard"})


def _reduction_zone_oids(state: GameState, zones: frozenset[str]):
    """Every object a reduction filter naming ``zones`` may look at.

    The command zone is per-player rather than global -- there is no
    `state.command` to walk the way there is a `state.battlefield` -- so every
    seat's is concatenated and the ownership keys below narrow it, exactly as
    they narrow the battlefield.
    """
    if "battlefield" in zones:
        yield from state.battlefield
    if "command" in zones:
        for player in state.players:
            yield from player.command
    if "graveyard" in zones:
        # Every seat's, narrowed by the ownership keys below exactly as the
        # command zone is -- "in **your** graveyard" is `controller: "you"`,
        # and a card in a graveyard is in its owner's (400.3).
        for player in state.players:
            yield from player.graveyard


def _reduction_matches(state: GameState, pid: int, filt: Any, source_oid: int | None = None):
    """The objects one reduction filter picks out, across the zones it names.

    ``controller`` and ``owner`` are both here and they are not the same
    question.  Every existing reduction counts permanents *you control*, which is
    what "for each Vampire you control" says.  Visions of Glory says "a commander
    you **own**", and the two part company on precisely the boards commanders are
    played on: a commander in the command zone is controlled by nobody in
    particular (the object's controller is its owner there, so `controller`
    happens to answer), while a commander an opponent has stolen with Control
    Magic is still one you own and still counts for the printed line.

    ``zone`` defaults to the battlefield, so every filter written before the
    command zone was reachable means what it always meant.

    Types, subtypes, supertypes, colours and keywords come from `chars` on the
    battlefield and from the printed face anywhere else.  A card in the command
    zone is not a permanent: no continuous effect applies to it, and asking the
    characteristics pipeline would let a static that forgot to say "creatures
    you control" reach into a zone no static can touch.

    **Every key the loader accepts is read here.**  It used to read six of
    twenty and ignore the rest in silence, so "for each **legendary** creature
    you control" -- Takenuma's channel ability -- priced itself off every
    creature instead, and nothing on a board or in a test would have said so: a
    reduction that counts too much simply makes the ability cheaper. The three
    keys `STATIC_FILTER_KEYS` carries that are *not* here -- `attached`,
    `paired` and `paired_with_source` -- are refused by the loader rather than
    implemented, because each names a relation to one particular permanent and
    a reduction counts a board.
    """
    zones = _filter_zones(filt)
    for oid in _reduction_zone_oids(state, zones):
        obj = state.objects.get(oid)
        if obj is None:
            continue
        owner = filt.get("owner")
        # "You control" is the default only while the filter has said nothing
        # about ownership. A filter that named `owner` and not `controller` is
        # asking the other question, and a defaulted control check on top of it
        # would silently re-impose the answer the card went out of its way not
        # to ask for -- a commander an opponent stole is one you own and *not*
        # one you control, so the default would drop exactly the case `owner`
        # was written for.
        controller = filt.get("controller", None if owner else "you")
        if controller == "you" and obj.controller != pid:
            continue
        if controller == "opponent" and obj.controller == pid:
            continue
        if owner == "you" and obj.owner != pid:
            continue
        if owner == "opponent" and obj.owner == pid:
            continue
        if "is_commander" in filt and bool(obj.is_commander) != bool(filt["is_commander"]):
            continue
        if filt.get("self_only") and oid != source_oid:
            continue
        if filt.get("exclude_self") and oid == source_oid:
            continue
        if obj.on_battlefield:
            c = chars(state, oid)
            types, subtypes, supertypes = c.types, c.subtypes, c.supertypes
            keywords, colors = c.keywords, c.colors
        else:
            card = state.card_of(obj)
            types, subtypes, supertypes = card.types, card.subtypes, card.supertypes
            keywords, colors = card.keywords, card.colors
        if (want := filt.get("types")) and not set(want).issubset(types):
            continue
        if (want := filt.get("not_types")) and set(want) & set(types):
            continue
        if (want := filt.get("subtypes")) and not set(want) & set(subtypes):
            continue
        if (want := filt.get("supertypes")) and not set(want).issubset(supertypes):
            continue
        if (want := filt.get("colors")) and not set(want) & set(colors):
            continue
        if (want := filt.get("keywords")) and not set(want).issubset(keywords):
            continue
        if (want := filt.get("not_keywords")) and set(want) & set(keywords):
            continue
        if (want := filt.get("mana_cost")) is not None:
            from .effects.selectors import has_printed_cost

            if not has_printed_cost(state, oid, want):
                continue
        # Board state, and only the three kinds of it a reduction can see. Each
        # is a pipeline *input* -- nothing in the characteristics layer writes
        # a tapped flag, a token flag or a combat assignment -- so reading them
        # while pricing cannot depend on a static that has not run.
        if "tapped" in filt and bool(obj.tapped) != bool(filt["tapped"]):
            continue
        if "is_token" in filt and bool(obj.is_token) != bool(filt["is_token"]):
            continue
        combat = state.combat
        if "attacking" in filt and bool(combat and combat.attacking(oid)) != bool(
            filt["attacking"]
        ):
            continue
        if "blocking" in filt and bool(combat and combat.blocking(oid)) != bool(filt["blocking"]):
            continue
        yield oid


def _filter_zones(filt: Any) -> frozenset[str]:
    """The zones a filter names, as a set -- one zone or a list of them.

    A list rather than a second filter key, because "on the battlefield **or** in
    the command zone" is one pool with one maximum taken over it, and two
    filters would be two maxima that something then has to combine.
    """
    zone = filt.get("zone", "battlefield")
    if isinstance(zone, str):
        return frozenset({zone})
    return frozenset(str(z) for z in zone)
