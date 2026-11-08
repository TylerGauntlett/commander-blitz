"""A token copy whose size is computed: `copy_permanent`'s ``except_`` P/T as a value.

    "Destroy target creature. If that creature dies this way, its controller
    creates two tokens that are copies of that creature, except their power is
    half that creature's power and their toughness is half that creature's
    toughness. Round up each time."                          -- Saw in Half

707.9b: an exception to a copy effect becomes part of the copiable values. So
"half that creature's power" is worked out once, as the spell resolves, and the
tokens *are* that size from then on -- a number on the token, exactly like
eternalize's printed 4/4, never an expression re-read later. The number is the
creature's power as it last existed on the battlefield (608.2h), pumps and
counters included, which is what a `snapshot` taken before the `destroy` holds.

The rest of the sentence composes from what exists. "Dies this way" is
`destroy`'s ``as`` (only what was actually destroyed, 701.8a) narrowed to the
graveyard: indestructible and a regeneration shield are not destroyed at all,
and a death a replacement sent to exile was destroyed but did not *die*
(700.4). "Its controller" is ``{"controller_of": <snapshot>}``, the seat that
controlled it as it left, which is not the caster's when the target was an
opponent's creature.

The near miss is a literal ``except_`` size, which only ever fits one creature,
or a `create_token` of a fixed token, which is not a copy at all. Saw in Half is
the shipped witness.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader.effects import _validate_effect
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Keyword, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, pump
from tests.conftest import oids_of, only_oid, pt

OGRE = "t_f_3_3"  # 3/3 vanilla
BEAR = "t_f_2_2"  # 2/2 vanilla
TROLL = "t_regenerator"  # 2/2, {G}: regenerate

HALF_UP = {"round": "up"}
SAW = [
    {"op": "snapshot", "objects": {"binding": "victim"}, "as": "sawn"},
    {"op": "destroy", "objects": {"binding": "victim"}, "as": "destroyed"},
    {
        "op": "copy_permanent",
        "objects": {"binding": "destroyed", "zone": "graveyard"},
        "amount": 2,
        "controller": {"controller_of": "sawn"},
        "except_": {
            "power": {"half": {"of": {"power_of": {"var": "sawn"}}, **HALF_UP}},
            "toughness": {"half": {"of": {"toughness_of": {"var": "sawn"}}, **HALF_UP}},
        },
        "as": "copies",
    },
]


def board(builder, mine=(), theirs=()):
    """Player 0's ``mine`` facing player 1's ``theirs``, frozen in main phase."""
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .build(advance=False)
    )


def saw(game, victim: int, *, controller: int = 0) -> EffectContext:
    """Resolve Saw in Half's sentence at ``victim`` for ``controller``."""
    ctx = EffectContext(state=game.state, controller=controller)
    ctx.bindings["victim"] = victim
    for _ in execute(ctx, SAW):  # pragma: no cover - nothing here asks
        raise AssertionError("Saw in Half asks no questions")
    return ctx


def copies_of(game, card_id: str, pid: int | None = None) -> list[int]:
    return [
        o
        for o in oids_of(game, card_id, pid)
        if game.state.objects[o].is_token
    ]


class TestHalfTheSizeRoundedUp:
    def test_a_3_3_makes_two_2_2s(self, builder):
        game = board(builder, [OGRE])
        saw(game, only_oid(game, OGRE))

        tokens = copies_of(game, OGRE)
        assert len(tokens) == 2
        assert [pt(game, t) for t in tokens] == [(2, 2), (2, 2)], "3/2 rounds up to 2"

    def test_an_even_size_halves_exactly(self, builder):
        game = board(builder, [BEAR])
        saw(game, only_oid(game, BEAR))

        assert [pt(game, t) for t in copies_of(game, BEAR)] == [(1, 1), (1, 1)]

    def test_power_and_toughness_are_halved_separately(self, builder):
        """A 5/4 makes 3/2s: each half is rounded on its own ("each time")."""
        game = board(builder, [OGRE])
        ogre = only_oid(game, OGRE)
        pump(game.state, ogre, 2, 1)
        saw(game, ogre)

        assert [pt(game, t) for t in copies_of(game, OGRE)] == [(3, 2), (3, 2)]


