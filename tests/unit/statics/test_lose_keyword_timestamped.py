"""``lose_keyword_timestamped`` -- "equipped creature ... **loses flying**".

    Colossus Hammer -- "Equipped creature gets +10/+10 and loses flying.
    Equip {8}"

A plain "loses <keyword>" is a layer-6 removal, and 613.7 orders layer-6
effects by timestamp: an effect granting the keyword that is *newer* than the
removal gives it back, and one that is older does not. So Jump cast on the
hammered creature makes it fly, while a Jump cast before the hammer was
attached is taken away with the printed flying.

The near miss is `lose_keyword`, which is Archetype of Courage's "lose first
strike **and can't have or gain** first strike": a standing prohibition that
outranks every grant whatever its timestamp. Written with it, the hammer would
ground a creature through every later Jump, aura, anthem and flying counter --
a stronger card than the printed one. `TestANewerGrantGivesItBack` is that
claim, and `TestAnOlderGrantDoesNot` is the other half: a removal that only
took the printed keyword would be the weaker card.

The removal's timestamp is the Equipment's, renewed as it becomes attached
(613.7e), so moving the hammer away and back makes it newer than a grant made
in between. `TestReattachingRenewsIt`.

Witness: Colossus Hammer (`colossus_hammer` in `data/cards/auto/`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import Keyword, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, attach, grant_keyword
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, pt

HAMMER = "t_hammer"  # "Equipped creature gets +10/+10 and loses flying."
FLIER = "t_flier"  # 2/2 with flying printed
BEAR = "t_bear"  # 2/2 vanilla
FLY_ANTHEM = "t_flying_anthem"  # "Creatures you control have flying."
FLYING = Keyword.FLYING.value


def position(builder, *, extra=(), hand=()):
    """A flier and an unattached hammer; returns ``(game, flier, hammer)``."""
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * 3 + [FLIER, HAMMER, *extra])
        .battlefield(1, ["plains"] * 3)
        .hand(0, ["plains", *hand])
        .hand(1, ["plains"])
        .build()
    )
    return game, only_oid(game, FLIER, 0), only_oid(game, HAMMER, 0)


def flies(game, oid) -> bool:
    return FLYING in chars(game.state, oid).keywords


def put_into_play(game, card_id):
    """Move the card from player 0's hand onto the battlefield -- a new timestamp."""
    state = game.state
    oid = next(o for o in state.players[0].hand if state.objects[o].def_id == card_id)
    move_object(game.state, oid, Zone.BATTLEFIELD)
    return oid


class TestItTakesThePrintedKeyword:
    def test_the_equipped_creature_loses_flying(self, builder):
        game, flier, hammer = position(builder)
        attach(game.state, hammer, flier)
        assert not flies(game, flier)
        assert pt(game, flier) == (12, 12)

    def test_unequipped_it_flies(self, builder):
        """Pins that the removal is the static's: nothing attached, nothing lost."""
        game, flier, _ = position(builder)
        assert flies(game, flier)

    def test_moving_the_hammer_off_gives_it_back(self, builder):
        game, flier, hammer = position(builder, extra=(BEAR,))
        attach(game.state, hammer, flier)
        attach(game.state, hammer, only_oid(game, BEAR, 0))
        assert flies(game, flier)
        assert not flies(game, only_oid(game, BEAR, 0))


class TestANewerGrantGivesItBack:
    """613.7 -- the clause that separates this from `lose_keyword`."""

    def test_an_until_end_of_turn_grant_after_the_hammer(self, builder):
        """Jump on a hammered creature: it flies."""
        game, flier, hammer = position(builder)
        attach(game.state, hammer, flier)
        grant_keyword(game.state, flier, FLYING)
        assert flies(game, flier)

    def test_a_flying_counter_put_on_afterwards(self, builder):
        game, flier, hammer = position(builder)
        attach(game.state, hammer, flier)
        add_counters(game.state, flier, FLYING, 1)
        assert flies(game, flier)

    def test_an_anthem_that_arrives_afterwards(self, builder):
        game, flier, hammer = position(builder, hand=(FLY_ANTHEM,))
        attach(game.state, hammer, flier)
        put_into_play(game, FLY_ANTHEM)
        assert flies(game, flier)

    def test_a_permanent_grant_afterwards(self, builder):
        game, flier, hammer = position(builder)
        attach(game.state, hammer, flier)
        grant_keyword(game.state, flier, FLYING, permanent=True)
        assert flies(game, flier)


