"""Paying costs.

Mana payment is automatic (see :mod:`automtg.engine.mana`): an action never
carries a payment, and legality only offers a cast or activation when the solver
can find a set of sources to tap.  Non-mana costs (sacrifice, discard, pay life)
may need a choice, so :func:`pay` is a generator.
"""

from __future__ import annotations

from collections.abc import Generator, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from .carddef import Ability, CardDef, Cost
from .characteristics import (
    abilities_of,
    chars,
    player_doubles_land_mana,
    spell_cost_reduction,
)
from .effects.context import EffectContext, ask_objects
from .effects.selectors import resolve_pool
from .enums import COLORLESS, Keyword, Zone
from .errors import DslError
from .events import EventType
from .mana import (
    ACTIVATE,
    CAST,
    CHOSEN_TYPE,
    SYMBOL_INDEX,
    SYMBOLS,
    ManaCost,
    ManaRestriction,
    ManaSource,
    Requirement,
    SpendPurpose,
    format_symbols,
    solve_payment,
)
from .primitives import (
    life_locked,
    lose_life,
    sacrifice_forbidden,
    tap_permanent,
    untap_permanent,
)
from .zones import bounce as bounce_object
from .zones import exile as exile_object
from .zones import sacrifice as sacrifice_object

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


def mana_sources(
    state: GameState, pid: int, *, purpose: SpendPurpose | None = None
) -> list[ManaSource]:
    """Every mana ability this player could activate right now.

    Only tap-only mana abilities are considered.  A mana ability with an extra
    cost (pay life, sacrifice) is left for the player to activate explicitly.

    ``purpose`` describes what the mana would be spent on -- the lowercased card
    types and subtypes of the spell being cast, or of the source whose ability
    is being activated.  Restricted sources ("spend this mana only to cast a
    creature spell") are dropped unless the purpose matches, so the solver never
    has to know restrictions exist.  ``None`` means "no particular spell", and
    offers only unrestricted mana: an under-count rather than an over-count,
    which is the safe direction for a number the AI reads.
    """
    out: list[ManaSource] = []
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None or obj.controller != pid or obj.tapped:
            continue
        out.extend(
            source for source in _sources_of(state, oid, obj) if source.permits(purpose)
        )
    return out


def spell_purpose(card: CardDef) -> SpendPurpose:
    """What restricted mana would have to allow, to *cast* this card.

    Subtypes as well as types, because the printed clause names either: "…only
    to cast a creature spell" is a type, and "…only to cast Vampire, Cleric,
    and/or Demon spells" is three subtypes. One flat set of lowercased names on
    both sides, matched by :meth:`ManaSource.permits` -- which is where the
    printed "and/or" (an any-of) and "a creature spell **of** the chosen type"
    (an all-of) are told apart.

    Tagged :data:`CAST`, which is the half of the purpose that keeps every
    restriction shipped before Secluded Courtyard meaning what it printed.
    """
    return SpendPurpose(
        kind=CAST, names=frozenset(t.lower() for t in (*card.types, *card.subtypes))
    )


def ability_purpose(state: GameState, oid: int) -> SpendPurpose:
    """What restricted mana would have to allow, to pay an ability's cost.

    "…or activate an ability of a **creature source of the chosen type**."
    Cavern of Souls, Unclaimed Territory, Secluded Courtyard. Restricted mana is
    not only for spells, and until this existed the second half of every one of
    those lines was unreachable: every `mana_sources` call that funded an
    activation passed no purpose at all, so a restricted source was dropped
    outright.

    Tagged :data:`ACTIVATE` rather than handed over as a bare name set, because
    the two are *not* interchangeable: Herd Heirloom's "only to cast a creature
    spell" and this card's "or activate an ability of" are different
    permissions, and a purpose that could not tell them apart would hand the
    first card the second card's text.

    The object's *current* characteristics on the battlefield, because that is
    what "a creature source" asks about -- a land animated into a Vampire
    creature really is one, and the printed face would say otherwise. Anywhere
    else (a creature card cycling from hand is an activated ability too, rule
    702.29a) there are no continuous effects to apply, so the printed face is
    the whole answer, exactly as `_reduction_matches` reads it.
    """
    obj = state.objects.get(oid)
    if obj is None:
        return SpendPurpose(kind=ACTIVATE, names=frozenset())
    if obj.on_battlefield:
        c = chars(state, oid)
        names = (*c.types, *c.subtypes)
    else:
        card = state.card_of(obj)
        names = (*card.types, *card.subtypes)
    return SpendPurpose(kind=ACTIVATE, names=frozenset(t.lower() for t in names))


def resolve_mana_restriction(ability: Ability, obj: Any) -> ManaRestriction | None:
    """This ability's spend restriction, as it stands on *this* permanent.

    Every group is a set of literal lowercased names except for the one leaf
    that cannot be known at load time: `{"chosen_type_of": "self"}`, which
    compiles to `mana.CHOSEN_TYPE` and is substituted here with whatever type
    the permanent chose as it entered.

    A group naming the chosen type before anything has been chosen is **dropped
    rather than widened**, so a Secluded Courtyard whose trigger has not
    resolved yet makes mana that pays for nothing at all. That is the same
    answer `characteristics.resolve_chosen_subtypes` gives an anthem in the same
    position, and it is the safe one: the alternative is a five-colour land that
    casts anything for a moment.

    A restriction with nothing dynamic in it is returned untouched, so the
    common case allocates nothing.
    """
    restriction = ability.mana_restriction
    if restriction is None or not restriction.dynamic:
        return restriction
    chosen = obj.chosen_type if obj is not None else None
    return ManaRestriction(
        cast=_resolve_groups(restriction.cast, chosen),
        activate=_resolve_groups(restriction.activate, chosen),
    )


def _resolve_groups(
    groups: tuple[frozenset[str], ...], chosen: str | None
) -> tuple[frozenset[str], ...]:
    out: list[frozenset[str]] = []
    for group in groups:
        if CHOSEN_TYPE not in group:
            out.append(group)
        elif chosen is not None:
            out.append((group - {CHOSEN_TYPE}) | {chosen.lower()})
    return tuple(out)


def available_mana(state: GameState, pid: int) -> int:
    """Upper bound on mana this player could produce, for heuristics and encoding."""
    pool = state.players[pid].mana_pool.total()
    return pool + sum(source.max_output() for source in mana_sources(state, pid))


