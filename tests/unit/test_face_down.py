"""Morph and manifest — face-down permanents.

    Morph {2}{G} — "You may cast this card face down as a 2/2 creature for {3}.
    Turn it face up any time for its morph cost."
    Manifest — "Put the top card of your library onto the battlefield face down
    as a 2/2 creature. Turn it face up any time for its mana cost if it's a
    creature card."

The census called this a subsystem and it is, but a small one, because the
engine already had the two things that make it hard elsewhere: `card_of` is a
single choke point (built for `transform`), and `chars` is a single place where
derived characteristics are decided.

So a face-down permanent is `chars` returning a **2/2 colourless creature with
nothing else**, before any layer, while `card_of` goes on answering with the
real card — which is what turning it face up needs in order to find it again.

Morph and manifest are one mechanism seen from two sides, and the tests are
mostly about the seams where they differ:

| | morph | manifest |
|---|---|---|
| how it arrives | **cast** face down for `{3}`, fixed by 702.37a | put there off the library |
| price to turn up | the printed **morph cost** | the hidden card's own mana cost |
| a non-creature card | cannot have morph at all (load error) | can be manifested, and can never be turned up (701.34c) |

**Turning face up reuses `ActionKind.ACTIVATE` with `ability_index` 0**, which
is not a shortcut: a face-down permanent has no abilities (707.2), so index 0 is
free, and modelling it as its own `ActionKind` would change the RL action space
for one row.

*Divergence*: anthems and counters do not apply to a face-down permanent here,
because the shell is returned instead of the printed face rather than layered
over it. A real face-down creature is still affected by them.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, Keyword
from tests.conftest import action_for_card, pass_until

FOREST = "forest"
PLAINS = "plains"
BEAST = "t_morpher"        # {4}{G} 5/5 flier, morph {2}{G}
RITE = "t_manifester"      # {1}{W} sorcery, manifest one
WHITE_CREATURE = "t_soulbond"   # {2}{W} -- payable off Plains


def morph_board(builder, lands: int = 6):
    return (
        builder(players=2)
        .battlefield(0, [FOREST] * lands)
        .hand(0, [BEAST])
        .library(0, [FOREST] * 20)
        .library(1, [FOREST] * 20)
        .build()
    )


def cast_face_down(game):
    action = next(a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.face_down)
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack)
    return action.source


def turn_up_action(game, oid: int):
    pass_until(
        game, lambda g: (d := g.pending()) is not None and d.player == 0, limit=200
    )
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == oid
        ),
        None,
    )


class TestCastingFaceDown:
    def test_the_face_down_line_is_offered(self, builder):
        game = morph_board(builder, lands=3)
        lines = [a for a in game.legal_actions() if a.kind is ActionKind.CAST]
        assert [a.face_down for a in lines] == [True], "{3} is payable, {4}{G} is not"

    def test_it_carries_no_targets(self, builder):
        """A face-down spell is a nameless 2/2 with no text."""
        game = morph_board(builder, lands=3)
        action = next(a for a in game.legal_actions() if a.kind is ActionKind.CAST)
        assert action.targets == ()

    def test_both_lines_appear_with_the_mana_for_both(self, builder):
        game = morph_board(builder, lands=6)
        lines = [a for a in game.legal_actions() if a.kind is ActionKind.CAST]
        assert sorted(a.face_down for a in lines) == [False, True]


class TestTheShell:
    def test_it_is_a_two_two_creature(self, builder):
        game = morph_board(builder, lands=3)
        beast = cast_face_down(game)
        c = chars(game.state, beast)

        assert (c.power, c.toughness) == (2, 2)
        assert c.types == frozenset({"Creature"})

    def test_it_has_none_of_the_hidden_cards_characteristics(self, builder):
        game = morph_board(builder, lands=3)
        beast = cast_face_down(game)
        c = chars(game.state, beast)

        assert Keyword.FLYING.value not in c.keywords
        assert c.subtypes == frozenset()
        assert c.colors == frozenset()

    def test_the_real_card_is_still_underneath(self, builder):
        """`card_of` goes on answering, which is what turning it up needs."""
        game = morph_board(builder, lands=3)
        beast = cast_face_down(game)

        assert game.state.card_of(game.state.objects[beast]).id == BEAST

    def test_only_its_controller_may_see_it(self, builder):
        game = morph_board(builder, lands=3)
        beast = cast_face_down(game)
        assert game.state.objects[beast].revealed_to == {0}


class TestTurningFaceUp:
    def test_it_is_offered_for_the_morph_cost(self, builder):
        game = morph_board(builder, lands=6)
        beast = cast_face_down(game)
        assert turn_up_action(game, beast) is not None

    def test_it_is_not_offered_without_the_morph_cost(self, builder):
        """Checked *immediately*, before the lands untap.

        `turn_up_action` waits for your own priority, and waiting long enough
        reaches a later turn with everything untapped -- at which point the cost
        is payable and the assertion passes for the wrong reason.
        """
        game = morph_board(builder, lands=3)
        beast = cast_face_down(game)

        offered = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == beast
        ]
        assert offered == [], "all three lands paid the {3}"

    def test_the_creature_becomes_itself(self, builder):
        game = morph_board(builder, lands=6)
        beast = cast_face_down(game)
        game.apply(turn_up_action(game, beast))
        pass_until(game, lambda g: g.pending() is None or not g.state.stack)

        c = chars(game.state, beast)
        assert (c.power, c.toughness) == (5, 5)
        assert Keyword.FLYING.value in c.keywords
        assert not game.state.objects[beast].face_down

    def test_it_uses_no_stack(self, builder):
        """A special action: nothing to respond to."""
        game = morph_board(builder, lands=6)
        beast = cast_face_down(game)
        game.apply(turn_up_action(game, beast))

        assert game.state.stack == []

    def test_the_hidden_cards_abilities_are_suppressed_until_then(self, builder):
        """707.2 -- and the turn-up action is the *only* thing it offers."""
        game = morph_board(builder, lands=6)
        beast = cast_face_down(game)
        offered = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == beast
        ]
        assert len(offered) == 1


class TestManifest:
    def _manifest(self, builder, top: str):
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS] * 6)
            .hand(0, [RITE])
            .library(0, [top] + [PLAINS] * 20)
            .library(1, [PLAINS] * 20)
            .build()
        )
        oid = game.state.players[0].library[0]
        game.apply(action_for_card(game, ActionKind.CAST, RITE))
        pass_until(game, lambda g: not g.state.stack)
        return game, oid

    def test_the_card_arrives_face_down(self, builder):
        game, oid = self._manifest(builder, BEAST)
        obj = game.state.objects[oid]

        assert obj.face_down
        assert (chars(game.state, oid).power, chars(game.state, oid).toughness) == (2, 2)

    def test_a_creature_card_turns_up_for_its_own_cost(self, builder):
        """Manifest's price is the hidden card's own, not a morph cost.

        A white creature, because the board is Plains: manifest can put *any*
        card down, and what makes it turnable is being a creature card whose
        printed cost the controller can actually pay.
        """
        game, oid = self._manifest(builder, WHITE_CREATURE)
        action = turn_up_action(game, oid)

        assert action is not None
        assert "morph" not in (action.label or "")

    def test_a_land_can_be_manifested_and_never_turned_up(self, builder):
        """701.34c: only a creature card may be turned face up this way."""
        game, oid = self._manifest(builder, PLAINS)

        assert game.state.objects[oid].face_down
        assert turn_up_action(game, oid) is None


class TestTheLoaderGuards:
    def _card(self, **extra) -> CardModel:
        base = {
            "id": "t_morph_probe",
            "name": "Morph Probe",
            "mana_cost": "{4}{G}",
            "types": ["Creature"],
            "power": 5,
            "toughness": 5,
        }
        base.update(extra)
        return CardModel.model_validate(base)

    def test_a_creature_with_morph_loads(self):
        compile_card(self._card(morph="{2}{G}"))

    def test_a_noncreature_with_morph_is_refused(self):
        """It would be castable face down and unable to turn up into anything."""
        with pytest.raises(DslError, match="only on creature cards"):
            compile_card(
                self._card(types=["Artifact"], power=None, toughness=None, morph="{2}")
            )

    def test_megamorph_needs_a_morph_cost(self):
        with pytest.raises(DslError, match="needs a 'morph' cost"):
            compile_card(self._card(morph_counter=True))
