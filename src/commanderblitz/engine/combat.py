"""Combat: declaring attackers and blockers, and dealing combat damage.

Declaration is **incremental**.  The attacking player issues repeated
``ADD_ATTACKER`` actions and then ``FINISH_DECLARATION``; each defending player
does the same for blockers.  Every increment is validated on its own, so the RL
action mask is always exact and never has to enumerate 2**n attack sets.  The
HTTP layer accepts a whole set and loops the increments server-side, so the human
UX is still "select all, confirm".
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .carddef import Cost
from .characteristics import block_restrictions, chars, matches_static, protected_from
from .costs import can_pay
from .effects.context import EffectContext, ask_objects
from .enums import LANDWALK_SUBTYPE, Keyword
from .events import EventType
from .mana import OTHER_PAYMENT, ManaCost
from .player_statics import (
    any_defender_attack_prohibition,
    attack_alone_forbidden,
    attack_compelled,
    attack_defender_forbidden,
    attack_forbidden,
    attack_tax,
    block_alone_forbidden,
    block_forbidden,
    block_tax,
)
from .primitives import become_monarch, damage_permanent, damage_player, tap_permanent
from .structs import CombatState
from .temp_effects import clear_attack_restrictions
from .triggers import fire

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


@dataclass(frozen=True)
class DamageAssignment:
    """One source dealing one amount to one recipient, collected before applying."""

    source: int
    to_player: int | None = None
    to_object: int | None = None
    amount: int = 0


# ----------------------------------------------------------------------
# attackers
# ----------------------------------------------------------------------


def start_combat(state: GameState) -> None:
    # `combat_number` identifies the phase, and this is the only place one
    # begins -- so "at end of combat" can name *this* combat rather than the
    # next `END_OF_COMBAT` step to come round. See `GameState.combat_number`.
    state.combat_number += 1
    # ...and the per-turn count, which is a different question: "the first
    # combat phase of the turn" (Genji Glove). See `TurnLedger.combats` for why
    # the monotonic one cannot answer it.
    state.turn_ledger.combats += 1
    # Pack tactics reads "this combat", so the last combat's attackers stop
    # counting the moment the next one begins.
    state.turn_ledger.attack_power_this_combat.clear()
    state.combat = CombatState(declaring_player=state.active_player)


def can_attack(state: GameState, oid: int) -> bool:
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield or obj.tapped:
        return False
    if obj.controller != state.active_player:
        return False
    c = chars(state, oid)
    if "Creature" not in c.types:
        return False
    if Keyword.DEFENDER.value in c.keywords:
        return False
    if obj.summoning_sick(state.turn) and Keyword.HASTE.value not in c.keywords:
        return False
    if attack_forbidden(state, oid):
        return False
    # Detain: "can't attack or block until your next turn". Read here rather
    # than through a static, because it is written onto the one permanent and
    # outlives the turn that wrote it.
    if obj.detained_by is not None:
        return False
    # "They can't attack you this combat." A creature with nobody left to attack
    # cannot attack, and this is the place that has to say so rather than
    # `legality`: `attack_required` is a requirement AND `can_attack`, so a
    # compelled creature whose every defender had become forbidden would have
    # "Done attacking" withheld with no ADD_ATTACKER left to offer -- a
    # declaration with no legal action in it at all.
    #
    # Guarded on the list being non-empty, which it is in every game that does
    # not play one of these cards, because this is the hot path of the attack
    # mask. Goad is deliberately **not** part of that guard: its clause in
    # `attack_target_forbidden` only fires while some other defender is
    # available, so a goad can never empty both lists and a goaded creature is
    # never made unable to attack by the goad itself.
    # `cant_attack_you` is the second thing that can empty both lists -- an
    # Inkling in a two-player game whose only opponent has a Combat Calligrapher
    # has nowhere legal to swing -- so it joins the cheap guard rather than
    # relying on the one already there.
    if (state.attack_restrictions or any_defender_attack_prohibition(state)) and not (
        legal_defenders(state, oid) or legal_permanent_defenders(state, oid)
    ):
        return False
    combat = state.combat
    return combat is None or oid not in combat.attackers


def attack_tax_cost(state: GameState, oid: int, defender: int, *, planeswalker: bool = False):
    """The `Cost` to declare ``oid`` against ``defender``, or ``None`` if free.

    Propaganda. Built here rather than in `characteristics`, which cannot import
    `costs` -- `costs` imports it. The mana string comes from the statics; this
    turns it into the same `Cost` every other payment goes through, so the tax
    is solved, restricted-mana-checked and charged by exactly one code path.

    ``planeswalker`` prices an attack on one of ``defender``'s planeswalkers,
    which only an ``or_planeswalkers`` tax reaches (Archangel of Tithes).
    """

    return _tax_cost(attack_tax(state, oid, defender, planeswalker=planeswalker))


def block_tax_cost(state: GameState, oid: int):
    """The `Cost` to declare ``oid`` as a blocker, or ``None`` if free.

    Archangel of Tithes' "creatures can't block unless their controller pays
    {1} for each of those creatures" -- `attack_tax_cost` at declare-blockers.
    """

    return _tax_cost(block_tax(state, oid))


def _tax_cost(mana: str):
    return Cost(mana=ManaCost.parse(mana)) if mana else None


def attack_tax_payable(
    state: GameState, oid: int, defender: int, cost=None, *, planeswalker: bool = False
) -> bool:
    """Can this attack be paid for? An unpayable tax is a prohibition (508.1g).

    "Creatures can't attack you **unless** their controller pays" -- so a
    declaration nobody can fund is simply not offered, rather than offered and
    then rewound. That is the 601.2 spirit `op_may` already follows for an
    optional cost, and it keeps the declare-attackers action list honest: every
    ADD_ATTACKER on it is one the player can actually make.
    """
    # `cost` is passed in by `legality`, which is the hot path of the attack
    # mask and has already built it once for the label.
    if cost is None:
        cost = attack_tax_cost(state, oid, defender, planeswalker=planeswalker)
    return combat_tax_payable(state, oid, cost)


def combat_tax_payable(state: GameState, oid: int, cost) -> bool:
    """Can ``oid``'s controller fund this attack or block tax right now?

    Shared by both declarations, so an attack tax and a block tax are judged
    affordable by the same `can_pay` -- 508.1g and 509.1e are one rule twice.
    """

    if cost is None:
        return True
    obj = state.objects.get(oid)
    if obj is None:
        return False
    # `source_oid=None`: the creature is not being tapped or sacrificed for
    # this, it is only the thing being priced -- passing it would let a `tap`
    # in the cost tap the attacker.
    return can_pay(state, obj.controller, cost, None, purpose=OTHER_PAYMENT)


def block_taxed(state: GameState, oid: int) -> bool:
    """Does declaring this creature as a blocker cost anything?

    509.1c: "If a creature can't block unless a player pays a cost, that player
    is not required to pay that cost, even if blocking with that creature would
    increase the number of requirements being obeyed." So a provoked or lured
    creature under Archangel of Tithes owes nothing -- it may block whatever it
    likes, or nothing at all, and "Done blocking" is not withheld for it.
    """
    return bool(block_tax_cost(state, oid))


def attack_required(state: GameState, oid: int) -> bool:
    """Must this creature attack right now, and can it?

    "…if able" is the whole of the second half: a requirement never makes an
    illegal attack legal, and a tapped or summoning-sick creature simply does
    not have to.  So this is the requirement AND `can_attack`, never one alone.
    """
    obj = state.objects.get(oid)
    if obj is None:
        return False
    # Three sources, one enforcement point. The `must_attack` op writes a
    # one-shot flag that `discharge_attack_requirements` spends; a printed
    # "attacks each combat if able" is a static, read live and never spent; and
    # a goad is a mark on the creature, also read live and also never spent --
    # `discharge_attack_requirements` touches `must_attack` and nothing else, so
    # a goaded creature is compelled again by the *next* combat and the one
    # after, until its goader untaps. That is the whole reason goad could not be
    # `must_attack` with a third duration.
    #
    # All three are "…if able", so all three go through `can_attack` below.
    # A fourth: Gideon Jura's mark on a planeswalker, read live for its turn
    # (`required_attack_walkers`), which also catches creatures that arrived
    # after the ability resolved.
    if (
        not attack_compelled(state, oid)
        and not obj.goaded_by
        and not required_attack_walkers(state, oid)
    ):
        if obj.must_attack is None:
            return False
        if obj.must_attack == "this_turn" and obj.must_attack_turn != state.turn:
            return False
    return can_attack(state, oid)


def unmet_attack_requirements(state: GameState) -> list[int]:
    """Creatures that must attack and are not, for the active player."""
    combat = state.combat
    attacking = set(combat.attackers) if combat else set()
    return [
        oid
        for oid in state.battlefield
        if oid not in attacking
        and state.objects[oid].controller == state.active_player
        and attack_required(state, oid)
    ]


def discharge_attack_requirements(state: GameState) -> None:
    """Spend the active player's requirements once attackers are locked in.

    A ``next_combat`` obligation is one-shot and expires here whether or not it
    was met -- the creature may have been tapped, and "if able" means it owed
    nothing.  Leaving it set would compel the following combat too.
    """
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None or obj.must_attack is None:
            continue
        if obj.controller != state.active_player:
            continue
        obj.must_attack = None


def unmet_block_requirements(state: GameState, defender: int) -> list[int]:
    """Creatures of ``defender`` that must block something and are not.

    The mirror of :func:`unmet_attack_requirements`, and "…if able" is the same
    whole second half: a requirement never makes an illegal block legal, so a
    creature that was tapped, or that cannot block the attacker at all, owes
    nothing. That is why every candidate is run through `can_block` -- provoke
    untaps its victim precisely because a tapped creature would otherwise be
    excused.

    A creature blocking *something else* has still not met this requirement:
    the obligation names one attacker, and rule 509.1c requires the declaration
    to satisfy the maximum number of requirements it can.
    """
    combat = state.combat
    if combat is None:
        return []
    unmet: list[int] = []
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None or obj.must_block is None or obj.controller != defender:
            continue
        attacker = obj.must_block
        if attacker not in combat.attackers or attacker in combat.removed:
            continue
        if combat.blockers.get(oid) == attacker:
            continue
        if not can_block(state, oid, attacker, defender, ignore_existing=True):
            continue
        # 509.1c: nobody is required to pay a block tax to obey a requirement.
        if block_taxed(state, oid):
            continue
        unmet.append(oid)
    return unmet


def discharge_block_requirements(state: GameState) -> None:
    """Spend every block requirement once blockers are locked in.

    Unconditionally, whether or not it was met -- "if able" means a creature
    that could not block owed nothing, and leaving the flag set would compel
    the *next* combat, which no printed provoke says.
    """
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is not None:
            obj.must_block = None


def legal_attackers(state: GameState) -> list[int]:
    return [oid for oid in state.battlefield if can_attack(state, oid)]


def attack_target_forbidden(
    state: GameState, oid: int, defender: int, *, permanent: int | None = None
) -> bool:
    """May this creature **not** attack this defender?

    The per-attacker, per-defender half of attack legality, which the engine did
    not have: `attack_forbidden` asks whether a creature may attack *at all*, and
    every other prohibition (tapped, `defender`, detained) is the same
    all-or-nothing shape.  "That player can't attack you" narrows the choice
    instead, and leaves the creature free to swing at anybody else.

    One predicate rather than a filter inside each of the three callers, because
    `legal_defenders`, `legal_permanent_defenders` and `add_attacker` have to
    agree exactly -- an action legality offers and `add_attacker` then refuses is
    a game that cannot continue.

    ``permanent`` is the attack's *non-seat* target kind (506.2) -- a
    planeswalker or a battle -- and it is deliberately exempt from
    `attack_restrictions`. "Creatures can't attack you" restricts attacking the
    **player**; attacking a planeswalker they control is not that, which is why
    a Ghostly Prison taxes nothing when the attack goes at a planeswalker
    instead. The argument is taken rather than assumed so a future restriction
    that *does* reach planeswalkers -- goad's "attacks a player other than you
    if able", where attacking your planeswalker does not discharge the
    requirement -- can say so here without touching the three callers again.

    A **battle** is passed in the same argument and is read the same way, and
    that is the whole of what battles cost this predicate: 506.2 makes the two
    one kind of declaration, and every sentence above that distinguishes a seat
    from a permanent distinguishes a seat from a battle for the same reason.

    That future arrived, and it is the second clause below. **Goad reaches
    planeswalkers** where an attack restriction does not, and the two answers are
    opposite for the same reason: "creatures can't attack *you*" is a sentence
    about being attacked, and attacking somebody's planeswalker is not attacking
    them (506.2); "attacks a player *other than you* if able" is a sentence about
    who the attack is aimed at, and swinging at the goader's planeswalker aims it
    at the goader just as squarely. Reading goad the way Ghostly Prison is read
    would leave every goad in a game with a planeswalker on the table free to be
    dodged, and the log would say the requirement had been met.

    An `AttackRestriction` may say so too, and the third divergence is decided
    the same way as the first two -- by what the printed sentence names.
    `AttackRestriction.planeswalkers` is `False` on every line that names a seat
    ("you can't attack that player this turn") and `True` for the one that names
    **no defender at all**: "creatures can't attack this combat"
    (Overencumbered). There is no seat in that sentence to read narrowly, so it
    forbids all three of 506.2's attack targets, and a restriction that exempted
    walkers would print a card whose whole text is "creatures can't attack" and
    then let creatures attack.
    """
    obj = state.objects.get(oid)
    if _attack_prohibited(state, oid, defender, permanent=permanent):
        return True
    # "During target opponent's next turn, creatures that player controls
    # attack Gideon Jura if able" -- a requirement naming one attack target.
    # Asked after the prohibitions, which a requirement never overrides
    # (508.1d: "if able"), and before goad, with which it is weighed below.
    if obj is not None and (required := required_attack_walkers(state, oid)):
        return _misses_attack_requirements(state, oid, defender, permanent, required)
    # Goad's second half (701.38a): "…and attacks a player other than you if
    # able". `defender` is the defending *player* for both attack kinds -- a
    # planeswalker's or battle's controller is the defending player (506.2) and
    # `legal_permanent_defenders` passes it -- so one membership test covers
    # the walker as well as the seat, which is what "goad reaches planeswalkers"
    # means in code.
    #
    # "…if able" is the guard, and it is the difference between a restriction and
    # a rule that can make a declaration impossible: with the goader the only
    # thing left to attack, the creature attacks the goader.
    if obj is not None and obj.goaded_by and defender in obj.goaded_by:
        return _has_non_goader_defender(state, oid, obj.goaded_by)
    return False


def _attack_prohibited(
    state: GameState, oid: int, defender: int, *, permanent: int | None = None
) -> bool:
    """The *prohibitions* half of `attack_target_forbidden` -- no requirements.

    Split out so the requirement checks can ask "could this creature attack
    there at all?" without re-entering the requirement logic that is asking.
    """
    obj = state.objects.get(oid)
    if state.attack_restrictions and obj is not None:
        for restriction in state.attack_restrictions:
            if restriction.attacker != obj.controller or restriction.defender != defender:
                continue
            if restriction.walker_subtypes:
                # "…can't attack Jaces you control": the seat and every other
                # permanent stay attackable, and only a walker that *is* one of
                # the named subtypes right now is closed.
                if permanent is not None:
                    walker = chars(state, permanent)
                    if "Planeswalker" in walker.types and any(
                        t in walker.subtypes for t in restriction.walker_subtypes
                    ):
                        return True
                continue
            if permanent is None or restriction.planeswalkers:
                return True
    # Combat Calligrapher: "Inklings can't attack you or planeswalkers you
    # control." The same seam read off a *static* instead of the table, so the
    # prohibition is filtered on the attacking creature and lives exactly as
    # long as the permanent printing it. Deliberately **not** under the
    # `permanent is None` guard above: this sentence names the walkers, where
    # `attack_restrictions`' sentence ("that player can't attack you") does not,
    # and reading either one the other's way would be a different card.
    #
    # A **battle** inherits this unchanged, which over-reads it by one word:
    # Combat Calligrapher says "you or planeswalkers you control" and this stops
    # the Inkling attacking that seat's battle too. Left as it is rather than
    # split, because the split would be a per-type prohibition list built for a
    # card that does not exist, and the over-reading is in the safe direction --
    # a battle that cannot be attacked is inert, where one that could be
    # attacked around a printed prohibition is a rules error. A `player_only`
    # wall ("can't attack you", Queen Mother Ramonda) reaches neither.
    return attack_defender_forbidden(state, oid, defender, permanent=permanent)


def required_attack_walkers(state: GameState, oid: int) -> set[int]:
    """The planeswalkers this creature must attack if able, right now.

    Gideon Jura: "During target opponent's next turn, creatures that player
    controls attack Gideon Jura if able." Read off the marks on the walkers
    (`GameObject.must_be_attacked_by`), so a creature that arrives during that
    turn is compelled too -- the sentence is about the *player's* creatures, not
    a list taken when it resolved.

    A walker is required only while the mark is armed for this very turn, the
    creature's controller is the active player, it is still on the battlefield
    as a planeswalker of somebody else's, and nothing *prohibits* this creature
    attacking it -- 508.1d's "if able": a requirement never makes an illegal
    attack legal. Empty in every game that plays none of these cards, after one
    walk that reads a normally-empty dict.
    """
    obj = state.objects.get(oid)
    if obj is None or obj.controller != state.active_player:
        return set()
    out: set[int] = set()
    for pw in state.battlefield:
        walker = state.objects.get(pw)
        if walker is None or not walker.must_be_attacked_by:
            continue
        if walker.must_be_attacked_by.get(obj.controller) != state.turn:
            continue
        if walker.controller == obj.controller or not state.is_alive(walker.controller):
            continue
        if "Planeswalker" not in chars(state, pw).types:
            continue
        if _attack_prohibited(state, oid, walker.controller, permanent=pw):
            continue
        out.add(pw)
    return out


def _misses_attack_requirements(
    state: GameState,
    oid: int,
    defender: int,
    permanent: int | None,
    required: set[int],
) -> bool:
    """Is attacking here worse than the best declaration 508.1d allows?

    Rule 508.1d: the attack must obey the **maximum number of requirements**
    possible without breaking a restriction. For a creature under a walker
    requirement alone that is simple -- attack one of the required walkers.
    Beside goad (701.38a) it is a count: attacking the walker obeys the walker
    requirement, attacking something no goader controls obeys goad's, and a
    walker no goader controls obeys both. Every candidate target is scored and
    anything below the best is refused; ties are all allowed, so the player
    still chooses between equally obedient attacks.
    """
    obj = state.objects.get(oid)
    goaders = obj.goaded_by if obj is not None else set()

    def score(seat: int, pw: int | None) -> int:
        points = 1 if pw is not None and pw in required else 0
        if goaders and seat not in goaders:
            points += 1
        return points

    best = 0
    seats = [pid for pid in state.alive() if pid != state.active_player]
    for seat in seats:
        if not _attack_prohibited(state, oid, seat):
            best = max(best, score(seat, None))
    for pw in state.battlefield:
        pw_obj = state.objects.get(pw)
        if pw_obj is None or pw_obj.controller not in seats:
            continue
        if not any(t in chars(state, pw).types for t in ATTACKABLE_TYPES):
            continue
        if not _attack_prohibited(state, oid, pw_obj.controller, permanent=pw):
            best = max(best, score(pw_obj.controller, pw))
    return score(defender, permanent) < best


def _has_non_goader_defender(state: GameState, oid: int, goaders: set[int]) -> bool:
    """Is there anything this creature could attack that no goader controls?

    Goad's "if able", asked once per goaded pair. It has to consider **both**
    attack kinds -- a planeswalker or battle controlled by a third player is
    somewhere else to swing, and a goaded creature offered only the goader's
    seat because the engine forgot about them would be forced into an attack the
    rules do not require.
    (Rule 701.38b: the requirement is discharged by attacking any other player,
    or by attacking a planeswalker or battle any other player controls -- the
    defending player is that permanent's controller either way, which is the
    same reading the clause in `attack_target_forbidden` takes.)

    It re-enters `attack_target_forbidden`, and that is not a loop: every
    candidate here is already filtered to a defender **no goader controls**, so
    the goad clause there cannot fire on it and cannot call back. Two levels
    deep, always, whatever the number of goaders. Asked the other way round --
    "is any defender legal" through `legal_defenders` -- it would be a plain
    infinite recursion, which is the trap this shape exists to avoid.

    A goader who has left the game is skipped by `alive()` and by the
    battlefield's controller check, so the last opponent standing being the only
    remaining goader still leaves them attackable.
    """
    others = [
        pid
        for pid in state.alive()
        if pid != state.active_player and pid not in goaders
    ]
    for pid in others:
        if not attack_target_forbidden(state, oid, pid):
            return True
    open_seats = set(others)
    for pw in state.battlefield:
        pw_obj = state.objects.get(pw)
        if pw_obj is None or pw_obj.controller not in open_seats:
            continue
        if not any(t in chars(state, pw).types for t in ATTACKABLE_TYPES):
            continue
        if not attack_target_forbidden(
            state, oid, pw_obj.controller, permanent=pw
        ):
            return True
    return False


def legal_defenders(state: GameState, oid: int | None = None) -> list[int]:
    """Players this creature may be declared as attacking.

    ``oid`` is the attacking creature, and ``None`` means "the players who could
    be attacked by *somebody*" -- the unfiltered set, which is what the
    declare-attackers step wants when it is only asking whether combat has
    anywhere to go.
    """
    defenders = [pid for pid in state.alive() if pid != state.active_player]
    if oid is None:
        return defenders
    return [pid for pid in defenders if not attack_target_forbidden(state, oid, pid)]


#: The permanent types 506.2 lets a creature be declared as attacking, beside a
#: player. Two of the three attack targets, and the only thing that separates
#: them downstream is which counter the damage comes off -- loyalty (306.8) or
#: defense (310.6).
ATTACKABLE_TYPES = ("Planeswalker", "Battle")


def legal_permanent_defenders(state: GameState, oid: int | None = None) -> list[int]:
    """Permanents that may be attacked, in deterministic order (506.2).

    Every planeswalker **or battle** controlled by a player who could be
    attacked. Its controller is the defending player, which is why attacking
    one does not need its own notion of "who is being attacked" --
    `attackers[oid]` still answers that, and still truthfully.

    Read off the **unfiltered** player set: a player under an attack restriction
    is still a legal defender when the attack goes at their planeswalker, so the
    filtering is left entirely to `attack_target_forbidden`, which is told which
    kind of attack it is being asked about.

    **Battles are offered to the attacking player's opponents**, exactly as
    planeswalkers are, and that is the one place the engine's battle differs
    from a printed Siege. 506.2b makes the *protector* the defending player, and
    a Siege's protector is an opponent of its controller -- so in a real game
    you attack the battle **you** control. Protectors are not modelled (see
    `docs/rules-coverage.md`), and rather than invent a defending player this
    follows the planeswalker precedent: a battle is attackable by the people who
    could attack its controller. A battle with no protector is therefore a
    permanent your opponents can shoot down, not one you race -- narrower than
    the printed card, and visibly so, rather than silently mis-seated.
    """

    defenders = set(legal_defenders(state))
    return [
        pw
        for pw in state.battlefield
        if (obj := state.objects.get(pw)) is not None
        and obj.controller in defenders
        and any(t in chars(state, pw).types for t in ATTACKABLE_TYPES)
        and (oid is None or not attack_target_forbidden(state, oid, obj.controller, permanent=pw))
    ]


def add_attacker(
    state: GameState, oid: int, defender: int, *, permanent: int | None = None
) -> bool:
    combat = state.combat
    if combat is None or not can_attack(state, oid):
        return False
    # Each of the two attack kinds is validated against exactly the list
    # legality offered for it, and `oid` is passed to both -- an attack legality
    # offers and this then refuses would strand the declaration with no way out.
    if permanent is None:
        if defender not in legal_defenders(state, oid):
            return False
    else:
        if permanent not in legal_permanent_defenders(state, oid):
            return False
        obj = state.objects.get(permanent)
        if obj is None or obj.controller != defender:
            # The permanent and the player have to agree, or `attackers[oid]`
            # -- which everything else reads as "the defending player" -- would
            # name someone this creature is not attacking.
            return False
        combat.attacking_permanent[oid] = permanent
    combat.attackers[oid] = defender
    return True


def remove_attacker(state: GameState, oid: int) -> None:
    if state.combat is not None:
        state.combat.attackers.pop(oid, None)
        state.combat.attacking_permanent.pop(oid, None)


def _declared_attackers(state: GameState, player: int) -> list[int]:
    """The creatures this player currently has declared as attacking.

    Filtered to permanents still on the battlefield and not removed from combat
    (506.4): a creature that has left is no longer an attacking creature, so it
    cannot be the "other creature" a can't-attack-alone restriction is counting.
    """
    combat = state.combat
    if combat is None:
        return []
    out = []
    for oid in combat.attackers:
        obj = state.objects.get(oid)
        if obj is None or not obj.on_battlefield or oid in combat.removed:
            continue
        if obj.controller == player:
            out.append(oid)
    return out


def attacks_valid(state: GameState, player: int) -> bool:
    """Check attack restrictions that only make sense on the *complete* declaration.

    The counterpart of `blocks_valid`, and the reason it did not exist until
    now: every other attack prohibition -- tapped, `defender`, `cant_attack`,
    detained, an unpayable tax -- is a fact about one creature, answered by
    `can_attack` before the attack is ever offered. "This creature can't attack
    alone" (508.1c) is a fact about the *declaration*: the same creature in the
    same position is legal beside a second attacker and illegal by itself, so
    there is nothing to refuse at the moment it is picked.

    Withheld "Done attacking" is how `legality` enforces it, exactly as it does
    for menace on the other side. A player part-way through a declaration has
    not broken a rule -- they have not finished.
    """
    attackers = _declared_attackers(state, player)
    if len(attackers) > 1:
        return True
    return not any(attack_alone_forbidden(state, oid) for oid in attackers)


def drop_illegal_attacks(state: GameState) -> list[int]:
    """Retract attacks that can never become a legal declaration.

    The mirror of `drop_illegal_blocks`, and it exists for the same reason: the
    rules declare attackers all at once and this engine does it one at a time,
    so a player can walk into a half-declaration the rules would never have
    produced -- a lone can't-attack-alone creature with nothing else able to
    attack beside it. `legality` withholds "Done attacking" while that is true,
    but hands it back when there is no `ADD_ATTACKER` left to offer, because a
    turn with no legal action in it is a game that cannot continue.

    Dropping is not a concession: "it doesn't attack" is precisely the
    declaration the rules would have produced, since the only alternative was
    illegal. Returns the attackers it retracted.
    """
    combat = state.combat
    if combat is None:
        return []
    controllers = []
    for oid in combat.attackers:
        obj = state.objects.get(oid)
        if obj is not None and obj.controller not in controllers:
            controllers.append(obj.controller)
    dropped: list[int] = []
    for player in controllers:
        if attacks_valid(state, player):
            continue
        for oid in _declared_attackers(state, player):
            if attack_alone_forbidden(state, oid):
                remove_attacker(state, oid)
                dropped.append(oid)
    return dropped


def finish_attackers(state: GameState) -> Generator[Any, list[int]]:
    """Lock in the attack: form bands, tap the attackers and fire their triggers.

    A generator because of the bands, and only because of them: 702.21b puts the
    declaration "as a player declares attackers", so it belongs here rather than
    anywhere later -- and the question is skipped entirely when nobody is
    attacking with banding, which is every combat in every deck that does not
    play a fifth-edition white creature.
    """
    combat = state.combat
    if combat is None:
        return
    # Before the bands, the taps and the triggers, and for the same reason
    # `finish_blockers` opens with `drop_illegal_blocks`: an incremental
    # declaration can reach a shape the rules would never have produced, and
    # what gets locked in has to be a declaration that was actually legal.
    # A creature dropped here never taps and never fires ATTACKS -- it did not
    # attack.
    drop_illegal_attacks(state)
    yield from _declare_bands(state)
    combat.attackers_declared = True
    discharge_attack_requirements(state)
    for oid in list(combat.attackers):
        c = chars(state, oid)
        if Keyword.VIGILANCE.value not in c.keywords:
            tap_permanent(state, oid)

    if combat.attackers:
        # `fire`, not `emit`: "whenever you attack" listens for this, and the
        # event had been recorded in the log with nothing subscribed to it. Once
        # per declaration whatever the number of attackers, which is the whole
        # difference from the per-creature ATTACKS fired just below.
        fire(
            state,
            EventType.ATTACKERS_DECLARED,
            player=state.active_player,
            attackers=sorted(combat.attackers),
        )
        # "Whenever one or more creatures attack one of your opponents or a
        # planeswalker they control" -- one per *defending player*, between the
        # declaration above and the per-creature ATTACKS below, because that is
        # exactly where it sits: coarser than one creature, finer than one
        # declaration.
        #
        # The subset, not `combat.attackers` entire. A pod attack split between
        # two seats is one declaration and two of these, and each may only speak
        # about the creatures aimed at its own defender -- otherwise Frontier
        # Warmonger hands menace to the creatures swinging at its controller.
        #
        # `combat.attackers[oid]` is the defending **player** even when the
        # attack is aimed at a planeswalker (`add_attacker` refuses a
        # planeswalker whose controller disagrees), so "or a planeswalker they
        # control" needs nothing here: attacking the walker is attacking its
        # controller, and one event covers both halves of the printed line.
        by_defender: dict[int, list[int]] = {}
        for oid in sorted(combat.attackers):
            by_defender.setdefault(combat.attackers[oid], []).append(oid)
        for defender in state.turn_order():
            if defender not in by_defender:
                continue
            fire(
                state,
                EventType.CREATURES_ATTACKED_PLAYER,
                player=state.active_player,
                defender=defender,
                attackers=by_defender[defender],
            )
        for oid in sorted(combat.attackers):
            obj = state.objects.get(oid)
            fire(
                state,
                EventType.ATTACKS,
                player=obj.controller if obj else state.active_player,
                source=oid,
                attacker=oid,
                defender=combat.attackers[oid],
                # The planeswalker or battle it attacks, when it attacks one
                # rather than a seat. `defender` is that permanent's controller
                # either way; the turn ledger needs to know the difference,
                # because only a creature that attacked a *player* attacked
                # that player (Angel of Destiny).
                attacked_permanent=combat.attacking_permanent.get(oid),
            )
    combat.pending_blockers = [
        pid for pid in state.turn_order() if pid in set(combat.attackers.values())
    ]


# ----------------------------------------------------------------------
# blockers
# ----------------------------------------------------------------------


def block_prohibited(state: GameState, oid: int) -> bool:
    """Is this creature under a one-shot "can't block", as opposed to a static?

    The counterpart of `characteristics.block_forbidden`, and split from it
    deliberately.  That one walks `_battlefield_statics` and answers "is there a
    permanent on the battlefield whose static says so"; this one reads
    `GameState.block_prohibitions`, which is where an effect with no permanent
    behind it has to live -- a resolving sorcery, or a trigger that named a
    creature as it resolved.  Folding the two together would mean either giving
    the characteristics layer table state to read or giving a one-shot effect a
    fake permanent to hang off, and both are worse than one extra call.

    An entry whose ``objects`` is ``None`` means *every* creature and is checked
    without looking at ``oid`` at all, which is the point: Aragorn's "creatures
    can't block this turn" is a continuous effect for the rest of the turn, so a
    creature that enters after it resolved is caught too.

    Guarded on the list being non-empty, which it is in every game that plays
    none of these cards, because this is on the hot path of the block mask.
    """
    if not state.block_prohibitions:
        return False
    return any(
        entry.objects is None or oid in entry.objects
        for entry in state.block_prohibitions
    )


def unblockable(state: GameState, oid: int, blocker_oid: int | None = None) -> bool:
    """Is this creature under a one-shot "can't be blocked", as opposed to a static?

    The exact mirror of :func:`block_prohibited` one function up, and the two are
    asked of opposite creatures: that one is asked of the would-be **blocker**,
    this one of the **attacker**.  They compose by both being consulted in
    `can_block` and either one refusing the block on its own -- a creature under
    a prohibition still cannot block an ordinary attacker, and an unblockable
    attacker is still unblockable by creatures under no prohibition at all.
    Neither reads the other, so a creature that is both prohibited from blocking
    and facing an unblockable attacker is refused twice, which is the same
    answer.

    Split from `characteristics.block_restrictions` -- the static "can't be
    blocked by Humans" -- for the reason `block_prohibited` is split from
    `block_forbidden`: that layer walks permanents on the battlefield and reads
    printed characteristics, and this belongs to no permanent and names a
    creature chosen when an ability resolved.  Rogue's Passage's target is not
    Rogue's Passage.

    "…can't be blocked this turn **except by creatures with haste**"
    (Gingerbrute) is an entry carrying ``except_blockers``, and it refuses only
    the blockers that do not match it -- so it can be answered only for a named
    ``blocker_oid``. Asked without one, the question is "can *nothing* block
    it?", and only an entry without an exemption says yes: a Gingerbrute that
    paid its {1} is still blockable by a hasty creature, and reading it as fully
    unblockable would be a strictly better card. The filter reads the blocker's
    derived characteristics, the way `block_restriction`'s ``blockers`` does, so
    a creature that gained haste this turn may block it; its ``controller``
    defaults to ``any`` for that reason's twin -- the blocker is the defending
    player's by definition, and "you" would exempt nobody. Two entries on one
    attacker are two restrictions, and a blocker must satisfy both.

    Guarded on the list being non-empty, because this is on the hot path of the
    block mask and the list is empty in most games.
    """
    if not state.unblockables:
        return False
    blocker = state.objects.get(blocker_oid) if blocker_oid is not None else None
    attacker = state.objects.get(oid)
    for entry in state.unblockables:
        if oid not in entry.objects:
            continue
        exempt = entry.except_blockers
        if exempt is None:
            return True
        if blocker is None or attacker is None:
            continue
        if not matches_static(
            state, blocker, attacker, {"controller": "any", **dict(exempt)}, derived=True
        ):
            return True
    return False


def can_block(
    state: GameState,
    blocker_oid: int,
    attacker_oid: int,
    defender: int,
    *,
    ignore_existing: bool = False,
) -> bool:
    """Whether this creature may be declared as a blocker of this attacker.

    ``ignore_existing`` skips the "it is already blocking something" check, and
    exists for block *requirements*. Rule 509.1c asks whether a declaration
    satisfies the maximum number of requirements it can, which is a question
    about what the creature is **able** to do -- and a creature that chose to
    block a different attacker was able to block this one. Asking plain
    `can_block` there would let any provoked creature excuse itself by blocking
    anything else at all, which is the one thing provoke exists to prevent.
    """
    combat = state.combat
    if combat is None or attacker_oid not in combat.attackers:
        return False
    if combat.attackers[attacker_oid] != defender:
        return False
    if attacker_oid in combat.removed:
        return False

    blocker = state.objects.get(blocker_oid)
    if blocker is None or not blocker.on_battlefield or blocker.tapped:
        return False
    if blocker.controller != defender:
        return False
    bc = chars(state, blocker_oid)
    if "Creature" not in bc.types:
        return False
    if not ignore_existing and blocker_oid in combat.blockers:
        return False

    # "This creature can't block." Unleash, and the mirror of `attack_forbidden`
    # -- checked here rather than in `blocks_valid` because it is a fact about
    # one creature, not about the shape of the whole declaration.
    if block_forbidden(state, blocker_oid):
        return False

    if blocker.detained_by is not None:
        return False

    # "That creature can't block this turn." The same sentence as the static
    # above, on a clock -- see `block_prohibited`. Asked here rather than folded
    # into `block_forbidden` because it is table state and not a static: the
    # characteristics layer reads permanents, and this belongs to none.
    if block_prohibited(state, blocker_oid):
        return False

    # "That creature can't be blocked this turn." (Rogue's Passage.) The line
    # above with the creatures swapped: that one asks whether this blocker may
    # block anything, this one whether this attacker may be blocked by anything.
    # Both are early-outs and neither consults the other, so a blocker under a
    # prohibition facing an unblockable attacker is refused by whichever is
    # asked first -- the same answer either way. The blocker is passed because
    # "…except by creatures with haste" (Gingerbrute) exempts some of them.
    if unblockable(state, attacker_oid, blocker_oid):
        return False

    # "Protection from Wizards" means it cannot be blocked by a Wizard. Checked
    # on the *attacker*, because it is the attacker that has the protection and
    # the blocker that has the quality.
    if protected_from(state, attacker_oid, blocker_oid):
        return False

    ac = chars(state, attacker_oid)
    grounded = not (
        Keyword.FLYING.value in bc.keywords or Keyword.REACH.value in bc.keywords
    )
    if Keyword.FLYING.value in ac.keywords and grounded:
        return False

    # Landwalk (702.14): unblockable while the *defending player* controls a
    # land of the named type. Unlike every other evasion, the condition is not a
    # quality of either creature -- which is exactly why it could not be written
    # as a `blockers` filter.
    for keyword, subtype in LANDWALK_SUBTYPE.items():
        if keyword in ac.keywords and _controls_land_type(state, defender, subtype):
            return False

    # Nonbasic landwalk: the same rule with the test inverted. A supertype the
    # land must *lack*, which is why it is its own keyword rather than a sixth
    # `LANDWALK_SUBTYPE` row.
    if Keyword.NONBASIC_LANDWALK.value in ac.keywords and _controls_nonbasic_land(
        state, defender
    ):
        return False

    # Skulk (702.72): "can't be blocked by creatures with greater power". The
    # first evasion that *compares* the two creatures rather than testing a
    # fixed quality of one, which is why it could not be a `blockers` filter:
    # those read printed characteristics, and skulk is asked of derived power on
    # both sides at the moment blockers are declared.
    if Keyword.SKULK.value in ac.keywords and bc.power > ac.power:
        return False

    # Horsemanship (702.32): "can't be blocked except by creatures with
    # horsemanship". The plainest of the exemption-shaped evasions -- the
    # blocker must carry the same keyword, and `chars` is read on both sides so
    # a granted horsemanship blocks a printed one.
    if Keyword.HORSEMANSHIP.value in ac.keywords and (
        Keyword.HORSEMANSHIP.value not in bc.keywords
    ):
        return False

    # Shadow (702.28): "can block or be blocked by only creatures with shadow".
    # The only evasion that cuts *both* ways, so it is asked of the pair rather
    # than of the attacker: a shadow creature may not block a normal one either,
    # which is what makes shadow a separate combat rather than an evasion.
    if (Keyword.SHADOW.value in ac.keywords) != (Keyword.SHADOW.value in bc.keywords):
        return False

    # Fear (702.36): "can't be blocked except by artifact creatures and/or black
    # creatures". Intimidate (702.13) is the same sentence with "black" replaced
    # by "creatures that share a color with it" -- a *relation*, so a colorless
    # creature with intimidate shares a color with nothing and only an artifact
    # creature may block it. Both read derived types and colors, which is why
    # neither could be a `blockers` filter even before the exemption/prohibition
    # mismatch: a creature made black by a static may block a fear creature.
    if "Artifact" not in bc.types:
        if Keyword.FEAR.value in ac.keywords and "B" not in bc.colors:
            return False
        if Keyword.INTIMIDATE.value in ac.keywords and not (ac.colors & bc.colors):
            return False

    # "This creature can't be blocked by Humans." A card-supplied restriction,
    # checked on the attacker because the attacker is what has it and the
    # blocker is what has the quality -- the same asymmetry as protection above.
    for source_obj, static in block_restrictions(state, attacker_oid):
        # "Can't be blocked by more than one creature" (Challenger Troll).
        # Asked per pair as well as on the whole declaration: once the attacker
        # has its quota no further blocker can ever make the declaration legal
        # again, so offering one would only build a block `blocks_valid` refuses.
        # This blocker is left out of the count, so a requirement asked with
        # `ignore_existing` does not count the creature against itself.
        if (cap := static.get("max_blockers")) is not None and (
            _blocker_count(state, attacker_oid, defender, excluding=blocker_oid) >= cap
        ):
            return False
        spec = static.get("blockers")
        if spec is None:
            continue
        # `controller` defaults to "you" everywhere else a static filter is
        # read, and here that default is always wrong: a blocker belongs to the
        # defending player by definition, so "you" would match nothing and the
        # restriction would silently never fire. Whose creature it is has
        # already been settled above; this clause is only about what it *is*.
        spec = {"controller": "any", **dict(spec)}
        # Derived, as the attacker side is: a creature some static made a Wall
        # is a Wall to "can't be blocked by Walls".
        if matches_static(state, blocker, source_obj, spec, derived=True):
            return False
    return True


def _controls_land_type(state: GameState, pid: int, subtype: str) -> bool:
    """Does this player control a land with that subtype, right now?

    Read from `chars`, not the printed card: Stormtide Leviathan's own second
    line makes every land an Island, and its islandwalk has to see that.
    """
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None or obj.controller != pid:
            continue
        c = chars(state, oid)
        if "Land" in c.types and subtype in c.subtypes:
            return True
    return False


def _controls_nonbasic_land(state: GameState, pid: int) -> bool:
    """Does this player control a land without the Basic supertype, right now?

    Read from `chars` for the same reason as :func:`_controls_land_type`, and
    the supertype is the whole test: a Forest that some effect turned into an
    Island is still basic, and a nonbasic land that gained a basic land type is
    still nonbasic.
    """
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None or obj.controller != pid:
            continue
        c = chars(state, oid)
        if "Land" in c.types and "Basic" not in c.supertypes:
            return True
    return False


def legal_blocks(state: GameState, defender: int) -> list[tuple[int, int]]:
    """Every legal (blocker, attacker) pair for this defending player."""
    combat = state.combat
    if combat is None:
        return []
    out: list[tuple[int, int]] = []
    for blocker_oid in state.battlefield:
        # A block requirement has to narrow what is *offered*, not merely what
        # can be finished -- which is where it stops being a mirror of
        # `must_attack`. Attacking is not exclusive, so a creature that must
        # attack can always be added to a declaration that already has others
        # in it, and withholding "Done attacking" is enough. Blocking is
        # exclusive: a provoked creature that blocks something else first has
        # no way back, `legal_blocks` then offers nothing, and the deadlock
        # escape in `legality._blocker_actions` hands out "Done blocking"
        # anyway -- so the requirement would be evadable by ignoring it early.
        required = _required_block(state, blocker_oid, defender)
        for attacker_oid in sorted(combat.attackers):
            if required is not None and attacker_oid != required:
                continue
            if can_block(state, blocker_oid, attacker_oid, defender):
                out.append((blocker_oid, attacker_oid))
    return out


def _required_block(state: GameState, blocker_oid: int, defender: int) -> int | None:
    """The attacker this creature must block, if it must and is able to."""
    obj = state.objects.get(blocker_oid)
    if obj is None or obj.must_block is None or obj.controller != defender:
        return None
    combat = state.combat
    attacker = obj.must_block
    if combat is None or attacker not in combat.attackers or attacker in combat.removed:
        return None
    if not can_block(state, blocker_oid, attacker, defender, ignore_existing=True):
        # "…if able". It owes nothing, so it is free to block whatever it likes.
        return None
    if block_taxed(state, blocker_oid):
        # 509.1c: a requirement never obliges a player to pay a block tax, so
        # a taxed creature owes nothing either -- and is just as free.
        return None
    return attacker


def drop_illegal_blocks(state: GameState, defender: int) -> list[int]:
    """Retract blocks that can never become a legal declaration.

    Declarations are made all at once in the rules and one block at a time
    here, and `require_all` is the shape where that difference bites.
    Tromokratis is "can't be blocked unless all creatures defending player
    controls block it": a player who blocks it with one creature and then finds
    no second legal block is **stuck forever** -- there is no `ADD_BLOCKER` left
    to offer and `blocks_valid` withholds "Done blocking", so the game cannot
    continue. A four-player rollout found exactly that on turn 47.

    Blocks like these were never legal, so dropping them is not a concession:
    "no creature blocks Tromokratis" is precisely what the rules would have
    produced. Returns the blockers it retracted.
    """
    combat = state.combat
    if combat is None:
        return []
    dropped: list[int] = []
    for attacker_oid, attacker_defender in combat.attackers.items():
        if attacker_defender != defender:
            continue
        blockers = [
            b
            for b in combat.block_order.get(attacker_oid, [])
            if state.objects.get(b) is not None
            and state.objects[b].controller == defender
        ]
        if not blockers or _all_blockers_present(state, attacker_oid, defender, blockers):
            continue
        for b in blockers:
            combat.blockers.pop(b, None)
            dropped.append(b)
        combat.block_order[attacker_oid] = [
            b for b in combat.block_order.get(attacker_oid, []) if b not in dropped
        ]
    # After the `require_all` pass, not before: dropping a Tromokratis block can
    # leave a can't-block-alone creature as the only blocker left, and then it
    # is the one that was never legal either.
    remaining = _blocking_for(state, defender)
    if not _alone_blocks_valid(state, remaining):
        for b in remaining:
            if not block_alone_forbidden(state, b):
                continue
            attacker_oid = combat.blockers.pop(b, None)
            dropped.append(b)
            if attacker_oid is not None:
                combat.block_order[attacker_oid] = [
                    other
                    for other in combat.block_order.get(attacker_oid, [])
                    if other != b
                ]
    return dropped


def add_blocker(state: GameState, blocker_oid: int, attacker_oid: int, defender: int) -> bool:
    combat = state.combat
    if combat is None or not can_block(state, blocker_oid, attacker_oid, defender):
        return False
    combat.blockers[blocker_oid] = attacker_oid
    combat.block_order.setdefault(attacker_oid, []).append(blocker_oid)
    return True


def _blocking_for(state: GameState, defender: int) -> list[int]:
    """The creatures this player currently has declared as blocking.

    Across every attacker, and filtered the way `_declared_attackers` is: a
    blocker that has left the battlefield or been removed from combat is not
    blocking any more (506.4), so it cannot be the company a can't-block-alone
    creature needs.
    """
    combat = state.combat
    if combat is None:
        return []
    out = []
    for oid in combat.blockers:
        obj = state.objects.get(oid)
        if obj is None or not obj.on_battlefield or oid in combat.removed:
            continue
        if obj.controller == defender:
            out.append(oid)
    return out


def _alone_blocks_valid(state: GameState, blocking: list[int]) -> bool:
    """Is no can't-block-alone creature this player's only blocker?

    Two of them blocking together is legal, and that is the point of writing it
    as "is there a second blocker" rather than "is this creature unrestricted":
    each is the other's company, which is what the printed word *alone* says.
    """
    if len(blocking) > 1:
        return True
    return not any(block_alone_forbidden(state, oid) for oid in blocking)


def blocks_valid(state: GameState, defender: int) -> bool:
    """Check evasion requirements that only make sense on the *complete* declaration.

    Three of them.  Menace: an attacker with menace must be blocked by zero or
    at least two creatures.  ``require_all``, Tromokratis' "can't be blocked
    unless all creatures defending player controls block it" -- which cannot be
    a per-pair check, because whether *this* block is legal depends on what
    every other creature is doing.  And "this creature can't block alone"
    (509.1b), which is the first of the three to be a fact about the *blocking*
    side rather than about one attacker.
    """
    combat = state.combat
    if combat is None:
        return True
    # "…can't block alone": legal alongside any second blocker this player
    # declares, whatever that one is blocking, and illegal by itself. Counted
    # across the whole declaration rather than per attacker, because the second
    # creature does not have to be blocking the same attacker -- which is
    # exactly what makes it a `blocks_valid` question and not a `can_block` one.
    if not _alone_blocks_valid(state, _blocking_for(state, defender)):
        return False
    # Provoke and the lure family. Enforced here rather than by refusing to
    # offer anything, for the same reason menace is: the declaration is legal
    # or not *as a whole*, and a player part-way through building one has not
    # broken a rule yet -- they have simply not finished.
    if unmet_block_requirements(state, defender):
        return False
    for attacker_oid, attacker_defender in combat.attackers.items():
        if attacker_defender != defender:
            continue
        blockers = [
            b
            for b in combat.block_order.get(attacker_oid, [])
            if state.objects.get(b) is not None
            and state.objects[b].controller == defender
        ]
        if (
            blockers
            and Keyword.MENACE.value in chars(state, attacker_oid).keywords
            and len(blockers) < 2
        ):
            return False
        if blockers and not _all_blockers_present(state, attacker_oid, defender, blockers):
            return False
        if len(blockers) > _max_blockers(state, attacker_oid):
            return False
    return True


def _blocker_count(
    state: GameState, attacker_oid: int, defender: int, *, excluding: int | None = None
) -> int:
    """How many of ``defender``'s creatures are declared blocking this attacker."""
    combat = state.combat
    if combat is None:
        return 0
    return sum(
        1
        for b in combat.block_order.get(attacker_oid, [])
        if b != excluding
        and (obj := state.objects.get(b)) is not None
        and obj.controller == defender
    )