def sources_by_controller(state: GameState) -> dict[int, list[ManaSource]]:
    """Every player's mana sources, from a single walk of the battlefield.

    :func:`mana_sources` filters the whole battlefield per player, so serializing
    a four-player pod walked it four times over.  The per-object work is
    identical either way; this just partitions instead of re-scanning.  Pass the
    result to :func:`mana_availability` as ``sources``.
    """
    out: dict[int, list[ManaSource]] = {p.pid: [] for p in state.players}
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None or obj.tapped:
            continue
        bucket = out.get(obj.controller)
        if bucket is None:
            continue
        bucket.extend(_sources_of(state, oid, obj))
    return out


def solver_taps(ability: Ability) -> bool:
    """Is this mana ability one the payment solver activates on its own?

    The solver only ever taps: :func:`_sources_of` collects nothing else, so a
    mana ability with any other cost -- a Signet's `{1}`, a Vivid land's counter
    -- is invisible to it and must be offered to the player instead. Legality
    asks this exact question in :func:`legality._activate_actions`, and the two
    must agree: an ability neither of them claims can never be activated at all,
    and one they both claim can be spent twice.

    ``mana_options`` is part of the test because
    :func:`activate_mana_ability` indexes it. An ability that produces nothing
    is not a mana source and is not offerable either.
    """
    if not ability.is_mana_ability or not ability.mana_options:
        return False
    return ability.cost is not None and ability.cost.is_tap_only()


def offerable_mana_ability(ability: Ability) -> bool:
    """Should legality put this mana ability in front of the player?

    The complement of :func:`solver_taps` over mana abilities that actually
    produce something.
    """
    return (
        ability.is_mana_ability
        and bool(ability.mana_options)
        and not solver_taps(ability)
    )


def _sources_of(state: GameState, oid: int, obj: Any) -> list[ManaSource]:
    """The tap-only mana abilities of one untapped permanent."""
    # A mana ability is an activated ability, so "its activated abilities can't
    # be activated this turn" stops it here as well as in `legality`. Filtered in
    # this one helper because both entry points above go through it.
    if obj.abilities_locked:
        return []
    card = state.card_of(obj)
    c = chars(state, oid)
    is_creature = "Creature" in c.types
    if is_creature and obj.summoning_sick(state.turn) and Keyword.HASTE.value not in c.keywords:
        return []
    is_land = "Land" in c.types
    doubled = is_land and player_doubles_land_mana(state, obj.controller)
    out: list[ManaSource] = []
    for ability in abilities_of(state, oid):
        if not solver_taps(ability):
            continue
        out.append(
            ManaSource(
                oid=oid,
                ability_index=ability.index,
                options=(
                    tuple(
                        mana_produced(
                            option,
                            doubled=doubled,
                            times=mana_amount(state, oid, ability),
                        )
                        for option in mana_options_of(state, oid, ability)
                    )
                ),
                is_land=is_land,
                sort_key=(0 if is_land else 1, card.id, oid),
                restriction=resolve_mana_restriction(ability, obj),
            )
        )
    return out


def mana_amount(state: GameState, oid: int, ability: Ability) -> int:
    """How many times this mana ability's symbols are produced, right now.

    "Add {G} for each +1/+1 counter on this creature" -- Gyre Sage. The count is
    a question about the board, so unlike everything else about a mana ability
    it cannot be folded into a constant at load time.

    Read at *activation* time, and read through the ordinary value language,
    which already computes exactly this (`counters_on` reads live counters off
    the source; `count` reads the board). A mana ability may not stop to ask
    anything, and this asks nothing -- it only looks.

    Clamped at zero: a negative multiplier is not a thing a card can mean, and
    an ability with no counters on it simply makes no mana.
    """
    if ability.mana_amount is None:
        return 1
    from .effects.context import EffectContext
    from .effects.values import evaluate_value

    obj = state.objects.get(oid)
    if obj is None:
        return 0
    ctx = EffectContext(
        state=state,
        controller=obj.controller,
        source_oid=oid,
        source_name=state.card_of(obj).name,
    )
    return max(0, int(evaluate_value(ctx, ability.mana_amount)))


def mana_options_of(state: GameState, oid: int, ability: Ability) -> tuple[tuple[int, ...], ...]:
    """Which symbol tuples this ability could produce **right now**.

    For almost every mana ability this is the load-time constant: the card says
    what it makes. Exotic Orchard says what to *ask* instead -- "one mana of any
    color that a land an opponent controls could produce" -- so its options are
    a question about the board.

    Called from ``_sources_of`` (so the solver plans against the real colours)
    and from ``activate_mana_ability`` (so the payment adds one of them), for
    exactly the reason ``mana_produced`` is: a spell offered on a colour and
    then paid in another would strand the payment mid-cast. Both read the same
    board within one payment, so the option index they agree on means the same
    thing to each.

    An empty result is a real answer -- an opponent with no lands offers no
    colours, and the Orchard taps for nothing. The solver simply never picks a
    source that produces nothing.

    It **only looks**. No `ask_*`, no generator, no stack: narrowing the option
    list narrows the choice a modal mana ability already had (the solver picks an
    option index while planning; manual mana offers one chip per option), and
    introduces no new question. That is what keeps a reflecting ability a mana
    ability for 605.1a.
    """
    if ability.mana_chosen_color:
        return _chosen_color_options(state, oid, ability)
    if ability.mana_identity:
        return _identity_options(state, oid, ability)
    if ability.mana_reflects is None:
        return ability.mana_options

    ctx = EffectContext(state=state, controller=state.objects[oid].controller, source_oid=oid)
    colors: set[int] = set()
    for other in resolve_pool(ctx, ability.mana_reflects):
        for other_ability in abilities_of(state, other):
            # A *reflecting* ability is skipped outright: two Exotic Orchards
            # facing each other would otherwise ask each other what they produce,
            # for ever. That skip is what makes the recursion below terminate.
            if not other_ability.is_mana_ability or other_ability.mana_reflects is not None:
                continue
            # Everything else is asked the same question this function answers,
            # rather than being read off its load-time `mana_options`. A land
            # whose own colours are a question about the game carries the
            # five-colour superset there -- so an opponent's Path of Ancestry,
            # which taps only for its controller's commander's identity, used to
            # tell a Fellwar Stone it "could produce" all five. That is the
            # unconditional any-colour approximation this whole capability exists
            # to refuse, arriving through the back door. The recursion is one
            # level deep and cannot cycle: the only self-referential branch is
            # `mana_reflects`, and it never gets here.
            for option in mana_options_of(state, other, other_ability):
                for index, amount in enumerate(option):
                    if amount and index != SYMBOL_INDEX[COLORLESS]:
                        colors.add(index)

    out: list[tuple[int, ...]] = []
    for option in ability.mana_options:
        if any(amount and i in colors for i, amount in enumerate(option)):
            out.append(option)
    return tuple(out)


