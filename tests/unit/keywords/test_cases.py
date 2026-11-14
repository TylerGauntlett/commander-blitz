"""Cases (rule 719): a designation the permanent earns, and abilities that come with it.

Case of the Shifting Visage is the witness -- "At the beginning of your upkeep,
surveil 1. / To solve — There are fifteen or more cards in your graveyard. (If
unsolved, solve at the beginning of your end step.) / Solved — Whenever you cast
a nonlegendary creature spell, copy that spell." Without the designation the
nearest spelling is `set_flag` from an end-step trigger and `has_flag` on the
cast trigger, which leaves the "Solved —" ability always on the permanent: a
static could not be switched off by it, an activated ability would be offered
and then refused, and nothing could tell a copy or a returned Case from the one
that was solved.

`TestToSolve`
    719.3b: "To solve — [condition]" means "At the beginning of your end step,
    if this Case is not solved and [condition], it becomes solved." Your end
    step only, an intervening-if checked again on resolution (603.4), once.

`TestSolvedAbilities`
    719.3c: a "Solved —" ability is there only while the Case is solved, for
    every reader of a permanent's abilities -- trigger collection, the
    characteristics pipeline, the printed-face walk for player-wide statics and
    legality -- through the one gate a Class level already uses, with the seat
    held by a latent stand-in.

`TestTheDesignation`
    719.3d and 400.7: solved is a designation, not a copiable value; a copy is
    unsolved, and a Case that leaves and returns is a new, unsolved object.

`TestTheLoaderRefuses` and `TestTheWire` cover the card format and the client.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import abilities_of, chars
from commanderblitz.engine.costs import land_drops_available
from commanderblitz.engine.enums import AbilityKind, ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.primitives import create_token
from commanderblitz.engine.serialize import card_view
from commanderblitz.engine.zones import move_object
from tests.conftest import advance_to_step, oids_of, only_oid, pass_until

CASE = "t_case"
BEAR = "t_bear"

#: Printed positions on `t_case`.
TO_SOLVE, ENTERS, ANTHEM, LAND, LIFE = range(5)


def position(builder, *, bears: int = 3, solved: bool = False, case_seat: int = 0):
    """Player 0's main phase with ``t_case`` beside ``bears`` Bears.

    The Case and the Bears sit with ``case_seat``. Player 1 holds a Lightning
    Bolt beside a Mountain, which stops the engine auto-passing the end-step
    trigger straight through to resolution, so a test can look in between.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * 4)
        .battlefield(case_seat, [BEAR] * bears)
        .battlefield(case_seat, [CASE], solved=solved)
        .battlefield(1, ["mountain"])
        .hand(1, ["lightning_bolt"])
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .build()
    )
    return game, only_oid(game, CASE)


def next_turn(game) -> None:
    """Through the rest of player 0's turn, end step included."""
    pass_until(game, lambda g: g.state.turn > 1)


def is_solved(game, oid: int) -> bool:
    return game.state.objects[oid].solved


def resolve(game) -> None:
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def to_solve_on_stack(game) -> bool:
    return any(item.ability_index == TO_SOLVE for item in game.state.stack)


def activation(game, oid: int, index: int):
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == oid and a.ability_index == index
        ),
        None,
    )


def pt(game, oid: int) -> tuple[int | None, int | None]:
    derived = chars(game.state, oid)
    return derived.power, derived.toughness


