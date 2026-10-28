"""Impending: a cheaper cast that arrives as an enchantment and counts down.

    Impending 4—{2}{W}{W} (If you cast this spell for its impending cost, it
    enters with four time counters and isn't a creature until the last is
    removed. At the beginning of your end step, remove a time counter from it.)

702.176a makes the keyword four abilities, and each is its own way to get it
wrong.

**It is an alternative cost** (601.2b), offered beside the printed one. A
discount would be clamped to the generic part and could never reach the {W}{W}
the impending price drops; replacing the printed line would take the 6/6 away
from a player who can pay for it.

**The counters belong to the cost, not to the card.** "If you chose to pay this
permanent's impending cost, it enters with N time counters." The printed cast
enters with none, and so does an Overlord put onto the battlefield by anything
other than its own resolution -- a reanimated permanent is a new object (400.7)
that was never cast.

**"Isn't a creature" holds only while both are true**: the impending cost was
paid and a time counter remains. A normally-cast Overlord handed a time counter
by something else is still a creature; an impending one whose last counter came
off is a creature again. Placed in `characteristics._compute` beside bestow,
reading two pipeline inputs (the cast stamp and the object's own counters), so
it cannot come to depend on another static's output (ADR 0001).

**The tick is a triggered ability**, at the beginning of *your* end step only.
It uses the stack, and it is the rule's: the card prints only the keyword line.

And the rest of the card must still work: "Whenever this permanent enters or
attacks" fires on the impending arrival, because an enchantment entering is
still the permanent entering.

Witness: Overlord of the Mistmoors (`overlord_of_the_mistmoors` in
`data/cards/auto/`), whose test twin is `t_impending_overlord`.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import TIME_COUNTER
from tests.conftest import battlefield_ids, pass_until

OVERLORD = "t_impending_overlord"  # {4}{W}{W} 6/6, Impending 4—{2}{W}{W}
INSECT = "insect_2_1_w_flying"


def board(builder, *, lands=6):
    """Player 0 on Plains with the Overlord in hand; a Forest keeps a play there.

    A position whose active player has nothing to do runs on by itself, so the
    Forest stays in hand to keep each test standing where it was put.
    """
    return (
        builder(players=2)
        .hand(0, [OVERLORD, "forest"])
        .battlefield(0, ["plains"] * lands)
        .hand(1, ["forest"])
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .build()
    )


def casts(game):
    oid = next(
        o for o in game.state.players[0].hand if game.state.objects[o].def_id == OVERLORD
    )
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


def impending_line(game):
    return next(a for a in casts(game) if a.impending)


def printed_line(game):
    return next(a for a in casts(game) if not a.impending)


def resolve_stack(game):
    pass_until(game, lambda g: not g.state.stack)


def cast(game, *, impending):
    """Cast the Overlord one way or the other, resolve it and its enter trigger."""
    game.apply(impending_line(game) if impending else printed_line(game))
    resolve_stack(game)
    return next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == OVERLORD)


def tapped_lands(game):
    return sum(1 for o in game.state.battlefield_objects(0) if o.tapped)


def time_counters(game, oid):
    return game.state.objects[oid].counter(TIME_COUNTER)


def is_creature(game, oid):
    return "Creature" in chars(game.state, oid).types


def to_main_of_turn(game, turn):
    """The first main phase of ``turn``: every end step before it has passed.

    Player 0 takes the odd turns. An end step with nothing to do runs straight
    through, tick and all, so the count is read on the far side of it.
    """
    pass_until(
        game, lambda g: g.state.turn == turn and g.state.step is Step.PRECOMBAT_MAIN
    )


class TestItIsAnAlternativeCost:
    """601.2b: the impending price replaces the printed one, pips included."""

    def test_both_lines_are_offered(self, builder):
        game = board(builder)
        assert sorted(a.impending for a in casts(game)) == [False, True]

    def test_the_impending_line_charges_the_impending_price(self, builder):
        game = board(builder)
        cast(game, impending=True)
        assert tapped_lands(game) == 4

    def test_the_printed_line_charges_the_printed_price(self, builder):
        game = board(builder)
        cast(game, impending=False)
        assert tapped_lands(game) == 6

    def test_four_lands_offer_only_the_impending_line(self, builder):
        game = board(builder, lands=4)
        assert [a.impending for a in casts(game)] == [True]

    def test_the_two_lines_are_different_actions(self, builder):
        # Same source, same targets, same X: the flag is the only difference,
        # so it has to be part of the identity or a lookup answers with
        # whichever came first.
        game = board(builder)
        assert impending_line(game).key() != printed_line(game).key()
        assert "(impending)" in impending_line(game).base_label

    def test_mana_value_is_the_printed_one(self, builder):
        game = board(builder)
        assert game.state.registry.get(OVERLORD).mana_value == 6


class TestTheCountersBelongToTheCost:
    """"If you chose to pay this permanent's impending cost, it enters with N."""

    def test_cast_for_impending_it_enters_with_four_time_counters(self, builder):
        game = board(builder)
        oid = cast(game, impending=True)
        assert time_counters(game, oid) == 4

    def test_cast_normally_it_enters_with_none(self, builder):
        game = board(builder)
        oid = cast(game, impending=False)
        assert time_counters(game, oid) == 0

    def test_a_reanimated_overlord_was_never_cast(self, builder):
        # 400.7: the permanent that comes back is a new object, and nothing
        # paid an impending cost for it. The stamp from its earlier cast must
        # not put the counters back on.
        from commanderblitz.engine.zones import destroy, move_object

        game = board(builder)
        oid = cast(game, impending=True)
        destroy(game.state, oid)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        move_object(game.state, oid, Zone.BATTLEFIELD, to_player=0, cause="effect")
        assert time_counters(game, oid) == 0
        assert is_creature(game, oid)


