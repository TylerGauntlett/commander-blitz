"""An X/X token: base power and toughness fixed by the effect that creates it.

Shark Typhoon is the witness, and both of its token lines are this one thing:
"Whenever you cast a noncreature spell, create an **X/X** blue Shark creature
token with flying, where X is that spell's mana value" and, after "Cycling
{X}{1}{U}", "When you cycle this card, create an **X/X** blue Shark…".

**The rules argument.** 111.4: a token's characteristics are the ones the
effect creating it specifies, and 707.2 makes those its copiable values. So the
X is the token's *printed* size -- not +1/+1 counters on a 0/0, and not a pump.
Each wrong reading is a different card, and each is visible:

- counters on a 0/0 Fractal-style token would be moved by proliferate, removed
  by -1/-1 counters annihilating them, and counted by "creatures with counters";
- a `set_pt` would sit in layer 7b, over which nothing a later effect sets
  could land, and would end with its duration;
- a size re-read as the game goes on would shrink when the spell leaves the
  stack. The X is evaluated once, as the token is made.

So `create_token` carries ``power`` and ``toughness`` value expressions and
hands them to `primitives.create_token` as the token's copy overrides -- the
base size eternalize's 4/4 already travels in (707.9b) -- and `variable_pt`
marks the tokens that take them: the pool's Shark is written 0/0 with the flag,
the way its token card prints `*/*`.

Two readers had to learn the X they were measuring. 202.3e counts the X a spell
on the stack was cast with, so "that spell's mana value" for Secure the Wastes
cast with X = 3 is 4, where the printed {X}{W} is 1. And the X in "When you
cycle this card" is the X paid in the cycling cost -- the card was never cast,
so the only place that number survives is the `cycle` event.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.loader.linking import validate_token_references
from commanderblitz.cards.registry import CardRegistry
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, Color, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters
from tests.conftest import (
    action_for_card,
    keywords,
    oids_of,
    plus_one_counters,
    pt,
    settle,
)

TYPHOON = "shark_typhoon"
SHARK = "shark_x_x_u_flying"
#: "{X}{W}: Create X 1/1 white Warrior creature tokens." A noncreature spell
#: whose mana value on the stack is X + 1.
WASTES = "secure_the_wastes"
BEAR = "t_bear"


def choose_x(game, x: int) -> None:
    pending = game.pending()
    assert pending is not None and pending.kind is DecisionKind.CHOOSE_X
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == x)
    )


def typhoon_in_play(builder, hand=(WASTES,)):
    """The enchantment on player 0's side, with plenty of white and green."""
    return (
        builder(players=2)
        .battlefield(0, [TYPHOON] + ["plains"] * 6 + ["forest"] * 4)
        .hand(0, list(hand))
        .active(0)
        .build()
    )


def cast_wastes(game, x: int) -> None:
    game.apply(action_for_card(game, ActionKind.CAST, WASTES))
    choose_x(game, x)
    settle(game)


def typhoon_in_hand(builder):
    return (
        builder(players=2)
        .battlefield(0, ["island"] * 8)
        .hand(0, [TYPHOON])
        .library(0, ["island"] * 5)
        .active(0)
        .build()
    )


def cycle_for(game, x: int) -> None:
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and game.state.objects[a.source].def_id == TYPHOON
        )
    )
    choose_x(game, x)
    settle(game)


def sharks(game) -> list[int]:
    return oids_of(game, SHARK, 0)


def run_op(game, spec: dict, *, source: int) -> None:
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    gen = execute(ctx, [spec])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


class TestTheToken:
    def test_it_is_a_blue_shark_with_flying_written_zero_zero(self, registry):
        shark = registry.get(SHARK)
        assert shark.is_token and shark.is_creature and shark.variable_pt
        assert (shark.power, shark.toughness) == (0, 0)
        assert list(shark.subtypes) == ["Shark"]
        assert sorted(shark.colors) == ["U"]
        assert "flying" in shark.keywords

    def test_no_printed_size_token_carries_the_flag(self):
        """The 0/0s that are created and then given counters are *not* X/X."""
        pool = CardRegistry.from_dir()
        flagged = sorted(c.id for c in pool if c.variable_pt)
        assert flagged == sorted([SHARK, "dragon_illusion_x_x_r_flying_haste"])
        assert not pool.get("fractal_0_0_gu").variable_pt


class TestTheCastTrigger:
    @pytest.mark.parametrize("x", [0, 3])
    def test_x_is_the_spells_mana_value_on_the_stack(self, builder, x):
        """202.3e: Secure the Wastes for X = 3 is mana value 4, not its printed 1."""
        game = typhoon_in_play(builder)
        cast_wastes(game, x)
        (shark,) = sharks(game)
        assert pt(game, shark) == (x + 1, x + 1)
        assert "flying" in keywords(game, shark)

    def test_the_size_does_not_move_once_the_spell_is_gone(self, builder):
        """Read once, as the token is made: the spell resolving changes nothing."""
        game = typhoon_in_play(builder)
        cast_wastes(game, 2)
        assert not game.state.stack
        assert pt(game, sharks(game)[0]) == (3, 3)

    def test_a_creature_spell_makes_no_shark(self, builder):
        game = typhoon_in_play(builder, hand=(BEAR,))
        game.apply(action_for_card(game, ActionKind.CAST, BEAR))
        settle(game)
        assert sharks(game) == []