class TestToSolve:
    def test_it_is_solved_at_your_end_step_when_the_condition_holds(self, builder):
        game, case = position(builder)
        advance_to_step(game, Step.END_STEP)
        pass_until(game, lambda g: is_solved(g, case) or g.state.step is not Step.END_STEP)
        assert is_solved(game, case)

    def test_not_before_the_end_step(self, builder):
        """The condition holding in the main phase solves nothing yet."""
        game, case = position(builder)
        advance_to_step(game, Step.POSTCOMBAT_MAIN)
        assert not is_solved(game, case)

    def test_not_when_the_condition_fails(self, builder):
        game, case = position(builder, bears=2)
        next_turn(game)
        assert not is_solved(game, case)

    def test_not_at_an_opponents_end_step(self, builder):
        """"Your end step": the Case's controller is not the active player."""
        game, case = position(builder, case_seat=1)
        next_turn(game)
        assert not is_solved(game, case)

    def test_the_condition_is_checked_again_on_resolution(self, builder):
        """603.4: the trigger is an intervening-if. A Bear gone before it
        resolves leaves the Case unsolved."""
        game, case = position(builder)
        pass_until(game, to_solve_on_stack)
        assert to_solve_on_stack(game)
        move_object(game.state, oids_of(game, BEAR, 0)[0], Zone.GRAVEYARD)
        resolve(game)
        assert not is_solved(game, case)

    def test_a_solved_case_does_not_trigger_again(self, builder):
        """"If this Case is not solved": the trigger never goes on the stack."""
        game, case = position(builder, solved=True)
        next_turn(game)
        assert is_solved(game, case)
        assert not any(
            e.type is EventType.BECAME_SOLVED for e in game.state.events
        ), "a Case is solved once"

    def test_solving_fires_became_solved(self, builder):
        game, case = position(builder)
        pass_until(game, lambda g: is_solved(g, case))
        fired = [e for e in game.state.events if e.type is EventType.BECAME_SOLVED]
        assert [e.source for e in fired] == [case]


class TestSolvedAbilities:
    def test_an_unsolved_anthem_is_absent(self, builder):
        game, _ = position(builder)
        assert pt(game, oids_of(game, BEAR, 0)[0]) == (2, 2)

    def test_a_solved_anthem_is_present(self, builder):
        game, _ = position(builder, solved=True)
        assert pt(game, oids_of(game, BEAR, 0)[0]) == (3, 3)

    def test_the_anthem_switches_on_as_it_is_solved(self, builder):
        game, case = position(builder)
        bear = oids_of(game, BEAR, 0)[0]
        pass_until(game, lambda g: is_solved(g, case))
        assert pt(game, bear) == (3, 3)

    def test_an_unsolved_trigger_does_not_fire(self, builder):
        game, _ = position(builder)
        life = game.state.players[0].life
        create_token(game.state, BEAR, 0)
        resolve(game)
        assert game.state.players[0].life == life

    def test_a_solved_trigger_fires(self, builder):
        game, _ = position(builder, solved=True)
        life = game.state.players[0].life
        create_token(game.state, BEAR, 0)
        resolve(game)
        assert game.state.players[0].life == life + 1

    def test_a_player_wide_static_is_gated_too(self, builder):
        """`player_statics` walks the printed face, so it asks the gate itself."""
        unsolved, _ = position(builder)
        solved, _ = position(builder, solved=True)
        assert land_drops_available(unsolved.state, 0) == 1
        assert land_drops_available(solved.state, 0) == 2

    def test_an_unsolved_activated_ability_is_not_offered(self, builder):
        game, case = position(builder)
        assert activation(game, case, LIFE) is None

    def test_a_solved_activated_ability_is_offered(self, builder):
        game, case = position(builder, solved=True)
        life = game.state.players[0].life
        game.apply(activation(game, case, LIFE))
        resolve(game)
        assert game.state.players[0].life == life + 2

    def test_seats_are_held_by_latent_stand_ins(self, builder):
        game, case = position(builder)
        have = abilities_of(game.state, case)
        assert [a.index for a in have] == list(range(len(have)))
        assert {a.index for a in have if a.kind is AbilityKind.LATENT} == {
            ENTERS,
            ANTHEM,
            LAND,
            LIFE,
        }
        assert have[TO_SOLVE].is_triggered


class TestTheDesignation:
    def test_a_copy_is_unsolved(self, builder):
        """707.2: solved is a designation, not a copiable value."""
        game, _ = position(builder, solved=True)
        (copy,) = create_token(game.state, CASE, 0)
        assert not is_solved(game, copy)

    def test_it_comes_back_unsolved(self, builder):
        """400.7: a Case that left and returned is a new object."""
        game, case = position(builder, solved=True)
        move_object(game.state, case, Zone.HAND)
        move_object(game.state, case, Zone.BATTLEFIELD)
        assert not is_solved(game, case)


