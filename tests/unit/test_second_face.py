"""A second castable face — adventure, aftermath, and the halves of a split card.

    Adventure (715.1): "Test Errand {1}{G} — Sorcery — Adventure. You gain 3
    life. (Then exile this card. You may cast the creature later from exile.)"
    Aftermath (702.127a): "Cast this spell only from your graveyard. Then exile
    it."

The census called this cluster "one card, two castable things, differing in
cost, type line and destination", and that sentence is the design: the engine
already had **two `CardDef`s and one `GameObject`**, because that is what
`back_face` is. What it did not have is a second face that is *cast*.

That difference is the whole of the work, and it points one way:

| | back face | second face |
|---|---|---|
| how you get it | you **turn the permanent over** | you **cast the card as it** |
| when it is showing | while the permanent is transformed | only while it is a spell |
| may it be in a deck | no | no — and it is castable on its own, so it matters more |

Everything else is `card_of`, which is the single choke point `transform` built:
the cost, the type line, the targets, the effects and the name in the log are
all the second face's, with nothing else in the engine changed.

The three keywords sharing the mechanism differ in **two words**, which are the
two extra fields:

| | cast from | after it resolves |
|---|---|---|
| split half | hand | graveyard, like any spell |
| **adventure** | hand | exile — *and the front face may be cast from there* |
| **aftermath** | graveyard, and nowhere else | exile, finished |

The boundaries worth pinning are the ones where the rider does *not* fire, since
each is a card that would otherwise get exiled for free: 715.3c exiles an
Adventure **as it resolves**, so one that is countered or fizzles is an ordinary
card in an ordinary graveyard.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.loader.linking import link_faces
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Zone
from automtg.engine.errors import DslError
from tests.conftest import action_for_card, pass_until

FOREST = "forest"
MOUNTAIN = "mountain"
ADVENTURER = "t_adventurer"      # {3}{G} 3/3, Adventure "Test Errand" {1}{G}
ERRAND = "t_errand"              # the Adventure half: gain 3
ONSLAUGHT = "t_aftermath_front"  # {1}{R} sorcery, 2 damage
AFTERSHOCK = "t_aftermath_back"  # {2}{R}, from the graveyard only: gain 5
LEFT = "t_split_left"            # {R} instant, gain 1
RIGHT = "t_split_right"          # {2}{R} instant, gain 4
BEAR = "t_bear"


def position(builder, card: str, land: str = FOREST, lands: int = 6):
    return (
        builder(players=2)
        .battlefield(0, [land] * lands)
        .battlefield(0, [BEAR])
        .hand(0, [card])
        .library(0, [land] * 20)
        .library(1, [land] * 20)
        .build()
    )


def cast_lines(game) -> list[str]:
    return [a.base_label or "" for a in game.legal_actions() if a.kind is ActionKind.CAST]


def cast_named(game, name: str):
    """Take the cast line whose *label* names this face, and let it resolve."""
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and name in (a.base_label or "")
    )
    game.apply(action)
    pass_until(game, lambda g: g.pending() is None or not g.state.stack)
    return action


def only_object(game, def_id: str) -> int:
    return next(o.oid for o in game.state.objects.values() if o.def_id == def_id)


class TestBothLinesAreOffered:
    def test_the_adventure_is_a_second_cast_line(self, builder):
        game = position(builder, ADVENTURER)
        assert sorted(cast_lines(game)) == [
            "Cast Test Adventurer",
            "Cast Test Errand",
        ]

    def test_each_is_priced_as_itself(self, builder):
        """{1}{G} for the Adventure, and two lands cannot buy the {3}{G}."""
        game = position(builder, ADVENTURER, lands=2)
        assert cast_lines(game) == ["Cast Test Errand"]

    def test_a_split_card_offers_both_halves(self, builder):
        game = position(builder, LEFT, land=MOUNTAIN)
        assert sorted(cast_lines(game)) == [
            "Cast Test Left Half",
            "Cast Test Right Half",
        ]

    def test_an_aftermath_half_is_not_offered_from_hand(self, builder):
        """702.127a: "cast this spell only from your graveyard"."""
        game = position(builder, ONSLAUGHT, land=MOUNTAIN)
        assert cast_lines(game) == ["Cast Test Onslaught"]


class TestTheSpellIsThatFace:
    def test_it_does_the_second_faces_effects(self, builder):
        game = position(builder, ADVENTURER)
        life = game.state.players[0].life

        cast_named(game, "Test Errand")

        assert game.state.players[0].life == life + 3

    def test_the_log_names_the_face_that_was_cast(self, builder):
        """Not `def_id` -- a card that logged one name and did another's effects."""
        game = position(builder, ADVENTURER)
        cast_named(game, "Test Errand")

        cast = next(e for e in game.state.events if e.type == "spell_cast")
        assert cast.data["card"] == ERRAND

    def test_the_creature_line_is_still_the_creature(self, builder):
        game = position(builder, ADVENTURER)
        cast_named(game, "Test Adventurer")

        adventurer = only_object(game, ADVENTURER)
        assert game.state.objects[adventurer].zone is Zone.BATTLEFIELD

    def test_the_card_stops_showing_that_face_afterwards(self, builder):
        """Only while it is a spell: everywhere else it is the printed card."""
        game = position(builder, ADVENTURER)
        cast_named(game, "Test Errand")

        adventurer = only_object(game, ADVENTURER)
        assert not game.state.objects[adventurer].showing_second_face
        assert game.state.card_of(game.state.objects[adventurer]).id == ADVENTURER


