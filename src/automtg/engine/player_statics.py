"""Player-wide static effects: what the permanents a player controls do to
the rules that apply to that player -- attack and block restrictions, taxes,
cost reduction, land-drop and casting permissions, token replacements.

Every function here is a wrapper over ``characteristics._active_player_statics``;
the layer engine itself stays in ``characteristics``.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any

from .carddef import CardDef
from .characteristics import (
    _battlefield_statics,
    _matches,
    _matches_printed,
    _static_active,
    _static_value,
    chars,
    resolve_chosen_colors,
    resolve_chosen_subtypes,
)
from .enums import Step, Zone
from .objects import GameObject

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


def _active_player_statics(
    state: GameState, effect: str
) -> Iterator[tuple[GameObject, Mapping[str, Any]]]:
    """Every *active* player-wide ``effect`` static on the battlefield, with its source.

    The player-wide twin of :func:`_battlefield_statics`, and the reason it
    exists is the one thing the two used to disagree about. That function gates
    each static on :func:`_static_active`; the four hand-rolled walks that read
    the `affects_player` effects did not, so a `condition` written beside
    `play_lands_from_library_top` was validated by the loader, stored on the
    ability, and then never asked. The card loaded clean, printed its "as long
    as" clause and granted the permission unconditionally -- a silent
    over-grant, which is worse than refusing the card.

    Verge Rangers is the witness: "**as long as an opponent controls more lands
    than you**, you may play lands from the top of your library" would otherwise
    have been Oracle of Mul Daya's unconditional permission on a 3/2 first
    striker.

    The condition reads pipeline *inputs* here exactly as it does in
    `_battlefield_statics`, and the acyclicity argument is easier rather than
    harder: these readers run at legality, payment, trigger collection,
    serialization and the cleanup step -- outside the characteristics pipeline
    entirely -- so there is no layer whose output one could come to depend on.

    The source is yielded beside the static because two of the callers need it:
    `affects_player` is resolved against its controller, and a `condition`'s
    "you" and its `counters` head are both relative to the permanent carrying it.
    """
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        for ability in state.card_of(obj).abilities:
            static = ability.static
            if not ability.is_static or not static:
                continue
            if static.get("effect") != effect:
                continue
            # Druid Class's "You may play an additional land on each of your
            # turns" is a level-2 ability: at level 1 the Class does not have it
            # (716.2b). Asked here because this walk reads the printed face.
            if not ability.present_at(obj.class_level):
                continue
            if not _static_active(state, obj, static):
                continue
            yield obj, static


def _reaches_player(source: GameObject, static: Mapping[str, Any], pid: int) -> bool:
    """Does a player-wide static's ``affects_player`` name ``pid``?

    Defaulting to ``"you"`` matches the loader, which requires the key on every
    effect that reaches here -- so the default is unreachable from an authored
    card and is only a floor under hand-built states.
    """
    who = static.get("affects_player", "you")
    if who == "you":
        return source.controller == pid
    if who == "opponent":
        return source.controller != pid
    return True


def life_loss_multiplier(state: GameState, pid: int) -> int:
    """What a life loss by ``pid`` is multiplied by right now.  Usually 1.

    Bloodletter of Aclazotz: "If an opponent would lose life during your turn,
    they lose twice that much life instead."  The "during your turn" half is an
    ordinary ``condition`` on the static and is honoured by
    `_active_player_statics`, which is the whole reason this reads through that
    function rather than walking the battlefield itself -- a condition written
    beside a player-wide static and never asked is the silent over-grant that
    function exists to stop.

    **Multiplied, not summed.**  Two Bloodletters are two separate replacements
    of one event, each applying once (614.5), and a loss doubled twice is
    quadrupled -- which is also why the empty case has to return 1 rather than
    0.  616.1 lets the affected player order two applicable replacements and
    this engine does not ask, the same divergence `_token_creation_plan`
    records; for a product the order cannot show, so here it costs nothing.

    Short-circuits on an empty battlefield walk, because this is asked on every
    point of life any player loses -- every damage to a player, every paid life,
    every drain -- so the games playing none of these cards must pay nothing.
    """
    multiplier = 1
    for obj, static in _active_player_statics(state, "replace_life_loss"):
        if _reaches_player(obj, static, pid):
            multiplier *= int(static.get("loss_multiplier", 1))
    return multiplier


def life_gain_multiplier(state: GameState, pid: int) -> int:
    """What a life gain by ``pid`` is multiplied by right now.  Usually 1.

    Alhammarret's Archive: "If you would gain life, you gain twice that much
    life instead."  The mirror of :func:`life_loss_multiplier`, and read the
    same way for the same reasons: through `_active_player_statics`, so an "as
    long as" clause beside it is asked; **multiplied**, not summed, because two
    Archives are two replacements of one event each applying once (614.5) and
    a gain doubled twice is quadrupled; and 616.1's ordering is not asked,
    which for a product cannot show.

    Asked by `primitives.gain_life` only, which is the one place a life total
    goes up -- lifelink reaches it too (702.15b), so a lifelinking creature
    under an Archive gains twice the damage it dealt, while the damage itself
    is untouched.
    """
    multiplier = 1
    for obj, static in _active_player_statics(state, "replace_life_gain"):
        if _reaches_player(obj, static, pid):
            multiplier *= int(static.get("gain_multiplier", 1))
    return multiplier


def player_cant_gain_life(state: GameState, pid: int) -> bool:
    """Is ``pid`` forbidden from gaining life right now?  Usually false.

    Erebos, God of the Dead: "Your opponents can't gain life."  A prohibition
    on a *player*, read through `_active_player_statics` like every other
    player-wide static, so it lifts the moment its source leaves the
    battlefield and an "as long as" clause beside it is asked.

    One reader, `primitives.gain_life`, because that is the one place a life
    total goes up -- the `gain_life` op and lifelink both arrive there -- and it
    is asked **before** `life_gain_multiplier`: a gain that cannot happen is not
    doubled into one that can (101.2, "can't" beats every effect that would
    make it happen, a replacement included).
    """
    return any(
        _reaches_player(obj, static, pid)
        for obj, static in _active_player_statics(state, "cant_gain_life")
    )


def draw_replacements(state: GameState, pid: int) -> list[tuple[int, int]]:
    """The ``replace_draw`` statics that apply to ``pid``'s next draw right now.

    Thought Reflection: "If you would draw a card, draw two cards instead." Bard,
    King of Dale and Alhammarret's Archive add "except the first one you draw in
    each of your draw steps", which is ``except_first_in_draw_step``.

    Each entry is ``(source oid, draw_multiplier)``. The oid is the identity
    `replacements.draw` uses to keep 614.5 -- a replacement never applies twice
    to the same event, so the draws a doubler produced are not doubled by that
    doubler again, while a *second* doubler (a different oid) still applies to
    each of them, which is how two compound (616.1).

    Asked **per draw**, never once for a batch, because the exemption moves:
    the answer for the first card of a draw step is not the answer for the
    second (121.2 -- each card drawn is its own draw).
    """
    out: list[tuple[int, int]] = []
    for obj, static in _active_player_statics(state, "replace_draw"):
        if not _reaches_player(obj, static, pid):
            continue
        if static.get("except_first_in_draw_step") and _first_draw_of_draw_step(state, pid):
            continue
        out.append((obj.oid, int(static.get("draw_multiplier", 1))))
    return out


def wins_on_empty_draw(state: GameState, pid: int) -> bool:
    """Does ``pid`` win instead of drawing from an empty library?

    Jace, Wielder of Mysteries and Laboratory Maniac: "If you would draw a card
    while your library has no cards in it, you win the game instead."

    A plain yes/no rather than a multiplier, because the replacement has no
    size -- it substitutes a different outcome for the draw rather than scaling
    it, which is exactly why it could not be spelled as a `replace_draw` whose
    only key is a number the loader refuses below 2.

    Read in `replacements._draw_one`, the seam every post-opening-hand draw
    passes through one card at a time, so it applies to a `draw` op, the draw
    step, and a `draw` rider on somebody else's card alike.
    """
    return _player_static(state, pid, "replace_empty_draw")


def mill_multiplier(state: GameState, pid: int) -> int:
    """How many times over ``pid`` mills, right now (`replace_mill`).

    Bruvac the Grandiloquent: "If an opponent would mill one or more cards, they
    mill twice that many cards instead." Fraying Sanity says it of one player.

    Returns a single factor rather than `draw_replacements`' list of
    ``(source, multiplier)`` pairs, and the difference is a rules one rather
    than a convenience. 701.13a makes milling N cards **one** event, where 121.2
    makes drawing N cards N separate draws -- so a mill is replaced once, in
    place, by multiplying its count, and there is no per-card recursion for
    614.5 to guard against. Two Bruvacs are two different replacements applying
    to the same event, so they compound (616.1) to four, which is the product
    taken here; and because each source is visited once, none applies twice.
    """
    factor = 1
    for obj, static in _active_player_statics(state, "replace_mill"):
        if not _reaches_player(obj, static, pid):
            continue
        factor *= max(1, int(static.get("mill_multiplier", 1)))
    return factor


def _first_draw_of_draw_step(state: GameState, pid: int) -> bool:
    """Would the card ``pid`` is about to draw be the first of *their* draw step?

    "Your draw steps": only the active player has one, so an opponent drawing
    during it is never exempt. And "the first one you **draw**", a card rather
    than the turn-based action: if that draw was skipped or dredged, whatever
    card is drawn first in the step is still the first.
    """
    return (
        state.step is Step.DRAW
        and state.active_player == pid
        and state.cards_drawn_this_draw_step.get(pid, 0) == 0
    )


def player_doubles_land_mana(state: GameState, pid: int) -> bool:
    """Vorinclex: "whenever you tap a land for mana, add one mana of any type
    that land produced"."""
    return _player_static(state, pid, "double_land_mana")


