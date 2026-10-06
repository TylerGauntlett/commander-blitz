"""Effect ops that change what a permanent is: subtypes, P/T, keywords,
protection, animation, ability grants and locks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..objects import PLUS_ONE
from ..primitives import (
    add_counters,
    add_subtypes,
    animate,
    grant_ability,
    grant_keyword,
    lock_abilities,
    pump,
)
from ..structs import TempEffect
from ..text_change import printed_type_instances
from .context import EffectContext, ask_mode
from .registry import register
from .selectors import (
    choose_objects,
    select_players,
)
from .values import evaluate_value

#: The two clocks a pump, an animation, a timed keyword grant and an ability
#: lock may run on. ``grant_keyword`` adds ``permanent`` (riot) to these.
TIMED_DURATIONS = ("until_end_of_turn", "until_your_next_turn")


def until_player_of(ctx: EffectContext, spec: Mapping[str, Any]) -> int | None:
    """The seat whose next turn ends this effect, or ``None`` for cleanup.

    "Until **your** next turn" (611.2b) is the *controller's* -- the player who
    activated the loyalty ability, not the owner of the creature it points at --
    which is what `ctx.controller` is while the effect resolves.
    """
    duration = str(spec.get("duration", "until_end_of_turn"))
    if duration == "until_your_next_turn":
        return ctx.controller
    if duration not in (*TIMED_DURATIONS, "permanent"):  # pragma: no cover - loader guards
        raise ValueError(f"unknown duration {duration!r}")
    return None


@register("add_subtype")
def op_add_subtype(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "It becomes a Vampire in addition to its other types." Captivating Vampire.

    The same two words as the `add_subtype` **static**, and a different
    mechanism: the static applies continuously to whatever currently matches its
    filter and stops when its source leaves, while this is written onto the one
    permanent it was pointed at and stays until that permanent changes zones.
    The printed lines differ the same way -- "creatures you control are
    Vampires" against "it becomes a Vampire".

    Types are always *added*.  Replacing a type line is `animate` or the
    `set_types` static.

    **Literal names only**, and the assertion is the point. `str()` stood where
    this check does, and it made `{"chosen_type_of": "self"}` -- which the
    static of the same name now takes, and which the loader refuses here -- into
    the subtype `"{'chosen_type_of': 'self'}"`: a permanent that loads,
    resolves, and is of no creature type at all. A one-shot cannot honour that
    entry anyway, because it writes a word onto the object and walks away, where
    the sentence is a continuous grant that has to be re-read after a second
    `choose_type` or a `change_text`. Unreachable through `compile_card`; loud
    rather than silent for a spec built in code.
    """
    wanted = tuple(spec.get("subtypes", ()))
    if not all(isinstance(t, str) for t in wanted):
        raise TypeError(
            f"add_subtype: subtypes are literal names, got {wanted!r} -- "
            f"'of the chosen type' is the add_subtype static, not this op"
        )
    subtypes = list(wanted)
    if not subtypes:
        return
    oids = yield from choose_objects(ctx, spec.get("objects"), "Becomes")
    for oid in oids:
        add_subtypes(ctx.state, oid, subtypes)


