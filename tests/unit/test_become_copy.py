"""Gogo, Mysterious Mime — becoming a copy, in place.

    At the beginning of combat on your turn, you may have Gogo become a copy of
    another target creature you control until end of turn, except its name is
    Gogo, Mysterious Mime.

Rule 706, and every copy the DSL could already make is a different thing:

- `copy_permanent` calls `create_token` with the source's def id. It makes a
  **new** permanent and never touches the object it is pointed at, so it cannot
  turn Gogo into anything — and it adds a permanent the card never creates,
  which is a strictly better card and one that looks ordinary on the board.
- `animate` overwrites power, toughness, colors, types and keywords with
  literals, so it cannot take another object's whole printed face.
- `transform` only flips a double-faced card to its own back.

The implementation is a def id on the object, read by `state.card_of` — which
is already documented as the single place a permanent's current face is decided,
and is why transforming cards needed no changes anywhere else. A copy therefore
shows up in the characteristics layers, legality, combat and the serializer at
once, for the same reason and through the same door.

Two details the printed card turns on, and both are asserted:

- **"except its name is Gogo"** (706.2 lets a copy override characteristics),
  so the copy is *not* legendary-rule fodder for the thing it copied and still
  answers to its own name.
- **"until end of turn"**, which is why the marker carries a duration at all.
  Clone's shape copies permanently, and only the timed form is cleared at
  cleanup.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.effects import execute_one
from automtg.engine.effects.context import EffectContext
from automtg.engine.primitives import clear_until_eot
from tests.conftest import only_oid

MIME = "t_mime"
BEAR = "t_bear"


def board(builder, mime: str = MIME):
    game = builder(players=2).battlefield(0, [mime, BEAR]).build(advance=False)
    return game, only_oid(game, mime)


def become_copy(game, oid: int, **overrides):
    spec = {
        "op": "become_copy",
        "objects": {"zone": "battlefield", "self_only": True},
        "copying": {
            "zone": "battlefield",
            "controller": "you",
            "types": ["Creature"],
            "exclude_self": True,
            "count": 1,
        },
        **overrides,
    }
    ctx = EffectContext(state=game.state, controller=0, source_oid=oid)
    gen = execute_one(ctx, spec)
    try:
        while True:
            next(gen)
    except StopIteration:
        pass
    return game


def face(game, oid: int) -> str:
    return game.state.card_of(game.state.objects[oid]).name


def pt(game, oid: int):
    c = chars(game.state, oid)
    return c.power, c.toughness


class TestItCopiesInPlace:
    def test_it_takes_the_other_creatures_body(self, builder):
        game, mime = board(builder)
        assert pt(game, mime) == (1, 1)
        become_copy(game, mime)
        assert pt(game, mime) == (2, 2)

    def test_the_original_is_untouched(self, builder):
        """The half `copy_permanent` gets backwards: nothing new is created."""
        game, mime = board(builder)
        before = len(game.state.battlefield_objects(0))
        become_copy(game, mime)
        assert len(game.state.battlefield_objects(0)) == before

    def test_it_is_the_same_object(self, builder):
        """In place -- the permanent that was there is the one that changed."""
        game, mime = board(builder)
        become_copy(game, mime)
        assert game.state.objects[mime].on_battlefield


class TestTheNameIsOverridden:
    def test_it_keeps_its_own_name(self, builder):
        """"except its name is Gogo, Mysterious Mime" -- 706.2."""
        game, mime = board(builder)
        become_copy(game, mime, except_name="Test Mime")
        assert face(game, mime) == "Test Mime"
        assert pt(game, mime) == (2, 2), "the body still came from the copy"

    def test_without_the_override_it_takes_the_copied_name(self, builder):
        """The ordinary case -- Clone really is called what it copied."""
        game, mime = board(builder)
        become_copy(game, mime)
        assert face(game, mime) == "Test Bear"


class TestTheDuration:
    def test_it_wears_off_at_cleanup(self, builder):
        game, mime = board(builder)
        become_copy(game, mime, except_name="Test Mime")
        assert pt(game, mime) == (2, 2)

        clear_until_eot(game.state)

        assert pt(game, mime) == (1, 1)
        assert face(game, mime) == "Test Mime"

    def test_a_permanent_copy_survives_cleanup(self, builder):
        """Clone's shape, and why the marker carries a duration at all."""
        game, mime = board(builder)
        become_copy(game, mime, duration="permanent")
        clear_until_eot(game.state)
        assert pt(game, mime) == (2, 2)
        assert face(game, mime) == "Test Bear"


class TestNothingToCopy:
    def test_with_no_other_creature_it_does_nothing(self, builder):
        """"another target creature" -- and the "if you do" rider is false."""
        game = builder(players=2).battlefield(0, [MIME]).build(advance=False)
        mime = only_oid(game, MIME)
        become_copy(game, mime, except_name="Test Mime")
        assert pt(game, mime) == (1, 1)
        assert face(game, mime) == "Test Mime"