class TestItIsNotACreatureWhileItCountsDown:
    """The layer-4 type change, and both halves of its condition."""

    def test_cast_for_impending_it_is_an_enchantment_and_no_creature(self, builder):
        game = board(builder)
        oid = cast(game, impending=True)
        c = chars(game.state, oid)
        assert "Creature" not in c.types
        assert "Enchantment" in c.types

    def test_its_creature_types_go_with_the_card_type(self, builder):
        # 205.1b, as under `set_types`: an Enchantment is not an Avatar Horror.
        game = board(builder)
        oid = cast(game, impending=True)
        assert not {"Avatar", "Horror"} & set(chars(game.state, oid).subtypes)

    def test_cast_normally_it_is_a_six_six_creature(self, builder):
        game = board(builder)
        oid = cast(game, impending=False)
        c = chars(game.state, oid)
        assert "Creature" in c.types
        assert {"Avatar", "Horror"} <= set(c.subtypes)
        assert (c.power, c.toughness) == (6, 6)

    def test_a_time_counter_alone_does_not_stop_a_normally_cast_one(self, builder):
        # The cost is half the condition. Counters put on by anything else do
        # nothing to an Overlord whose impending cost was never paid.
        game = board(builder)
        oid = cast(game, impending=False)
        game.state.objects[oid].add_counter(TIME_COUNTER, 2)
        game.state.bump_chars()
        assert is_creature(game, oid)

    def test_the_last_counter_coming_off_makes_it_a_creature(self, builder):
        from commanderblitz.engine.primitives import remove_counters

        game = board(builder)
        oid = cast(game, impending=True)
        remove_counters(game.state, oid, TIME_COUNTER, 3)
        assert not is_creature(game, oid)
        remove_counters(game.state, oid, TIME_COUNTER, 1)
        assert is_creature(game, oid)
        assert {"Avatar", "Horror"} <= set(chars(game.state, oid).subtypes)

    def test_it_cannot_attack_while_it_is_not_a_creature(self, builder):
        game = board(builder)
        oid = cast(game, impending=True)
        to_main_of_turn(game, 3)
        pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
        assert not any(
            a.source == oid for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER
        )


class TestTheEnterTriggerStillFires:
    """"Whenever this permanent enters" -- an enchantment entering is still it."""

    def test_cast_for_impending_it_makes_two_insects(self, builder):
        game = board(builder)
        cast(game, impending=True)
        assert battlefield_ids(game, 0).count(INSECT) == 2

    def test_cast_normally_it_makes_two_insects(self, builder):
        game = board(builder)
        cast(game, impending=False)
        assert battlefield_ids(game, 0).count(INSECT) == 2


class TestTheEndStepTick:
    """"At the beginning of your end step, remove a time counter from it.\""""

    def test_your_end_step_removes_one(self, builder):
        game = board(builder)
        oid = cast(game, impending=True)
        to_main_of_turn(game, 2)
        assert time_counters(game, oid) == 3

    def test_an_opponents_end_step_removes_none(self, builder):
        game = board(builder)
        oid = cast(game, impending=True)
        to_main_of_turn(game, 3)
        assert time_counters(game, oid) == 3

    def test_four_of_your_end_steps_make_it_a_creature(self, builder):
        game = board(builder)
        oid = cast(game, impending=True)
        to_main_of_turn(game, 6)
        assert time_counters(game, oid) == 1
        assert not is_creature(game, oid)
        to_main_of_turn(game, 8)
        assert time_counters(game, oid) == 0
        assert is_creature(game, oid)

    def test_it_is_an_ability_the_permanent_can_lose(self, builder):
        # 702.176a makes the tick one of the permanent's abilities, so a
        # permanent that has lost them stops counting down -- which a
        # turn-based rule like suspend's would not.
        game = board(builder)
        oid = cast(game, impending=True)
        game.state.objects[oid].lost_all_abilities = True
        game.state.bump_chars()
        to_main_of_turn(game, 2)
        assert time_counters(game, oid) == 4

    def test_a_normally_cast_one_is_never_ticked(self, builder):
        # The intervening-if reads the cost: counters from elsewhere on an
        # Overlord nobody paid impending for stay where they are.
        game = board(builder)
        oid = cast(game, impending=False)
        game.state.objects[oid].add_counter(TIME_COUNTER, 2)
        to_main_of_turn(game, 2)
        assert time_counters(game, oid) == 2


