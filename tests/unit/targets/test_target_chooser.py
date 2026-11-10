"""A target chosen by another player -- still the ability's target.

    Bladegriff Prototype -- "Whenever this creature deals combat damage to a
    player, destroy target nonland permanent of that player's choice that one
    of your opponents controls."

603.3d and 601.2c: a triggered ability's targets are chosen as it goes on the
stack. "Of that player's choice" changes only who answers -- the damaged
player -- and nothing else: the candidates are the ones legal for the
ability's **controller** (hexproof and protection read the ability, not who
pointed it), drawn from every opponent of the controller and not only the
damaged one, and the target is re-checked on resolution like any other. The
near miss is an untargeted `destroy` with `chooser` in its `objects`, which
picks on resolution, ignores hexproof and never fizzles; and without this a
target selector's `chooser` was read by nobody, so the controller chose -- a
strictly better card.

`stack.target_chooser` names the seat; the loader allows the clause only on a
triggered ability's one fixed-size spec.
"""

from __future__ import annotations

import pytest

from commanderblitz.ai.agents.heuristic_agent import HeuristicAgent
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import attack_with, find_action, only_oid, pass_until

GRIFF = "t_tc_griff"


def board(builder, *, theirs=("t_bear", "t_hexproof", "forest"), others=("t_dork",)):
    """Seat 0's Griff, seat 1 to be hit, seat 2 a bystander opponent."""
    game = (
        builder(players=3)
        .battlefield(0, [GRIFF, "t_wall"])
        .battlefield(1, list(theirs))
        .battlefield(2, list(others))
        .build()
    )
    return game, only_oid(game, GRIFF, 0)


def connect(game, griff: int, defender: int = 1):
    """Attack ``defender`` with the Griff and stop at the target question."""
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
    attack_with(game, griff, defender)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(
        game,
        lambda g: (
            g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_OBJECTS
        )
        or any(item.source_oid == griff for item in g.state.stack),
    )


def through_combat(game, griff: int) -> list[int]:
    """Connect, then settle; the seats asked about the Griff's target."""
    connect(game, griff)
    asked: list[int] = []

    def watch(g) -> bool:
        decision = g.pending()
        if decision is not None and decision.context.get("source") == griff:
            asked.append(decision.player)
        return not g.state.stack and not g.state.pending_triggers

    pass_until(game, watch)
    return asked


def offered(game) -> set[str]:
    decision = game.pending()
    return {game.state.objects[o.ref.id].def_id for o in decision.options if o.ref}


def answer(game, card_id: str):
    decision = game.pending()
    index = next(
        o.value for o in decision.options
        if o.ref and game.state.objects[o.ref.id].def_id == card_id
    )
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index)
    )


class TestWhoChooses:
    def test_the_damaged_player_is_asked(self, builder):
        game, griff = board(builder)
        connect(game, griff)

        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.player == 1
        assert decision.context["chosen_for"] == 0

    def test_the_choice_spans_every_opponent_of_the_controller(self, builder):
        game, griff = board(builder)
        connect(game, griff)

        # The bystander's creature is on offer; the controller's own is not,
        # nor a land, nor a hexproof creature -- hexproof reads the ability's
        # controller, who is the damaged player's opponent.
        assert offered(game) == {"t_bear", "t_dork"}

    def test_the_answer_is_what_is_destroyed(self, builder):
        game, griff = board(builder)
        connect(game, griff)
        dork = only_oid(game, "t_dork", 2)
        answer(game, "t_dork")
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)

        assert game.state.objects[dork].zone is Zone.GRAVEYARD
        assert only_oid(game, "t_bear", 1)

    def test_one_legal_target_asks_nobody(self, builder):
        game, griff = board(builder, theirs=("t_hexproof",))
        dork = only_oid(game, "t_dork", 2)
        asked = through_combat(game, griff)

        assert asked == []
        assert game.state.objects[dork].zone is Zone.GRAVEYARD

    def test_no_legal_target_targets_nothing(self, builder):
        game, griff = board(builder, theirs=("t_hexproof",), others=())
        asked = through_combat(game, griff)

        assert asked == []
        assert only_oid(game, "t_hexproof", 1)
        assert only_oid(game, "t_wall", 0)


