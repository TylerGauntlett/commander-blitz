"""Attack *requirements* — the first thing on a card that removes an option.

    Trench Behemoth — "Landfall — Whenever a land you control enters, target
    creature an opponent controls attacks during its controller's next combat
    phase if able."

Every other way a card touches combat takes something away: `tap`, `freeze`,
`skip_untap`, `defender`, protection. All prohibitions. This one takes away the
option *not* to attack, and nothing in the engine could express that — which is
why the gap record was right that it cannot be spelled as the negation of any
existing op.

Two things make it awkward, and both are asserted here.

**"If able" is half the rule.** A requirement never makes an illegal attack
legal. A tapped or summoning-sick creature owes nothing, and if the requirement
did not know that, the declaration would deadlock: there is no action for
"refuse to attack", so legality enforces this by withholding *Done attacking*.

**The duration is not "this turn".** Trench Behemoth's trigger fires on *your*
landfall and binds *their* combat, which has not happened yet and is usually a
different turn. So it cannot be a `TempEffect` — the cleanup step would wipe it
before the combat it names. It is a one-shot obligation that survives to the
controller's next declare-attackers and expires there whether or not it was met.
"""

from __future__ import annotations

from commanderblitz.engine.combat import attack_required, unmet_attack_requirements
from commanderblitz.engine.enums import ActionKind, DecisionKind
from tests.conftest import find_action, only_oid, pass_until


def to_attackers(game):
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )


def board(builder, *, tapped: bool = False, mine: list[str] | None = None):
    """Player 0 is active and holds the compelled creature."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4 + (mine or ["t_bear"]), tapped=tapped)
        .battlefield(1, ["t_dork"])
        .build()
    )
    return game


def compel(game, oid: int, duration: str = "next_combat") -> None:
    """Place the requirement directly -- the op is exercised through the card
    elsewhere; here the subject is the *rule*."""
    obj = game.state.objects[oid]
    obj.must_attack = duration
    obj.must_attack_turn = game.state.turn


class TestTheRequirementIsEnforced:
    def test_done_attacking_is_withheld_while_it_is_unmet(self, builder):
        game = board(builder)
        bear = only_oid(game, "t_bear")
        to_attackers(game)
        compel(game, bear)
        kinds = {a.kind for a in game.legal_actions()}
        assert ActionKind.ADD_ATTACKER in kinds
        assert ActionKind.FINISH_DECLARATION not in kinds, (
            "the player can decline to attack with a creature that must"
        )

    def test_attacking_with_it_releases_the_declaration(self, builder):
        game = board(builder)
        bear = only_oid(game, "t_bear")
        to_attackers(game)
        compel(game, bear)
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER)
        )
        assert any(
            a.kind is ActionKind.FINISH_DECLARATION for a in game.legal_actions()
        )

    def test_without_the_requirement_declining_is_always_available(self, builder):
        game = board(builder)
        to_attackers(game)
        assert any(
            a.kind is ActionKind.FINISH_DECLARATION for a in game.legal_actions()
        )


class TestIfAble:
    def test_a_tapped_creature_owes_nothing(self, builder):
        """Otherwise the declaration deadlocks: it cannot attack, and there is
        no action for refusing."""
        game = board(builder, tapped=True)
        bear = only_oid(game, "t_bear")
        to_attackers(game)
        compel(game, bear)
        assert not attack_required(game.state, bear)
        assert not unmet_attack_requirements(game.state)
        assert any(
            a.kind is ActionKind.FINISH_DECLARATION for a in game.legal_actions()
        )

    def test_a_defender_owes_nothing(self, builder):
        game = board(builder, mine=["t_wall"])
        wall = only_oid(game, "t_wall")
        to_attackers(game)
        compel(game, wall)
        assert not attack_required(game.state, wall)


class TestTheDuration:
    def test_this_turn_expires_with_the_turn(self, builder):
        game = board(builder)
        bear = only_oid(game, "t_bear")
        compel(game, bear, "this_turn")
        assert attack_required(game.state, bear), "placed this turn, so it applies now"
        game.state.turn += 1
        assert not attack_required(game.state, bear), (
            "a this-turn requirement outlived its turn"
        )

    def test_next_combat_survives_the_turn_boundary(self, builder):
        """The reason it is not a TempEffect. Trench Behemoth's trigger fires on
        your landfall and binds an opponent's combat, a turn or more later."""
        game = board(builder)
        bear = only_oid(game, "t_bear")
        compel(game, bear, "next_combat")
        game.state.turn += 1
        assert game.state.objects[bear].must_attack == "next_combat"

    def test_it_is_spent_once_attackers_are_locked_in(self, builder):
        """One-shot: it expires at the declaration whether or not it was met, or
        it would compel the following combat too."""
        game = board(builder)
        bear = only_oid(game, "t_bear")
        to_attackers(game)
        compel(game, bear)
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER)
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        assert game.state.objects[bear].must_attack is None

    def test_it_is_spent_even_when_it_could_not_be_met(self, builder):
        """"If able" means an unable creature owes nothing -- but the obligation
        is still one-shot, so it must not carry over to the next combat."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 4 + ["t_dork"])
            .battlefield(0, ["t_bear"], tapped=True)
            .battlefield(1, ["t_wall"])
            .build()
        )
        bear = only_oid(game, "t_bear")
        to_attackers(game)
        assert game.state.active_player == 0, "the compelled creature's controller"
        compel(game, bear)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        assert game.state.objects[bear].must_attack is None

    def test_another_players_declaration_does_not_spend_it(self, builder):
        """It is discharged at *its controller's* next combat, which is the
        whole meaning of "its controller's next combat phase"."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 4 + ["t_dork"])
            .battlefield(1, ["t_bear"])
            .build()
        )
        bear = only_oid(game, "t_bear", 1)
        compel(game, bear)
        to_attackers(game)
        assert game.state.active_player == 0, "player 0 declares first"
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        assert game.state.objects[bear].must_attack == "next_combat", (
            "an opponent's declaration spent a requirement that was not theirs"
        )