class TestTheLoaderRefusesTheSilentFailures:
    """Each would load clean and print a line the card does not perform."""

    def _card(self, **kwargs):
        base = dict(
            id="t_bad",
            name="Bad",
            mana_cost="{4}{W}{W}",
            types=["Enchantment", "Creature"],
            power=6,
            toughness=6,
            impending={"cost": "{2}{W}{W}", "counters": 4},
        )
        base.update(kwargs)
        return CardModel(**base)

    def test_the_well_formed_card_loads(self):
        from commanderblitz.cards.loader import compile_card

        card = compile_card(self._card())
        assert card.impending[1] == 4

    def test_impending_on_a_noncreature_is_refused(self):
        from commanderblitz.cards.loader import compile_card

        model = self._card(types=["Enchantment"], power=None, toughness=None)
        with pytest.raises(DslError, match="only on creature cards"):
            compile_card(model)

    def test_zero_counters_is_refused(self):
        from commanderblitz.cards.loader import compile_card

        model = self._card(impending={"cost": "{2}{W}{W}", "counters": 0})
        with pytest.raises(DslError, match="at least 1"):
            compile_card(model)

    def test_the_printed_price_is_refused(self):
        from commanderblitz.cards.loader import compile_card

        model = self._card(impending={"cost": "{4}{W}{W}", "counters": 4})
        with pytest.raises(DslError, match="the same as the printed cost"):
            compile_card(model)

    def test_an_unknown_key_is_refused(self):
        from commanderblitz.cards.loader import compile_card

        model = self._card(impending={"cost": "{2}{W}{W}", "counters": 4, "zone": "hand"})
        with pytest.raises(DslError, match="unsupported keys"):
            compile_card(model)

    def test_the_condition_without_the_field_is_refused(self):
        from commanderblitz.cards.loader import compile_card

        model = self._card(
            impending=None,
            abilities=[
                {
                    "kind": "triggered",
                    "text": "x",
                    "trigger": {
                        "event": "self_enters",
                        "source": "self",
                        "condition": {"impending": True},
                    },
                    "effects": [{"op": "draw", "amount": {"const": 1}}],
                }
            ],
        )
        with pytest.raises(DslError, match="'impending' condition"):
            compile_card(model)


class TestThePrintedLineIsClaimed:
    """Gate 3: the field claims the line, and only with the printed numbers."""

    LINE = (
        "Impending 4—{2}{W}{W} (If you cast this spell for its impending cost, it "
        "enters with four time counters and isn't a creature until the last is "
        "removed. At the beginning of your end step, remove a time counter from it.)"
    )

    def _card(self, **extra):
        base = {
            "id": "t_impending_residual",
            "name": "Impending Residual",
            "mana_cost": "{4}{W}{W}",
            "oracle_text": self.LINE + "\nFlying",
            "types": ["Enchantment", "Creature"],
            "power": 6,
            "toughness": 6,
            "keywords": ["flying"],
            "impending": {"cost": "{2}{W}{W}", "counters": 4},
        }
        base.update(extra)
        return CardModel.model_validate(base)

    def residual(self, **extra):
        from commanderblitz.cards.authoring.verify import residual_text
        from commanderblitz.cards.loader import compile_card

        card = compile_card(self._card(**extra))
        return residual_text(card, card.oracle_text)

    def test_the_printed_line_is_claimed(self):
        assert self.residual() == ""

    def test_a_card_without_the_field_leaves_it_residual(self):
        assert "Impending 4" in self.residual(impending=None)

    def test_a_cheaper_declared_cost_cannot_claim_the_printed_one(self):
        assert "Impending 4" in self.residual(impending={"cost": "{1}{W}", "counters": 4})

    def test_fewer_declared_counters_cannot_claim_the_printed_count(self):
        # Without the strict claimant the implied enters-with-counters
        # replacement would wave the line through on its reminder text.
        assert "Impending 4" in self.residual(impending={"cost": "{2}{W}{W}", "counters": 3})
