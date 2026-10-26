"""Duplicant -- the size and creature types of the last creature card exiled with it.

    Imprint -- When this creature enters, you may exile target nontoken
    creature.
    As long as a card exiled with this creature is a creature card, this
    creature has the power, toughness, and creature types of the last creature
    card exiled with it. It's still a Shapeshifter.

The `imprint_characteristics` static. Three rules make the card, and each is a
way to get it wrong:

* **607.2a, linked abilities.** "Exiled with this creature" means exiled by its
  own linked ability, and by *this object*: an oid survives every zone change,
  so the card's `exiled_by` alone would let a flickered Duplicant (400.7, a new
  object) keep the size its previous incarnation imprinted. The link it reads
  is the source's ordered `exiled_cards`, emptied as it leaves.
* **"The last creature card".** Order matters once two cards are linked, and a
  card that left exile is no longer exiled with anything, so the effect falls
  back to the one before it, or stops.
* **613.4b and 613.1d.** The size is a 7b setting effect and the creature types
  a layer-4 replacement: counters and anthems still add on top, the old creature
  types go and Shapeshifter stays. Nothing else is copied -- not flying, not a
  colour, not a name.

604.3 makes the copied numbers the card's numbers *in exile*: a `*/*` card's
characteristic-defining ability and a changeling card's every-creature-type
both function there.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars, creature_types_of
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import exile, link_exiled, move_object
from tests.conftest import only_oid, pass_until, settle, static_probe

DUPLICANT = "t_duplicant"
STAR = "t_star_beast"
ANGEL = "serra_angel"
BEAR = "grizzly_bears"
CHANGELING = "changeling_sentinel"


def position(builder, theirs=(ANGEL,), *, take: str | None = ANGEL):
    """Duplicant arrives on player 0's side and imprints ``take`` (or nothing).

    Returns ``(game, duplicant)``.
    """
    game = (
        builder(players=2)
        .battlefield(1, list(theirs))
        .hand(0, [DUPLICANT])
        .build()
    )
    dup = next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == DUPLICANT)
    target = only_oid(game, take, 1) if take else None
    move_object(game.state, dup, Zone.BATTLEFIELD)

    def choose(g):
        decision = g.pending()
        if decision is None or decision.context.get("source") != dup:
            return False
        for action in g.legal_actions():
            wanted = (action.targets and action.targets[0].id == target) if target else not action.targets
            if wanted:
                g.apply(action)
                return True
        return False

    pass_until(game, choose)
    choose(game)
    settle(game)
    return game, dup


def oid_zone(game, card_id: str) -> Zone:
    return next(o.zone for o in game.state.objects.values() if o.def_id == card_id)


def size(game, oid: int) -> tuple[int, int]:
    c = chars(game.state, oid)
    return c.power, c.toughness


def link(game, oid: int, dup: int) -> None:
    """Exile ``oid`` with Duplicant, as its own linked ability would."""
    exile(game.state, oid)
    link_exiled(game.state, oid, dup)


class TestTheImprint:
    def test_it_takes_the_exiled_creature_s_size(self, builder):
        game, dup = position(builder)
        assert oid_zone(game, ANGEL) is Zone.EXILE
        assert size(game, dup) == (4, 4)

    def test_and_its_creature_types_replacing_its_own_but_shapeshifter(self, builder):
        game, dup = position(builder)
        assert creature_types_of(game.state, dup) == {"Angel", "Shapeshifter"}

    def test_nothing_else_is_copied(self, builder):
        """Not flying, not white, and still an artifact."""
        game, dup = position(builder)
        c = chars(game.state, dup)
        assert "flying" not in c.keywords
        assert c.colors == frozenset()
        assert {"Artifact", "Creature"} <= c.types

    def test_declining_leaves_the_printed_two_four(self, builder):
        game, dup = position(builder, take=None)
        assert size(game, dup) == (2, 4)
        assert creature_types_of(game.state, dup) == {"Shapeshifter"}

    def test_counters_still_add_on_top(self, builder):
        """613.4b before 613.4c: a +1/+1 counter lands on the copied size."""
        game, dup = position(builder)
        game.state.objects[dup].counters["+1/+1"] = 1
        game.state.bump_chars()
        assert size(game, dup) == (5, 5)


class TestTheLastCreatureCard:
    def test_the_last_one_exiled_wins(self, builder):
        game, dup = position(builder, theirs=(ANGEL, BEAR), take=BEAR)
        assert size(game, dup) == (2, 2)
        link(game, only_oid(game, ANGEL, 1), dup)
        assert size(game, dup) == (4, 4)
        assert creature_types_of(game.state, dup) == {"Angel", "Shapeshifter"}

    def test_when_the_last_leaves_exile_the_one_before_it_counts(self, builder):
        game, dup = position(builder, theirs=(ANGEL, BEAR), take=BEAR)
        angel = only_oid(game, ANGEL, 1)
        link(game, angel, dup)
        move_object(game.state, angel, Zone.GRAVEYARD)
        assert size(game, dup) == (2, 2)
        assert creature_types_of(game.state, dup) == {"Bear", "Shapeshifter"}

    def test_a_noncreature_card_is_skipped(self, builder):
        game, dup = position(builder, theirs=(ANGEL, "forest"))
        link(game, only_oid(game, "forest", 1), dup)
        assert size(game, dup) == (4, 4)

    def test_only_a_noncreature_card_is_no_effect(self, builder):
        game, dup = position(builder, theirs=("forest",), take=None)
        link(game, only_oid(game, "forest", 1), dup)
        assert size(game, dup) == (2, 4)


class TestTheLinkEnds:
    def test_a_card_that_leaves_exile_ends_it(self, builder):
        game, dup = position(builder)
        angel = game.state.objects[dup].exiled_cards[-1]
        move_object(game.state, angel, Zone.GRAVEYARD)
        assert size(game, dup) == (2, 4)
        assert creature_types_of(game.state, dup) == {"Shapeshifter"}

    def test_exiled_again_by_something_else_is_not_exiled_with_it(self, builder):
        game, dup = position(builder)
        angel = game.state.objects[dup].exiled_cards[-1]
        move_object(game.state, angel, Zone.BATTLEFIELD)
        exile(game.state, angel)
        assert size(game, dup) == (2, 4)

    def test_a_flickered_duplicant_is_a_new_object(self, builder):
        """400.7: the card stays in exile, and it is not this object's."""
        game, dup = position(builder)
        angel = game.state.objects[dup].exiled_cards[-1]
        move_object(game.state, dup, Zone.EXILE)
        move_object(game.state, dup, Zone.BATTLEFIELD)
        settle(game)
        assert game.state.objects[angel].zone is Zone.EXILE
        assert size(game, dup) == (2, 4)


