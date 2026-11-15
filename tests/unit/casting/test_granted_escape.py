"""Granted escape: a cost a permission hands to cards in your graveyard.

    Each nonland card in your graveyard has escape. The escape cost is equal to
    the card's mana cost plus exile three other cards from your graveyard.
                                                         -- Underworld Breach

    {T}: Until end of turn, each creature card in your graveyard gains
    "Escape--{3}{B}, Exile four other cards from your graveyard."
                                                -- The Grim Captain's Locker

702.138a: escape is a static ability that lets a card be cast from its
owner's graveyard for its escape cost; 702.138c-d: a spell cast that way
*escaped*. When another card grants the ability, the card is castable from the
graveyard **at that price only** -- Breach is not an Edgar, and a bear under it
does not come back for {1}{G}. Without the rider, the permission the engine had
(`cast_from_graveyard`) would let it out at the printed cost and exile nothing,
which is a much stronger card than the printed one.

Three things the rider has to get right, each a class below:

- **"Other"** is the card being escaped, not the permanent granting escape, so
  a graveyard of exactly three cards cannot pay for its own third card.
- **No per-turn cap.** The exiled cards are the brake; Breach prints no limit
  and an invented one would be the approximation.
- **It escaped, and it comes back.** Escape does not exile the spell (unlike
  flashback), and "if it escaped" reads true of it.

The Locker's grant is the same rider on `grant_graveyard_cast`, with its own
mana: a turn-long, standing permission that covers creature cards that reach
the graveyard after it resolved.

Witnesses: Underworld Breach (`t_breach`) and The Grim Captain's Locker
(`t_locker_grant`, its grant as a sorcery that exiles itself).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import settle_to_priority

BREACH = "t_breach"
GRANT = "t_locker_grant"
BEAR = "t_bear"  # {1}{G} creature
BOLT = "t_gy_gain"  # {R} instant, gain 2 life
FODDER = "forest"


def position(builder, *, graveyard, breach=True, hand=(), library_top=()):
    """Player 0 in their main phase with lands for either price and ``graveyard``.

    Keep something castable or playable in hand when the graveyard offers
    nothing, or the turn passes itself.
    """
    battlefield = ["forest"] * 3 + ["mountain"] * 2 + ["swamp"] * 4
    if breach:
        battlefield.append(BREACH)
    return (
        builder(players=2)
        .battlefield(0, battlefield)
        .battlefield(1, ["plains"])
        .graveyard(0, list(graveyard))
        .hand(0, list(hand))
        .hand(1, ["forest"])
        .library(0, [*library_top] + ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def in_graveyard(game, card_id: str) -> list[int]:
    return [o for o in game.state.players[0].graveyard if game.state.objects[o].def_id == card_id]


def in_hand(game, card_id: str) -> int:
    return next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == card_id)


def casts(game, oid: int):
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


def escape(game, oid: int, price: str | None = None) -> None:
    """Cast ``oid`` on its (only, or ``price``-d) escape line and resolve it."""
    line = next(
        a for a in casts(game, oid) if a.escape is not None and price in (None, a.escape)
    )
    game.apply(line)
    # The exile is a decision taken before the spell is pushed, so the wait is
    # for priority over an empty stack, not for the stack alone.
    settle_to_priority(game)


class TestBreachGrantsEscapeAtTheCardsOwnCost:
    def test_the_only_line_is_the_escape_line(self, builder):
        game = position(builder, graveyard=[BEAR] + [FODDER] * 3)
        (bear,) = in_graveyard(game, BEAR)
        lines = casts(game, bear)
        assert [(a.escape, a.escape_exile) for a in lines] == [("{1}{G}", 3)]

    def test_without_breach_nothing_is_offered(self, builder):
        game = position(builder, graveyard=[BEAR] + [FODDER] * 3, breach=False)
        (bear,) = in_graveyard(game, BEAR)
        assert casts(game, bear) == []

    def test_lands_are_not_offered(self, builder):
        game = position(builder, graveyard=[FODDER] * 4)
        for oid in in_graveyard(game, FODDER):
            assert casts(game, oid) == []

    def test_casting_pays_the_mana_and_three_others(self, builder):
        game = position(builder, graveyard=[BEAR] + [FODDER] * 4)
        (bear,) = in_graveyard(game, BEAR)
        escape(game, bear)
        obj = game.state.objects[bear]
        assert obj.zone is Zone.BATTLEFIELD
        assert len(game.state.players[0].exile) == 3
        assert len(game.state.players[0].graveyard) == 1


class TestOtherMeansTheEscapingCard:
    def test_two_others_are_not_enough(self, builder):
        # The bear plus two: three cards in the graveyard, and the bear is not
        # one of the three it may exile.
        game = position(builder, graveyard=[BEAR] + [FODDER] * 2)
        (bear,) = in_graveyard(game, BEAR)
        assert casts(game, bear) == []


class TestItEscapedAndComesBack:
    def test_the_permanent_escaped(self, builder):
        game = position(builder, graveyard=[BEAR] + [FODDER] * 3)
        (bear,) = in_graveyard(game, BEAR)
        escape(game, bear)
        obj = game.state.objects[bear]
        assert obj.cast_escaped
        assert obj.cast_from_graveyard

    def test_an_escaped_instant_returns_to_the_graveyard(self, builder):
        game = position(builder, graveyard=[BOLT] + [FODDER] * 3)
        (bolt,) = in_graveyard(game, BOLT)
        life = game.state.players[0].life
        escape(game, bolt)
        assert game.state.objects[bolt].zone is Zone.GRAVEYARD
        assert game.state.players[0].life == life + 2

    def test_no_per_turn_cap(self, builder):
        game = position(builder, graveyard=[BOLT] + [FODDER] * 6)
        (bolt,) = in_graveyard(game, BOLT)
        life = game.state.players[0].life
        escape(game, bolt)
        escape(game, bolt)
        assert game.state.players[0].life == life + 4
        assert len(game.state.players[0].exile) == 6
        # Nothing left to exile: the brake, and the only one.
        assert casts(game, bolt) == []


class TestTheLockersTurnLongGrant:
    def granted(self, builder, *, graveyard, library_top=()):
        game = position(
            builder,
            graveyard=graveyard,
            breach=False,
            hand=[GRANT, "forest"],
            library_top=library_top,
        )
        grant = in_hand(game, GRANT)
        game.apply(next(a for a in casts(game, grant)))
        settle_to_priority(game)
        assert game.state.objects[grant].zone is Zone.EXILE
        return game

    def test_a_creature_escapes_at_the_granted_price(self, builder):
        game = self.granted(builder, graveyard=[BEAR] + [FODDER] * 4)
        (bear,) = in_graveyard(game, BEAR)
        assert [(a.escape, a.escape_exile) for a in casts(game, bear)] == [("{3}{B}", 4)]
        escape(game, bear)
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[bear].cast_escaped
        assert len(game.state.players[0].exile) == 5  # four others and the grant

    def test_a_noncreature_is_not_covered(self, builder):
        game = self.granted(builder, graveyard=[BOLT] + [FODDER] * 4)
        (bolt,) = in_graveyard(game, BOLT)
        assert casts(game, bolt) == []

    def test_a_creature_arriving_later_is_covered(self, builder):
        # A snapshot of the graveyard as the grant resolved would miss it.
        game = self.granted(builder, graveyard=[FODDER] * 4, library_top=[BEAR])
        bear = game.state.players[0].library[0]
        assert game.state.objects[bear].def_id == BEAR
        move_object(game.state, bear, Zone.GRAVEYARD, to_player=0, cause="effect")
        assert [a.escape for a in casts(game, bear)] == ["{3}{B}"]

    def test_it_ends_with_the_turn(self, builder):
        game = self.granted(builder, graveyard=[BEAR] + [FODDER] * 4)
        (bear,) = in_graveyard(game, BEAR)
        game.state.turn += 1
        assert casts(game, bear) == []

    def test_beside_breach_each_price_is_its_own_line(self, builder):
        game = position(builder, graveyard=[BEAR] + [FODDER] * 4, hand=[GRANT])
        grant = in_hand(game, GRANT)
        game.apply(next(a for a in casts(game, grant)))
        settle_to_priority(game)
        (bear,) = in_graveyard(game, BEAR)
        assert sorted((a.escape, a.escape_exile) for a in casts(game, bear)) == [
            ("{1}{G}", 3),
            ("{3}{B}", 4),
        ]
        escape(game, bear, price="{3}{B}")
        assert len(game.state.players[0].exile) == 5


def _static(**escape_fields):
    return {
        "id": "t_bad_breach",
        "name": "Bad Breach",
        "oracle_text": "",
        "mana_cost": "{1}{R}",
        "types": ["Enchantment"],
        "abilities": [
            {
                "kind": "static",
                "text": "x",
                "effect": "cast_from_graveyard",
                "affects_player": "you",
                "affects_spells": {"not_types": ["Land"]},
                **escape_fields,
            }
        ],
    }


class TestTheLoaderRefuses:
    @pytest.mark.parametrize(
        "rider",
        [{}, {"exile_from_graveyard": 0}, {"exile_from_graveyard": 3, "life": 2}, {"mana": ""}],
    )
    def test_a_malformed_rider(self, rider):
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(_static(escape=rider)))

    def test_escape_beside_flashback(self):
        with pytest.raises(DslError, match="second price"):
            compile_card(
                CardModel.model_validate(
                    _static(escape={"exile_from_graveyard": 3}, grants_flashback=True)
                )
            )

    def test_escape_on_another_static(self):
        card = _static(escape={"exile_from_graveyard": 3})
        card["abilities"][0]["effect"] = "cast_from_library_top"
        with pytest.raises(DslError, match="escape"):
            compile_card(CardModel.model_validate(card))

    def test_the_op_without_a_cap_is_accepted_only_with_escape(self):
        card = {
            "id": "t_bad_grant",
            "name": "Bad Grant",
            "oracle_text": "",
            "mana_cost": "{B}",
            "types": ["Sorcery"],
            "spell_effects": [
                {"op": "grant_graveyard_cast", "affects_spells": {"types": ["Creature"]}}
            ],
        }
        with pytest.raises(DslError, match="max_per_turn"):
            compile_card(CardModel.model_validate(card))
        card["spell_effects"][0]["escape"] = {"exile_from_graveyard": 4}
        compile_card(CardModel.model_validate(card))

    def test_a_static_without_a_cap_is_accepted_with_escape(self):
        compile_card(CardModel.model_validate(_static(escape={"exile_from_graveyard": 3})))
