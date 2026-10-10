"""``base_power`` / ``base_toughness`` — the copiable size, before anything was
done to the creature.

    Angelic Aberration — "When this creature enters, sacrifice any number of
    creatures **each with base power or toughness 1 or less**. Create that many
    4/4 colorless Eldrazi Angel creature tokens with flying and vigilance."

613.2 layers 7a and 7b: the base size is the printed one, or the one a copy
effect or a type-changing effect set. Counters (7d), anthems and Auras (7c) and
pump (7c) are all *later* layers, and the printed word "base" is the card
declining to read them.

The selector already had `power` and `toughness`, and they read the **live**
value — `chars(state, oid)`, after every continuous effect. That is the whole
reason this was a gap rather than a spelling: on any board carrying a +1/+1
counter or an anthem the two keys name different creatures **in both
directions**. The live keys would spare the 1/1 the printed card sacrifices the
moment somebody put a counter on it, and would swallow a creature whose printed
line is 1/1 but which is currently a 4/4. Either way the card sacrifices a
different set and makes a different number of Angels, and nothing on screen
says so.

`characteristics._base_pt` is the one function that answers it — the same one
`_compute` starts from and static filters stop at — so the selector's idea of
where a creature's size begins cannot drift from the pipeline's.

Witness: Angelic Aberration
(`angelic_aberration` in `data/cards/auto/`).
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool, validate_selector
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters
from tests.conftest import only_oid

BEAR = "t_bear"  # 2/2 vanilla
DORK = "t_dork"  # 1/1 with a mana ability
PLAINS = "plains"

#: Angelic Aberration's own clause, written exactly as the card writes it.
SMALL_BY_BASE = {
    "zone": "battlefield",
    "controller": "you",
    "types": ["Creature"],
    "count": "all",
    "any_of": [
        {"base_power": {"op": "<=", "value": {"const": 1}}},
        {"base_toughness": {"op": "<=", "value": {"const": 1}}},
    ],
}

#: The same line with the only words that existed before. It is a different set.
SMALL_BY_LIVE = {
    "zone": "battlefield",
    "controller": "you",
    "types": ["Creature"],
    "count": "all",
    "any_of": [
        {"power": {"op": "<=", "value": {"const": 1}}},
        {"toughness": {"op": "<=", "value": {"const": 1}}},
    ],
}


def board(builder, mine=(DORK, BEAR)):
    return (
        builder(players=2)
        .battlefield(0, [PLAINS] * 4 + list(mine))
        .battlefield(1, ["forest"])
        .hand(0, [PLAINS])
        .build()
    )


def ctx(game, controller: int = 0) -> EffectContext:
    return EffectContext(state=game.state, controller=controller, source_oid=None)


def pool(game, selector) -> set[int]:
    return set(resolve_pool(ctx(game), selector))


class TestItReadsThePrintedSize:
    def test_a_one_one_is_gathered(self, builder):
        game = board(builder)
        assert only_oid(game, DORK, 0) in pool(game, SMALL_BY_BASE)

    def test_a_two_two_is_not(self, builder):
        game = board(builder)
        assert only_oid(game, BEAR, 0) not in pool(game, SMALL_BY_BASE)

    def test_either_half_of_the_or_is_enough(self, builder):
        """"base power **or** toughness 1 or less" is a disjunction, which is
        why the card writes it as `any_of` over the two keys."""
        game = board(builder)
        by_power = pool(game, {**SMALL_BY_BASE, "any_of": [SMALL_BY_BASE["any_of"][0]]})
        by_toughness = pool(game, {**SMALL_BY_BASE, "any_of": [SMALL_BY_BASE["any_of"][1]]})
        dork = only_oid(game, DORK, 0)
        assert dork in by_power and dork in by_toughness


class TestACounterDoesNotChangeTheBase:
    """Layer 7d is later than 7b, and "base" is the card declining to read it.

    This is the claim the live keys get wrong, and the reason the gap was filed
    rather than the card written with `power`.
    """

    def test_the_one_one_is_still_gathered_wearing_counters(self, builder):
        game = board(builder)
        oid = only_oid(game, DORK, 0)
        add_counters(game.state, oid, "+1/+1", 3)
        assert oid in pool(game, SMALL_BY_BASE)

    def test_the_live_keys_would_have_dropped_it(self, builder):
        """The other half of the same board, and the whole difference between
        the printed card and the one that was nearly written."""
        game = board(builder)
        oid = only_oid(game, DORK, 0)
        add_counters(game.state, oid, "+1/+1", 3)
        assert oid not in pool(game, SMALL_BY_LIVE)

    def test_counters_cannot_pull_a_big_creature_in_either(self, builder):
        """The mirror: shrinking is not the only way the two disagree. A -1/-1
        counter makes the Bear a live 1/1, which the live keys would sacrifice
        and the printed card would not."""
        game = board(builder)
        oid = only_oid(game, BEAR, 0)
        add_counters(game.state, oid, "-1/-1", 1)
        assert oid in pool(game, SMALL_BY_LIVE)
        assert oid not in pool(game, SMALL_BY_BASE)


class TestOffTheBattlefieldBothAgree:
    def test_a_card_in_hand_answers_from_its_printed_line(self, builder):
        """There is no object to layer anything onto, so the printed value is
        already the base one. Pinned so the branch does not quietly return 0."""
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS] * 4)
            .battlefield(1, ["forest"])
            .hand(0, [DORK, BEAR])
            .build()
        )
        in_hand = {
            "zone": "hand",
            "controller": "you",
            "types": ["Creature"],
            "count": "all",
            "base_power": {"op": "<=", "value": {"const": 1}},
        }
        gathered = pool(game, in_hand)
        hand = game.state.players[0].hand
        dork = next(o for o in hand if game.state.objects[o].def_id == DORK)
        bear = next(o for o in hand if game.state.objects[o].def_id == BEAR)
        assert dork in gathered and bear not in gathered


class TestTheLoaderKnowsTheKeys:
    def test_the_selector_validates(self):
        validate_selector(SMALL_BY_BASE, "t_probe.effects[0].objects")

    def test_a_word_it_cannot_answer_is_still_refused(self):
        with pytest.raises(DslError):
            validate_selector(
                {"zone": "battlefield", "printed_power": {"op": "<=", "value": {"const": 1}}},
                "t_probe.effects[0].objects",
            )
