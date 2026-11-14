"""The as-enters copy whose exception applies only to an embalmed token.

    "You may have this creature enter as a copy of any creature on the
    battlefield, **except if this creature was embalmed, the token has no mana
    cost, it's white, and it's a Zombie in addition to its other types**.
    Embalm {3}{U}{U}"                              -- Vizier of Many Faces

Three rules make the card, and each is a way to get it wrong.

**The embalmed token is asked too.** 614.1b: the token embalm creates is a copy
of Vizier, so it has Vizier's replacement and enters as a copy of a creature --
`copy_permanent` asks the question of each token before it exists
(`effects.tokens.ask_token_enters_copies`). Without it the embalmed Vizier
would arrive as a white 0/1 Zombie Shapeshifter, a different card.

**A later copy overwrites embalm's exception.** Embalm's "except it's a white
Zombie with no mana cost" is part of the copiable values the token was created
with (707.9b), and the as-enters copy then overwrites every copiable value
(613.2a, 707.2) -- `GameObject.live_copy_overrides` is none while `copying`
applies. That is why Vizier prints its own exception: without it the copy would
be a red Ogre with a mana cost.

**The exception is conditional.** ``except_.condition`` is
``{"embalmed": true}``, true only of a token stamped by `copy_permanent`'s
``embalm`` key (702.128a). Cast from hand, Vizier is a plain copy: an Ogre
that is red, costs {3}{R} and is no Zombie.

Deceptive Frostkite is the unconditional ``add_subtypes``: "except it's a Dragon
in addition to its other types".
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects.values import object_mana_value
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import keywords, only_oid, pass_until
from tests.unit.copies.test_enters_as_copy import cast, name_of

VIZIER = "t_eace_vizier"  # 0/1 blue, copy of any creature; white Zombie if embalmed
FROSTKITE = "t_eace_frostkite"  # copy of your power-4 creature, plus Dragon and flying
OGRE = "t_eace_ogre"  # 4/4 red Ogre, {3}{R}: the thing copied


def position(builder, *, hand=(), graveyard=(), lands=6):
    game = (
        builder(players=2)
        .battlefield(0, ["island"] * lands)
        .battlefield(0, [OGRE])
        .hand(0, list(hand))
        .graveyard(0, list(graveyard))
        .library(0, ["island"] * 20)
        .library(1, ["island"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def embalm(game, *, say_yes: bool = True) -> int:
    """Activate the Vizier's embalm, answer the copy question, return the token."""
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE and game.state.objects[a.source].def_id == VIZIER
    )
    game.apply(action)
    for _ in range(40):
        pending = game.pending()
        if pending is None:
            break
        actions = game.legal_actions()
        if pending.kind is DecisionKind.MAY:
            want = ActionKind.YES if say_yes else ActionKind.NO
            game.apply(next(a for a in actions if a.kind is want))
            continue
        choose = next((a for a in actions if a.kind is ActionKind.CHOOSE), None)
        if choose is not None:
            game.apply(choose)
            continue
        if pending.kind is DecisionKind.PRIORITY and game.state.stack:
            game.apply(next(a for a in actions if a.kind is ActionKind.PASS))
            continue
        break
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
    return next(o for o in game.state.battlefield if game.state.objects[o].is_token)


def colors_of(game, oid: int) -> set[str]:
    return {str(c) for c in chars(game.state, oid).colors}


def subtypes_of(game, oid: int) -> set[str]:
    return {str(s) for s in chars(game.state, oid).subtypes}


class TestTheEmbalmedTokenEntersAsACopy:
    def test_it_is_asked_and_copies_the_creature(self, builder):
        game = position(builder, graveyard=[VIZIER])
        token = embalm(game)
        assert game.state.objects[token].embalmed
        assert name_of(game, token) == "Test Ogre"
        c = chars(game.state, token)
        assert (c.power, c.toughness) == (4, 4)

    def test_the_exception_makes_it_a_white_zombie_with_no_mana_cost(self, builder):
        game = position(builder, graveyard=[VIZIER])
        token = embalm(game)
        assert colors_of(game, token) == {"W"}
        assert subtypes_of(game, token) == {"Ogre", "Zombie"}
        assert object_mana_value(game.state, game.state.objects[token]) == 0
        assert not game.state.card_of(game.state.objects[token]).mana_cost.text

    def test_declined_it_is_embalm_s_own_white_zombie_vizier(self, builder):
        """No copy, so embalm's exception is the token's copiable values."""
        game = position(builder, graveyard=[VIZIER])
        token = embalm(game, say_yes=False)
        assert name_of(game, token) == "Test Vizier"
        assert colors_of(game, token) == {"W"}
        assert subtypes_of(game, token) == {"Shapeshifter", "Cleric", "Zombie"}
        assert object_mana_value(game.state, game.state.objects[token]) == 0


