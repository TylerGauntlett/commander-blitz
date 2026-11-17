""""This creature can block only creatures with flying": the blocker's own filter.

Rule 509.1b makes a block declaration illegal if any restriction is disobeyed,
and a restriction can sit on either creature in the pair. `block_restriction`
is the attacker's half -- "can't be blocked by Humans" filters the would-be
**blockers**. The witness here is **Brazen Borrower**, whose line is the other
half: a restriction on the **blocker**, filtering which **attackers** it may
block. Without `can_block_only` the card's only honest spellings are no line at
all (a Borrower that blocks a ground creature, strictly better than printed) or
`cant_block` (one that blocks nothing, strictly worse).

The attacker is read as it now is. A restriction modifies the rules of combat
rather than a characteristic, so it is no layer (613) and sees the layer
system's output: a creature granted flying this turn is a creature with flying.

Rule 509.1c is the other half of the argument. A block requirement -- provoke,
"blocks this turn if able" -- never makes an illegal block legal, so a Borrower
lured toward a ground creature owes nothing, and "Done blocking" stays on offer.
Every requirement asks `combat.can_block`, which is where this static is read,
so the excuse is not a second code path that could drift.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.combat import can_block
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import block_only_refused
from commanderblitz.engine.structs import TargetRef
from tests.conftest import attack_with, find_action, only_oid, pass_until, static_probe

BORROWER = "t_cbo_borrower"  # 3/1 flash, flying; can block only creatures with flying
FLIER = "t_flier"  # 2/2 flying
BEAR = "t_bear"  # 2/2
GRANTER = "t_flying_granter"  # "Creatures you control have flying."


def position(builder, attackers=(FLIER, BEAR), *, mine=()):
    """``(game, borrower)`` at player 1's block declaration, every attacker in."""
    game = (
        builder(players=2)
        .battlefield(0, list(attackers) + list(mine))
        .battlefield(1, [BORROWER])
        .build()
    )
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
    for card_id in attackers:
        attack_with(game, only_oid(game, card_id, 0))
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS)
    return game, only_oid(game, BORROWER, 1)


def run(game, spec: dict, controller: int = 0) -> None:
    ctx = EffectContext(state=game.state, controller=controller, source_oid=None)
    gen = execute(ctx, [spec])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def offered(game, blocker: int) -> list[int]:
    """The attackers the legal actions offer this blocker."""
    return sorted(
        t.id
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_BLOCKER and a.source == blocker
        for t in a.targets
    )


def can_finish(game) -> bool:
    return any(a.kind is ActionKind.FINISH_DECLARATION for a in game.legal_actions())


class TestTheFilterOnTheAttacker:
    def test_a_flier_can_be_blocked(self, builder):
        game, borrower = position(builder)
        assert can_block(game.state, borrower, only_oid(game, FLIER, 0), 1)

    def test_a_ground_creature_cannot(self, builder):
        game, borrower = position(builder)
        bear = only_oid(game, BEAR, 0)
        assert block_only_refused(game.state, borrower, bear)
        assert not can_block(game.state, borrower, bear, 1)

    def test_the_offered_blocks_are_exactly_the_fliers(self, builder):
        game, borrower = position(builder)
        assert offered(game, borrower) == [only_oid(game, FLIER, 0)]

    def test_the_static_binds_only_its_own_creature(self, builder):
        """`affects` is `self_only`: a second creature beside it blocks freely."""
        game = (
            builder(players=2)
            .battlefield(0, [BEAR])
            .battlefield(1, [BORROWER, BEAR])
            .build()
        )
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
        )
        attacker = only_oid(game, BEAR, 0)
        attack_with(game, attacker)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
        )
        assert offered(game, only_oid(game, BEAR, 1)) == [attacker]
        assert offered(game, only_oid(game, BORROWER, 1)) == []


