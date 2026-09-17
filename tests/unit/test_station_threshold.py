"""Station symbols -- an ability a permanent has only at N or more charge counters.

    Rule 721 (station cards): each station symbol means "As long as this
    permanent has N or more charge counters on it, it has [abilities]."

    Uthros, Titanic Godcore -- "12+ | {U}, {T}: Add {U} for each artifact you
    control."
    Adagia, Windswept Bastion -- "12+ | {3}{W}, {T}: Create a token that's a
    copy of target artifact or enchantment you control, except it's legendary.
    Activate only as a sorcery."

The claim is **existence**, not permission. `condition` on an activated ability
("activate only if…") was the near miss: it refuses the activation of an ability
the permanent still has. Uthros's gated line is a mana ability, and the payment
solver and the by-hand mana path never ask legality -- so a refusal written there
is a Planet tapping for a pile of blue mana on turn one. Below the number the
ability is simply not in `abilities_of`, which every reader asks: legality, the
mana solver, the AI and the client's action list.

Indices have to survive that. An action and a stack item name an ability by
position, and resolution reads the printed list at that position, so the loader
keeps gated abilities at the end and in rising order: an absent ability only
ever takes the ones after it with it.

Once activated, the ability is independent of its source (113.7a), so losing
the counters in response does not stop it resolving.

`t_station_planet` carries a 4+ draw and a 12+ mana ability on top of the
Station cost from `test_station.py`.
"""

from __future__ import annotations

import copy

import pytest

from automtg.cards.authoring.verify import residual_text
from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import abilities_of
from automtg.engine.enums import ActionKind, Zone
from automtg.engine.mana import SYMBOLS
from automtg.engine.primitives import remove_counters
from tests.conftest import only_oid, pass_until

PLANET = "t_station_planet"
STATION, DRAW, MANA = 1, 2, 3


def position(builder, charge: int, *, artifacts: int = 0, respond: bool = False):
    """The Planet with ``charge`` counters, two Islands, a Bear and ``artifacts`` Sol Rings.

    ``respond`` hands the opponent a castable Bolt, so a window with the draw
    ability on the stack is a real one rather than passed automatically.
    """
    b = (
        builder(players=2)
        .battlefield(0, [PLANET], counters={"charge": charge} if charge else None)
        .battlefield(0, ["island", "island"])
        .battlefield(0, ["sol_ring"] * artifacts)
        .battlefield(0, ["t_bear"])
        .library(0, ["island"] * 20)
        .library(1, ["island"] * 20)
    )
    if respond:
        b = b.hand(1, ["t_bolt"]).battlefield(1, ["mountain"])
    game = b.build()
    return game, only_oid(game, PLANET)


def offered(game, planet: int, index: int):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE and a.source == planet and a.ability_index == index
    ]


def indices(game, planet: int) -> list[int]:
    return [a.index for a in abilities_of(game.state, planet)]


class TestBelowTheNumberTheAbilityIsAbsent:
    def test_with_no_counters_only_the_unstriated_abilities_exist(self, builder):
        game, planet = position(builder, 0)
        assert indices(game, planet) == [0, STATION]

    def test_one_short_of_four_is_still_absent(self, builder):
        game, planet = position(builder, 3)
        assert DRAW not in indices(game, planet)
        assert not offered(game, planet, DRAW)

    def test_exactly_four_has_it(self, builder):
        game, planet = position(builder, 4)
        assert indices(game, planet) == [0, STATION, DRAW]
        assert offered(game, planet, DRAW)

    def test_eleven_has_the_four_but_not_the_twelve(self, builder):
        game, planet = position(builder, 11, artifacts=1)
        assert MANA not in indices(game, planet)
        assert not offered(game, planet, MANA)

    def test_twelve_has_both_at_their_printed_positions(self, builder):
        """Indices are the printed ones -- the action and the stack item agree."""
        game, planet = position(builder, 12, artifacts=1)
        assert indices(game, planet) == [0, STATION, DRAW, MANA]
        assert offered(game, planet, MANA)

    def test_station_is_still_offered_past_the_last_number(self, builder):
        """721: the station ability is had at all times; more counters are legal."""
        game, planet = position(builder, 12)
        assert offered(game, planet, STATION)

    def test_a_card_off_the_battlefield_has_no_striations(self, builder):
        game = builder(players=2).hand(0, [PLANET]).build()
        card = next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == PLANET)
        assert game.state.objects[card].zone is Zone.HAND
        assert indices(game, card) == [0, STATION]


