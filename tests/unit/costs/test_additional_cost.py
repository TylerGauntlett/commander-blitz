"""Casualty and replicate — an additional cost that is not mana.

    Casualty 2 — "As an additional cost to cast this spell, you may sacrifice a
    creature with power 2 or greater. When you do, copy this spell."
    Replicate {1} — "…you may pay an additional {1} any number of times. When
    you cast this spell, copy it for each time you paid."

`kicker` is the only additional cost a hand-cast spell could carry, and it is
wrong twice over for both of these: it is **mana-only** — `_cast_variant`
computes `mana_cost.plus(kicker)`, a `ManaCost`, which cannot sacrifice
anything — and it is paid **once**.

So `additional_cost` is a full `Cost`, and legality offers **one cast line per
number of times paid**, which is convoke's shape rather than kicker's: the count
changes the price, and it is the player's to choose.

Three things the modifiers decide, and each is a different printed card:

| | |
|---|---|
| neither | Deadly Dispute — "sacrifice an artifact or creature", mandatory |
| `additional_optional` | casualty — "you **may** sacrifice" |
| both | replicate — "any number of times", which includes none |

Moving the payment into `spell_effects` is the approximation the DSL notes
forbid, and it fails in a way nothing on screen would show: the spell could be
cast with no creature to sacrifice and would still draw the card.

**The copy needs no new machinery.** "When you cast this spell" is a
`spell_cast` trigger with `active_zones: ["stack"]`, which already ships — so
the trigger goes on the stack *above* the spell and its copy resolves first,
which is what rule 706.10 wants and what a `copy_spell` inside `spell_effects`
would get backwards.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.errors import DslError
from tests.conftest import pass_until

SWAMP = "swamp"
MOUNTAIN = "mountain"
CASUALTY = "t_casualty"     # {1}{B} sorcery, casualty 2, draws a card
REPLICATE = "t_replicate"   # {R} instant, replicate {1}, 1 damage
MANDATORY = "t_mandatory_sac"  # {B} instant, sacrifice a creature, draw two
BEAR = "t_bear"             # 2/2 -- power 2, so legal casualty fodder
DORK = "t_dork"             # 1/1 -- power 1, so not


def casualty_board(builder, *creatures: str):
    return (
        builder(players=2)
        .battlefield(0, [SWAMP] * 3)
        .battlefield(0, list(creatures))
        .hand(0, [CASUALTY])
        .library(0, [SWAMP] * 20)
        .library(1, [SWAMP] * 20)
        .build()
    )


def replicate_board(builder, lands: int):
    return (
        builder(players=2)
        .battlefield(0, [MOUNTAIN] * lands)
        .hand(0, [REPLICATE])
        .library(0, [MOUNTAIN] * 20)
        .library(1, [MOUNTAIN] * 20)
        .build()
    )


def lines(game, card_id: str):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card_id
    ]


class TestCasualty:
    def test_both_lines_are_offered_with_legal_fodder(self, builder):
        game = casualty_board(builder, BEAR)
        counts = sorted({a.additional_times for a in lines(game, CASUALTY)})
        assert counts == [0, 1], "pay it, or do not"

    def test_only_the_free_line_is_offered_with_no_fodder(self, builder):
        game = casualty_board(builder)
        counts = sorted({a.additional_times for a in lines(game, CASUALTY)})
        assert counts == [0]

    def test_a_creature_too_small_is_not_fodder(self, builder):
        """The selector's own `power` clause -- casualty 2 needs power 2."""
        game = casualty_board(builder, DORK)
        counts = sorted({a.additional_times for a in lines(game, CASUALTY)})
        assert counts == [0]

    def test_paying_it_sacrifices_the_creature(self, builder):
        game = casualty_board(builder, BEAR)
        bear = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEAR)
        game.apply(next(a for a in lines(game, CASUALTY) if a.additional_times == 1))
        pass_until(game, lambda g: not g.state.stack)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_paying_it_copies_the_spell(self, builder):
        game = casualty_board(builder, BEAR)
        hand = len(game.state.players[0].hand)
        game.apply(next(a for a in lines(game, CASUALTY) if a.additional_times == 1))
        pass_until(game, lambda g: not g.state.stack)

        # Cast one, drew two: the copy and the original.
        assert len(game.state.players[0].hand) == hand - 1 + 2

    def test_declining_copies_nothing(self, builder):
        game = casualty_board(builder, BEAR)
        hand = len(game.state.players[0].hand)
        bear = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEAR)
        game.apply(next(a for a in lines(game, CASUALTY) if a.additional_times == 0))
        pass_until(game, lambda g: not g.state.stack)

        assert len(game.state.players[0].hand) == hand - 1 + 1
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD


