"""Choosing a card name, and finding the cards that carry it.

    Tamiyo, Collector of Tales, +1 — "Choose a nonland card name, then reveal
    the top four cards of your library. Put all cards with the chosen name from
    among them into your hand and the rest into your graveyard."

Two pieces, and neither existed: a question whose answer is a **name** (the
engine could choose a creature type, a permanent type, a colour and a player),
and a selector that matches the name chosen a line earlier -- `name` took only
a literal written into the card.

`choose_card_name` binds the name under `as`; a selector reads it back as
`{"name": {"binding": …}}`. The answers offered are every distinct name among
the cards the chooser owns plus "another card name": a library holds only its
owner's cards (400.3), so every other name ever printed has the same outcome --
it matches nothing -- and that outcome is a real choice (naming a card that is
not there mills all four). The nonland restriction is `not_types: ["Land"]`.

No new `DecisionKind`: it is `ask_mode`, tagged `choose_card_name`, and the
heuristic agent names what its library holds most of rather than the first
label alphabetically.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.ops_control import OTHER_CARD_NAME
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import action_for_card

SPELL = "t_name_and_look"
BEAR, ELF, BOLT = "t_bear", "t_elf", "t_bolt"

EFFECTS = [
    {"op": "choose_card_name", "as": "named", "not_types": ["Land"]},
    {
        "op": "look_at_top",
        "amount": {"const": 4},
        "objects": {"name": {"binding": "named"}, "count": "all"},
        "destination": "hand",
        "rest_to": "graveyard",
    },
]


def position(builder, library=(BEAR, ELF, BEAR, "island", BOLT, BEAR)):
    """Player 0's library, top first; their hand empty; a bolt in their graveyard."""
    return (
        builder(players=2)
        .library(0, list(library))
        .library(1, ["island"] * 5)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def resolve(game, name: str | None) -> list:
    """Run the +1, naming ``name`` (a label); return the questions asked."""
    ctx = EffectContext(state=game.state, controller=0)
    gen = execute(ctx, EFFECTS)
    asked = []
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            labels = [o.label for o in decision.options]
            decision = gen.send([labels.index(name)])
    except StopIteration:
        pass
    return asked


def names(game, zone: str) -> list[str]:
    player = game.state.players[0]
    return sorted(game.state.card_of(game.state.objects[o]).name for o in getattr(player, zone))


class TestTheChoice:
    def test_it_asks_one_label_question(self, builder):
        game = position(builder)
        (decision,) = resolve(game, "Test Bear")
        assert decision.kind is DecisionKind.CHOOSE_MODE
        assert decision.context["purpose"] == "choose_card_name"

    def test_the_names_are_the_nonland_cards_i_own_plus_another(self, builder):
        game = position(builder)
        (decision,) = resolve(game, "Test Bear")
        labels = [o.label for o in decision.options]
        assert labels == ["Test Bear", "Test Bolt", "Test Elf", OTHER_CARD_NAME]

    def test_an_opponents_cards_are_not_offered(self, builder):
        game = (
            builder(players=2)
            .library(0, [BEAR] * 4)
            .library(1, [ELF] * 4)
            .battlefield(1, [BOLT])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        (decision,) = resolve(game, "Test Bear")
        assert [o.label for o in decision.options] == ["Test Bear", OTHER_CARD_NAME]


class TestTheLook:
    def test_every_card_with_the_name_goes_to_hand(self, builder):
        game = position(builder)
        resolve(game, "Test Bear")
        assert names(game, "hand") == ["Test Bear", "Test Bear"]
        assert names(game, "graveyard") == ["Island", "Test Elf"]

    def test_only_the_top_four_are_looked_at(self, builder):
        """The bear under the fourth card stays in the library."""
        game = position(builder)
        resolve(game, "Test Bear")
        assert names(game, "library") == ["Test Bear", "Test Bolt"]

    def test_a_name_among_them_once(self, builder):
        game = position(builder)
        resolve(game, "Test Elf")
        assert names(game, "hand") == ["Test Elf"]

    def test_a_name_not_among_them_mills_all_four(self, builder):
        game = position(builder)
        resolve(game, "Test Bolt")
        assert names(game, "hand") == []
        assert len(game.state.players[0].graveyard) == 4

    def test_another_name_matches_nothing(self, builder):
        game = position(builder)
        resolve(game, OTHER_CARD_NAME)
        assert names(game, "hand") == []
        assert len(game.state.players[0].graveyard) == 4


class TestTheHeuristicAgent:
    def test_it_names_what_its_library_holds_most_of(self, builder):
        from commanderblitz.ai.agents.heuristic_agent import HeuristicAgent

        game = (
            builder(players=2)
            .hand(0, [SPELL])
            .battlefield(0, ["island"])
            .library(0, [ELF, BEAR, BEAR, BEAR, BOLT])
            .library(1, ["island"] * 5)
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, SPELL))
        agent = HeuristicAgent(seed=0)
        for _ in range(50):
            decision = game.pending()
            if (decision.context or {}).get("purpose") == "choose_card_name":
                action = agent.act(game, 0, game.legal_actions())
                assert action.label == "Test Bear"
                return
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
        raise AssertionError("the name was never asked")


class TestTheLoader:
    def test_the_printed_shape_loads(self):
        compile_card(CardModel.model_validate(_card()))

    def test_as_is_required(self):
        card = _card()
        card["spell_effects"][0].pop("as")
        with pytest.raises(DslError, match="choose_card_name needs an 'as'"):
            compile_card(CardModel.model_validate(card))

    def test_an_unknown_card_type_is_refused(self):
        card = _card()
        card["spell_effects"][0]["not_types"] = ["Lnd"]
        with pytest.raises(DslError, match="unknown card type"):
            compile_card(CardModel.model_validate(card))

    def test_a_name_that_is_neither_literal_nor_binding_is_refused(self):
        card = _card()
        card["spell_effects"][1]["objects"]["name"] = {"var": "named"}
        with pytest.raises(DslError, match="'name' takes a card name"):
            compile_card(CardModel.model_validate(card))


def _card() -> dict:
    return {
        "id": "t_bad_name",
        "name": "Test Bad Name",
        "oracle_text": "Choose a nonland card name, then reveal the top four cards of your library.",
        "mana_cost": "{U}",
        "types": ["Sorcery"],
        "spell_effects": [dict(e) for e in EFFECTS[:1]]
        + [{**EFFECTS[1], "objects": dict(EFFECTS[1]["objects"])}],
    }
