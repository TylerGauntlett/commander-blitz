""""Crackle with Power deals 5 damage to each of **X** targets."

The one computed target count a *spell* may carry, and the reason it is the only
one is an ordering rule. `loader.targets._compile_targets` refuses a value
expression on a card's own `targets` because "a spell's are declared while it is
being cast (601.2c), before X is chosen and before any additional cost is paid,
so the expression would read 0". That is exactly right for
`{"additional_paid": true}` — kicker is paid at 601.2h, long after — and exactly
wrong for X, because **601.2b announces X and 601.2c declares targets, in that
order**.

The engine already put them in that order. `Game._cast` asks `_ask_x` first, then
`_ask_modes`, then `_ask_mode_targets` — the last of which is a target
declaration made at cast time, after a cast-time choice, which the method's own
docstring calls "exactly where 601.2 puts it". `_ask_x_targets` is its sibling
and does the same thing keyed on X.

Legality is untouched and stays a **gate**, which it already was for the cost:
the comment beside the `x_count` check says "X is a gate here, not a value…
`game._cast` then asks the player which one". It sizes the spec at zero, offers
one line, and the refs are chosen where X is a number.

`filter_legal` needed nothing at all. `variable_size` already makes the last spec
swallow whatever refs remain, and its comment already argues that re-evaluating a
computed count on resolution would be *worse* than using the stored length —
"the number is fixed when the targets are declared (601.2c)". That is the
semantics an X-sized target wants, written before one existed.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import pass_until

CRACKLE = "t_crackle"  # {X}{R}{R}{R}, 5 damage to each of X targets
BEAR = "t_bear"  # 2/2 -- dies to 5
WALL = "t_big_wall"  # 0/9 -- survives, so damage is readable as marks


def position(builder, *, lands: int = 8):
    return (
        builder(players=2)
        .battlefield(0, ["mountain"] * lands)
        .battlefield(1, [BEAR, WALL, "plains"])
        .library(0, ["forest"] * 20)
        .hand(0, [CRACKLE])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def cast_with_x(game, x: int) -> None:
    """Cast Crackle, answer CHOOSE_X with ``x``, then take the targets offered."""
    game._advance()
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == CRACKLE
    )
    game.apply(action)

    pending = game.pending()
    assert pending is not None and pending.kind is DecisionKind.CHOOSE_X, pending
    choose = next(
        a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == x
    )
    game.apply(choose)

    # `pass_until` answers a CHOOSE_OBJECTS prompt by taking what it is asked
    # for, so the targets are declared without this test naming them -- what is
    # under test is how *many* it asks for.
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


def target_prompt(game):
    pending = game.pending()
    return pending if pending is not None and pending.kind is DecisionKind.CHOOSE_OBJECTS else None


class TestTheLineIsOffered:
    def test_crackle_is_castable(self, builder):
        """Legality sizes the spec at zero and still offers the line."""
        game = position(builder)
        game._advance()

        assert any(
            a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == CRACKLE
            for a in game.legal_actions()
        )


class TestTheNumberOfTargetsIsX:
    def test_x_of_one_asks_for_one(self, builder):
        game = position(builder)
        game._advance()
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == CRACKLE
        )
        game.apply(action)
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == 1))

        prompt = target_prompt(game)
        assert prompt is not None, "the targets are asked for after X"
        assert prompt.min_count == 1 and prompt.max_count == 1

    def test_x_of_two_asks_for_two(self, builder):
        game = position(builder)
        game._advance()
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == CRACKLE
        )
        game.apply(action)
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == 2))

        prompt = target_prompt(game)
        assert prompt is not None
        assert prompt.min_count == 2 and prompt.max_count == 2


class TestTheDamageLands:
    def test_one_target_takes_five(self, builder):
        game = position(builder)
        cast_with_x(game, 1)

        hit = [
            o
            for o in game.state.objects.values()
            if o.def_id in (BEAR, WALL) and (o.damage or o.zone is Zone.GRAVEYARD)
        ]
        assert len(hit) == 1, "exactly one thing was dealt damage"

    def test_two_targets_both_take_five(self, builder):
        """The claim the whole capability is for: X is the *number* of targets."""
        game = position(builder)
        cast_with_x(game, 2)

        bear = next(o for o in game.state.objects.values() if o.def_id == BEAR)
        wall = next(o for o in game.state.objects.values() if o.def_id == WALL)

        assert bear.zone is Zone.GRAVEYARD, "a 2/2 takes 5"
        assert wall.damage == 5, "and the 0/9 is marked"


class TestXOfZero:
    def test_it_is_castable_and_asks_nothing(self, builder):
        """"each of zero targets" is a spell that targets nothing.

        Legal, and not a question -- so there is no prompt to answer.
        """
        game = position(builder)
        cast_with_x(game, 0)

        bear = next(o for o in game.state.objects.values() if o.def_id == BEAR)
        assert bear.zone is Zone.BATTLEFIELD and bear.damage == 0


class TestTheLoaderStillRefusesTheOthers:
    def spell(self, count):
        return {
            "id": "t_probe_xt",
            "name": "Probe X Targets",
            "mana_cost": "{X}{R}",
            "types": ["Sorcery"],
            "targets": [{"id": "t1", "kind": "any", "count": count}],
            "spell_effects": [{"op": "damage", "target": "t1", "amount": {"const": 1}}],
        }

    def test_additional_paid_is_still_refused(self):
        """Kicker is paid at 601.2h -- after targets -- so it would read zero."""
        with pytest.raises(DslError, match="computed 'count' only works on an"):
            compile_card(CardModel.model_validate(self.spell({"additional_paid": True})))

    def test_x_needs_an_x_in_the_cost(self):
        """Otherwise the spec sizes to zero for ever: a spell that never targets."""
        card = self.spell({"x": True})
        card["mana_cost"] = "{R}"
        with pytest.raises(DslError, match=r"needs an \{X\} in the card's mana cost"):
            compile_card(CardModel.model_validate(card))

    def test_x_is_accepted_with_one(self):
        compile_card(CardModel.model_validate(self.spell({"x": True})))