def _chosen_color_options(
    state: GameState, oid: int, ability: Ability
) -> tuple[tuple[int, ...], ...]:
    """The five-colour superset narrowed to the colour this permanent chose.

    "{T}: Add one mana of the chosen color" -- Heraldic Banner. Exactly one
    option once a colour has been named, and **none at all** before then, which
    is the same match-nothing default `resolve_chosen_colors` gives the anthem
    on the line above it: an ability that offered all five while the enters
    trigger was still on the stack would be a Chromatic Lantern for a moment.

    An empty result is a real answer the solver already understands -- it simply
    never picks a source that produces nothing -- and it is the same answer
    `_identity_options` gives a colourless commander.

    It **only looks**: reading `chosen_color` asks nothing and puts nothing on
    the stack, so this stays a mana ability for 605.1a.
    """
    obj = state.objects.get(oid)
    chosen = obj.chosen_color if obj is not None else None
    if chosen is None:
        return ()
    index = SYMBOL_INDEX.get(chosen)
    if index is None:  # pragma: no cover - the loader only writes WUBRG here
        return ()
    return tuple(
        option for option in ability.mana_options if option[index]
    )


def _identity_options(
    state: GameState, oid: int, ability: Ability
) -> tuple[tuple[int, ...], ...]:
    """The five-colour superset narrowed to the controller's commanders' identity.

    Read off the **printed** `color_identity` rather than the object's current
    colours, and wherever the commander happens to be. Colour identity is a
    deck-construction fact fixed by the card: it counts mana symbols in rules
    text, it is the same set in the command zone as on the battlefield, and a
    Command Tower does not stop working because the general is in a graveyard.
    Asking `chars()` instead would be a different and smaller set on most
    commanders, and a wrong one on all of them the turn somebody makes the
    commander an artifact.

    A colourless commander narrows this to nothing, and the land taps for
    nothing -- which is the printed card, not a bug: the solver simply never
    picks a source that produces nothing.
    """
    controller = state.objects[oid].controller
    colors: set[int] = set()
    for commander in state.commanders_of(controller):
        obj = state.objects.get(commander)
        if obj is None:
            continue
        for symbol in state.card_of(obj).color_identity:
            index = SYMBOL_INDEX.get(symbol)
            if index is not None and index != SYMBOL_INDEX[COLORLESS]:
                colors.add(index)
    return tuple(
        option
        for option in ability.mana_options
        if any(amount and i in colors for i, amount in enumerate(option))
    )


def mana_produced(option: Sequence[int], *, doubled: bool, times: int = 1) -> tuple[int, ...]:
    """What tapping for ``option`` actually yields.

    Vorinclex's "whenever you tap a land for mana, add one mana of any type that
    land produced" is not a trigger: a mana ability must never use the stack or
    stop to ask, so it is folded in here instead.

    This one helper is called from **both** ``_sources_of`` (so legality counts
    the extra mana when deciding what is castable) and ``activate_mana_ability``
    (so payment actually adds it).  The two must not be able to disagree -- a
    spell offered on doubled mana and then paid for on single mana would strand
    the payment mid-cast.

    *Simplification*: a dual land doubles whatever it produced rather than
    offering a free choice of type, because a mana ability cannot ask.  Recorded
    in ``docs/rules-coverage.md`` alongside the other automatic-mana trades.

    ``times`` is the variable-output multiplier from :func:`mana_amount`, and it
    is threaded through *here* for the same reason the doubling is: this is the
    one place both the offer and the payment come through, so they cannot be
    given different numbers.
    """
    scale = (2 if doubled else 1) * times
    if scale == 1:
        return tuple(option)
    return tuple(v * scale for v in option)


def produced_symbols(card: CardDef) -> list[str]:
    """Every mana symbol this card's mana abilities could make, deduplicated.

    The client colours lands by what they tap for, and this is the only honest
    source for that: "Island" is inferable from a subtype, but a nonbasic dual is
    not, and re-deriving it by parsing ``oracle_text`` in the browser is exactly
    the guess :mod:`frontend/src/logic/mana.ts` refuses to make.
    """
    found: set[str] = set()
    for ability in card.mana_abilities():
        for option in ability.mana_options:
            found.update(_option_symbols(option))
    return sorted(found, key=SYMBOL_INDEX.get)


def mana_availability(
    state: GameState, pid: int, sources: Sequence[ManaSource] | None = None
) -> dict[str, Any]:
    """What this player could produce right now, for the client's mana row.

    Deliberately *not* a single colour histogram.  A dual land reading "Add {G}
    or {U}" is one mana that could be either, so a histogram claiming one {G}
    and one {U} would overstate the board by a mana per dual.  Instead every
    untapped source keeps its own list of the symbols it might make, and the UI
    renders an ambiguous source as one split pip rather than two solid ones.

    ``total`` is still an upper bound rather than a promise: two sources that
    each make "{G} or {U}" can produce two mana, but never two {U} *and* two
    {G}.  Only :func:`can_pay_mana` answers affordability, and the client uses
    the action list for that.

    ``sources`` lets a caller serializing every seat share one battlefield walk;
    see :func:`sources_by_controller`.  Omitted, it is computed here as before.
    """
    pool = state.players[pid].mana_pool
    if sources is None:
        sources = mana_sources(state, pid)
    return {
        "pool": pool.to_dict(),
        "sources": [
            {
                "oid": source.oid,
                # Every yield the ability could choose, each as the symbols it
                # actually makes.  "{T}: Add {G} or {U}" is [["G"], ["U"]];
                # "{T}: Add {G}{U}" is [["G", "U"]].  The union alone cannot
                # tell those apart, and the difference is a whole mana.
                "options": [_option_symbols(option) for option in source.options],
                # Sorted by SYMBOLS order so {G}{U} and {U}{G} render alike.
                "symbols": sorted(
                    (SYMBOLS[i] for i in source.producible()), key=SYMBOL_INDEX.get
                ),
                "amount": source.max_output(),
            }
            for source in sources
        ],
        "total": pool.total() + sum(source.max_output() for source in sources),
    }


def _option_symbols(option: Sequence[int]) -> list[str]:
    """One mana-ability yield as repeated symbols: (0,1,0,0,1,0) -> ["U", "G"]."""
    return [SYMBOLS[i] for i, count in enumerate(option) for _ in range(count)]