class TestReplicate:
    def test_one_line_per_number_of_times_paid(self, builder):
        """Convoke's shape: the count changes the price and is the player's."""
        game = replicate_board(builder, lands=3)
        counts = sorted({a.additional_times for a in lines(game, REPLICATE)})
        assert counts == [0, 1, 2], "{R}, {R}{1}, {R}{1}{1}"

    def test_the_mana_is_really_charged(self, builder):
        game = replicate_board(builder, lands=1)
        counts = sorted({a.additional_times for a in lines(game, REPLICATE)})
        assert counts == [0], "one Mountain pays {R} and nothing more"

    def test_the_number_of_copies_is_the_number_paid(self, builder):
        game = replicate_board(builder, lands=3)
        life = game.state.players[1].life
        action = next(
            a
            for a in lines(game, REPLICATE)
            if a.additional_times == 2
            and any(t.kind == "player" and t.id == 1 for t in a.targets)
        )
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack)

        assert game.state.players[1].life == life - 3, "the original and two copies"

    def test_paying_none_copies_nothing(self, builder):
        game = replicate_board(builder, lands=3)
        life = game.state.players[1].life
        action = next(
            a
            for a in lines(game, REPLICATE)
            if a.additional_times == 0
            and any(t.kind == "player" and t.id == 1 for t in a.targets)
        )
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack)

        assert game.state.players[1].life == life - 1


def mandatory_board(builder, *creatures: str):
    return (
        builder(players=2)
        .battlefield(0, [SWAMP] * 3)
        .battlefield(0, list(creatures))
        .hand(0, [MANDATORY])
        .library(0, [SWAMP] * 20)
        .library(1, [SWAMP] * 20)
        .build()
    )


class TestTheFreeLineIsReallyWithdrawn:
    """The half of "mandatory" that the flag alone does not deliver.

    Legality builds the plain cast line first and only later learns about the
    additional cost, so withdrawing it is an act rather than an absence. It used
    to be withdrawn *only when the cost was unpayable*, which is the same thing
    as never charging it: a player holding a creature was offered both lines and
    every automatic driver -- the verifier's `find_play`, the arena, the RL
    agent -- took the first. Village Rites was a one-mana draw-two that
    sacrificed nothing, and no test said otherwise.
    """

    def test_only_the_paying_line_is_offered(self, builder):
        game = mandatory_board(builder, BEAR)
        counts = sorted({a.additional_times for a in lines(game, MANDATORY)})
        assert counts == [1], "there is no line that does not pay"

    def test_casting_it_sacrifices_the_creature(self, builder):
        game = mandatory_board(builder, BEAR)
        bear = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEAR)
        game.apply(lines(game, MANDATORY)[0])
        pass_until(game, lambda g: not g.state.stack)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_it_is_not_castable_with_nothing_to_sacrifice(self, builder):
        """An unpayable mandatory cost falls out of the same rule."""
        game = mandatory_board(builder)
        assert lines(game, MANDATORY) == []

    def test_an_optional_cost_still_offers_both(self, builder):
        """The fix must not withdraw casualty's free line, which is printed."""
        game = casualty_board(builder, BEAR)
        counts = sorted({a.additional_times for a in lines(game, CASUALTY)})
        assert counts == [0, 1]


class TestAMandatoryCost:
    """Deadly Dispute's shape: neither modifier, so the free line is withdrawn."""

    def _card(self, **extra) -> CardModel:
        base = {
            "id": "t_mandatory_probe",
            "name": "Mandatory Probe",
            "mana_cost": "{1}{B}",
            "types": ["Sorcery"],
            "additional_cost": {"sacrifice": {"controller": "you", "types": ["Creature"]}},
            "spell_effects": [{"op": "draw", "player": "you"}],
        }
        base.update(extra)
        return CardModel.model_validate(base)

    def test_it_loads_with_nothing_reading_it(self):
        """Unlike kicker: "sacrifice an artifact" is the whole cost, read by nobody."""
        compile_card(self._card())

    def test_the_modifiers_need_a_cost(self):
        with pytest.raises(DslError, match="need an 'additional_cost'"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_probe2",
                        "name": "Probe 2",
                        "mana_cost": "{1}",
                        "types": ["Sorcery"],
                        "additional_optional": True,
                        "spell_effects": [{"op": "draw", "player": "you"}],
                    }
                )
            )

    def test_repeatable_needs_optional(self):
        """"Any number of times" includes none."""
        with pytest.raises(DslError, match="includes none"):
            compile_card(self._card(additional_repeatable=True))

    def test_reading_the_count_without_a_cost_is_refused(self):
        with pytest.raises(DslError, match="reads 'additional_paid'"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_probe3",
                        "name": "Probe 3",
                        "mana_cost": "{1}",
                        "types": ["Sorcery"],
                        "spell_effects": [
                            {
                                "op": "if",
                                "condition": {
                                    "cmp": ">=",
                                    "left": {"additional_paid": True},
                                    "right": {"const": 1},
                                },
                                "then": [{"op": "draw", "player": "you"}],
                            }
                        ],
                    }
                )
            )

