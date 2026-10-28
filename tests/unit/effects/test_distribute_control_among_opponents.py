"""`distribute_control_among_opponents` -- "for each of those permanents, choose a
different opponent. Each opponent gains control of the permanent for which they
were chosen."

Dack Fayden, Helping Hand is the witness, and the whole card is end to end at
the bottom of this file: reveal until X creature cards (X = the number of
opponents you have), put them onto the battlefield, shuffle, goad them for the
rest of the game, then deal one to each opponent.

The rules argument is a **pairing**. `gain_control` gives a pool to one player,
so a `for_each` around it either hands everything to the same seat or has no
way to say "a *different* one"; `rotate_control` passes boards one seat round
the table with nothing chosen. Here the controller chooses, once per
permanent, among the opponents not yet chosen, which reaches every pairing --
and with fewer permanents than opponents, the seats never picked get nothing.
Every choice is made before any control moves, and each move is permanent and
goes through `change_control` (302.6, 506.4).

The order of Dack's lines is the second claim: the goad comes first, so the
mark is Dack's controller's, and each opponent's new creature must attack a
player other than him (701.15a) for the rest of the game.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine import sba
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import action_for_card, oids_of, only_oid, pass_until
from tests.unit.combat.test_goad import defenders_offered, to_declare_attackers

BEAR = "t_bear"
DACK = "dack_fayden_helping_hand"
SPEC = {"op": "distribute_control_among_opponents", "objects": {"binding": "given"}}


def a_table(builder, players: int = 4, bears: int = 3):
    """Seat 0 controls ``bears`` bears; nobody else has anything."""
    game = (
        builder(players=players)
        .battlefield(0, [BEAR] * bears)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    return game, sorted(oids_of(game, BEAR))


def distribute(game, oids, answers=(), controller: int = 0):
    """Run the op over ``oids``; ``answers`` are option indices, in order."""
    ctx = EffectContext(state=game.state, controller=controller)
    ctx.bindings["given"] = list(oids)
    gen = execute(ctx, [SPEC])
    asked = []
    queue = list(answers)
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            decision = gen.send([queue.pop(0) if queue else 0])
    except StopIteration:
        pass
    return asked


def controllers(game, oids) -> list[int]:
    return [game.state.objects[o].controller for o in oids]


class TestEachOpponentGetsADifferentOne:
    def test_three_permanents_three_opponents(self, builder):
        game, bears = a_table(builder)
        distribute(game, bears)
        assert sorted(controllers(game, bears)) == [1, 2, 3]

    def test_the_controller_picks_the_pairing(self, builder):
        """Option indices into the seats still free: 3 of [1,2,3], then 1 of [1,2]."""
        game, bears = a_table(builder)
        distribute(game, bears, answers=[2, 0])
        assert controllers(game, bears) == [3, 1, 2]

    def test_each_question_offers_only_the_seats_still_free(self, builder):
        game, bears = a_table(builder)
        asked = distribute(game, bears, answers=[1, 1])
        assert [d.kind for d in asked] == [DecisionKind.CHOOSE_PLAYER] * 2
        assert all(d.player == 0 for d in asked), "the controller chooses"
        assert [[o.value for o in d.options] for d in asked] == [[1, 2, 3], [1, 3]]

    def test_the_last_one_is_not_asked(self, builder):
        """One seat left is no choice -- `ask_player`'s own short-circuit."""
        game, bears = a_table(builder)
        assert len(distribute(game, bears)) == 2


class TestFewerPermanentsThanOpponents:
    def test_some_opponents_get_nothing(self, builder):
        game, bears = a_table(builder, bears=1)
        asked = distribute(game, bears, answers=[2])
        assert len(asked) == 1
        assert controllers(game, bears) == [3]

    def test_none_is_nothing(self, builder):
        game, _ = a_table(builder, bears=0)
        assert distribute(game, []) == []


class TestEdges:
    def test_more_permanents_than_opponents_leaves_the_rest(self, builder):
        """No different opponent is left for the third (609.3)."""
        game, bears = a_table(builder, players=3)
        distribute(game, bears)
        assert sorted(controllers(game, bears)) == [0, 1, 2]
        assert controllers(game, bears)[2] == 0

    def test_an_eliminated_opponent_is_not_offered(self, builder):
        game, bears = a_table(builder, bears=2)
        game.state.players[2].has_lost = True
        asked = distribute(game, bears)
        assert [[o.value for o in d.options] for d in asked] == [[1, 3]]
        assert sorted(controllers(game, bears)) == [1, 3]

    def test_a_permanent_gone_from_the_battlefield_is_skipped(self, builder):
        game, bears = a_table(builder, bears=2)
        game.state.objects[bears[0]].zone = Zone.GRAVEYARD
        game.state.battlefield.remove(bears[0])
        distribute(game, bears)
        assert game.state.objects[bears[1]].controller == 1, "the first free seat"

    def test_every_choice_is_made_before_any_control_moves(self, builder):
        game, bears = a_table(builder)
        ctx = EffectContext(state=game.state, controller=0)
        ctx.bindings["given"] = list(bears)
        gen = execute(ctx, [SPEC])
        next(gen)
        gen.send([0])
        assert controllers(game, bears) == [0, 0, 0], "asked twice, nothing moved yet"

    def test_the_change_is_permanent_and_the_creature_sick(self, builder):
        """302.6: not under its new controller since their turn began."""
        game, bears = a_table(builder, bears=1)
        distribute(game, bears)
        bear = game.state.objects[bears[0]]
        assert bear.until_eot == []
        assert bear.summoning_sick(game.state.turn)


