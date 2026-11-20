""""Up to **X** target creatures gain fear" owned by one bullet of a modal spell
-- 601.2b, 601.2c, 608.2b.

    Profane Command -- "{X}{B}{R} Choose two --
    * Target player loses X life.
    * Return target creature card with mana value X or less from your
      graveyard to the battlefield.
    * Target creature gets -X/-X until end of turn.
    * Up to X target creatures gain fear until end of turn."

    Heliod's Intervention -- "{X}{W}{W} Choose one --
    * Destroy X target artifacts and/or enchantments.
    * Target player gains twice X life."

601.2b announces X and chooses the modes; 601.2c then declares the targets of
the modes chosen. So when a bullet's targets are declared, X is already a
number: "up to X" has a ceiling, "exactly X" a size, and "mana value X or less"
a pool. `Game._cast` asks in that order -- `_ask_x`, `_ask_modes`,
`_ask_mode_targets` -- and hands the announced X to the last two, so the
mode-owned spec is sized by it (`targeting.target_count`) and its selector reads
it (`targeting.candidates`).

Without it each bullet is a different card. Sized at the zero legality
enumerates at, "up to X target creatures" gains fear on nobody; a printed
ceiling instead is "up to N" whatever was paid; and lifting the spec off the
mode demands the fear targets whichever two bullets are chosen. A reanimation
bullet whose pool reads X at zero returns only a mana-value-0 creature card, so
the mode is never offered once there is none.

The loader admits ``count: {"x": true}`` on a mode-owned spec of a **spell**
only. An activated or triggered ability declares its mode-owned targets with no
announced X for `target_count` to read, so there it stays refused.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import keywords, only_oid, pt, settle_to_priority

COMMAND = "t_profane_command"
INTERVENTION = "t_heliod_intervention"
BEAR = "t_bear"  # {1}{G} 2/2
BIG = "t_big"  # {5}{G} 6/6
DORK = "t_dork"  # {G} 1/1

DRAIN, RAISE, SHRINK, FEAR = range(4)
COMMAND_LABELS = (
    "Target player loses X life.",
    "Return target creature card with mana value X or less from your graveyard to the battlefield.",
    "Target creature gets -X/-X until end of turn.",
    "Up to X target creatures gain fear until end of turn.",
)
DESTROY, HEAL = range(2)
INTERVENTION_LABELS = (
    "Destroy X target artifacts and/or enchantments.",
    "Target player gains twice X life.",
)


def command_board(builder, *, buried=(BEAR, BIG), theirs=(BEAR, DORK, BIG)):
    """Player 0 holds Profane Command with five lands (X up to 3) and two
    creature cards in the graveyard; player 1 controls three creatures."""
    return (
        builder(players=2)
        .battlefield(0, ["swamp"] * 3 + ["mountain"] * 2)
        .hand(0, [COMMAND])
        .graveyard(0, list(buried))
        .battlefield(1, [*theirs, "plains"])
        .hand(1, ["t_plain_instant"])
        .library(0, ["swamp"] * 10)
        .library(1, ["swamp"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def intervention_board(builder):
    """Player 0 holds Heliod's Intervention with five Plains (X up to 3);
    player 1 controls two artifacts and an enchantment."""
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 5)
        .hand(0, [INTERVENTION])
        .battlefield(1, ["sol_ring", "sol_ring", "rhystic_study", "plains"])
        .hand(1, ["t_plain_instant"])
        .library(0, ["plains"] * 10)
        .library(1, ["plains"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def begin(game, card_id: str, x: int) -> None:
    """Cast ``card_id`` and announce X."""
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        )
    )
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_X, decision
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == x)
    )


def offered_modes(game, labels) -> list[int]:
    """The bullets the mode question offers, as printed indices."""
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_MODE, decision
    return [labels.index(option.label) for option in decision.options]


def choose_modes(game, labels, modes: list[int]) -> None:
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_MODE, decision
    for mode in modes:
        ordinal = next(
            i for i, option in enumerate(decision.options) if option.label == labels[mode]
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.choice == ordinal
            )
        )
    if game.pending() is decision:
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
        )


def target_prompt(game):
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS, decision
    return decision


def pick(game, ids: list[int]) -> None:
    """Answer one target question with ``ids`` (player seats or object ids)."""
    decision = target_prompt(game)
    for wanted in ids:
        ordinal = next(
            i
            for i, option in enumerate(decision.options)
            if option.ref is not None and option.ref.id == wanted
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.choice == ordinal
            )
        )
    if game.pending() is decision:
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
        )


def theirs(game, card_id: str) -> int:
    return only_oid(game, card_id, 1)


class TestUpToXTargets:
    @pytest.mark.parametrize("x", [1, 2, 3])
    def test_the_ceiling_is_the_announced_x(self, builder, x):
        game = command_board(builder)
        begin(game, COMMAND, x)
        choose_modes(game, COMMAND_LABELS, [DRAIN, FEAR])
        pick(game, [1])
        prompt = target_prompt(game)
        assert (prompt.min_count, prompt.max_count) == (0, x)

    def test_the_chosen_creatures_gain_fear_and_the_drain_reads_x(self, builder):
        game = command_board(builder)
        bear, dork, big = theirs(game, BEAR), theirs(game, DORK), theirs(game, BIG)
        life = game.state.players[1].life
        begin(game, COMMAND, 2)
        choose_modes(game, COMMAND_LABELS, [DRAIN, FEAR])
        pick(game, [1])
        pick(game, [bear, dork])
        settle_to_priority(game)
        assert game.state.players[1].life == life - 2
        assert "fear" in keywords(game, bear)
        assert "fear" in keywords(game, dork)
        assert "fear" not in keywords(game, big)

    def test_fewer_than_x_is_a_choice(self, builder):
        game = command_board(builder)
        big = theirs(game, BIG)
        begin(game, COMMAND, 3)
        choose_modes(game, COMMAND_LABELS, [SHRINK, FEAR])
        pick(game, [big])
        pick(game, [])
        settle_to_priority(game)
        assert pt(game, big) == (3, 3)
        assert not any("fear" in keywords(game, oid) for oid in game.state.battlefield
                       if "Creature" in game.state.card(oid).types)

    def test_x_of_zero_asks_nothing(self, builder):
        """"Up to zero targets" is a bullet that targets nothing -- choosable,
        and not a question."""
        game = command_board(builder)
        life = game.state.players[1].life
        begin(game, COMMAND, 0)
        choose_modes(game, COMMAND_LABELS, [DRAIN, FEAR])
        pick(game, [1])
        assert game.pending().kind is not DecisionKind.CHOOSE_OBJECTS
        settle_to_priority(game)
        assert game.state.players[1].life == life

    def test_the_fear_bucket_is_stored_last(self, builder):
        """The X-sized spec is caster-sized, so `CardDef.specs_for_modes`
        stores it after the fixed-size bullet that precedes it in print order
        -- and the -X/-X lands on the creature the shrink bullet named."""
        game = command_board(builder)
        bear, big = theirs(game, BEAR), theirs(game, BIG)
        begin(game, COMMAND, 2)
        choose_modes(game, COMMAND_LABELS, [SHRINK, FEAR])
        pick(game, [big])
        pick(game, [bear])
        settle_to_priority(game)
        assert pt(game, big) == (4, 4)
        assert "fear" in keywords(game, bear)
        assert "fear" not in keywords(game, big)


class TestManaValueXOrLess:
    def test_the_pool_reads_the_announced_x(self, builder):
        """X = 2 offers the bear ({1}{G}) and the dork ({G}), not the six-drop."""
        game = command_board(builder, buried=(BEAR, DORK, BIG))
        bear, dork, big = game.state.players[0].graveyard
        assert [game.state.objects[o].def_id for o in (bear, dork, big)] == [BEAR, DORK, BIG]
        begin(game, COMMAND, 2)
        choose_modes(game, COMMAND_LABELS, [DRAIN, RAISE])
        pick(game, [1])
        offered = {o.ref.id for o in target_prompt(game).options if o.ref is not None}
        assert offered == {bear, dork}
        pick(game, [bear])
        settle_to_priority(game)
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[big].zone is Zone.GRAVEYARD

    def test_the_mode_is_offered_by_x(self, builder):
        """601.2b: a bullet with no legal target cannot be chosen -- and with
        only a two-drop in the graveyard, whether it has one depends on X."""
        game = command_board(builder, buried=(BEAR,))
        begin(game, COMMAND, 1)
        assert offered_modes(game, COMMAND_LABELS) == [DRAIN, SHRINK, FEAR]

        game = command_board(builder, buried=(BEAR,))
        begin(game, COMMAND, 2)
        assert offered_modes(game, COMMAND_LABELS) == [DRAIN, RAISE, SHRINK, FEAR]


class TestExactlyXTargets:
    @pytest.mark.parametrize("x", [1, 2])
    def test_the_size_is_x(self, builder, x):
        game = intervention_board(builder)
        begin(game, INTERVENTION, x)
        choose_modes(game, INTERVENTION_LABELS, [DESTROY])
        prompt = target_prompt(game)
        assert (prompt.min_count, prompt.max_count) == (x, x)

    def test_x_equal_to_the_pool_takes_all_of_it(self, builder):
        """Three artifacts and enchantments, X = 3: no choice is left, so
        nothing is asked and every one of them is destroyed."""
        game = intervention_board(builder)
        begin(game, INTERVENTION, 3)
        choose_modes(game, INTERVENTION_LABELS, [DESTROY])
        settle_to_priority(game)
        assert not any(
            game.state.objects[o].def_id in ("sol_ring", "rhystic_study")
            for o in game.state.battlefield
        )

    def test_the_x_targets_are_destroyed(self, builder):
        game = intervention_board(builder)
        study = theirs(game, "rhystic_study")
        ring = next(iter(o for o in game.state.battlefield
                         if game.state.objects[o].def_id == "sol_ring"))
        begin(game, INTERVENTION, 2)
        choose_modes(game, INTERVENTION_LABELS, [DESTROY])
        pick(game, [study, ring])
        settle_to_priority(game)
        assert game.state.objects[study].zone is Zone.GRAVEYARD
        assert game.state.objects[ring].zone is Zone.GRAVEYARD
        rings = [o for o in game.state.battlefield if game.state.objects[o].def_id == "sol_ring"]
        assert len(rings) == 1

    def test_the_other_bullet_declares_no_x_targets(self, builder):
        game = intervention_board(builder)
        life = game.state.players[0].life
        begin(game, INTERVENTION, 3)
        choose_modes(game, INTERVENTION_LABELS, [HEAL])
        pick(game, [0])
        settle_to_priority(game)
        assert game.state.players[0].life == life + 6
        assert sum(
            1 for o in game.state.battlefield
            if game.state.objects[o].def_id in ("sol_ring", "rhystic_study")
        ) == 3


def json_card(card_id: str) -> dict:
    path = Path(__file__).resolve().parents[2] / "data" / "x_sized_mode_targets.cards.json"
    cards = json.loads(path.read_text(encoding="utf-8"))["cards"]
    return copy.deepcopy(next(card for card in cards if card["id"] == card_id))


def compile_(card) -> None:
    compile_card(CardModel.model_validate(card))


class TestTheLoaderBoundary:
    def test_both_cards_load(self):
        compile_(json_card(COMMAND))
        compile_(json_card(INTERVENTION))

    def test_x_needs_an_x_in_the_cost(self):
        card = json_card(INTERVENTION)
        card["mana_cost"] = "{W}{W}"
        with pytest.raises(DslError, match=r"needs an \{X\} in the card's mana cost"):
            compile_(card)

    def test_optional_beside_x_is_refused(self):
        card = json_card(INTERVENTION)
        card["targets"][0]["optional"] = True
        with pytest.raises(DslError, match="X-sized mode-owned target"):
            compile_(card)

    def test_another_computed_size_is_still_refused(self):
        card = json_card(INTERVENTION)
        card["targets"][0]["count"] = {"const": 2}
        with pytest.raises(DslError, match="computed 'count' only works"):
            compile_(card)

    def test_x_on_a_triggered_mode_target_is_refused(self):
        """A trigger declares its mode-owned targets with no announced X."""
        ability = {
            "kind": "triggered",
            "text": "Whenever you cast a creature spell, choose one.",
            "trigger": {"event": "spell_cast", "controller": "you"},
            "targets": [
                {"id": "feared", "kind": "permanent", "mode": 0, "count": {"x": True},
                 "up_to": True, "selector": {"zone": "battlefield", "types": ["Creature"]}},
            ],
            "effects": [
                {"op": "choose_mode", "count": 1, "modes": [
                    {"label": "fear", "effects": [
                        {"op": "grant_keyword", "objects": {"target": "feared"},
                         "keywords": ["fear"], "duration": "until_end_of_turn"}]},
                    {"label": "draw", "effects": [{"op": "draw"}]},
                ]},
            ],
        }
        card = {
            "id": "x_modal_trigger",
            "name": "X Modal Trigger",
            "mana_cost": "{X}",
            "types": ["Artifact"],
            "abilities": [ability],
        }
        with pytest.raises(DslError, match="size must be printed"):
            compile_(card)