def mana_added_on_tap(state: GameState, pid: int, oid: int) -> list[tuple[int, tuple[int, ...]]]:
    """What ``add_mana_on_tap`` statics add when ``pid`` taps ``oid`` for mana.

    Crypt Ghast: "Whenever you tap a Swamp for mana, add an additional {B}." A
    triggered mana ability (605.1b): it triggers off a mana ability and resolves
    immediately, never using the stack (605.4a), so it is answered here at the
    mana choke point beside `player_doubles_land_mana` rather than queued.

    Returns ``(source oid, mana)`` pairs, one per applicable static, so the pool
    can tag each pip with the permanent whose ability made it -- the Ghast, not
    the Swamp. Two Ghasts add two {B}: each is its own triggered ability.

    ``tapped_permanent`` is matched against the tapped permanent's *current*
    characteristics, so a land Urborg, Tomb of Yawgmoth has made a Swamp is a
    Swamp. ``affects_player`` names whose taps count -- "you" for Crypt Ghast,
    "any" for "whenever a Forest is tapped for mana, its controller adds"
    (Vernal Bloom). The mana always goes to the player who tapped.

    ``attached`` is the Aura form -- Wild Growth's "whenever enchanted land is
    tapped for mana". It is checked against ``source.attached_to`` rather than
    against the tapped permanent's characteristics, because it names *one*
    permanent and every other key names a class: written as Vernal Bloom's
    ``{"types": ["Land"]}`` the card would pay out for every land its controller
    taps, which is a different and far larger card. An Aura attached to nothing
    matches nothing, which is the same answer a state-based action is about to
    give by binning it.
    """
    out: list[tuple[int, tuple[int, ...]]] = []
    tapped: Any = None
    for source, static in _active_player_statics(state, "add_mana_on_tap"):
        if not _reaches_player(source, static, pid):
            continue
        wanted = static.get("tapped_permanent") or {}
        if wanted.get("attached") and source.attached_to != oid:
            continue
        if tapped is None:
            tapped = chars(state, oid)
        if not all(t in tapped.types for t in wanted.get("types", [])):
            continue
        if not all(t in tapped.supertypes for t in wanted.get("supertypes", [])):
            continue
        subtypes = wanted.get("subtypes", [])
        if subtypes and not any(t in tapped.subtypes for t in subtypes):
            continue
        out.append((source.oid, _mana_added(source, static.get("add_mana", ""))))
    return out