def _max_blockers(state: GameState, attacker_oid: int) -> float:
    """The most creatures that may block this attacker; unbounded without a cap.

    Challenger Troll's "can't be blocked by more than one creature", a
    `block_restriction` with `max_blockers`. Two caps on one creature are both
    obeyed, so the least of them wins.
    """
    caps = [
        int(static["max_blockers"])
        for _source, static in block_restrictions(state, attacker_oid)
        if static.get("max_blockers") is not None
    ]
    return min(caps, default=float("inf"))


def _all_blockers_present(
    state: GameState, attacker_oid: int, defender: int, blockers: list[int]
) -> bool:
    """Tromokratis: every creature the defending player controls must be blocking it.

    The reminder text is literal -- "if any creature that player controls doesn't
    block this creature, it can't be blocked" -- and it says *controls*, not
    "could block". A tapped creature therefore makes the block illegal too,
    which is why the card is nearly unblockable and is the whole point of it.
    """
    for _source, static in block_restrictions(state, attacker_oid):
        if not static.get("require_all"):
            continue
        theirs = {
            oid
            for oid in state.battlefield
            if (obj := state.objects.get(oid)) is not None
            and obj.controller == defender
            and "Creature" in chars(state, oid).types
        }
        if theirs - set(blockers):
            return False
    return True


