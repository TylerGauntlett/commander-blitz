""""You may cast this card from your graveyard as long as you control a Zombie."

Gravecrawler. A permission printed on the card it frees, so it has to be read
off the card *while the card is in the graveyard* -- and the battlefield walk
that every other `cast_from_graveyard` static goes through never looks there.
Without a reader the static loaded clean and was inert, and the only shipped
alternative, `graveyard_cost`, has no condition: the card would be castable from
the graveyard whether or not a Zombie was around, a strictly better card.

So the permission is a `cast_from_graveyard` static with ``active_zones:
["graveyard"]``, read by `player_statics.own_graveyard_cast_permission`. It is
cast at the printed price and the creature enters the battlefield as any
creature spell does (it is not flashback: nothing exiles it).

The condition is asked when legality offers the line, which is the moment
601.2a/601.3 care about -- the permission must hold as the cast begins -- and it
is asked afresh every time, so a Zombie that leaves takes the line with it
(`TestTheConditionIsLive`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import settle_to_priority

CRAWLER = "t_gravecrawler"
ZOMBIE = "t_zombie"
KEEPER = "t_crypt_keeper"  # Edgar-shaped: a creature spell from your graveyard, once a turn
OGRE = "t_gy_creature"  # a non-Zombie creature card


def position(builder, *, mine=(), theirs=(), graveyard=(CRAWLER,)):
    game = (
        builder(players=2)
        .battlefield(0, ["swamp"] * 4 + ["mountain"] + list(mine))
        .battlefield(1, ["plains", *theirs])
        .graveyard(0, list(graveyard))
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def in_graveyard(game, card_id: str, seat: int = 0) -> int:
    found = [o for o in game.state.players[seat].graveyard if game.state.objects[o].def_id == card_id]
    assert len(found) == 1, f"expected one {card_id} in seat {seat}'s graveyard"
    return found[0]


def on_battlefield(game, card_id: str) -> int:
    return next(o for o in game.state.battlefield if game.state.objects[o].def_id == card_id)


def casts(game, oid: int) -> list:
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


def cast_and_resolve(game, oid: int) -> None:
    game.apply(casts(game, oid)[0])
    settle_to_priority(game)
    while game.state.stack:
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
        settle_to_priority(game)


class TestTheCondition:
    def test_castable_from_the_graveyard_with_a_zombie(self, builder):
        game = position(builder, mine=[ZOMBIE])
        assert casts(game, in_graveyard(game, CRAWLER))

    def test_not_castable_without_one(self, builder):
        """The control: without the condition this is `graveyard_cost`'s card."""
        game = position(builder)
        assert not casts(game, in_graveyard(game, CRAWLER))

    def test_an_opponents_zombie_does_not_count(self, builder):
        """ "…as long as **you** control a Zombie" -- you is the card's owner."""
        game = position(builder, theirs=[ZOMBIE])
        assert not casts(game, in_graveyard(game, CRAWLER))

    def test_a_non_zombie_does_not_count(self, builder):
        game = position(builder, mine=[OGRE])
        assert not casts(game, in_graveyard(game, CRAWLER))


class TestTheConditionIsLive:
    def test_the_line_goes_when_the_zombie_leaves(self, builder):
        game = position(builder, mine=[ZOMBIE])
        crawler = in_graveyard(game, CRAWLER)
        assert casts(game, crawler)

        move_object(game.state, on_battlefield(game, ZOMBIE), Zone.GRAVEYARD)
        assert not casts(game, crawler)

    def test_and_comes_back_with_another(self, builder):
        game = position(builder, mine=[ZOMBIE])
        crawler = in_graveyard(game, CRAWLER)
        zombie = on_battlefield(game, ZOMBIE)
        move_object(game.state, zombie, Zone.GRAVEYARD)
        assert not casts(game, crawler)

        move_object(game.state, zombie, Zone.BATTLEFIELD)
        assert casts(game, crawler)