def _mana_added(source: Any, add_mana: Any) -> tuple[int, ...]:
    """The mana one ``add_mana_on_tap`` static adds, as a production tuple.

    Almost always the literal the card printed. ``{"chosen_color_of": "self"}``
    is Utopia Sprawl's "one mana of the chosen color", where the symbol is a
    question about the Aura and cannot be known until the colour has been
    chosen. The same spelling and the same reader as the ``add_mana`` *op*, so
    one card cannot mean two things by it.

    A source that has chosen no colour yet adds **nothing** -- the match-nothing
    default the chosen colour has everywhere else, and the only safe answer here,
    since this runs inside cost payment where nothing may stop to ask (605.1a).
    """
    from .characteristics import resolve_chosen_color_list
    from .mana import parse_mana_production

    if isinstance(add_mana, Mapping):
        colors = resolve_chosen_color_list([add_mana], source)
        return parse_mana_production("".join(f"{{{c}}}" for c in colors))
    return parse_mana_production(str(add_mana))


def players_freezing_opponent_lands(state: GameState) -> frozenset[int]:
    """Everyone whose ``freeze_opponent_lands`` static is on the battlefield.

    Returned as a set of players rather than asked per-player, because the
    question at the mana choke point is "does *anybody but this land's
    controller* have it", and asking once is cheaper than asking per opponent
    inside a payment.
    """
    return frozenset(
        obj.controller for obj, _ in _active_player_statics(state, "freeze_opponent_lands")
    )


def players_doubling_land_triggers(state: GameState) -> frozenset[int]:
    """Everyone whose ``double_land_triggers`` static is on the battlefield.

    Ancient Greenwarden. Shaped like `players_freezing_opponent_lands` and read
    by `triggers._land_trigger_doublers`, which owns the much narrower question
    of *which* event doubles; this owns only who is switched on, so the
    "as long as…" gate lives in one place with the other six.
    """
    return frozenset(
        obj.controller for obj, _ in _active_player_statics(state, "double_land_triggers")
    )


def player_has_no_hand_limit(state: GameState, pid: int) -> bool:
    """Whether this player has no maximum hand size (402.2, 514.1).

    Reliquary Tower, Thought Vessel, Nezahal. Written as a player-wide static
    like ``extra_land_drops`` rather than as a characteristic, because it is a
    fact about the *player* and there is no object for it to attach to.

    Two sources, one answer. The statics above last as long as the permanent
    printing them; `PlayerState.has_no_maximum_hand_size` is the one-shot
    version -- Sea Gate Restoration's "for the rest of the game", written by the
    `no_maximum_hand_size` op off a sorcery that is in the graveyard by the
    time any cleanup step asks. Both are read here rather than the flag being
    read in `turn._cleanup_step`, so there is one rule path to the hand limit
    and nothing that asks it can see half the answer.
    """
    if state.players[pid].has_no_maximum_hand_size:
        return True
    return _player_static(state, pid, "no_hand_limit")


def player_pays_life_for_black(state: GameState, pid: int) -> bool:
    """Whether every ``{B}`` in a cost this player pays may be paid with 2 life.

    K'rrik, Son of Yawgmoth: "For each {B} in a cost, you may pay 2 life rather
    than pay that mana." A fact about the *payer*, read wherever a cost is
    priced -- the cast line in `casting._cast_variant` and `Game._cast`, and
    every other cost through `costs.can_pay` / `costs.pay` -- by turning each
    black pip into a Phyrexian one with `ManaCost.black_as_phyrexian`.
    """
    return _player_static(state, pid, "black_mana_as_phyrexian")


def player_skips_draw_step(state: GameState, pid: int) -> bool:
    """Whether any ``skip_draw_step`` static stops this player's turn-based draw.

    Necropotence, Yawgmoth's Bargain, Solitary Confinement. Player-wide like
    `player_has_no_hand_limit` and read at the same kind of place -- the turn
    walk, in `turn._draw_step` -- because a step that does not happen is a fact
    about the turn rather than a characteristic of any permanent.

    What it does **not** suppress is the step itself. 505.1 still has a draw
    step; only its turn-based action (504.1) is skipped, so
    ``EventType.DRAW_STEP`` still fires and the abilities that watch for the
    step -- Sagas' lore tick, "at the beginning of your draw step" triggers --
    keep working under a Necropotence. Suppressing the event too is the tempting
    one-line version and is a different game: it would silently stop a Saga
    advancing, and nothing on screen would say why.

    Only the *turn-based* draw. A `draw_cards` op resolving from a spell is
    untouched, which is what the printed card says -- Necropotence's own
    controller may still cast Ancestral Recall.
    """
    return _player_static(state, pid, "skip_draw_step")


def player_skips_extra_turn(state: GameState, pid: int) -> bool:
    """Whether a ``skip_extra_turn`` static makes this player skip an extra turn.

    Trouble in Pairs: "If an opponent would begin an extra turn, that player
    skips that turn instead." Read by `turn._take_extra_turn` at the moment a
    scheduled extra turn would begin, which is when a replacement effect applies
    (614.10) -- not by the `extra_turn` op, whose job is only to schedule.

    Only **extra** turns. The printed line is inert against the ordinary turn
    order, and nothing else reads this, so there is no path by which it could
    skip one.
    """
    return _player_static(state, pid, "skip_extra_turn")


