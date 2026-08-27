""""Inklings can't attack you or planeswalkers you control": a wall, not a lock.

Rule 508.1c is the rule -- as attackers are declared, "the declaration is
illegal if any restrictions aren't obeyed" -- and the witness is **Combat
Calligrapher**, whose middle line is a prohibition with *three* things in it at
once: a set of creatures picked out by a printed characteristic, a defending
seat, and a duration of "for as long as this permanent is on the battlefield".
The engine had each of those separately and no shape that carried all three:

- `cant_attack` (Stormtide Leviathan) filters the attacking creature and takes
  **no defender at all**. Written on Combat Calligrapher it would stop Inklings
  attacking *anybody* -- strictly stronger than the printed line, and it would
  switch off the card's own third line, which hands each opponent an Inkling
  expressly so that they keep swinging at each other. That counterfactual is
  `t_ink_lock`, and it is asserted against below rather than argued about.
- the `cant_attack_player` **op** is the defender-scoped shape and carries no
  creature filter whatsoever, being keyed on the pair of *seats*. Its `duration`
  is required precisely because it is a resolving one-shot with no permanent to
  hang off, so it can never be a creature's continuous ability.
- `attack_tax` (Propaganda) is defender-scoped *and* filtered, and it prices an
  attack instead of forbidding one. A tax that cannot be paid is a prohibition,
  but a tax that can is a different card.

So this is `attack_tax` with the price taken out: a `cant_attack_you` static
whose `affects` says which creatures are stopped and whose own controller is the
seat they are stopped from attacking. It is read at
`combat.attack_target_forbidden` -- the per-attacker/per-defender seam
`cant_attack_player` built and goad reused -- so legality, `add_attacker` and
the RL action mask cannot disagree about it.

Four things are worth pinning, and each is a way this could be quietly wrong:

1. It **narrows** rather than removes. An Inkling still attacks every other
   seat, which is the whole difference from `cant_attack`.
2. It **reaches planeswalkers**, and that is the opposite answer from
   `cant_attack_player`, which exempts them. Not a rule the engine picks: the
   two printed sentences differ. "You can't attack that player this turn" is
   506.2's reading -- attacking somebody's planeswalker is not attacking them --
   and Combat Calligrapher's sentence names the walkers out loud. Goad already
   made the same divergence, in the same predicate, for the same reason.
3. It **points one way**, and the way it points is at the seat the permanent
   sits under. The Calligrapher's controller's own Inklings attack everyone else
   as normal.
4. It lives **exactly as long as the permanent**, and a creature it leaves with
   nowhere to attack is not a legal attacker at all -- which the declare
   attackers step has to survive without a deadlock, since a creature compelled
   to attack owes nothing it cannot legally do.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import combat as combat_mod
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.primitives import restrict_attack
from automtg.engine.zones import move_object
from tests.conftest import _default_answer, only_oid, pass_until

BEAR = "t_bear"  # 2/2 Bear -- the creature the filter does not name
INKLING = "t_inkling"  # 2/1 Inkling with flying
WALL = "t_calligrapher"  # "Inklings can't attack you or planeswalkers you control."
LOCK = "t_ink_lock"  # the counterfactual: "Inklings can't attack." (`cant_attack`)
WALKER = "t_walker"  # loyalty 4


def position(builder, *, players=3, mine=(INKLING, BEAR), theirs=(WALL,), third=(), active=0):
    """``mine`` under player 0, ``theirs`` under player 1, ``third`` under player 2.

    Built from the untap step and advanced, so the position starts at the active
    player's first priority with the turn's own machinery having run.
    """
    b = builder(players=players)
    if mine:
        b.battlefield(0, list(mine))
    if theirs:
        b.battlefield(1, list(theirs))
    if third and players > 2:
        b.battlefield(2, list(third))
    return b.active(active).step(Step.UNTAP).build()


def to_declare_attackers(game, limit: int = 60):
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


class TestItStopsOnlyTheSeatItSitsUnder:
    def test_without_it_every_opponent_is_offered(self, builder):
        game = position(builder, theirs=())
        inkling = only_oid(game, INKLING, 0)
        to_declare_attackers(game)
        assert defenders_offered(game, inkling) == [1, 2]

    def test_the_protected_seat_is_withheld(self, builder):
        game = position(builder)
        inkling = only_oid(game, INKLING, 0)
        to_declare_attackers(game)
        assert defenders_offered(game, inkling) == [2], (
            "player 1 is behind their own wall; player 2 is not"
        )

    def test_a_creature_the_filter_does_not_name_is_untouched(self, builder):
        """The filter is the whole sentence. A Bear is not an Inkling, and a
        wall that stopped it would be a strictly better card with no line on it
        saying so."""
        game = position(builder)
        bear = only_oid(game, BEAR, 0)
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [1, 2]

    def test_a_second_wall_closes_a_second_seat(self, builder):
        game = position(builder, third=(WALL,))
        inkling = only_oid(game, INKLING, 0)
        bear = only_oid(game, BEAR, 0)
        to_declare_attackers(game)
        assert defenders_offered(game, inkling) == []
        assert defenders_offered(game, bear) == [1, 2], "each wall closes its own seat"

    def test_add_attacker_refuses_what_legality_withheld(self, builder):
        """The seam exists so the two cannot disagree: an attack the action list
        never offered must also be refused if it is asked for directly."""
        game = position(builder)
        inkling = only_oid(game, INKLING, 0)
        to_declare_attackers(game)
        assert not combat_mod.add_attacker(game.state, inkling, 1)
        assert combat_mod.add_attacker(game.state, inkling, 2)


class TestItReachesPlaneswalkers:
    def test_the_walker_behind_the_wall_is_not_offered(self, builder):
        """"…or planeswalkers you control" is the second half of the printed
        line, and a planeswalker's controller *is* the defending player (506.2),
        so the seat test covers the walker as well as the chair."""
        game = position(builder, theirs=(WALL, WALKER))
        inkling = only_oid(game, INKLING, 0)
        to_declare_attackers(game)
        assert defenders_offered(game, inkling) == [2]
        assert walkers_offered(game, inkling) == []

    def test_the_same_walker_is_open_to_a_creature_the_wall_does_not_name(self, builder):
        game = position(builder, theirs=(WALL, WALKER))
        bear = only_oid(game, BEAR, 0)
        walker = only_oid(game, WALKER, 1)
        to_declare_attackers(game)
        assert walkers_offered(game, bear) == [walker]

    def test_a_walker_no_wall_stands_in_front_of_is_still_offered(self, builder):
        game = position(builder, third=(WALKER,))
        inkling = only_oid(game, INKLING, 0)
        walker = only_oid(game, WALKER, 2)
        to_declare_attackers(game)
        assert walkers_offered(game, inkling) == [walker]

    def test_the_per_seat_op_still_exempts_planeswalkers(self, builder):
        """The divergence, pinned from both sides. `cant_attack_player` says
        "that player can't attack you" and 506.2 makes attacking their
        planeswalker a different thing -- the Ghostly Prison ruling -- so
        widening the static must not have widened the op with it."""
        game = position(builder, theirs=(WALKER,))
        bear = only_oid(game, BEAR, 0)
        walker = only_oid(game, WALKER, 1)
        restrict_attack(game.state, 0, 1, "this_turn")
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [2]
        assert walkers_offered(game, bear) == [walker]


class TestItPointsOneWay:
    def test_the_wall_does_not_stop_its_own_controllers_inklings(self, builder):
        """The seat is the permanent's controller's, so an Inkling *they*
        control is stopped from attacking a player it could never attack anyway
        -- and is free everywhere else. A wall read as "Inklings can't attack"
        would ground their own Inklings too."""
        game = position(builder, mine=(), theirs=(WALL, INKLING), active=1)
        inkling = only_oid(game, INKLING, 1)
        to_declare_attackers(game)
        assert defenders_offered(game, inkling) == [0, 2]

    def test_it_says_nothing_about_attacking_the_other_way(self, builder):
        """Player 0's Inkling cannot attack player 1. Player 1's Bear attacking
        player 0 is a different sentence, and nobody has printed it."""
        game = position(builder, mine=(WALL,), theirs=(BEAR,), active=1)
        bear = only_oid(game, BEAR, 1)
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [0, 2]


class TestItIsNotTheLockCantAttackWouldHaveBeen:
    def test_the_cant_attack_version_grounds_the_inkling_entirely(self, builder):
        """`t_ink_lock` is the card the DSL could already write. It is a
        different, strictly stronger card, and this is the assertion that says
        so."""
        game = position(builder, theirs=(LOCK,))
        inkling = only_oid(game, INKLING, 0)
        to_declare_attackers(game)
        assert not combat_mod.can_attack(game.state, inkling)
        assert attack_actions(game, inkling) == []

    def test_the_defender_scoped_version_leaves_the_other_seats_open(self, builder):
        game = position(builder)
        inkling = only_oid(game, INKLING, 0)
        to_declare_attackers(game)
        assert combat_mod.can_attack(game.state, inkling)
        assert defenders_offered(game, inkling) == [2]


class TestACreatureWithNowhereLeftToAttack:
    """Two players and one wall is the boundary: narrowing the choice to nothing
    is the same as removing it, and `can_attack` has to notice."""

    def test_it_is_not_a_legal_attacker(self, builder):
        game = position(builder, players=2, third=())
        inkling = only_oid(game, INKLING, 0)
        bear = only_oid(game, BEAR, 0)
        assert not combat_mod.can_attack(game.state, inkling)
        assert combat_mod.legal_attackers(game.state) == [bear]

    def test_a_compelled_creature_does_not_deadlock_the_step(self, builder):
        """"…if able" is the whole second half. A creature required to attack
        with every defender forbidden owes nothing -- and if `can_attack` said
        otherwise, legality would withhold "Done attacking" with no ADD_ATTACKER
        left to offer, which is a step with no legal action in it at all."""
        game = position(builder, players=2, third=())
        inkling = only_oid(game, INKLING, 0)
        game.state.objects[inkling].must_attack = "this_turn"
        game.state.objects[inkling].must_attack_turn = game.state.turn
        assert combat_mod.unmet_attack_requirements(game.state) == []
        assert attack_actions(game, inkling) == []
        assert any(
            a.kind is ActionKind.FINISH_DECLARATION for a in game.legal_actions()
        ), "'Done attacking' is still offered"
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.turn >= 2, "the turn ran to completion"

    def test_the_requirement_is_live_again_once_the_wall_leaves(self, builder):
        game = position(builder, players=2, third=())
        inkling = only_oid(game, INKLING, 0)
        wall = only_oid(game, WALL, 1)
        game.state.objects[inkling].must_attack = "this_turn"
        game.state.objects[inkling].must_attack_turn = game.state.turn
        assert combat_mod.unmet_attack_requirements(game.state) == []
        move_object(game.state, wall, Zone.GRAVEYARD)
        assert combat_mod.unmet_attack_requirements(game.state) == [inkling]

    def test_the_declaration_step_needs_no_attacker_to_survive(self, builder):
        """`position` stops at the first decision of the game. With its only
        creature walled in, player 0's turn holds none at all: the step is
        skipped rather than offered with no legal action in it."""
        game = position(builder, players=2, mine=(INKLING,), third=())
        assert (game.state.turn, game.state.active_player) == (2, 1)


class TestItLivesExactlyAsLongAsThePermanent:
    def test_the_seat_reopens_the_moment_the_source_leaves(self, builder):
        """Read live off the battlefield rather than written onto anything, so
        it wears off with its source *inside* a declaration -- which is what
        makes it a static and not the `cant_attack_player` op with a third
        duration."""
        game = position(builder)
        inkling = only_oid(game, INKLING, 0)
        wall = only_oid(game, WALL, 1)
        to_declare_attackers(game)
        assert defenders_offered(game, inkling) == [2]
        move_object(game.state, wall, Zone.GRAVEYARD)
        assert defenders_offered(game, inkling) == [1, 2]

    def test_it_is_gone_next_turn_too(self, builder):
        game = position(builder)
        inkling = only_oid(game, INKLING, 0)
        wall = only_oid(game, WALL, 1)
        move_object(game.state, wall, Zone.GRAVEYARD)
        pass_until(game, lambda g: g.state.turn >= 4 and g.state.step is Step.DECLARE_ATTACKERS)
        assert game.state.active_player == 0, "back round to the wall's victim"
        assert defenders_offered(game, inkling) == [1, 2]


def probe(ability: dict) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "x",
                "mana_cost": "{W}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [{"kind": "static", "text": "x", **ability}],
            }
        )
    )


class TestTheLoaderGuardsIt:
    def test_a_wall_with_no_filter_is_refused(self):
        """`characteristics._matches` reads a missing filter as "matches
        nothing", so a filterless wall is a printed restriction that restricts
        nobody: it loads clean, shows on the card and never fires."""
        with pytest.raises(DslError, match="cant_attack_you needs an 'affects'"):
            probe({"effect": "cant_attack_you"})

    def test_a_filter_that_is_not_a_printed_characteristic_is_refused(self):
        with pytest.raises(DslError, match="printed characteristics"):
            probe({"effect": "cant_attack_you", "affects": {"subtypes": ["Inkling"], "hexproof": True}})

    def test_it_takes_no_cost_the_way_a_tax_does(self):
        """The wall and the toll are deliberately two effects. One with a price
        on it is `attack_tax`, and accepting a `cost` here would be a second,
        silent spelling of it that nothing charges."""
        with pytest.raises(DslError, match="cost"):
            probe(
                {
                    "effect": "cant_attack_you",
                    "affects": {"controller": "any", "subtypes": ["Inkling"]},
                    "cost": {"mana": "{2}"},
                }
            )

    def test_the_witness_compiles(self, registry):
        card = registry.get(WALL)
        static = card.abilities[0].static
        assert static["effect"] == "cant_attack_you"
        assert static["affects"]["subtypes"] == ["Inkling"]
