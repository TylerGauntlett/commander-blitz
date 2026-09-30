"""Cost reduction and the filters that decide what a reduction counts.
Split from ``costs``, which keeps the mana sources and the payment itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .carddef import CardDef, Cost
from .characteristics import (
    chars,
    compare_pt,
    spell_cost_reduction,
    spell_mana_tax,
)

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


def cost_reduction(state: GameState, pid: int, card: CardDef, targets=None) -> int:
    """How much less this card costs its controller right now.

    ``targets`` is what the cast actually aimed at, when it is known. A
    discount whose clause reads them -- "Aura spells you cast **that target
    enchanted creature** cost {3} less" -- is read generously while it is
    ``None``, which is the only reading a gate can take: legality asks whether
    the card is castable at all before it enumerates a target tuple, and
    refusing there would drop a spell that is affordable at the discounted
    price. Each offered cast is then priced with its own targets.

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
    total = spell_cost_reduction(state, pid, card, targets)
    # And the one that points the other way: Kasmina's "spells your opponents
    # cast that target a creature or planeswalker you control cost {2} more".
    # Netted in as a negative discount, so the offer and the charge price it
    # through the same number -- see `spell_mana_tax`. The total may therefore
    # be negative, which every caller already folds into an `extra_generic`.
    total -= spell_mana_tax(state, pid, card, targets)
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

    Six shapes of arithmetic, exactly one per spec:

    - ``{"amount": 3}`` -- a **flat** number, which is what a conditional
      reduction needs.  Not expressible as `count`: "costs {3} less if you're
      the monarch" would need a filter matching exactly three permanents while
      the crown is yours and none otherwise, and no filter over a board can say
      that.
    - ``{"count": {filter}}`` -- "{1} less for each Vampire you control".
    - ``{"greatest_count": {filter}}`` -- Cavern-Hoard Dragon, "where X is the
      greatest number of artifacts **an opponent** controls".  The same
      relation `greatest_mana_value` has to `total_mana_value`, one axis over:
      a maximum where `count` is a sum, taken **per player** rather than over
      one flat pool.  Its own key for the sharpest of the reasons any of these
      has one -- a reduction filter's ``controller: "opponent"`` names every
      opponent at once, so `count` at a pod of four would read three opponents
      with two artifacts each as {6} where the printed card says {2}, and in a
      two-player game the two numbers coincide exactly.
    - ``{"total_power": {filter}}`` -- Ghalta.
    - ``{"total_mana_value": {filter}}`` -- Excalibur, Sword of Eden, "where X
      is the total mana value of historic permanents you control".
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
    if "greatest_count" in spec:
        # "…where X is the greatest number of artifacts **an opponent**
        # controls" -- Cavern-Hoard Dragon. One pool, tallied per controller
        # and maximised, because the filter language can say "not you" but not
        # "them, separately" -- the same thing `_counts_per_player`'s docstring
        # says about the effect-side `max_count_of`, which has the arithmetic
        # and cannot be reached from a price.
        #
        # `default=0` because a seat controlling nothing contributes no tally
        # and is right not to: a board where no opponent has an artifact gives
        # no discount, and the spell costs what it prints.
        per_player: dict[int, int] = {}
        for oid in _reduction_matches(state, pid, spec["greatest_count"], source_oid):
            obj = state.objects.get(oid)
            if obj is None:  # pragma: no cover -- yielded from state.objects
                continue
            per_player[obj.controller] = per_player.get(obj.controller, 0) + 1
        return max(per_player.values(), default=0)
    if "total_power" in spec:
        return sum(
            max(0, chars(state, oid).power)
            for oid in _reduction_matches(state, pid, spec["total_power"], source_oid)
        )
    if "total_mana_value" in spec:
        # "…where X is the **total** mana value of historic permanents you
        # control" -- Excalibur, Sword of Eden. The mana-value analogue of
        # `total_power`, and a separate key from `greatest_mana_value` for that
        # key's own reason read the other way round: a maximum must not sum and
        # a sum must not take a maximum. Two permanents of mana value 3 and 5
        # are 8 here and 5 there, and each printed card means exactly one.
        #
        # The **printed** mana value, off the card rather than the object -- the
        # same face `greatest_mana_value` reads, because a mana value is a
        # property of a card and nothing in the characteristics pipeline writes
        # one.
        return sum(
            state.card(oid).mana_value
            for oid in _reduction_matches(state, pid, spec["total_mana_value"], source_oid)
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


def _object_matches(
    state: GameState, pid: int, filt: Any, oid: int, obj: Any, source_oid: int | None
) -> bool:
    """Does this one object match this filter?

    Split out of `_reduction_matches` so that it can **recurse**, which is the
    whole of `any_of`: a branch is the same filter language asked about the same
    object, exactly as the effect-side selector's `any_of` is.
    """
    # "…the total mana value of **historic** permanents you control. (Artifacts,
    # legendaries, and Sagas are historic.)" -- Excalibur, Sword of Eden.
    #
    # Every other key here is ANDed, which is what makes a disjunction
    # unsayable without this: `{"types": ["Artifact"], "supertypes":
    # ["Legendary"], "subtypes": ["Saga"]}` matches only a permanent that is all
    # three at once, which nothing is, and the card would price itself off an
    # empty board for ever. `any_types` is an or over *types* alone and cannot
    # reach a supertype or a subtype.
    #
    # A branch names no `zone`: the zones are chosen once, outside the loop, and
    # a branch that named its own would be read by nobody -- so the loader
    # refuses one rather than accepting it silently.
    if (branches := filt.get("any_of")) is not None and not any(
        _object_matches(state, pid, branch, oid, obj, source_oid) for branch in branches
    ):
        return False
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
        return False
    if controller == "opponent" and obj.controller == pid:
        return False
    if owner == "you" and obj.owner != pid:
        return False
    if owner == "opponent" and obj.owner == pid:
        return False
    if "is_commander" in filt and bool(obj.is_commander) != bool(filt["is_commander"]):
        return False
    if filt.get("self_only") and oid != source_oid:
        return False
    if filt.get("exclude_self") and oid == source_oid:
        return False
    if obj.on_battlefield:
        c = chars(state, oid)
        types, subtypes, supertypes = c.types, c.subtypes, c.supertypes
        keywords, colors = c.keywords, c.colors
        power, toughness = c.power, c.toughness
    else:
        card = state.card_of(obj)
        types, subtypes, supertypes = card.types, card.subtypes, card.supertypes
        keywords, colors = card.keywords, card.colors
        power, toughness = card.power or 0, card.toughness or 0
    if (want := filt.get("types")) and not set(want).issubset(types):
        return False
    if (want := filt.get("not_types")) and set(want) & set(types):
        return False
    if (want := filt.get("subtypes")) and not set(want) & set(subtypes):
        return False
    if (want := filt.get("supertypes")) and not set(want).issubset(supertypes):
        return False
    if (want := filt.get("colors")) and not set(want) & set(colors):
        return False
    if (want := filt.get("keywords")) and not set(want).issubset(keywords):
        return False
    if (want := filt.get("not_keywords")) and set(want) & set(keywords):
        return False
    if (want := filt.get("mana_cost")) is not None:
        from .effects.selectors import has_printed_cost

        if not has_printed_cost(state, oid, want):
            return False
    # "…costs {1} less for each creature you control with power 4 or greater."
    # Honoured here because a reduction filter is validated against
    # `STATIC_FILTER_KEYS`, and a key the loader accepts and this function does
    # not read prices the spell off a clause that matched the whole board.
    #
    # **Derived**, off `chars`, exactly like the types and keywords above and
    # exactly like `total_power` in this same module: pricing happens outside
    # the characteristics pipeline, so every layer has already applied and there
    # is nothing half-computed to read. `characteristics._matches` is restricted
    # to base P/T because it runs *inside* that pipeline and cannot be; the
    # divergence between the two readers is the one `keywords` already has.
    if (want := filt.get("power")) is not None and not compare_pt(power, want):
        return False
    if (want := filt.get("toughness")) is not None and not compare_pt(toughness, want):
        return False
    # Board state, and only the three kinds of it a reduction can see. Each
    # is a pipeline *input* -- nothing in the characteristics layer writes
    # a tapped flag, a token flag or a combat assignment -- so reading them
    # while pricing cannot depend on a static that has not run.
    if "tapped" in filt and bool(obj.tapped) != bool(filt["tapped"]):
        return False
    if "has_counters" in filt and any(n > 0 for n in obj.counters.values()) != bool(
        filt["has_counters"]
    ):
        return False
    if "is_token" in filt and bool(obj.is_token) != bool(filt["is_token"]):
        return False
    # "…for each creature that entered this turn". Honoured here because the
    # docstring above promises it: **every key the loader accepts is read here**,
    # and a reduction filtered on a key nobody honoured is priced off a clause
    # that matched everything. A ledger arrival is an input the same way the
    # three above are -- nothing in the characteristics pipeline writes one -- so
    # reading it while pricing cannot depend on a static that has not run. Off
    # the battlefield it is false, which is right: a card in a graveyard or the
    # command zone did not enter the battlefield this turn.
    if "entered_this_turn" in filt and bool(
        state.turn_ledger.entered_this_turn(oid)
    ) != bool(filt["entered_this_turn"]):
        return False
    combat = state.combat
    if "attacking" in filt and bool(combat and combat.attacking(oid)) != bool(
        filt["attacking"]
    ):
        return False
    if "blocking" in filt and bool(combat and combat.blocking(oid)) != bool(filt["blocking"]):
        return False
    return True


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
        if _object_matches(state, pid, filt, oid, obj, source_oid):
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