def attack_forbidden(state: GameState, oid: int) -> bool:
    """Is this creature under a global "can't attack" static?

    Stormtide Leviathan's "creatures without flying or islandwalk can't
    attack". Unlike every other static, its filter routinely names creatures its
    controller does not control -- the card is a lock on the whole table -- so
    `affects` here is written with an explicit ``controller: "any"``.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "cant_attack":
            continue
        if _matches(state, obj, source_obj, static.get("affects")):
            return True
    return False


def attack_defender_forbidden(state: GameState, oid: int, defender: int) -> bool:
    """May this creature **not** attack ``defender``, or a planeswalker they control?

    Combat Calligrapher -- "Inklings can't attack you or planeswalkers you
    control." A prohibition that is a *continuous ability of a permanent*,
    scoped to one seat and filtered on the attacking creature's printed
    characteristics. None of the three near misses is that shape.

    Written as `attack_tax`'s twin, with the price taken out: `affects` says
    which creatures are stopped and the static's own controller is the seat they
    are stopped from attacking -- "creatures can't attack **you**" is the same
    sentence in both, once as a toll and once as a wall.
    `cant_attack`/`attack_forbidden` is the wrong one because no defender is in
    the question at all, so an Inkling under it could not attack *anybody* --
    strictly stronger than the printed line, and it would switch off
    Calligrapher's own second ability, which hands opponents Inklings expressly
    to keep them swinging at each other. The `cant_attack_player` op has the
    right scope and carries no creature filter at all, and its `duration` is
    required precisely because it is a resolving one-shot with no permanent to
    hang off, so it cannot be a creature's continuous ability.

    **Planeswalkers are included here**, which is the opposite answer from that
    op, and it is opposite for the reason goad's is opposite to Ghostly
    Prison's: the answer follows the printed sentence rather than a house rule.
    "You can't attack that player" is 506.2's reading -- attacking somebody's
    planeswalker is not attacking them -- and the sentence *this* effect exists
    for says "or planeswalkers you control" out loud, so neither half is
    inferred. A planeswalker's controller **is** the defending player (506.2)
    and `combat.legal_planeswalker_defenders` passes it, so the one seat test
    below covers the walker as well as the chair, exactly as goad's does.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "cant_attack_you":
            continue
        # The wall protects the seat the permanent is under -- the line
        # `attack_tax` already draws, and the whole shape of the family.
        if source_obj.controller != defender:
            continue
        if _matches(state, obj, source_obj, static.get("affects")):
            return True
    return False


def any_defender_attack_prohibition(state: GameState) -> bool:
    """Is there a ``cant_attack_you`` static on the battlefield at all?

    The cheap half of `combat.can_attack`'s guard against a creature with
    nowhere left to attack, beside the `attack_restrictions` list test that
    guard already had. The expensive half -- "has this creature any legal
    defender left" -- walks every seat and every planeswalker through
    `attack_target_forbidden`, and is worth asking only in a game that plays one
    of these cards.
    """
    return any(
        static.get("effect") == "cant_attack_you" for _, static in _battlefield_statics(state)
    )


def attack_tax(state: GameState, oid: int, defender: int) -> str:
    """The mana a creature's controller must pay to declare it against ``defender``.

    "Creatures can't attack you unless their controller pays {2} for each
    creature they control that's attacking you" -- Propaganda, and the whole
    pillowfort family behind it (Ghostly Prison, Norn's Annex, Sphere of
    Safety).

    Neither near miss can say it. `cant_attack` and the `cant_attack_player` op
    are absolute prohibitions with no cost to them, so a card built on either is
    a *lock* rather than a tax -- strictly stronger than what is printed, and it
    would look entirely normal on screen. `ward` is the only other
    cost-parameterised static and it prices *targeting*, paying out as a
    triggered counter that never reaches the declare-attackers step.

    Returned as a mana string rather than a `Cost`, so this module stays free of
    `costs`, which imports it. Taxes from several permanents add up, which is
    what two Propagandas do.

    The per-creature scaling in the printed text falls out of *where* this is
    charged: the price is settled once per attacker as it is declared, so a
    three-creature attack pays {2} three times, exactly as 508.1g totals it.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return ""
    generic = 0
    parts: list[str] = []
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "attack_tax":
            continue
        # The tax protects the seat the permanent is under, which is the whole
        # shape of the card: "creatures can't attack **you**".
        if source_obj.controller != defender:
            continue
        if not _matches(state, obj, source_obj, static.get("affects")):
            continue
        # The same `cost` mapping ward stores, so the two go through one
        # validator and there is one place for a price to be written.
        spec = static.get("cost")
        inner = str((spec or {}).get("mana") or "").strip() if isinstance(spec, Mapping) else ""
        # Summed rather than concatenated where they are plain generic, so two
        # Propagandas read as {4} instead of an unpayable "{2}{2}".
        if inner.startswith("{") and inner.endswith("}") and inner[1:-1].isdigit():
            generic += int(inner[1:-1])
        elif inner:
            parts.append(inner)
    if generic:
        parts.insert(0, "{" + str(generic) + "}")
    return "".join(parts)


def block_forbidden(state: GameState, oid: int) -> bool:
    """Is this creature under a "can't block" static?

    Unleash's "this creature can't block as long as it has a +1/+1 counter on
    it", and the plain "can't block" printed on a hundred aggressive commons.
    The exact mirror of `attack_forbidden`, down to reusing `_matches`, and a
    static rather than a `Keyword` for the reason `block_restriction` is one:
    a keyword is a characteristic and this is a permission.

    Unlike `attack_forbidden` this is nearly always self-referential -- the
    static sits on the creature it stops -- but the filter is the same one, so
    a global "creatures your opponents control can't block" costs nothing extra.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "cant_block":
            continue
        if _matches(state, obj, source_obj, static.get("affects")):
            return True
    return False