class TestTheLoader:
    def test_objects_are_required(self):
        card = {
            "id": "t_bad_split",
            "name": "Test Bad Split",
            "oracle_text": "Split.",
            "mana_cost": "{W}",
            "types": ["Sorcery"],
            "spell_effects": [{"op": "distribute_control_among_opponents"}],
        }
        with pytest.raises(DslError, match="distribute_control_among_opponents needs 'objects'"):
            compile_card(CardModel.model_validate(card))


def dack_table(builder, players: int, library: list[str]):
    """Player 0 holds Dack with six Plains; ``library`` is the exact top."""
    b = (
        builder(players=players)
        .hand(0, [DACK])
        .battlefield(0, ["plains"] * 6)
        .library(0, library)
        .step(Step.PRECOMBAT_MAIN)
    )
    return b.build()


def cast_dack(game, picks=()) -> list:
    """Cast Dack and resolve him and his trigger; ``picks`` answer each
    CHOOSE_PLAYER by option index. Returns the questions asked."""
    game.apply(action_for_card(game, ActionKind.CAST, DACK))
    queue = list(picks)
    asked = []
    for _ in range(200):
        decision = game.pending()
        if (
            not game.state.stack
            and not game.state.pending_triggers
            and decision is not None
            and decision.kind is DecisionKind.PRIORITY
            and only_on_battlefield(game)
        ):
            return asked
        if decision is None:
            game._advance()
            continue
        if decision.kind is DecisionKind.CHOOSE_PLAYER:
            asked.append(decision)
            pick = queue.pop(0) if queue else 0
            game.apply(next(a for a in game.legal_actions() if a.choice == pick))
            continue
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
    raise AssertionError("Dack never finished resolving")


def only_on_battlefield(game) -> bool:
    return any(game.state.objects[o].def_id == DACK for o in game.state.battlefield)


class TestDackFaydenEndToEnd:
    """Four players, so X is 3: reveal until three creature cards."""

    LIBRARY = ["forest", BEAR, "forest", BEAR, "island", BEAR, "forest", "island"]

    def test_x_is_the_number_of_opponents(self, builder):
        game = dack_table(builder, 4, self.LIBRARY)
        cast_dack(game)
        assert len(oids_of(game, BEAR)) == 3
        assert all(game.state.objects[o].zone is Zone.BATTLEFIELD for o in oids_of(game, BEAR))
        # Eight cards, three onto the battlefield, the rest shuffled back in.
        assert len(game.state.players[0].library) == 5

    def test_each_opponent_gets_one_of_the_controllers_choosing(self, builder):
        game = dack_table(builder, 4, self.LIBRARY)
        asked = cast_dack(game, picks=[2, 1])
        assert [d.player for d in asked] == [0, 0]
        assert [[o.value for o in d.options] for d in asked] == [[1, 2, 3], [1, 2]]
        first, second, third = sorted(oids_of(game, BEAR))
        assert controllers(game, [first, second, third]) == [3, 2, 1]
        assert all(game.state.objects[o].owner == 0 for o in (first, second, third))

    def test_they_are_goaded_by_dacks_controller_for_the_rest_of_the_game(self, builder):
        game = dack_table(builder, 4, self.LIBRARY)
        cast_dack(game)
        for oid in oids_of(game, BEAR):
            assert game.state.objects[oid].goaded_by == {0}
            assert game.state.objects[oid].goaded_permanently_by == {0}
        pass_until(game, lambda g: g.state.active_player == 0 and g.state.turn >= 5)
        assert all(game.state.objects[o].goaded_by == {0} for o in oids_of(game, BEAR)), (
            "Dack's controller untapped and they are still goaded"
        )

    def test_the_new_controllers_creature_attacks_someone_else(self, builder):
        game = dack_table(builder, 4, self.LIBRARY)
        cast_dack(game)
        theirs = next(o for o in oids_of(game, BEAR) if game.state.objects[o].controller == 1)
        pass_until(game, lambda g: g.state.active_player == 1)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == [theirs]
        assert defenders_offered(game, theirs) == [2, 3], "never Dack's controller"

    def test_fewer_creatures_than_opponents(self, builder):
        """The library holds one creature: one opponent of three gets it, the
        controller choosing which, and the other two get nothing."""
        game = dack_table(builder, 4, ["forest", BEAR, "island"])
        asked = cast_dack(game, picks=[1])
        bear = only_oid(game, BEAR)
        assert len(asked) == 1
        assert game.state.objects[bear].controller == 2
        assert game.state.objects[bear].goaded_by == {0}

    def test_three_players_two_creatures(self, builder):
        game = dack_table(builder, 3, [BEAR, BEAR, BEAR, "forest"])
        cast_dack(game)
        on_field = [o for o in oids_of(game, BEAR) if game.state.objects[o].zone is Zone.BATTLEFIELD]
        assert len(on_field) == 2, "X is 2 at a three-player table"
        assert sorted(controllers(game, on_field)) == [1, 2]

    def test_when_dacks_controller_leaves_their_creatures_go_with_them(self, builder):
        """800.4a: the revealed creatures are Dack's controller's, so they leave
        the game with that player, goad and all."""
        game = dack_table(builder, 4, self.LIBRARY)
        cast_dack(game)
        game.state.players[0].life = 0
        sba.run(game.state)
        assert all(
            game.state.objects[o].zone is not Zone.BATTLEFIELD for o in oids_of(game, BEAR)
        )
