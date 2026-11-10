"""`playable_pay_life_instead` -- "pay life equal to its mana value rather than paying its mana cost."

    Nashi, Moon Sage's Scion -- "Whenever Nashi deals combat damage to a
    player, exile the top card of each player's library. Until end of turn,
    you may play one of those cards. If you cast a spell this way, pay life
    equal to its mana value rather than paying its mana cost."

Two rules meet on one permission.

**An alternative cost (118.9) the permission carries.** "This way" is the only
way the permission reaches, so the life line is not an option beside the printed
price: a player with mana in the pool still pays life, and nothing is offered at
the printed cost, free, or under a second alternative cost (118.9a). X is 0
(107.3b), so the life is the mana value with X at 0; additional costs are still
owed on top (118.9d); and life can be paid only while the player has that much,
paying 0 always succeeding (119.4). Without the rider the card is Nashi at the
printed price, which in a deck that mostly casts its opponents' cards is a far
weaker card; with `playable_free` it is a far stronger one.

**"Play one of those cards."** `grant_playable`'s `limit` caps one resolution's
cards at one play, and a land played from among them is that one play (305.9
says a land is played, never cast, so it pays nothing). Each resolution is its
own group: a double-striking Nashi's second trigger is a second card.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import hand_ids, settle

RAID = "t_ppl_raid"  # Nashi's trigger as a {B} sorcery
PLAIN = "t_ppl_plain_raid"  # the same play-one permission at the printed price
HEIST = "t_ppl_heist"  # the rider on `exile`'s own permission
FLARE = "t_czr_flare"  # {3}{R} sorcery, mana value 4
DRAW_X = "t_cane_draw_x"  # {X}{U}: draw X cards, mana value 1
DELUGE = "t_fixed_deluge"  # {2}{B}, as an additional cost pay 3 life
RITE = "t_expend_kicked"  # {1}, kicker {3}: gain 1 life, 1 more if kicked


def raid(builder, mine: str, theirs: str, *, spell: str = RAID, life: int = 40,
         mountains: int = 0, raids: int = 1, second: str = "forest"):
    """Player 0 casts ``spell`` off a Swamp and lets it resolve.

    ``mine`` and ``theirs`` are the top cards of the two libraries, ``second``
    the card under ``mine``; ``mountains`` is mana left over afterwards. A
    Plains in hand keeps the window open."""
    game = (
        builder(players=2)
        .battlefield(0, ["swamp"] * raids + ["mountain"] * mountains)
        .hand(0, [spell] * raids + ["plains"])
        .library(0, [mine, second] + ["forest"] * 8)
        .library(1, [theirs] + ["island"] * 8)
        .life(0, life)
        .active(0)
        .max_turns(1)
        .build()
    )
    cast_raid(game, spell)
    return game


def cast_raid(game, spell: str = RAID) -> None:
    game.apply(next(a for a in casts(game, spell) if a.kind is ActionKind.CAST))
    settle(game)


def casts(game, def_id: str) -> list:
    state = game.state
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and a.source is not None
        and state.objects[a.source].def_id == def_id
    ]


def land_drops(game, def_id: str) -> list:
    state = game.state
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.PLAY_LAND and state.objects[a.source].def_id == def_id
    ]


def exiled(game, def_id: str) -> int:
    state = game.state
    return next(
        oid for p in state.players for oid in p.exile if state.objects[oid].def_id == def_id
    )


def untapped_mountains(game) -> int:
    state = game.state
    return sum(
        not state.objects[oid].tapped
        for oid in state.battlefield
        if state.objects[oid].def_id == "mountain"
    )


class TestPaysLifeRatherThanMana:
    def test_a_four_drop_costs_four_life_and_no_mana(self, builder):
        game = raid(builder, FLARE, "island")
        (line,) = casts(game, FLARE)
        assert line.granted_cost == (("pay_life", 4),)
        game.apply(line)
        assert game.state.players[0].life == 36
        settle(game)
        assert game.state.players[1].life == 39, "the flare resolved"

    def test_mana_on_hand_buys_nothing_else(self, builder):
        """No printed-price line beside the life one, and the Mountains stay up."""
        game = raid(builder, FLARE, "island", mountains=4)
        lines = casts(game, FLARE)
        assert lines and all(a.granted_cost == (("pay_life", 4),) for a in lines)
        game.apply(lines[0])
        assert untapped_mountains(game) == 4
        assert game.state.players[0].life == 36

    def test_without_the_rider_it_is_the_printed_price(self, builder):
        """The near miss: the same permission, without the life clause."""
        game = raid(builder, FLARE, "island", spell=PLAIN)
        assert game.state.objects[exiled(game, FLARE)].playable_by == 0
        assert casts(game, FLARE) == [], "{3}{R} with no mana up"

    def test_an_opponents_card_is_yours_to_cast(self, builder):
        game = raid(builder, "forest", FLARE)
        assert exiled(game, FLARE) in game.state.players[1].exile
        game.apply(casts(game, FLARE)[0])
        assert game.state.players[0].life == 36


class TestTheAlternativeCostsRules:
    def test_x_is_zero(self, builder):
        """107.3b: {X}{U} costs 1 life and draws nothing."""
        game = raid(builder, DRAW_X, "island")
        (line,) = casts(game, DRAW_X)
        assert line.granted_cost == (("pay_life", 1),)
        before = len(hand_ids(game))
        game.apply(line)
        settle(game)
        assert game.state.players[0].life == 39
        assert len(hand_ids(game)) == before

    def test_an_additional_cost_is_still_owed(self, builder):
        """118.9d: three life for the mana value and three more on top."""
        game = raid(builder, DELUGE, "island")
        game.apply(casts(game, DELUGE)[0])
        settle(game)
        assert game.state.players[0].life == 34

    def test_a_kicker_is_still_paid_in_mana(self, builder):
        """The kicked line is {3} and 1 life; the unkicked one is 1 life."""
        game = raid(builder, RITE, "island", mountains=3)
        lines = casts(game, RITE)
        assert {a.kicked for a in lines} == {False, True}
        game.apply(next(a for a in lines if a.kicked))
        assert untapped_mountains(game) == 0
        settle(game)
        assert game.state.players[0].life == 41, "40, less 1, plus 2 kicked"

    def test_no_mana_no_kicker(self, builder):
        game = raid(builder, RITE, "island")
        assert [a.kicked for a in casts(game, RITE)] == [False]


class TestPayingLife:
    def test_exactly_enough_life_pays_down_to_zero(self, builder):
        """119.4 asks for the life, not for surviving the payment."""
        game = raid(builder, FLARE, "island", life=4)
        assert casts(game, FLARE)

    def test_less_life_than_the_mana_value_casts_nothing(self, builder):
        game = raid(builder, FLARE, "island", life=3, mountains=4)
        assert casts(game, FLARE) == [], "and the mana is no help"


class TestPlayOneOfThoseCards:
    def test_a_land_is_played_for_nothing(self, builder):
        game = raid(builder, "forest", "island")
        state = game.state
        oid = exiled(game, "forest")
        game.apply(land_drops(game, "forest")[0])
        assert oid in state.battlefield
        assert state.players[0].life == 40

    def test_casting_one_closes_the_rest(self, builder):
        game = raid(builder, FLARE, DRAW_X)
        game.apply(casts(game, FLARE)[0])
        settle(game)
        assert casts(game, DRAW_X) == []

    def test_playing_the_land_closes_the_spell(self, builder):
        game = raid(builder, "forest", FLARE)
        game.apply(land_drops(game, "forest")[0])
        settle(game)
        assert casts(game, FLARE) == []

    def test_casting_the_spell_closes_the_land(self, builder):
        game = raid(builder, FLARE, "island")
        game.apply(casts(game, FLARE)[0])
        settle(game)
        assert land_drops(game, "island") == []

    def test_without_the_limit_both_lands_would_be_offered(self, builder):
        """Before either is played, both of the group's cards are offered."""
        game = raid(builder, "forest", "island")
        assert land_drops(game, "forest") and land_drops(game, "island")

    def test_two_resolutions_are_two_plays(self, builder):
        """A double-striking Nashi: the second trigger's cards are a new group."""
        game = raid(builder, FLARE, "island", raids=2, second=FLARE)
        state = game.state
        first_island = exiled(game, "island")
        game.apply(casts(game, FLARE)[0])
        settle(game)
        cast_raid(game)
        assert casts(game, FLARE), "the second raid's card"
        offered = {a.source for a in land_drops(game, "island")}
        assert first_island not in offered, "the first raid's card stays closed"
        assert len(offered) == 1, "the second raid's island is open"
        assert state.players[0].life == 36