def _alone_forbidden(state: GameState, oid: int, effect: str) -> bool:
    """Is this creature under a "…alone" static of this kind?

    The shared body of the two below, which differ only in the effect name they
    look for. Deliberately **not** folded into `attack_forbidden` and
    `block_forbidden` with a flag: those two answer "may this creature do it at
    all", and every caller of them treats a `True` as an absolute prohibition.
    A creature that can't attack alone can attack, so it must not be visible to
    that question at all -- which is why this is a separate effect name rather
    than an extra key on `cant_attack`.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != effect:
            continue
        if _matches(state, obj, source_obj, static.get("affects")):
            return True
    return False


def attack_alone_forbidden(state: GameState, oid: int) -> bool:
    """ "This creature can't attack alone" -- may it be the *only* attacker?

    A restriction on the declaration as a whole (508.1c), not on the creature,
    so the answer here is only half of it: this says the creature carries the
    restriction, and `combat.attacks_valid` decides whether the declaration
    being built breaks it.
    """
    return _alone_forbidden(state, oid, "cant_attack_alone")


def block_alone_forbidden(state: GameState, oid: int) -> bool:
    """ "This creature can't block alone" -- may it be its controller's only blocker?

    The mirror of `attack_alone_forbidden`, read by `combat.blocks_valid`
    (509.1b) beside menace and `require_all`, which have the same shape: a
    legality that only exists once the whole declaration does.
    """
    return _alone_forbidden(state, oid, "cant_block_alone")


def spell_cost_reduction(state: GameState, pid: int, card: CardDef) -> int:
    """How much less ``pid`` pays for ``card`` because of statics on the board.

    "Creature spells with flying you cast cost {1} less to cast." The card-level
    `cost_reduction` field points the other way -- it discounts the card that
    *carries* it, by counting permanents -- so Warden of Evos Isle cannot be
    written with it. This discounts a **different** card, picked out by that
    card's own printed characteristics.

    The filter is matched against the printed face rather than a permanent,
    which is why it reuses `_matches_printed` and nothing else: the spell is
    still in hand while legality prices it, so there is no board state to read
    and no derived characteristics to recurse into.

    Returns a total, clamped and applied by `costs.cost_reduction` -- the one
    function both legality and payment already call, so a spell offered at the
    reduced price is also paid at it.
    """
    total = 0
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "spell_cost_reduction":
            continue
        filt = static.get("affects_spells")
        if not filt:
            # The loader requires one. Defaulting to `{}` here would make an
            # empty filter match *every* spell, so a compile bug would silently
            # discount the whole game rather than nothing.
            continue
        who = str(filt.get("controller", "you"))
        if who == "you" and source_obj.controller != pid:
            continue
        if who == "opponent" and source_obj.controller == pid:
            continue
        # "Creature spells you cast **of the chosen type** cost {1} less."
        # Herald's Horn. The substitution needs the permanent that made the
        # choice, and this loop has had it all along -- `_battlefield_statics`
        # yields the source beside the static, and only `_matches_printed`'s
        # signature (a printed card, no object) suggested otherwise.
        resolved = resolve_chosen_colors(resolve_chosen_subtypes(filt, source_obj), source_obj)
        if not _matches_printed(card, resolved):
            continue
        total += _static_value(state, static.get("amount"), source_obj)
    return total


def attack_compelled(state: GameState, oid: int) -> bool:
    """Is this creature under a continuous "attacks each combat if able"?

    The permanent counterpart of the `must_attack` op. That op writes a
    one-shot flag on the object -- Bident of Thassa's "this turn", Trench
    Behemoth's "next combat" -- and is spent once the declaration is locked in.
    A printed "This creature attacks each combat if able" is not spent: it is
    true again next turn, and it stops being true the moment its source leaves
    or its condition turns off. That is a static, so it is read live off the
    battlefield rather than stored.

    One effect covers all the printed variants -- "This creature…", "Creatures
    your opponents control…", "Enchanted creature…" -- because they differ only
    in `affects`. Like `cant_attack`, that filter routinely names creatures the
    static's own controller does not control.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "attacks_if_able":
            continue
        if _matches(state, obj, source_obj, static.get("affects")):
            return True
    return False


def untap_also(state: GameState, active_pid: int) -> list[int]:
    """Permanents that untap during *someone else's* untap step.

    Murkfiend Liege: "Untap all green and/or blue creatures you control during
    each other player's untap step." A fact about a set of permanents rather
    than a characteristic of any one of them, so it is read here at the untap
    step rather than layered into `chars` -- the same shape as the player-wide
    statics below, which is what `extra_land_drops` and `no_hand_limit` already
    are.

    "each *other* player's" is the whole of it: on your own untap step these
    creatures untap anyway, so a version that ignored whose turn it is would
    look identical every time you tested it.
    """
    out: list[int] = []
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "untap_during_each_untap_step":
            continue
        if source_obj.controller == active_pid:
            continue
        for oid in state.battlefield:
            obj = state.objects.get(oid)
            if obj is None or obj.controller != source_obj.controller:
                continue
            if _matches(state, obj, source_obj, static.get("affects")):
                out.append(oid)
    return out