def finish_blockers(state: GameState) -> None:
    """Lock in blocks, sort the damage assignment order and fire block triggers."""
    combat = state.combat
    if combat is None:
        return
    # An incremental declaration can reach a state the rules would never have
    # produced -- see `drop_illegal_blocks`. Retract those before locking in,
    # so what gets recorded is a declaration that was actually legal.
    for defender in set(combat.attackers.values()):
        drop_illegal_blocks(state, defender)
    combat.blockers_declared = True
    discharge_block_requirements(state)

    # Damage assignment order is sorted by effective toughness ascending -- the
    # engine never asks the attacking player to order blockers.  Documented
    # simplification (docs/rules-coverage.md).
    for attacker_oid, blockers in combat.block_order.items():
        blockers.sort(key=lambda b: (_effective_toughness(state, b), b))
        del attacker_oid

    if combat.blockers:
        state.emit(
            EventType.BLOCKERS_DECLARED,
            attackers=sorted(combat.block_order),
            blockers=sorted(combat.blockers),
        )
        for blocker_oid in sorted(combat.blockers):
            obj = state.objects.get(blocker_oid)
            fire(
                state,
                EventType.BLOCKS,
                player=obj.controller if obj else None,
                source=blocker_oid,
                blocker=blocker_oid,
                attacker=combat.blockers[blocker_oid],
            )

    # Rule 509.1h, from the *attacker's* side. `BLOCKS` is one event per
    # blocker and says nothing to the creature being blocked -- an attacker
    # blocked by three creatures sees three unrelated events about somebody
    # else, and an attacker blocked by nobody sees none at all.
    #
    # Outside the `if combat.blockers` guard on purpose: the unblocked half is
    # the case where that guard is false, and frenzy is printed for exactly it.
    #
    # One `batch` for the whole declaration, because every attacker becomes
    # blocked or stays unblocked at the same instant (509.1h). It is what a
    # `batched` "whenever one or more creatures … attack you and aren't
    # blocked" (Coveted Jewel) groups by: one firing however many got through,
    # and a second combat is a second batch. See `triggers.BATCHED_EVENTS`.
    state.event_batch += 1
    batch = state.event_batch
    for attacker_oid in sorted(combat.attackers):
        if attacker_oid in combat.removed:
            continue
        obj = state.objects.get(attacker_oid)
        if obj is None:
            continue
        blocking_it = [b for b in combat.block_order.get(attacker_oid, []) if b in combat.blockers]
        fire(
            state,
            EventType.BECAME_BLOCKED if blocking_it else EventType.ATTACKED_UNBLOCKED,
            player=obj.controller,
            source=attacker_oid,
            attacker=attacker_oid,
            oid=attacker_oid,
            card=state.card_of(obj).id,
            # Rampage is "for each creature blocking it **beyond the first**",
            # so the count is the number and the card does the arithmetic.
            blockers=len(blocking_it),
            defender=combat.attackers[attacker_oid],
            batch=batch,
        )