class TestWearingOff:
    def test_it_ends_with_the_turn(self, builder):
        game = raid(builder, FLARE, "island")
        game.state.turn += 1
        assert casts(game, FLARE) == []

    def test_it_leaves_with_the_card(self, builder):
        """400.7: a card that changes zones is a new object with no grant."""
        game = raid(builder, FLARE, "island")
        state = game.state
        oid = exiled(game, FLARE)
        move_object(state, oid, Zone.GRAVEYARD)
        assert state.objects[oid].playable_pay_life is False


class TestOnTheExileOp:
    def test_the_rider_rides_on_exiles_permission(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["swamp"])
            .hand(0, [HEIST, "plains"])
            .graveyard(1, [FLARE])
            .active(0)
            .max_turns(1)
            .build()
        )
        cast_raid(game, HEIST)
        oid = exiled(game, FLARE)
        assert game.state.objects[oid].playable_pay_life
        game.apply(casts(game, FLARE)[0])
        assert game.state.players[0].life == 36


def _probe(effect: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_probe",
            "name": "Probe",
            "oracle_text": "",
            "mana_cost": "{1}",
            "types": ["Sorcery"],
            "colors": [],
            "color_identity": [],
            "spell_effects": [effect],
        }
    )


GRANT = {"op": "grant_playable", "limit": 1, "objects": {"zone": "exile", "exiled_with": "self"}}


class TestTheLoaderRefuses:
    def test_the_witness_shape_loads(self):
        compile_card(_probe({**GRANT, "playable_pay_life_instead": True}))

    def test_a_bare_exile(self):
        with pytest.raises(DslError, match="needs one"):
            compile_card(
                _probe({"op": "exile", "objects": {"zone": "graveyard"},
                        "playable_pay_life_instead": True})
            )

    @pytest.mark.parametrize("value", [False, 1, "yes"])
    def test_anything_but_true(self, value):
        with pytest.raises(DslError, match="only value is true"):
            compile_card(_probe({**GRANT, "playable_pay_life_instead": value}))

    @pytest.mark.parametrize(
        "rider",
        [
            {"playable_free": True},
            {"playable_cost_reduction": 2},
            {"any_color": True},
            {"any_type": True},
            {"as_flashback": True},
        ],
    )
    def test_beside_a_second_price(self, rider):
        with pytest.raises(DslError, match="second price"):
            compile_card(_probe({**GRANT, "playable_pay_life_instead": True, **rider}))
