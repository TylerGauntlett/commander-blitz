"""Ascend, and the city's blessing -- the engine's first per-player designation.

"Ascend (If you control ten or more permanents, you get the city's blessing for
the rest of the game.)" plus "This creature has flying as long as you have the
city's blessing." Skymarcher Aspirant is the shipped witness, and both printed
lines were blocked: one because there was nothing to grant, the other because
there was nothing to ask.

This reverses a documented decision. `rules-coverage.md` listed "the monarch,
initiative, day/night, and other designated-player mechanics" under Not
implemented, and the city's blessing is exactly one of those.

**It is a state trigger, not a triggered ability** (rule 702.131a), and that is
the whole design. Ascend is not an *event*: a player at nine permanents who
plays a land gets the blessing at the instant of the tenth, with nothing having
fired, and gets it on an opponent's turn just as readily. State triggers are
checked whenever state-based actions are, use no stack and cannot be responded
to -- so it lives in the SBA pass beside the legend rule. A trigger-plus-counter
version would be a different card in the direction that matters, because a
re-checked trigger would come and go and the blessing never does.

**It is player state, not object state.** `monstrous` is the closest existing
one-way flag and is wrong in all three respects: it lives on a `GameObject`, so
`reset_permanent_state` clears it on any zone change; it is set by an op
resolving from the stack rather than by a continuous check; and it cannot be
shared between two cards. The blessing has to survive the permanents leaving,
survive the Ascend card leaving, and be visible to every card that player
controls -- so that a second Ascend card printed later reads the blessing a
first one granted.

**`ascend` is a card field, not a `Keyword`.** The enum's members are read by
`grant_keyword` and the evasion checks off *derived characteristics*, and Ascend
is neither granted nor evasive.

The properties worth pinning are the boundary (ten, not nine) and the
permanence -- a blessing that went away when the board shrank would be a
strictly worse card, and would look perfectly normal.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import sba
from automtg.engine.characteristics import chars
from automtg.engine.errors import DslError
from automtg.engine.sba import ASCEND_THRESHOLD
from automtg.engine.zones import destroy

ASPIRANT = "skymarcher_aspirant"


def board(builder, permanents: int, *, players: int = 2):
    """The Aspirant plus enough Plains to reach `permanents` in total."""
    game = (
        builder(players=players)
        .battlefield(0, [ASPIRANT] + ["plains"] * (permanents - 1))
        .build()
    )
    sba.run(game.state)
    oid = next(
        o for o in game.state.battlefield if game.state.objects[o].def_id == ASPIRANT
    )
    return game, oid


def blessed(game, pid: int = 0) -> bool:
    return game.state.players[pid].has_city_s_blessing


def flies(game, oid: int) -> bool:
    return "flying" in chars(game.state, oid).keywords


class TestTheThreshold:
    def test_nine_permanents_is_not_enough(self, builder):
        game, _ = board(builder, ASCEND_THRESHOLD - 1)
        assert not blessed(game)

    def test_ten_is(self, builder):
        game, _ = board(builder, ASCEND_THRESHOLD)
        assert blessed(game)

    def test_more_than_ten_is_too(self, builder):
        game, _ = board(builder, ASCEND_THRESHOLD + 4)
        assert blessed(game)

    def test_it_counts_only_your_own(self, builder):
        """"If **you** control ten or more permanents"."""
        game = (
            builder(players=2)
            .battlefield(0, [ASPIRANT])
            .battlefield(1, ["plains"] * 20)
            .build()
        )
        sba.run(game.state)
        assert not blessed(game, 0)
        assert not blessed(game, 1), "the opponent has no Ascend card"


class TestItIsForTheRestOfTheGame:
    def test_it_survives_the_board_shrinking(self, builder):
        game, oid = board(builder, ASCEND_THRESHOLD)
        assert blessed(game)

        for plains in [
            o for o in list(game.state.battlefield)
            if game.state.objects[o].def_id == "plains"
        ]:
            destroy(game.state, plains)
        sba.run(game.state)

        assert blessed(game), (
            "'for the rest of the game' -- a blessing that came and went would "
            "be a strictly worse card, and would look perfectly normal"
        )
        assert flies(game, oid)

    def test_it_survives_the_ascend_card_leaving(self, builder):
        game, oid = board(builder, ASCEND_THRESHOLD)
        assert blessed(game)
        destroy(game.state, oid)
        sba.run(game.state)
        assert blessed(game), "the blessing is the player's, not the permanent's"


class TestTheConditionalFlying:
    def test_it_does_not_fly_below_the_threshold(self, builder):
        game, oid = board(builder, ASCEND_THRESHOLD - 1)
        assert not flies(game, oid), (
            "printing flying unconditionally would be a strictly better card: "
            "a 2/1 flier for {W} from turn one"
        )

    def test_it_flies_once_blessed(self, builder):
        game, oid = board(builder, ASCEND_THRESHOLD)
        assert flies(game, oid)

    def test_the_blessing_is_shared(self, builder):
        """Every card the player controls reads the same flag.

        A second Ascend card printed later sees the blessing a first one
        granted, which is why this is player state rather than a flag on the
        permanent that granted it.
        """
        game, first = board(builder, ASCEND_THRESHOLD)
        from automtg.engine.enums import Zone
        from automtg.engine.state import new_object

        second = new_object(game.state, ASPIRANT, owner=0, zone=Zone.BATTLEFIELD).oid
        game.state.battlefield.append(second)
        game.state.bump_chars()
        assert flies(game, first) and flies(game, second)


def probe(**card) -> dict:
    base = {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "Ascend",
        "mana_cost": "{W}",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
    }
    base.update(card)
    return base


class TestTheConditionLanguage:
    def test_a_static_may_ask_for_the_blessing(self):
        compile_card(
            CardModel.model_validate(
                probe(
                    ascend=True,
                    abilities=[
                        {
                            "kind": "static",
                            "text": "Ascend",
                            "effect": "grant_keyword",
                            "affects": {"self_only": True},
                            "keywords": ["flying"],
                            "condition": {"has_city_s_blessing": "you"},
                        }
                    ],
                )
            )
        )

    def test_an_unknown_player_spec_is_refused(self):
        with pytest.raises(DslError, match="has_city_s_blessing"):
            compile_card(
                CardModel.model_validate(
                    probe(
                        ascend=True,
                        abilities=[
                            {
                                "kind": "static",
                                "text": "Ascend",
                                "effect": "grant_keyword",
                                "affects": {"self_only": True},
                                "keywords": ["flying"],
                                "condition": {"has_city_s_blessing": "the_monarch"},
                            }
                        ],
                    )
                )
            )

    def test_ascend_is_not_a_keyword(self):
        """It is a card field. The `Keyword` enum is read off derived
        characteristics by `grant_keyword` and the evasion checks, and Ascend is
        neither granted nor evasive."""
        with pytest.raises(DslError, match="unknown keyword"):
            compile_card(CardModel.model_validate(probe(keywords=["ascend"])))
