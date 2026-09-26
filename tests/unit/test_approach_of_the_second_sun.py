"""Approach of the Second Sun — three clauses, three seams that already existed.

    "If this spell was cast from your hand and you've cast another spell named
    Approach of the Second Sun this game, you win the game. Otherwise, put it
    into its owner's library seventh from the top and you gain 7 life."

Only "you win the game" and "you gain 7 life" were sayable. The other three
clauses each needed one small addition, and each has a near miss that would have
been silently wrong:

**`cast_from_hand`** is the sibling of `cast_from_graveyard`, not its negation.
A spell cast from exile (foretell, plot, adventure), off a Citadel top or from
the command zone was cast from neither — and a **copy** was never cast at all
(707.10), so a copy of Approach must not win the game. `zone_is` cannot answer it
either: it reports the source's *current* zone, which for any resolving sorcery
is the stack.

**`spells_cast_this_game`** is a game-long tally, because
`TurnLedger.spells_cast_ids` is cleared at every turn boundary — on the turn that
matters it reads empty, so a card written against it could never win. Nothing
else in the engine keeps cast history: object flags die with the object on a zone
change, and `set_turn_flag` is one turn by name.

The subtlety is **"another"**, and it is deliberately the card's job rather than
the leaf's. `push_spell` fires `SPELL_CAST` as the spell goes on the stack, so by
the time its own effects run it has already recorded itself. A card meaning
"another" therefore compares `> 1`. Subtracting one inside the leaf would be
wrong for every sentence that does not say "another", and nothing inside it can
tell which was meant. `TestTheSecondCopyWins` measures exactly that boundary: one
cast does not win, two do.

**`tucks_itself`** is the eighth rider on the resolution slot and the only one
whose destination is a library and that carries a depth. Written as a
`put_on_top` op in the card's own effects it would reach nothing —
`_place_after_resolution` runs after `spell_effects` and moves a nonpermanent to
the graveyard unconditionally, which is the same reason `exiles_itself` is a
rider. The ordinal converts to an index the way `op_put_on_top` does, and for its
stated reason: a card tucked sixth when the card says seventh is drawn a turn
early, which is the whole of what the depth buys.

Witness: Approach of the Second Sun
(`data/authoring/answers/approach_of_the_second_sun.json`).
"""

from __future__ import annotations

from automtg.engine.effects.conditions import evaluate_condition
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.values import evaluate_value
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.state import new_object
from tests.conftest import _default_answer

APPROACH = "t_approach"  # the printed card
TUCK = "t_approach_tuck_only"  # the tuck rider with no win half
PLAINS = "plains"


