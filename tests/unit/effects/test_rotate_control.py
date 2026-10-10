"""`rotate_control` -- "choose left or right; each player gains control of the
permanents of the next player in the chosen direction".

Aminatou, the Fateshifter's -6 is the witness: "Choose left or right. Each
player gains control of all nonland permanents other than Aminatou controlled
by the next player in the chosen direction."

The rules argument is **simultaneity**. The near miss is `for_each_player`
around `gain_control`, and it is wrong in a way that looks right at a glance:
the first player takes their neighbour's board, the next player's
`gain_control` then reads a neighbour who controls two boards and takes both,
and the rotation cascades until one seat holds everything. So the claims are
that every permanent moves exactly one seat, in the direction chosen, with
controllers read before anything moves; that left is the next seat in turn
order; that the source, lands and eliminated seats stay out of it; and that
every moved permanent is summoning sick for its new controller (302.6).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import action_for_card, oids_of, only_oid

BEAR = "t_bear"
RING = "sol_ring"
FATESHIFT = "t_fateshift"
NONLAND = {"not_types": ["Land"], "exclude_self": True}


def a_table(builder, players: int = 4):
    """Every seat has a bear and a forest; seat 0 also has a Sol Ring as the source."""
    b = builder(players=players)
    for pid in range(players):
        b = b.battlefield(pid, [BEAR, "forest"])
    b = b.battlefield(0, [RING])
    game = b.step(Step.PRECOMBAT_MAIN).build(advance=False)
    return game, only_oid(game, RING, 0)


def rotate(game, source: int | None, answer: int | None = None, controller: int = 0, **spec):
    """Run the op; ``answer`` is the index picked if it asks (0 = left, 1 = right)."""
    ctx = EffectContext(state=game.state, controller=controller, source_oid=source)
    gen = execute(ctx, [{"op": "rotate_control", "objects": NONLAND, **spec}])
    asked = []
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            decision = gen.send([answer if answer is not None else 0])
    except StopIteration:
        pass
    return asked


def bears(game) -> dict[int, int]:
    """Each original bear's owner -> its controller now."""
    return {game.state.objects[oid].owner: game.state.objects[oid].controller for oid in oids_of(game, BEAR)}


class TestEveryPermanentMovesOneSeat:
    def test_left_takes_from_the_next_seat_in_turn_order(self, builder):
        game, ring = a_table(builder)
        rotate(game, ring, answer=0)
        # Seat 0 takes seat 1's bear, 1 takes 2's, ..., 3 takes 0's.
        assert bears(game) == {1: 0, 2: 1, 3: 2, 0: 3}

    def test_right_takes_from_the_previous_seat(self, builder):
        game, ring = a_table(builder)
        rotate(game, ring, answer=1)
        assert bears(game) == {3: 0, 0: 1, 1: 2, 2: 3}

    def test_it_does_not_cascade(self, builder):
        """The loop-of-gain_control reading: one seat would end up with all four."""
        game, ring = a_table(builder)
        rotate(game, ring, answer=0)
        for pid in range(4):
            assert len([o for o in game.state.battlefield_objects(pid) if o.def_id == BEAR]) == 1

    def test_a_fixed_direction_asks_nobody(self, builder):
        game, ring = a_table(builder)
        assert rotate(game, ring, direction="right") == []
        assert bears(game) == {3: 0, 0: 1, 1: 2, 2: 3}


class TestWhatStaysPut:
    def test_lands_and_the_source_do_not_move(self, builder):
        game, ring = a_table(builder)
        rotate(game, ring, answer=0)
        assert game.state.objects[ring].controller == 0
        for oid in oids_of(game, "forest"):
            assert game.state.objects[oid].controller == game.state.objects[oid].owner

    def test_an_eliminated_seat_is_skipped(self, builder):
        game, ring = a_table(builder)
        game.state.players[1].has_lost = True
        rotate(game, ring, answer=0)
        # 0's left neighbour is now 2; 3's is 0; nobody takes from or gives to 1.
        bear_of = {game.state.objects[o].owner: o for o in oids_of(game, BEAR)}
        assert game.state.objects[bear_of[2]].controller == 0
        assert game.state.objects[bear_of[3]].controller == 2
        assert game.state.objects[bear_of[0]].controller == 3
        assert game.state.objects[bear_of[1]].controller == 1


class TestTheQuestion:
    def test_a_pod_asks_left_or_right_with_the_seats_behind_them(self, builder):
        game, ring = a_table(builder)
        asked = rotate(game, ring, answer=0)
        assert len(asked) == 1
        decision = asked[0]
        assert decision.kind is DecisionKind.CHOOSE_MODE
        assert decision.player == 0
        assert [o.label for o in decision.options] == ["Left", "Right"]
        assert decision.context["purpose"] == "choose_direction"
        assert decision.context["takes_from"] == [1, 3]

    def test_a_duel_is_not_asked_and_swaps_the_boards(self, builder):
        """Both directions name the same neighbour, so there is no question."""
        game, ring = a_table(builder, players=2)
        assert rotate(game, ring) == []
        assert bears(game) == {0: 1, 1: 0}


class TestTheNewController:
    def test_a_moved_creature_is_summoning_sick(self, builder):
        """302.6: it has not been under its new controller since their turn began."""
        game, ring = a_table(builder)
        rotate(game, ring, answer=0)
        taken = next(o for o in oids_of(game, BEAR) if game.state.objects[o].owner == 1)
        assert game.state.objects[taken].summoning_sick(game.state.turn)

    def test_the_change_outlasts_the_turn(self, builder):
        game, ring = a_table(builder)
        rotate(game, ring, answer=0)
        taken = next(o for o in oids_of(game, BEAR) if game.state.objects[o].owner == 1)
        assert game.state.objects[taken].until_eot == []


class TestTheHeuristicAgent:
    def test_it_takes_the_richer_board(self, builder):
        """`choices[0]` would be "left" whatever sits there; seat 3 has the rings."""
        from commanderblitz.ai.agents.heuristic_agent import HeuristicAgent

        b = builder(players=4).hand(0, [FATESHIFT]).battlefield(0, ["island"])
        b = b.battlefield(3, [RING, RING, RING])
        game = b.step(Step.PRECOMBAT_MAIN).build()
        game.apply(action_for_card(game, ActionKind.CAST, FATESHIFT))
        agent = HeuristicAgent(seed=0)
        for _ in range(100):
            decision = game.pending()
            if decision.context.get("purpose") == "choose_direction":
                game.apply(agent.act(game, 0, game.legal_actions()))
                break
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
        else:
            raise AssertionError("the direction was never asked")
        assert all(game.state.objects[o].controller == 0 for o in oids_of(game, RING))


class TestTheLoader:
    def card(self, **effect):
        return {
            "id": "t_bad_rotation",
            "name": "Test Bad Rotation",
            "oracle_text": "Rotate.",
            "mana_cost": "{U}",
            "types": ["Sorcery"],
            "spell_effects": [{"op": "rotate_control", **effect}],
        }

    def test_objects_are_required(self):
        with pytest.raises(DslError, match="rotate_control needs 'objects'"):
            compile_card(CardModel.model_validate(self.card()))

    def test_a_misspelt_direction_is_refused(self):
        card = self.card(objects={"not_types": ["Land"]}, direction="clockwise")
        with pytest.raises(DslError, match="'left' or 'right'"):
            compile_card(CardModel.model_validate(card))