@register("lose_all_abilities")
def op_lose_all_abilities(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "…and **loses all other abilities**." The Irencrag.

    `lose_all_abilities` existed only as a **static**, and a static is the wrong
    shape for this line twice over. It is gathered off the printed face, so
    written on The Irencrag it would strip "{T}: Add {C}" from the moment the
    artifact entered -- before any legendary creature arrived, and whether or
    not the player ever said yes. And no `condition` can gate it, because the
    transformation it waits for is not a fact the engine had a flag for.

    So the fact goes on the **object**, read by `_derived_abilities` beside the
    static, which is the one place that decides what abilities a permanent has.
    Both mean the same thing about the printed list; they differ only in who is
    saying it and for how long.

    Permanent for as long as the permanent is. "Loses all abilities until end of
    turn" is `temp_effects`' business and a different clause; this one is The
    Irencrag's, which never changes back.

    **Other** abilities: the grants applied alongside it survive, because
    `_derived_abilities` drops the *printed* list and appends the granted ones
    after -- which is exactly what "loses all other abilities and gains …" says.
    """
    oids = yield from choose_objects(ctx, spec.get("objects"), "Loses all abilities")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None or not obj.on_battlefield:
            continue
        obj.lost_all_abilities = True
        _drop_earlier_grants(obj, ctx.began_at)
    ctx.state.bump_chars()


#: The `TempEffect` kinds that *are* abilities (layer 6), and so go when a
#: permanent loses all abilities. A pump, an animation, a steal and an ability
#: lock are not abilities and stay.
_ABILITY_KINDS = frozenset({"keyword", "ability", "protection"})


def _drop_earlier_grants(obj, cutoff: int) -> None:
    """Take away every ability granted to ``obj`` before ``cutoff`` (613.7).

    Oko, Thief of Crowns: "target artifact or creature loses all abilities".
    The loss has a later timestamp than a flying granted earlier in the turn,
    so the flying goes with the printed abilities; a flying granted *after*
    Oko's +1 resolves is a later effect and survives. Both lists of grants are
    walked -- the timed one (`until_eot`) and the ones for as long as the
    permanent lasts (`granted_abilities_permanent`, `granted_keywords`) -- and
    suspend's haste, which is a keyword too.

    ``cutoff`` is the start of the resolution doing the removing, not the
    moment of the removal. "It gains \"…\" **and loses all other
    abilities**" (The Irencrag) is one simultaneous change, and the grant
    written just before this op in the same effect list must survive it.
    """
    obj.until_eot = [
        t for t in obj.until_eot if t.kind not in _ABILITY_KINDS or t.timestamp >= cutoff
    ]
    obj.granted_abilities_permanent = [
        t for t in obj.granted_abilities_permanent if t.timestamp >= cutoff
    ]
    for word in list(obj.granted_keywords):
        if obj.granted_keyword_at.get(word, 0) < cutoff:
            obj.granted_keywords.discard(word)
            obj.granted_keyword_at.pop(word, None)
    obj.hasted_by_suspend = False


@register("rename")
def op_rename(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "…become a legendary Equipment artifact **named Everflame, Heroes'
    Legacy**." The Irencrag.

    Nothing in the engine could change a name. The characteristics pipeline has
    no name layer at all, and `_matches_printed` says so where it tests
    `selector.name`: "a name is the most printed characteristic there is and
    nothing in the pipeline can change one".

    So the name is written onto the **object** and read by `GameState.card_of`,
    the single funnel that decides a permanent's current face -- which is where
    a copy effect's 706.2 name override already lives. One place, and every
    reader gets the new name at once: the characteristics layers, `selector.name`,
    the legend rule and the serializer.

    The two near misses are both the wrong shape. `change_text` rewrites
    *creature types* and the loader refuses it anything else; `become_copy`'s
    `except_name` renames a permanent that is copying something, which The
    Irencrag is not -- it stays itself and is called something else.

    Permanent for as long as the permanent is: `reset_permanent_state` clears
    it, so a renamed artifact that dies comes back answering to its printed
    name (400.7).
    """
    name = str(spec.get("name") or "")
    if not name:
        return
    oids = yield from choose_objects(ctx, spec.get("objects"), "Renamed")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None or not obj.on_battlefield:
            continue
        obj.renamed_to = name
    ctx.state.bump_chars()


@register("change_text")
def op_change_text(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Change the text of that creature by replacing all instances of one
    creature type with Vampire." New Blood. Layer 3 (613.1c).

    The **opposite** of `add_subtype`, and the pair is worth holding in mind
    because the two printed lines look alike. "It becomes a Vampire in addition
    to its other types" (Captivating Vampire) leaves the printed word in place,
    so the creature still answers to its old tribe's lords and its old tribe's
    removal, and its own rules text is untouched. This one *replaces* the word,
    and replaces it everywhere -- the subtype line and every instance inside the
    permanent's own abilities. That second half is why anyone casts New Blood:
    a stolen "other Goblins you control get +1/+0" becomes a Vampire lord.

    The choice is `ask_mode`, so **no new `DecisionKind`** -- the same argument
    `choose_type` makes. "Pick one of these labels, hand back the index" is
    exactly this question, so legality's `_choice_actions`, `game.apply` and the
    authoring verifier's auto-answer table all work unchanged.

    The candidates are the types with an *instance* in the target's printed text
    rather than every creature type in the pool. Naming a word the card never
    says replaces nothing, so the options removed are the options that do
    nothing -- and what it buys is a prompt of two or three real choices instead
    of the 400-entry cap `choose_type` needs, on a card whose whole decision is
    which of this creature's words to rewrite.

    Written onto the target, not held as a `TempEffect`: the printed effect
    lasts indefinitely, and a permanent that leaves and comes back is a new
    object with its printed text, which is what `reset_permanent_state` already
    does with `added_subtypes`.
    """
    replacement = str(spec.get("to") or "")
    if not replacement:
        return
    oids = yield from choose_objects(ctx, spec.get("objects"), "Change the text of")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None or not obj.on_battlefield:
            continue
        candidates = sorted(printed_type_instances(ctx.state, ctx.state.card_of(obj)))
        # The replacement itself is not a candidate: "replacing all instances of
        # Vampire with Vampire" is a choice with no consequence, and offering it
        # on a creature that is *already* a Vampire would make the prompt look
        # like the card had done something.
        candidates = [t for t in candidates if t != replacement]
        if not candidates:
            continue
        picked = yield from ask_mode(
            ctx,
            f"Replace which creature type with {replacement}?",
            candidates,
            ctx.controller,
        )
        if not picked:
            continue
        obj.text_changes = (*obj.text_changes, (candidates[picked[0]], replacement))
        ctx.state.bump_chars()


@register("pump")
def op_pump(ctx: EffectContext, spec: Mapping[str, Any]):
    power = evaluate_value(ctx, spec.get("power", 0))
    toughness = evaluate_value(ctx, spec.get("toughness", 0))
    until_player = until_player_of(ctx, spec)
    oids = yield from choose_objects(ctx, spec.get("objects"), "Pump")
    for oid in oids:
        pump(ctx.state, oid, power, toughness, source=ctx.source_oid, until_player=until_player)


@register("grant_keyword")
def op_grant_keyword(ctx: EffectContext, spec: Mapping[str, Any]):
    """Grant keywords until end of turn, or -- with ``duration: "permanent"`` --
    for as long as the permanent lasts.

    Riot's "enters with haste" is the second: a haste that wore off at cleanup
    would let the creature attack the turn it arrived and be indistinguishable
    from the counter mode ever after, which is not a smaller version of the
    card, it is the wrong one half the time.
    """
    keywords = spec.get("keywords") or ([spec["keyword"]] if "keyword" in spec else [])
    permanent = str(spec.get("duration", "until_end_of_turn")) == "permanent"
    # "…and gain lifelink **until your next turn**" -- Sorin, Solemn Visitor.
    until_player = until_player_of(ctx, spec)
    oids = yield from choose_objects(ctx, spec.get("objects"), "Grant")
    for oid in oids:
        for keyword in keywords:
            grant_keyword(
                ctx.state,
                oid,
                str(keyword),
                source=ctx.source_oid,
                permanent=permanent,
                until_player=until_player,
            )


@register("grant_protection")
def op_grant_protection(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Creatures you control gain protection from each color until end of turn."

    The effect half of the `protection` static, which existed only as a printed
    ability on a permanent: `protection_from` collected candidates from
    `_battlefield_statics`, which walks `card.abilities` and never saw anything
    granted. Akroma's Will is the card, and there is no near miss --
    `grant_keyword` cannot carry a parameter, and protection is parameterised by
    definition ("from black", "from Wizards").

    One `TempEffect` per quality rather than one carrying a list, because
    `TempEffect.keyword` is already a single string and `protection_from`
    already returns a flat set of qualities: three colours is three entries and
    nothing had to learn a new shape.

    Three things arrived with Teferi's Protection and The One Ring, and all
    three are additions to this one op rather than a second one: a ``player``
    recipient, the quality ``from_everything``, and a ``duration`` that outlasts
    the turn. A separate "grant protection to a player" op would have been a
    second place for "protection from black" to mean something, and the two
    would drift the first time a quality was added.
    """
    from ..characteristics import resolve_chosen_color_list
    from ..primitives import grant_player_protection
    from ..structs import PROTECTION_COLORLESS, PROTECTION_EVERYTHING

    # "…protection from the color of your choice" -- Brave the Elements, whose
    # colour is named by a `choose_color` earlier in the same effect list and
    # read back off the spell's own object. The substitution is the leaf the
    # anthem and the mana ability use; an unmade choice drops out, so the
    # sentence grants protection from nothing rather than from everything.
    source = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
    qualities = [
        *resolve_chosen_color_list(spec.get("from_colors"), source),
        *(spec.get("from_types") or ()),
        *(spec.get("from_subtypes") or ()),
    ]
    # "…protection from **everything**" (702.16i) -- Teferi's Protection, The
    # One Ring. A quality in the same flat list rather than a flag beside it,
    # because every rule that reads protection reads that list; a boolean would
    # be a second question asked in four places, which is how one of them comes
    # to be forgotten.
    if spec.get("from_everything"):
        qualities.append(PROTECTION_EVERYTHING)
    # "…protection from **colorless**" (Giver of Runes) -- the same sentinel
    # shape for the same reason: colorless is not a colour letter (105.2c).
    if spec.get("from_colorless"):
        qualities.append(PROTECTION_COLORLESS)
    if not qualities:
        return
    # "**You** gain protection from everything until your next turn." A seat
    # cannot come out of `choose_objects` -- it resolves object ids and the loop
    # below skips anything not on the battlefield -- so the player half is its
    # own clause, reading the ordinary player spec and writing to the table
    # instead of to an object's `until_eot`.
    if (who := spec.get("player")) is not None:
        duration = str(spec.get("duration", "until_your_next_turn"))
        for pid in select_players(ctx, who):
            grant_player_protection(ctx.state, pid, qualities, duration, source=ctx.source_oid)
    if spec.get("objects") is None:
        return
    oids = yield from choose_objects(ctx, spec.get("objects"), "Grant protection to")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None or not obj.on_battlefield:
            continue
        for quality in qualities:
            obj.until_eot.append(
                TempEffect(
                    kind="protection",
                    keyword=str(quality),
                    source=ctx.source_oid,
                    timestamp=ctx.state.alloc_timestamp(),
                )
            )
    ctx.state.bump_chars()


@register("animate")
def op_animate(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Becomes a 4/4 white and blue Elemental creature with vigilance until end
    of turn. It's still a land."

    One op for the whole sentence, keywords included, rather than an `animate`
    beside a `grant_keyword`: the authoring verifier's residual gate asks each
    *ability* which printed sentence it implements, and a creature-land's
    animation is one sentence.  Splitting it would work and would read as two
    claims on the same line.

    Distinct from `set_pt`, which is a compensating pump over whatever the
    permanent's power happens to be right now.  An animation names the base
    value, so counters and anthems add to it instead of being cancelled by it.
    """
    power = evaluate_value(ctx, spec.get("power", 0))
    toughness = evaluate_value(ctx, spec.get("toughness", 0))
    types = [str(t) for t in spec.get("types", ("Creature",))]
    subtypes = [str(t) for t in spec.get("subtypes", ())]
    colors = [str(c) for c in spec.get("colors", ())]
    keywords = [str(k) for k in spec.get("keywords", ())]
    # "…with \"**During your turn**, this creature has first strike\"" -- the
    # Restless cycle, Restless Spire among them. A quoted ability on the
    # animated body, live for half the turn cycle, and it has to ride the
    # animation: a flat `keywords` entry would give first strike while blocking
    # on an opponent's turn, and a separate static beside the animation would
    # have no printed line of its own to claim -- the residual gate's objection,
    # and the reason Raging Ravine still fails.
    your_turn_keywords = [str(k) for k in spec.get("your_turn_keywords", ())]
    # "Target artifact or creature loses all abilities and **becomes a green Elk
    # creature with base power and toughness 3/3**." Oko, Thief of Crowns. No
    # printed duration, so `duration: "permanent"` -- the loader refuses any
    # other spelling than the pair `gain_control` takes -- and no "in addition
    # to its other types", so `exact`: the colours, card types and creature
    # types named replace the permanent's own.
    permanent = spec.get("duration", "until_end_of_turn") == "permanent"
    exact = bool(spec.get("exact", False))
    # "**Until your next turn**, it becomes a 5/5 Elemental creature with
    # haste" -- Nissa, Vital Force. The body and its keywords share the clock.
    until_player = until_player_of(ctx, spec)
    oids = yield from choose_objects(ctx, spec.get("objects"), "Animate")
    for oid in oids:
        animate(
            ctx.state,
            oid,
            power,
            toughness,
            types=types,
            subtypes=subtypes,
            colors=colors,
            your_turn_keywords=your_turn_keywords,
            source=ctx.source_oid,
            permanent=permanent,
            exact=exact,
            until_player=until_player,
        )
        for keyword in keywords:
            grant_keyword(
                ctx.state,
                oid,
                keyword,
                source=ctx.source_oid,
                permanent=permanent,
                until_player=until_player,
            )


@register("monstrosity")
def op_monstrosity(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Monstrosity N": counters and a one-way flag, in that order.

    The flag is the mechanic. Without it the ability is a repeatable pump, and
    the "when this becomes monstrous" trigger that usually accompanies it would
    fire every time rather than once.
    """
    from ..events import EventType
    from ..triggers import fire

    amount = evaluate_value(ctx, spec.get("amount", 1))
    oid = ctx.source_oid
    obj = ctx.state.objects.get(oid) if oid is not None else None
    if obj is None or not obj.on_battlefield or obj.monstrous:
        return
    add_counters(ctx.state, oid, PLUS_ONE, amount, source=oid)
    obj.monstrous = True
    ctx.state.bump_chars()
    fire(
        ctx.state,
        EventType.BECAME_MONSTROUS,
        player=obj.controller,
        source=oid,
        oid=oid,
        card=obj.def_id,
        amount=amount,
    )


@register("become_level")
def op_become_level(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "This Class's level becomes N." -- the resolution of "{cost}: Level N".

    716.2a's whole effect, and never written by a card: the loader supplies it
    on a ``kind: "level"`` ability, the way it supplies a chapter's trigger, and
    refuses it anywhere else. The *restriction* half of the same rule ("only if
    this Class is level N-1") is a legality question and lives in
    `legality._ability_aims`; by the time this runs the ability was legal.

    **Becomes**, literally. The level is set to N, not raised by one, so a copy
    of the level-2 ability resolving on a Class already at 2 changes nothing.

    A source that has left the battlefield has no level to set: the ability
    still resolves (113.7a) and does nothing, which is what the printed card
    does with a Class destroyed in response.
    """
    oid = ctx.source_oid
    obj = ctx.state.objects.get(oid) if oid is not None else None
    if obj is None or not obj.on_battlefield:
        return
    level = int(spec["level"])
    if obj.class_level == level:
        return
    obj.class_level = level
    # The level is a pipeline input: a level-3 anthem switches on here.
    ctx.state.bump_chars()
    # After the write, so what triggers off it is collected from a Class that
    # already has the new level's abilities (716.4).
    from ..events import EventType
    from ..triggers import fire

    fire(
        ctx.state,
        EventType.BECAME_LEVEL,
        player=obj.controller,
        source=oid,
        oid=oid,
        card=obj.def_id,
        level=level,
    )


@register("freeze")
def op_freeze(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "…don't untap during their controllers' untap steps for as long as you
    control this creature."

    Recorded on the frozen permanent as the *oid of the source*, rather than as
    a flag with a lifetime of its own: the hold has to end when the source does,
    and pointing at it is the only way the untap step can tell.
    """
    oids = yield from choose_objects(ctx, spec.get("objects"), "Freeze")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is not None and obj.on_battlefield:
            obj.frozen_by = ctx.source_oid


@register("grant_ability")
def op_grant_ability(ctx: EffectContext, spec: Mapping[str, Any]):
    """Give a permanent one of this card's ``grantable_abilities``.

    "…and 'Whenever this creature deals combat damage to a player, draw a
    card'." The quoted ability is written out on the granting card and referred
    to here by index, so there is one definition of it rather than a copy.

    Until end of turn by default, or ``duration: "permanent"`` for as long as
    the permanent lasts -- the same option `grant_keyword` already carries.
    Clavileño's "It gains 'when this creature dies, …'" prints no duration, and
    a grant swept at cleanup would be a strictly weaker card that looks
    identical on the turn it was made.
    """
    # Both spellings, because two shipped cards disagree and the disagreement is
    # invisible: `ability` and `ability_index` each defaulted to 0, so a card
    # using the other name worked by accident and would silently have granted
    # the wrong ability the first time a card carried two grantables. The loader
    # now insists on one of them being present.
    index = int(spec.get("ability", spec.get("ability_index", 0)))
    permanent = str(spec.get("duration", "until_end_of_turn")) == "permanent"
    oids = yield from choose_objects(ctx, spec.get("objects"), "Grant an ability to")
    if ctx.source_oid is None:
        return
    for oid in oids:
        grant_ability(ctx.state, oid, index, ctx.source_oid, permanent=permanent)


@register("skip_untap")
def op_skip_untap(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "It doesn't untap during its controller's next untap step."

    A *one-shot*, cleared by the untap step it skips -- which is what separates
    it from `freeze`, where the hold lasts as long as its source is on the
    battlefield. Using either for the other would be wrong in both directions,
    so they are two ops over two fields rather than one with a flag.
    """
    oids = yield from choose_objects(ctx, spec.get("objects"), "Keep tapped")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is not None and obj.on_battlefield:
            obj.skip_next_untap = True


@register("lock_abilities")
def op_lock_abilities(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Its activated abilities can't be activated this turn."

    Separate from `tap`, which usually accompanies it, because the two are
    different halves of the sentence and a card may want only one.

    ``duration: "until_your_next_turn"`` is Dovin Baan's "…**until your next
    turn**, … its activated abilities can't be activated", which must still
    bind on the opponent's turn -- the only turn it matters on.
    """
    until_player = until_player_of(ctx, spec)
    oids = yield from choose_objects(ctx, spec.get("objects"), "Lock")
    for oid in oids:
        lock_abilities(ctx.state, oid, source=ctx.source_oid, until_player=until_player)


@register("set_pt")
def op_set_pt(ctx: EffectContext, spec: Mapping[str, Any]):
    """Set base power/toughness until end of turn.

    Implemented as a pump that cancels the current values, which is equivalent
    under this engine's fixed-order characteristic pipeline for the cards in the
    curated decks (none of them combine ``set_pt`` with counters).
    """
    from ..characteristics import chars

    power = evaluate_value(ctx, spec.get("power", 0))
    toughness = evaluate_value(ctx, spec.get("toughness", 0))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Set power/toughness")
    for oid in oids:
        current = chars(ctx.state, oid)
        pump(
            ctx.state,
            oid,
            power - current.power,
            toughness - current.toughness,
            source=ctx.source_oid,
        )