def position(builder, hand=(APPROACH,), library=None, lands=8):
    return (
        builder(players=2)
        .battlefield(0, [PLAINS] * lands)
        .battlefield(1, [PLAINS])
        .hand(0, list(hand))
        .hand(1, [PLAINS])
        .library(0, list(library) if library is not None else [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def ctx(game, source=None) -> EffectContext:
    return EffectContext(state=game.state, controller=0, source_oid=source)


def cast(game, card_id: str) -> None:
    """Cast the sorcery and let it resolve."""
    game._advance()
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    for _ in range(60):
        decision = game.pending()
        if decision is None:
            return
        if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
            return
        game.apply(_default_answer(game, decision))


class TestCastFromHand:
    def test_a_spell_cast_from_hand_answers_true(self, builder):
        game = position(builder)
        oid = game.state.players[0].hand[0]
        game.state.objects[oid].cast_from_hand = True
        assert evaluate_condition(game.state, {"cast_from_hand": True}, controller=0, source=oid) is True

    def test_one_that_was_not_answers_false(self, builder):
        """A copy, a foretold card, a Citadel cast -- none of them is a hand."""
        game = position(builder)
        oid = game.state.players[0].hand[0]
        game.state.objects[oid].cast_from_hand = False
        assert evaluate_condition(game.state, {"cast_from_hand": True}, controller=0, source=oid) is False

    def test_it_is_not_the_negation_of_cast_from_graveyard(self, builder):
        """The claim that makes it a separate key: an object cast from exile
        answers **false to both**, where a negation would answer true to one."""
        game = position(builder)
        oid = game.state.players[0].hand[0]
        obj = game.state.objects[oid]
        obj.cast_from_hand = False
        obj.cast_from_graveyard = False
        assert evaluate_condition(game.state, {"cast_from_hand": True}, controller=0, source=oid) is False
        assert evaluate_condition(game.state, {"cast_from_graveyard": True}, controller=0, source=oid) is False


class TestTheGameLongCastLedger:
    def test_it_counts_a_cast(self, builder):
        game = position(builder)
        cast(game, APPROACH)
        assert evaluate_value(
            ctx(game), {"spells_cast_this_game": "you"}
        ) == 1

    def test_it_survives_a_turn_boundary(self, builder):
        """The whole reason it is not the turn ledger. `spells_cast_ids` is
        cleared at every boundary, so a card reading it could never win."""
        game = position(builder)
        cast(game, APPROACH)
        game.state.turn_ledger.clear()
        assert not game.state.turn_ledger.spells_cast_ids
        assert evaluate_value(
            ctx(game), {"spells_cast_this_game": "you"}
        ) == 1

    def test_the_name_filter_only_counts_matching_spells(self, builder):
        game = position(builder, hand=(APPROACH, TUCK))
        cast(game, TUCK)
        by_name = {
            "spells_cast_this_game": {
                "player": "you",
                "filter": {"name": "Test Approach"},
            }
        }
        assert evaluate_value(ctx(game), {"spells_cast_this_game": "you"}) == 1
        assert evaluate_value(ctx(game), by_name) == 0

    def test_it_is_per_player(self, builder):
        game = position(builder)
        cast(game, APPROACH)
        assert evaluate_value(
            ctx(game), {"spells_cast_this_game": "opponent"}
        ) == 0


class TestTheSecondCopyWins:
    """"**Another** spell named Approach" -- the `> 1` boundary.

    The spell records itself before its own effects run, so one cast counts one
    and does not win; the second counts two and does. This is the pair that would
    break if the leaf tried to subtract the spell itself.
    """

    def test_the_first_cast_does_not_win(self, builder):
        game = position(builder)
        cast(game, APPROACH)
        assert game.over is False
        assert game.state.players[0].life == 47, "the Otherwise branch gains 7"

    def test_the_second_cast_wins(self, builder):
        game = position(builder, hand=(APPROACH, APPROACH), lands=16)
        cast(game, APPROACH)
        assert game.over is False
        cast(game, APPROACH)
        assert game.over and game.winners == [0]


class TestTheTuck:
    def test_it_goes_to_the_library_and_not_the_graveyard(self, builder):
        game = position(builder)
        cast(game, TUCK if False else APPROACH)
        oid = next(
            o for o, obj in game.state.objects.items() if obj.def_id == APPROACH
        )
        assert game.state.objects[oid].zone is Zone.LIBRARY
        assert oid not in game.state.players[0].graveyard

    def test_it_lands_seventh_from_the_top(self, builder):
        """The depth is the point. Index 6 is the seventh card, and the printed
        ordinal counting from 1 is what `op_put_on_top` converts the same way."""
        game = position(builder)
        cast(game, APPROACH)
        oid = next(
            o for o, obj in game.state.objects.items() if obj.def_id == APPROACH
        )
        assert game.state.players[0].library.index(oid) == 6

    def test_a_card_without_the_rider_still_goes_to_the_graveyard(self, builder):
        """Pins that the redirect is the rider's and not the harness's: a
        foreign sorcery in the same position ends where it always did."""
        game = position(builder, hand=("t_gain_three",))
        obj = new_object(game.state, "t_gain_three", owner=0, zone=Zone.HAND)
        assert obj is not None
        cast(game, "t_gain_three")
        oid = next(
            o
            for o, ob in game.state.objects.items()
            if ob.def_id == "t_gain_three" and ob.zone is Zone.GRAVEYARD
        )
        assert oid in game.state.players[0].graveyard


class TestGateFourAcceptsTheTuck:
    """The authoring gate that asks "did the card end where a card of its kind
    ends", and the reason widening it is not weakening it.

    `verify._play_once` allows a nonpermanent to finish in a graveyard, plus exile
    for the two declared riders that say so. `tucks_itself` is the third,
    admitted on identical terms: **a declared flag**. A spell that merely finds
    itself in a library still fails, which is the whole point of the gate reading
    the card rather than the type.

    The gate itself is pinned where every gate is: `tests/cards` re-runs all six
    over every machine-authored card on each run, so Approach sitting in the
    shipped pool *is* the assertion that gate 4 accepts it. What is worth pinning
    here is the flag the gate reads, because that is what distinguishes the two
    cases.
    """

    def _pool(self):
        from pathlib import Path

        from automtg.cards.registry import CardRegistry, authored_card_paths

        return CardRegistry.from_paths(
            authored_card_paths(Path("data/cards"))
            + sorted(Path("tests/data").glob("*.cards.json"))
        )

    def test_the_tucking_card_declares_its_depth(self):
        assert self._pool().get(APPROACH).tucks_itself == 7

    def test_an_ordinary_sorcery_declares_nothing(self):
        """The half that keeps the gate a gate: `_play_once` widens on the flag,
        so a spell without one has no business in a library."""
        assert self._pool().get("t_gain_three").tucks_itself is None