class TestTheAdventureRider:
    def test_it_is_exiled_rather_than_binned(self, builder):
        game = position(builder, ADVENTURER)
        cast_named(game, "Test Errand")

        adventurer = only_object(game, ADVENTURER)
        assert game.state.objects[adventurer].zone is Zone.EXILE
        assert game.state.objects[adventurer].on_adventure

    def test_the_creature_may_then_be_cast_from_exile(self, builder):
        game = position(builder, ADVENTURER)
        cast_named(game, "Test Errand")
        pass_until(
            game, lambda g: (d := g.pending()) is not None and d.player == 0, limit=200
        )

        assert "Cast Test Adventurer" in cast_lines(game)

    def test_and_it_arrives_as_the_creature(self, builder):
        game = position(builder, ADVENTURER)
        cast_named(game, "Test Errand")
        pass_until(
            game, lambda g: (d := g.pending()) is not None and d.player == 0, limit=200
        )
        cast_named(game, "Test Adventurer")

        adventurer = only_object(game, ADVENTURER)
        obj = game.state.objects[adventurer]
        assert obj.zone is Zone.BATTLEFIELD
        assert not obj.on_adventure, "it has finished adventuring"

    def test_a_countered_adventure_goes_to_the_graveyard(self, builder):
        """715.3c exiles it *as it resolves*, and this one never did.

        Pushed onto the stack by hand rather than cast through the game loop:
        with nobody holding a response the whole cast resolves inside one
        `apply`, so there is never a stack for a counterspell to point at from
        outside. The claim under test is about the seam between `push_spell` and
        `_place_after_resolution`, which is exactly what this drives.
        """
        from automtg.engine import stack
        from automtg.engine.effects.context import EffectContext
        from automtg.engine.effects.ops_stack import op_counter

        game = position(builder, ADVENTURER)
        adventurer = only_object(game, ADVENTURER)
        item = stack.push_spell(game.state, adventurer, 0, second_face=True)
        assert game.state.objects[adventurer].showing_second_face

        ctx = EffectContext(state=game.state, controller=1, source_oid=adventurer)
        op_counter(ctx, {"op": "counter", "sid": {"const": item.sid}})

        assert game.state.objects[adventurer].zone is Zone.GRAVEYARD
        assert not game.state.objects[adventurer].on_adventure
        assert not game.state.objects[adventurer].showing_second_face


class TestAftermath:
    def _to_graveyard(self, builder):
        game = position(builder, ONSLAUGHT, land=MOUNTAIN)
        game.apply(action_for_card(game, ActionKind.CAST, ONSLAUGHT))
        pass_until(game, lambda g: g.pending() is None or not g.state.stack)
        pass_until(
            game, lambda g: (d := g.pending()) is not None and d.player == 0, limit=200
        )
        return game

    def test_the_second_half_appears_once_the_card_is_there(self, builder):
        game = self._to_graveyard(builder)
        assert "Cast Test Aftershock" in cast_lines(game)

    def test_the_front_half_does_not_come_back_with_it(self, builder):
        """The graveyard offer is the *second* face only, not a free flashback."""
        game = self._to_graveyard(builder)
        assert "Cast Test Onslaught" not in cast_lines(game)

    def test_it_exiles_itself_afterwards(self, builder):
        game = self._to_graveyard(builder)
        life = game.state.players[0].life

        cast_named(game, "Test Aftershock")

        card = only_object(game, ONSLAUGHT)
        assert game.state.objects[card].zone is Zone.EXILE
        assert game.state.players[0].life == life + 5

    def test_and_is_not_offered_a_second_time(self, builder):
        game = self._to_graveyard(builder)
        cast_named(game, "Test Aftershock")
        pass_until(
            game, lambda g: (d := g.pending()) is not None and d.player == 0, limit=200
        )

        assert "Cast Test Aftershock" not in cast_lines(game)

    def test_it_is_not_an_adventure(self, builder):
        """Exiled for good: nothing may be cast out of an Aftermath exile."""
        game = self._to_graveyard(builder)
        cast_named(game, "Test Aftershock")

        card = only_object(game, ONSLAUGHT)
        assert not game.state.objects[card].on_adventure


