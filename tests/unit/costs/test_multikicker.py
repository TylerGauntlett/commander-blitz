"""Multikicker — the kicker you may pay *any number of times*.

    702.32b — "Multikicker is a variant of the kicker ability. 'Multikicker
    [cost]' means 'You may pay [cost] any number of times as you cast this
    spell.'"

`kicker` could not say it and never will: its cast variant is
`mana_cost.plus(kicker)` selected by a **bool** on the action, so it is paid
once, and `{"kicked": true}` can only answer yes or no — never how many. A card
whose whole point is counting the kicks (Everflowing Chalice's charge counters,
Comet Storm's second target, Marshal's Anthem's X reanimations) gets nothing
from it.

The payment machinery it does need already shipped, unnamed: `additional_cost`
plus `additional_optional` plus `additional_repeatable` is replicate's slot,
legality offers one cast line per number of times paid, `Action.additional_times`
carries the count and `{"additional_paid": true}` reads it back off
`obj.cast_additional`. So `multikicker` is a **desugaring**, not a mechanism, and
what it buys is the *word*: a printed line reading "Multikicker {1}{W}" now has a
claimant, where before a card spelling it through the replicate slot loaded fine
and then failed the residual gate on its own first line.

There is no shipped witness card yet. Marshal's Anthem is the card that asked for
this and it is still blocked on `variable_target_count` ("return up to X target
creature cards", where a target spec's `count` is `int | "any"` and cannot be
bound to a value), which is a separate capability. So this file is the *only*
coverage this change has, and it is written to be: it exercises paying zero, once
and several times, it proves the count survives the zone change onto the
battlefield, and it holds the residual gate to both halves of its job — accepting
a multikicker line, and still rejecting a line nothing implements.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.authoring.verify import residual_text
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError

PLAINS = "plains"
ANTHEM = "t_multikicker"  # {1}{W} enchantment, multikicker {1}{W}, draws per kick

#: The printed first line, reminder text and all.
MULTIKICKER_LINE = (
    "Multikicker {1}{W} (You may pay an additional {1}{W} any number of times "
    "as you cast this spell.)"
)
ENTERS_LINE = "When this enchantment enters, draw a card for each time it was kicked."


def board(builder, lands: int):
    return (
        builder(players=2)
        .battlefield(0, [PLAINS] * lands)
        .hand(0, [ANTHEM])
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .build()
    )


def lines(game, card_id: str = ANTHEM):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card_id
    ]


def settle(game, limit: int = 60):
    """Pass until the spell, and the enters trigger it queues, have both resolved.

    Waiting on an empty stack alone returns too early: the trigger is queued as
    the permanent enters and only reaches the stack at the next priority.
    """
    for _ in range(limit):
        if not game.state.pending_triggers and not game.state.stack:
            return
        if game.pending() is None:
            return
        passes = [a for a in game.legal_actions() if a.kind is ActionKind.PASS]
        if not passes:
            return
        game.apply(passes[0])
    raise AssertionError("the stack never emptied")


def cast_paying(game, times: int):
    hand = len(game.state.players[0].hand)
    game.apply(next(a for a in lines(game) if a.additional_times == times))
    settle(game)
    return hand


def the_anthem(game):
    return next(o for o in game.state.battlefield_objects(0) if o.def_id == ANTHEM)


class TestAnyNumberOfTimesIncludingNone:
    """The count is the player's, so every payable number is its own cast line."""

    def test_zero_is_offered(self, builder):
        """"Any number of times" includes none — the printed cast is still there."""
        game = board(builder, lands=2)
        assert sorted({a.additional_times for a in lines(game)}) == [0]

    def test_once_is_offered_when_the_mana_is_there(self, builder):
        game = board(builder, lands=4)
        assert sorted({a.additional_times for a in lines(game)}) == [0, 1]

    def test_several_are_offered(self, builder):
        """{1}{W} to cast plus {1}{W} a kick: eight Plains buys three."""
        game = board(builder, lands=8)
        assert sorted({a.additional_times for a in lines(game)}) == [0, 1, 2, 3]

    def test_the_boundary_is_the_mana(self, builder):
        """Seven Plains pays for three kicks with one to spare, not four."""
        game = board(builder, lands=7)
        assert sorted({a.additional_times for a in lines(game)}) == [0, 1, 2]

    def test_a_kick_is_really_charged(self, builder):
        """Three Plains casts it and cannot afford the fourth mana a kick costs."""
        game = board(builder, lands=3)
        assert sorted({a.additional_times for a in lines(game)}) == [0]


