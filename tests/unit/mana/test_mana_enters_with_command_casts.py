""""If you spend this mana to cast your commander, it enters with…counters."

    "{1}, {T}: Add one mana of any color in your commander's color identity. If
    you spend this mana to cast your commander, it enters with a number of
    additional +1/+1 counters on it equal to the number of times it's been cast
    from the command zone this game."                      -- Opal Palace

Not a trigger, unlike Study Hall's rider beside it: "enters with" is a
replacement on the arrival (614.1c), so the commander is never on the
battlefield without the counters, and they are one placement with anything
else it enters with (122.6). And not a static on the land: the promise is the
**mana's**, so Opal Palace's plain `{C}` gives nothing, and it rides the spell
it paid for whatever became of the land.

`mana_grant`'s `commander_only` narrows it to a commander the payer owns;
`enters_with_command_zone_casts` names the counter. `costs.pay_mana` stages the
kind on the spell (`GameObject.cast_enters_with_command_casts`), `move_object`
carries it to the battlefield only, and `zones._enter_battlefield` counts it as
it arrives, off the 903.8 tally -- which `Game` bumps after payment, so a count
taken as the mana is spent would be one short of "this cast included".
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import activate_mana_ability
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import PLUS_ONE
from tests.conftest import action_for_card, only_oid, settle

PALACE = "t_op_palace"
COMMANDER = "t_commander_two"  # {1}{W}
NOT_A_COMMANDER = "t_commander_five"  # {3}{W}{W}, cast from hand here

PLAIN_MANA = 0
RIDER_MANA = 1


def position(builder):
    return (
        builder(players=2)
        .battlefield(0, [PALACE] + ["plains"] * 5)
        .hand(0, [NOT_A_COMMANDER])
        .commander(0, [COMMANDER])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .build()
    )


def cast(game, card_id: str) -> int:
    action = action_for_card(game, ActionKind.CAST, card_id)
    game.apply(action)
    settle(game)
    return action.source


def counters(game, oid: int) -> int:
    return game.state.objects[oid].counters.get(PLUS_ONE, 0)


def palace_mana(game, ability: int = RIDER_MANA) -> None:
    """Tap the Palace. The rider's ``{1}`` is not charged: what is under test is
    the mana, and paying would let the solver pick which Plains."""
    activate_mana_ability(game.state, only_oid(game, PALACE, 0), ability, 0)


class TestSpendingItOnTheCommander:
    def test_the_first_cast_enters_with_one(self, builder):
        game = position(builder)
        palace_mana(game)
        commander = cast(game, COMMANDER)
        assert game.state.objects[commander].on_battlefield
        assert counters(game, commander) == 1

    def test_it_counts_every_cast_from_the_command_zone(self, builder):
        """Two earlier casts on the tally, and this one makes three."""
        game = position(builder)
        commander = game.state.players[0].commanders[0]
        game.state.players[0].commander_tax[commander] = 2
        palace_mana(game)
        cast(game, COMMANDER)
        assert counters(game, commander) == 3


class TestWhatGivesNothing:
    def test_the_plain_mana(self, builder):
        game = position(builder)
        palace_mana(game, PLAIN_MANA)
        commander = cast(game, COMMANDER)
        assert game.state.players[0].mana_pool.total() == 0, "the Palace's mana was spent"
        assert counters(game, commander) == 0

    def test_other_mana(self, builder):
        game = position(builder)
        commander = cast(game, COMMANDER)
        assert counters(game, commander) == 0

    def test_a_spell_that_is_not_your_commander(self, builder):
        game = position(builder)
        palace_mana(game)
        creature = cast(game, NOT_A_COMMANDER)
        assert game.state.players[0].mana_pool.total() == 0, "the Palace's mana was spent"
        assert counters(game, creature) == 0


def palace_with(grant: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "probe_palace",
            "name": "Probe Palace",
            "types": ["Land"],
            "abilities": [
                {
                    "kind": "activated",
                    "is_mana_ability": True,
                    "cost": {"tap": True},
                    "effects": [{"op": "add_mana", "mana": "{W}"}],
                    "mana_grant": grant,
                }
            ],
        }
    )


class TestTheLoader:
    def test_it_loads_without_keywords(self):
        compile_card(
            palace_with({"commander_only": True, "enters_with_command_zone_casts": "+1/+1"})
        )

    def test_it_needs_commander_only(self):
        with pytest.raises(DslError, match="needs 'commander_only'"):
            compile_card(palace_with({"enters_with_command_zone_casts": "+1/+1"}))

    def test_a_grant_of_nothing_is_still_refused(self):
        with pytest.raises(DslError, match="non-empty 'keywords'"):
            compile_card(palace_with({"commander_only": True}))