def _effective_toughness(state: GameState, oid: int) -> int:
    obj = state.objects.get(oid)
    if obj is None:
        return 0
    return max(0, chars(state, oid).toughness - obj.damage)


# ----------------------------------------------------------------------
# damage
# ----------------------------------------------------------------------


def has_first_strike_combatants(state: GameState) -> bool:
    combat = state.combat
    if combat is None:
        return False
    participants = set(combat.attackers) | set(combat.blockers)
    for oid in participants:
        if oid in combat.removed or oid not in state.objects:
            continue
        keywords = chars(state, oid).keywords
        if Keyword.FIRST_STRIKE.value in keywords or Keyword.DOUBLE_STRIKE.value in keywords:
            return True
    return False


def _deals_damage_this_step(state: GameState, oid: int, first_strike_step: bool) -> bool:
    keywords = chars(state, oid).keywords
    first = Keyword.FIRST_STRIKE.value in keywords
    double = Keyword.DOUBLE_STRIKE.value in keywords
    if first_strike_step:
        return first or double
    return double or not first


def deal_combat_damage(
    state: GameState, *, first_strike_step: bool
) -> Generator[Any, list[int]]:
    """Collect every assignment, then apply them all at once.

    A generator because of banding, and only because of it: 702.21 moves the
    choice of a creature's **damage assignment order** to the other player, and
    a choice has to be asked. Every combat without banding in it asks nothing
    and behaves exactly as it did -- `_ask_order` returns immediately when there
    is nothing to order.
    """
    combat = state.combat
    if combat is None:
        return

    assignments: list[DamageAssignment] = []

    for attacker_oid in sorted(combat.attackers):
        if not _in_combat(state, attacker_oid):
            continue
        if not _deals_damage_this_step(state, attacker_oid, first_strike_step):
            continue
        # 702.21: a blocking creature with banding takes this order away from
        # the attacking player. The automatic sort *is* the attacker's choice
        # made silently, so this is the whole of banding's defensive half.
        chooser = _order_chooser(state, attacker_oid)
        if chooser is not None:
            blockers = [
                b for b in combat.block_order.get(attacker_oid, []) if _in_combat(state, b)
            ]
            order = yield from _ask_order(
                state, chooser, attacker_oid,
                blockers, f"Order the blockers of {state.card(attacker_oid).name}",
            )
            combat.block_order[attacker_oid] = order
        assignments.extend(_attacker_assignments(state, attacker_oid))

    for blocker_oid in sorted(combat.blockers):
        if not _in_combat(state, blocker_oid):
            continue
        attacker_oid = combat.blockers[blocker_oid]
        if not _in_combat(state, attacker_oid):
            continue
        if not _deals_damage_this_step(state, blocker_oid, first_strike_step):
            continue
        power = chars(state, blocker_oid).power
        if power <= 0:
            continue
        # A creature blocking a **band** has several attackers to divide its
        # damage between, and 702.21 gives that order to the attacking player.
        # `band_of` returns a band of one for everything else, so the ordinary
        # case falls straight through to the single assignment below.
        band = [b for b in combat.band_of(attacker_oid) if _in_combat(state, b)]
        if len(band) > 1:
            attacking = state.objects[attacker_oid].controller
            band = yield from _ask_order(
                state, attacking, blocker_oid, band,
                f"Order the band for {state.card(blocker_oid).name}'s damage",
            )
        assignments.extend(_divide(state, blocker_oid, power, band))

    # Read before a single point lands: the monarch's own inherent trigger asks
    # who was the monarch *when the damage was dealt*, and the transfer below
    # would otherwise be answering a question its own first hit had changed.
    monarch_before = state.monarch

    # 510.2: all of this step's combat damage is dealt at once, so it is one
    # batch -- what a `batched` `dealt_damage` trigger groups by, and sums, so
    # a creature blocked by two others is dealt damage once, for the total.
    # Captured here and passed down rather than read as each point lands, so
    # nothing a replacement runs mid-step can split the event. A first-strike
    # step is a batch of its own (510.4).
    state.event_batch += 1
    batch = state.event_batch

    # What each source actually dealt, after prevention -- "deals combat damage"
    # is about damage that was dealt, and a fully prevented blow is none.
    dealt: dict[int, int] = {}
    for assignment in assignments:
        amount = 0
        if assignment.to_player is not None:
            amount = damage_player(
                state, assignment.to_player, assignment.amount, assignment.source, is_combat=True
            )
        elif assignment.to_object is not None:
            amount = damage_permanent(
                state, assignment.to_object, assignment.amount, assignment.source,
                is_combat=True, batch=batch,
            )
        if amount and assignment.source is not None:
            dealt[assignment.source] = dealt.get(assignment.source, 0) + amount

    _monarch_transfer(state, monarch_before, assignments)
    _fire_damage_batch(state, assignments)
    _fire_per_source(state, dealt)

    if first_strike_step:
        combat.first_strike_done = True


