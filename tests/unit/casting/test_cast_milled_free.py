"""A free cast from a named pool, one choice per owner.

The Ur-Sphinx: "Whenever one or more Sphinxes you control attack, each player
mills that many cards. For each player, you may cast a card that player milled
this way without paying its mana cost."

`cast_from_hand` made the free cast during resolution (601.2, 608.2g), but only
out of the caster's own zone lists, so a card in an opponent's graveyard could
never be offered, and it asked once, so "for each player" would have been one
spell in total. `objects` names the pool -- the `mill` binding narrowed to
`zone: "graveyard"` -- and `per_owner` asks once per owner of a card in it. The
caster controls the spell and its owner keeps it (108.3): an opponent's creature
cast this way enters under the caster's control. A card that was already in a
graveyard, or one that left it after being milled, is not "milled this way", and
a land is never cast (305.9).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.state import new_object
from commanderblitz.engine.zones import move_object
from tests.conftest import attack_with, find_action, only_oid, pass_until

MILL = {"op": "mill", "player": "each_player", "amount": {"const": 2}, "as": "milled"}
UR_SPHINX = {
    "op": "cast_from_hand",
    "objects": {"binding": "milled", "zone": "graveyard"},
    "per_owner": True,
}


def a_table(builder, *, mine=(), theirs=(), their_graveyard=()):
    """Both libraries topped with the given cards; player 1 may already have a graveyard.

    The tops are stacked after the build, so the auto-pass draws none of them."""
    game = builder(players=2).graveyard(1, list(their_graveyard)).build()
    for pid, ids in ((0, mine), (1, theirs)):
        for card_id in reversed(ids):
            obj = new_object(game.state, card_id, owner=pid, zone=Zone.LIBRARY)
            game.state.players[pid].library.insert(0, obj.oid)
    return game


def resolve(game, spec=UR_SPHINX, *, take=(), before=None) -> list[list[int]]:
    """Mill, then resolve ``spec`` for player 0; return each question's offer.

    ``take`` names the def_ids to pick, one per question at most; ``before`` runs
    on the context between the mill and the cast."""
    ctx = EffectContext(state=game.state, controller=0)
    OPS["mill"](ctx, MILL)
    if before is not None:
        before(ctx)
    gen = OPS[spec["op"]](ctx, spec)
    asked: list[list[int]] = []
    answer = None
    while True:
        try:
            decision = gen.send(answer)
        except StopIteration:
            break
        offered = [option.value for option in decision.options]
        asked.append(offered)
        answer = [
            i for i, oid in enumerate(offered) if game.state.objects[oid].def_id in take
        ][:1]
    pass_until(game, lambda g: not g.state.stack)
    return asked


def owners(game, offered) -> set[int]:
    return {game.state.objects[oid].owner for oid in offered}


class TestOneQuestionPerOwner:
    def test_each_player_is_a_separate_choice(self, builder):
        game = a_table(builder, mine=["t_bear", "t_legend"], theirs=["t_bear", "t_legend"])
        asked = resolve(game)
        assert [owners(game, offered) for offered in asked] == [{0}, {1}]
        assert all(len(offered) == 2 for offered in asked)

    def test_without_per_owner_it_is_one_choice(self, builder):
        game = a_table(builder, mine=["t_bear"], theirs=["t_bear"])
        asked = resolve(game, {k: v for k, v in UR_SPHINX.items() if k != "per_owner"})
        assert len(asked) == 1 and owners(game, asked[0]) == {0, 1}

    def test_a_player_who_milled_nothing_castable_is_not_asked(self, builder):
        game = a_table(builder, theirs=["t_bear"])
        asked = resolve(game)
        assert [owners(game, offered) for offered in asked] == [{1}]


class TestWhatWasMilledThisWay:
    def test_a_land_is_not_offered(self, builder):
        game = a_table(builder, mine=["t_bear"])
        asked = resolve(game)
        offered = [oid for group in asked for oid in group]
        assert {game.state.objects[oid].def_id for oid in offered} == {"t_bear"}

    def test_a_card_already_in_the_graveyard_is_not_offered(self, builder):
        game = a_table(builder, their_graveyard=["t_legend"])
        assert resolve(game) == []

    def test_a_milled_card_that_left_the_graveyard_is_not_offered(self, builder):
        game = a_table(builder, theirs=["t_bear"])

        def exile_it(ctx):
            for oid in ctx.bindings["milled"]:
                if game.state.objects[oid].def_id == "t_bear":
                    move_object(game.state, oid, Zone.EXILE)

        assert resolve(game, before=exile_it) == []


class TestTheCast:
    def test_an_opponents_creature_enters_under_your_control(self, builder):
        game = a_table(builder, theirs=["t_bear"])
        resolve(game, take={"t_bear"})
        bear = next(
            oid for oid in game.state.battlefield if game.state.objects[oid].def_id == "t_bear"
        )
        assert game.state.objects[bear].controller == 0
        assert game.state.objects[bear].owner == 1

    def test_one_card_from_each_player(self, builder):
        game = a_table(builder, mine=["t_bear", "t_legend"], theirs=["t_bear", "t_legend"])
        resolve(game, take={"t_bear"})
        bears = [
            oid for oid in game.state.battlefield if game.state.objects[oid].def_id == "t_bear"
        ]
        assert {game.state.objects[oid].owner for oid in bears} == {0, 1}
        assert not any(
            game.state.objects[oid].def_id == "t_legend" for oid in game.state.battlefield
        )

    def test_declining_casts_nothing(self, builder):
        game = a_table(builder, theirs=["t_bear"])
        resolve(game, take=())
        assert all(
            game.state.objects[oid].def_id != "t_bear" for oid in game.state.battlefield
        )


class TestTheUrSphinx:
    """The printed card: "that many" is the Sphinxes among the attackers."""

    def test_a_sphinx_and_a_bear_attacking_mill_one_each(self, builder):
        game = builder(players=2).battlefield(0, ["the_ur_sphinx", "t_bear"]).build()
        for pid in (0, 1):
            obj = new_object(game.state, "t_legend", owner=pid, zone=Zone.LIBRARY)
            game.state.players[pid].library.insert(0, obj.oid)
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
        )
        attack_with(game, only_oid(game, "the_ur_sphinx", 0))
        attack_with(game, only_oid(game, "t_bear", 0))
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        asked: list[set[int]] = []
        while True:
            pass_until(
                game,
                lambda g: not g.state.stack
                or (g.pending() and g.pending().kind is DecisionKind.CHOOSE_OBJECTS),
            )
            decision = game.pending()
            if decision is None or decision.kind is not DecisionKind.CHOOSE_OBJECTS:
                break
            asked.append(owners(game, [option.value for option in decision.options]))
            game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        # One card each, the legend: one Sphinx attacked, not two creatures.
        assert asked == [{0}, {1}]
        for pid in (0, 1):
            graveyard = game.state.players[pid].graveyard
            assert [game.state.objects[oid].def_id for oid in graveyard] == ["t_legend"]


class TestTheLoaderGuards:
    def _card(self, effects: list[dict]) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_milled_caster",
                "name": "Test Milled Caster",
                "mana_cost": "{2}",
                "types": ["Sorcery"],
                "oracle_text": "Each player mills two cards. For each player, you may cast a "
                "card that player milled this way without paying its mana cost.",
                "spell_effects": effects,
            }
        )

    def test_the_ur_sphinx_form_loads(self):
        compile_card(self._card([MILL, UR_SPHINX]))

    def test_objects_and_zones_together_are_refused(self):
        with pytest.raises(DslError, match="not both"):
            compile_card(self._card([MILL, {**UR_SPHINX, "zones": ["graveyard"]}]))

    def test_per_owner_without_objects_is_refused(self):
        with pytest.raises(DslError, match="per_owner"):
            compile_card(self._card([{"op": "cast_from_hand", "per_owner": True}]))

    def test_objects_must_be_a_selector(self):
        with pytest.raises(DslError, match="objects"):
            compile_card(self._card([MILL, {**UR_SPHINX, "objects": "milled"}]))
