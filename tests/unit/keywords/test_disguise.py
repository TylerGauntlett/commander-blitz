"""Disguise (702.168a) -- morph whose face-down permanent has ward {2}.

    Disguise {G} -- "You may cast this card face down for {3} as a 2/2 creature
    with ward {2}. Turn it face up any time for its disguise cost."

Read against what the engine already had, that is **morph plus cloak's ward**.
Morph ships the face-down cast for a fixed {3}, the 2/2 shell and the turn-up
for the printed price; cloak ships ward {2} on a face-down shell, supplied by
the rule because 707.2 leaves the permanent no abilities of its own. So the card
field `disguise` loads as `morph` holding the disguise cost plus a flag, and the
permanent cast face down with it is marked `disguised`, which reads the same
`CLOAK_WARD` a cloaked one does.

Written as plain `morph` -- the shortcut that loads and plays -- Nervous
Gardener's shell would be free to remove, and a disguise land or enchantment
(Branch of Vitu-Ghazi, True Identity) would be refused, since morph is only on
creature cards. Disguise is printed on any permanent card, and a land card is
then cast: what goes on the stack is a 2/2 creature spell (601.3e), so
`_cast_actions` offers the face-down line for a land card in hand.

The ward is the cast's, not the card's: a disguise card that is manifested
instead turns up for its disguise cost (701.34a) but has no ward.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.authoring.packet import CARD_LEVEL_COST_KEYS
from commanderblitz.cards.authoring.verify import residual_text
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import pass_until

DISGUISER = "t_disguiser"  # {4}{G} 5/5 flier, disguise {G}
LAND = "t_disguised_land"  # "{T}: Add {C}." and disguise {3}
MORPHER = "t_morpher"  # {4}{G} 5/5 flier, morph {2}{G} -- the near miss
BOLT = "t_bolt"  # a targeted removal spell for the opponent to try

REMINDER = (
    " (You may cast this card face down for {3} as a 2/2 creature with ward {2}. "
    "Turn it face up any time for its disguise cost.)"
)


def board(builder, card: str = DISGUISER, lands: int = 4):
    """Forests for the {3} and the {G}; Mountains for the opponent's bolt."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * lands)
        .battlefield(1, ["mountain"] * 5)
        .hand(0, [card])
        .hand(1, [BOLT])
        .library(0, ["forest"] * 20)
        .library(1, ["mountain"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    oid = game.state.players[0].hand[0]
    return game, oid


def cast_face_down(game, oid: int) -> None:
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and a.source == oid and a.face_down
        )
    )
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def turn_up(game, oid: int):
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == oid
        ),
        None,
    )


def bolt_it(game, oid: int) -> None:
    """The opponent points their removal at the shell."""

    def bolt(g):
        return next(
            (
                a
                for a in g.legal_actions()
                if a.kind is ActionKind.CAST
                and g.state.objects[a.source].def_id == BOLT
                and any(ref.id == oid for ref in a.targets)
            ),
            None,
        )

    pass_until(game, lambda g: bolt(g) is not None)
    game.apply(bolt(game))


class TestCastingFaceDown:
    def test_the_face_down_line_costs_three(self, builder):
        game, _ = board(builder, lands=3)
        lines = [a for a in game.legal_actions() if a.kind is ActionKind.CAST]
        assert [a.face_down for a in lines] == [True], "{3} is payable, {4}{G} is not"

    def test_it_arrives_as_a_two_two_with_nothing_else(self, builder):
        game, oid = board(builder)
        cast_face_down(game, oid)
        obj = game.state.objects[oid]
        c = chars(game.state, oid)
        assert obj.zone is Zone.BATTLEFIELD and obj.face_down and obj.disguised
        assert (c.power, c.toughness) == (2, 2)
        assert c.types == frozenset({"Creature"})
        assert "flying" not in c.keywords

    def test_a_land_card_is_cast_face_down(self, builder):
        """Branch of Vitu-Ghazi: a land card with disguise is castable."""
        game, oid = board(builder, card=LAND, lands=3)
        lines = [a for a in game.legal_actions() if a.source == oid]
        assert [(a.kind, a.face_down) for a in lines if a.kind is ActionKind.CAST] == [
            (ActionKind.CAST, True)
        ]
        assert any(a.kind is ActionKind.PLAY_LAND for a in lines), "and still playable"
        cast_face_down(game, oid)
        assert game.state.objects[oid].face_down
        assert chars(game.state, oid).types == frozenset({"Creature"})

    def test_a_land_card_is_cast_at_sorcery_speed(self, builder):
        game, oid = board(builder, card=LAND, lands=3)
        game.state.step = Step.UPKEEP
        assert not [
            a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid
        ]


