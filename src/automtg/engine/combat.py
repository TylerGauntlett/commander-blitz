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

from .characteristics import (
    attack_compelled,
    attack_forbidden,
    block_forbidden,
    block_restrictions,
    chars,
    matches_static,
    protected_from,
)
from .enums import LANDWALK_SUBTYPE, Keyword
from .events import EventType
from .primitives import damage_permanent, damage_player, tap_permanent
from .structs import CombatState
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
    combat = state.combat
    return combat is None or oid not in combat.attackers


def attack_required(state: GameState, oid: int) -> bool:
    """Must this creature attack right now, and can it?

    "…if able" is the whole of the second half: a requirement never makes an
    illegal attack legal, and a tapped or summoning-sick creature simply does
    not have to.  So this is the requirement AND `can_attack`, never one alone.
    """
    obj = state.objects.get(oid)
    if obj is None:
        return False
    # Two sources, one enforcement point. The `must_attack` op writes a
    # one-shot flag that `discharge_attack_requirements` spends; a printed
    # "attacks each combat if able" is a static, read live and never spent.
    # Both are "…if able", so both go through `can_attack` below.
    if not attack_compelled(state, oid):
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


def legal_defenders(state: GameState) -> list[int]:
    return [pid for pid in state.alive() if pid != state.active_player]


def legal_planeswalker_defenders(state: GameState) -> list[int]:
    """Planeswalkers that may be attacked, in deterministic order (506.2).

    Every planeswalker controlled by a player who could be attacked. Its
    controller is the defending player, which is why attacking one does not
    need its own notion of "who is being attacked" -- `attackers[oid]` still
    answers that, and still truthfully.
    """
    from .characteristics import chars

    defenders = set(legal_defenders(state))
    return [
        oid
        for oid in state.battlefield
        if (obj := state.objects.get(oid)) is not None
        and obj.controller in defenders
        and "Planeswalker" in chars(state, oid).types
    ]


def add_attacker(
    state: GameState, oid: int, defender: int, *, planeswalker: int | None = None
) -> bool:
    combat = state.combat
    if combat is None or not can_attack(state, oid) or defender not in legal_defenders(state):
        return False
    if planeswalker is not None:
        if planeswalker not in legal_planeswalker_defenders(state):
            return False
        obj = state.objects.get(planeswalker)
        if obj is None or obj.controller != defender:
            # The planeswalker and the player have to agree, or `attackers[oid]`
            # -- which everything else reads as "the defending player" -- would
            # name someone this creature is not attacking.
            return False
        combat.attacking_planeswalker[oid] = planeswalker
    combat.attackers[oid] = defender
    return True


def remove_attacker(state: GameState, oid: int) -> None:
    if state.combat is not None:
        state.combat.attackers.pop(oid, None)
        state.combat.attacking_planeswalker.pop(oid, None)


def finish_attackers(state: GameState) -> Generator[Any, list[int], None]:
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
        for oid in sorted(combat.attackers):
            obj = state.objects.get(oid)
            fire(
                state,
                EventType.ATTACKS,
                player=obj.controller if obj else state.active_player,
                source=oid,
                attacker=oid,
                defender=combat.attackers[oid],
            )
    combat.pending_blockers = [
        pid for pid in state.turn_order() if pid in set(combat.attackers.values())
    ]


# ----------------------------------------------------------------------
# blockers
# ----------------------------------------------------------------------


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
        spec = static.get("blockers")
        if spec is None:
            continue
        # `controller` defaults to "you" everywhere else a static filter is
        # read, and here that default is always wrong: a blocker belongs to the
        # defending player by definition, so "you" would match nothing and the
        # restriction would silently never fire. Whose creature it is has
        # already been settled above; this clause is only about what it *is*.
        spec = {"controller": "any", **dict(spec)}
        if matches_static(state, blocker, source_obj, spec):
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
    return dropped


def add_blocker(state: GameState, blocker_oid: int, attacker_oid: int, defender: int) -> bool:
    combat = state.combat
    if combat is None or not can_block(state, blocker_oid, attacker_oid, defender):
        return False
    combat.blockers[blocker_oid] = attacker_oid
    combat.block_order.setdefault(attacker_oid, []).append(blocker_oid)
    return True


def blocks_valid(state: GameState, defender: int) -> bool:
    """Check evasion requirements that only make sense on the *complete* declaration.

    Two of them.  Menace: an attacker with menace must be blocked by zero or at
    least two creatures.  And ``require_all``, Tromokratis' "can't be blocked
    unless all creatures defending player controls block it" -- which cannot be
    a per-pair check, because whether *this* block is legal depends on what
    every other creature is doing.
    """
    combat = state.combat
    if combat is None:
        return True
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
    return True


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
) -> Generator[Any, list[int], None]:
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

    for assignment in assignments:
        if assignment.to_player is not None:
            damage_player(
                state, assignment.to_player, assignment.amount, assignment.source, is_combat=True
            )
        elif assignment.to_object is not None:
            damage_permanent(
                state, assignment.to_object, assignment.amount, assignment.source, is_combat=True
            )

    if first_strike_step:
        combat.first_strike_done = True


def _declare_bands(state: GameState) -> Generator[Any, list[int], None]:
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
    from .effects.context import EffectContext, ask_objects

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
    from .effects.context import EffectContext, ask_objects

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
        # 508.1: a creature attacking a planeswalker that is still there deals
        # its damage to the planeswalker instead of to its controller. If the
        # planeswalker has already left -- burned down in response, or bounced
        # -- the attacker deals no combat damage at all rather than falling
        # through to the player, which is 506.4c and the whole risk of the
        # attack.
        target = combat.attacking_planeswalker.get(attacker_oid)
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
