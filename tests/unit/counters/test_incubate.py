"""Incubate N: an Incubator token created with N +1/+1 counters on it.

Rule 701.53a: *Create an Incubator token with N +1/+1 counters on it and "{2}:
Transform this artifact." It transforms into a 0/0 Phyrexian artifact
creature.* The Incubator is a double-faced token (the catalog's tfrc
Incubator // Phyrexian row): a colorless artifact in front, and a 0/0 colorless
Phyrexian artifact creature on the back. Sunfall ("Exile all creatures.
Incubate X, where X is the number of creatures exiled this way.") is the
shipped witness.

The ways to get it wrong, each a different card from the printed one:

- **Counters put on afterwards.** `create_token` then `add_counters` has the
  Incubator on the battlefield without them first, and is a second placement.
  They are on it as it is created (122.6), one placement with any other.
- **Treating the Incubator as a creature.** It enters as an artifact, so a
  counter replacement that reads "a creature you control" (Hardened Scales)
  does not apply, while "a permanent you control" (Doubling Season) does.
- **A creature from the start.** The front is not a creature: nothing dies at
  incubate 0 until it transforms, and nothing can attack with it until then.
- **Losing the counters on the way over.** Transforming is not a zone change
  (701.28), so the back face is a 0/0 that is N/N with what the front held.
- **Counting the wrong thing.** Sunfall's X is what its exile moved, every
  controller's creatures and tokens alike, not what is in exile afterwards.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.loader.linking import validate_token_references
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.ops_counters import INCUBATOR_TOKEN
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import (
    action_for_card,
    activations,
    oids_of,
    pass_until,
    plus_one_counters,
    pt,
    settle,
)

PHYREXIAN = "phyrexian_0_0_c_artifact"
BEAR = "t_bear"


def board(builder, *, mine=(), theirs=(), hand=("plains",)):
    """Player 0 in their precombat main with six Plains; the card in hand keeps
    the builder's auto-pass from handing an empty board's turn to player 1."""
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 6 + list(mine))
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .library(0, ["island"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def incubate(game, amount, *, bind: str | None = None) -> dict:
    """Run ``incubate`` directly for player 0. Returns the bindings."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    spec = {"op": "incubate", "amount": amount}
    if bind:
        spec["as"] = bind
    for _ in execute(ctx, [spec]):
        raise AssertionError("incubate asks nothing")
    return ctx.bindings


def incubators(game, pid: int = 0) -> list[int]:
    return oids_of(game, INCUBATOR_TOKEN, pid)


def transform_it(game, oid: int) -> None:
    """Activate "{2}: Transform this artifact." and let it resolve."""
    [activation] = activations(game, oid)
    game.apply(activation)
    settle(game)


class TestTheToken:
    def test_it_is_a_colorless_incubator_artifact(self, builder):
        game = board(builder)
        incubate(game, {"const": 2})
        [token] = incubators(game)
        c = chars(game.state, token)
        assert game.state.objects[token].is_token
        assert list(c.types) == ["Artifact"]
        assert list(c.subtypes) == ["Incubator"]
        assert not c.colors

    def test_it_carries_the_counters_as_it_is_created(self, builder):
        game = board(builder)
        incubate(game, {"const": 3})
        [token] = incubators(game)
        assert plus_one_counters(game, token) == 3

    def test_zero_still_creates_it_and_nothing_dies(self, builder):
        """Incubate 0 makes an Incubator with no counters, and an artifact at
        no toughness is not a creature for 704.5f to look at."""
        game = board(builder)
        incubate(game, {"const": 0})
        settle(game)
        [token] = incubators(game)
        assert plus_one_counters(game, token) == 0

    def test_a_negative_amount_is_zero(self, builder):
        """107.1b: a negative X is 0."""
        game = board(builder)
        incubate(game, {"const": -2})
        [token] = incubators(game)
        assert plus_one_counters(game, token) == 0

    def test_as_records_the_incubator(self, builder):
        game = board(builder)
        bindings = incubate(game, {"const": 1}, bind="made")
        assert bindings["made"] == incubators(game)