VISAGE = "case_of_the_shifting_visage"


def visage_position(builder, *, solved: bool, hand: list[str]):
    game = (
        builder(players=2)
        .battlefield(0, ["plains", "forest"] * 3)
        .battlefield(0, [VISAGE], solved=solved)
        .hand(0, hand)
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .build()
    )
    pass_until(game, lambda g: (d := g.pending()) is not None and d.player == 0)
    return game


def cast_and_resolve(game, card_id: str) -> None:
    cast = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(cast)
    resolve(game)


class TestTheWitness:
    """Case of the Shifting Visage: "Solved — Whenever you cast a nonlegendary
    creature spell, copy that spell. (The copy becomes a token.)"
    """

    def test_unsolved_it_copies_nothing(self, builder):
        game = visage_position(builder, solved=False, hand=[BEAR])
        cast_and_resolve(game, BEAR)
        assert len(oids_of(game, BEAR, 0)) == 1

    def test_solved_it_copies_a_nonlegendary_creature_spell(self, builder):
        game = visage_position(builder, solved=True, hand=[BEAR])
        cast_and_resolve(game, BEAR)
        bears = oids_of(game, BEAR, 0)
        assert len(bears) == 2
        assert sorted(game.state.objects[b].is_token for b in bears) == [False, True]

    def test_solved_it_does_not_copy_a_legendary_one(self, builder):
        game = visage_position(builder, solved=True, hand=["t_legend"])
        cast_and_resolve(game, "t_legend")
        assert len(oids_of(game, "t_legend", 0)) == 1


def _case(abilities, *, subtypes=("Case",)) -> dict:
    return {
        "id": "x_case",
        "name": "X Case",
        "types": ["Enchantment"],
        "subtypes": list(subtypes),
        "abilities": abilities,
    }


_SOLVE = {
    "kind": "to_solve",
    "text": "To solve — You control three or more creatures.",
    "condition": {
        "cmp": ">=",
        "left": {"count": {"controller": "you", "types": ["Creature"]}},
        "right": {"const": 3},
    },
}
_GATED = {
    "kind": "activated",
    "text": "Solved — {2}: You gain 2 life.",
    "solved": True,
    "cost": {"mana": "{2}"},
    "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 2}}],
}


class TestTheLoaderRefuses:
    @pytest.mark.parametrize(
        ("card", "message"),
        [
            (_case([_SOLVE], subtypes=()), "'Case' subtype"),
            (_case([_GATED]), "no to_solve line"),
            (_case([_SOLVE, _SOLVE]), "one to_solve line"),
            (_case([{"kind": "to_solve", "text": "To solve — x"}]), "needs the 'condition'"),
            (_case([{**_SOLVE, "effects": [{"op": "draw"}]}]), "cannot also set"),
            (_case([_SOLVE, {**_GATED, "level": 2}]), "not both"),
            (_case([_SOLVE, {**_GATED, "active_zones": ["graveyard"]}]), "only exists on the battlefield"),
            (
                _case(
                    [
                        {
                            "kind": "triggered",
                            "text": "x",
                            "trigger": {"event": "end_step", "controller": "you"},
                            "effects": [{"op": "solve"}],
                        }
                    ]
                ),
                "written by the loader",
            ),
        ],
    )
    def test_refused(self, card, message):
        with pytest.raises(DslError, match=message):
            compile_card(CardModel.model_validate(card))

    def test_a_case_with_its_line_loads(self):
        card = compile_card(CardModel.model_validate(_case([_SOLVE, _GATED])))
        assert card.solvable
        assert card.abilities[1].solved


class TestTheWire:
    def test_a_case_sends_its_designation(self, builder):
        game, case = position(builder, solved=True)
        assert card_view(game.state, case)["solved"] is True

    def test_any_other_permanent_does_not(self, builder):
        game, _ = position(builder)
        assert "solved" not in card_view(game.state, oids_of(game, BEAR, 0)[0])