def untap_held(state: GameState, active_pid: int) -> set[int]:
    """Permanents a static stops from untapping (`skip_untap_step`).

    "Nonbasic lands don't untap during their controllers' untap steps" (Back to
    Basics); "Creatures don't untap during their controllers' untap steps"
    (Intruder Alarm); "This artifact doesn't untap during your untap step"
    (Mana Vault, `affects: {"self": true}`).

    The exact inverse of :func:`untap_also` directly above, and read in the same
    place for the same reason: whether a permanent untaps is a fact about a set
    of permanents at one moment in the turn, not a characteristic of any one of
    them, so it belongs at the untap step rather than layered into `chars`.

    Three things this has to get right, each of which would be a different card:

    * **Any controller, not just the source's.** Both printed sentences say
      "their controllers' untap steps" -- Intruder Alarm stops the whole table
      untapping, which is the drawback the card is built around. `untap_also`
      filters to `source_obj.controller` because Murkfiend Liege says "you
      control"; this one must not.
    * **It is a printed characteristic with no lifetime of its own.** It holds
      for exactly as long as the source is on the battlefield, and is spent by
      nothing -- unlike `skip_next_untap`, which `untap_all` consumes in the
      untap step it skips.
    * **It must not fight `skip_next_untap`.** A permanent already held by this
      static must not *also* burn its one-shot: `untap_all` checks this set
      first and leaves the flag alone, or Mana Vault's own static would eat the
      skip a Winter Orb effect had put there and release it a turn early.

    Explicit `untap` effects are untouched -- this is read only by the untap
    step, so Mana Vault's own upkeep payment still untaps it (302.6 / the
    printed card), exactly as `frozen_by` leaves targeted untaps alone.
    """
    held: set[int] = set()
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "skip_untap_step":
            continue
        for oid in state.battlefield:
            obj = state.objects.get(oid)
            if obj is None:
                continue
            # The active player's untap step is the only one being resolved, so
            # a permanent somebody else controls is not untapping now anyway;
            # narrowing here keeps the set to what this step would have touched.
            if obj.controller != active_pid:
                continue
            if _matches(state, obj, source_obj, static.get("affects")):
                held.add(oid)
    return held


def _player_static(state: GameState, pid: int, effect: str) -> bool:
    """Whether any *active* permanent grants ``effect`` to this player.

    "Active" is the whole of what `_active_player_statics` adds: an "as long
    as…" clause on a player-wide static is honoured here rather than dropped.
    """
    return any(
        _reaches_player(obj, static, pid) for obj, static in _active_player_statics(state, effect)
    )


def player_cant_cast_spells(state: GameState, pid: int) -> bool:
    """ "Your opponents can't cast spells during your turn." Voice of Victory.

    A prohibition on the *player*, read everywhere a spell can be cast rather
    than at one of those places: `casting._cast_actions` withholds the cast
    actions, and the three resolution-time casts -- `suspend.cast_for_free`
    (suspend, rebound, cascade, ripple, `cast_from_hand`, `play_exiled`,
    `look_at_top`'s `cast_free`), `replacements._offer_cast` (madness, miracle)
    and `op_cast_copy` (707.12: casting a copy *is* casting) -- refuse it. Rule
    101.2 is why the last three matter: when a rule or effect says a player
    may cast something and another says they can't, the "can't" wins, so a
    cascade trigger an opponent already has on the stack does not slip a free
    spell past the lock.

    What it does **not** stop, each on purpose: copying a spell (707.10 -- a
    copy put on the stack was never cast), activating abilities, playing a
    land, and the special actions suspend and foretell (116.2), none of which
    is casting. Grand Abolisher's second half is a different static.

    `affects_player` picks out the stopped seats and `condition` is the
    "during your turn", both answered through `_active_player_statics`, so the
    lock lifts the instant the source leaves or the turn passes.
    """
    return _player_static(state, pid, "cant_cast_spells")


def player_casts_as_though_flash(state: GameState, pid: int) -> bool:
    """"Any player may cast spells as though they had flash." Tidal Barracuda.

    Also Leyline of Anticipation and Vedalken Orrery, with
    ``affects_player: "you"``. The permissive twin of `player_cant_cast_spells`,
    and the first thing in the engine that can widen a *timing* window rather
    than a zone one.

    Read in `casting._timing_ok`, which is why that function had to learn
    `state` and `pid`: it decided casting speed from printed characteristics
    alone (`card.is_instant or FLASH in card.keywords`) and took neither, so no
    permanent on the board could be consulted from it. One seam, twelve callers,
    and every zone a spell can be cast from goes through it -- hand, graveyard,
    exile, a Citadel top, a second face -- which is the whole reason the check
    lives there and not in `_cast_actions` beside the prohibition.

    Granting `Keyword.FLASH` is the tempting substitute and is wrong three times
    over: `_timing_ok` reads the **CardDef**'s keywords and never an object's
    granted ones; a static's filter has no `zone`, so it could not name the cards
    in hand even if it did; and the permission covers cards drawn after the
    source arrived, which no pool resolved once could reach.

    It permits and never compels, so it cannot make a spell castable that some
    other rule forbids: 101.2 still gives a "can't" the last word, and
    `player_cant_cast_spells` is checked before any of this.
    """
    return _player_static(state, pid, "cast_as_though_flash")


def player_reveals_library_top(state: GameState, pid: int) -> bool:
    """ "Play with the top card of your library revealed." Vampire Nocturnus.

    Purely a *visibility* change -- it grants no permission and moves no card,
    which is what separates it from `play_lands_from_library_top`. The whole of
    it is that the client is allowed to draw the card, so this is read by
    `serialize` and by nothing in the rules.

    It matters anyway, and not only as flavour: Vampire Nocturnus is a card you
    cannot pilot without it. Whether your team has flying is a fact you are
    supposed to know before declaring attackers, and the condition that decides
    it is otherwise invisible.
    """
    return _player_static(state, pid, "reveal_library_top")


