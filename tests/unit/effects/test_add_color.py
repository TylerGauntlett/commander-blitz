"""A colour added in addition to the others: the `add_color` op.

    "Destroy all creatures, then return a creature card put into a graveyard
    this way to the battlefield under your control. **It's a black Zombie in
    addition to its other colors and types.**"      -- Necromantic Selection

Rule 105.3 lets an effect change an object's colour, and "in addition to its
other colors" makes it an *adding* layer-5 effect (613.1e): the printed colours
stay, and nothing about types or size changes. The sentence is two ops over one
binding -- `add_subtype` for the Zombie, `add_color` for the black -- and the
binding is new too: `return_from_graveyard`'s ``as`` names the one card that
came back, where before only `link` could, tying it to a sorcery that has
already exiled itself.

The near miss is `animate` with `colors`. It does add colours, but a creature
animation sets a base power and toughness, so the returned 5/5 would come back
whatever size the card wrote down; `keep_pt` is refused on a binding and
`keep_colors` belongs to an exact animation, which replaces colours. Without
this op the card was a wrath that returned a creature of the wrong colour, or
one of the wrong size.

Necromantic Selection, Grimoire of the Dead and Liliana, Death's Majesty are
the witnesses.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader.effects import _validate_effect
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects import RECORDING_OPS, execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_colors, animate, clear_until_eot
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, pt

BEAR = "t_bear"  # {1}{G} 2/2 Bear
FLYER = "t_flyer"  # {1}{U} 2/2 Bird with flying
BAD_MOON = "bad_moon"  # Black creatures get +1/+1.

BLACK = {"op": "add_color", "colors": ["B"], "objects": {"binding": "returned"}}
ZOMBIE = {"op": "add_subtype", "subtypes": ["Zombie"], "objects": {"binding": "returned"}}

#: Necromantic Selection's first three sentences.
SELECTION = [
    {
        "op": "destroy",
        "objects": {"zone": "battlefield", "types": ["Creature"], "count": "all"},
        "as": "destroyed",
    },
    {
        "op": "return_from_graveyard",
        "destination": "battlefield",
        "controller": "you",
        "objects": {
            "binding": "destroyed",
            "zone": "graveyard",
            "types": ["Creature"],
            "is_token": False,
            "count": 1,
        },
        "as": "returned",
    },
    ZOMBIE,
    BLACK,
]

#: Grimoire of the Dead's second ability, its cost aside.
GRIMOIRE = [
    {
        "op": "put_onto_battlefield",
        "controller": "you",
        "objects": {"zone": "graveyard", "controller": "any", "types": ["Creature"], "count": "all"},
        "as": "returned",
    },
    ZOMBIE,
    BLACK,
]


def position(builder, mine=(), theirs=(), *, graveyards=((), ())):
    """Player 0's ``mine`` facing player 1's ``theirs``, graveyards as given."""
    b = builder(players=2).battlefield(0, list(mine)).battlefield(1, list(theirs))
    for pid, cards in enumerate(graveyards):
        b = b.graveyard(pid, list(cards))
    return b.build(advance=False)


def run(game, effects) -> EffectContext:
    """Resolve ``effects`` for player 0, picking the first option of any choice."""
    ctx = EffectContext(state=game.state, controller=0)
    gen = execute(ctx, effects)
    send = None
    while True:
        try:
            gen.send(send)
        except StopIteration:
            return ctx
        send = [0]


def in_graveyard(game, card_id: str) -> int:
    """The one ``card_id`` in any graveyard."""
    (oid,) = [
        o for p in game.state.players for o in p.graveyard if game.state.card(o).id == card_id
    ]
    return oid


def a_bear(builder):
    game = position(builder, [BEAR])
    return game, only_oid(game, BEAR)


class TestWhatItAdds:
    def test_the_colour_is_added_and_the_printed_one_stays(self, builder):
        game, bear = a_bear(builder)
        add_colors(game.state, bear, ["B"])
        assert chars(game.state, bear).colors == frozenset({"G", "B"})

    def test_types_and_size_are_untouched(self, builder):
        """What separates it from `animate`: no base power and toughness."""
        game, bear = a_bear(builder)
        add_colors(game.state, bear, ["B"])
        c = chars(game.state, bear)
        assert pt(game, bear) == (2, 2)
        assert c.types == frozenset({"Creature"})
        assert c.subtypes == frozenset({"Bear"})

    def test_a_colour_it_already_has_changes_nothing(self, builder):
        game, bear = a_bear(builder)
        add_colors(game.state, bear, ["G"])
        assert chars(game.state, bear).colors == frozenset({"G"})

    def test_a_card_off_the_battlefield_is_not_touched(self, builder):
        game = position(builder, graveyards=([BEAR], ()))
        bear = in_graveyard(game, BEAR)
        assert add_colors(game.state, bear, ["B"]) == ()
        assert chars(game.state, bear).colors == frozenset({"G"})


class TestHowLongItLasts:
    def test_it_outlives_the_turn(self, builder):
        game, bear = a_bear(builder)
        add_colors(game.state, bear, ["B"])
        clear_until_eot(game.state)
        assert "B" in chars(game.state, bear).colors

    def test_a_permanent_that_leaves_and_comes_back_is_a_new_object(self, builder):
        """400.7: the returned card arrives with its printed colours."""
        game, bear = a_bear(builder)
        add_colors(game.state, bear, ["B"])
        move_object(game.state, bear, Zone.HAND, to_player=0)
        move_object(game.state, bear, Zone.BATTLEFIELD)
        assert chars(game.state, bear).colors == frozenset({"G"})


class TestTimestampOrder:
    """613.7: in layer 5 the later effect wins, so the order of the exact
    animation and the addition decides the colours."""

    def test_an_exact_animation_that_began_later_replaces_it(self, builder):
        game, bear = a_bear(builder)
        add_colors(game.state, bear, ["B"])
        animate(game.state, bear, 3, 3, subtypes=["Elk"], colors=["G"], permanent=True, exact=True)
        assert chars(game.state, bear).colors == frozenset({"G"})

    def test_an_exact_animation_that_began_earlier_is_added_to(self, builder):
        game = position(builder, [FLYER])
        flyer = only_oid(game, FLYER)
        animate(game.state, flyer, 3, 3, subtypes=["Elk"], colors=["G"], permanent=True, exact=True)
        add_colors(game.state, flyer, ["B"])
        assert chars(game.state, flyer).colors == frozenset({"G", "B"})


class TestAStaticSeesIt:
    def test_bad_moon_pumps_a_creature_made_black(self, builder):
        """A pipeline input like an added subtype, so a static's filter reads
        it: the black half of the black Zombie is worth what the Zombie half is."""
        game = position(builder, [BEAR, BAD_MOON])
        bear = only_oid(game, BEAR)
        assert pt(game, bear) == (2, 2)
        add_colors(game.state, bear, ["B"])
        assert pt(game, bear) == (3, 3)


class TestNecromanticSelection:
    def test_the_returned_creature_is_a_black_zombie_of_its_own_size(self, builder):
        game = position(builder, [BEAR], [FLYER])
        ctx = run(game, SELECTION)

        (returned,) = ctx.bindings["returned"]
        obj = game.state.objects[returned]
        assert obj.zone is Zone.BATTLEFIELD and obj.controller == 0
        c = chars(game.state, returned)
        assert "B" in c.colors and "Zombie" in c.subtypes
        assert len(c.colors) == 2, "its printed colour stays"
        assert pt(game, returned) == (2, 2)

    def test_only_the_returned_creature_changes(self, builder):
        game = position(builder, [BEAR], [FLYER])
        ctx = run(game, SELECTION)

        (returned,) = ctx.bindings["returned"]
        other = next(o for o in ctx.bindings["destroyed"] if o != returned)
        assert game.state.objects[other].zone is Zone.GRAVEYARD

    def test_an_empty_board_returns_nothing_and_binds_nothing(self, builder):
        game = position(builder)
        ctx = run(game, SELECTION)
        assert ctx.bindings["returned"] == []


class TestReturnFromGraveyardBinding:
    def test_it_binds_what_arrived(self, builder):
        game = position(builder, graveyards=([BEAR], ()))
        bear = in_graveyard(game, BEAR)
        effects = [
            {
                "op": "return_from_graveyard",
                "destination": "battlefield",
                "objects": {"controller": "you", "types": ["Creature"], "count": "all"},
                "as": "returned",
            },
            BLACK,
        ]
        ctx = run(game, effects)
        assert ctx.bindings["returned"] == [bear]
        assert "B" in chars(game.state, bear).colors

    def test_it_records(self):
        assert "return_from_graveyard" in RECORDING_OPS


class TestGrimoireOfTheDead:
    def test_every_graveyards_creatures_arrive_as_black_zombies(self, builder):
        game = position(builder, graveyards=([BEAR], [FLYER]))
        bear, flyer = in_graveyard(game, BEAR), in_graveyard(game, FLYER)
        run(game, GRIMOIRE)

        for oid in (bear, flyer):
            assert game.state.objects[oid].controller == 0
            c = chars(game.state, oid)
            assert "B" in c.colors and "Zombie" in c.subtypes
        assert chars(game.state, flyer).colors == frozenset({"U", "B"})
        assert pt(game, flyer) == (2, 2)


class TestTheLoader:
    def test_the_op_is_accepted(self):
        _validate_effect(BLACK, "test", {})

    def test_no_colours_is_refused(self):
        with pytest.raises(DslError, match="colors"):
            _validate_effect({**BLACK, "colors": []}, "test", {})

    def test_an_unknown_colour_is_refused(self):
        with pytest.raises(DslError, match="colour"):
            _validate_effect({**BLACK, "colors": ["black"]}, "test", {})

    def test_no_objects_is_refused(self):
        with pytest.raises(DslError, match="objects"):
            _validate_effect({"op": "add_color", "colors": ["B"]}, "test", {})

    def test_a_duration_is_refused(self):
        with pytest.raises(DslError, match="duration"):
            _validate_effect({**BLACK, "duration": "until_end_of_turn"}, "test", {})

    def test_a_type_or_size_is_refused_not_dropped(self):
        with pytest.raises(DslError, match="colours only"):
            _validate_effect({**BLACK, "subtypes": ["Zombie"]}, "test", {})

    def test_as_on_return_from_graveyard_is_accepted(self):
        _validate_effect(SELECTION[1], "test", {})