class TestItReadsTheAttackerAsItNowIs:
    def test_a_creature_granted_flying_by_a_static_counts(self, builder):
        game, borrower = position(builder, attackers=(BEAR,), mine=(GRANTER,))
        assert offered(game, borrower) == [only_oid(game, BEAR, 0)]

    def test_a_creature_granted_flying_this_turn_counts(self, builder):
        game, borrower = position(builder)
        bear = only_oid(game, BEAR, 0)
        run(game, {"op": "grant_keyword", "keywords": ["flying"], "objects": {"oid": bear}})
        assert can_block(game.state, borrower, bear, 1)
        assert offered(game, borrower) == sorted([only_oid(game, FLIER, 0), bear])

    def test_a_flier_that_loses_flying_cannot_be_blocked(self, builder):
        game, borrower = position(builder)
        flier = only_oid(game, FLIER, 0)
        run(game, {"op": "lose_keyword", "keywords": ["flying"], "objects": {"oid": flier}})
        assert not can_block(game.state, borrower, flier, 1)


class TestLosingTheStatic:
    def test_without_its_abilities_it_blocks_anything(self, builder):
        """The restriction is the creature's own ability, so stripping the
        abilities strips the restriction -- unlike a prohibition from outside."""
        game, borrower = position(builder)
        run(game, {"op": "lose_all_abilities", "objects": {"oid": borrower}}, controller=0)
        assert offered(game, borrower) == sorted(
            [only_oid(game, FLIER, 0), only_oid(game, BEAR, 0)]
        )


class TestRequirementsNeverForceAnIllegalBlock:
    def test_a_named_requirement_toward_a_ground_creature_is_excused(self, builder):
        """509.1c: provoke at a Borrower names an attacker it cannot block."""
        game, borrower = position(builder)
        game.state.objects[borrower].must_block = only_oid(game, BEAR, 0)
        assert can_finish(game)
        assert offered(game, borrower) == [only_oid(game, FLIER, 0)], (
            "an excused requirement does not narrow the creature to its attacker"
        )

    def test_a_named_requirement_toward_a_flier_binds(self, builder):
        game, borrower = position(builder)
        flier = only_oid(game, FLIER, 0)
        game.state.objects[borrower].must_block = flier
        assert not can_finish(game)
        game.apply(
            find_action(
                game, ActionKind.ADD_BLOCKER, source=borrower, targets=(TargetRef.obj(flier),)
            )
        )
        assert can_finish(game)

    def test_blocks_if_able_with_only_ground_attackers_is_excused(self, builder):
        game, borrower = position(builder, attackers=(BEAR,))
        game.state.objects[borrower].must_block_any_turn = game.state.turn
        assert offered(game, borrower) == []
        assert can_finish(game)


def probe(static: dict) -> CardModel:
    card = static_probe(static)
    card.update(types=["Creature"], power=1, toughness=1)
    return CardModel.model_validate(card)


class TestTheLoaderKnowsIt:
    def test_the_borrower_compiles(self, registry):
        card = registry.get(BORROWER)
        (static,) = [a for a in card.abilities if a.is_static]
        assert static.static["effect"] == "can_block_only"
        assert static.static["attackers"] == {"keywords": ["flying"]}

    @pytest.mark.parametrize("attackers", [None, {}], ids=["missing", "empty"])
    def test_a_static_without_a_filter_is_refused(self, attackers):
        """"Can block only creatures" restricts nothing."""
        spec = {"effect": "can_block_only", "affects": {"self_only": True}}
        if attackers is not None:
            spec["attackers"] = attackers
        with pytest.raises(DslError, match="non-empty 'attackers'"):
            compile_card(probe(spec))

    def test_an_unknown_filter_key_is_refused(self):
        with pytest.raises(DslError, match="unsupported keys"):
            compile_card(
                probe(
                    {
                        "effect": "can_block_only",
                        "affects": {"self_only": True},
                        "attackers": {"flies": True},
                    }
                )
            )

    @pytest.mark.parametrize("key", ["self_only", "exclude_self"])
    def test_a_self_reference_in_the_filter_is_refused(self, key):
        """The source is the blocker, never the attacker it blocks."""
        with pytest.raises(DslError, match="never the attacker"):
            compile_card(
                probe(
                    {
                        "effect": "can_block_only",
                        "affects": {"self_only": True},
                        "attackers": {key: True},
                    }
                )
            )

    def test_attackers_on_another_effect_is_refused(self):
        with pytest.raises(DslError, match="only means anything on a can_block_only"):
            compile_card(
                probe(
                    {
                        "effect": "cant_block",
                        "affects": {"self_only": True},
                        "attackers": {"keywords": ["flying"]},
                    }
                )
            )