class TestAnOlderGrantDoesNot:
    """The other half: a grant older than the removal is removed with the
    printed keyword, so a creature that was already flying by Jump is grounded
    by the hammer."""

    def test_an_until_end_of_turn_grant_before_the_hammer(self, builder):
        game, flier, hammer = position(builder)
        grant_keyword(game.state, flier, FLYING)
        attach(game.state, hammer, flier)
        assert not flies(game, flier)

    def test_a_flying_counter_put_on_before(self, builder):
        game, _, hammer = position(builder, extra=(BEAR,))
        bear = only_oid(game, BEAR, 0)
        add_counters(game.state, bear, FLYING, 1)
        attach(game.state, hammer, bear)
        assert not flies(game, bear)

    def test_an_anthem_already_on_the_battlefield(self, builder):
        game, flier, hammer = position(builder, extra=(FLY_ANTHEM,))
        attach(game.state, hammer, flier)
        assert not flies(game, flier)

    def test_that_anthem_flies_the_unequipped(self, builder):
        """Pins that the anthem is real: the bear beside the flier flies."""
        game, flier, hammer = position(builder, extra=(FLY_ANTHEM, BEAR))
        attach(game.state, hammer, flier)
        assert flies(game, only_oid(game, BEAR, 0))


class TestReattachingRenewsIt:
    """613.7e: an Equipment receives a new timestamp as it becomes attached."""

    def test_a_grant_made_while_it_was_elsewhere_is_older(self, builder):
        game, flier, hammer = position(builder, extra=(BEAR,))
        attach(game.state, hammer, only_oid(game, BEAR, 0))
        grant_keyword(game.state, flier, FLYING)
        attach(game.state, hammer, flier)
        assert not flies(game, flier)


class TestItTakesOnlyWhatItNames:
    def test_another_keyword_survives(self, builder):
        game, flier, hammer = position(builder)
        grant_keyword(game.state, flier, Keyword.VIGILANCE.value)
        attach(game.state, hammer, flier)
        keywords = chars(game.state, flier).keywords
        assert Keyword.VIGILANCE.value in keywords
        assert FLYING not in keywords


class TestTheLoaderRefusesTheSilentFailures:
    def _card(self, **extra) -> CardModel:
        static = {
            "kind": "static",
            "text": "Equipped creature loses flying.",
            "effect": "lose_keyword_timestamped",
            "keywords": ["flying"],
            "affects": {"attached": True},
        }
        static.update(extra)
        return CardModel.model_validate(
            {
                "id": "t_lose_ts_probe",
                "name": "Lose Probe",
                "mana_cost": "{1}",
                "oracle_text": "Equipped creature loses flying.",
                "types": ["Artifact"],
                "subtypes": ["Equipment"],
                "abilities": [static],
            }
        )

    def test_the_printed_shape_loads(self):
        assert compile_card(self._card()) is not None

    def test_no_keywords_is_refused(self):
        with pytest.raises(DslError, match="needs the keywords it removes"):
            compile_card(self._card(keywords=[]))

    def test_no_affects_is_refused(self):
        with pytest.raises(DslError, match="needs 'affects'"):
            compile_card(self._card(affects=None))

    def test_a_numbered_keyword_is_refused(self):
        """Annihilator's instances are counted without timestamps, so the count
        and the keyword would disagree."""
        with pytest.raises(DslError, match="numbered keyword"):
            compile_card(self._card(keywords=["annihilator"]))
