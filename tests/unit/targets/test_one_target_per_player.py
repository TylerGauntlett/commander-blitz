"""Turf War -- "When this enchantment enters, **for each player**, put a
contested counter on **target land that player controls**."

601.2c: an ability that targets "for each player" has one target per player
who controls a candidate, and none for a player who controls none. The number
is set by the board as the trigger goes on the stack (603.3d), not by its
controller, so the controller cannot leave a seat out -- their own included,
which is the card's whole drawback -- and no seat gives two. That is
`one_per_player` with ``count: "each"``; the near misses are each a different
card:

* ``count: "any"`` is "up to one target land per player", and lets the
  controller skip their own land;
* a literal ``count`` is the right number in exactly one pod size;
* a `for_each_player` with a non-targeting choice ignores hexproof and shroud.

The picks are asked seat by seat (`stack._ask_one_from_each_seat`), the
controller's own first, each over that seat's whole pool; a seat with a single
candidate is not asked. Hexproof is honoured through `targeting.candidates`: an
opponent whose only land has hexproof is owed no target, while the
controller's own hexproof land is theirs to target.

The witnesses are in `tests/data/one_target_per_player.cards.json`.
"""

from __future__ import annotations

import copy

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.targeting import enumerate_target_tuples
from tests.conftest import action_for_card, find_action, pass_until

TURF = "t_tw_turf"
VEILED = "t_tw_veiled_land"


def board(builder, lands: dict[int, list[str]], *, players: int = 3):
    """Turf in player 0's hand with an Island to cast it; ``lands`` for each seat."""
    game = (
        builder(players=players)
        .battlefield(0, ["island"])
        .hand(0, [TURF])
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
    )
    for pid in range(players):
        game = game.library(pid, ["island"] * 10)
        if lands.get(pid):
            game = game.battlefield(pid, lands[pid])
    return game.build(advance=False)


def contested(game) -> dict[int, list[int]]:
    """Each seat's lands carrying a contested counter."""
    out: dict[int, list[int]] = {}
    for obj in game.state.objects.values():
        if obj.counters.get("contested"):
            out.setdefault(obj.controller, []).append(obj.oid)
    return out


def play(builder, lands, *, players: int = 3, pick=None):
    """Cast Turf and answer every target question.

    ``pick(seat, oids)`` chooses among one seat's pool; the first by default.
    Returns the game and each question as ``(seat, pool, min, max)``.
    """
    game = board(builder, lands, players=players)
    game._advance()
    game.apply(action_for_card(game, ActionKind.CAST, TURF))
    asked: list[tuple[int, list[int], int, int]] = []
    for _ in range(80):
        pending = game.pending()
        if pending is None or (pending.kind is DecisionKind.PRIORITY and not game.state.stack):
            break
        actions = game.legal_actions()
        if pending.kind is DecisionKind.PRIORITY:
            game.apply(next(a for a in actions if a.kind is ActionKind.PASS))
            continue
        assert pending.kind is DecisionKind.CHOOSE_OBJECTS
        choices = [a for a in actions if a.kind is ActionKind.CHOOSE]
        if not choices:
            game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
            continue
        pool = [opt.ref.id for opt in pending.options]
        seats = {game.state.objects[oid].controller for oid in pool}
        assert len(seats) == 1, "one question asks one seat's lands"
        (seat,) = seats
        asked.append((seat, pool, pending.min_count, pending.max_count))
        want = pick(seat, pool) if pick else pool[0]
        game.apply(next(a for a in choices if pending.options[a.choice].ref.id == want))
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
    return game, asked


class TestOneFromEverySeat:
    def test_every_seat_with_a_land_gets_exactly_one(self, builder):
        lands = {0: ["island"], 1: ["island", "island"], 2: ["island", "island"]}
        game, asked = play(builder, lands)
        marked = contested(game)
        assert sorted(marked) == [0, 1, 2]
        assert all(len(oids) == 1 for oids in marked.values())
        assert all((lo, hi) == (1, 1) for _, _, lo, hi in asked)

    def test_the_pick_is_the_controllers_own_choice(self, builder):
        """Each seat's whole pool is offered, not a capped list of sets."""
        lands = {1: ["island"] * 6, 2: ["island"] * 6}
        game, asked = play(builder, lands, pick=lambda seat, pool: pool[-1])
        pools = {seat: pool for seat, pool, _, _ in asked}
        assert len(pools[1]) == len(pools[2]) == 6
        marked = contested(game)
        assert marked[1] == [pools[1][-1]] and marked[2] == [pools[2][-1]]

    def test_a_seat_with_no_land_is_owed_no_target(self, builder):
        lands = {1: ["island", "island"]}
        game, asked = play(builder, lands)
        assert [seat for seat, *_ in asked] == [1]  # player 0's one Island is taken
        marked = contested(game)
        assert sorted(marked) == [0, 1]
        assert 2 not in marked


