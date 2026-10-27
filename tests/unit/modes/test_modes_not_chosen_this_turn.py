""""Choose one that hasn't been chosen this turn —"

    Parapet Thrasher — "Whenever one or more Dragons you control deal combat
    damage to an opponent, choose one that hasn't been chosen this turn —
    • Destroy target artifact that opponent controls. • This creature deals 4
    damage to each other opponent. • Exile the top card of your library. You may
    play it this turn."

`choose_mode`'s `once_each: true` is Henrika Domnathi's "hasn't been chosen":
the spent modes are flags on the source and stay spent for the object's whole
life. Written that way Parapet Thrasher runs out of modes after its first turn
and is a much weaker card. `once_each: "turn"` keeps the strike-off and moves
the record to `TurnLedger.modes_chosen`, so the modes come back at the turn
boundary.

Three rules decide where the record is written and when it is dropped:

- **603.3c: the mode is chosen as the trigger is put on the stack.** Hit two
  opponents in one step and two triggers go on the stack together; the second
  is asked after the first has spent its mode, so the two cannot take the same
  one. Recording at resolution would offer it twice.
- **The ruling on the fourth firing**: once every mode is spent, a later
  instance chooses nothing and does nothing.
- **400.7: a permanent that leaves and comes back is a new object**, which has
  chosen nothing, though it keeps its oid. The record is dropped at that zone
  change.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer, oids_of, only_oid

ROTATION = "t_mtt_rotation"  # Parapet Thrasher's line on an enchantment
WYRM = "t_bcd_wyrm"  # 2/2 Wyrm
DRAIN = "That player loses 5 life"
GAIN = "You gain 3 life"
DRAW = "Draw a card"
ALL = [DRAIN, GAIN, DRAW]


def pod(builder, *, wyrms: int = 1, players: int = 3):
    """We are seat 0 with the rotation and some Wyrms, in our main phase.

    The Dark Ritual is a priority stop: with nothing but Pass legal the engine
    passes for us, and would run on past postcombat main into the next turn,
    whose cleanup has already cleared the ledger this file is about.
    """
    game = builder(players=players).battlefield(0, ["swamp", ROTATION] + [WYRM] * wyrms)
    for seat in range(players):
        game = game.library(seat, ["swamp"] * 30)
    return game.hand(0, ["dark_ritual"]).step(Step.PRECOMBAT_MAIN).active(0).max_turns(40).build()


def drive(game, until, picks: list[str] | None = None) -> list[list[str]]:
    """Play forward to ``until``, answering each mode choice from ``picks``.

    Returns the labels offered at each mode choice, in order. A choice with a
    pick not on offer takes the first label offered.
    """
    picks = list(picks or [])
    offers: list[list[str]] = []
    for _ in range(800):
        if until(game) or game.over:
            return offers
        decision = game.pending()
        if decision is None:
            return offers
        if decision.kind is DecisionKind.CHOOSE_MODE:
            labels = [o.label for o in decision.options]
            offers.append(labels)
            want = picks.pop(0) if picks else labels[0]
            index = labels.index(want) if want in labels else 0
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == index
                )
            )
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("drive did not reach its condition")


def swing(game, plan: dict[int, int], picks: list[str] | None = None) -> list[list[str]]:
    """Declare each attacker (oid) at its seat, then run past combat damage."""
    drive(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
    for attacker, seat in plan.items():
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == attacker
                and any(ref.kind == "player" and ref.id == seat for ref in a.targets)
            )
        )
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
    )
    mark = (game.state.turn, Step.POSTCOMBAT_MAIN)
    return drive(game, lambda g: (g.state.turn, g.state.step) >= mark, picks)


def rotation(game) -> int:
    return only_oid(game, ROTATION, 0)


def spent(game) -> set[str]:
    return game.state.turn_ledger.chosen_modes(rotation(game))


class TestASpentModeIsStruckOffForTheTurn:
    def test_every_mode_is_offered_first(self, builder):
        game = pod(builder)
        offers = swing(game, {only_oid(game, WYRM, 0): 1}, [GAIN])
        assert len(offers) == 1
        assert sorted(offers[0]) == sorted(ALL)

    def test_the_chosen_mode_is_recorded_for_the_turn(self, builder):
        game = pod(builder)
        swing(game, {only_oid(game, WYRM, 0): 1}, [GAIN])
        assert spent(game) == {GAIN}
        assert game.state.players[0].life == 40 + 3

    def test_it_is_not_a_life_long_flag(self, builder):
        """The near miss, `once_each: true`, writes onto the source's flags."""
        game = pod(builder)
        swing(game, {only_oid(game, WYRM, 0): 1}, [GAIN])
        assert not any(f.startswith("mode_chosen:") for f in game.state.objects[rotation(game)].flags)