def player_looks_at_library_top(state: GameState, pid: int) -> bool:
    """ "You may look at the top card of your library any time." Verge Rangers.

    The *private* half of the pair. `reveal_library_top` above is "play with the
    top card revealed": the card becomes public and `serialize` sends it to
    every seat, because an opponent who cannot see a revealed card is playing
    against information they are entitled to. This one grants no such
    entitlement -- Verge Rangers never shows the card to anybody but its
    controller -- so `serialize` sends it to that player's seat and no other.
    Substituting the public static would have handed the opponent a card the
    printed card does not show them, which is a *different* card.

    It is not the `look_at_top` op either. That op looks once, at resolution,
    and is spent; this is a continuous permission, true again the next time you
    care and false the instant its source leaves. "Any time" is not a moment for
    a trigger to fire at.

    Like its public twin it changes no rule: it grants no permission to play or
    move the card, and it is read by `serialize` and by nothing else.
    """
    return _player_static(state, pid, "look_at_library_top")


def player_plays_lands_from_graveyard(state: GameState, pid: int) -> bool:
    """Whether this player may play lands from their graveyard.

    Ramunap Excavator, Crucible of Worlds, Ancient Greenwarden. Widens *where* a
    land may be played from; the one-land-per-turn rule is untouched and still
    enforced by `lands_played`.
    """
    return _player_static(state, pid, "play_lands_from_graveyard")


def graveyard_cast_permissions(
    state: GameState, pid: int
) -> list[tuple[GameObject, Mapping[str, Any]]]:
    """ "…you may cast an artifact spell from your graveyard." Edgar.

    The permissions currently reaching ``pid``, each with the permanent granting
    it -- the source matters because the rate limit is counted per granting
    permanent, so two Edgars are two casts a turn the way two Welcoming Vampires
    each draw.

    A list rather than a bool, which is the whole difference from
    `player_plays_lands_from_graveyard`: that one answers a yes/no the land drop
    asks, while this has to say *which* spells and *how many times*.
    """
    out = [
        (obj, static)
        for obj, static in _active_player_statics(state, "cast_from_graveyard")
        if _reaches_player(obj, static, pid)
    ]
    # The floating, turn-scoped half. A permission granted by a resolving
    # effect rather than by a permanent still on the battlefield -- Urabrask's
    # third chapter, which exiles the Saga in the same breath -- so it is read
    # off the table and joins the same list. Everything downstream (the
    # `affects_spells` filter, `max_per_turn`, `grants_flashback`, and the
    # `cast_from_graveyard` mark that exiles the spell as it resolves) is then
    # the code that already existed.
    #
    # The granting object is looked up even though it has left the battlefield:
    # a `GameObject` outlives its zone, the rate limit is counted against its
    # oid, and `graveyard_cast_allows` resolves a chosen type against it.
    for grant in state.graveyard_cast_grants:
        if grant.turn != state.turn or grant.player != pid:
            continue
        source = state.objects.get(grant.source)
        if source is not None:
            out.append((source, grant.static))
    return out


def graveyard_cast_allows(
    state: GameState, source_obj: GameObject, static: Mapping[str, Any], card: CardDef
) -> bool:
    """Does this permission let *this* card out of the graveyard?

    The same `affects_spells` filter `spell_cost_reduction` matches a card in
    hand with, and matched the same way -- `_matches_printed`, because a card in
    a graveyard has a printed face and an owner and no board state.
    """
    filt = static.get("affects_spells")
    if not filt:
        # The loader requires one. Defaulting to `{}` would make an empty filter
        # free the whole graveyard, so a compile bug would hand over everything
        # rather than nothing.
        return False
    resolved = resolve_chosen_colors(resolve_chosen_subtypes(filt, source_obj), source_obj)
    return _matches_printed(card, resolved)


def graveyard_cast_arrival_ok(state: GameState, static: Mapping[str, Any], obj: GameObject) -> bool:
    """ "…put there **from anywhere other than the battlefield this turn**".

    Banon, the Returners' Leader. Asked of the *object* rather than the printed
    card, because when a card reached a graveyard and from where are facts about
    this copy of it and not about the card -- which is why they could not go in
    `affects_spells` beside the type filter.

    Absent from the static, every card in the yard qualifies, which is Edgar.
    """
    arrival = static.get("arrived_this_turn_from")
    if arrival is None:
        return True
    if obj.graveyard_turn != state.turn:
        return False
    allowed = [str(z) for z in arrival]
    if allowed == ["any"]:
        return True
    forbidden = [z[1:] for z in allowed if z.startswith("!")]
    if forbidden:
        # "from anywhere **other than** the battlefield" -- a complement, and
        # written as one because the printed line is: listing the four zones a
        # card could otherwise have come from would silently miss the fifth.
        return obj.graveyard_from not in forbidden
    return obj.graveyard_from in allowed


def library_top_cast_permission(state: GameState, pid: int):
    """The permanent letting this player cast off the top of their library.

    Bolas's Citadel. The casting twin of
    `player_plays_lands_from_library_top`, which is documented as lands only and
    so grants nothing for a nonland spell -- and unlike it this returns the
    granting permanent rather than a bool, because the price rides on the same
    static and `Game._cast` has to read it.
    """
    for obj, static in _active_player_statics(state, "cast_from_library_top"):
        if _reaches_player(obj, static, pid):
            return obj, static
    return None


def player_plays_lands_from_library_top(state: GameState, pid: int) -> bool:
    """Whether this player may play the top card of their library, if it is a land.

    Oracle of Mul Daya, Courser of Kruphix. Only the *top* card, which is what
    the cards say and also the only part of a hidden zone anybody is allowed to
    know about.
    """
    return _player_static(state, pid, "play_lands_from_library_top")


def player_extra_land_drops(state: GameState, pid: int) -> int:
    """Sum of every *active* ``extra_land_drops`` static affecting this player.

    A switched-off one contributes nothing rather than its amount -- the one
    place among the player-wide statics where the gate changes a number instead
    of a permission.
    """
    return sum(
        _static_value(state, static.get("amount"), obj)
        for obj, static in _active_player_statics(state, "extra_land_drops")
        if _reaches_player(obj, static, pid)
    )