class TestTheCountSurvivesEnteringTheBattlefield:
    """`additional_paid` off a permanent, which is the whole reason for the word.

    `cast_additional` is written in `game._cast` onto the object being cast, and
    an oid survives the zone change onto the battlefield — so a `self_enters`
    trigger, which is sourced to the permanent, reads the number the *spell* was
    kicked. Without that this mechanic would only ever work on instants and
    sorceries, and every printed multikicker permanent counts its kicks after it
    has landed.
    """

    def test_paying_none_reads_zero(self, builder):
        game = board(builder, lands=2)
        hand = cast_paying(game, 0)

        assert the_anthem(game).cast_additional == 0
        assert len(game.state.players[0].hand) == hand - 1, "cast it, drew nothing"

    def test_paying_once_reads_one(self, builder):
        game = board(builder, lands=4)
        hand = cast_paying(game, 1)

        assert the_anthem(game).cast_additional == 1
        assert len(game.state.players[0].hand) == hand - 1 + 1

    def test_paying_three_times_reads_three(self, builder):
        game = board(builder, lands=8)
        hand = cast_paying(game, 3)

        assert the_anthem(game).cast_additional == 3
        assert len(game.state.players[0].hand) == hand - 1 + 3

    def test_it_is_on_the_battlefield_either_way(self, builder):
        """The kicks buy the trigger's size, not whether the card resolves."""
        game = board(builder, lands=8)
        cast_paying(game, 2)

        assert the_anthem(game).zone is Zone.BATTLEFIELD


class TestItDesugarsToTheRepeatableSlot:
    """No new machinery: the word compiles to the fields replicate already used."""

    def test_the_cost_becomes_a_repeatable_optional_additional_cost(self, registry):
        card = registry.get(ANTHEM)
        assert card.multikicker is not None
        assert card.additional_cost is not None
        assert card.additional_optional and card.additional_repeatable

    def test_the_mana_charged_is_the_mana_printed(self, registry):
        card = registry.get(ANTHEM)
        assert card.additional_cost.mana.mana_value() == 2
        assert card.additional_cost.mana.colored == card.multikicker.colored

    def test_it_is_not_the_one_shot_kicker(self, registry):
        """A card with multikicker has no `kicker`, so no kicked/unkicked pair."""
        assert registry.get(ANTHEM).kicker is None


def _model(**extra) -> CardModel:
    base = {
        "id": "t_mk_probe",
        "name": "Multikicker Probe",
        "mana_cost": "{1}{W}",
        "types": ["Sorcery"],
        "multikicker": "{1}{W}",
        "spell_effects": [
            {"op": "draw", "player": "you", "amount": {"additional_paid": True}}
        ],
    }
    base.update(extra)
    return CardModel.model_validate(base)


class TestTheLoaderRefusesHalfOfIt:
    """Half a multikicker is half a kicker: it loads clean and means nothing."""

    def test_the_whole_thing_loads(self):
        card = compile_card(_model())
        assert card.multikicker is not None

    def test_a_cost_nothing_counts_is_refused(self):
        """A spell that charges more and does the same thing."""
        with pytest.raises(DslError, match="no effect reads via 'additional_paid'"):
            compile_card(
                _model(spell_effects=[{"op": "draw", "player": "you"}])
            )

    def test_both_spellings_of_the_slot_are_refused(self):
        """One would win and the other would never be charged."""
        with pytest.raises(DslError, match="not both"):
            compile_card(_model(additional_cost={"mana": "{1}"}))

    def test_setting_the_modifiers_alongside_it_is_refused(self):
        with pytest.raises(DslError, match="already implies"):
            compile_card(_model(additional_optional=True))

    def test_a_free_multikicker_is_refused(self):
        """Repeatable and free is six kicks for nothing, which is no printing."""
        with pytest.raises(DslError, match="costs nothing"):
            compile_card(_model(multikicker="{0}"))

    def test_x_is_refused(self):
        with pytest.raises(DslError, match="multikicker cost with X"):
            compile_card(_model(multikicker="{X}"))