def can_pay_mana(
    state: GameState,
    pid: int,
    cost: ManaCost,
    *,
    x: int = 0,
    extra_generic: int = 0,
    purpose: SpendPurpose | None = None,
) -> bool:
    req = cost.with_x(x)
    if extra_generic:
        req = req.with_generic(req.generic + extra_generic)
    return (
        solve_payment(
            req, state.players[pid].mana_pool, mana_sources(state, pid, purpose=purpose)
        )
        is not None
    )


def defined_x(
    state: GameState, pid: int, cost: Cost | None, source_oid: int | None
) -> int | None:
    """What X is, when the ability *says* rather than *asks*.

    "{X}, {T}: Create a token that's a copy of the exiled card. **X is the mana
    value of that card.**" -- Soul Foundry. Rule 601.2b announces X for a spell,
    and 602.2b puts an activated ability's costs on the same footing, but an
    ability whose own text fixes X never asks: the number is read off the board
    when the ability is activated.

    ``None`` -- not ``0`` -- means "this cost does not define X", because 0 is a
    perfectly good defined X (an imprinted Ornithopter) and reading the two the
    same way would send every ordinary Fireball down this path.

    Clamped at zero: a value expression can go negative (a `minus`), and a
    negative X is not a discount on the rest of the cost.
    """
    if cost is None or cost.x_value is None:
        return None
    from .effects.values import evaluate_value

    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    return max(0, int(evaluate_value(ctx, cost.x_value)))


def ability_mana(
    state: GameState,
    pid: int,
    cost: Cost,
    x: int = 0,
    source_oid: int | None = None,
) -> Requirement:
    """What this ability's mana half actually costs right now.

    "This ability costs {1} less to activate for each Vampire you control."
    Both card-level reductions discount *casting a spell* -- a card's own
    `cost_reduction` and the `spell_cost_reduction` static -- and both are read
    only from the cast path, so an activated ability's price was the literal
    string written on the card.

    The arithmetic lives in `reduction_amount`, shared with the cast path, so
    "costs {N} less" means one thing everywhere it is written.

    Generic only and clamped at zero, like every other reduction: "costs {1}
    less" never reaches through the generic part into the coloured pips.

    One helper, called by `can_pay` and by `pay`, because an ability offered at
    the reduced price and then charged the printed one would strand the payment
    -- the same care `life_cost` and `mana_produced` already take.  ``source_oid``
    is threaded through for the same reason: a reduction gated on a condition
    about its own permanent must answer that question identically in both.

    An ability that **defines** its own X ("X is the mana value of that card")
    is priced here too, and the ``x`` the caller passed is overridden rather
    than trusted: this one function is what legality, `can_pay` and `pay` all
    reach, so a defined X cannot be offered at one number and charged at
    another.  See :func:`defined_x`.
    """
    defined = defined_x(state, pid, cost, source_oid)
    if defined is not None:
        x = defined
    req = cost.mana.with_x(x)
    less = reduction_amount(state, pid, cost.mana_reduction, source_oid=source_oid)
    if not less:
        return req
    return req.with_generic(req.generic - less)


def life_cost(state: GameState, pid: int, cost: Cost, source_oid: int | None) -> int:
    """How much life this cost asks for, right now.

    Almost always the integer written on the card. War Room's is a value
    expression -- "pay life equal to the number of colors in your commanders'
    color identity" -- and is the only part of a cost besides `times` that is
    not fixed when the card is written.

    One helper, because `can_pay` and `pay` must not be able to disagree: a cost
    checked at one price and charged at another either strands the payment or
    hands out a discount. The same care `mana_produced` and `mana_options_of`
    already take, for the same reason.
    """
    spec = cost.pay_life
    if isinstance(spec, int):
        return spec
    from .effects.values import evaluate_value

    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    return max(0, int(evaluate_value(ctx, spec)))


