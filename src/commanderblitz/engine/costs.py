"""Paying costs.

Mana payment is automatic (see :mod:`commanderblitz.engine.mana`): an action never
carries a payment, and legality only offers a cast or activation when the solver
can find a set of sources to tap.  Non-mana costs (sacrifice, discard, pay life)
may need a choice, so :func:`pay` is a generator.
"""

from __future__ import annotations

from collections.abc import Generator, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from .carddef import Ability, CardDef, Cost
from .characteristics import abilities_of, chars, crew_power_bonus, mana_source_traits
from .cost_reduction import reduction_amount
from .effects import execute
from .effects.behold import announce_beheld, behold_count, behold_pool
from .effects.conditions import evaluate
from .effects.context import EffectContext, ask_mode, ask_objects
from .effects.counter_removal import remove_counters_one_at_a_time
from .effects.selectors import matches, resolve_pool
from .effects.values import evaluate_value
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
    ManaOrigin,
    ManaRestriction,
    ManaSource,
    ManaSpendTrigger,
    Requirement,
    RestrictionGroup,
    SpendPurpose,
    format_symbols,
    solve_payment,
)
from .objects import MINUS_ONE
from .player_statics import (
    ability_cost_reduction,
    counters_prohibited,
    mana_added_on_tap,
    player_cant_activate,
    player_doubles_mana_from,
    player_extra_land_drops,
    player_pays_life_for_black,
    player_spends_mana_as_any_color,
    players_freezing_opponent_lands,
)
from .primitives import (
    add_counters,
    life_locked,
    lose_life,
    mill_cards,
    pay_energy,
    remove_counters,
    tap_permanent,
    untap_or_stun,
    untap_permanent,
)
from .replacements import discard as discard_with_replacements
from .temp_effects import sacrifice_forbidden
from .zones import bounce as bounce_object
from .zones import exile as exile_object
from .zones import sacrifice as sacrifice_object
from .zones import snapshot as capture_snapshot

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
        out.extend(source for source in _sources_of(state, oid, obj) if source.permits(purpose))
    return out


def spell_purpose(card: CardDef) -> SpendPurpose:
    """What restricted mana would have to allow, to *cast* this card.

    Subtypes and supertypes as well as types, because the printed clause names
    any of the three: "…only to cast a creature spell" is a type, "…only to cast
    Vampire, Cleric, and/or Demon spells" is three subtypes, and Delighted
    Halfling's "…only to cast a **legendary** spell" is a supertype. One flat set
    of lowercased names on both sides, matched by :meth:`ManaSource.permits` --
    which is where the printed "and/or" (an any-of) and "a creature spell **of**
    the chosen type" (an all-of) are told apart.

    The supertypes were the quiet omission. `mana._restriction_name`
    accepts any alphabetic word, so "legendary" loaded clean and then matched
    nothing on every card in the game -- mana that was permanently unspendable,
    which reads on the board as a land that taps for nothing rather than as an
    error.

    Tagged :data:`CAST`, which is the half of the purpose that keeps every
    restriction shipped before Secluded Courtyard meaning what it printed.

    The two **numbers** ride along beside the names for the same reason the
    supertypes had to: Helga, Skittish Seer's "…only to cast creature spells
    with mana value 4 or greater or creature spells with {X} in their mana
    costs" names no type for either clause, and a purpose carrying names alone
    would leave both unaskable -- so the restriction would have to be written as
    a bare "creature" and fund every creature spell ever printed.

    `mana_cost.x_count` rather than a mana value of X, for rule 107.3's reason:
    a Fireball cast for X=0 is still "a spell with {X} in its mana cost", and
    202.3b scores that X as 0 -- so `mana_value` catches Fireball and Shock
    together or neither, and the symbol question is a different question.
    """
    return SpendPurpose(
        kind=CAST,
        names=frozenset(
            t.lower() for t in (*card.types, *card.subtypes, *card.supertypes)
        ),
        mana_value=card.mana_value,
        x_in_mana_cost=card.mana_cost.x_count > 0,
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
    card = state.card_of(obj)
    if obj.on_battlefield:
        c = chars(state, oid)
        names = (*c.types, *c.subtypes, *c.supertypes)
    else:
        names = (*card.types, *card.subtypes, *card.supertypes)
    # The cost predicates are answered here too, off the printed face, rather
    # than left `None`. A source has a mana value and a printed cost whether or
    # not any card asks about them, and answering honestly means the day one
    # prints "or activate an ability of a permanent with mana value 4 or
    # greater" this is not the place that quietly said no.
    return SpendPurpose(
        kind=ACTIVATE,
        names=frozenset(t.lower() for t in names),
        mana_value=card.mana_value,
        x_in_mana_cost=card.mana_cost.x_count > 0,
    )


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
        other=restriction.other,
    )


def _resolve_groups(
    groups: tuple[RestrictionGroup, ...], chosen: str | None
) -> tuple[RestrictionGroup, ...]:
    out: list[RestrictionGroup] = []
    for group in groups:
        if CHOSEN_TYPE not in group.names():
            out.append(group)
        elif chosen is not None:
            # Both halves, though only `required` can hold the sentinel today --
            # the loader refuses a negated chosen type, since no card prints
            # "spend this only to cast a spell that is *not* the chosen type".
            # Substituting both anyway means the day one does, this is not the
            # place that quietly kept the sentinel.
            # `replace` rather than a fresh `RestrictionGroup`, so a predicate
            # the group also carries survives the substitution. Rebuilt from
            # the two name sets alone, a "creature spell of the chosen type
            # with mana value 4 or greater" would quietly lose the comparison
            # the instant a type was chosen -- which is the one moment the
            # restriction starts being read.
            out.append(
                replace(
                    group,
                    required=_swap(group.required, chosen),
                    forbidden=_swap(group.forbidden, chosen),
                )
            )
    return tuple(out)


def _swap(names: frozenset[str], chosen: str) -> frozenset[str]:
    if CHOSEN_TYPE not in names:
        return names
    return (names - {CHOSEN_TYPE}) | {chosen.lower()}


def _by_permanent(sources: Sequence[ManaSource]) -> dict[int, list[ManaSource]]:
    """Sources grouped by the permanent they tap, first-seen order kept.

    A :class:`ManaSource` is one *ability*; a Talisman or a painland has two
    tap abilities and so appears twice.  Every count of "how much mana" has to
    go through here, because the permanent taps once whichever ability is used.
    """
    out: dict[int, list[ManaSource]] = {}
    for source in sources:
        out.setdefault(source.oid, []).append(source)
    return out


def permanents_output(sources: Sequence[ManaSource]) -> int:
    """Upper bound on mana from these sources: each permanent taps once, for
    its best ability."""
    return sum(max(s.max_output() for s in group) for group in _by_permanent(sources).values())


def available_mana(state: GameState, pid: int) -> int:
    """Upper bound on mana this player could produce, for heuristics and encoding."""
    pool = state.players[pid].mana_pool.total()
    return pool + permanents_output(mana_sources(state, pid))