class TestTheAgent:
    def test_the_chooser_points_it_at_somebody_else(self, builder):
        game, griff = board(builder)
        connect(game, griff)
        dork = only_oid(game, "t_dork", 2)

        game.apply(HeuristicAgent(seed=0).act(game, 1, game.legal_actions()))
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)

        assert game.state.objects[dork].zone is Zone.GRAVEYARD

    def test_with_only_its_own_it_gives_up_the_least(self, builder):
        game, griff = board(builder, theirs=("t_bear", "t_wall"), others=())
        connect(game, griff)
        bear, wall = only_oid(game, "t_bear", 1), only_oid(game, "t_wall", 1)
        cheaper = min((bear, wall), key=lambda o: game.state.card(o).mana_value)

        game.apply(HeuristicAgent(seed=0).act(game, 1, game.legal_actions()))
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)

        assert game.state.objects[cheaper].zone is Zone.GRAVEYARD


class TestTheLoader:
    def _card(self, *, kind="triggered", target=None, extra_targets=()) -> CardModel:
        spec = {
            "id": "t1",
            "kind": "permanent",
            "count": 1,
            "selector": {"controller": "opponent", "chooser": {"binding": "event_player"}},
            **(target or {}),
        }
        ability = {
            "kind": kind,
            "text": "x",
            "targets": [spec, *extra_targets],
            "effects": [{"op": "destroy", "objects": {"target": "t1"}}],
        }
        if kind == "triggered":
            ability["trigger"] = {"event": "deals_combat_damage_to_player", "source": "self"}
        else:
            ability["cost"] = {"tap": True}
        return CardModel.model_validate(
            {
                "id": "t_tc_probe",
                "name": "Chooser Probe",
                "mana_cost": "{1}",
                "types": ["Artifact", "Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [ability],
            }
        )

    def test_it_loads_on_a_trigger(self):
        compile_card(self._card())

    def test_an_activated_ability_is_refused(self):
        with pytest.raises(DslError, match="chooser"):
            compile_card(self._card(kind="activated"))

    def test_a_spell_is_refused(self):
        model = CardModel.model_validate(
            {
                "id": "t_tc_spell",
                "name": "Chooser Spell",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "targets": [
                    {
                        "id": "t1",
                        "kind": "permanent",
                        "selector": {"chooser": "active_player"},
                    }
                ],
                "spell_effects": [{"op": "destroy", "objects": {"target": "t1"}}],
            }
        )
        with pytest.raises(DslError, match="chooser"):
            compile_card(model)

    def test_a_sibling_target_is_refused(self):
        with pytest.raises(DslError, match="chooser"):
            compile_card(self._card(extra_targets=[{"id": "p1", "kind": "player"}]))

    @pytest.mark.parametrize(
        "extra",
        [{"optional": True}, {"count": 2, "up_to": True}, {"count": "any"}],
        ids=["optional", "up_to", "any"],
    )
    def test_a_size_the_chooser_could_shrink_is_refused(self, extra):
        with pytest.raises(DslError, match="chooser"):
            compile_card(self._card(target=extra))

    @pytest.mark.parametrize("who", ["owner", "none", "nobody", {"target": "t1"}])
    def test_a_chooser_that_is_not_a_player_is_refused(self, who):
        with pytest.raises(DslError):
            compile_card(
                self._card(target={"selector": {"controller": "opponent", "chooser": who}})
            )

    def test_random_and_a_chooser_are_refused_together(self):
        with pytest.raises(DslError):
            compile_card(
                self._card(
                    target={
                        "selector": {
                            "controller": "opponent",
                            "random": True,
                            "chooser": {"binding": "event_player"},
                        }
                    }
                )
            )