class TestALaterCopyOverwritesEmbalmsException:
    def test_without_its_own_exception_the_copy_is_plain(self, builder):
        """The same token, its condition failing: embalm's white, Zombie and
        missing mana cost are gone with the copy that overwrote them."""
        game = position(builder, graveyard=[VIZIER])
        token = embalm(game)
        obj = game.state.objects[token]
        obj.embalmed = False
        obj.copying_colors = None
        obj.copying_add_subtypes = None
        obj.copying_no_mana_cost = False
        game.state.bump_chars()
        assert colors_of(game, token) == {"R"}
        assert subtypes_of(game, token) == {"Ogre"}
        assert object_mana_value(game.state, obj) == 4


class TestCastFromHandItIsAPlainCopy:
    def test_not_embalmed_no_exception(self, builder):
        game = position(builder, hand=[VIZIER])
        cast(game, VIZIER, copy_id=OGRE)
        oid = only_oid(game, VIZIER, 0)
        assert name_of(game, oid) == "Test Ogre"
        assert colors_of(game, oid) == {"R"}
        assert subtypes_of(game, oid) == {"Ogre"}
        assert object_mana_value(game.state, game.state.objects[oid]) == 4

    def test_declined_it_is_the_blue_shapeshifter(self, builder):
        game = position(builder, hand=[VIZIER])
        cast(game, VIZIER, say_yes=False)
        oid = only_oid(game, VIZIER, 0)
        assert colors_of(game, oid) == {"U"}
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (0, 1)


class TestAnUnconditionalSubtype:
    def test_the_copy_is_a_dragon_with_flying(self, builder):
        game = position(builder, hand=[FROSTKITE], lands=8)
        cast(game, FROSTKITE, copy_id=OGRE)
        oid = only_oid(game, FROSTKITE, 0)
        assert name_of(game, oid) == "Test Ogre"
        assert subtypes_of(game, oid) == {"Ogre", "Dragon"}
        assert "flying" in keywords(game, oid)
        assert colors_of(game, oid) == {"R"}, "no colour clause, the copied colour"

    def test_the_subtype_ends_with_the_copy(self, builder):
        from commanderblitz.engine.enums import Zone
        from commanderblitz.engine.zones import move_object

        game = position(builder, hand=[FROSTKITE], lands=8)
        cast(game, FROSTKITE, copy_id=OGRE)
        oid = only_oid(game, FROSTKITE, 0)
        move_object(game.state, oid, Zone.HAND)
        obj = game.state.objects[oid]
        assert obj.copying_add_subtypes is None
        assert "Dragon" not in game.state.card_of(obj).subtypes


def _model(except_: dict, abilities=()) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_eace_probe",
            "name": "Probe",
            "mana_cost": "{3}",
            "types": ["Creature"],
            "power": 0,
            "toughness": 0,
            "abilities": list(abilities),
            "replacements": [
                {
                    "event": "self_enters_as_copy",
                    "copying": {"zone": "battlefield", "types": ["Creature"]},
                    "except_": except_,
                }
            ],
        }
    )


EMBALM = {
    "kind": "activated",
    "text": "Embalm {3}",
    "active_zones": ["graveyard"],
    "sorcery_speed_only": True,
    "cost": {"mana": "{3}", "exile_from_graveyard": {"self_only": True, "count": 1}},
    "effects": [
        {
            "op": "copy_permanent",
            "objects": {"zone": "exile", "controller": "any", "self_only": True},
            "controller": "you",
            "embalm": True,
            "except_": {"colors": ["W"], "add_subtypes": ["Zombie"], "no_mana_cost": True},
        }
    ],
}


class TestTheLoaderChecksIt:
    def test_the_vizier_shape_loads(self):
        compile_card(
            _model(
                {
                    "condition": {"embalmed": True},
                    "colors": ["W"],
                    "add_subtypes": ["Zombie"],
                    "no_mana_cost": True,
                },
                [EMBALM],
            )
        )

    def test_embalmed_without_an_embalm_ability_is_refused(self):
        with pytest.raises(DslError, match="'embalmed' condition"):
            compile_card(_model({"condition": {"embalmed": True}, "colors": ["W"]}))

    def test_a_condition_alone_is_an_empty_exception(self):
        with pytest.raises(DslError, match="empty exception"):
            compile_card(_model({"condition": {"embalmed": True}}, [EMBALM]))

    @pytest.mark.parametrize(
        ("except_", "message"),
        [
            ({"colors": ["White"]}, "unknown colour"),
            ({"colors": []}, "non-empty list"),
            ({"add_subtypes": []}, "non-empty list"),
            ({"no_mana_cost": False}, "must be true"),
        ],
    )
    def test_a_malformed_key_is_refused(self, except_, message):
        with pytest.raises(DslError, match=message):
            compile_card(_model(except_))

    def test_embalm_must_be_true(self):
        bad = {**EMBALM, "effects": [{**EMBALM["effects"][0], "embalm": "yes"}]}
        with pytest.raises(DslError, match="embalm: must be true"):
            compile_card(_model({"colors": ["W"]}, [bad]))