def _fire_damage_batch(state: GameState, assignments: list[DamageAssignment]) -> None:
    """"Whenever one or more creatures you control deal combat damage to one or
    more players" -- once for the batch, not once per creature.

    Read off the same `assignments` list `_monarch_transfer` above reads, and
    for the same reason: 510.2 makes combat damage one simultaneous event, so
    the whole of "one or more creatures … one or more players" is knowable here
    and nowhere else. `damage_player` sees the hits one at a time and cannot
    tell the first of a batch from the third.

    One event per **damaging player**, which is where the batching has to stop.
    Firing it once for the whole step would leave `controller: "you"` with no
    actor to compare against; firing it per (damager, defender) pair would pay
    twice for a seat whose creatures connected with two opponents, and the
    printed clause is "to one or more **players**". So the seats hit ride along
    on `damaged` for anything that wants to ask, and the event itself counts
    seats that *swung*.

    "…to **a player**" / "…to **an opponent**" is the other reading, and it is
    per seat: the ability triggers once for each player dealt damage, and "that
    player" is the one seat it fired for. That is not a second event -- it
    would fire every existing card's trigger twice on the same swing -- but a
    `per_player` trigger fanned out by `triggers.collect` over `hits`, which
    pairs each damaged seat with the creatures that hit it.

    **Creatures**, by derived type, which is the same reading `_monarch_transfer`
    takes one line up: an animated Equipment that got through is a creature and
    its printed face says otherwise. Damage to a blocker is not damage to a
    player and is filtered out with it.

    **…or battle** (310.6). "Whenever one or more Dragons you control deal
    combat damage to a player **or battle**" -- Zurgo and Ojutai -- is one
    printed sentence with two kinds of recipient in it, and it is the same batch
    on the same step, so the battles ride along on `damaged_battles` beside the
    seats on `damaged`. The event now fires for a swing that hit **only** a
    battle, where before there was nothing to fire it for, and that is exactly
    the thing a widening has to be careful about: `triggers._matches` refuses a
    battle-only firing unless the trigger says `or_battle`, so every card
    already written against this event keeps meaning "to one or more players".
    Firing it and filtering there rather than deciding here is what lets one
    event serve both sentences -- a second event would double every existing
    card's trigger on a mixed swing.

    A planeswalker hit is **not** in either list. That half of 506.2 has its own
    per-connection event (`COMBAT_DAMAGE_TO_PLANESWALKER`) because the cards
    that name planeswalkers name one creature at a time; no printed card says
    "one or more creatures … deal combat damage to a planeswalker".

    Fired once per **step**, so first strike and regular damage are two batches
    (510.4). A card that connects in both windows triggers twice, which is what
    the rules say and what the per-creature event has always done.
    """
    by_player: dict[int, dict[str, list[int]]] = {}
    for assignment in assignments:
        if assignment.amount <= 0:
            continue
        # A seat, or a battle. Anything else -- a blocker, a planeswalker -- is
        # not what this sentence is about.
        hit_battle = assignment.to_object is not None and "Battle" in chars(
            state, assignment.to_object
        ).types
        if assignment.to_player is None and not hit_battle:
            continue
        source = state.objects.get(assignment.source)
        if source is None or "Creature" not in chars(state, source.oid).types:
            continue
        batch = by_player.setdefault(
            source.controller, {"damagers": [], "damaged": [], "battles": [], "hits": {}}
        )
        if source.oid not in batch["damagers"]:
            batch["damagers"].append(source.oid)
        if assignment.to_player is not None:
            if assignment.to_player not in batch["damaged"]:
                batch["damaged"].append(assignment.to_player)
            hit = batch["hits"].setdefault(assignment.to_player, [])
            if source.oid not in hit:
                hit.append(source.oid)
        elif assignment.to_object not in batch["battles"]:
            batch["battles"].append(assignment.to_object)
    for pid in state.turn_order():
        batch = by_player.get(pid)
        if batch is None:
            continue
        fire(
            state,
            EventType.CREATURES_DEALT_COMBAT_DAMAGE,
            player=pid,
            damagers=sorted(batch["damagers"]),
            damaged=sorted(batch["damaged"]),
            damaged_battles=sorted(batch["battles"]),
            # Which creatures connected with which seat, for the
            # `per_player` reading -- "…deal combat damage to **an
            # opponent**, destroy target artifact **that opponent**
            # controls" (Parapet Thrasher). One entry per seat in `damaged`,
            # in seat order, so `triggers.collect` can ask the trigger once
            # per seat with only the creatures that hit *that* seat: a Dragon
            # that hit one opponent and an Elf that hit another are not "one
            # or more Dragons" for the second.
            hits=[
                {"player": seat, "damagers": sorted(batch["hits"][seat])}
                for seat in sorted(batch["hits"])
            ],
        )


