"""Putting counters on the source as a *cost*, and why it cannot be an effect.

"{T}, **Put a page counter on this artifact**: Scry 1." -- Mazemind Tome.

Rule 602.2b (through 601.2h): the costs of an activated ability are paid as it
is put on the stack. The counter is part of the price, so it is on the
permanent *while the ability waits to resolve*, and it stays there whatever
happens to the ability afterwards. Writing the placement as an `add_counters`
effect instead moves it to resolution, and the gap is observable on the card
that motivated the cost: Mazemind Tome's third line watches the page count, so
an ability countered in response would never turn a page, and a fourth page
would arrive one resolution late. `t_pc_naive_tome` is that wrong card, kept as
the counterfactual.

A placement made as a cost is still a placement (122.6): it raises
`counter_placed`, it is "put" by the activating player, and the counter
replacements apply -- except Doubling Season's, whose "if **an effect** would
put" excludes a cost (118.1; the same ruling `loyalty` honours).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from tests.conftest import activations, only_oid, settle

TOME = "t_pc_tome"  # {T}, put a page counter: gain 1 life
BATTERY = "t_pc_battery"  # {1}, put two charge counters: gain 1 life
NAIVE = "t_pc_naive_tome"  # {T}: put a page counter, gain 1 life -- the wrong card
WATCHER = "t_pc_watcher"  # the cost, plus "whenever counters are put on this"
SEASON = "t_ceo_season"  # Doubling Season: "if an effect would put", doubled
UNCHECKED = "t_rc_season"  # the same line without `effects_only`
TALENT = "t_pb_talent"  # "if you would put", doubled


def position(builder, card_id: str, board=()):
    """``card_id`` and four Forests for player 0, in a main phase.

    The opponent holds a Lightning Bolt beside a Mountain and never casts it:
    an instant they could answer with is what stops the engine auto-passing an
    activation straight through to resolution, so a test can look at the board
    while the ability waits on the stack.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4 + [card_id, *board])
        .battlefield(1, ["mountain"])
        .hand(1, ["lightning_bolt"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game, only_oid(game, card_id, 0)


def activate(game, oid: int) -> None:
    game.apply(activations(game, oid)[0])


def counters(game, oid: int, kind: str) -> int:
    return game.state.objects[oid].counter(kind)


def life(game, pid: int = 0) -> int:
    return game.state.players[pid].life


class TestTheCostIsPaidOnActivation:
    def test_the_counter_is_on_while_the_ability_waits(self, builder):
        game, oid = position(builder, TOME)
        activate(game, oid)
        assert game.state.stack, "the ability should still be on the stack"
        assert counters(game, oid, "page") == 1

    def test_the_effect_still_resolves(self, builder):
        game, oid = position(builder, TOME)
        before = life(game)
        activate(game, oid)
        settle(game)
        assert (counters(game, oid, "page"), life(game)) == (1, before + 1)

    def test_the_naive_effect_is_a_different_card(self, builder):
        """The counterfactual: the same words as an effect place nothing until
        the ability resolves, which is the window a response lives in."""
        game, oid = position(builder, NAIVE)
        activate(game, oid)
        assert game.state.stack
        assert counters(game, oid, "page") == 0

    def test_it_puts_exactly_the_amount_printed(self, builder):
        game, oid = position(builder, BATTERY)
        activate(game, oid)
        assert counters(game, oid, "charge") == 2

    def test_paying_again_adds_again(self, builder):
        """Nothing taps, so the battery can be fed twice -- a cost is a cost
        every time, not a one-time arrival."""
        game, oid = position(builder, BATTERY)
        activate(game, oid)
        settle(game)
        activate(game, oid)
        assert counters(game, oid, "charge") == 4


class TestItIsAPlacement:
    """122.6: putting counters as a cost is putting counters."""

    def test_it_raises_counter_placed_put_by_the_activator(self, builder):
        game, oid = position(builder, TOME)
        mark = len(game.state.events)
        activate(game, oid)
        placed = [e for e in game.state.events[mark:] if e.type == EventType.COUNTER_PLACED]
        assert [(e.data["oid"], e.data["counter"], e.data["put_by"]) for e in placed] == [
            (oid, "page", 0)
        ]

    def test_a_counter_placed_trigger_fires_off_it(self, builder):
        game, oid = position(builder, WATCHER)
        before = life(game)
        activate(game, oid)
        settle(game)
        assert life(game) == before + 1


class TestReplacements:
    def test_doubling_season_leaves_a_cost_alone(self, builder):
        """"If an effect would put" -- and a cost is not an effect (118.1)."""
        game, oid = position(builder, TOME, board=[SEASON])
        activate(game, oid)
        assert counters(game, oid, "page") == 1

    def test_would_be_put_reaches_a_cost(self, builder):
        game, oid = position(builder, TOME, board=[UNCHECKED])
        activate(game, oid)
        assert counters(game, oid, "page") == 2

    def test_if_you_would_put_reaches_a_cost_you_pay(self, builder):
        """The activator is the one putting them, so Innkeeper's Talent's
        "if you would put" applies."""
        game, oid = position(builder, TOME, board=[TALENT])
        activate(game, oid)
        assert counters(game, oid, "page") == 2


class TestTheSolverMustNotPayItSilently:
    def test_a_put_counters_cost_is_not_tap_only(self, builder):
        game, oid = position(builder, TOME)
        cost = game.state.card_of(game.state.objects[oid]).abilities[0].cost
        assert not cost.is_tap_only()

    def test_describe_names_the_counter(self, builder):
        game, oid = position(builder, BATTERY)
        cost = game.state.card_of(game.state.objects[oid]).abilities[0].cost
        assert "Put 2 charge counters on this" in cost.describe()


def _artifact(cost: dict, **extra) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "Probe.",
            "mana_cost": "{2}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "activated",
                    "text": "Probe.",
                    "cost": cost,
                    "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
                }
            ],
            **extra,
        }
    )