class TestTheCyclingTrigger:
    def test_x_is_the_x_paid_to_cycle(self, builder):
        game = typhoon_in_hand(builder)
        cycle_for(game, 3)
        (shark,) = sharks(game)
        assert pt(game, shark) == (3, 3)
        assert len(game.state.players[0].hand) == 1, "cycling still draws"

    def test_cycling_for_zero_makes_a_zero_zero_that_dies(self, builder):
        """The printed card at X = 0: a 0/0 Shark, put into the graveyard by
        704.5f -- and a token there ceases to exist."""
        game = typhoon_in_hand(builder)
        mark = len(game.state.events)
        cycle_for(game, 0)
        assert sharks(game) == []
        assert any(
            e.type == "zone_change" and e.data.get("card") == SHARK
            for e in game.state.events[mark:]
        ), "it was made, and then died"


class TestItIsABaseSizeNotCounters:
    def test_counters_land_on_top_of_it(self, builder):
        game = typhoon_in_hand(builder)
        cycle_for(game, 2)
        (shark,) = sharks(game)
        assert plus_one_counters(game, shark) == 0, "the X is no counters at all"
        add_counters(game.state, shark, "+1/+1", 1)
        assert pt(game, shark) == (3, 3)

    def test_a_copy_of_it_is_the_same_size(self, builder):
        """707.2: the size its creating effect set is copiable."""
        game = typhoon_in_hand(builder)
        cycle_for(game, 2)
        (shark,) = sharks(game)
        run_op(game, {"op": "copy_permanent", "objects": {"self_only": True}}, source=shark)
        assert sorted(pt(game, oid) for oid in sharks(game)) == [(2, 2), (2, 2)]

    def test_a_doubled_shark_is_the_same_size(self, builder):
        """Doubling Season's "twice that many of those tokens" are X/X too."""
        game = (
            builder(players=2)
            .battlefield(0, ["doubling_season"] + ["island"] * 8)
            .hand(0, [TYPHOON])
            .library(0, ["island"] * 5)
            .active(0)
            .build()
        )
        cycle_for(game, 2)
        assert sorted(pt(game, oid) for oid in sharks(game)) == [(2, 2), (2, 2)]

    def test_its_colour_is_the_tokens(self, builder):
        game = typhoon_in_hand(builder)
        cycle_for(game, 1)
        assert set(chars(game.state, sharks(game)[0]).colors) == {Color.BLUE}


def maker(token: str, **pair) -> dict:
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "Probe.",
        "mana_cost": "{U}",
        "types": ["Sorcery"],
        "spell_effects": [{"op": "create_token", "token": token, **pair}],
    }


def load_with(card: dict) -> None:
    """The probe card alongside the real token pool, through the linking checks."""
    pool = CardRegistry.from_dir()
    cards = {c.id: c for c in pool}
    cards["probe"] = compile_card(CardModel.model_validate(card))
    validate_token_references(cards)


X = {"x": True}


class TestTheLoader:
    def test_the_pair_on_the_x_x_token_loads(self):
        load_with(maker(SHARK, power=X, toughness=X))

    def test_the_x_x_token_without_the_pair_is_refused(self):
        """It would arrive the 0/0 it is written as and die."""
        with pytest.raises(DslError, match="is an X/X token"):
            load_with(maker(SHARK))

    def test_the_pair_on_a_printed_size_token_is_refused(self):
        """A 0/0 Fractal given X counters is not an X/X; neither is a 2/2."""
        for token in ("fractal_0_0_gu", "drake_2_2_u_flying"):
            with pytest.raises(DslError, match="has a printed size"):
                load_with(maker(token, power=X, toughness=X))

    def test_one_half_of_the_pair_is_refused(self):
        with pytest.raises(DslError, match="go together"):
            compile_card(CardModel.model_validate(maker(SHARK, power=X)))

    def test_the_flag_needs_a_zero_zero_creature_token(self):
        bad = {
            "id": "probe_token",
            "name": "Probe Token",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "is_token": True,
            "variable_pt": True,
        }
        with pytest.raises(DslError, match="X/X creature token"):
            compile_card(CardModel.model_validate(bad))
        with pytest.raises(DslError, match="X/X creature token"):
            compile_card(CardModel.model_validate({**bad, "power": 0, "toughness": 0, "is_token": False}))

    def test_a_replacement_cannot_create_it(self):
        """``create_instead`` names a token by id alone, with no size to give it."""
        card = {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "Probe.",
            "mana_cost": "{U}",
            "types": ["Enchantment"],
            "abilities": [
                {
                    "kind": "static",
                    "text": "Probe.",
                    "effect": "replace_token_creation",
                    "affects_token": {"types": ["Creature"]},
                    "create_instead": [SHARK],
                }
            ],
        }
        with pytest.raises(DslError, match="X/X token whose size"):
            load_with(card)