class TestTheControllersOwnSeat:
    def test_is_asked_first_and_cannot_be_declined(self, builder):
        lands = {0: ["island"], 1: ["island", "island"], 2: ["island"]}
        _, asked = play(builder, lands)
        seat, pool, lo, hi = asked[0]
        assert seat == 0 and len(pool) == 2 and (lo, hi) == (1, 1)

    def test_no_enumerated_set_leaves_it_out(self, builder):
        """The tuple form agrees: every set holds one land of every seat."""
        lands = {1: ["island", "island"], 2: ["island"]}
        game = board(builder, lands)
        card = game.state.registry.get(TURF)
        sets = enumerate_target_tuples(game.state, 0, card.abilities[0].targets, None)
        assert sets
        for refs in sets:
            seats = sorted(game.state.objects[r.id].controller for r in refs)
            assert seats == [0, 1, 2]

    def test_a_lone_own_land_is_taken_without_asking(self, builder):
        game, asked = play(builder, {1: ["island", "island"]}, players=2)
        assert [seat for seat, *_ in asked] == [1]
        assert sorted(contested(game)) == [0, 1]


class TestHexproof:
    def test_an_opponents_hexproof_land_is_not_a_candidate(self, builder):
        lands = {1: [VEILED], 2: ["island"]}
        game, _ = play(builder, lands)
        marked = contested(game)
        assert sorted(marked) == [0, 2]

    def test_the_controllers_own_hexproof_land_is(self, builder):
        lands = {0: [VEILED], 1: ["island"]}
        game, asked = play(builder, lands, players=2, pick=lambda seat, pool: pool[-1])
        (own,) = contested(game)[0]
        assert game.state.objects[own].def_id == VEILED
        assert asked[0][0] == 0 and len(asked[0][1]) == 2

    def test_nobody_with_a_candidate_asks_for_nothing(self, builder):
        """Every land out of reach: the ability declares no target at all --
        not a set with nobody in it, and not "no legal choice"."""
        game = builder(players=2).battlefield(1, [VEILED]).build(advance=False)
        specs = game.state.registry.get(TURF).abilities[0].targets
        assert enumerate_target_tuples(game.state, 0, specs, None) == [()]


CARD = {
    "id": "t_tw_probe",
    "name": "Test Turf Probe",
    "oracle_text": "When this enchantment enters, for each player, put a contested counter on target land that player controls.",
    "mana_cost": "{U}",
    "types": ["Enchantment"],
    "abilities": [
        {
            "kind": "triggered",
            "trigger": {"event": "self_enters", "source": "self"},
            "targets": [
                {
                    "id": "t1",
                    "kind": "permanent",
                    "count": "each",
                    "one_per_player": True,
                    "selector": {"zone": "battlefield", "types": ["Land"], "controller": "any"},
                }
            ],
            "effects": [
                {
                    "op": "add_counters",
                    "counter": "contested",
                    "amount": {"const": 1},
                    "objects": {"target": "t1"},
                }
            ],
        }
    ],
}


def _compile(card=None, **overrides):
    card = copy.deepcopy(card or CARD)
    card["abilities"][0]["targets"][0].update(overrides)
    return compile_card(CardModel.model_validate(card))


class TestTheLoader:
    def test_each_loads(self):
        (spec,) = _compile().abilities[0].targets
        assert spec.one_per_player and spec.count == "each" and spec.variable_size

    def test_each_needs_one_per_player(self):
        with pytest.raises(DslError, match="one_per_player"):
            _compile(one_per_player=False)

    @pytest.mark.parametrize("extra", [{"optional": True}, {"up_to": True}])
    def test_each_takes_no_other_size(self, extra):
        with pytest.raises(DslError, match="each"):
            _compile(**extra)

    def test_a_spells_targets_are_refused(self):
        card = copy.deepcopy(CARD)
        card["types"] = ["Sorcery"]
        ability = card.pop("abilities")[0]
        card["targets"] = ability["targets"]
        card["spell_effects"] = ability["effects"]
        with pytest.raises(DslError, match="triggered or reflexive"):
            compile_card(CardModel.model_validate(card))

    def test_an_activated_abilitys_targets_are_refused(self):
        card = copy.deepcopy(CARD)
        ability = card["abilities"][0]
        ability["kind"] = "activated"
        ability.pop("trigger")
        ability["cost"] = {"mana": "{1}"}
        with pytest.raises(DslError, match="triggered or reflexive"):
            compile_card(CardModel.model_validate(card))

    def test_a_second_target_is_refused(self):
        card = copy.deepcopy(CARD)
        card["abilities"][0]["targets"].insert(
            0, {"id": "who", "kind": "player", "count": 1}
        )
        with pytest.raises(DslError, match="only target"):
            compile_card(CardModel.model_validate(card))