class TestASplitHalfIsNeither:
    def test_it_goes_to_the_graveyard_like_any_spell(self, builder):
        game = position(builder, LEFT, land=MOUNTAIN)
        cast_named(game, "Test Right Half")

        card = only_object(game, LEFT)
        assert game.state.objects[card].zone is Zone.GRAVEYARD

    def test_the_effects_are_the_half_that_was_cast(self, builder):
        game = position(builder, LEFT, land=MOUNTAIN)
        life = game.state.players[0].life

        cast_named(game, "Test Right Half")

        assert game.state.players[0].life == life + 4, "the {2}{R} half, not the {R} one"


class TestTheLoaderGuards:
    def _pool(self, front: dict, face: dict | None = None):
        cards = {}
        for model in (front, face):
            if model is None:
                continue
            card = compile_card(CardModel.model_validate(model))
            cards[card.id] = card
        link_faces(cards)
        return cards

    def _adventurer(self, **extra) -> dict:
        base = {
            "id": "t_face_probe",
            "name": "Face Probe",
            "mana_cost": "{3}{G}",
            "types": ["Creature"],
            "power": 3,
            "toughness": 3,
            "second_face": "t_face_probe_half",
        }
        base.update(extra)
        return base

    def _half(self, **extra) -> dict:
        base = {
            "id": "t_face_probe_half",
            "name": "Face Probe Half",
            "mana_cost": "{1}{G}",
            "types": ["Sorcery"],
            "spell_effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
        }
        base.update(extra)
        return base

    def test_a_well_formed_adventurer_loads(self):
        self._pool(self._adventurer(adventure=True), self._half())

    def test_adventure_without_a_second_face_is_refused(self):
        """It would be aftermath, silently, under the wrong word."""
        with pytest.raises(DslError, match="'adventure' needs a 'second_face'"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_face_probe",
                        "name": "Face Probe",
                        "mana_cost": "{3}{G}",
                        "types": ["Creature"],
                        "power": 3,
                        "toughness": 3,
                        "adventure": True,
                    }
                )
            )

    def test_a_zone_without_a_second_face_is_refused(self):
        with pytest.raises(DslError, match="'second_face_zone' needs a 'second_face'"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_face_probe",
                        "name": "Face Probe",
                        "mana_cost": "{R}",
                        "types": ["Instant"],
                        "second_face_zone": "graveyard",
                    }
                )
            )

    def test_a_missing_second_face_is_refused(self):
        with pytest.raises(DslError, match="references unknown card"):
            self._pool(self._adventurer())

    def test_a_second_face_with_no_cost_is_refused(self):
        """An unwritten cost parses to a back face's empty one -- a free spell."""
        with pytest.raises(DslError, match="needs a mana cost of its own"):
            self._pool(self._adventurer(), self._half(mana_cost=None))

    def test_a_permanent_adventure_is_refused(self):
        """715.1, and it never reaches the exile that makes it an Adventure."""
        with pytest.raises(DslError, match="must be an instant or a sorcery"):
            self._pool(
                self._adventurer(adventure=True),
                self._half(types=["Creature"], power=1, toughness=1, spell_effects=[]),
            )

    def test_a_non_permanent_adventurer_is_refused(self):
        with pytest.raises(DslError, match="must be a permanent"):
            self._pool(
                self._adventurer(
                    adventure=True, types=["Sorcery"], power=None, toughness=None
                ),
                self._half(),
            )

    def test_three_castable_faces_are_refused(self):
        """`card_of` is a lookup, not a walk."""
        cards = {}
        for model in (
            self._adventurer(),
            self._half(second_face="t_face_probe_third"),
            {
                "id": "t_face_probe_third",
                "name": "Face Probe Third",
                "mana_cost": "{G}",
                "types": ["Sorcery"],
            },
        ):
            card = compile_card(CardModel.model_validate(model))
            cards[card.id] = card
        with pytest.raises(DslError, match="may not have a second face of its own"):
            link_faces(cards)