class TestTheCountersComeAndGo:
    def test_losing_counters_takes_the_ability_away(self, builder):
        """Proliferate or removal changes what it has, both ways (release notes)."""
        game, planet = position(builder, 12, artifacts=1)
        remove_counters(game.state, planet, "charge", 1)
        assert MANA not in indices(game, planet)
        assert DRAW in indices(game, planet)

    def test_an_activated_ability_resolves_after_the_counters_are_gone(self, builder):
        """113.7a: once on the stack it is independent of its source."""
        game, planet = position(builder, 4, respond=True)
        hand_before = len(game.state.players[0].hand)
        game.apply(offered(game, planet, DRAW)[0])
        assert game.state.stack, "the draw ability should be waiting on the stack"

        remove_counters(game.state, planet, "charge", 4)
        pass_until(game, lambda g: not g.state.stack)

        assert len(game.state.players[0].hand) == hand_before + 1


class TestTheGatedManaAbility:
    def test_at_twelve_it_adds_one_blue_per_artifact(self, builder):
        game, planet = position(builder, 12, artifacts=3)
        game.apply(offered(game, planet, MANA)[0])
        pool = game.state.players[0].mana_pool
        assert pool.total() == 3 and pool.amounts[SYMBOLS.index("U")] == 3

    def test_below_twelve_the_by_hand_mana_path_does_not_have_it(self, builder):
        game, planet = position(builder, 11, artifacts=3)
        game.state.players[0].manual_mana = True
        assert not offered(game, planet, MANA)


def _planet(**changes) -> dict:
    card = copy.deepcopy(
        {
            "id": "t_planet_guard",
            "name": "Test Planet Guard",
            "oracle_text": "{T}: Add {C}.\n4+ | {T}: Draw a card.",
            "types": ["Land"],
            "abilities": [
                {
                    "kind": "activated",
                    "text": "{T}: Add {C}.",
                    "cost": {"tap": True},
                    "is_mana_ability": True,
                    "effects": [{"op": "add_mana", "mana": "{C}"}],
                },
                {
                    "kind": "activated",
                    "text": "4+ | {T}: Draw a card.",
                    "threshold": {"counter": "charge", "at_least": 4},
                    "cost": {"tap": True},
                    "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                },
            ],
        }
    )
    for key, value in changes.items():
        card[key] = value
    return card


def _load(card: dict):
    return compile_card(CardModel.model_validate(card))


class TestLoadTimeGuards:
    def test_the_printed_shape_loads(self):
        assert _load(_planet()).abilities[1].threshold == ("charge", 4)

    def test_an_ungated_ability_after_a_gated_one_is_refused(self):
        """It would shift position whenever the gated one is absent."""
        card = _planet()
        card["abilities"].reverse()
        with pytest.raises(DslError, match="gated abilities come last"):
            _load(card)

    def test_falling_thresholds_are_refused(self):
        card = _planet()
        later = copy.deepcopy(card["abilities"][1])
        later["threshold"] = {"counter": "charge", "at_least": 2}
        card["abilities"].append(later)
        with pytest.raises(DslError, match="rising order"):
            _load(card)

    def test_zero_is_refused(self):
        card = _planet()
        card["abilities"][1]["threshold"]["at_least"] = 0
        with pytest.raises(DslError, match="positive number"):
            _load(card)

    def test_an_unknown_key_is_refused(self):
        card = _planet()
        card["abilities"][1]["threshold"]["at_most"] = 8
        with pytest.raises(DslError, match="unsupported keys"):
            _load(card)

    def test_a_gated_trigger_is_refused_rather_than_always_on(self):
        card = _planet()
        card["abilities"][1] = {
            "kind": "triggered",
            "text": "4+ | At the beginning of your upkeep, draw a card.",
            "threshold": {"counter": "charge", "at_least": 4},
            "trigger": {"event": "upkeep"},
            "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
        }
        with pytest.raises(DslError, match="only an activated ability"):
            _load(card)


class TestTheResidualGate:
    def test_the_striated_card_claims_every_line(self, registry):
        card = registry.get(PLANET)
        assert residual_text(card, card.oracle_text).strip() == ""

    def test_an_ungated_ability_cannot_claim_a_striation(self):
        """The loose substring match would let "{T}: Draw a card." claim
        "4+ | {T}: Draw a card." -- a Planet drawing from turn one."""
        card = _planet()
        del card["abilities"][1]["threshold"]
        card["abilities"][1]["text"] = "{T}: Draw a card."
        loaded = _load(card)
        assert "4+" in residual_text(loaded, loaded.oracle_text)

    def test_a_gate_at_another_number_cannot_claim_it(self):
        card = _planet()
        card["abilities"][1]["threshold"]["at_least"] = 2
        card["abilities"][1]["text"] = "4+ | {T}: Draw a card."
        loaded = _load(card)
        assert "4+" in residual_text(loaded, loaded.oracle_text)