class TestTheCast:
    def test_it_resolves_onto_the_battlefield(self, builder):
        """Printed price, normal destination: no flashback exile on a permanent."""
        game = position(builder, mine=[ZOMBIE])
        crawler = in_graveyard(game, CRAWLER)
        cast_and_resolve(game, crawler)

        obj = game.state.objects[crawler]
        assert obj.zone is Zone.BATTLEFIELD
        assert obj.cast_from_graveyard

    def test_it_costs_the_printed_mana(self, builder):
        game = position(builder, mine=[ZOMBIE])
        untapped = sum(
            1
            for o in game.state.battlefield
            if game.state.objects[o].def_id == "swamp" and not game.state.objects[o].tapped
        )
        cast_and_resolve(game, in_graveyard(game, CRAWLER))
        after = sum(
            1
            for o in game.state.battlefield
            if game.state.objects[o].def_id == "swamp" and not game.state.objects[o].tapped
        )
        assert untapped - after == 1

    def test_on_the_battlefield_it_frees_nothing(self, builder):
        """The permission is a graveyard one. On the battlefield it is not
        Gravecrawler's to lend another creature card."""
        game = position(builder, mine=[CRAWLER], graveyard=(OGRE,))
        assert not casts(game, in_graveyard(game, OGRE))


class TestBesideAnotherPermission:
    def test_the_cards_own_permission_is_the_one_spent(self, builder):
        """Billing the Keeper for a cast the card could make alone would take
        that turn's use away for nothing."""
        game = position(builder, mine=[ZOMBIE, KEEPER], graveyard=(CRAWLER, OGRE))
        ogre = in_graveyard(game, OGRE)
        crawler = in_graveyard(game, CRAWLER)
        assert len(casts(game, crawler)) == 1, "one line, not one per permission"

        cast_and_resolve(game, crawler)
        assert casts(game, ogre)


def crawler_model(**overrides) -> CardModel:
    static = {
        "kind": "static",
        "text": "You may cast this card from your graveyard as long as you control a Zombie.",
        "effect": "cast_from_graveyard",
        "affects_player": "you",
        "active_zones": ["graveyard"],
        "condition": {"exists": {"subtypes": ["Zombie"], "controller": "you"}},
    }
    card = {
        "id": "x",
        "name": "X",
        "oracle_text": static["text"],
        "mana_cost": "{B}",
        "types": ["Creature"],
        "subtypes": ["Zombie"],
        "power": 2,
        "toughness": 1,
    }
    card_overrides = overrides.pop("card", {})
    static.update(overrides)
    static = {k: v for k, v in static.items() if v is not None}
    return CardModel.model_validate({**card, **card_overrides, "abilities": [static]})


class TestLoadTimeRefusals:
    def test_the_shape_loads(self):
        compile_card(crawler_model())

    def test_unconditional_loads_too(self):
        """Squee's shape: the condition is optional."""
        compile_card(crawler_model(condition=None))

    def test_a_second_zone(self):
        with pytest.raises(DslError, match="active in the graveyard alone"):
            compile_card(crawler_model(active_zones=["battlefield", "graveyard"]))

    @pytest.mark.parametrize(
        "key,value",
        [
            ("affects_spells", {"types": ["Creature"]}),
            ("static_max_per_turn", 1),
            ("grants_flashback", True),
            ("enters_tapped", True),
        ],
    )
    def test_keys_nothing_reads(self, key, value):
        with pytest.raises(DslError, match="the card's own permission"):
            compile_card(crawler_model(**{key: value}))

    def test_an_opponents_permission(self):
        with pytest.raises(DslError, match="must be 'you'"):
            compile_card(crawler_model(affects_player="opponent"))

    def test_a_nonpermanent(self):
        with pytest.raises(DslError, match="permanent cards only"):
            compile_card(
                crawler_model(
                    card={
                        "types": ["Sorcery"],
                        "subtypes": [],
                        "power": None,
                        "toughness": None,
                        "spell_effects": [{"op": "draw", "amount": {"const": 1}}],
                    }
                )
            )

    def test_a_bad_condition(self):
        with pytest.raises(DslError):
            compile_card(crawler_model(condition={"no_such_condition": True}))