def sources_by_controller(state: GameState) -> dict[int, list[ManaSource]]:
    """Every player's mana sources, from a single walk of the battlefield.

    :func:`mana_sources` filters the whole battlefield per player, so serializing
    a four-player pod walked it four times over.  The per-object work is
    identical either way; this just partitions instead of re-scanning.  Pass the
    result to :func:`mana_availability` as ``sources``.

    Per ability, exactly like :func:`mana_sources` -- this is the solver-shaped
    list.  Collapsing to one entry per permanent is :func:`mana_availability`'s
    job, since only the client wants that shape.
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
    return ability.is_mana_ability and bool(ability.mana_options) and not solver_taps(ability)


def _sources_of(state: GameState, oid: int, obj: Any) -> list[ManaSource]:
    """The tap-only mana abilities of one untapped permanent."""
    # A mana ability is an activated ability, so "its activated abilities can't
    # be activated this turn" stops it here as well as in `legality`. Filtered in
    # this one helper because both entry points above go through it.
    if obj.abilities_locked:
        return []
    # Grand Abolisher, Myrel. 605.1a: a mana ability *is* an activated ability,
    # and the printed line excepts nothing -- so the board's standing
    # prohibition is asked here for the same reason the object's own flag is,
    # one line above. Without it a locked permanent would still tap for mana,
    # which is most of what the lock is for.
    if player_cant_activate(state, obj.controller, oid):
        return []
    card = state.card_of(obj)
    c = chars(state, oid)
    is_creature = "Creature" in c.types
    if is_creature and obj.summoning_sick(state.turn) and Keyword.HASTE.value not in c.keywords:
        return []
    is_land = "Land" in c.types
    # Vorinclex over a land, Kinnan over anything else. Asked of the permanent
    # rather than recomputed from `is_land` here, so the two doubling statics
    # cannot drift apart between this offer and the payment below.
    doubled = player_doubles_mana_from(state, obj.controller, oid)
    # Crypt Ghast. Every ability reaching the solver is tap-only, so each one
    # is "tapping it for mana" (106.12) and each option gets the extra -- asked
    # per option, since what the tap made can decide it (Forsaken Monument).
    def _with_extra(produced: tuple[int, ...]) -> tuple[int, ...]:
        return plus_mana(produced, mana_added_total(state, obj.controller, oid, produced))

    out: list[ManaSource] = []
    for ability in abilities_of(state, oid):
        if not solver_taps(ability):
            continue
        # "{T}: Add {U}. Activate only if you control a Plains or an Island."
        # -- Floodfarm Verge. 602.5c restricts a mana ability exactly as it does
        # any other, and legality's `_activation_allowed` never sees this one:
        # a tap-only mana ability is the solver's and is never offered. Skipped
        # here, the Verge alone paid {U} for anything.
        if ability.activation_condition is not None and not _mana_condition_met(
            state, obj.controller, oid, ability
        ):
            continue
        out.append(
            ManaSource(
                oid=oid,
                ability_index=ability.index,
                options=(
                    tuple(
                        _with_extra(
                            mana_produced(
                                option,
                                doubled=doubled,
                                times=mana_amount(state, oid, ability),
                            )
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


def _mana_condition_met(state: GameState, pid: int, oid: int, ability: Ability) -> bool:
    """ "Activate only if …" on a mana ability, asked as legality asks it."""

    ctx = EffectContext(state=state, controller=pid, source_oid=oid)
    return bool(evaluate(ctx, ability.activation_condition))


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
    if ability.mana_split:
        # A split ability's size is already inside each option -- the
        # compositions `_split_options` builds each sum to X -- so multiplying
        # by X here would produce X*X mana. The amount is read once, there.
        return 1
    if ability.mana_amount is None:
        return 1

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
    if ability.mana_split:
        return _split_options(state, oid, ability)
    if ability.mana_chosen_color:
        return _chosen_color_options(state, oid, ability)
    if ability.mana_identity:
        return _identity_options(state, oid, ability)
    if ability.mana_colors_of is not None:
        return _colors_of_options(state, oid, ability)
    if ability.mana_each_color_among is not None:
        return _each_color_among_options(state, oid, ability)
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
                    if not amount:
                        continue
                    # "any **color**" drops the sixth type of mana here;
                    # "any **type**" keeps it. That one index is the entire
                    # difference between Exotic Orchard and Reflecting Pool: a
                    # Pool beside a Wastes taps for {C}, an Orchard beside one
                    # taps for nothing. Only the *type list* widens -- the
                    # question, the recursion and the skip above are the same,
                    # so a Pool still offers nothing the board cannot make.
                    if index == SYMBOL_INDEX[COLORLESS] and not ability.mana_reflects_any_type:
                        continue
                    colors.add(index)

    out: list[tuple[int, ...]] = []
    for option in ability.mana_options:
        if any(amount and i in colors for i, amount in enumerate(option)):
            out.append(option)
    return tuple(out)


def _colors_of_options(state: GameState, oid: int, ability: Ability) -> tuple[tuple[int, ...], ...]:
    """The five-colour superset narrowed to the colours *printed on a card*.

    "{T}: Add one mana of any of the exiled card's colors" -- Chrome Mox. The
    sibling of `mana_options_of`'s reflecting branch, asking a different
    question of the same shape: `reflecting` polls each matched object's own
    mana **abilities**, and the card this one reads is a nonartifact, nonland
    card lying in exile, which has none. Written as `reflecting` the Mox taps
    for nothing whatever it imprinted.

    **Nothing imprinted is nothing added.** An unimprinted Mox matches no card,
    so this is the empty tuple and the solver simply never picks it -- the same
    real answer `_identity_options` gives a colourless commander and
    `_chosen_color_options` gives a permanent that has not chosen yet. The near
    miss is a `choose_mode` over five `add_mana`s, which taps for any colour
    with nothing imprinted at all: a strictly better card than the printed one.

    Colourless is not a colour (105.1), so an imprinted colourless card offers
    nothing either -- that is the printed sentence, not an oversight, and it is
    why there is no `any_type` here.

    Colours come from `chars` on the battlefield and off the card everywhere
    else, matching what a selector's own `colors` filter reads, so a Mox Amber
    reading legendary creatures sees a repainted one as it now is.

    It **only looks**: `resolve_pool` over a zone asks nothing and puts nothing
    on the stack, which is what keeps this a mana ability for 605.1a.
    """
    obj = state.objects.get(oid)
    if obj is None:  # pragma: no cover - callers hold a live permanent
        return ()
    ctx = EffectContext(state=state, controller=obj.controller, source_oid=oid)
    colors: set[int] = set()
    for other in resolve_pool(ctx, ability.mana_colors_of):
        found = state.objects.get(other)
        if found is None:  # pragma: no cover - resolve_pool returns live oids
            continue
        printed = chars(state, other).colors if found.on_battlefield else state.card_of(found).colors
        for symbol in printed:
            index = SYMBOL_INDEX.get(symbol)
            if index is not None and index != SYMBOL_INDEX[COLORLESS]:
                colors.add(index)
    return tuple(
        option
        for option in ability.mana_options
        if any(amount and i in colors for i, amount in enumerate(option))
    )


def _each_color_among_options(
    state: GameState, oid: int, ability: Ability
) -> tuple[tuple[int, ...], ...]:
    """**One** option holding one mana of every colour the selector shows.

    "Vivid — {T}: For each color among permanents you control, add one mana of
    that color." Bloom Tender. The same board question `_colors_of_options`
    asks, answered in the other shape: that one hands back one *single-symbol
    option per colour* and the payer picks one, and this one hands back a single
    multi-symbol option and the payer gets all of it. A board showing three
    colours taps this for three mana, one of each, and never asks which.

    That is the whole capability, and why `mana_colors_of` over the same
    selector is a different card rather than a rougher one: written that way
    Bloom Tender is Mox Amber, adding one mana off a five-colour board.

    One option and not several is also what keeps the ability decision-free for
    605.1a — `legality._mana_option_indices` offers one chip per option, so a
    list of colours here would put a question in front of the player that the
    printed card does not ask.

    Colourless is not a colour (105.1), so a board of Wastes and Eldrazi offers
    nothing and the empty tuple is the real answer — the same one an unimprinted
    Mox and a colourless commander give, and the solver simply never picks a
    source that produces nothing.

    Colours are read off `chars` on the battlefield and off the card elsewhere,
    the way `_colors_of_options` reads them, so a permanent repainted by a
    continuous effect counts as it now is.

    It **only looks**: `resolve_pool` asks nothing and puts nothing on the stack.
    """
    obj = state.objects.get(oid)
    if obj is None:  # pragma: no cover - callers hold a live permanent
        return ()
    ctx = EffectContext(state=state, controller=obj.controller, source_oid=oid)
    colors: set[int] = set()
    for other in resolve_pool(ctx, ability.mana_each_color_among):
        found = state.objects.get(other)
        if found is None:  # pragma: no cover - resolve_pool returns live oids
            continue
        present = chars(state, other).colors if found.on_battlefield else state.card_of(found).colors
        for symbol in present:
            index = SYMBOL_INDEX.get(symbol)
            if index is not None and index != SYMBOL_INDEX[COLORLESS]:
                colors.add(index)
    if not colors:
        return ()
    produced = [0] * len(SYMBOLS)
    for index in colors:
        produced[index] = 1
    return (tuple(produced),)


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

    "{T}: Add {R} or one mana of the chosen color" -- the Thriving lands --
    carries its fixed options in `mana_chosen_color_fixed`. Those are offered
    always and first, in printed order, and the chosen colour follows once one
    is named: {R} alone before the choice, {R} and {G} after a green one. A
    chosen colour the fixed options already make is not offered twice.

    It **only looks**: reading `chosen_color` asks nothing and puts nothing on
    the stack, so this stays a mana ability for 605.1a.
    """
    fixed = ability.mana_chosen_color_fixed
    obj = state.objects.get(oid)
    chosen = obj.chosen_color if obj is not None else None
    if chosen is None:
        return fixed
    index = SYMBOL_INDEX.get(chosen)
    if index is None:  # pragma: no cover - the loader only writes WUBRG here
        return fixed
    live = tuple(
        option
        for option in ability.mana_options
        if option[index] and sum(option) == 1 and option not in fixed
    )
    return fixed + live


