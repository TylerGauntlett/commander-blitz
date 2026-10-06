""""Exile target player's graveyard" — scoping a zone to a chosen player.

    Bojuka Bog — "When this land enters, exile target player's graveyard."

A selector reaching a non-battlefield zone had to decide *whose* zone to walk,
and `_zone_owners` answered with `controller`: "you", "opponent" or everyone.
None of those is "the one player this trigger targeted", and the failure mode is
not a missing card but a much better one — `controller: "any"` with
`count: "all"` exiles every graveyard at the table, which is Relic of
Progenitus, not Bojuka Bog. At a four-player pod that is three extra graveyards.

The fix is a caller, not a mechanism. `select_players` has always understood
`{"target": "t1"}`; `_zone_owners` simply never asked it. So a selector may now
carry `player`, the full player spec, and it takes precedence over `controller`.

**The battlefield deliberately ignores it, and the loader says so out loud.**
`resolve_pool` reads one shared list for the battlefield and the stack, so a
`player` clause there would be silently dropped — and a card that says "target
player's" while quietly meaning "everyone's" is exactly the class of bug this
key exists to close. It is a load error instead.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Zone
from automtg.engine.errors import DslError
from tests.conftest import pass_until

EXILER = "t_graveyard_exiler"
BEAR = "t_bear"
SWAMP = "swamp"


def board(builder, *, mine: int, theirs: int):
    """Both graveyards stocked, so "whose" is a question with a wrong answer."""
    return (
        builder(players=2)
        .battlefield(0, [SWAMP] * 3)
        .graveyard(0, [BEAR] * mine)
        .graveyard(1, [BEAR] * theirs)
        .hand(0, [EXILER])
        .library(0, [SWAMP] * 20)
        .library(1, [SWAMP] * 20)
        .build()
    )


def cast_at(game, pid: int):
    """Cast the exiler naming ``pid``, and let the trigger resolve.

    The player is chosen on the *cast* action rather than answered later:
    legality enumerates one line per legal target, which is how the two lines
    that differ only in whose graveyard is named become distinguishable here.
    """
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == EXILER
        and any(t.kind == "player" and t.id == pid for t in a.targets)
    )
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack)


class TestOnlyTheNamedPlayersGraveyard:
    def test_the_targeted_graveyard_is_exiled(self, builder):
        game = board(builder, mine=2, theirs=3)
        cast_at(game, 1)
        assert len(game.state.players[1].graveyard) == 0

    def test_the_other_graveyard_is_untouched(self, builder):
        """The whole difference between Bojuka Bog and Relic of Progenitus.

        Three, not two: the sorcery itself lands in its controller's graveyard
        as it resolves, on top of the two that were already there.
        """
        game = board(builder, mine=2, theirs=3)
        cast_at(game, 1)
        assert len(game.state.players[0].graveyard) == 3

    def test_it_can_name_its_own_controller(self, builder):
        """"Target player" includes you -- and the spell is what is left."""
        game = board(builder, mine=2, theirs=3)
        cast_at(game, 0)
        assert len(game.state.players[0].graveyard) == 1
        assert len(game.state.players[1].graveyard) == 3

    def test_the_cards_go_to_exile_not_the_graveyard(self, builder):
        game = board(builder, mine=0, theirs=3)
        cast_at(game, 1)
        exiled = [o for o in game.state.objects.values() if o.zone is Zone.EXILE]
        assert len(exiled) == 3


class TestTheLoaderRefusesASharedZone:
    def _card(self, zone: str) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_bad_player_scope",
                "name": "Bad Player Scope",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "targets": [{"id": "t1", "kind": "player", "count": 1, "selector": {}}],
                "spell_effects": [
                    {
                        "op": "exile",
                        "objects": {
                            "zone": zone,
                            "player": {"target": "t1"},
                            "count": "all",
                        },
                    }
                ],
            }
        )

    def test_the_battlefield_is_shared(self):
        with pytest.raises(DslError, match="shared"):
            compile_card(self._card("battlefield"))

    def test_the_stack_is_shared(self):
        with pytest.raises(DslError, match="shared"):
            compile_card(self._card("stack"))

    def test_a_zone_somebody_owns_is_fine(self):
        compile_card(self._card("graveyard"))