class TestTheResidualGate:
    """The gate learns a new *claimant*, and gives nothing else away.

    The residual gate asks whether every printed line is accounted for by
    something the card really has. "Multikicker {1}{W}" is a card-level **cost**
    paid inside `game._cast`, so — exactly like `kicker`, `evoke`, `emerge` and
    "as an additional cost" before it — there is no ability whose `text` could
    honestly carry it: an ability is activated, triggered or static, and a cost
    is none of those.

    So the exemption is narrower than the ones already there, not looser. It
    fires only when `card.multikicker` is set, which the loader does only after
    desugaring the cost into working machinery *and* proving something reads the
    count; and it additionally checks that the symbols printed on the line are
    the symbols actually charged, which no previous cost exemption does.
    """

    def _card(self, oracle: str, **extra):
        """An *enchantment*, deliberately.

        `claimed_lines` consumes every printed line the moment a card has
        `spell_effects` — a spell has one place for its text to go — so a
        sorcery would clear the gate whatever this exemption did, and would test
        nothing at all.
        """
        base = {
            "id": "t_mk_perm",
            "name": "Multikicker Permanent",
            "mana_cost": "{1}{W}",
            "types": ["Enchantment"],
            "multikicker": "{1}{W}",
            "oracle_text": oracle,
            "abilities": [
                {
                    "kind": "triggered",
                    "text": ENTERS_LINE,
                    "trigger": {"event": "self_enters", "source": "self"},
                    "effects": [
                        {
                            "op": "draw",
                            "player": "you",
                            "amount": {"additional_paid": True},
                        }
                    ],
                }
            ],
        }
        base.update(extra)
        return compile_card(CardModel.model_validate(base))

    def test_the_multikicker_line_is_claimed(self):
        card = self._card(f"{MULTIKICKER_LINE}\n{ENTERS_LINE}")
        assert residual_text(card, card.oracle_text).strip() == ""

    def test_a_line_nothing_implements_is_still_residual(self):
        """The exemption claims its own line and stops there."""
        unimplemented = "Whenever you gain life, each opponent loses 1 life."
        card = self._card(f"{MULTIKICKER_LINE}\n{ENTERS_LINE}\n{unimplemented}")
        left = residual_text(card, card.oracle_text)
        assert "Whenever you gain life" in left
        assert "Multikicker" not in left

    def test_a_different_printed_cost_is_not_claimed(self):
        """Declaring {1}{W} does not launder a card printing "Multikicker {2}{R}"."""
        card = self._card(f"Multikicker {{2}}{{R}}\n{ENTERS_LINE}")
        assert "Multikicker {2}{R}" in residual_text(card, card.oracle_text)

    def test_an_unparsable_cost_fails_closed(self):
        card = self._card(f"Multikicker sometimes\n{ENTERS_LINE}")
        assert "Multikicker sometimes" in residual_text(card, card.oracle_text)

    def test_the_symbols_may_be_written_in_any_order(self):
        """Matched on the parsed cost, so "{W}{1}" is the same price as "{1}{W}"."""
        card = self._card(f"Multikicker {{W}}{{1}}\n{ENTERS_LINE}")
        assert residual_text(card, card.oracle_text).strip() == ""

    def test_a_card_without_the_cost_gets_nothing(self):
        """The word alone claims nothing — the card has to have the mechanic."""
        model = CardModel.model_validate(
            {
                "id": "t_mk_liar",
                "name": "Multikicker Liar",
                "mana_cost": "{1}{W}",
                "types": ["Enchantment"],
                "oracle_text": MULTIKICKER_LINE,
            }
        )
        card = compile_card(model)
        assert "Multikicker" in residual_text(card, card.oracle_text)