class TestTheLastKnownSize:
    """608.2h: the creature as it last existed, not the printed card."""

    def test_a_pump_at_the_time_counts(self, builder):
        game = board(builder, [OGRE])
        ogre = only_oid(game, OGRE)
        pump(game.state, ogre, 4, 4)  # a 7/7 as it is sawn
        saw(game, ogre)

        assert [pt(game, t) for t in copies_of(game, OGRE)] == [(4, 4), (4, 4)]

    def test_counters_at_the_time_count(self, builder):
        game = board(builder, [OGRE])
        ogre = only_oid(game, OGRE)
        add_counters(game.state, ogre, "+1/+1", 2)  # a 5/5
        saw(game, ogre)

        tokens = copies_of(game, OGRE)
        assert [pt(game, t) for t in tokens] == [(3, 3), (3, 3)]
        assert all(not game.state.objects[t].counters.get("+1/+1") for t in tokens), (
            "a copy copies the printed card, never its counters"
        )

    def test_the_size_is_a_copiable_number(self, builder):
        """707.9b: stored as an integer, so it is never re-read later."""
        game = board(builder, [OGRE])
        saw(game, only_oid(game, OGRE))

        for t in copies_of(game, OGRE):
            overrides = game.state.objects[t].copy_overrides
            assert overrides["power"] == 2 and overrides["toughness"] == 2
            assert isinstance(overrides["power"], int)

    def test_a_pump_on_a_token_lands_on_top(self, builder):
        game = board(builder, [OGRE])
        saw(game, only_oid(game, OGRE))
        token = copies_of(game, OGRE)[0]
        pump(game.state, token, 1, 1)

        assert pt(game, token) == (3, 3)


class TestItsController:
    def test_an_opponents_creature_makes_the_opponents_tokens(self, builder):
        game = board(builder, theirs=[OGRE])
        saw(game, only_oid(game, OGRE), controller=0)

        assert len(copies_of(game, OGRE, 1)) == 2, "'its controller creates'"
        assert copies_of(game, OGRE, 0) == []

    def test_my_creature_makes_my_tokens(self, builder):
        game = board(builder, [OGRE])
        saw(game, only_oid(game, OGRE))

        assert len(copies_of(game, OGRE, 0)) == 2


class TestOnlyIfItDiesThisWay:
    def test_it_is_in_the_graveyard(self, builder):
        game = board(builder, theirs=[OGRE])
        ogre = only_oid(game, OGRE)
        saw(game, ogre)

        assert game.state.objects[ogre].zone is Zone.GRAVEYARD

    def test_indestructible_makes_no_tokens(self, builder):
        game = board(builder, theirs=[OGRE])
        ogre = only_oid(game, OGRE)
        game.state.objects[ogre].granted_keywords.add(Keyword.INDESTRUCTIBLE.value)
        game.state.bump_chars()
        ctx = saw(game, ogre)

        assert game.state.objects[ogre].zone is Zone.BATTLEFIELD
        assert ctx.bindings["destroyed"] == []
        assert copies_of(game, OGRE) == []

    def test_a_regenerated_creature_makes_no_tokens(self, builder):
        game = board(builder, theirs=[TROLL])
        troll = only_oid(game, TROLL)
        shield = EffectContext(state=game.state, controller=1, source_oid=troll)
        regenerate = [{"op": "regenerate", "objects": {"zone": "battlefield", "self_only": True}}]
        for _ in execute(shield, regenerate):  # pragma: no cover - nothing here asks
            raise AssertionError("a shield asks no questions")
        saw(game, troll)

        assert game.state.objects[troll].zone is Zone.BATTLEFIELD
        assert copies_of(game, TROLL) == []

    def test_a_death_sent_to_exile_did_not_die(self, builder):
        """Destroyed, but it never reached the graveyard, so it did not die."""
        game = board(builder, theirs=[OGRE])
        ogre = only_oid(game, OGRE)
        game.state.objects[ogre].dies_to = "exile"
        ctx = saw(game, ogre)

        assert game.state.objects[ogre].zone is Zone.EXILE
        assert ctx.bindings["destroyed"] == [ogre]
        assert copies_of(game, OGRE) == []


class TestLoadTime:
    COPY = SAW[2]

    def test_the_expression_loads(self):
        _validate_effect(self.COPY, "test", {})

    def test_a_literal_size_still_loads(self):
        _validate_effect({**self.COPY, "except_": {"power": 4, "toughness": 4}}, "test", {})

    @pytest.mark.parametrize(
        "power",
        [
            "half",
            -1,
            True,
            {"half": {"of": {"power_of": {"var": "sawn"}}}},  # no rounding direction
            {"halve": {"of": 3, "round": "up"}},  # not a value expression
        ],
    )
    def test_a_malformed_size_is_refused(self, power):
        bad = {**self.COPY, "except_": {**self.COPY["except_"], "power": power}}
        with pytest.raises(DslError, match=r"except_\.power"):
            _validate_effect(bad, "test", {})

    def test_half_a_size_is_refused(self):
        bad = {**self.COPY, "except_": {"power": self.COPY["except_"]["power"]}}
        with pytest.raises(DslError, match="come as a pair"):
            _validate_effect(bad, "test", {})