#: How many ways a split may be offered before it is truncated. Two colours and
#: a power of nine is ten options, which is nothing; five colours and a large X
#: is combinatorial. The cap is far above any printed card -- Vivi is the only
#: one in the pool and splits two ways -- and exists so a pathological board
#: cannot hang the solver rather than to express a rule.
MAX_SPLIT_OPTIONS = 64


def _split_options(state: GameState, oid: int, ability: Ability) -> tuple[tuple[int, ...], ...]:
    """Every way to divide X mana among the named colours.

    "Add X mana in any combination of {U} and/or {R}, where X is Vivi
    Ornitier's power." The combination is a *choice*, so it is offered as one
    option per composition and the solver picks the one that pays the spell --
    which is exactly what a player does at a table.

    X is read here, at activation, through `_split_amount`; it is the same
    value expression `mana_amount` reads, and `mana_amount` returns 1 for a
    split ability so the size is not applied twice.

    X of zero yields nothing -- a Vivi with 0 power taps for no mana, which is
    the printed card.
    """
    total = _split_amount(state, oid, ability)
    indices = [SYMBOL_INDEX[c] for c in ability.mana_split if c in SYMBOL_INDEX]
    if total <= 0 or not indices:
        return ()

    rows: list[list[int]] = []

    def walk(depth: int, left: int, so_far: list[int]) -> None:
        if len(rows) >= MAX_SPLIT_OPTIONS:
            return
        if depth == len(indices) - 1:
            rows.append([*so_far, left])
            return
        for take in range(left + 1):
            walk(depth + 1, left - take, [*so_far, take])

    walk(0, total, [])

    options = []
    for row in rows:
        produced = [0] * len(SYMBOLS)
        for index, amount in zip(indices, row, strict=True):
            produced[index] += amount
        options.append(tuple(produced))
    return tuple(options)


def _split_amount(state: GameState, oid: int, ability: Ability) -> int:
    """X for a split ability, read the way `mana_amount` reads every other one."""
    if ability.mana_amount is None:
        return 0

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


def _identity_options(state: GameState, oid: int, ability: Ability) -> tuple[tuple[int, ...], ...]:
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


def mana_added_total(
    state: GameState, pid: int, oid: int, produced: Sequence[int]
) -> tuple[int, ...] | None:
    """Everything ``add_mana_on_tap`` statics add when ``pid`` taps ``oid`` for
    ``produced``, summed.

    ``None`` when nothing applies. Read by the planner (`_sources_of`) and the
    chip label, while `activate_mana_ability` reads the same pairs pip by pip
    with their sources -- so the offer and the payment cannot disagree about how
    much a Swamp makes. Per option, because Forsaken Monument's "tap a permanent
    for {C}" adds to a painland's {C} and not to its {R}.
    """
    added = mana_added_on_tap(state, pid, oid, produced)
    if not added:
        return None
    total = [0] * len(added[0][1])
    for _, mana in added:
        for i, v in enumerate(mana):
            total[i] += v
    return tuple(total)