class TestLoaderRefusals:
    def test_the_amount_defaults_to_one(self):
        card = compile_card(_artifact({"tap": True, "put_counters": {"counter": "page"}}))
        assert card.abilities[0].cost.put_counters == {"counter": "page"}

    def test_a_kind_is_required(self):
        with pytest.raises(DslError, match="'counter' kind"):
            compile_card(_artifact({"tap": True, "put_counters": {"amount": 1}}))

    @pytest.mark.parametrize("amount", [0, -1, "1", True])
    def test_the_amount_is_a_positive_integer(self, amount):
        with pytest.raises(DslError, match="positive integer"):
            compile_card(
                _artifact({"tap": True, "put_counters": {"counter": "page", "amount": amount}})
            )

    def test_an_unknown_key_is_refused(self):
        with pytest.raises(DslError, match="unknown keys"):
            compile_card(
                _artifact({"tap": True, "put_counters": {"counter": "page", "objects": {}}})
            )

    def test_a_near_miss_keyword_counter_is_refused(self):
        with pytest.raises(DslError, match="keyword counter"):
            compile_card(_artifact({"tap": True, "put_counters": {"counter": "Flying"}}))

    def test_it_is_refused_off_an_activated_ability(self):
        """An additional cost to cast has a spell for its source, and a spell on
        the stack is no permanent to hold a counter."""
        with pytest.raises(DslError, match="activated ability only"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "probe",
                        "name": "Probe",
                        "oracle_text": "Probe.",
                        "mana_cost": "{1}",
                        "types": ["Sorcery"],
                        "additional_cost": {"put_counters": {"counter": "page"}},
                        "spell_effects": [
                            {"op": "gain_life", "player": "you", "amount": {"const": 1}}
                        ],
                    }
                )
            )


def test_activation_is_an_ordinary_action(builder):
    """Nothing about the cost asks a question: one action, paid at once."""
    game, oid = position(builder, TOME)
    actions = activations(game, oid)
    assert len(actions) == 1 and actions[0].kind is ActionKind.ACTIVATE
