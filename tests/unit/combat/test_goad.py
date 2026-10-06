"""Goad: two rules in one word, and both of them "if able".

Rule 701.38a -- "until your next turn, that creature attacks each combat if able
and attacks a player other than you if able". Every other combat effect in the
engine is one of those two halves and never both:

- **The compulsion** existed twice already and neither form fits. The
  `must_attack` op is one-shot: `combat.discharge_attack_requirements` spends the
  flag when attackers lock in, so `this_turn` and `next_combat` each compel
  exactly one combat where goad compels *every* combat until its goader untaps.
  The `attacks_if_able` static is the live, unspent form, but it is a continuous
  ability on a permanent -- a sorcery leaves nothing on the battlefield to own
  it, and a static's `affects` filter reads only printed characteristics, so it
  can say neither "those creatures" (the set chosen at resolution) nor "until
  your next turn".
- **The target restriction did not exist at all.** Nothing in the engine
  restricted *which* defender a given attacker could pick: `legal_defenders` was
  a list of everybody who is not the active player, and `cant_attack` /
  `attack_forbidden` is all-or-nothing. Without this half a goaded creature
  swings straight back at the player who goaded it, and goad stops being a
  political card and becomes a one-sided Overrun.

The witness is **Taunt from the Rampart** -- "Goad all creatures your opponents
control. Until your next turn, those creatures can't block." Its other half
shipped with `cant_block`; this is the half that makes the card work, and the two
together are also why `detain` could not stand in for either: detain forbids
attacking, which is the thing this card demands.

What is pinned below, and each is a way goad could be silently wrong rather than
broken:

1. The compulsion bites -- a goaded creature has "Done attacking" withheld.
2. It is **not spent** by a declaration. `discharge_attack_requirements` clears
   `must_attack` and nothing else, so the next combat is compelled too. A goad
   built on `must_attack` passes a one-combat test and is wrong from the second
   combat onwards.
3. The defender restriction bites, and it **reaches planeswalkers** -- the exact
   opposite answer from `cant_attack_player`, which is why
   `combat.attack_target_forbidden` takes `planeswalker` as a parameter rather
   than inferring it. Attacking the goader's planeswalker is attacking the
   goader; a Ghostly Prison reading would let every goad be dodged by a board
   with a walker on it.
4. Both "if able" escapes:
   - a creature that cannot attack at all owes nothing, so the step never
     deadlocks with "Done attacking" withheld and no `ADD_ATTACKER` to offer;
   - a creature whose only remaining defender *is* its goader may attack them.
5. The clock. Goad ends in the **goading player's** untap step -- detain's clock,
   keyed to a player and never to a turn number, because eliminating somebody
   moves everybody else's "next turn". Somebody else's untap step must not clear
   it, and an eliminated goader's mark must not outlive them.
6. Two goaders are two obligations: one clock expiring leaves the other standing,
   and a creature goaded by everybody left is free to attack any of them.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import combat as combat_mod
from automtg.engine import sba
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.primitives import untap_permanent
from automtg.engine.state import new_object
from automtg.engine.temp_effects import clear_goad, goad_creature, restrict_attack
from automtg.engine.turn import grant_extra_phases
from automtg.engine.zones import move_object
from tests.conftest import _default_answer, only_oid, pass_until

BEAR = "t_bear"
WALKER = "t_walker"
GOADER = "t_goader"  # {2}{R} sorcery: goad all creatures your opponents control


def position(builder, *, players=3, theirs=(BEAR,), mine=(), lends=(), active=1, hand=()):
    """Player 1's creatures, goaded by player 0, on player 1's own turn.

    ``active`` defaults to 1 because that is the only turn a goad can be *owed*
    on: a creature cannot attack on somebody else's turn, so "if able" excuses it
    everywhere else. Built from the untap step and advanced, so the position
    starts at the active player's first priority with the turn's own machinery
    having run -- a mark placed after this is one a resolving spell could have
    placed.
    """
    b = builder(players=players)
    if theirs:
        b.battlefield(1, list(theirs))
    if mine:
        b.battlefield(0, list(mine))
    if lends:
        b.battlefield(2, list(lends))
    if hand:
        b.hand(0, list(hand)).battlefield(0, ["mountain", "mountain", "mountain"])
    return b.active(active).step(Step.UNTAP).build()


def to_declare_attackers(game, limit: int = 80):
    """Advance to the declare-attackers decision, resolving whatever is on the way."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_ATTACKERS:
            return game
        game.apply(_default_answer(game, decision))
    raise AssertionError("never reached declare attackers")


