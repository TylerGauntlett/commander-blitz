"""`return_from_graveyard`'s ``total_mana_value``: an untargeted return capped by a **sum**.

    Technomancer -- "When this creature enters, mill three cards, then return
    any number of artifact creature cards with total mana value 6 or less from
    your graveyard to the battlefield."

The return names no target, so the cards are chosen as the effect resolves
(608.2c), after the mill: the three cards it just binned are as eligible as
anything already there. The target key of the same name is the wrong spelling
twice over -- it is chosen as the trigger goes on the stack (601.2c), before
the mill, so a milled card could never come back, and it makes an untargeted
return targeted, which a hexproof-free graveyard hides but a fizzle does not.

"Total" is a constraint between the picks that no selector clause can state:
a per-card `mana_value <= 6` filter returns a graveyard of 6-drops all at
once. The pick is asked one card at a time, as `look_at_top`'s
is (`ops_cards._pick_within_total_mana_value`), each question offering only
what still fits under what is left; mana values never go negative, so every
legal set is reachable. Composed from `ask_objects`; no new `DecisionKind`.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError

#: Artifact creatures of mana value 2, 3, 3, 4 and 9; an artifact that is not a
#: creature; a creature that is not an artifact.
OVERSEER, HART, INSPECTOR, SOLEMN, TITAN = (
    "steel_overseer",
    "burnished_hart",
    "foundry_inspector",
    "solemn_simulacrum",
    "triplicate_titan",
)
RING, BEAR = "sol_ring", "grizzly_bears"

MILL = {"op": "mill", "amount": 3, "player": "you"}


def return_spec(cap=6, count="any", **extra):
    return {
        "op": "return_from_graveyard",
        "objects": {
            "zone": "graveyard",
            "controller": "you",
            "types": ["Artifact", "Creature"],
            "count": count,
            **extra,
        },
        "total_mana_value": cap,
        "destination": "battlefield",
    }


def a_board(builder, graveyard=(), library=()):
    return (
        builder(players=2)
        .graveyard(0, list(graveyard))
        .library(0, [*library, "island", "island", "island"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def run(game, effects, pick):
    """Run ``effects``; ``pick(decision)`` answers each question (indices into its options)."""
    ctx = EffectContext(state=game.state, controller=0)
    gen = execute(ctx, effects)
    asked = []
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            decision = gen.send(pick(decision))
    except StopIteration:
        pass
    return asked


def take(game, *def_ids):
    """Answer each question with the next of ``def_ids``, then decline."""
    queue = list(def_ids)

    def pick(decision):
        if not queue:
            return []
        want = queue.pop(0)
        for i, option in enumerate(decision.options):
            if game.state.objects[option.value].def_id == want:
                return [i]
        raise AssertionError(f"{want} was not offered")

    return pick


def offered(game, decision) -> list[str]:
    return sorted(game.state.objects[o.value].def_id for o in decision.options)


def on_battlefield(game) -> list[str]:
    return sorted(
        game.state.objects[o].def_id
        for o in game.state.battlefield
        if game.state.objects[o].owner == 0
    )


class TestTheSumIsCapped:
    def test_each_question_offers_only_what_still_fits(self, builder):
        game = a_board(builder, [OVERSEER, HART, SOLEMN, TITAN, RING, BEAR])
        asked = run(game, [return_spec()], take(game, SOLEMN, OVERSEER))
        assert [offered(game, d) for d in asked] == [
            sorted([OVERSEER, HART, SOLEMN]),
            [OVERSEER],
        ], "the Titan never fits; after a 4 only the 2 does; after it nothing"
        assert all(d.kind is DecisionKind.CHOOSE_OBJECTS for d in asked)
        assert all((d.min_count, d.max_count) == (0, 1) for d in asked)
        assert on_battlefield(game) == sorted([SOLEMN, OVERSEER])

    def test_two_threes_spend_the_whole_cap(self, builder):
        game = a_board(builder, [HART, INSPECTOR, OVERSEER])
        asked = run(game, [return_spec()], take(game, HART, INSPECTOR))
        assert len(asked) == 2, "3 + 3 is 6; the 2 no longer fits, so nothing is asked"
        assert on_battlefield(game) == sorted([HART, INSPECTOR])

    def test_the_picks_never_add_up_over_the_cap(self, builder):
        game = a_board(builder, [OVERSEER, HART, INSPECTOR, SOLEMN, TITAN])
        run(game, [return_spec()], lambda d: [0])
        back = [game.state.card_of(game.state.objects[o]).mana_value
                for o in game.state.battlefield if game.state.objects[o].owner == 0]
        assert back and sum(back) <= 6

    def test_the_cap_is_a_value_expression(self, builder):
        game = a_board(builder, [OVERSEER, HART])
        asked = run(game, [return_spec({"const": 2})], lambda d: [])
        assert [offered(game, d) for d in asked] == [[OVERSEER]]

    def test_a_count_caps_how_many_as_well_as_how_much(self, builder):
        game = a_board(builder, ["ornithopter", "ornithopter", "ornithopter"])
        asked = run(game, [return_spec(count=2, optional=True)], lambda d: [0])
        assert len(asked) == 2, "three 0-drops fit under 6, but the count is two"
        assert on_battlefield(game) == ["ornithopter", "ornithopter"]


class TestItMayStopShort:
    def test_declining_returns_nothing(self, builder):
        game = a_board(builder, [OVERSEER, HART])
        asked = run(game, [return_spec()], lambda d: [])
        assert len(asked) == 1
        assert on_battlefield(game) == []
        assert len(game.state.players[0].graveyard) == 2

    def test_an_empty_graveyard_asks_nothing(self, builder):
        game = a_board(builder, [RING, BEAR])
        assert run(game, [return_spec()], lambda d: [0]) == []
        assert on_battlefield(game) == []


class TestTheMillFeedsTheReturn:
    """Technomancer's order: the pick is made after the mill, so what it binned counts."""

    def test_a_milled_card_is_offered(self, builder):
        game = a_board(builder, [OVERSEER], library=[SOLEMN, BEAR, HART])
        asked = run(game, [MILL, return_spec()], take(game, SOLEMN, OVERSEER))
        assert offered(game, asked[0]) == sorted([OVERSEER, SOLEMN, HART])
        assert on_battlefield(game) == sorted([SOLEMN, OVERSEER])
        hart = next(o for o in game.state.players[0].graveyard
                    if game.state.objects[o].def_id == HART)
        assert game.state.objects[hart].zone is Zone.GRAVEYARD


class TestTheLoader:
    def card(self, effect):
        return {
            "id": "t_bad_return_tmv",
            "name": "Test Bad Return Total",
            "oracle_text": "Return.",
            "mana_cost": "{B}",
            "types": ["Sorcery"],
            "spell_effects": [effect],
        }

    def compile(self, effect):
        return compile_card(CardModel.model_validate(self.card(effect)))

    def test_an_any_number_return_loads(self):
        self.compile(return_spec())

    def test_an_up_to_return_loads(self):
        self.compile(return_spec(count=2, optional=True))

    @pytest.mark.parametrize("count", ["all", 2], ids=["all", "mandatory"])
    def test_a_count_the_cap_cannot_stop_short_of_is_refused(self, count):
        with pytest.raises(DslError, match="total_mana_value"):
            self.compile(return_spec(count=count))

    def test_the_cap_is_validated_as_a_value(self):
        with pytest.raises(DslError):
            self.compile(return_spec({"nonsense": 1}))

    def test_an_op_that_does_not_read_it_refuses_it(self):
        with pytest.raises(DslError, match="total_mana_value"):
            self.compile({"op": "draw", "amount": 1, "total_mana_value": 6})
