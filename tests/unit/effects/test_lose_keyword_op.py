"""The `lose_keyword` op -- "until end of turn, creatures your opponents control
**lose hexproof and shroud and can't have hexproof or shroud**".

Arcane Lighthouse is the witness. The `lose_keyword` static already said the
same words for as long as its source stood; this is the one-shot form, and two
rules decide its shape.

**611.2c, which set it reaches.** "A continuous effect from a resolved spell or
ability that modifies the characteristics or changes the controller of any
objects modifies only the values of objects on the battlefield at that time."
Losing an ability is a characteristic change (layer 6, 613.1f), so the creatures
are the ones the ability found as it resolved. A creature an opponent casts
afterwards, or takes control of afterwards, keeps its hexproof; one that blinks
is a new object (400.7) and has it again. The static would get all three wrong,
because it reads its filter on every recompute.

**"Can't have", which grant wins.** A bare "loses hexproof" is a layer-6
removal that a later grant survives (613.7). "And can't have hexproof" is a
prohibition, so nothing given after the ability resolves -- an opponent's
`grant_keyword`, an anthem, a hexproof counter -- hands the keyword back. That
is why the entry is read in the last keyword step of `chars`, beside the static,
and not where the until-end-of-turn grants are.

Without the op the Lighthouse could only be a static, which would be on from the
moment the land entered and free of its {1}, {T}.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Keyword, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, change_control, clear_until_eot
from commanderblitz.engine.targeting import can_be_targeted
from commanderblitz.engine.zones import move_object
from tests.conftest import keywords, only_oid

HEXPROOF_BEAR = "t_hexproof"
SHROUDED = "t_shrouded"
SHROUD_ANTHEM = "t_shroud_granter"  # "Creatures you control have shroud."
BEAR = "t_bear"
HEXPROOF = Keyword.HEXPROOF.value
SHROUD = Keyword.SHROUD.value

#: Arcane Lighthouse's effect, as the card writes it.
LIGHTHOUSE = {
    "op": "lose_keyword",
    "cant_have": True,
    "keywords": [HEXPROOF, SHROUD],
    "objects": {
        "controller": "opponent",
        "types": ["Creature"],
        "zone": "battlefield",
        "count": "all",
    },
}


def position(builder, mine=(BEAR,), theirs=(HEXPROOF_BEAR, SHROUDED)):
    """Player 0 holds the Lighthouse's ability; player 1 is the opponent.

    Returns ``(game, oid)`` with ``oid`` player 1's hexproof creature.
    """
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .build(advance=False)
    )
    return game, only_oid(game, HEXPROOF_BEAR, 1)


def run(game, spec: dict, controller: int = 0) -> None:
    ctx = EffectContext(state=game.state, controller=controller, source_oid=None)
    gen = execute(ctx, [spec])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def in_hand(game, card_id: str, pid: int = 1) -> int:
    return next(o for o in game.state.players[pid].hand if game.state.objects[o].def_id == card_id)


def grant(oid: int, keyword: str = HEXPROOF) -> dict:
    return {"op": "grant_keyword", "keywords": [keyword], "objects": {"oid": oid}}


class TestItTakesTheKeywords:
    def test_the_opponents_creatures_lose_both(self, builder):
        game, hexproof = position(builder)
        shrouded = only_oid(game, SHROUDED, 1)
        run(game, LIGHTHOUSE)

        assert HEXPROOF not in keywords(game, hexproof)
        assert SHROUD not in keywords(game, shrouded)

    def test_and_so_they_can_be_targeted(self, builder):
        """What the card is for: the targeting check reads derived keywords."""
        game, hexproof = position(builder)
        shrouded = only_oid(game, SHROUDED, 1)
        assert not can_be_targeted(game.state, 0, hexproof)
        assert not can_be_targeted(game.state, 0, shrouded)

        run(game, LIGHTHOUSE)
        assert can_be_targeted(game.state, 0, hexproof)
        assert can_be_targeted(game.state, 0, shrouded)

    def test_its_own_side_is_untouched(self, builder):
        game, _ = position(builder, mine=(HEXPROOF_BEAR,))
        run(game, LIGHTHOUSE)
        assert HEXPROOF in keywords(game, only_oid(game, HEXPROOF_BEAR, 0))

    def test_it_takes_only_what_it_names(self, builder):
        game, hexproof = position(builder)
        run(game, {**LIGHTHOUSE, "keywords": [SHROUD]})
        assert HEXPROOF in keywords(game, hexproof)


class TestItBeatsALaterGrant:
    """ "…and can't have hexproof or shroud" -- the clause that puts the entry
    after every grant rather than among the until-end-of-turn ones."""

    def test_a_later_grant_keyword_cannot_give_it_back(self, builder):
        game, hexproof = position(builder)
        bear = only_oid(game, BEAR, 0)
        run(game, LIGHTHOUSE)
        change_control(game.state, bear, 1)  # now an opponent's, and unaffected
        run(game, grant(hexproof), controller=1)
        run(game, grant(bear), controller=1)

        assert HEXPROOF not in keywords(game, hexproof)
        assert HEXPROOF in keywords(game, bear), "the grant itself works"

    def test_an_anthem_arriving_later_cannot_give_it_back(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR])
            .battlefield(1, [BEAR])
            .hand(1, [SHROUD_ANTHEM])
            .build(advance=False)
        )
        bear = only_oid(game, BEAR, 1)
        mine = only_oid(game, BEAR, 0)
        run(game, LIGHTHOUSE)
        move_object(game.state, in_hand(game, SHROUD_ANTHEM), Zone.BATTLEFIELD)
        change_control(game.state, mine, 1)  # unaffected, so the anthem reaches it

        assert SHROUD not in keywords(game, bear)
        assert SHROUD in keywords(game, mine), "the anthem itself works"

    def test_a_keyword_counter_cannot_give_it_back(self, builder):
        game, hexproof = position(builder)
        run(game, LIGHTHOUSE)
        add_counters(game.state, hexproof, HEXPROOF, 1)
        assert HEXPROOF not in keywords(game, hexproof)

    def test_losing_all_abilities_does_not_end_it(self, builder):
        """The prohibition is not an ability of the creature (113.1)."""
        game, hexproof = position(builder)
        run(game, LIGHTHOUSE)
        run(game, {"op": "lose_all_abilities", "objects": {"oid": hexproof}})
        run(game, grant(hexproof), controller=1)
        assert HEXPROOF not in keywords(game, hexproof)


class TestTheSetIsFixedAsItResolves:
    """611.2c: only the objects on the battlefield as the ability resolved."""

    def test_a_creature_that_arrives_later_keeps_hexproof(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR])
            .battlefield(1, [SHROUDED])
            .hand(1, [HEXPROOF_BEAR])
            .build(advance=False)
        )
        run(game, LIGHTHOUSE)
        late = move_object(game.state, in_hand(game, HEXPROOF_BEAR), Zone.BATTLEFIELD)

        assert HEXPROOF in keywords(game, late.oid)

    def test_a_creature_an_opponent_takes_later_keeps_hexproof(self, builder):
        game, _ = position(builder, mine=(HEXPROOF_BEAR,))
        mine = only_oid(game, HEXPROOF_BEAR, 0)
        run(game, LIGHTHOUSE)
        change_control(game.state, mine, 1)

        assert HEXPROOF in keywords(game, mine)

    def test_one_that_changes_sides_afterwards_stays_affected(self, builder):
        """The set is the objects, not "whatever an opponent controls now"."""
        game, hexproof = position(builder)
        run(game, LIGHTHOUSE)
        change_control(game.state, hexproof, 0)

        assert HEXPROOF not in keywords(game, hexproof)

    def test_a_blinked_creature_is_a_new_object_with_hexproof(self, builder):
        """400.7: the entry goes with the old object."""
        game, hexproof = position(builder)
        run(game, LIGHTHOUSE)
        move_object(game.state, hexproof, Zone.EXILE)
        back = move_object(game.state, hexproof, Zone.BATTLEFIELD)

        assert HEXPROOF in keywords(game, back.oid)


class TestWearingOff:
    def test_it_ends_at_cleanup(self, builder):
        game, hexproof = position(builder)
        run(game, LIGHTHOUSE)
        clear_until_eot(game.state)

        assert HEXPROOF in keywords(game, hexproof)
        assert not can_be_targeted(game.state, 0, hexproof)


def _lighthouse_card(**overrides) -> CardModel:
    effect = {**LIGHTHOUSE, **overrides}
    effect = {k: v for k, v in effect.items() if v is not None}
    return CardModel.model_validate(
        {
            "id": "t_probe_lighthouse",
            "name": "Probe Lighthouse",
            "types": ["Land"],
            "abilities": [
                {
                    "kind": "activated",
                    "cost": {"mana": "{1}", "tap": True},
                    "effects": [effect],
                }
            ],
        }
    )


class TestTheLoaderRefuses:
    def test_the_printed_effect_loads(self):
        compile_card(_lighthouse_card())

    def test_a_plain_loss_without_cant_have(self):
        """"Loses flying until end of turn" is the weaker, unbuilt removal."""
        with pytest.raises(DslError, match="cant_have"):
            compile_card(_lighthouse_card(cant_have=None))

    def test_no_keywords(self):
        with pytest.raises(DslError, match="keywords"):
            compile_card(_lighthouse_card(keywords=[]))

    def test_an_unknown_keyword(self):
        with pytest.raises(DslError, match="unknown keyword"):
            compile_card(_lighthouse_card(keywords=["hexproff"]))

    def test_no_objects(self):
        with pytest.raises(DslError, match="objects"):
            compile_card(_lighthouse_card(objects=None))

    def test_a_longer_duration(self):
        with pytest.raises(DslError, match="duration"):
            compile_card(_lighthouse_card(duration="until_your_next_turn"))