def can_pay(
    state: GameState,
    pid: int,
    cost: Cost | None,
    source_oid: int | None,
    *,
    x: int = 0,
    purpose: SpendPurpose | None = None,
) -> bool:
    """Can this player pay every part of ``cost`` right now?

    ``purpose`` is what restricted mana would have to be allowed to pay for, and
    it must be the same value :func:`pay` is given -- a cost found payable on
    restricted mana and then charged without it strands the payment.

    It is a **parameter rather than something derived from ``source_oid``**,
    because most costs reaching here are not an activation at all: "counter this
    spell unless its controller pays {3}" and a cast's additional cost both
    carry a source object, and neither is casting a spell or activating an
    ability of it. Only the activation paths know to pass
    :func:`ability_purpose`, so only they get restricted mana.
    """
    if cost is None:
        return True
    player = state.players[pid]

    if cost.tap:
        obj = state.objects.get(source_oid) if source_oid is not None else None
        if obj is None or obj.tapped or not obj.on_battlefield:
            return False
        c = chars(state, source_oid)
        if (
            "Creature" in c.types
            and obj.summoning_sick(state.turn)
            and Keyword.HASTE.value not in c.keywords
        ):
            return False
    if cost.untap:
        obj = state.objects.get(source_oid) if source_oid is not None else None
        if obj is None or not obj.tapped:
            return False
    # 118.4: you may pay life down to exactly 0 -- losing is a state-based
    # action afterwards, not a reason the cost was illegal.  `<=` would stop a
    # fetchland being cracked at 1 life, which is precisely when somebody wants
    # to.
    life = life_cost(state, pid, cost, source_oid)
    if life and player.life < life:
        return False
    # "Your life total can't change" makes paying life impossible rather than
    # free: 118.4 makes paying life a loss of life, and a cost that cannot be
    # paid cannot be paid (601.2h). Refused here rather than in `pay`, so the
    # action is never offered -- a War Room offered and then drawing for nothing
    # is the strictly better card this check exists to refuse.
    if life and life_locked(state, pid):
        return False
    if cost.discard and len(_discard_pool(state, pid, cost, source_oid)) < cost.discard:
        return False
    if cost.exile_self:
        # "Exile this artifact" -- the source has to still be on the battlefield
        # to exile, checked for the same reason `discard_self` checks the hand:
        # legality offered the action and the board can move before `pay` runs.
        obj = state.objects.get(source_oid) if source_oid is not None else None
        if obj is None or not obj.on_battlefield:
            return False
    if cost.discard_self:
        # The card must be the payer's to throw away and still be in the zone it
        # is activated from. Checked rather than assumed because legality offers
        # the action and the board can move before `pay` runs -- a discard in
        # response is the obvious way.
        obj = state.objects.get(source_oid) if source_oid is not None else None
        if obj is None or obj.owner != pid or source_oid not in state.players[pid].hand:
            return False
    if cost.exile_self_from_hand:
        # "Exile this card from your hand" -- the same check `discard_self`
        # makes, for the same reason and against the same zone. Not folded into
        # `exile_self` above: that one is Phoenix Down's "exile this artifact",
        # and a card on the battlefield must not be exiled out of a hand it is
        # not in.
        obj = state.objects.get(source_oid) if source_oid is not None else None
        if obj is None or obj.owner != pid or source_oid not in state.players[pid].hand:
            return False
    if cost.exile_from_hand is not None and not _hand_exile_pool(
        state, pid, cost, source_oid
    ):
        return False
    if cost.sacrifice is not None and not _sacrifice_pool(state, pid, cost, source_oid):
        return False
    if cost.return_to_hand is not None and not _return_pool(state, pid, cost, source_oid):
        return False
    if cost.tap_permanents is not None and not _tap_cost_pool(state, pid, cost, source_oid):
        return False
    if cost.untap_permanents is not None and not _untap_cost_pool(
        state, pid, cost, source_oid
    ):
        return False
    if cost.remove_counters is not None:
        obj = state.objects.get(source_oid) if source_oid is not None else None
        kind = str(cost.remove_counters.get("counter", "+1/+1"))
        amount = int(cost.remove_counters.get("amount", 1))
        if obj is None or obj.counter(kind) < amount:
            return False
    if cost.loyalty is not None and cost.loyalty < 0:
        # 606.3: a minus ability may only be activated if there is enough
        # loyalty to pay it. A plus or a zero is always payable, which is why
        # only the negative half is tested -- and why this is not
        # `remove_counters`, which can never add.
        obj = state.objects.get(source_oid) if source_oid is not None else None
        if obj is None or obj.counter("loyalty") < -cost.loyalty:
            return False
    if cost.exile_from_graveyard is not None and not _graveyard_pool(
        state, pid, cost, source_oid
    ):
        return False

    # `cost.mill` is deliberately **not** tested, and the asymmetry with
    # `discard` above is the whole point. 701.13b: "If a player is instructed to
    # mill a number of cards greater than the number of cards in their library,
    # that player mills their entire library." Milling more than you have is a
    # legal action that mills fewer, so the cost is always payable and Millikin
    # still taps for {C} on an empty library. There is no equivalent rule for
    # discarding, which is why an empty hand *does* make `discard` unpayable.

    # Mana last: it is the most expensive check.
    if not cost.mana.is_free() or cost.mana.x_count:
        sources = mana_sources(state, pid, purpose=purpose)
        # A source that is about to be tapped for this cost cannot also pay for it.
        if cost.tap and source_oid is not None:
            sources = [s for s in sources if s.oid != source_oid]
        if solve_payment(
            ability_mana(state, pid, cost, x, source_oid), player.mana_pool, sources
        ) is None:
            return False
    return True


def _discard_pool(
    state: GameState, pid: int, cost: Cost, source_oid: int | None = None
) -> list[int]:
    """Which cards in hand this cost is allowed to throw away.

    The whole hand unless the cost narrows it -- "by discarding a **land**
    card".  Kept as a pool rather than a count so `can_pay` and `pay` cannot
    disagree about whether the cost is payable.

    **The source is never its own fodder.** 601.2a moves a spell to the stack
    before any of its costs are paid, so a card can never discard *itself* to
    pay its own additional cost. Legality prices the cost while the card is
    still in hand, though, so without this the card was offered as fodder --
    and Bitter Triumph ("discard a card or pay 3 life") could eat the very
    spell being cast, which then never resolved. On a card whose hand held
    nothing else the cost instead charged silently nothing, which is a free
    Laughing Mad.

    Cycling is unaffected: `discard_self` is its own flag and does not come
    through here. An activated ability's source is on the battlefield, so
    excluding it from a *hand* pool is a no-op there.
    """
    hand = [oid for oid in state.players[pid].hand if oid != source_oid]
    if cost.discard_selector is None:
        return hand
    from .effects.selectors import matches

    spec = {**dict(cost.discard_selector), "zone": "hand"}
    ctx = EffectContext(state=state, controller=pid)
    return [oid for oid in hand if matches(ctx, oid, spec)]


def _hand_exile_pool(
    state: GameState, pid: int, cost: Cost, source_oid: int | None = None
) -> list[int]:
    """Which cards in hand this cost is allowed to exile -- "a **blue** card".

    Empty when there are fewer than ``count`` of them, the way `_graveyard_pool`
    is, so `can_pay` is a truthiness test and cannot disagree with `pay` about
    whether the cost is payable.

    **The source is never its own fodder**, exactly as in `_discard_pool` and
    for the same rule: 601.2a moves a spell to the stack before any of its costs
    are paid, so Force of Will -- itself a blue card, and still sitting in hand
    while `legality` prices the line -- can never pitch itself.

    Only the payer's own hand is walked, rather than `resolve_pool` over a
    ``zone: "hand"`` selector: the hand is hidden, and an opponent's card must
    not become fodder or leak into a pool the client can count.
    """
    hand = [oid for oid in state.players[pid].hand if oid != source_oid]
    from .effects.selectors import matches

    spec = {**dict(cost.exile_from_hand or {}), "zone": "hand"}
    count = int(spec.pop("count", 1) or 1)
    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    pool = [oid for oid in hand if matches(ctx, oid, spec)]
    return pool if len(pool) >= count else []


def _sacrifice_pool(
    state: GameState, pid: int, cost: Cost, source_oid: int | None
) -> list[int]:
    """Which permanents this cost is allowed to sacrifice.

    The **cost** half of "you can't sacrifice those creatures this turn"
    (701.17b) is this one filter, and it is here rather than at `zones.sacrifice`
    because `can_pay` and `pay` both build the pool through this function: a
    protected permanent is not fodder, so an outlet with nothing else to eat is
    *unpayable* and `legality` never offers the activation. That is what the
    rule says -- the cost cannot be paid -- rather than a cost that is paid and
    then does nothing.

    It covers the activated-ability cost ("Sacrifice a creature: …", an Altar,
    a Bloodthrone Vampire) and the additional cost to cast ("As an additional
    cost to cast this spell, sacrifice a creature"), because `carddef`'s
    `additional_cost` is a `Cost` and goes through `can_pay` like any other.
    Emerge and offering choose their fodder as part of the cast action instead
    of out of a `Cost`, so they are filtered in `legality._emerge_fodder`.
    """
    from .effects.selectors import resolve_pool

    spec = dict(cost.sacrifice or {})
    spec.setdefault("controller", "you")
    spec.setdefault("zone", "battlefield")
    count = int(spec.pop("count", 1) or 1)
    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    pool = [oid for oid in resolve_pool(ctx, spec) if not sacrifice_forbidden(state, oid)]
    return pool if len(pool) >= count else []


