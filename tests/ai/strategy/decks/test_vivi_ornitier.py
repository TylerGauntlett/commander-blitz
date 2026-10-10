"""Vivi Ornitier: the auras go on Vivi, spells never hit home, the Reservoir kills."""

from __future__ import annotations

from commanderblitz.ai.agents.heuristic_agent import HeuristicAgent
from commanderblitz.ai.strategy.archetypes import Spellslinger
from commanderblitz.engine.enums import ActionKind
from tests.conftest import only_oid

DECK = "vivi_ornitier"


def make_commander(game, seat: int, card_id: str) -> int:
    oid = only_oid(game, card_id, seat)
    game.state.objects[oid].is_commander = True
    game.state.players[seat].commanders.append(oid)
    return oid


def test_curiosity_goes_on_vivi_not_the_other_creature(builder):
    game = (
        builder()
        .deck(0, DECK)
        .hand(0, ["curiosity"])
        .battlefield(0, ["t_bear", "vivi_ornitier", "island"])
        .battlefield(1, ["t_bear"])
        .build()
    )
    vivi = make_commander(game, 0, "vivi_ornitier")
    chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
    assert chosen.kind is ActionKind.CAST
    assert game.state.objects[chosen.source].def_id == "curiosity"
    assert [ref.id for ref in chosen.targets] == [vivi]


def test_curiosity_waits_for_vivi(builder):
    game = (
        builder()
        .deck(0, DECK)
        .hand(0, ["curiosity"])
        .battlefield(0, ["t_bear", "island"])
        .build()
    )
    chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
    assert chosen.kind is ActionKind.PASS


def test_bounce_is_held_with_only_our_own_creature_to_hit(builder):
    game = (
        builder()
        .deck(0, DECK)
        .hand(0, ["ice_magic"])
        .battlefield(0, ["t_bear", "island", "mountain", "mountain"])
        .build()
    )
    # Ice Magic is a noncreature spell, and the plain spellslinger casts it at
    # the only creature there is: our own.
    plain = HeuristicAgent(0, strategy=Spellslinger()).act(game, 0, game.legal_actions())
    assert plain.kind is ActionKind.CAST
    chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
    assert chosen.kind is ActionKind.PASS


def test_the_reservoir_fires_before_anything_else(builder):
    game = (
        builder()
        .deck(0, DECK)
        .hand(0, ["archmage_emeritus"])
        .battlefield(0, ["aetherflux_reservoir"] + ["island"] * 4)
        .battlefield(1, ["t_big"])
        .life(0, 80)
        .build()
    )
    chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
    assert chosen.kind is ActionKind.ACTIVATE
    assert game.state.objects[chosen.source].def_id == "aetherflux_reservoir"
    assert [(ref.kind, ref.id) for ref in chosen.targets] == [("player", 1)]