def attack_actions(game, oid: int | None = None):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_ATTACKER and (oid is None or a.source == oid)
    ]


def defenders_offered(game, oid: int) -> list[int]:
    """Which *players* this creature is offered as able to attack."""
    return sorted(
        t.id for a in attack_actions(game, oid) for t in a.targets if t.kind == "player"
    )


def walkers_offered(game, oid: int) -> list[int]:
    """Which *planeswalkers* this creature is offered as able to attack."""
    return sorted(
        t.id for a in attack_actions(game, oid) for t in a.targets if t.kind == "object"
    )


def can_finish(game) -> bool:
    return any(a.kind is ActionKind.FINISH_DECLARATION for a in game.legal_actions())


def cast(game, card_id: str, limit: int = 40) -> None:
    """Cast a sorcery from player 0's hand and let it resolve."""
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and a.source is not None
        and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    for _ in range(limit):
        if not game.state.stack and not game.state.pending_triggers:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError(f"{card_id} never resolved")


class TestTheCompulsion:
    def test_the_unrestricted_baseline(self, builder):
        game = position(builder)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == []
        assert can_finish(game), "nobody has to attack"

    def test_a_goaded_creature_must_attack(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        assert combat_mod.attack_required(game.state, bear)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == [bear]
        assert not can_finish(game), '"Done attacking" is withheld'

    def test_attacking_satisfies_it(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        to_declare_attackers(game)
        add = next(a for a in attack_actions(game, bear))
        game.apply(add)
        assert combat_mod.unmet_attack_requirements(game.state) == []
        assert can_finish(game)

    def test_it_is_owed_only_on_the_creatures_own_turn(self, builder):
        """The goading player's own declaration must not be held hostage. A
        creature cannot attack on somebody else's turn, so "if able" excuses it
        -- and without that, player 0 could never finish a declaration while an
        opponent held an untapped goaded creature."""
        game = position(builder, mine=(BEAR,), active=0)
        theirs = only_oid(game, BEAR, 1)
        goad_creature(game.state, theirs, 0)
        assert not combat_mod.attack_required(game.state, theirs)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == []
        assert can_finish(game)


class TestItIsNotSpentByADeclaration:
    """The whole reason goad is not `must_attack` with a third duration.

    `discharge_attack_requirements` clears `must_attack` when attackers lock in,
    because a one-shot obligation the creature could not meet is still spent. A
    goad is not an obligation that was placed -- it is a mark that is *read*, so
    it survives the declaration and compels the next combat too.
    """

    def test_the_mark_survives_where_must_attack_does_not(self, builder):
        game = position(builder, theirs=(BEAR, BEAR))
        goaded, flagged = sorted(
            o for o in game.state.battlefield if game.state.objects[o].def_id == BEAR
        )
        goad_creature(game.state, goaded, 0)
        game.state.objects[flagged].must_attack = "this_turn"
        game.state.objects[flagged].must_attack_turn = game.state.turn
        to_declare_attackers(game)
        for oid in (goaded, flagged):
            game.apply(next(a for a in attack_actions(game, oid)))
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
        assert game.state.objects[flagged].must_attack is None, "one-shot, spent"
        assert game.state.objects[goaded].goaded_by == {0}, "a mark, not a flag"

    def test_the_next_combat_is_compelled_too(self, builder):
        """An extra combat phase in the same turn: the goad is live again, and a
        `must_attack` creature beside it owes nothing."""
        game = position(builder, theirs=(BEAR, BEAR))
        goaded, flagged = sorted(
            o for o in game.state.battlefield if game.state.objects[o].def_id == BEAR
        )
        goad_creature(game.state, goaded, 0)
        game.state.objects[flagged].must_attack = "this_turn"
        game.state.objects[flagged].must_attack_turn = game.state.turn
        to_declare_attackers(game)
        for oid in (goaded, flagged):
            game.apply(next(a for a in attack_actions(game, oid)))
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
        assert grant_extra_phases(game.state, ["combat"]) == ["combat"]
        # Both attacked and so both are tapped; untapping is what isolates the
        # requirement from "if able" and lets the two be compared at all.
        for oid in (goaded, flagged):
            untap_permanent(game.state, oid)
        pass_until(
            game,
            lambda g: g.state.extra_phases_taken >= 1
            and g.state.step is Step.DECLARE_ATTACKERS,
        )
        assert game.state.step is Step.DECLARE_ATTACKERS, "reached the second combat"
        assert combat_mod.attack_required(game.state, goaded), "re-armed"
        assert not combat_mod.attack_required(game.state, flagged), "spent"
        assert combat_mod.unmet_attack_requirements(game.state) == [goaded]
        assert not can_finish(game), "the second combat is compelled too"


class TestTheDefenderRestriction:
    def test_the_goader_drops_out_and_the_others_do_not(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [2], (
            "player 0 goaded it, so it must attack somebody else if it can"
        )

    def test_the_predicate_is_asked_per_pair(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        assert combat_mod.attack_target_forbidden(game.state, bear, 0)
        assert not combat_mod.attack_target_forbidden(game.state, bear, 2)

    def test_an_ungoaded_creature_beside_it_is_unrestricted(self, builder):
        """The mark is on one creature, not on its controller's whole team."""
        game = position(builder, theirs=(BEAR, BEAR))
        goaded, free = sorted(
            o for o in game.state.battlefield if game.state.objects[o].def_id == BEAR
        )
        goad_creature(game.state, goaded, 0)
        to_declare_attackers(game)
        assert defenders_offered(game, goaded) == [2]
        assert defenders_offered(game, free) == [0, 2]

    def test_add_attacker_refuses_the_goader(self, builder):
        """An action legality offers and `add_attacker` then refuses is a
        declaration that cannot be completed, so both read one predicate."""
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        to_declare_attackers(game)
        assert not combat_mod.add_attacker(game.state, bear, 0)
        assert combat_mod.add_attacker(game.state, bear, 2)


class TestItReachesPlaneswalkers:
    """The opposite answer from `cant_attack_player`, on purpose.

    "Creatures can't attack you" is about being attacked, and attacking a
    planeswalker its controller is not attacking them (506.2) -- the Ghostly
    Prison ruling. "Attacks a player other than you if able" is about where the
    attack is aimed, and the goader's planeswalker is the goader. Read the other
    way, every goad on a board with a walker on it could be dodged while the log
    said the requirement had been met.
    """

    def test_the_goaders_own_walker_is_not_offered(self, builder):
        game = position(builder, mine=(WALKER,))
        bear = only_oid(game, BEAR, 1)
        walker = only_oid(game, WALKER, 0)
        goad_creature(game.state, bear, 0)
        to_declare_attackers(game)
        assert walker not in walkers_offered(game, bear)
        assert not combat_mod.add_attacker(game.state, bear, 0, permanent=walker)

    def test_a_third_partys_walker_is_offered(self, builder):
        game = position(builder, mine=(WALKER,), lends=(WALKER,))
        bear = only_oid(game, BEAR, 1)
        theirs = only_oid(game, WALKER, 2)
        goad_creature(game.state, bear, 0)
        to_declare_attackers(game)
        assert walkers_offered(game, bear) == [theirs]

    def test_a_third_partys_walker_is_the_alternative_that_bites(self, builder):
        """"If able" has to count both attack kinds. With player 2 protected as a
        *player* but their walker still attackable, the goad restriction is live:
        there is somewhere else to swing, so the goader stays off limits."""
        game = position(builder, lends=(WALKER,))
        bear = only_oid(game, BEAR, 1)
        theirs = only_oid(game, WALKER, 2)
        goad_creature(game.state, bear, 0)
        restrict_attack(game.state, 1, 2, "this_turn")
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == []
        assert walkers_offered(game, bear) == [theirs]
        assert combat_mod.can_attack(game.state, bear), (
            "the walker keeps it a legal attacker"
        )

    def test_the_goaders_walker_alone_is_attackable(self, builder):
        """The escape, on the planeswalker side: with only the goader left, their
        planeswalker is a legal attack like their seat is."""
        game = position(builder, players=2, mine=(WALKER,))
        bear = only_oid(game, BEAR, 1)
        walker = only_oid(game, WALKER, 0)
        goad_creature(game.state, bear, 0)
        to_declare_attackers(game)
        assert walkers_offered(game, bear) == [walker]


class TestTheIfAbleEscapes:
    def test_a_creature_that_cannot_attack_owes_nothing(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        game.state.objects[bear].tapped = True
        goad_creature(game.state, bear, 0)
        assert not combat_mod.attack_required(game.state, bear)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == []
        assert can_finish(game)

    def test_a_summoning_sick_creature_owes_nothing(self, builder):
        game = builder(players=3)
        game.battlefield(1, [BEAR], sick=True)
        game = game.active(1).step(Step.PRECOMBAT_MAIN).build()
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        assert not combat_mod.attack_required(game.state, bear)

    def test_the_step_does_not_deadlock(self, builder):
        """The trap `cant_attack_player` hit: if a compelled creature that cannot
        attack still counted as an unmet requirement, "Done attacking" would be
        withheld with no `ADD_ATTACKER` to offer -- a step with no legal action
        in it at all."""
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        game.state.objects[bear].tapped = True
        goad_creature(game.state, bear, 0)
        pass_until(game, lambda g: g.state.turn >= 3)
        assert game.state.turn >= 3, "the turn ran to completion"

    def test_with_only_the_goader_left_it_attacks_the_goader(self, builder):
        game = position(builder, players=2)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [0], (
            '"attacks a player other than you **if able**" -- and it is not able'
        )
        assert combat_mod.attack_required(game.state, bear), "still compelled"
        assert combat_mod.add_attacker(game.state, bear, 0)

    def test_the_only_other_defender_being_forbidden_frees_the_goader(self, builder):
        """The two restrictions compose the right way round: with player 2 out of
        reach the goaded creature is not stranded, it attacks the goader."""
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        restrict_attack(game.state, 1, 2, "this_turn")
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [0]
        assert combat_mod.can_attack(game.state, bear)

    def test_every_defender_forbidden_is_still_no_attack(self, builder):
        """Goad never makes a creature *able*: with both seats closed by attack
        restrictions there is nothing to declare, and the requirement lapses."""
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        restrict_attack(game.state, 1, 0, "this_turn")
        restrict_attack(game.state, 1, 2, "this_turn")
        assert not combat_mod.can_attack(game.state, bear)
        assert not combat_mod.attack_required(game.state, bear)


class TestTheClock:
    """"Until **your** next turn" -- detain's clock, keyed to a player."""

    def test_it_ends_in_the_goading_players_untap_step(self, builder):
        game = position(builder, active=0)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.objects[bear].goaded_by == {0}, "player 1's turn: still on"
        pass_until(game, lambda g: g.state.active_player == 0 and g.state.turn >= 4)
        assert game.state.objects[bear].goaded_by == set(), "player 0 untapped"

    def test_somebody_elses_untap_step_does_not_clear_it(self, builder):
        game = position(builder, active=0)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        pass_until(game, lambda g: g.state.active_player == 2)
        assert game.state.objects[bear].goaded_by == {0}

    def test_it_survives_the_turn_it_was_placed_in(self, builder):
        """Not a `TempEffect`: cleanup would wipe it before the combat it names.
        A goad is placed on *your* turn and owed on *theirs*, so an
        until-end-of-turn effect would be a card that does nothing at all."""
        game = position(builder, active=0)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        pass_until(game, lambda g: g.state.active_player == 1)
        assert game.state.objects[bear].goaded_by == {0}
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == [bear], (
            "it reached the combat it names"
        )

    def test_an_eliminated_goader_takes_its_goad_with_it(self, builder):
        """A player who has left never untaps again, so nothing else would ever
        clear the mark: the creature would be compelled for the rest of the game
        and restricted from a seat `alive()` no longer offers, which is an "if
        able" escape that can never fire."""
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        game.state.players[0].life = 0
        sba.run(game.state)
        assert game.state.objects[bear].goaded_by == set()
        assert not combat_mod.attack_required(game.state, bear)

    def test_leaving_the_battlefield_clears_the_mark(self, builder):
        """400.7: a permanent that left and came back is a new object, and it is
        not the creature anybody goaded."""
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        move_object(game.state, bear, Zone.HAND)
        assert game.state.objects[bear].goaded_by == set()


class TestTwoGoaders:
    def test_both_are_recorded(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        assert goad_creature(game.state, bear, 0)
        assert goad_creature(game.state, bear, 2)
        assert game.state.objects[bear].goaded_by == {0, 2}

    def test_a_creature_goaded_by_everybody_may_attack_anybody(self, builder):
        """"If able" again, with both seats goading: there is no third player to
        attack, so neither restriction bites and the compulsion still stands."""
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        goad_creature(game.state, bear, 2)
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [0, 2]
        assert combat_mod.unmet_attack_requirements(game.state) == [bear]

    def test_one_clock_expiring_leaves_the_other_standing(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        goad_creature(game.state, bear, 2)
        clear_goad(game.state, 0)
        assert game.state.objects[bear].goaded_by == {2}
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [0], "only player 2 is off limits now"

    def test_the_same_goad_twice_is_one_mark(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        assert goad_creature(game.state, bear, 0)
        assert not goad_creature(game.state, bear, 0)
        assert game.state.objects[bear].goaded_by == {0}


class TestThePrimitiveRefusesWhatCannotBite:
    def test_a_creature_off_the_battlefield_is_not_goaded(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        move_object(game.state, bear, Zone.GRAVEYARD)
        assert not goad_creature(game.state, bear, 0)

    def test_an_eliminated_goader_goads_nobody(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        game.state.players[0].has_lost = True
        assert not goad_creature(game.state, bear, 0)

    def test_you_cannot_goad_your_own_creature_for_yourself(self, builder):
        """A creature cannot attack its own controller, so "attacks a player
        other than you" would be vacuous and the compulsion would be a Bident
        with no author. Goading a creature you do *not* control is the normal
        case and is not this."""
        game = position(builder, mine=(BEAR,), active=0)
        mine = only_oid(game, BEAR, 0)
        assert not goad_creature(game.state, mine, 0)


class TestTheSorceryForm:
    """Taunt from the Rampart's first sentence: "Goad all creatures your
    opponents control." A resolving sorcery, so there is no permanent left to own
    the effect and the set is fixed when it resolves."""

    def test_it_goads_every_opponents_creature(self, builder):
        game = position(builder, mine=(BEAR,), active=0, hand=(GOADER,))
        cast(game, GOADER)
        theirs = only_oid(game, BEAR, 1)
        mine = only_oid(game, BEAR, 0)
        assert game.state.objects[theirs].goaded_by == {0}
        assert game.state.objects[mine].goaded_by == set(), "your own team is not goaded"

    def test_the_set_is_fixed_when_it_resolves(self, builder):
        """A mark on each creature, not a continuous effect: unlike `cant_block`'s
        `all_creatures` form there is no printed goad that catches latecomers, and
        701.38a goads the creatures named when the spell resolves."""
        game = position(builder, active=0, hand=(GOADER,))
        cast(game, GOADER)
        latecomer = new_object(game.state, BEAR, owner=1, zone=Zone.BATTLEFIELD)
        game.state.battlefield.append(latecomer.oid)
        assert latecomer.goaded_by == set(), (
            "a creature that entered afterwards was not one of 'those creatures'"
        )

    def test_it_then_compels_and_restricts_on_their_turn(self, builder):
        game = position(builder, active=0, hand=(GOADER,))
        cast(game, GOADER)
        theirs = only_oid(game, BEAR, 1)
        pass_until(game, lambda g: g.state.active_player == 1)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == [theirs]
        assert defenders_offered(game, theirs) == [2]


def probe(effect: dict) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "x",
                "mana_cost": "{R}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )
    )


class TestTheLoaderGuardsIt:
    def test_a_missing_objects_is_refused(self):
        """A goad with no selector goads nobody: the spell resolves, the log says
        nothing, and every creature attacks as it pleases."""
        with pytest.raises(DslError, match="goad needs 'objects'"):
            probe({"op": "goad"})

    def test_a_duration_is_refused(self):
        """701.38a has exactly one clock and it is a *player*. Accepting a
        duration would invite `this_turn`, which is `must_attack` -- a strictly
        weaker card that looks identical in a one-combat test."""
        with pytest.raises(DslError, match="goad takes no 'duration'"):
            probe(
                {
                    "op": "goad",
                    "objects": {"controller": "opponent", "types": ["Creature"]},
                    "duration": "this_turn",
                }
            )

    def test_an_unknown_player_spec_is_refused(self):
        with pytest.raises(DslError, match="unknown player spec"):
            probe(
                {
                    "op": "goad",
                    "objects": {"controller": "opponent", "types": ["Creature"]},
                    "player": "the_monarch",
                }
            )

    def test_a_target_the_card_never_declared_is_refused(self):
        with pytest.raises(DslError, match="does not declare"):
            probe(
                {
                    "op": "goad",
                    "objects": {"controller": "opponent", "types": ["Creature"]},
                    "player": {"target": "t1"},
                }
            )

    def test_the_witness_shape_compiles(self, registry):
        assert [e["op"] for e in registry.get(GOADER).spell_effects] == ["goad"]