class TestTheWard:
    def test_targeting_it_asks_the_opponent_to_pay(self, builder):
        game, oid = board(builder)
        cast_face_down(game, oid)
        bolt_it(game, oid)
        pass_until(
            game, lambda g: (d := g.pending()) is not None and d.kind is DecisionKind.MAY
        )
        assert game.pending().player == 1, "the ward taxes the caster, not its controller"

    def test_declining_the_tax_counters_the_spell(self, builder):
        game, oid = board(builder)
        cast_face_down(game, oid)
        bolt_it(game, oid)
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD

    def test_a_morph_would_not(self, builder):
        """The near miss: the same shell cast with morph has no ward."""
        game, oid = board(builder, card=MORPHER)
        cast_face_down(game, oid)
        assert not game.state.objects[oid].disguised
        bolt_it(game, oid)
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert game.state.objects[oid].zone is not Zone.BATTLEFIELD

    def test_the_ward_goes_when_it_turns_up(self, builder):
        game, oid = board(builder, lands=4)
        cast_face_down(game, oid)
        game.apply(turn_up(game, oid))
        pass_until(game, lambda g: not g.state.objects[oid].face_down)
        assert not game.state.objects[oid].disguised
        assert "flying" in chars(game.state, oid).keywords


class TestTurningItUp:
    def test_it_turns_up_for_the_disguise_cost(self, builder):
        """{3} to cast, then {G} -- not the printed {4}{G} -- to turn up."""
        game, oid = board(builder, lands=4)
        cast_face_down(game, oid)
        assert turn_up(game, oid) is not None

    def test_not_without_the_disguise_cost(self, builder):
        game, oid = board(builder, lands=3)
        cast_face_down(game, oid)
        assert turn_up(game, oid) is None

    def test_a_land_turns_up_into_a_land(self, builder):
        game, oid = board(builder, card=LAND, lands=6)
        cast_face_down(game, oid)
        game.apply(turn_up(game, oid))
        pass_until(game, lambda g: not g.state.objects[oid].face_down)
        assert chars(game.state, oid).types == frozenset({"Land"})
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD


class TestTheLoaderGuards:
    def _card(self, **extra) -> CardModel:
        base = {
            "id": "t_disguise_probe",
            "name": "Disguise Probe",
            "mana_cost": "{4}{G}",
            "types": ["Creature"],
            "power": 5,
            "toughness": 5,
        }
        base.update(extra)
        return CardModel.model_validate(base)

    def test_it_loads_as_morph_with_the_flag(self):
        card = compile_card(self._card(disguise="{G}"))
        assert card.disguise and str(card.morph) == "{G}"

    def test_a_noncreature_may_carry_it(self):
        compile_card(
            self._card(types=["Enchantment"], power=None, toughness=None, disguise="{W}")
        )

    def test_never_beside_morph(self):
        """One face-down cast, one turn-up price."""
        with pytest.raises(DslError, match="'disguise' is its own"):
            compile_card(self._card(disguise="{G}", morph="{G}"))

    def test_megamorph_is_not_a_disguise_rider(self):
        with pytest.raises(DslError, match="needs a 'morph' cost"):
            compile_card(self._card(disguise="{G}", morph_counter=True))

    def test_the_packet_offers_it(self):
        assert "disguise" in CARD_LEVEL_COST_KEYS


class TestThePrintedLineIsClaimed:
    def _card(self, line: str, **extra):
        base = {
            "id": "t_disguise_residual",
            "name": "Disguise Residual",
            "mana_cost": "{4}{G}",
            "oracle_text": line + REMINDER,
            "types": ["Creature"],
            "power": 5,
            "toughness": 5,
            "disguise": "{1}{G}",
        }
        base.update(extra)
        return compile_card(CardModel.model_validate(base))

    def test_the_printed_line_is_claimed(self):
        card = self._card("Disguise {1}{G}")
        assert residual_text(card, card.oracle_text) == ""

    def test_a_different_cost_is_not(self):
        card = self._card("Disguise {2}{G}")
        assert residual_text(card, card.oracle_text) != ""

    def test_the_word_morph_is_not(self):
        card = self._card("Morph {1}{G}")
        assert residual_text(card, card.oracle_text) != ""
