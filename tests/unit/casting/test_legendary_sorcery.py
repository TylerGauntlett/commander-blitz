"""A legendary instant or sorcery needs a legend of yours to be cast.

    Urza's Ruinous Blast -- "(You may cast a legendary sorcery only if you
    control a legendary creature or planeswalker.) Exile all nonland
    permanents that aren't legendary."

205.4e: "A player can't cast a legendary instant or sorcery spell unless that
player controls a legendary creature or a legendary planeswalker." Without it
the Blast is a one-sided wrath anyone can cast for five. The restriction is
read off the printed supertype, so a card needs no key of its own, and it is a
"can't" asked in `player_statics.player_cant_cast_spells`, the question every
cast path asks (601.3). The legend is read off the derived characteristics: a
legendary artifact that is not a creature does not count.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.player_statics import (
    controls_a_legend_that_casts,
    player_cant_cast_spells,
)

BLAST = "t_lsor_blast"
INSTANT = "t_lsor_instant"
LEGEND = "t_lsor_legend"
RELIC = "t_lsor_relic"
WALKER = "t_patient_walker"


def board(builder, own: list[str], *, spell: str = BLAST, theirs: list[str] = ()):
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 2 + own)
        .battlefield(1, list(theirs))
        .hand(0, [spell])
        .build()
    )


def castable(game, card_id: str = BLAST) -> bool:
    return any(
        a.kind is ActionKind.CAST
        and a.source is not None
        and game.state.objects[a.source].def_id == card_id
        for a in game.legal_actions()
    )


class TestWithoutALegend:
    @pytest.mark.parametrize("spell", [BLAST, INSTANT])
    def test_it_cannot_be_cast(self, builder, spell):
        assert not castable(board(builder, [], spell=spell), spell)

    def test_a_legendary_noncreature_artifact_does_not_count(self, builder):
        assert not castable(board(builder, [RELIC]))

    def test_an_opponents_legend_does_not_count(self, builder):
        assert not castable(board(builder, [], theirs=[LEGEND]))


class TestWithALegend:
    @pytest.mark.parametrize("spell", [BLAST, INSTANT])
    def test_a_legendary_creature_lets_it_be_cast(self, builder, spell):
        assert castable(board(builder, [LEGEND], spell=spell), spell)

    def test_a_legendary_planeswalker_lets_it_be_cast(self, builder):
        assert castable(board(builder, [WALKER]))


class TestTheQuestion:
    def test_it_is_the_lock_every_cast_path_asks(self, builder, registry):
        game = board(builder, [])
        assert player_cant_cast_spells(game.state, 0, registry.get(BLAST))
        assert not controls_a_legend_that_casts(game.state, 0)

    def test_a_nonlegendary_sorcery_is_never_locked_by_it(self, builder, registry):
        game = board(builder, [])
        assert not player_cant_cast_spells(game.state, 0, registry.get("divination"))

    def test_a_legendary_permanent_spell_is_not_restricted(self, builder, registry):
        game = board(builder, [], spell=LEGEND)
        assert castable(game, LEGEND)