def _monarch_transfer(
    state: GameState, monarch_before: int | None, assignments: list[DamageAssignment]
) -> None:
    """"Whenever a creature deals combat damage to the monarch, that creature's
    controller becomes the monarch" (721.3).

    One of the monarch's two inherent triggered abilities. It has no source and
    is controlled by the game, which is why it lives here rather than on a card
    -- and it is what makes the designation *worth* something: on most boards it
    is the only way the crown ever moves, and it is the only thing that can ever
    end Palace Jailer's exile.

    Here rather than inside `damage_player`, and the reason is the batch. Combat
    damage is dealt simultaneously (510.2) and this collects every assignment
    before applying any, so `monarch_before` is the one true answer to "who was
    the monarch" for the whole step. Folded into `damage_player` it would read the
    field one hit at a time, and a second creature connecting in the same step
    would find the crown already moved by the first and transfer nothing.

    **Divergence, shared with `delay` and the day/night switch:** this resolves
    inline rather than going on the stack, so nothing can respond between the
    damage and the crown changing hands. Observable only to somebody who would
    answer the transfer differently from the damage that caused it.

    Ties are 603.3b rather than iteration order. Several players' creatures
    hitting the same monarch each trigger, the active player puts theirs on the
    stack first, and first on is last off -- so the APNAP-earliest damager is the
    one whose trigger resolves last and wins. Unreachable while every attacker
    belongs to the active player, and written the right way round so it stays
    correct when that changes.
    """
    if monarch_before is None:
        return
    by_player: dict[int, int] = {}
    for assignment in assignments:
        if assignment.to_player != monarch_before or assignment.amount <= 0:
            continue
        source = state.objects.get(assignment.source)
        # "A **creature**": read off derived types, for the reason every other
        # combat check does -- an animated Equipment that got through is a
        # creature, and the printed face would say otherwise.
        if source is None or "Creature" not in chars(state, source.oid).types:
            continue
        by_player.setdefault(source.controller, source.oid)
    if not by_player:
        return
    for pid in state.turn_order():
        if pid in by_player:
            become_monarch(state, pid, source=by_player[pid])
            return