class TestTwoTriggersPutOnTheStackTogether:
    def test_the_second_is_not_offered_the_firsts_mode(self, builder):
        """603.3c: each trigger's mode is chosen as it goes on the stack, so the
        second is asked after the first's answer is spent."""
        game = pod(builder, wyrms=2)
        first, second = oids_of(game, WYRM, 0)
        offers = swing(game, {first: 1, second: 2}, [DRAIN, DRAIN])
        assert len(offers) == 2
        assert sorted(offers[0]) == sorted(ALL)
        assert sorted(offers[1]) == sorted([GAIN, DRAW])
        assert spent(game) == {DRAIN, GAIN}

    def test_both_resolve_with_their_own_mode(self, builder):
        game = pod(builder, wyrms=2)
        first, second = oids_of(game, WYRM, 0)
        swing(game, {first: 1, second: 2}, [DRAIN, GAIN])
        drained = [game.state.players[seat].life for seat in (1, 2)]
        assert sorted(drained) == [40 - 2 - 5, 40 - 2]
        assert game.state.players[0].life == 40 + 3


class TestTheTurnRunsOut:
    def test_with_every_mode_spent_a_firing_does_nothing(self, builder):
        """The printed ruling: past the third, no mode can be chosen, and the
        instance is removed from the stack and does nothing."""
        game = pod(builder)
        oid = rotation(game)
        for label in ALL:
            game.state.turn_ledger.mode_chosen(oid, label)
        hand = len(game.state.players[0].hand)

        offers = swing(game, {only_oid(game, WYRM, 0): 1})

        assert offers == []
        assert game.state.players[1].life == 40 - 2
        assert game.state.players[0].life == 40
        assert len(game.state.players[0].hand) == hand

    def test_the_last_mode_left_is_taken_without_asking(self, builder):
        game = pod(builder)
        oid = rotation(game)
        game.state.turn_ledger.mode_chosen(oid, GAIN)
        game.state.turn_ledger.mode_chosen(oid, DRAW)

        swing(game, {only_oid(game, WYRM, 0): 1})

        assert game.state.players[1].life == 40 - 2 - 5


class TestTheModesComeBack:
    def test_next_turn_every_mode_is_offered_again(self, builder):
        game = pod(builder)
        swing(game, {only_oid(game, WYRM, 0): 1}, [GAIN])
        turn = game.state.turn
        drive(
            game,
            lambda g: g.state.turn > turn
            and g.state.active_player == 0
            and g.state.step is Step.PRECOMBAT_MAIN,
        )
        assert spent(game) == set()

        offers = swing(game, {only_oid(game, WYRM, 0): 1}, [GAIN])

        assert sorted(offers[0]) == sorted(ALL)

    def test_a_new_object_has_chosen_nothing(self, builder):
        """400.7. The oid survives the zone change; the record must not."""
        from commanderblitz.engine.zones import destroy

        game = pod(builder)
        oid = rotation(game)
        game.state.turn_ledger.mode_chosen(oid, GAIN)

        destroy(game.state, oid)

        assert game.state.turn_ledger.chosen_modes(oid) == set()


def _card(abilities=None, spell_effects=None, types=("Enchantment",)) -> CardModel:
    body = {
        "id": "t_bad_once_each_turn",
        "name": "Bad Once Each Turn",
        "mana_cost": "{1}",
        "types": list(types),
        "oracle_text": "Choose one that hasn't been chosen this turn —",
    }
    if abilities is not None:
        body["abilities"] = abilities
    if spell_effects is not None:
        body["spell_effects"] = spell_effects
    return CardModel.model_validate(body)


def _modes(once_each) -> dict:
    return {
        "op": "choose_mode",
        "count": 1,
        "once_each": once_each,
        "modes": [
            {"label": "A", "effects": [{"op": "draw", "player": "you"}]},
            {"label": "B", "effects": [{"op": "draw", "player": "you"}]},
        ],
    }


class TestTheLoader:
    def test_a_spell_is_refused(self):
        with pytest.raises(DslError, match="remembers nothing"):
            compile_card(_card(spell_effects=[_modes("turn")], types=("Instant",)))

    def test_an_activated_ability_is_refused(self):
        """602.2b answers its modes in `Game._ask_modes`, which strikes nothing
        off -- Kargan Intimidator would offer every bullet every time."""
        ability = {"kind": "activated", "text": "{1}: …", "cost": {"mana": "{1}"}, "effects": [_modes("turn")]}
        with pytest.raises(DslError, match="activated ability"):
            compile_card(_card(abilities=[ability]))

    def test_any_other_lifetime_is_refused(self):
        trigger = {
            "kind": "triggered",
            "text": "…",
            "trigger": {"event": "upkeep", "controller": "you"},
            "effects": [_modes("game")],
        }
        with pytest.raises(DslError, match="once_each"):
            compile_card(_card(abilities=[trigger]))

    def test_the_rotation_loads(self, registry):
        assert registry.get(ROTATION).abilities[0].effects[0]["once_each"] == "turn"