PLUMB = "t_plumb"  # {1}{B} instant, repeatable *sacrifice*, copies per payment


def settle(game):
    """Pay the sacrifice, then wait for the copy trigger.

    Two things a plain `pass_until` gets wrong here. Paying a *sacrifice* cost
    suspends the cast on a CHOOSE_OBJECTS, and the passive answer is not to
    choose -- so the cast never completes and the card stays in hand. And the
    "when you do" trigger queues as the spell is cast but reaches the stack only
    at the next priority, so waiting on an empty stack alone returns before
    anything has copied.
    """
    for _ in range(60):
        if not game.state.pending_triggers and not game.state.stack and game.pending() is None:
            return
        decision = game.pending()
        if decision is None:
            return
        actions = game.legal_actions()
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            choose = [a for a in actions if a.kind is ActionKind.CHOOSE]
            if choose:
                game.apply(choose[0])
                continue
            finish = [a for a in actions if a.kind is ActionKind.FINISH_DECLARATION]
            if finish:
                game.apply(finish[0])
                continue
        if not game.state.pending_triggers and not game.state.stack:
            return
        passes = [a for a in actions if a.kind is ActionKind.PASS]
        if not passes:
            return
        game.apply(passes[0])


def plumb_board(builder, creatures: int):
    return (
        builder(players=2)
        .battlefield(0, [SWAMP] * 6)
        .battlefield(0, [BEAR] * creatures)
        .hand(0, [PLUMB])
        .library(0, [SWAMP] * 20)
        .library(1, [SWAMP] * 20)
        .build()
    )


class TestARepeatableCostThatIsNotMana:
    """Plumb the Forbidden -- the case replicate's ceiling never covered.

    `_additional_ceiling` returned `MAX_ADDITIONAL_TIMES` for anything
    repeatable and left per-line affordability to the *price*. That works only
    because replicate's cost is mana: each line is priced `mana.scaled(times)`
    and the solver drops the ones that cannot be paid.

    A repeatable **sacrifice** has an empty `mana`, so every line was priced at
    the printed cost and all six were offered whatever the board held. And `pay`
    does not fail closed -- `ask_objects` returns `[]` for an empty pool, the
    sacrifice branch consumes it happily, and `cast_additional` records the
    count *requested*. One creature bought seven copies for {1}{B}.

    Gate 5 could not see it: the harness takes the first cast line, which is the
    one that pays nothing.
    """

    def test_the_lines_stop_at_the_creatures_available(self, builder):
        game = plumb_board(builder, creatures=2)
        counts = sorted({a.additional_times for a in lines(game, PLUMB)})
        assert counts == [0, 1, 2], "nothing beyond what the board can pay"

    def test_one_creature_offers_one_payment(self, builder):
        game = plumb_board(builder, creatures=1)
        counts = sorted({a.additional_times for a in lines(game, PLUMB)})
        assert counts == [0, 1]

    def test_no_creatures_offers_only_the_free_line(self, builder):
        """Optional, so the spell is still castable -- for nothing."""
        game = plumb_board(builder, creatures=0)
        counts = sorted({a.additional_times for a in lines(game, PLUMB)})
        assert counts == [0]

    def test_paying_twice_really_eats_two(self, builder):
        game = plumb_board(builder, creatures=2)
        bears = [
            o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEAR
        ]
        game.apply(next(a for a in lines(game, PLUMB) if a.additional_times == 2))
        settle(game)

        assert all(
            game.state.objects[b].zone is Zone.GRAVEYARD for b in bears
        )

    def test_the_copies_match_what_was_paid(self, builder):
        """Two payments, two copies, so three draws and three life."""
        game = plumb_board(builder, creatures=2)
        hand = len(game.state.players[0].hand)
        life = game.state.players[0].life

        game.apply(next(a for a in lines(game, PLUMB) if a.additional_times == 2))
        settle(game)

        assert len(game.state.players[0].hand) == hand - 1 + 3
        assert game.state.players[0].life == life - 3

    def test_the_free_line_copies_nothing(self, builder):
        game = plumb_board(builder, creatures=2)
        hand = len(game.state.players[0].hand)
        life = game.state.players[0].life

        game.apply(next(a for a in lines(game, PLUMB) if a.additional_times == 0))
        settle(game)

        assert len(game.state.players[0].hand) == hand - 1 + 1
        assert game.state.players[0].life == life - 1