def _declare_bands(state: GameState) -> Generator[Any, list[int]]:
    """"One or more attacking creatures with banding and up to one without" (702.21b).

    Asked as **two** questions rather than one, because that sentence is two
    constraints and `ask_objects` expresses each of them exactly: any number
    from the creatures with banding, then at most one from the creatures
    without. A single question over all attackers could not say "up to one
    without" at all, and validating the answer afterwards would mean offering a
    choice the engine then refuses.

    Looped, because a player may declare more than one band. The loop ends when
    they stop picking, which is also how they decline to band at all.
    """

    combat = state.combat
    if combat is None:
        return
    pid = state.active_player
    ctx = EffectContext(state=state, controller=pid, source_oid=None)
    banded: set[int] = set()
    for _ in range(len(combat.attackers)):
        pool = [
            oid
            for oid in sorted(combat.attackers)
            if oid not in banded
            and Keyword.BANDING.value in chars(state, oid).keywords
        ]
        if not pool:
            return
        members = yield from ask_objects(
            ctx, pool, 0, len(pool), "Form a band with", pid, purpose="banding"
        )
        if not members:
            return
        # "…and up to one attacking creature without banding", which has to be
        # attacking the same player: a band is blocked as a unit, and a unit
        # spread across two defenders is not one.
        defender = combat.attackers[members[0]]
        others = [
            oid
            for oid in sorted(combat.attackers)
            if oid not in banded
            and oid not in members
            and combat.attackers[oid] == defender
            and Keyword.BANDING.value not in chars(state, oid).keywords
        ]
        tagalong: list[int] = []
        if others:
            tagalong = yield from ask_objects(
                ctx, others, 0, 1, "Add one creature without banding to the band",
                pid, purpose="banding",
            )
        band = [*members, *tagalong]
        combat.bands.append(band)
        banded.update(band)
        state.emit("band_declared", player=pid, attackers=sorted(band))


