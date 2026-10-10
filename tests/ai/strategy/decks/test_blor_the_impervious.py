"""Blor the Impervious: everything goes on the frog, and the frog blocks."""

from __future__ import annotations

from commanderblitz.ai.agents.heuristic_agent import HeuristicAgent
from commanderblitz.ai.strategy.archetypes import Voltron
from commanderblitz.ai.strategy.decks.blor_the_impervious import STRATEGY
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.structs import TargetRef
from tests.conftest import find_action, only_oid, pass_until

DECK = "blor_the_impervious"


def make_commander(game, seat: int, card_id: str) -> int:
    oid = only_oid(game, card_id, seat)
    game.state.objects[oid].is_commander = True
    game.state.players[seat].commanders.append(oid)
    return oid


def test_the_sword_goes_on_blor_not_the_elf(builder):
    game = (
        builder()
        .deck(0, DECK)
        .battlefield(0, ["blor_the_impervious", "llanowar_elves", "sword_of_fire_and_ice"])
        .battlefield(0, ["forest"] * 2)
        .build()
    )
    blor = make_commander(game, 0, "blor_the_impervious")
    chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
    assert chosen.kind is ActionKind.ACTIVATE
    assert [ref.id for ref in chosen.targets] == [blor]


def test_tanuki_reconfigures_onto_blor(builder):
    game = (
        builder()
        .deck(0, DECK)
        .battlefield(0, ["blor_the_impervious", "tanuki_transplanter"])
        .battlefield(0, ["forest"] * 3)
        .hand(0, ["high_score"])
        .build()
    )
    blor = make_commander(game, 0, "blor_the_impervious")
    # Reconfigure is an attach that is not an equip ability; Voltron treats it
    # as one, and spends the mana on Blor rather than on the enchantment.
    chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
    assert chosen.kind is ActionKind.ACTIVATE
    assert game.state.objects[chosen.source].def_id == "tanuki_transplanter"
    assert [ref.id for ref in chosen.targets] == [blor]


def test_indestructible_blor_blocks_where_plain_voltron_would_not(builder):
    game = (
        builder()
        .deck(1, DECK)
        .battlefield(0, ["t_big"])
        .battlefield(1, ["blor_the_impervious"])
        .active(0)
        .build()
    )
    blor = make_commander(game, 1, "blor_the_impervious")
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
    big = only_oid(game, "t_big", 0)
    game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=big, targets=(TargetRef.player(1),)))
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS)

    plain = HeuristicAgent(1, strategy=Voltron()).act(game, 1, game.legal_actions())
    assert plain.kind is ActionKind.FINISH_DECLARATION, "Voltron keeps its commander out of blocks"
    chosen = HeuristicAgent(1).act(game, 1, game.legal_actions())
    assert chosen.kind is ActionKind.ADD_BLOCKER
    assert chosen.source == blor


def test_two_lands_needs_a_dork_to_keep(builder):
    slow = ["forest", "forest", "beast_within", "high_score", "bone_sabres", "eternal_witness", "berserk"]
    fast = ["forest", "forest", "llanowar_elves", "high_score", "bone_sabres", "eternal_witness", "berserk"]
    assert STRATEGY.keep_hand(builder().hand(0, slow).build().state, 0) is False
    assert STRATEGY.keep_hand(builder().hand(0, fast).build().state, 0) is True


def test_an_equip_already_spent_this_turn_stays_spent(builder):
    game = (
        builder()
        .deck(0, DECK)
        .battlefield(0, ["elvish_mystic", "staff_of_titania"])
        .battlefield(0, ["forest"] * 3)
        .build()
    )
    staff = only_oid(game, "staff_of_titania", 0)
    equip = next(a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == staff)
    # The agent scores a second activation this turn 0. Voltron used to lift
    # it back to 10 with no commander out -- in a real game, an endless loop
    # of re-equipping the Staff onto the same elf.
    assert Voltron().priority_value(game.state, 0, equip, 0.0) == 0.0
    assert STRATEGY.priority_value(game.state, 0, equip, 0.0) == 0.0