class TestTransforming:
    def test_the_back_face_is_a_phyrexian_with_the_counters(self, builder):
        game = board(builder)
        incubate(game, {"const": 3})
        [token] = incubators(game)
        transform_it(game, token)
        obj = game.state.objects[token]
        assert obj.transformed
        assert game.state.card_of(obj).id == PHYREXIAN
        c = chars(game.state, token)
        assert sorted(c.types) == ["Artifact", "Creature"]
        assert list(c.subtypes) == ["Phyrexian"]
        assert not c.colors
        assert pt(game, token) == (3, 3)

    def test_it_costs_two(self, builder):
        """Two lands: one activation and none left for a second."""
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 2)
            .hand(0, ["plains"])
            .library(0, ["island"] * 10)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        incubate(game, {"const": 1})
        incubate(game, {"const": 1})
        first, second = incubators(game)
        transform_it(game, first)
        assert not activations(game, second)

    def test_the_back_face_has_no_transform_ability(self, builder):
        game = board(builder)
        incubate(game, {"const": 1})
        [token] = incubators(game)
        transform_it(game, token)
        assert not activations(game, token)

    def test_incubate_zero_transformed_dies(self, builder):
        """A 0/0 creature once it is turned over, and 704.5f takes it."""
        game = board(builder)
        incubate(game, {"const": 0})
        [token] = incubators(game)
        transform_it(game, token)
        pass_until(game, lambda g: token not in g.state.battlefield)


class TestCounterReplacements:
    def test_doubling_season_doubles_the_tokens_and_the_counters(self, builder):
        """"A permanent you control": the Incubator, as it enters."""
        game = board(builder, mine=["doubling_season"])
        incubate(game, {"const": 3})
        made = incubators(game)
        assert len(made) == 2
        assert [plus_one_counters(game, oid) for oid in made] == [6, 6]

    def test_a_creature_only_addend_does_not_apply(self, builder):
        """Hardened Scales reads "a creature you control", and the Incubator
        enters as an artifact."""
        game = board(builder, mine=["t_rc_scales"])
        incubate(game, {"const": 3})
        [token] = incubators(game)
        assert plus_one_counters(game, token) == 3


class TestTheLoaderRefuses:
    @staticmethod
    def probe(effect):
        return CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "Incubate 2.",
                "mana_cost": "{W}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )

    def test_an_incubate_without_an_amount(self):
        with pytest.raises(DslError, match="incubate needs an 'amount'"):
            compile_card(self.probe({"op": "incubate"}))

    def test_creating_the_back_face_on_its_own(self, registry):
        """The Phyrexian is reached by transforming; created directly it would
        be a 0/0 artifact creature token no card prints."""
        card = compile_card(self.probe({"op": "create_token", "token": PHYREXIAN}))
        cards = {c.id: c for c in registry} | {card.id: card}
        with pytest.raises(DslError, match="back face"):
            validate_token_references(cards)


class TestSunfall:
    """The witness, through a real cast."""

    def cast(self, builder, *, mine=(), theirs=()):
        game = board(builder, mine=mine, theirs=theirs, hand=["sunfall"])
        game.apply(action_for_card(game, ActionKind.CAST, "sunfall"))
        settle(game)
        return game

    def test_it_exiles_every_creature_and_counts_them(self, builder):
        game = self.cast(builder, mine=[BEAR, BEAR], theirs=[BEAR, BEAR, BEAR])
        assert not oids_of(game, BEAR)
        [token] = incubators(game)
        assert plus_one_counters(game, token) == 5

    def test_tokens_count_as_creatures_exiled(self, builder):
        game = self.cast(builder, mine=["saproling_1_1_g"], theirs=[BEAR])
        [token] = incubators(game)
        assert plus_one_counters(game, token) == 2

    def test_noncreatures_stay_and_do_not_count(self, builder):
        game = self.cast(builder, mine=[BEAR], theirs=["sol_ring"])
        assert oids_of(game, "sol_ring", 1)
        [token] = incubators(game)
        assert plus_one_counters(game, token) == 1

    def test_an_empty_board_still_incubates_zero(self, builder):
        game = self.cast(builder)
        [token] = incubators(game)
        assert plus_one_counters(game, token) == 0


class TestTheArtIsTheTokenRow:
    def test_both_faces_take_the_incubator_row_and_differ_by_face(self, real_registry):
        """A double-faced token is one catalog row under the joined name, so
        neither "Incubator" nor "Phyrexian" alone finds it -- and the back's
        subtype on its own would find some other Phyrexian token's art."""
        from commanderblitz.cards.images import build_registry_images, load_index

        index = load_index()
        if index is None:
            pytest.skip("no card catalog")
        images = build_registry_images(real_registry, index)
        front, back = images[INCUBATOR_TOKEN], images[PHYREXIAN]
        assert front.scryfall_id is not None
        assert front.scryfall_id == back.scryfall_id
        assert (front.back, back.back) == (False, True)
