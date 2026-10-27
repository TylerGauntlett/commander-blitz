"""Toxic N -- poison on top of the damage, not instead of it.

    "Toxic 1 (Players dealt combat damage by this creature also get a poison
    counter.)"

Rule 702.164b: combat damage dealt to a player by a creature with toxic gives
that player N poison counters **in addition to** the damage's other results
(120.3g). That clause is the whole difference from infect, which is the near
miss: an infect creature's damage *becomes* poison and costs no life, and a
toxic creature's hit costs the life and adds the poison. Written as infect, a
Phyrexian Mite would give one poison and take no life; written as poisonous (a
`deals_combat_damage_to_player` trigger) it would use the stack, be respondable
and copyable, and count as a triggered ability for every card that asks.

The routing rule in `docs/keywords.md` pulls two ways, and both are met. "Creatures you
control **with toxic** have lifelink" (Skrelv's Hive) filters on the word for
any N, and only a `Keyword` can be filtered on; N has nowhere to live on a bare
string. So the word is `Keyword.TOXIC` and the number is the card-level
`CardDef.toxic` -- the total of every printed instance, which is 702.164c's
"add up". The loader requires the two together, and refuses every grant
spelling of toxic: a grant has no N to give.

The witness is the 1/1 colorless Phyrexian Mite artifact token Skrelv's Hive and
White Sun's Twilight both create.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.authoring.verify import claimed_lines
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import KEYWORD_COUNTERS, ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import damage_player
from tests.conftest import (
    attack_with,
    find_action,
    keywords,
    only_oid,
    pass_until,
    two_seat_board,
)

MITE = "phyrexian_mite_1_1_c_toxic"     # 1/1, toxic 1, can't block
STALKER = "t_toxic_two"                 # 3/3 trample, toxic 2
BLIGHT = "t_toxic_infecter"             # 2/2 infect, toxic 1
BEAR = "t_bear"                         # 2/2
LORD = "t_toxic_lord"                   # creatures you control with toxic have lifelink
SUPPRESSOR = "t_toxic_suppressor"       # creatures lose toxic


def position(builder, attacker: str, *, mine=(), theirs=()):
    """``attacker`` for player 0 facing player 1, frozen in the main phase."""
    game = two_seat_board(builder, [attacker, *mine], list(theirs), advance=False)
    return game, only_oid(game, attacker, 0)


def poison(game, pid: int = 1) -> int:
    return game.state.players[pid].poison


def life(game, pid: int = 1) -> int:
    return game.state.players[pid].life


class TestCombatDamageGivesPoison:
    def test_the_mite_gives_one_poison_and_the_life_is_still_lost(self, builder):
        game, mite = position(builder, MITE)
        before = life(game)

        damage_player(game.state, 1, 1, mite, is_combat=True)

        assert poison(game) == 1
        assert life(game) == before - 1, "in addition to the damage, not instead"

    def test_n_is_the_number_not_the_damage(self, builder):
        """Three damage from a toxic 2 creature is two poison, not three."""
        game, stalker = position(builder, STALKER)
        before = life(game)

        damage_player(game.state, 1, 3, stalker, is_combat=True)

        assert poison(game) == 2
        assert life(game) == before - 3

    def test_infect_and_toxic_both_give_poison(self, builder):
        """Infect's poison replaces the life loss; toxic's is added to the hit."""
        game, blight = position(builder, BLIGHT)
        before = life(game)

        damage_player(game.state, 1, 2, blight, is_combat=True)

        assert poison(game) == 3
        assert life(game) == before

    def test_an_ordinary_creature_gives_none(self, builder):
        game, bear = position(builder, BEAR)

        damage_player(game.state, 1, 2, bear, is_combat=True)

        assert poison(game) == 0


class TestOnlyCombatDamage:
    def test_noncombat_damage_gives_no_poison(self, builder):
        """702.164b says *combat* damage; a fling of a Mite is only a point."""
        game, stalker = position(builder, STALKER)

        damage_player(game.state, 1, 3, stalker, is_combat=False)

        assert poison(game) == 0

    def test_no_damage_dealt_gives_no_poison(self, builder):
        game, stalker = position(builder, STALKER)

        damage_player(game.state, 1, 0, stalker, is_combat=True)

        assert poison(game) == 0

    def test_a_full_combat_poisons_the_defender(self, builder):
        game = two_seat_board(builder, [MITE])
        mite = only_oid(game, MITE, 0)
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
        )
        attack_with(game, mite)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        before = life(game)
        pass_until(
            game,
            lambda g: int(g.state.step) > int(Step.COMBAT_DAMAGE) or g.state.turn != 1,
        )

        assert poison(game) == 1
        assert life(game) == before - 1


class TestTheKeywordIsDerived:
    def test_a_creature_that_lost_toxic_gives_no_poison(self, builder):
        """`damage_player` reads `chars`, not the printed card: N stays on the
        card, but without the word it poisons nobody."""
        game, stalker = position(builder, STALKER, theirs=[SUPPRESSOR])
        assert "toxic" not in keywords(game, stalker)

        damage_player(game.state, 1, 3, stalker, is_combat=True)

        assert poison(game) == 0


class TestWithToxic:
    def test_creatures_you_control_with_toxic_are_selected_whatever_their_n(self, builder):
        """Skrelv's Hive's filter: the word, for any N."""
        game, mite = position(builder, MITE, mine=[STALKER, BEAR, LORD])
        stalker = only_oid(game, STALKER, 0)
        bear = only_oid(game, BEAR, 0)

        assert "lifelink" in keywords(game, mite)
        assert "lifelink" in keywords(game, stalker)
        assert "lifelink" not in keywords(game, bear)

    def test_an_opponents_toxic_creature_is_not_yours(self, builder):
        game, _ = position(builder, BEAR, theirs=[MITE], mine=[LORD])
        theirs = only_oid(game, MITE, 1)

        assert "lifelink" not in keywords(game, theirs)


class TestTheMite:
    def test_it_cannot_block(self, builder):
        from commanderblitz.engine.combat import can_block

        game = two_seat_board(builder, [BEAR], [MITE], advance=False)
        bear = only_oid(game, BEAR, 0)
        mite = only_oid(game, MITE, 1)

        assert not can_block(game.state, mite, bear, 1)


def _creature(**fields) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_toxic_probe",
            "name": "Toxic Probe",
            "mana_cost": "{B}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            **fields,
        }
    )


def _granter(ability: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_toxic_granter",
            "name": "Toxic Granter",
            "mana_cost": "{B}",
            "types": ["Enchantment"],
            "abilities": [{"text": "Probe.", **ability}],
        }
    )


class TestTheLoaderGuard:
    def test_the_word_and_the_number_load(self):
        assert compile_card(_creature(keywords=["toxic"], toxic=2)).toxic == 2

    def test_the_word_without_a_number_is_refused(self):
        """It would filter as "with toxic" and poison nobody."""
        with pytest.raises(DslError, match="write both or neither"):
            compile_card(_creature(keywords=["toxic"]))

    def test_a_number_without_the_word_is_refused(self):
        with pytest.raises(DslError, match="write both or neither"):
            compile_card(_creature(toxic=1))

    def test_a_negative_number_is_refused(self):
        with pytest.raises(DslError, match="cannot be negative"):
            compile_card(_creature(keywords=["toxic"], toxic=-1))

    def test_a_granting_static_is_refused(self):
        """"Other Rats you control have toxic 1" -- the grant has no N."""
        with pytest.raises(DslError, match="never granted"):
            compile_card(
                _granter(
                    {
                        "kind": "static",
                        "effect": "grant_keyword",
                        "affects": {"types": ["Creature"]},
                        "keywords": ["toxic"],
                    }
                )
            )

    def test_a_granting_op_is_refused(self):
        """Skrelv, Defector Mite's "gains toxic 1 … until end of turn"."""
        with pytest.raises(DslError, match="never granted"):
            compile_card(
                _granter(
                    {
                        "kind": "activated",
                        "cost": {"mana": "{B}"},
                        "effects": [
                            {"op": "grant_keyword", "keywords": ["toxic"], "objects": {"self_only": True}}
                        ],
                    }
                )
            )

    def test_losing_toxic_is_allowed(self):
        compile_card(
            _granter(
                {
                    "kind": "static",
                    "effect": "lose_keyword",
                    "affects": {"types": ["Creature"]},
                    "keywords": ["toxic"],
                }
            )
        )

    def test_there_is_no_toxic_counter(self):
        assert "toxic" not in KEYWORD_COUNTERS


class TestTheResidualClaim:
    def test_a_keyword_line_with_the_cards_own_n_is_claimed(self):
        card = compile_card(_creature(keywords=["trample", "toxic"], toxic=2))
        line = "Trample, toxic 2 (Players dealt combat damage by this creature also get two poison counters.)"

        assert line in claimed_lines(card, line)

    def test_a_different_n_is_not_claimed(self):
        """A toxic 1 card wearing "Toxic 2" is a weaker card than the printed one."""
        card = compile_card(_creature(keywords=["toxic"], toxic=1))

        assert "Toxic 2" not in claimed_lines(card, "Toxic 2")

    def test_a_keyword_the_card_lacks_is_not_claimed(self):
        card = compile_card(_creature(keywords=["toxic"], toxic=1))

        assert "Trample, toxic 1" not in claimed_lines(card, "Trample, toxic 1")
