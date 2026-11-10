"""Who picks from a `look_at_top` window: "you", unless the card says otherwise.

    Siphon Insight -- "Look at the top two cards of target opponent's library.
    Exile one of them face down and put the other on the bottom of that
    library."
    Gonti, Lord of Luxury -- "look at the top four cards of target opponent's
    library, exile one of them face down, then put the rest on the bottom of
    that library in a random order."

Rule 109.5: "you" in an effect's text is its controller. The library being
looked at is the opponent's; the choice is still the caster's. Asking the
library's owner instead hands the pick to the player the card is stealing from,
who exiles the worst card for you -- a much weaker card than the printed one,
and a silent one, since the card still exiles something.

The claims: the controller picks over another player's library, in the pool
branch and in every `destinations` step; the controller's own library is
unchanged; `chooser: "owner"` is the printed "target player looks at the top
... and puts one into their hand", per library under `each_player`; a player
spec hands the pick to that player; a step's own clause beats the window's; and
`chooser: "none"` asks nobody. Siphon Insight is pinned on its shipped JSON.
"""

from __future__ import annotations

from commanderblitz.cards.registry import default_registry
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.structs import TargetRef

LIBRARY = ["t_bear", "t_stormbolt", "t_casualty", "island", "forest", "island"]

PICK_ONE = {
    "op": "look_at_top",
    "player": "opponent",
    "amount": 3,
    "objects": {"count": 1},
    "destination": "exile",
}


def a_board(builder):
    game = (
        builder(players=2)
        .battlefield(0, ["t_bear"])
        .library(0, list(LIBRARY))
        .library(1, list(LIBRARY))
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    return game, game.state.battlefield[0]


def run(game, source, effects, answer=lambda d: [0], targets=None):
    """Resolve `effects` for seat 0; returns every decision asked."""
    ctx = EffectContext(
        state=game.state, controller=0, source_oid=source, targets=targets or {}, bindings={}
    )
    gen = execute(ctx, list(effects))
    asked = []
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            decision = gen.send(answer(decision))
    except StopIteration:
        pass
    return asked


def choosers(asked) -> list[int]:
    return [d.player for d in asked]


class TestTheControllerPicksFromAnotherLibrary:
    def test_the_pool_is_offered_to_the_caster(self, builder):
        game, source = a_board(builder)
        asked = run(game, source, [PICK_ONE])
        assert choosers(asked) == [0]

    def test_the_card_the_caster_chose_is_the_one_exiled(self, builder):
        game, source = a_board(builder)
        third = game.state.players[1].library[2]
        options = []

        def take_third(decision):
            options.extend(o.value for o in decision.options)
            return [options.index(third)]

        run(game, source, [PICK_ONE], take_third)
        assert game.state.objects[third].zone is Zone.EXILE
        assert game.state.objects[third].owner == 1

    def test_an_explicit_controller_clause_says_the_same(self, builder):
        game, source = a_board(builder)
        spec = {**PICK_ONE, "objects": {"count": 1, "chooser": "controller"}}
        assert choosers(run(game, source, [spec])) == [0]

    def test_your_own_library_is_still_yours_to_pick(self, builder):
        game, source = a_board(builder)
        spec = {**PICK_ONE, "player": "you"}
        assert choosers(run(game, source, [spec])) == [0]


class TestTheOwnerPicksWhereTheCardSaysSo:
    def test_owner_hands_the_pick_to_the_library_s_player(self, builder):
        game, source = a_board(builder)
        spec = {**PICK_ONE, "objects": {"count": 1, "chooser": "owner"}}
        assert choosers(run(game, source, [spec])) == [1]

    def test_each_player_with_owner_asks_each_their_own(self, builder):
        game, source = a_board(builder)
        spec = {
            **PICK_ONE,
            "player": "each_player",
            "objects": {"count": 1, "chooser": "owner"},
        }
        asked = run(game, source, [spec])
        assert sorted(choosers(asked)) == [0, 1]
        for decision in asked:
            owners = {game.state.objects[o.value].owner for o in decision.options}
            assert owners == {decision.player}

    def test_a_player_spec_hands_the_pick_to_that_player(self, builder):
        game, source = a_board(builder)
        spec = {**PICK_ONE, "player": "you", "objects": {"count": 1, "chooser": "opponent"}}
        assert choosers(run(game, source, [spec])) == [1]


class TestDestinationStepsReadTheSameClause:
    STEPS = {
        "op": "look_at_top",
        "player": "opponent",
        "amount": 3,
        "objects": {},
        "destinations": [{"to": "exile", "count": 1}, {"to": "graveyard", "count": 1}],
    }

    def test_every_step_is_the_controller_s(self, builder):
        game, source = a_board(builder)
        assert choosers(run(game, source, [self.STEPS])) == [0, 0]

    def test_the_window_s_clause_reaches_the_steps(self, builder):
        game, source = a_board(builder)
        spec = {**self.STEPS, "objects": {"chooser": "owner"}}
        assert choosers(run(game, source, [spec])) == [1, 1]

    def test_a_step_s_own_clause_beats_the_window_s(self, builder):
        game, source = a_board(builder)
        spec = {
            **self.STEPS,
            "objects": {"chooser": "owner"},
            "destinations": [
                {"to": "exile", "count": 1, "selector": {"chooser": "controller"}},
                {"to": "graveyard", "count": 1},
            ],
        }
        assert choosers(run(game, source, [spec])) == [0, 1]

    def test_none_asks_nobody_and_takes_from_the_top(self, builder):
        game, source = a_board(builder)
        top = list(game.state.players[1].library[:2])
        spec = {**self.STEPS, "objects": {"chooser": "none"}}
        assert run(game, source, [spec]) == []
        assert [game.state.objects[o].zone for o in top] == [Zone.EXILE, Zone.GRAVEYARD]


class TestSiphonInsightAsShipped:
    def test_the_caster_picks_which_card_is_exiled_face_down(self, builder):
        game, source = a_board(builder)
        card = default_registry().registry.get("siphon_insight")
        library = game.state.players[1].library
        first, second = library[:2]
        options = []

        def take_second(decision):
            options.extend(o.value for o in decision.options)
            return [options.index(second)]

        asked = run(
            game,
            source,
            card.spell_effects,
            take_second,
            targets={"t1": (TargetRef.player(1),)},
        )
        assert choosers(asked) == [0]
        assert game.state.objects[second].zone is Zone.EXILE
        assert game.state.objects[second].hidden_in_exile
        assert game.state.players[1].library[-1] == first

    def test_gonti_s_controller_picks_from_the_four(self, builder):
        game, source = a_board(builder)
        card = default_registry().registry.get("gonti_lord_of_luxury")
        (trigger,) = [a for a in card.abilities if "look at the top four" in a.text]
        asked = run(game, source, trigger.effects, targets={"t1": (TargetRef.player(1),)})
        assert choosers(asked) == [0]
        assert len(asked[0].options) == 4