def _order_chooser(state: GameState, attacker_oid: int) -> int | None:
    """Who picks this attacker's damage assignment order, if not the engine.

    702.21: a creature with banding on the **blocking** side takes the choice
    away from the attacking player and gives it to its own controller. The
    engine's automatic sort is that choice made silently on the attacker's
    behalf, so banding's whole content here is "ask, and ask the other player".

    ``None`` means nobody is asked and the automatic order stands, which is
    every combat without banding in it.
    """
    combat = state.combat
    assert combat is not None
    for blocker_oid in combat.block_order.get(attacker_oid, []):
        if not _in_combat(state, blocker_oid):
            continue
        if Keyword.BANDING.value in chars(state, blocker_oid).keywords:
            obj = state.objects.get(blocker_oid)
            return obj.controller if obj is not None else None
    return None


def _ask_order(
    state: GameState, chooser: int, subject: int, options: list[int], prompt: str
) -> Generator[Any, list[int], list[int]]:
    """Ask a player to order some creatures for damage assignment.

    Returns the chosen order followed by anything not chosen, so a short answer
    is still a complete order and the caller never has to handle a partial one.
    `ask_objects` records the order the options were taken in, which is exactly
    what a damage assignment order is -- the engine has had the concept all
    along and has simply been sorting it by effective toughness.
    """

    if len(options) < 2:
        return options
    ctx = EffectContext(state=state, controller=chooser, source_oid=subject)
    picked = yield from ask_objects(
        ctx, options, 0, len(options), prompt, chooser, purpose="damage_order"
    )
    return [*picked, *[oid for oid in options if oid not in picked]]


def _divide(
    state: GameState, source_oid: int, power: int, targets: list[int]
) -> list[DamageAssignment]:
    """Lethal to each in order, the way an attacker already divides among blockers.

    Rule 510.1c is one rule, not two: whoever is assigning, they must give each
    creature lethal damage before assigning any to the next. So this is the same
    walk `_attacker_assignments` makes, factored out and pointed the other way --
    a blocker dividing among a band it is blocking.
    """
    deathtouch = Keyword.DEATHTOUCH.value in chars(state, source_oid).keywords
    out: list[DamageAssignment] = []
    remaining = power
    for oid in targets:
        if remaining <= 0:
            break
        lethal = 1 if deathtouch else max(1, _effective_toughness(state, oid))
        assign = min(remaining, lethal)
        out.append(DamageAssignment(source=source_oid, to_object=oid, amount=assign))
        remaining -= assign
    if remaining > 0 and out:
        last = out[-1]
        out[-1] = DamageAssignment(
            source=last.source, to_object=last.to_object, amount=last.amount + remaining
        )
    return out


def _in_combat(state: GameState, oid: int) -> bool:
    combat = state.combat
    if combat is None or oid in combat.removed:
        return False
    obj = state.objects.get(oid)
    return obj is not None and obj.on_battlefield


def _attacker_assignments(state: GameState, attacker_oid: int) -> list[DamageAssignment]:
    combat = state.combat
    assert combat is not None
    power = chars(state, attacker_oid).power
    if power <= 0:
        return []

    keywords = chars(state, attacker_oid).keywords
    deathtouch = Keyword.DEATHTOUCH.value in keywords
    trample = Keyword.TRAMPLE.value in keywords
    defender = combat.attackers[attacker_oid]

    blockers = [b for b in combat.block_order.get(attacker_oid, []) if _in_combat(state, b)]
    # 702.21e: a band is blocked as a unit. A member nobody blocked is still
    # blocked if any of its band was, so it deals no damage to the player --
    # which is the whole defensive value of blocking a band, and the reason a
    # band is a unit rather than a convenience.
    was_blocked = any(combat.block_order.get(oid) for oid in combat.band_of(attacker_oid))

    if not was_blocked:
        # 508.1: a creature attacking a planeswalker **or battle** that is still
        # there deals its damage to that permanent instead of to its controller.
        # If it has already left -- burned down in response, or bounced -- the
        # attacker deals no combat damage at all rather than falling through to
        # the player, which is 506.4c and the whole risk of the attack.
        #
        # One branch for both, because the difference between them is entirely
        # downstream: `damage_permanent` reads the type and takes the amount off
        # loyalty (306.8) or off defense (310.6). Nothing about *assigning* the
        # damage knows which it is.
        target = combat.attacking_permanent.get(attacker_oid)
        if target is not None:
            obj = state.objects.get(target)
            if obj is None or not obj.on_battlefield:
                return []
            return [
                DamageAssignment(source=attacker_oid, to_object=target, amount=power)
            ]
        return [DamageAssignment(source=attacker_oid, to_player=defender, amount=power)]

    out: list[DamageAssignment] = []
    remaining = power
    for blocker_oid in blockers:
        if remaining <= 0:
            break
        lethal = 1 if deathtouch else max(1, _effective_toughness(state, blocker_oid))
        assign = min(remaining, lethal)
        out.append(DamageAssignment(source=attacker_oid, to_object=blocker_oid, amount=assign))
        remaining -= assign

    if remaining > 0:
        if trample:
            out.append(
                DamageAssignment(source=attacker_oid, to_player=defender, amount=remaining)
            )
        elif out:
            last = out[-1]
            out[-1] = DamageAssignment(
                source=last.source, to_object=last.to_object, amount=last.amount + remaining
            )
        elif not blockers:
            # Every blocker has died or left; a blocked creature without trample
            # deals no damage at all.
            pass
    return out


def end_combat(state: GameState) -> None:
    state.combat = None
    # "…can't attack you **this combat**." Cleared here rather than at cleanup,
    # which is the whole difference between the two durations: a turn with an
    # extra combat phase re-asks Champions of Minas Tirith's tax, because its
    # trigger fires at the beginning of each combat and the previous combat's
    # restriction has gone with the combat that bought it.
    clear_attack_restrictions(state, "this_combat")
    # "…deals combat damage to a player **this combat**" (Love on the
    # Battlefield): the event-watching delayed abilities on the same clock, for
    # the same reason. An extra combat later this turn is a combat of its own.
    state.delayed_triggers = [
        d
        for d in state.delayed_triggers
        if d.trigger is None or d.duration != "this_combat"
    ]


def _fire_per_source(state: GameState, dealt: dict[int, int]) -> None:
    """"Whenever this creature deals combat damage, …" -- once per creature per
    combat damage step, **whatever it hit and however many things**.

    Tamiyo, Field Researcher: "whenever either of those creatures deals combat
    damage, you draw a card." The three per-recipient events are each the wrong
    half: `COMBAT_DAMAGE_TO_PLAYER` and `COMBAT_DAMAGE_TO_PLANESWALKER` miss a
    blocked creature, and `DAMAGE_DEALT` fires once per recipient -- so a
    trampler that hits its blocker and the player would trigger twice where the
    printed ability triggers once (510.2 makes the step's damage one event).
    Hanging the card on all three would be that double draw.

    Read off the amounts actually dealt, after prevention, so a creature whose
    every point was prevented dealt nothing and fires nothing. Fired once per
    step, so first strike and regular damage are two firings (510.4), as for
    every other combat damage event. ``source`` is the dealer and there is no
    ``oid`` key, so `triggers._subject_oid` falls through to it.
    """
    for source_oid in sorted(dealt):
        source = state.objects.get(source_oid)
        fire(
            state,
            EventType.CREATURE_DEALT_COMBAT_DAMAGE,
            player=None if source is None else source.controller,
            source=source_oid,
            amount=dealt[source_oid],
        )