def _return_pool(
    state: GameState, pid: int, cost: Cost, source_oid: int | None
) -> list[int]:
    """Which permanents this cost may bounce -- "return a land you control".

    Deliberately a separate pool from ``_sacrifice_pool`` even though the
    selectors look identical, because what happens to the permanent is the
    whole difference: Meloku and Trench Behemoth both replay the land they
    return, and a sacrifice would graveyard it.
    """
    from .effects.selectors import resolve_pool

    spec = dict(cost.return_to_hand or {})
    spec.setdefault("controller", "you")
    spec.setdefault("zone", "battlefield")
    count = int(spec.pop("count", 1) or 1)
    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    pool = resolve_pool(ctx, spec)
    return pool if len(pool) >= count else []


def _tap_cost_pool(
    state: GameState, pid: int, cost: Cost, source_oid: int | None
) -> list[int]:
    """Which permanents this cost may tap -- "five untapped Vampires you control".

    ``tapped: False`` is forced rather than defaulted, because "untapped" is
    part of every printed line of this shape and a cost that could re-tap an
    already-tapped Vampire would be free.

    **Summoning sickness does not apply**, and that is not an oversight: rule
    302.6 restricts the ``{T}`` *symbol in a permanent's own cost*, and this is
    a cost that taps other permanents. Captivating Vampire's ruling is explicit
    that a Vampire which just arrived may be tapped for it, and the source
    itself counts among the five.
    """
    from .effects.selectors import resolve_pool

    spec = dict(cost.tap_permanents or {})
    spec.setdefault("controller", "you")
    spec.setdefault("zone", "battlefield")
    spec["tapped"] = False
    count = int(spec.pop("count", 1) or 1)
    total_power = spec.pop("total_power", None)
    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    pool = resolve_pool(ctx, spec)
    if total_power is not None:
        # Crew. The requirement is a *sum* rather than a headcount, so what
        # makes it payable is the whole pool's power and not its length -- one
        # 4/4 crews a Vehicle that four 0/1s cannot.
        return pool if _total_power(state, pool) >= int(total_power) else []
    return pool if len(pool) >= count else []


def _total_power(state: GameState, oids: list[int]) -> int:
    """Summed **derived** power, which is the whole reason crew is not a count.

    An anthem, a pump spell or a +1/+1 counter all change who can crew a
    Vehicle, so the printed face is the wrong thing to read -- and reading it
    would be wrong in the direction that matters, refusing a crew the board
    plainly supports.
    """
    from .characteristics import chars

    return sum(chars(state, oid).power for oid in oids if oid in state.objects)


def _untap_cost_pool(
    state: GameState, pid: int, cost: Cost, source_oid: int | None
) -> list[int]:
    """Which permanents this cost may untap -- "two tapped creatures you control".

    The mirror of :func:`_tap_cost_pool`, and ``tapped: True`` is forced for the
    same reason its twin forces ``tapped: False``: "tapped" is part of every
    printed line of this shape, and a cost that could "untap" something already
    untapped would be free. Halo Fountain is a combo engine whose whole
    constraint is that the board has to be bent before it can be unbent.

    No ``total_power``. Crew is a printed sum -- "total power 3 or greater" --
    and nothing printed unbends a board by power; the loader refuses one rather
    than letting it load and be ignored.

    Summoning sickness does not apply, for `_tap_cost_pool`'s reason: rule 302.6
    restricts the ``{T}`` symbol in a permanent's *own* cost, and this is a cost
    that reaches other permanents. A creature that arrived tapped this turn --
    off Halo Fountain's own Citizen line, or attacking -- pays it.
    """
    from .effects.selectors import resolve_pool

    spec = dict(cost.untap_permanents or {})
    spec.setdefault("controller", "you")
    spec.setdefault("zone", "battlefield")
    spec["tapped"] = True
    count = int(spec.pop("count", 1) or 1)
    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    pool = resolve_pool(ctx, spec)
    return pool if len(pool) >= count else []


def _graveyard_pool(
    state: GameState, pid: int, cost: Cost, source_oid: int | None
) -> list[int]:
    from .effects.selectors import resolve_pool

    spec = dict(cost.exile_from_graveyard or {})
    spec.setdefault("controller", "you")
    spec["zone"] = "graveyard"
    count = int(spec.pop("count", 1) or 1)
    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    pool = resolve_pool(ctx, spec)
    return pool if len(pool) >= count else []