def token_creation_replacements(state: GameState, pid: int) -> list[Mapping[str, Any]]:
    """The active ``replace_token_creation`` statics reaching ``pid``, in battlefield order.

    Academy Manufactor, Divine Visitation, and the doublers -- Doubling Season,
    Parallel Lives, Bard, King of Dale. Read by
    `primitives._token_creation_plan` and by nothing else, the way
    `untap_during_each_untap_step` is read by the untap step alone: a token that
    is about to be created has no object for a characteristic to attach to, so
    this cannot be a layer -- it is a fact about what *will* be made.

    ``pid`` is the player the token will be created *under*. `affects_player` is
    optional here and defaults to ``"you"`` -- every card before Primal Vigor
    said "you" and was written without the key -- so the default is the
    source's controller, and ``"any"`` is Primal Vigor's "if one or more tokens
    would be created", which names nobody.
    Order is `state.battlefield` order, which is arrival order: rule 616.1 gives
    the choice of which replacement to apply first to the affected player, and
    this engine does not ask -- see `_token_creation_plan`, which owns that
    divergence and the once-per-event rule with it.
    """
    return [
        static
        for obj, static in _active_player_statics(state, "replace_token_creation")
        if _reaches_player(obj, static, pid)
    ]


def counter_placement_replacements(
    state: GameState, oid: int, kind: str
) -> list[Mapping[str, Any]]:
    """The active ``replace_counters`` statics that apply to this placement.

    High Score, Hardened Scales, Doubling Season, Corpsejack Menace. Read by
    `primitives.add_counters` and by nothing else, the way
    `token_creation_replacements` is read by `create_token` alone: a
    replacement is a fact about what *will* happen, not a characteristic of
    anything, so it cannot be a layer.

    Filtered here rather than in the caller so both halves of "would be put on
    **a creature you control**" and "**+1/+1** counters" are asked in one place.
    ``_matches`` refuses anything not on the battlefield, which is what keeps
    these statics away from the suspend counters on a card in exile.

    Order is `state.battlefield` order, which is arrival order. 616.1 gives the
    choice to the affected player and this engine does not ask -- see
    `primitives._replaced_counter_amount`, which owns that divergence together
    with 614.5.
    """
    obj = state.objects.get(oid)
    if obj is None:
        return []
    out: list[Mapping[str, Any]] = []
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "replace_counters":
            continue
        wanted = static.get("counter")
        if wanted is not None and str(wanted) != kind:
            continue
        if not _matches(state, obj, source_obj, static.get("affects")):
            continue
        out.append(static)
    return out


def damage_multiplier(
    state: GameState,
    source_oid: int | None,
    target_oid: int | None,
    *,
    is_combat: bool,
) -> int:
    """What this damage is multiplied by, after every `replace_damage` applies.

    Inquisitor's Flail, Furnace of Rath, Gratuitous Violence, Fiery
    Emancipation. Read by `primitives.damage_permanent` and
    `primitives.damage_player` and by nothing else, the way
    `counter_placement_replacements` is read by `add_counters` alone.

    ``target_oid`` is ``None`` when the damage is being dealt to a **player**,
    and a static carrying an `affects` filter never applies then: a player is
    not a permanent, and "…to equipped creature" is a sentence about one. A
    static with no `affects` reaches both, which is Furnace of Rath's "to a
    permanent or player" and the Flail's first line.

    Returned as a product rather than applied here, because the two call sites
    have different things to do with the number and only one of them exists at
    a time. 614.5 is kept by the shape: each static is consulted once, and
    multiplication commutes, so 616.1's unasked ordering cannot show between
    two of these.
    """
    multiplier = 1
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "replace_damage":
            continue
        if static.get("combat_only") and not is_combat:
            continue
        dealer = static.get("damage_source")
        if dealer is not None:
            obj = state.objects.get(source_oid) if source_oid is not None else None
            if obj is None or not _matches(state, obj, source_obj, dealer):
                continue
        recipient = static.get("affects")
        if recipient is not None:
            obj = state.objects.get(target_oid) if target_oid is not None else None
            if obj is None or not _matches(state, obj, source_obj, recipient):
                continue
        multiplier *= max(1, int(static.get("damage_multiplier") or 1))
    return multiplier


def printed_token_matches(state: GameState, def_id: str, selector: Mapping[str, Any]) -> bool:
    """Does the token about to be created match this filter?

    A token definition is nothing *but* a printed face -- there is no object yet,
    no controller on it and no board state -- so this is `_matches_printed` and
    only `_matches_printed`, shared with the counting filters rather than
    rewritten beside `create_token`, where the two spellings of "Artifact
    subtype Treasure" would drift.

    An empty selector matches everything, which is the one place the static
    filter language differs here on purpose: `_matches` refuses `None` because
    "every permanent gets +1/+1" is not a card, and "if you would create a
    token" with no filter at all is a shape a card really does print.
    """
    return _matches_printed(state.registry.get(def_id), selector)


def commander_subtypes(state: GameState, pid: int) -> frozenset[str]:
    """Every creature type this player's commanders currently have.

    The union across their commanders, so a partner pair contributes both
    halves' types -- "shares a creature type with your commander" is satisfied
    by either one.

    Read through `chars` where the commander is on the battlefield and off the
    printed card otherwise: an animated or type-changed general really does
    share its new type, and a commander sitting in the command zone -- where it
    is for most of the game -- has only what is printed on it.

    Lives here rather than in `selectors` because both halves of the filter
    language ask it: `selectors.matches` for effects, and
    `triggers.matches_card_filter` for trigger filters, which is the one Path of
    Ancestry actually reaches.
    """
    out: set[str] = set()
    for oid in state.commanders_of(pid):
        obj = state.objects.get(oid)
        if obj is None:
            continue
        if obj.zone is Zone.BATTLEFIELD:
            out |= set(chars(state, oid).subtypes)
        else:
            out |= set(state.card_of(obj).subtypes)
    return frozenset(out)