class TestCharacteristicDefiningAbilitiesInExile:
    def test_a_star_card_counts_in_exile(self, builder):
        """604.3, and its "you" is the card's owner (108.4a), not Duplicant's controller."""
        game, dup = position(builder, theirs=(STAR, BEAR, BEAR), take=STAR)
        assert size(game, dup) == (2, 3), "player 1 controls the two Bears"

    def test_a_changeling_card_is_every_creature_type_in_exile(self, builder):
        game, dup = position(builder, theirs=(CHANGELING,), take=CHANGELING)
        types = creature_types_of(game.state, dup)
        assert {"Shapeshifter", "Human", "Dragon", "Bear"} <= types
        assert size(game, dup) == (3, 2)


class TestTheLoaderRefuses:
    def _compile(self, **static):
        return compile_card(
            CardModel.model_validate(static_probe({"effect": "imprint_characteristics", **static}))
        )

    def test_it_describes_only_its_own_source(self):
        with pytest.raises(DslError, match="self_only"):
            self._compile(affects={"controller": "you"})
        with pytest.raises(DslError, match="needs 'affects'"):
            self._compile()

    def test_it_takes_no_written_size(self):
        with pytest.raises(DslError, match="no 'power'"):
            self._compile(affects={"self_only": True}, power={"const": 1}, toughness={"const": 1})

    def test_a_kept_type_is_a_literal(self):
        with pytest.raises(DslError, match="add_subtype"):
            self._compile(affects={"self_only": True}, subtypes=[{"chosen_type_of": "self"}])

    def test_the_printed_shape_loads(self):
        self._compile(affects={"self_only": True}, subtypes=["Shapeshifter"])