def pay(
    state: GameState,
    pid: int,
    cost: Cost | None,
    source_oid: int | None,
    *,
    x: int = 0,
    extra_generic: int = 0,
    purpose: SpendPurpose | None = None,
    record_colors_on: int | None = None,
) -> Generator[Any, list[int], bool]:
    """Pay a cost, asking the player for any choices it requires.

    Returns ``True`` on success.  Callers only invoke this after :func:`can_pay`,
    so a ``False`` return means the game state changed underneath them.

    ``purpose`` is what the mana is being spent on, and must be the same value
    legality used when it decided this was payable -- restricted mana is offered
    or withheld by that alone.
    """
    # A payment is one group, the way an effect op is: an
    # `exile_from_graveyard` cost that takes three cards takes them at
    # once. See `triggers._queue`.
    state.event_batch += 1
    if cost is None and not extra_generic:
        return True
    cost = cost or Cost()
    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)

    if cost.tap and source_oid is not None:
        tap_permanent(state, source_oid)
    if cost.untap and source_oid is not None:
        obj = state.objects.get(source_oid)
        if obj is not None:
            obj.tapped = False
            state.bump_chars()

    # Mana is paid first: activating mana abilities happens before other costs
    # are paid (rule 601.2g), so sacrificing a mana creature as part of the cost
    # cannot strand the payment.
    req = ability_mana(state, pid, cost, x, source_oid)
    if extra_generic:
        # Clamped at zero: `extra_generic` is negative for a cost *reduction*,
        # and "costs {X} less" never reaches through the generic part into the
        # coloured pips however large X gets.
        req = req.with_generic(req.generic + extra_generic)
    if req.total and not pay_mana(
        state,
        pid,
        req,
        exclude_oid=source_oid if cost.tap else None,
        purpose=purpose,
        record_colors_on=record_colors_on,
    ):
        return False

    if cost.pay_life:
        # A Phyrexian pip bought with life arrives here, as `pay_life` on a cost
        # `Game._cast` assembles -- rule 107.4f is a *way of paying one symbol*,
        # not a separate cost, and `ManaCost.paying_phyrexian` has already taken
        # the symbol out of the mana half above. Paid in the same `pay` call and
        # so in the same event batch, because the mana and the life are one
        # payment however the printed symbol is read.
        lose_life(state, pid, life_cost(state, pid, cost, source_oid), source=source_oid)

    if cost.discard:
        pool = _discard_pool(state, pid, cost, source_oid)
        picked = yield from ask_objects(
            ctx, "Discard", pool, cost.discard, cost.discard, pid, "discard"
        )
        yield from _discard(state, pid, picked)

    if cost.discard_self and source_oid is not None:
        # No `ask_objects`: which card goes is not a choice, it is *this* card.
        # That is the whole difference from `discard`, and asking would let the
        # player cycle by pitching something else.
        yield from _discard(state, pid, [source_oid])

    if cost.exile_self and source_oid is not None:
        # No `ask_objects` and no selector: which permanent goes is not a
        # choice, it is *this* one -- the same reason `discard_self` asks
        # nothing. Paid here, as the ability goes on the stack, so the source is
        # gone before it can be responded to or feed its own effects.
        exile_object(state, source_oid, cause="cost")

    if cost.exile_self_from_hand and source_oid is not None:
        # "Exile this card from your hand" -- `discard_self`'s shape with the
        # other destination. No `ask_objects` and no selector for the same
        # reason: which card goes is not a choice, it is *this* one, and asking
        # would let a Simian Spirit Guide be "activated" by exiling something
        # else and staying in hand.
        exile_object(state, source_oid, cause="cost")

    if cost.exile_from_hand is not None:
        spec = dict(cost.exile_from_hand)
        count = int(spec.pop("count", 1) or 1)
        pool = _hand_exile_pool(state, pid, cost, source_oid)
        picked = yield from ask_objects(
            ctx, "Exile from your hand", pool, count, count, pid, "exile_cost"
        )
        for oid in picked:
            exile_object(state, oid, cause="cost")

    if cost.sacrifice is not None:
        spec = dict(cost.sacrifice)
        count = int(spec.pop("count", 1) or 1)
        pool = _sacrifice_pool(state, pid, cost, source_oid)
        picked = yield from ask_objects(ctx, "Sacrifice", pool, count, count, pid, "sacrifice")
        for oid in picked:
            # The thing being paid for, so the log can say what the creature
            # was sacrificed *to* rather than only that it was sacrificed.
            sacrifice_object(state, oid, by=source_oid)

    if cost.return_to_hand is not None:
        spec = dict(cost.return_to_hand)
        count = int(spec.pop("count", 1) or 1)
        pool = _return_pool(state, pid, cost, source_oid)
        picked = yield from ask_objects(
            ctx, "Return to hand", pool, count, count, pid, "return_cost"
        )
        for oid in picked:
            bounce_object(state, oid, by=source_oid)

    if cost.tap_permanents is not None:
        spec = dict(cost.tap_permanents)
        count = int(spec.pop("count", 1) or 1)
        total_power = spec.pop("total_power", None)
        pool = _tap_cost_pool(state, pid, cost, source_oid)
        if total_power is None:
            picked = yield from ask_objects(ctx, "Tap", pool, count, count, pid, "tap_cost")
            for oid in picked:
                tap_permanent(state, oid)
        else:
            # Crew, asked one creature at a time. `ask_objects` takes counts,
            # not sums, so a single subset question could be answered with a
            # set that does not reach the number -- and a cost cannot fail
            # halfway. Asking repeatedly until the total is met is also how a
            # player crews at a table: each creature is a real choice, and the
            # question stops the moment the Vehicle is crewed rather than
            # taking everything that could have helped.
            needed = int(total_power)
            remaining = list(pool)
            while needed > 0 and remaining:
                picked = yield from ask_objects(
                    ctx, f"Tap to crew ({needed} more power)", remaining, 1, 1, pid, "tap_cost"
                )
                if not picked:
                    break
                chosen = picked[0]
                needed -= _total_power(state, [chosen])
                tap_permanent(state, chosen)
                remaining.remove(chosen)

    if cost.untap_permanents is not None:
        spec = dict(cost.untap_permanents)
        count = int(spec.pop("count", 1) or 1)
        pool = _untap_cost_pool(state, pid, cost, source_oid)
        picked = yield from ask_objects(ctx, "Untap", pool, count, count, pid, "untap_cost")
        for oid in picked:
            untap_permanent(state, oid)

    if cost.remove_counters is not None and source_oid is not None:
        from .primitives import remove_counters

        remove_counters(
            state,
            source_oid,
            str(cost.remove_counters.get("counter", "+1/+1")),
            int(cost.remove_counters.get("amount", 1)),
        )

    if cost.loyalty is not None and source_oid is not None:
        # A **cost**, so it is paid as the ability goes on the stack and is not
        # refunded if the ability is countered or does nothing -- which is what
        # makes a planeswalker's loyalty spendable in response to removal.
        from .primitives import add_counters, remove_counters

        if cost.loyalty > 0:
            add_counters(state, source_oid, "loyalty", cost.loyalty)
        elif cost.loyalty < 0:
            remove_counters(state, source_oid, "loyalty", -cost.loyalty)

    if cost.mill:
        # No `ask_objects`: the cards come off the top of the library, so there
        # is nothing to choose. `mill_cards` already stops at an empty library,
        # which is 701.13b and the reason `can_pay` does not gate on this.
        from .primitives import mill_cards

        mill_cards(state, pid, cost.mill)

    if cost.exile_from_graveyard is not None:
        spec = dict(cost.exile_from_graveyard)
        count = int(spec.pop("count", 1) or 1)
        pool = _graveyard_pool(state, pid, cost, source_oid)
        picked = yield from ask_objects(ctx, "Exile from your graveyard", pool, count, count, pid, "exile_cost")
        for oid in picked:
            exile_object(state, oid, cause="cost")

    return True


def _discard(state: GameState, pid: int, oids):
    """Discard as a *cost*, through the madness replacement.

    Rule 702.35a does not care why the card was discarded -- a cycling cost and
    a Wheel are both discards -- so the cost path goes through the same route
    the effect path does. Imported here rather than at module scope because
    `replacements` needs this module.
    """
    from .replacements import discard as discard_with_replacements

    return (yield from discard_with_replacements(state, pid, oids))


