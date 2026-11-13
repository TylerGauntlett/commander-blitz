"""A "you may cast it" permission held by the exiled card's **owner**.

    Whenever this creature enters or deals combat damage to a player, exile up
    to one target nonland permanent. **For as long as that card remains
    exiled, its owner may cast it.**            -- Aerial Extortionist

`exile`'s `playable` writes ``obj.playable_by = ctx.controller``: the seat
whose effect exiled the card. That is right for impulse draw and exactly wrong
here, because the permanent Extortionist takes is usually an opponent's, and
granting the permission to the effect's controller would let me cast my
opponent's card out of their exile. 108.3 makes the owner the one identity a
card never loses, so `playable_by: "owner"` reads the holder off the object --
a permanent I had stolen goes back to the player who brought it.

The near miss is `airbend`, which also grants to the owner but at a flat {2}
in place of the mana cost (118.9). Here the price is the printed one, so a
{4}{U}{U} card off two lands is not castable, and with six it is.

The permission is `while_exiled` and cast-only, so it ends with the zone change
(400.7) and a land never could be exiled by it anyway (the target is nonland).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.casting import _cast_actions
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import move_object
from tests.conftest import pass_until

EXTORT = "t_owner_extortion"  # {0} sorcery: exile target nonland permanent, owner may cast it
YAK = "t_stone_yak"  # {G} 2/2
DRAKE = "t_thunder_drake"  # {4}{U}{U} 3/3


def position(builder, *, p1_lands=("island", "island"), stolen=False):
    """p0 holds the free sorcery and owns a Yak; p1 owns a Drake.

    Returns ``(game, drake)``. With ``stolen`` p0 controls p1's Drake, the
    sharpest form of "its owner".
    """
    game = (
        builder(players=2)
        .hand(0, [EXTORT])
        .battlefield(0, [YAK, "forest"])
        .battlefield(1, [DRAKE, *p1_lands])
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    drake = only(game, DRAKE)
    if stolen:
        game.state.objects[drake].controller = 0
        game.state.bump_chars()
    return game, drake


def only(game, card_id):
    return next(o for o, obj in game.state.objects.items() if obj.def_id == card_id)


def extort(game, target: int):
    spell = only(game, EXTORT)
    cast = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and a.source == spell
        and TargetRef.obj(target) in a.targets
    )
    game.apply(cast)
    for _ in range(4):
        if not game.state.stack:
            break
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
    return game


def offered(game, pid, oid):
    """The cast lines legality offers ``pid`` for ``oid`` at sorcery speed.

    `_cast_actions` directly, since the claim is about two seats at once.
    """
    return [a for a in _cast_actions(game.state, pid, sorcery_speed=True) if a.source == oid]


class TestThePermissionIsTheOwners:
    def test_the_card_lands_in_its_owners_exile_held_by_its_owner(self, builder):
        game, drake = position(builder)
        extort(game, drake)
        assert drake in game.state.players[1].exile
        assert game.state.objects[drake].playable_by == 1

    def test_the_effects_controller_is_not_offered_it(self, builder):
        game, drake = position(builder, p1_lands=["island"] * 6)
        extort(game, drake)
        assert offered(game, 0, drake) == []

    def test_the_owner_is_offered_it(self, builder):
        game, drake = position(builder, p1_lands=["island"] * 6)
        extort(game, drake)
        assert len(offered(game, 1, drake)) == 1

    def test_a_stolen_permanent_goes_back_to_its_owner(self, builder):
        game, drake = position(builder, p1_lands=["island"] * 6, stolen=True)
        extort(game, drake)
        assert game.state.objects[drake].playable_by == 1
        assert offered(game, 0, drake) == []

    def test_exiling_your_own_permanent_leaves_it_yours(self, builder):
        game, _ = position(builder)
        yak = only(game, YAK)
        extort(game, yak)
        assert game.state.objects[yak].playable_by == 0
        assert len(offered(game, 0, yak)) == 1


class TestThePriceIsTheManaCost:
    def test_two_lands_do_not_pay_six(self, builder):
        """Airbend's {2} would; the printed {4}{U}{U} does not."""
        game, drake = position(builder)
        extort(game, drake)
        assert game.state.objects[drake].playable_alt_cost is None
        assert offered(game, 1, drake) == []

    def test_six_do(self, builder):
        game, drake = position(builder, p1_lands=["island"] * 6)
        extort(game, drake)
        pass_until(
            game, lambda g: g.state.active_player == 1 and g.state.step is Step.PRECOMBAT_MAIN
        )
        cast = [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == drake]
        assert cast, "the owner casts it on their own turn"
        game.apply(cast[0])
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.objects[drake].zone is Zone.BATTLEFIELD
        assert game.state.objects[drake].controller == 1


class TestItLastsWhileExiled:
    def test_on_a_later_turn_it_is_still_open(self, builder):
        game, drake = position(builder, p1_lands=["island"] * 6)
        extort(game, drake)
        game.state.turn += 3
        assert len(offered(game, 1, drake)) == 1

    def test_leaving_exile_ends_it(self, builder):
        """400.7: a card that left exile is a new object with nothing granted."""
        game, drake = position(builder, p1_lands=["island"] * 6)
        extort(game, drake)
        move_object(game.state, drake, Zone.GRAVEYARD)
        move_object(game.state, drake, Zone.EXILE)
        assert game.state.objects[drake].playable_by is None
        assert offered(game, 1, drake) == []


class TestTheLoader:
    def compile(self, effect):
        return compile_card(
            CardModel.model_validate(
                {
                    "id": "t_probe_owner_cast",
                    "name": "Probe Owner Cast",
                    "mana_cost": "{0}",
                    "types": ["Sorcery"],
                    "spell_effects": [effect],
                }
            )
        )

    EXILE = {"op": "exile", "objects": {"zone": "battlefield", "count": "all"}}

    def test_on_a_while_exiled_exile_it_loads(self):
        self.compile({**self.EXILE, "playable": "while_exiled", "playable_by": "owner"})

    def test_without_a_permission_it_is_refused(self):
        with pytest.raises(DslError, match="playable_by"):
            self.compile({**self.EXILE, "playable_by": "owner"})

    def test_on_another_duration_it_is_refused(self):
        with pytest.raises(DslError, match="playable_by"):
            self.compile({**self.EXILE, "playable": "this_turn", "playable_by": "owner"})

    def test_on_another_op_it_is_refused(self):
        with pytest.raises(DslError, match="playable_by"):
            self.compile(
                {
                    "op": "grant_playable",
                    "objects": {"zone": "exile", "count": "all"},
                    "playable": "while_exiled",
                    "playable_by": "owner",
                }
            )

    def test_only_owner(self):
        with pytest.raises(DslError, match="playable_by"):
            self.compile({**self.EXILE, "playable": "while_exiled", "playable_by": "you"})
