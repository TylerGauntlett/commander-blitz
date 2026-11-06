"""Choosing any number of creatures under a total-power ceiling.

    Slaughter the Strong — "Each player chooses any number of creatures they
    control with total power 4 or less, then sacrifices all other creatures
    they control."

The ceiling is on the **sum** of the chosen set, not on each creature. A
per-creature `power <= 4` filter is the near miss and a different card: it
keeps two 4/4s where the printed card keeps one. `count` is one flat number
and the selector filters creatures one at a time, so neither can say it.

`max_total_power` on `choose_permanents` asks one creature at a time -- the
way crew's `total_power` cost is paid -- offering only the creatures whose
power still fits under what is left, until the chooser is done or nothing
fits. Every set the printed card allows is reachable that way (choose a
negative-power creature first and the room it makes is there for the next),
and no set over the ceiling is. Composed from `ask_objects` through
`pick_from_pool`; no new `DecisionKind`.

Each player chooses for themselves, in APNAP order (`for_each_player`), and
the binding accumulates, so the `sacrifice` that follows spares every
player's survivors with one `exclude_binding`. It is a sacrifice, so an
indestructible creature that was not kept still goes: indestructible
stops destruction (702.12b), not a sacrifice.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import DecisionKind, Step
from commanderblitz.engine.errors import DslError

EFFECTS = [
    {
        "op": "for_each_player",
        "players": "each_player",
        "effects": [
            {
                "op": "choose_permanents",
                "as": "kept",
                "max_total_power": 4,
                "prompt": "Keep creatures with total power 4 or less",
                "objects": {
                    "zone": "battlefield",
                    "controller": {"binding": "each_player"},
                    "types": ["Creature"],
                    "count": "any",
                    "chooser": {"binding": "each_player"},
                },
            }
        ],
    },
    {
        "op": "sacrifice",
        "chooser": "none",
        "objects": {
            "zone": "battlefield",
            "controller": "any",
            "types": ["Creature"],
            "count": "all",
            "exclude_binding": "kept",
        },
    },
]


def position(builder, mine=("t_mayhem_brute", "t_commander", "t_bear", "t_elf", "t_wall"),
             theirs=("t_indestructible", "t_menacer", "t_big")):
    """Player 0: 4/4, 4/4, 2/2, 1/1, 0/4. Player 1: an indestructible 2/2, 3/3, 6/6."""
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .library(0, ["island"] * 5)
        .library(1, ["island"] * 5)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def ids(game, oids) -> list[str]:
    return sorted(game.state.card_of(game.state.objects[o]).id for o in oids)


def resolve(game, picks: dict[int, list[str]]) -> list:
    """Run the effects; each player keeps ``picks[player]`` in order, then is done.

    Returns the questions asked.
    """
    ctx = EffectContext(state=game.state, controller=0)
    gen = execute(ctx, EFFECTS)
    asked = []
    queues = {pid: list(cards) for pid, cards in picks.items()}
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            queue = queues.get(decision.player, [])
            offered = [game.state.card_of(game.state.objects[o.value]).id for o in decision.options]
            answer = [offered.index(queue.pop(0))] if queue else []
            decision = gen.send(answer)
    except StopIteration:
        pass
    return asked


def survivors(game, pid: int) -> list[str]:
    state = game.state
    return ids(
        game,
        [o.oid for o in state.objects.values() if o.on_battlefield and o.controller == pid],
    )


class TestTheCeiling:
    def test_the_total_not_each_creature_is_capped(self, builder):
        """After one 4/4 the other 4/4 is no longer offered."""
        game = position(builder)
        asked = resolve(game, {0: ["t_mayhem_brute"], 1: []})
        second = asked[1]
        assert second.player == 0
        offered = ids(game, [o.value for o in second.options])
        assert "t_commander" not in offered
        assert offered == ["t_wall"]

    def test_only_what_fits_what_is_left_is_offered(self, builder):
        game = position(builder)
        asked = resolve(game, {0: ["t_bear"], 1: []})
        offered = ids(game, [o.value for o in asked[1].options])
        assert offered == ["t_elf", "t_wall"]

    def test_a_zero_power_creature_always_fits(self, builder):
        game = position(builder)
        resolve(game, {0: ["t_mayhem_brute", "t_wall"], 1: []})
        assert survivors(game, 0) == ["t_mayhem_brute", "t_wall"]

    def test_several_small_creatures_up_to_the_total(self, builder):
        game = position(builder)
        resolve(game, {0: ["t_bear", "t_elf", "t_wall"], 1: []})
        assert survivors(game, 0) == ["t_bear", "t_elf", "t_wall"]

    def test_the_chooser_may_keep_nothing(self, builder):
        game = position(builder)
        resolve(game, {0: [], 1: []})
        assert survivors(game, 0) == []

    def test_a_question_is_a_decline_able_one_creature_pick(self, builder):
        game = position(builder)
        (first, *_) = resolve(game, {0: [], 1: []})
        assert first.kind is DecisionKind.CHOOSE_OBJECTS
        assert (first.min_count, first.max_count) == (0, 1)
        assert first.context["purpose"] == "choose_permanents"


class TestEachPlayer:
    def test_each_player_chooses_their_own_in_apnap_order(self, builder):
        game = position(builder)
        asked = resolve(game, {0: [], 1: []})
        assert [d.player for d in asked] == [0, 1]
        theirs = ids(game, [o.value for o in asked[1].options])
        assert theirs == ["t_indestructible", "t_menacer"]

    def test_everyone_elses_survivors_are_spared(self, builder):
        game = position(builder)
        resolve(game, {0: ["t_commander"], 1: ["t_menacer"]})
        assert survivors(game, 0) == ["t_commander"]
        assert survivors(game, 1) == ["t_menacer"]

    def test_indestructible_is_still_sacrificed(self, builder):
        game = position(builder)
        resolve(game, {0: [], 1: ["t_menacer"]})
        assert "t_indestructible" not in survivors(game, 1)
        indestructible = next(
            o for o in game.state.objects.values()
            if game.state.card_of(o).id == "t_indestructible"
        )
        assert indestructible.oid in game.state.players[1].graveyard


class TestTheLoader:
    def test_the_printed_shape_loads(self):
        compile_card(CardModel.model_validate(_card()))

    def test_the_ceiling_needs_count_any(self):
        card = _card()
        card["spell_effects"][0]["effects"][0]["objects"]["count"] = 2
        with pytest.raises(DslError, match="max_total_power"):
            compile_card(CardModel.model_validate(card))

    def test_the_ceiling_refuses_random(self):
        card = _card()
        card["spell_effects"][0]["effects"][0]["objects"]["random"] = True
        with pytest.raises(DslError, match="cannot be random"):
            compile_card(CardModel.model_validate(card))

    def test_the_ceiling_is_only_for_choose_permanents(self):
        card = _card()
        card["spell_effects"][1]["max_total_power"] = 4
        with pytest.raises(DslError, match="caps a choose_permanents choice"):
            compile_card(CardModel.model_validate(card))

    def test_the_ceiling_is_a_value_expression(self):
        card = _card()
        card["spell_effects"][0]["effects"][0]["max_total_power"] = "four"
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(card))


def _card() -> dict:
    import copy

    return {
        "id": "t_slaughter",
        "name": "Test Slaughter",
        "oracle_text": "Each player chooses any number of creatures they control with total "
        "power 4 or less, then sacrifices all other creatures they control.",
        "mana_cost": "{1}{R}{W}",
        "types": ["Sorcery"],
        "spell_effects": copy.deepcopy(EFFECTS),
    }