def pay_mana(
    state: GameState,
    pid: int,
    req: Requirement,
    *,
    exclude_oid: int | None = None,
    purpose: SpendPurpose | None = None,
    record_colors_on: int | None = None,
) -> bool:
    """Tap sources and deduct ``req`` from the pool.

    ``record_colors_on`` is the object to write the payment's provenance onto:
    the colours actually spent (sunburst and converge) and the permanents whose
    mana abilities made them (Path of Ancestry's "when that mana is spent").
    This is the only moment either is knowable -- once the pool is decremented,
    one blue mana is indistinguishable from another and so is the land that made
    it -- so a card that reads them later has to be handed them here.
    """
    player = state.players[pid]
    sources = mana_sources(state, pid, purpose=purpose)
    if exclude_oid is not None:
        sources = [s for s in sources if s.oid != exclude_oid]
    payment = solve_payment(req, player.mana_pool, sources)
    if payment is None:
        return False
    for oid, ability_index, option_index in payment.taps:
        activate_mana_ability(state, oid, ability_index, pid, option_index)
    spent = player.mana_pool.spend(req)
    if record_colors_on is not None and (obj := state.objects.get(record_colors_on)):
        obj.colors_spent = spent.colors
        obj.mana_sources_spent = spent.sources
    state.emit(
        EventType.MANA_SPENT,
        player=pid,
        amount=req.total,
        colors=sorted(spent.colors),
        sources=sorted(spent.sources),
    )
    return True


def activate_mana_ability(
    state: GameState, oid: int, ability_index: int, pid: int, option_index: int = 0
) -> None:
    """Tap a permanent for mana.  Mana abilities never use the stack.

    The produced mana comes straight from the ability's precomputed
    ``mana_options`` rather than from running its effects.  A modal mana ability
    ("Add {G} or {U}") would otherwise ask its controller to pick a mode, and a
    mana ability must never stop to ask anything.

    A *variable* ability ("Add {G} for each +1/+1 counter") is the one part read
    from the board, and it is read **before** the tap. The payment solver
    enumerates sources while they are still untapped, so measuring after tapping
    would let the offer and the payment see two different boards -- the exact
    disagreement `mana_produced` exists to prevent.
    """
    ability = abilities_of(state, oid)[ability_index]

    obj = state.objects.get(oid)
    is_land = obj is not None and "Land" in chars(state, oid).types
    doubled = is_land and obj is not None and player_doubles_land_mana(state, obj.controller)
    options = mana_options_of(state, oid, ability)
    if option_index >= len(options):
        # The board changed what this ability offers between the plan and the
        # payment. A reflecting ability is the first whose options are not
        # constant, so this refuses rather than indexing into another colour.
        raise DslError(
            f"mana ability {ability.index} of {state.card(oid).name} no longer "
            f"offers option {option_index}"
        )
    produced = mana_produced(
        options[option_index],
        doubled=doubled,
        times=mana_amount(state, oid, ability),
    )

    if ability.cost is not None and ability.cost.tap:
        tap_permanent(state, oid)

    # Tagged with the permanent that made it. The tag is the whole of what
    # Path of Ancestry's "when that mana is spent" reads back, and it is
    # knowable only here -- a pool of six integers cannot say where a pip
    # came from once it has landed in it.
    state.players[pid].mana_pool.add_tuple(produced, source=oid)
    state.emit(
        EventType.MANA_ADDED, player=pid, source=oid, mana=format_symbols(produced)
    )
    if ability.mana_rider:
        _run_mana_rider(state, oid, pid, ability)
    if is_land and obj is not None:
        _lands_tapped_for_mana(state, obj)


def _run_mana_rider(state: GameState, oid: int, pid: int, ability: Any) -> None:
    """"…This land deals 1 damage to you", inline and off the stack.

    Every tap for mana reaches here -- the payment solver's automatic taps go
    through ``pay_mana`` and a player's own activation through ``Game.apply`` --
    so the rider has exactly one home and cannot be skipped by one path and
    applied by the other.  That matters more than it sounds: the solver taps a
    painland without asking, and a rider that only ran on manual activation
    would make the land painless exactly when the engine used it for you.

    Run to exhaustion rather than suspended.  Nothing here can ask a question
    (`loader.vocabulary.MANA_RIDER_OPS` is the whitelist that guarantees it), and there is
    nowhere to suspend to: this is inside cost payment, with no stack and no
    priority window.
    """
    from .effects import execute

    ctx = EffectContext(state=state, controller=pid, source_oid=oid)
    generator = execute(ctx, list(ability.mana_rider))
    for _ in generator:  # pragma: no cover - the whitelist forbids yielding
        raise DslError(
            f"a mana ability's rider asked a question ({ability.text!r}); "
            f"mana abilities are activated during payment and cannot stop"
        )


def _lands_tapped_for_mana(state: GameState, land: Any) -> None:
    """Vorinclex's second half: an opponent's land does not untap next turn.

    Applied here rather than as a triggered ability because tapping for mana
    happens *inside* payment, where nothing can go on the stack -- the same
    reason the doubling above is inline.  One-shot, so it is
    ``skip_next_untap`` rather than the `frozen_by` lock, which lasts as long as
    its source is on the battlefield: these are different lifetimes and using
    either for the other would be wrong.
    """
    from .characteristics import players_freezing_opponent_lands

    freezers = players_freezing_opponent_lands(state)
    if any(pid != land.controller for pid in freezers):
        land.skip_next_untap = True


def land_drops_available(state: GameState, pid: int) -> int:
    """How many more lands this player may play this turn."""
    from .characteristics import player_extra_land_drops

    player = state.players[pid]
    return 1 + player.extra_land_drops + player_extra_land_drops(state, pid) - player.lands_played


def commander_cost(state: GameState, oid: int) -> int:
    """Extra generic mana owed for casting a commander from the command zone."""
    obj = state.objects.get(oid)
    if obj is None:
        return 0
    return 2 * state.players[obj.owner].commander_tax.get(oid, 0)


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


def variant_reduction(
    state: GameState, pid: int, cost: Cost | None, source_oid: int | None
) -> int:
    """"This spell costs {X} less to cast **this way**."

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


def _reduction_matches(
    state: GameState, pid: int, filt: Any, source_oid: int | None = None
):
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
        if "blocking" in filt and bool(combat and combat.blocking(oid)) != bool(
            filt["blocking"]
        ):
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


def zone_of(state: GameState, oid: int) -> Zone:
    return state.objects[oid].zone