def plus_mana(option: Sequence[int], extra: Sequence[int] | None) -> tuple[int, ...]:
    """``option`` with the triggered-mana ``extra`` added on top."""
    if extra is None:
        return tuple(option)
    return tuple(a + b for a, b in zip(option, extra, strict=True))


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

    *Simplification*: a dual land adds one mana of **a** type it produced rather
    than offering a free choice of which, because a mana ability cannot ask.
    Recorded in ``docs/rules-coverage.md`` alongside the other automatic-mana
    trades.

    ``times`` is the variable-output multiplier from :func:`mana_amount`, and it
    is threaded through *here* for the same reason the doubling is: this is the
    one place both the offer and the payment come through, so they cannot be
    given different numbers.

    **One mana, not twice the mana.** The printed line is "add *one* mana of any
    type that permanent produced", and for the one-mana sources this family was
    written against -- a mana dork, a basic land -- one more and twice as many
    are the same number, which is why doubling the whole tuple read correctly
    for years. They part company the moment the source makes two: a Sol Ring
    under Kinnan is ``{C}{C}{C}``, not ``{C}{C}{C}{C}``, and Ancient Tomb under
    Vorinclex is ``{C}{C}{C}``. Doubling was wrong in the strictly-better
    direction, and silently, since nothing in the pool exercised it.
    """
    produced = tuple(v * times for v in option) if times != 1 else tuple(option)
    if not doubled:
        return produced
    # Which type the extra mana is, when the source made more than one, is the
    # choice a mana ability may not stop to ask about. Taken as the first symbol
    # in WUBRGC order that the source actually produced -- deterministic, so the
    # offer in `_sources_of` and the payment in `activate_mana_ability` cannot
    # disagree, which is the one failure this helper exists to prevent.
    extra = list(produced)
    for i, v in enumerate(produced):
        if v:
            extra[i] += 1
            break
    return tuple(extra)


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

    One entry per **permanent**, not per ability.  A Talisman prints "{T}: Add
    {C}" and "{T}: Add {B} or {R}" -- two abilities, one tap -- and shows up
    here as a single source whose ``options`` are ``[["C"], ["B"], ["R"]]`` and
    whose ``amount`` is 1.  Listed per ability it rendered as two pips and
    claimed a mana the permanent cannot make.  ``amount`` is the best single
    tap, so a permanent whose abilities differ in size ("{C}{C}" beside "{G}")
    reports the larger; an upper bound, like ``total``.

    ``sources`` lets a caller serializing every seat share one battlefield walk;
    see :func:`sources_by_controller`.  Omitted, it is computed here as before.
    """
    pool = state.players[pid].mana_pool
    if sources is None:
        sources = mana_sources(state, pid)
    entries: list[dict[str, Any]] = []
    for oid, group in _by_permanent(sources).items():
        # Every yield any of the permanent's abilities could choose, each as
        # the symbols it actually makes.  "{T}: Add {G} or {U}" is
        # [["G"], ["U"]]; "{T}: Add {G}{U}" is [["G", "U"]].  The union alone
        # cannot tell those apart, and the difference is a whole mana.
        # Deduplicated in order: two abilities that both make {G} are one
        # choice, not two.
        options = list(dict.fromkeys(tuple(o) for s in group for o in s.options))
        producible = frozenset().union(*(s.producible() for s in group))
        entries.append(
            {
                "oid": oid,
                "options": [_option_symbols(option) for option in options],
                # Sorted by SYMBOLS order so {G}{U} and {U}{G} render alike.
                "symbols": sorted((SYMBOLS[i] for i in producible), key=SYMBOL_INDEX.get),
                "amount": max(s.max_output() for s in group),
            }
        )
    return {
        "pool": pool.to_dict(),
        "sources": entries,
        "total": pool.total() + permanents_output(sources),
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
    if payable_mana(state, pid, cost).phyrexian_count:
        # A special action's mana (suspend, foretell) is paid through `pay`,
        # which may buy Phyrexian pips -- and K'rrik's black ones -- with life,
        # so the offer has to count them the same way.
        return (
            life_for_mana_range(
                state, pid, Cost(mana=cost), None, x=x, extra_generic=extra_generic, purpose=purpose
            )
            is not None
        )
    # "…including the mana costs of spells, activation costs, and even costs for
    # special actions": suspend and foretell come through here rather than
    # `ability_mana`, so Chromatic Orrery's waiver is read here too, and at the
    # same point in the arithmetic -- before `extra_generic`, exactly as
    # `ability_mana` reads it before `can_pay` and `pay` add theirs.
    req = spendable_requirement(state, pid, cost.with_x(x))
    if extra_generic:
        req = req.with_generic(req.generic + extra_generic)
    return (
        solve_payment(
            req,
            # The pool as this purpose may spend it: a pip carrying "spend this
            # mana only to cast spells" is no more available to an activation
            # than a restricted *source* is, and the solver plans on integers.
            state.players[pid].mana_pool.spendable(purpose),
            mana_sources(state, pid, purpose=purpose),
        )
        is not None
    )


def defined_x(state: GameState, pid: int, cost: Cost | None, source_oid: int | None) -> int | None:
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

    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    return max(0, int(evaluate_value(ctx, cost.x_value)))


def ability_mana(
    state: GameState,
    pid: int,
    cost: Cost,
    x: int = 0,
    source_oid: int | None = None,
    ability=None,
    targets=None,
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
    # "Equip abilities you activate … cost {3} less to activate" -- Strong Back,
    # a discount written on a *different* permanent. Added to the ability's own
    # `mana_reduction` rather than replacing it: two cards may both be talking
    # about the same activation, and the printed answer is that both apply.
    less += ability_cost_reduction(state, pid, ability, source_oid, targets)
    if less:
        req = req.with_generic(req.generic - less)
    # Chromatic Orrery, **after** the discount: "you may spend mana as though it
    # were mana of any color" is a rule about which mana pays a pip, not about
    # how many pips there are, and the clamp above has to have run first or
    # "costs {2} less" would eat a coloured pip that had become generic. Read
    # here because this one function is what legality, `can_pay` and `pay` all
    # reach -- so an ability offered because its {G} was loosened is an ability
    # charged the loosened price.
    return spendable_requirement(state, pid, req)


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

    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    return max(0, int(evaluate_value(ctx, spec)))


def payable_mana(state: GameState, pid: int, mana: ManaCost) -> ManaCost:
    """``mana`` as this player may pay it: K'rrik's black pips made Phyrexian.

    "For each {B} in a cost, you may pay 2 life rather than pay that mana."
    Every cost path that prices mana reads it through here or through the
    identical conversion on the cast line, so a pip offered as buyable with life
    is a pip charged that way.
    """

    # Cheap test first: this is asked of every cost legality prices, and most
    # have no black in them at all -- the battlefield walk is for the rest.
    if not (mana.colored[SYMBOL_INDEX["B"]] or mana.hybrid):
        return mana
    if player_pays_life_for_black(state, pid):
        return mana.black_as_phyrexian()
    return mana


def spendable_requirement(state: GameState, pid: int, req: Requirement) -> Requirement:
    """``req`` as this player may pay it: Chromatic Orrery's loosened pips.

    "You may spend mana as though it were mana of any color." The payment twin
    of :func:`payable_mana` and written to the same shape, one level down: a
    `Requirement` rather than a `ManaCost`, because the waiver is read *after*
    every discount and a discount is applied to the requirement.

    Deliberately **not** folded into `payable_mana`. That helper's answer is
    asked for its `phyrexian_count` -- by `can_pay`, by `can_pay_mana` and by
    `life_for_mana_range` -- and `as_any_color` turns hybrid pips into generic
    ones, so loosening there would hide a printed ``{G/P}`` activation's life
    half behind an Orrery. The two waivers stack instead: the Phyrexian pips are
    bought first, and what is left of the cost is loosened here.
    """
    colorless = SYMBOL_INDEX[COLORLESS]
    # Cheap test first: this runs for every cost the engine prices, and a cost
    # with nothing coloured in it has nothing to loosen whatever is on the
    # battlefield -- the board walk is for the rest.
    if not req.hybrid and not any(n for i, n in enumerate(req.colored) if i != colorless):
        return req

    if player_spends_mana_as_any_color(state, pid):
        return req.as_any_color()
    return req


def _life_budget(state: GameState, pid: int, cost: Cost, source_oid: int | None) -> int:
    """How much life is left over for Phyrexian pips once the cost's own
    "pay N life" is set aside. 118.4 lets the whole of it go; a locked life
    total (Teferi's Protection) lets none of it go, because paying life is
    losing it."""
    if life_locked(state, pid):
        return 0
    return max(0, state.players[pid].life - life_cost(state, pid, cost, source_oid))


def life_for_mana_range(
    state: GameState,
    pid: int,
    cost: Cost,
    source_oid: int | None,
    *,
    x: int = 0,
    extra_generic: int = 0,
    purpose: SpendPurpose | None = None,
    ability=None,
    targets=None,
) -> tuple[ManaCost, int, int] | None:
    """How many of this cost's Phyrexian pips may be paid with life, or ``None``.

    Returns ``(mana, fewest, most)``: the cost's mana as this player pays it
    (:func:`payable_mana`), the fewest pips that must go the life way for the
    rest to be payable with the mana on hand, and the most the life total can
    buy. ``None`` when no number between 0 and that ceiling leaves a payable
    remainder -- the cost cannot be paid at all.

    Every cost that is not a spell's own cast line comes through here: an
    activated ability, a mana ability tapped by hand, a morph turned face up,
    "unless its controller pays {B}". The cast line counts its pips as separate
    *lines* instead (`casting._cast_variant`), which is why `pay` is told not to
    ask when the cast calls it.

    Feasibility is monotone in the number bought -- buying one more pip only
    takes a demand away -- so the answer is a contiguous range and the scan can
    stop at the first payable number.
    """
    mana = payable_mana(state, pid, cost.mana)
    most = min(mana.phyrexian_count, _life_budget(state, pid, cost, source_oid) // 2)
    sources = mana_sources(state, pid, purpose=purpose)
    if cost.tap and source_oid is not None:
        sources = [s for s in sources if s.oid != source_oid]
    pool = state.players[pid].mana_pool.spendable(purpose)
    for bought in range(most + 1):
        remaining, _ = mana.paying_phyrexian(bought)
        req = ability_mana(
            state,
            pid,
            replace(cost, mana=remaining),
            x,
            source_oid,
            ability=ability,
            targets=targets,
        )
        if extra_generic:
            req = req.with_generic(req.generic + extra_generic)
        if solve_payment(req, pool, sources) is not None:
            return mana, bought, most
    return None


def most_life_for_mana(
    state: GameState, pid: int, cost: Cost, source_oid: int | None
) -> ManaCost:
    """This cost's mana with as many Phyrexian pips bought as the life allows.

    The cheapest the mana half can get, and so what an ``{X}`` ceiling is
    measured against: `pay` then asks for at least the pips that X needs, never
    more than the life can buy.

    Chromatic Orrery's waiver is applied to what is left, after the pips are
    bought, for the reason `spendable_requirement` gives -- and it has to be
    applied *here*, because this is the only cost `max_affordable_x` ever sees
    for an activated ability. Without it an ``{X}{G}`` line under an Orrery was
    found payable by `can_pay` and then withheld by the X gate, which is the
    two halves of legality disagreeing about the same ability.
    """
    mana = payable_mana(state, pid, cost.mana)
    most = min(mana.phyrexian_count, _life_budget(state, pid, cost, source_oid) // 2)
    mana = mana.paying_phyrexian(most)[0]

    if player_spends_mana_as_any_color(state, pid):
        return mana.as_any_color()
    return mana


def can_pay(
    state: GameState,
    pid: int,
    cost: Cost | None,
    source_oid: int | None,
    *,
    x: int = 0,
    purpose: SpendPurpose | None = None,
    ability=None,
    targets=None,
) -> bool:
    """Can this player pay every part of ``cost`` right now?

    ``ability`` is the activated ability being priced, when one is -- a cost is
    also paid for a spell, a suspend and a special action, and none of those is
    an ability. It is threaded down to `ability_mana` because a discount written
    on a *different* permanent ("equip abilities you activate cost {3} less")
    is a fact about which ability this is, and nothing else in a `Cost` says.

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
    if cost.exert:
        # 702.121a: exerting is done to a permanent, so the source has to be on
        # the battlefield -- and nothing else is required. Deliberately no
        # "untapped" test (702.121b exerts a tapped permanent quite happily),
        # no "creature" test and no "attacking" test: Arena of Glory is a land
        # that never attacks, and the keyword's usual home on an attack trigger
        # is that card's business, not the cost's.
        obj = state.objects.get(source_oid) if source_oid is not None else None
        if obj is None or not obj.on_battlefield:
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
    # 107.14: energy is spent, never borrowed -- a player with seven cannot pay
    # eight, and there is no "down to exactly 0" question because nothing
    # happens at zero.
    if cost.pay_energy and player.energy < cost.pay_energy:
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
    if cost.exile_from_hand is not None and not _hand_exile_pool(state, pid, cost, source_oid):
        return False
    if cost.behold is not None and len(
        behold_pool(state, pid, cost.behold, source_oid, exclude_source=True)
    ) < behold_count(cost.behold):
        return False
    if cost.sacrifice is not None and not _sacrifice_pool(state, pid, cost, source_oid):
        return False
    if cost.return_to_hand is not None and not _return_pool(state, pid, cost, source_oid):
        return False
    if cost.tap_permanents is not None and not _tap_cost_pool(state, pid, cost, source_oid):
        return False
    if cost.untap_permanents is not None and not _untap_cost_pool(state, pid, cost, source_oid):
        return False
    if cost.remove_counters_from_among is not None:
        needed = int(cost.remove_counters_from_among.get("count", 1) or 1)
        pool = _counter_removal_pool(state, pid, cost, source_oid)
        if sum(_counters_on(state, oid) for oid in pool) < needed:
            return False
    if cost.remove_counters is not None:
        obj = state.objects.get(source_oid) if source_oid is not None else None
        kind = str(cost.remove_counters.get("counter", "+1/+1"))
        amount = int(cost.remove_counters.get("amount", 1))
        if obj is None or obj.counter(kind) < amount:
            return False
    # Always payable while the source is on the battlefield to take them: a
    # counter needs a permanent (122.1), and one whose source has left is not.
    if cost.put_counters is not None and (
        source_oid is None or source_oid not in state.battlefield
    ):
        return False
    # A cost that would put on a counter the permanent can't have (Darksteel
    # Angel, Melira) can't be paid: the placement would not happen, and a cost
    # is paid only by doing all of it (601.2h).
    if cost.put_counters is not None and counters_prohibited(
        state, source_oid, str(cost.put_counters["counter"])
    ):
        return False
    if cost.blight and not _blight_pool(state, pid, source_oid):
        return False
    if cost.loyalty is not None and cost.loyalty > 0 and source_oid is not None and (
        counters_prohibited(state, source_oid, "loyalty")
    ):
        return False
    if cost.loyalty is not None and cost.loyalty < 0:
        # 606.3: a minus ability may only be activated if there is enough
        # loyalty to pay it. A plus or a zero is always payable, which is why
        # only the negative half is tested -- and why this is not
        # `remove_counters`, which can never add.
        obj = state.objects.get(source_oid) if source_oid is not None else None
        if obj is None or obj.counter("loyalty") < -cost.loyalty:
            return False
    if cost.loyalty_x and x > 0:
        # "-X": the same 606.4 test at the announced number. X = 0 is always
        # payable, which is what lets legality offer the ability at its floor
        # and `game._activate` bound the announcement by the loyalty there is.
        obj = state.objects.get(source_oid) if source_oid is not None else None
        if obj is None or obj.counter("loyalty") < x:
            return False
    if cost.exile_from_graveyard is not None and not _graveyard_pool(state, pid, cost, source_oid):
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
        if payable_mana(state, pid, cost.mana).phyrexian_count:
            # 107.4f, and K'rrik: some pips may be bought with life, and the
            # cost is payable if any number of them leaves a payable remainder.
            if (
                life_for_mana_range(
                    state,
                    pid,
                    cost,
                    source_oid,
                    x=x,
                    purpose=purpose,
                    ability=ability,
                    targets=targets,
                )
                is None
            ):
                return False
        elif (
            solve_payment(
                ability_mana(
                    state, pid, cost, x, source_oid, ability=ability, targets=targets
                ),
                player.mana_pool.spendable(purpose),
                sources,
            )
            is None
        ):
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

    spec = {**dict(cost.exile_from_hand or {}), "zone": "hand"}
    count = int(spec.pop("count", 1) or 1)
    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    pool = [oid for oid in hand if matches(ctx, oid, spec)]
    return pool if len(pool) >= count else []


def _sacrifice_pool(state: GameState, pid: int, cost: Cost, source_oid: int | None) -> list[int]:
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

    spec = dict(cost.sacrifice or {})
    # `as` names what was sacrificed for the ability's effects; like
    # `tap_permanents`' it says nothing about which permanents qualify.
    spec.pop("as", None)
    spec.setdefault("controller", "you")
    spec.setdefault("zone", "battlefield")
    count = int(spec.pop("count", 1) or 1)
    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    pool = [oid for oid in resolve_pool(ctx, spec) if not sacrifice_forbidden(state, oid)]
    return pool if len(pool) >= count else []


def _blight_pool(state: GameState, pid: int, source_oid: int | None) -> list[int]:
    """Which creatures the payer may blight -- "a creature **they** control".

    Built around ``pid``, the *paying* player, and never the source's
    controller: ward's "Blight 2" is paid by the opponent who targeted, onto a
    creature of their own. The source itself qualifies when it is a creature
    its payer controls -- nothing in the rule excludes it, and an activated
    "Blight 1:" on a creature may blight that creature.

    A creature that can't have -1/-1 counters is not in the pool, for
    `put_counters`' reason: the placement would not happen, and a cost is paid
    only by doing all of it (601.2h). So a board of nothing but such creatures
    makes the cost unpayable rather than free.
    """
    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    spec = {"types": ["Creature"], "controller": "you", "zone": "battlefield"}
    return [
        oid for oid in resolve_pool(ctx, spec) if not counters_prohibited(state, oid, MINUS_ONE)
    ]


def _return_pool(state: GameState, pid: int, cost: Cost, source_oid: int | None) -> list[int]:
    """Which permanents this cost may bounce -- "return a land you control".

    Deliberately a separate pool from ``_sacrifice_pool`` even though the
    selectors look identical, because what happens to the permanent is the
    whole difference: Meloku and Trench Behemoth both replay the land they
    return, and a sacrifice would graveyard it.
    """

    spec = dict(cost.return_to_hand or {})
    spec.setdefault("controller", "you")
    spec.setdefault("zone", "battlefield")
    count = int(spec.pop("count", 1) or 1)
    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    pool = resolve_pool(ctx, spec)
    return pool if len(pool) >= count else []


def _tap_cost_pool(state: GameState, pid: int, cost: Cost, source_oid: int | None) -> list[int]:
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

    spec = dict(cost.tap_permanents or {})
    # `as` names what was tapped for the ability's effects; it says nothing
    # about which permanents qualify, so the selector language never sees it.
    spec.pop("as", None)
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
        return pool if _crew_power(state, pool) >= int(total_power) else []
    return pool if len(pool) >= count else []


def bind_paid_object(state: GameState, oid: int) -> dict[str, int]:
    """Name a permanent a cost tapped, so the ability's effects can read it.

    The binding is a *reference to a record*, not a snapshot. Station's release
    notes are explicit on both halves: the tapped creature's power is read **as
    the station ability resolves**, so a pump spell cast in response counts;
    and if the creature has left the battlefield by then, its power **as it last
    existed there** is used. A snapshot at payment gets the first half wrong,
    and a bare oid gets the second half wrong -- an oid survives its permanent
    in this engine, and the graveyard card it points at answers with its printed
    power, or not at all for a token.

    So the record starts empty, `zones.move_object` writes the last-known
    numbers into it as the permanent leaves, and `values._characteristic` reads
    the live permanent while the record is empty and the record once it is not.
    """
    key = state.next_paid_object
    state.next_paid_object += 1
    state.paid_objects[key] = {"oid": oid, "power": None, "toughness": None}
    return {"paid_object": key}


def _crew_power(state: GameState, oids: list[int]) -> int:
    """Summed **derived** power, which is the whole reason crew is not a count.

    An anthem, a pump spell or a +1/+1 counter all change who can crew a
    Vehicle, so the printed face is the wrong thing to read -- and reading it
    would be wrong in the direction that matters, refusing a crew the board
    plainly supports.

    Plus each creature's ``crew_power_bonus`` -- the Pilot's "crews Vehicles as
    though its power were 2 greater". Added here and nowhere else, because this
    sum is the only place the printed line reaches: the Pilot is a 1/1 for
    combat and for every other reader of power, and `total_power` on
    `tap_permanents` is crew's by definition (the loader refuses it elsewhere).
    """

    return sum(
        chars(state, oid).power + crew_power_bonus(state, oid)
        for oid in oids
        if oid in state.objects
    )


def _untap_cost_pool(state: GameState, pid: int, cost: Cost, source_oid: int | None) -> list[int]:
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

    spec = dict(cost.untap_permanents or {})
    spec.setdefault("controller", "you")
    spec.setdefault("zone", "battlefield")
    spec["tapped"] = True
    count = int(spec.pop("count", 1) or 1)
    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    pool = resolve_pool(ctx, spec)
    return pool if len(pool) >= count else []


def _counter_removal_pool(
    state: GameState, pid: int, cost: Cost, source_oid: int | None
) -> list[int]:
    """The permanents a `remove_counters_from_among` cost may take counters off.

    Tekuthal: "Remove three counters from among **other** artifacts, creatures,
    and planeswalkers you control" -- the selector says which permanents
    (``exclude_self`` for "other"), and only those that carry a counter are in
    the pool, since one without has nothing to give.
    """

    spec = dict(cost.remove_counters_from_among or {})
    spec.pop("count", None)
    spec.setdefault("controller", "you")
    spec.setdefault("zone", "battlefield")
    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    return [oid for oid in resolve_pool(ctx, spec) if _counters_on(state, oid) > 0]


def _counters_on(state: GameState, oid: int) -> int:
    obj = state.objects.get(oid)
    return sum(n for n in obj.counters.values() if n > 0) if obj is not None else 0


def _graveyard_pool(state: GameState, pid: int, cost: Cost, source_oid: int | None) -> list[int]:
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
    bindings: dict[str, Any] | None = None,
    life_for_mana: bool = True,
    ability=None,
    targets=None,
) -> Generator[Any, list[int], bool]:
    """Pay a cost, asking the player for any choices it requires.

    ``ability`` is the activated ability being priced, when one is -- a cost is
    also paid for a spell, a suspend and a special action, and none of those is
    an ability. It is threaded down to `ability_mana` because a discount written
    on a *different* permanent ("equip abilities you activate cost {3} less")
    is a fact about which ability this is, and nothing else in a `Cost` says.

    Returns ``True`` on success.  Callers only invoke this after :func:`can_pay`,
    so a ``False`` return means the game state changed underneath them.

    ``bindings`` is where a cost that **names** what paid it writes the name --
    `tap_permanents` with ``as``, Station's "the tapped creature", and
    `sacrifice` with ``as``, Ghoulcaller Gisa's "the sacrificed creature". The caller
    hands the same dict to the stack item, so the ability's effects read it
    back. ``None`` from every caller with no ability to hand it to; a named cost
    paid there simply names nothing.

    ``purpose`` is what the mana is being spent on, and must be the same value
    legality used when it decided this was payable -- restricted mana is offered
    or withheld by that alone.

    ``life_for_mana`` is whether a Phyrexian pip still in the cost -- printed,
    or a ``{B}`` under K'rrik -- may be bought with 2 life here (107.4f). The
    player is asked how many when there is a choice. ``False`` from the cast
    line alone, which has already made that choice as the line it offered
    (`Action.phyrexian`), so every pip still in its cost is one the caster chose
    to pay with mana.
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
            # {Q} untaps like anything else, so a stun counter is spent instead
            # (122.1d) and the permanent stays tapped.
            untap_or_stun(state, obj)
            state.bump_chars()
    if cost.exert and source_oid is not None:
        obj = state.objects.get(source_oid)
        if obj is not None and obj.on_battlefield:
            # The two halves of 702.121a, and they are two stores on purpose --
            # the same call `set_turn_flag` and `skip_untap` already made.
            # `skip_next_untap` is a *one-shot* consumed by the untap step it
            # skips; the ledger flag is a word that wears off at the turn
            # boundary and is what "hasn't been exerted this turn" reads.
            obj.skip_next_untap = True
            state.turn_ledger.set_object_flag(source_oid, "exerted")

    # Mana is paid first: activating mana abilities happens before other costs
    # are paid (rule 601.2g), so sacrificing a mana creature as part of the cost
    # cannot strand the payment.
    phyrexian_life = 0
    if life_for_mana:
        span = life_for_mana_range(
            state, pid, cost, source_oid, x=x, extra_generic=extra_generic, purpose=purpose
        )
        if span is not None and span[2]:
            mana, fewest, most = span
            bought = fewest
            if most > fewest:
                # The payer's choice, made while paying (601.2g-h) -- the same
                # choice the cast line offers as separate lines, asked here
                # because an activation or a resolving "unless" has no lines.
                labels = [
                    "Pay with mana"
                    if n == 0
                    else f"Pay {n * 2} life for {n} mana symbol{'s' if n > 1 else ''}"
                    for n in range(fewest, most + 1)
                ]
                picked = yield from ask_mode(
                    ctx, "Pay mana symbols with 2 life each?", labels, pid
                )
                bought = fewest + (picked[0] if picked else 0)
            remaining, phyrexian_life = mana.paying_phyrexian(bought)
            cost = replace(cost, mana=remaining)
    req = ability_mana(state, pid, cost, x, source_oid, ability=ability, targets=targets)
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

    if phyrexian_life:
        # The pips bought above: one symbol of this cost paid in a different
        # currency, so the same payment and the same event batch as the mana.
        lose_life(state, pid, phyrexian_life, source=source_oid)

    if cost.pay_life:
        # A Phyrexian pip bought with life arrives here, as `pay_life` on a cost
        # `Game._cast` assembles -- rule 107.4f is a *way of paying one symbol*,
        # not a separate cost, and `ManaCost.paying_phyrexian` has already taken
        # the symbol out of the mana half above. Paid in the same `pay` call and
        # so in the same event batch, because the mana and the life are one
        # payment however the printed symbol is read.
        lose_life(state, pid, life_cost(state, pid, cost, source_oid), source=source_oid)

    if cost.pay_energy:
        pay_energy(state, pid, cost.pay_energy, source=source_oid)

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

    if cost.behold is not None:
        # Nothing moves: the permanent stays where it is and the hand card goes
        # back among the others. Choosing it, and showing the table a card from
        # hand, is the whole payment.
        count = behold_count(cost.behold)
        pool = behold_pool(state, pid, cost.behold, source_oid, exclude_source=True)
        picked = yield from ask_objects(ctx, "Behold", pool, count, count, pid)
        if len(picked) < count:
            return False
        announce_beheld(state, pid, picked, source_oid)

    if cost.sacrifice is not None:
        spec = dict(cost.sacrifice)
        count = int(spec.pop("count", 1) or 1)
        name = spec.pop("as", None)
        pool = _sacrifice_pool(state, pid, cost, source_oid)
        picked = yield from ask_objects(ctx, "Sacrifice", pool, count, count, pid, "sacrifice")
        if name and picked and bindings is not None:
            # Ghoulcaller Gisa: "…where X is **the sacrificed creature's**
            # power". A snapshot, where `tap_permanents`' `as` is a record read
            # at resolution, and the difference is the rules rather than taste:
            # a sacrificed creature has left the battlefield by the time the
            # cost is paid, so its last-known information (608.2h) is fixed
            # here and nothing cast in response can change it. Taken in the one
            # window where it has been chosen and has not yet moved -- after the
            # move it is a graveyard card answering with its printed line, or a
            # token with no object at all -- and in `zones.snapshot`'s shape,
            # the one the `sacrifice` op's `snapshot` key writes, so
            # `power_of {"binding": …}` and `{"binding": …}` as a selector read
            # it without knowing a cost wrote it.
            bindings[str(name)] = capture_snapshot(state, picked[0])
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
        name = spec.pop("as", None)
        pool = _tap_cost_pool(state, pid, cost, source_oid)
        if total_power is None:
            picked = yield from ask_objects(ctx, "Tap", pool, count, count, pid, "tap_cost")
            for oid in picked:
                tap_permanent(state, oid)
            if name and picked and bindings is not None:
                # Station: "…equal to **the tapped creature's** power". Bound at
                # the moment of payment -- 601.2h, the only moment the choice
                # exists -- but *read* at resolution; see `bind_paid_object`.
                bindings[str(name)] = bind_paid_object(state, picked[0])
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
                needed -= _crew_power(state, [chosen])
                tap_permanent(state, chosen)
                remaining.remove(chosen)

    if cost.untap_permanents is not None:
        spec = dict(cost.untap_permanents)
        count = int(spec.pop("count", 1) or 1)
        pool = _untap_cost_pool(state, pid, cost, source_oid)
        picked = yield from ask_objects(ctx, "Untap", pool, count, count, pid, "untap_cost")
        for oid in picked:
            untap_permanent(state, oid)

    if cost.remove_counters_from_among is not None:
        # One counter at a time: which permanent, then -- if it carries more
        # than one kind -- which kind. "From among" lets the payer split the
        # removal however they like (all three off one permanent, or one off
        # each); see `effects.counter_removal`. A cost is paid in full, so the
        # payer may not stop short: `least` is the whole count.
        needed = int(cost.remove_counters_from_among.get("count", 1) or 1)
        yield from remove_counters_one_at_a_time(
            ctx,
            lambda: _counter_removal_pool(state, pid, cost, source_oid),
            most=needed,
            least=needed,
            chooser=pid,
            purpose="remove_counter_cost",
        )

    if cost.remove_counters is not None and source_oid is not None:
        remove_counters(
            state,
            source_oid,
            str(cost.remove_counters.get("counter", "+1/+1")),
            int(cost.remove_counters.get("amount", 1)),
        )

    if cost.put_counters is not None and source_oid is not None:
        # `as_cost` for the reason the loyalty branch below gives: Doubling
        # Season's "if an effect would put" leaves a cost alone, while Hardened
        # Scales' "would be put" does not. Through `add_counters`, so the
        # placement raises `counter_placed` like any other placement.
        add_counters(
            state,
            source_oid,
            str(cost.put_counters["counter"]),
            int(cost.put_counters.get("amount", 1)),
            as_cost=True,
            by=pid,
        )

    if cost.blight:
        # "To blight N, a player puts N -1/-1 counters on a creature they
        # control." One creature takes all N -- the rule says "a creature" --
        # chosen now, while paying (601.2h), by the payer. Through
        # `add_counters` with `as_cost`, `put_counters`' reason: the placement
        # raises `counter_placed` (Auntie Ool's own trigger reads it) and the
        # counter replacements that are not "if an effect would" apply.
        pool = _blight_pool(state, pid, source_oid)
        picked = yield from ask_objects(
            ctx, f"Blight {cost.blight}", pool, 1, 1, pid, "blight_cost"
        )
        if not picked:
            return False
        add_counters(state, picked[0], MINUS_ONE, cost.blight, as_cost=True, by=pid)

    if cost.loyalty is not None and source_oid is not None:
        # A **cost**, so it is paid as the ability goes on the stack and is not
        # refunded if the ability is countered or does nothing -- which is what
        # makes a planeswalker's loyalty spendable in response to removal.
        if cost.loyalty_x:
            # "-X": the announced number, which `game._activate` bounded by
            # the loyalty on the permanent.
            if x > 0:
                remove_counters(state, source_oid, "loyalty", x)
        elif cost.loyalty > 0:
            # `as_cost`: a cost is not an effect, so Doubling Season's "if an
            # effect would put" leaves a +1 at one counter (its ruling).
            add_counters(state, source_oid, "loyalty", cost.loyalty, as_cost=True)
        elif cost.loyalty < 0:
            remove_counters(state, source_oid, "loyalty", -cost.loyalty)

    if cost.mill:
        # No `ask_objects`: the cards come off the top of the library, so there
        # is nothing to choose. `mill_cards` already stops at an empty library,
        # which is 701.13b and the reason `can_pay` does not gate on this.
        mill_cards(state, pid, cost.mill)

    if cost.exile_from_graveyard is not None:
        spec = dict(cost.exile_from_graveyard)
        count = int(spec.pop("count", 1) or 1)
        pool = _graveyard_pool(state, pid, cost, source_oid)
        picked = yield from ask_objects(
            ctx, "Exile from your graveyard", pool, count, count, pid, "exile_cost"
        )
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
    payment = solve_payment(req, player.mana_pool.spendable(purpose), sources)
    if payment is None:
        return False
    for oid, ability_index, option_index in payment.taps:
        obj = state.objects.get(oid)
        if obj is None or obj.tapped:
            # The plan was made against untapped permanents, so this can only
            # mean the solver named one permanent twice -- a Talisman's two
            # abilities, once.  Refuse loudly: `activate_mana_ability` would
            # add the mana regardless of the tap, and the pool would hold a
            # mana no permanent made.
            raise DslError(
                f"payment plan taps {state.card(oid).name} (#{oid}) but it is "
                "already tapped; the solver must never tap one permanent twice"
            )
        activate_mana_ability(state, oid, ability_index, pid, option_index)
    spent = player.mana_pool.spend(req, purpose)
    # The pool is a static's input ("+1/+1 for each unspent mana you have",
    # Omnath, Locus of the Void), and a payment from floating mana taps nothing
    # that would bump for it.
    state.bump_chars()
    if record_colors_on is not None and (obj := state.objects.get(record_colors_on)):
        obj.colors_spent = spent.colors
        obj.mana_sources_spent = spent.sources
        # "…if mana from a Treasure was spent to cast it." Unioned, not
        # assigned, for `uncounterable_mana_spent`'s reason one line down: a
        # cast pays in more than one call when it has an additional cost, and a
        # spell partly paid for with Treasure mana was paid for with Treasure
        # mana. (`mana_sources_spent` above predates that reading and keeps its
        # assignment, so this change cannot alter any shipped card's behaviour.)
        obj.mana_spent_traits = obj.mana_spent_traits | spent.source_traits
        # Accumulated with `or`, not assigned, for `mana_spent`'s reason: a cast
        # pays in more than one call when it has an additional cost, and a spell
        # paid for partly with Cavern mana was paid for with Cavern mana.
        obj.uncounterable_mana_spent = obj.uncounterable_mana_spent or spent.uncounterable
        # "**If that mana is spent on a creature spell**, it gains haste until
        # end of turn." The type test belongs here and nowhere later: "creature
        # spell" is a question about the *spell*, asked at the instant the mana
        # is spent, and by the time the permanent exists to be given haste the
        # spell is gone. Accumulated for `uncounterable_mana_spent`'s reason --
        # one cast can pay in more than one call.
        for grant in spent.grants:
            if grant.spell_types and not (set(grant.spell_types) & chars(state, obj.oid).types):
                continue
            obj.mana_granted_keywords.update(grant.keywords)
        # "When you spend this mana to cast your commander, …" -- Study Hall.
        # Asked here for the grant's reason: the spell is what the filter is
        # about, and only this payment knows which mana paid for it.
        if spent.spend_triggers:
            _queue_spend_triggers(state, pid, obj.oid, spent.spend_triggers)
        # Accumulated rather than assigned: a cast pays in more than one call
        # when it has an additional cost, and "how much mana was spent to cast
        # it" is all of them.
        obj.mana_spent += req.total
    state.emit(
        EventType.MANA_SPENT,
        player=pid,
        amount=req.total,
        colors=sorted(spent.colors),
        sources=sorted(spent.sources),
    )
    return True


def activate_mana_ability(
    state: GameState,
    oid: int,
    ability_index: int,
    pid: int,
    option_index: int = 0,
    source_traits: ManaOrigin | None = None,
    ability: Any = None,
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

    ``source_traits`` is what the source **was**, for "if mana from a Treasure
    was spent to cast it". A parameter rather than a lookup here, because this
    function is not always early enough: `Game._activate_mana` runs the
    ability's cost *before* calling it, and a Treasure's cost sacrifices the
    Treasure. That path passes the snapshot it took while the token was still on
    the battlefield. Left ``None`` -- the payment solver's path, which only ever
    taps -- the snapshot is taken here, which is still before the tap.

    ``ability`` is the same kind of snapshot, for the same path: a *granted*
    sacrifice-for-mana ability (Vraska, Betrayal's Sting's Treasure) is on the
    permanent only while it is on the battlefield, so once the cost has
    sacrificed it `abilities_of` no longer lists it. `Game._activate_mana`
    hands over the ability it read before paying.
    """
    if ability is None:
        ability = abilities_of(state, oid)[ability_index]
    if source_traits is None:
        source_traits = mana_source_traits(state, oid)

    obj = state.objects.get(oid)
    is_land = obj is not None and "Land" in chars(state, oid).types
    # The payment half of the pair in `_sources_of`, and it must ask the same
    # question: a spell offered on doubled mana and then paid on single mana
    # strands the payment mid-cast.
    doubled = obj is not None and player_doubles_mana_from(state, obj.controller, oid)
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
    # "Whenever you tap a Swamp for mana, add an additional {B}." Read before
    # the tap for the reason the variable amount above is, and only when the
    # ability really taps: 106.12 makes "tap for mana" a mana ability with {T}
    # in its cost, and nothing else.
    tapping = ability.cost is not None and ability.cost.tap
    added_on_tap = mana_added_on_tap(state, pid, oid, produced) if tapping else []

    if ability.cost is not None and ability.cost.tap:
        # The return value is deliberately not checked: `Game._activate_mana`
        # has already tapped the source through `pay()` by the time it reaches
        # here, so a False is the normal by-hand case.  The solver's plan is
        # checked against the board in `pay_mana` instead.
        tap_permanent(state, oid)

    # Tagged with the permanent that made it, and with any rider the ability
    # attached. The tag is the whole of what Path of Ancestry's "when that mana
    # is spent" reads back, and it is knowable only here -- a pool of six
    # integers cannot say where a pip came from once it has landed in it.
    #
    # The rider is read off the **ability**, not the permanent, because Cavern of
    # Souls has two mana abilities and only the second one prints "…and that
    # spell can't be countered": recorded per permanent, its plain {C} would make
    # the spell uncounterable too.
    #
    # `source_traits` rides beside the oid rather than replacing it, and is the
    # half that survives the source: this ability's cost may *sacrifice* the
    # permanent -- every Treasure does -- and `sba._tokens_and_attachments`
    # deletes a sacrificed token from `state.objects` outright, so the oid is
    # already a dangling pointer by the time the spell it paid for is on the
    # stack. Snapshotted here because here is the last moment it is knowable.
    state.players[pid].mana_pool.add_tuple(
        produced,
        source=oid,
        uncounterable=ability.mana_uncounterable,
        # Arena of Glory's "…it gains haste until end of turn", read off the
        # **ability** for the reason above: Arena's plain `{R}` ability must not
        # hand out the haste its exerting one pays for.
        grant=ability.mana_grant,
        source_traits=source_traits,
        # Study Hall's "When you spend this mana to cast your commander…", read
        # off the **ability** for the reason above. One tag per activation,
        # which every pip this activation made shares -- see `ManaSpendTrigger`.
        spend_trigger=_spend_trigger_tag(state, oid, pid, ability),
    )
    state.emit(EventType.MANA_ADDED, player=pid, source=oid, mana=format_symbols(produced))
    # The triggered mana ability's mana is its source's, not the land's: tagged
    # with the Ghast, so provenance readers see who really made it.
    for source, mana in added_on_tap:
        state.players[pid].mana_pool.add_tuple(
            mana, source=source, source_traits=mana_source_traits(state, source)
        )
        state.emit(EventType.MANA_ADDED, player=pid, source=source, mana=format_symbols(mana))
    # The pool grew, and it is a static's input (`unspent_mana_count`); the tap
    # above bumps only when there was one to make.
    state.bump_chars()
    if ability.mana_rider:
        _run_mana_rider(state, oid, pid, ability)
    if is_land and obj is not None:
        _lands_tapped_for_mana(state, obj)


def _spend_trigger_tag(
    state: GameState, oid: int, pid: int, ability: Ability
) -> ManaSpendTrigger | None:
    """The tag this activation's mana carries for a spent-mana trigger, if any.

    Where the trigger's definition lives is settled **now**, while the source is
    on the battlefield: a granted mana ability is addressed through its granter
    (`triggers._granter_of`), and the source's card id is snapshotted so the
    trigger can still be found once the source has gone -- 106.6 makes the
    trigger the mana's, and the mana can outlive the permanent that made it.
    """
    if ability.mana_spent_trigger is None:
        return None
    # Local: `triggers` imports this module.
    from .triggers import _granter_of

    obj = state.objects[oid]
    granted_by, index = _granter_of(state, obj, ability)
    return ManaSpendTrigger(
        source=oid,
        ability_index=index,
        def_id=obj.def_id,
        controller=pid,
        ability=ability.mana_spent_trigger,
        granted_by=granted_by,
    )


def _queue_spend_triggers(
    state: GameState, pid: int, spell_oid: int, tags: Sequence[ManaSpendTrigger]
) -> None:
    """Queue each spent-mana trigger whose spell filter the spell being cast meets.

    "When you spend this mana to cast **your commander**" is a question about the
    spell, asked at the instant the mana is spent (601.2h) -- the same instant
    `mana_grant`'s "creature spell" is asked -- and answered with a `spell_cast`
    trigger's filter semantics, which is what the loader validated it against.
    Queued here rather than off the `spell_cast` event: that event cannot say
    which mana paid, and the trigger has triggered by the time the spell is
    cast. It goes on the stack when a player would next receive priority (603.3),
    above the spell it paid for.

    The ability source the filter compares against ("owner: you") is the source
    permanent while it exists, and a stand-in carrying the activator otherwise:
    the trigger belongs to the mana (106.6), and the loader refuses every filter
    key that would need the real permanent.
    """
    from .objects import GameObject
    from .structs import TriggerInstance
    from .triggers import matches_card_filter

    for tag in tags:
        trigger = tag.ability
        spec = trigger.trigger
        source = state.objects.get(tag.source)
        if source is None:
            source = GameObject(
                oid=tag.source,
                def_id=tag.def_id,
                owner=tag.controller,
                controller=tag.controller,
                zone=Zone.GRAVEYARD,
            )
        filt = spec.filter if spec is not None else None
        if filt and not matches_card_filter(state, spell_oid, filt, source):
            continue
        name = state.registry.get(tag.def_id).name if tag.def_id in state.registry else "?"
        state.pending_triggers.append(
            TriggerInstance(
                source_oid=tag.source,
                ability_index=tag.ability_index,
                controller=tag.controller,
                # "Scry X, where X is the number of times **it**'s been cast":
                # the spell the mana paid for is the subject, the shape a
                # `spell_cast` trigger binds it in.
                bindings={
                    "self": tag.source,
                    "subject": spell_oid,
                    "event_player": pid,
                    "event_type": EventType.MANA_SPENT,
                },
                description=f"{name}: {trigger.text or 'mana spent'}",
                def_id=tag.def_id,
                granted_by=tag.granted_by,
                mana_spent=True,
            )
        )
        state.emit(
            EventType.ABILITY_TRIGGERED,
            player=tag.controller,
            source=tag.source,
            card=tag.def_id,
            ability=tag.ability_index,
            trigger="mana_spent",
        )


def _run_mana_rider(state: GameState, oid: int, pid: int, ability: Any) -> None:
    """ "…This land deals 1 damage to you", inline and off the stack.

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

    freezers = players_freezing_opponent_lands(state)
    if any(pid != land.controller for pid in freezers):
        land.skip_next_untap = True


def land_drops_available(state: GameState, pid: int) -> int:
    """How many more lands this player may play this turn."""

    player = state.players[pid]
    return 1 + player.extra_land_drops + player_extra_land_drops(state, pid) - player.lands_played


def commander_cost(state: GameState, oid: int) -> int:
    """Extra generic mana owed for casting a commander from the command zone."""
    obj = state.objects.get(oid)
    if obj is None:
        return 0
    return 2 * state.players[obj.owner].commander_tax.get(oid, 0)


def zone_of(state: GameState, oid: int) -> Zone:
    return state.objects[oid].zone
