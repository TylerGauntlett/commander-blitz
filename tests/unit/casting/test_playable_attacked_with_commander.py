"""A "you may play it" permission usable only on turns you attacked with a commander.

    Whenever Neriv attacks, exile a number of cards from the top of your
    library equal to the number of differently named tokens you control.
    **During any turn you attacked with a commander, you may play those
    cards.**                               -- Neriv, Crackling Vanguard

The permission never ends while the card stays exiled -- `playable:
"while_exiled"` -- but it is **shut** on every turn in which its holder did not
declare a commander (903.3) as an attacker. That is `playable_condition:
"you_attacked_with_a_commander"`, read where the play is offered
(`objects.playable_condition_met`) off `TurnLedger.creatures_attacked`.

Without it the nearest spellings are both wrong: `while_exiled` alone lets the
cards be played on any turn, a strictly stronger card; `this_turn` lets them
be played only on the turn Neriv attacked, and loses them for good after it.

"A commander" is any commander, not only your own: an opponent's commander you
control and attack with is still a commander. A commander that attacked and
then died still attacked, so the cards stay open for the rest of that turn.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import move_object
from tests.conftest import find_action, oids_of, only_oid, pass_until, settle

IMPULSE = "t_cmdr_impulse"          # {R}: exile top two, playable on commander-attack turns
EXILE_IMPULSE = "t_cmdr_exile_impulse"
GIFT = "t_cmdr_free_gift"           # {0} instant: the cast path
BEAR = "t_bear"


def position(builder):
    """Seat 0 has two bears -- one of them a commander -- and the impulse.

    The library's top two are a Forest (the land path) and a {0} instant (the
    cast path): neither needs mana, so the permission is the only thing that
    makes playing them legal and `legal_actions` answers whether it is open.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["mountain", BEAR, BEAR])
        .library(0, ["forest", GIFT] + ["mountain"] * 20)
        .library(1, ["mountain"] * 20)
        .hand(0, [IMPULSE])
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    commander, plain = oids_of(game, BEAR, 0)
    game.state.objects[commander].is_commander = True
    return game, commander, plain


def cast_impulse(game, def_id: str = IMPULSE) -> list[int]:
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == def_id
        )
    )
    settle(game)
    return list(game.state.players[0].exile)


def playable(game, oid: int) -> bool:
    return any(
        a.source == oid and a.kind in (ActionKind.CAST, ActionKind.PLAY_LAND)
        for a in game.legal_actions()
    )


def declare(game, *attackers: int) -> None:
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
    for oid in attackers:
        game.apply(
            find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(1),))
        )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def to_main_two(game) -> None:
    pass_until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN and g.state.active_player == 0)


class TestShutUntilACommanderAttacks:
    def test_nothing_is_playable_before_combat(self, builder):
        game, _, _ = position(builder)
        exiled = cast_impulse(game)
        assert len(exiled) == 2
        assert not any(playable(game, oid) for oid in exiled)

    def test_attacking_with_a_commander_opens_both_halves(self, builder):
        """The land half (`legality`) and the cast half (`casting`)."""
        game, commander, _ = position(builder)
        forest, gift = cast_impulse(game)
        declare(game, commander)
        to_main_two(game)
        assert playable(game, forest), "the land is played under the permission"
        assert playable(game, gift), "the spell is cast under the permission"

    def test_attacking_with_another_creature_does_not(self, builder):
        game, _, plain = position(builder)
        exiled = cast_impulse(game)
        declare(game, plain)
        to_main_two(game)
        assert not any(playable(game, oid) for oid in exiled)

    def test_a_commander_that_attacked_and_died_still_attacked(self, builder):
        game, commander, _ = position(builder)
        forest, _ = cast_impulse(game)
        declare(game, commander)
        to_main_two(game)
        move_object(game.state, commander, Zone.GRAVEYARD)
        assert playable(game, forest)

    def test_anybodys_commander_counts(self, builder):
        """A stolen commander is still a commander (903.3)."""
        game, commander, _ = position(builder)
        game.state.objects[commander].owner = 1
        forest, _ = cast_impulse(game)
        declare(game, commander)
        to_main_two(game)
        assert playable(game, forest)

    def test_it_is_the_permission_holders_attack_that_counts(self, builder):
        game, commander, _ = position(builder)
        forest, _ = cast_impulse(game)
        # The opponent declared a commander this turn; the holder did not.
        game.state.turn_ledger.creatures_attacked[1] = {commander}
        assert not playable(game, forest)


class TestItLastsWhileExiled:
    def test_a_later_turn_without_a_commander_attack_stays_shut(self, builder):
        game, commander, _ = position(builder)
        forest, _ = cast_impulse(game)
        declare(game, commander)
        to_main_two(game)
        assert playable(game, forest)
        pass_until(game, lambda g: g.state.active_player == 1 and g.state.step is Step.PRECOMBAT_MAIN)
        assert not playable(game, forest)
        pass_until(game, lambda g: g.state.active_player == 0 and g.state.step is Step.PRECOMBAT_MAIN)
        assert not playable(game, forest), "a new turn, and no commander has attacked in it"
        assert forest in game.state.players[0].exile

    def test_a_later_turn_with_a_commander_attack_opens_again(self, builder):
        game, commander, _ = position(builder)
        forest, _ = cast_impulse(game)
        pass_until(game, lambda g: g.state.active_player == 0 and g.state.turn > 1
                   and g.state.step is Step.PRECOMBAT_MAIN)
        assert not playable(game, forest)
        declare(game, commander)
        to_main_two(game)
        assert playable(game, forest), "the permission waited in exile"

    def test_leaving_exile_ends_it(self, builder):
        game, _, _ = position(builder)
        forest, _ = cast_impulse(game)
        move_object(game.state, forest, Zone.GRAVEYARD)
        assert game.state.objects[forest].playable_condition is None


class TestTheExileOp:
    def test_exile_carries_the_condition_too(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["mountain", BEAR])
            .graveyard(0, ["forest"])
            .library(0, ["mountain"] * 20)
            .library(1, ["mountain"] * 20)
            .hand(0, [EXILE_IMPULSE])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        commander = only_oid(game, BEAR, 0)
        game.state.objects[commander].is_commander = True
        (forest,) = cast_impulse(game, EXILE_IMPULSE)
        assert not playable(game, forest)
        declare(game, commander)
        to_main_two(game)
        assert playable(game, forest)


def _card(effect: dict) -> dict:
    return {
        "id": "t_probe",
        "name": "Probe",
        "mana_cost": "{R}",
        "types": ["Sorcery"],
        "spell_effects": [effect],
    }


LOOK = {
    "op": "look_at_top",
    "player": "you",
    "amount": {"const": 1},
    "objects": {"count": "all"},
    "destination": "exile",
}


class TestTheLoader:
    def test_it_loads_beside_a_permission(self):
        compile_card(
            CardModel.model_validate(
                _card({**LOOK, "playable": "while_exiled",
                       "playable_condition": "you_attacked_with_a_commander"})
            )
        )

    def test_it_needs_a_permission_to_sit_on(self):
        with pytest.raises(DslError, match="needs one"):
            compile_card(
                CardModel.model_validate(
                    _card({**LOOK, "playable_condition": "you_attacked_with_a_commander"})
                )
            )

    def test_an_unknown_condition_is_refused(self):
        with pytest.raises(DslError, match="unknown 'playable_condition'"):
            compile_card(
                CardModel.model_validate(
                    _card({**LOOK, "playable": "while_exiled",
                           "playable_condition": "you_attacked"})
                )
            )
