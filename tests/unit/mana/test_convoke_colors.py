"""Convoke's coloured half, and the creatures that convoked a spell.

702.51a: "each creature you tap while casting this spell pays for {1} **or one
mana of that creature's color**." Without the second half a black creature
could not pay the {B}{B} of Lethal Scheme, and four black creatures with no
land beside them -- a cast the printed card allows -- would offer nothing.
The colour is the creature's own: a green creature still pays only {1}.

702.51c: "a creature 'convoked' a spell if it was tapped to pay for it", which
Lethal Scheme reads back on resolution -- "each creature that convoked this
spell connives". The cast records the tapped creatures on the stack item and
`{"convoked": true}` names them. A convoking creature that left the battlefield
in the meantime is not that creature any more (400.7) and connives no more than
`connive` lets any departed permanent do.

ADR 0020's shape is kept: one cast line, the creatures a `CHOOSE_OBJECTS` asked
as the spell is paid for. Which symbol each creature pays is not a second
question -- the engine takes the split that leaves the rest payable.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.casting import convoke_payments
from commanderblitz.engine.effects.ops_stack import put_copy_on_stack
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import SYMBOL_INDEX, ManaCost
from commanderblitz.engine.structs import CONVOKED_BINDING
from commanderblitz.engine.zones import move_object
from tests.conftest import oids_of, plus_one_counters, settle_completely

SCHEME = "t_scheme"  # {2}{B}{B} instant, convoke; destroy, then each convoker connives
BLACK = "t_black_bear"
ORZHOV = "t_orzhov_bear"
WHITE = "t_white_bear"
GREEN = "t_bear"
VICTIM = "t_bear"

B = SYMBOL_INDEX["B"]
W = SYMBOL_INDEX["W"]


def cast_lines(game, card_id: str = SCHEME) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    ]


def position(builder, mine, *, lands=(), hand=SCHEME, library=6, top="swamp"):
    # The free instant is a reason to stop: with it in hand the caster is asked
    # for priority over the spell, so the spell can be looked at -- and
    # answered -- on the stack before it resolves.
    return (
        builder(players=2)
        .hand(0, [hand, "t_free_trick"])
        .library(0, [top] * library)
        .battlefield(0, list(lands))
        .battlefield(0, list(mine))
        .battlefield(1, [VICTIM])
        .build()
    )


def pick(game, oids) -> None:
    """Answer the convoke pick with exactly these creatures."""
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS, decision
    assert decision.context.get("purpose") == "convoke", decision.context
    wanted = set(oids)
    for index, option in enumerate(decision.options):
        if option.ref is not None and option.ref.id in wanted:
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == index
                )
            )
    if game.pending() is decision:
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))


def cast_at_victim(game, convokers) -> None:
    victim = oids_of(game, VICTIM, 1)[0]
    line = next(a for a in cast_lines(game) if a.targets and a.targets[0].id == victim)
    game.apply(line)
    decision = game.pending()
    if decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS:
        pick(game, convokers)


def resolve(game) -> None:
    """Pass until the spell has resolved, answering its connive discards."""
    settle_completely(game)


class TestAColouredPip:
    def test_black_creatures_pay_the_black_pips(self, builder):
        """Four black creatures and no land: {2}{B}{B} is all convoke."""
        game = position(builder, [BLACK] * 4)
        lines = cast_lines(game)
        assert lines, "four black creatures pay {2}{B}{B} on their own"
        assert {a.pay_generic for a in lines} == {4}
        victim = oids_of(game, VICTIM, 1)[0]
        cast_at_victim(game, oids_of(game, BLACK, 0))
        resolve(game)
        assert game.state.objects[victim].zone is Zone.GRAVEYARD

    def test_a_black_creature_pays_a_b_pip_beside_lands(self, builder):
        """Three Swamps and one black creature: the creature is the fourth mana."""
        game = position(builder, [BLACK], lands=["swamp"] * 3)
        assert {a.pay_generic for a in cast_lines(game)} == {1}

    def test_a_green_creature_beside_one_swamp_leaves_a_b_unpaid(self, builder):
        """{2}{B}{B} off one Swamp and three green creatures: the Swamp pays
        one {B}, the green creatures only the {2}, and the second {B} has
        nobody to pay it."""
        game = position(builder, [GREEN] * 3, lands=["swamp"])
        assert cast_lines(game) == []

    def test_a_green_creature_cannot_pay_b(self, builder):
        """Two green creatures pay the {2}; nothing pays {B}{B}."""
        game = position(builder, [GREEN] * 4)
        assert cast_lines(game) == []

    def test_green_pays_the_generic_while_black_pays_the_pips(self, builder):
        game = position(builder, [GREEN, GREEN, BLACK, BLACK])
        assert {a.pay_generic for a in cast_lines(game)} == {4}
        cast_at_victim(game, oids_of(game, GREEN, 0) + oids_of(game, BLACK, 0))
        resolve(game)
        assert all(game.state.objects[o].tapped for o in oids_of(game, BLACK, 0))

    def test_a_pick_that_cannot_pay_the_pips_is_asked_again(self, builder):
        """Two Swamps pay {B}{B}, and three green creatures can pay only the
        {2}: a third green creature would be tapped for nothing, so a pick of
        all three is refused and asked again."""
        game = position(builder, [GREEN] * 3, lands=["swamp"] * 2)
        victim = oids_of(game, VICTIM, 1)[0]
        game.apply(next(a for a in cast_lines(game) if a.targets[0].id == victim))
        first = game.pending()
        assert (first.min_count, first.max_count) == (2, 3)
        pick(game, oids_of(game, GREEN, 0))
        again = game.pending()
        assert again is not first and "Not enough mana" in again.prompt
        assert not any(game.state.objects[o].tapped for o in oids_of(game, GREEN, 0))
        pick(game, oids_of(game, GREEN, 0)[:2])
        resolve(game)
        assert game.state.objects[victim].zone is Zone.GRAVEYARD

    def test_a_two_colour_creature_pays_either(self, builder):
        """{W}{B} off a white-black creature and a white one: only the split
        that sends the Orzhov creature to {B} pays it."""
        game = position(builder, [ORZHOV, WHITE], hand="t_orzhov_charm")
        lines = cast_lines(game, "t_orzhov_charm")
        assert [a.pay_generic for a in lines] == [2]
        hand = len(game.state.players[0].hand)
        game.apply(lines[0])
        resolve(game)
        assert len(game.state.players[0].hand) == hand, "cast one, drew one"

    def test_a_hybrid_pip_is_paid_by_either_colour(self, builder):
        game = position(builder, [WHITE], hand="t_hybrid_convoker")
        assert [a.pay_generic for a in cast_lines(game, "t_hybrid_convoker")] == [1]
        green = position(builder, [GREEN], hand="t_hybrid_convoker")
        assert cast_lines(green, "t_hybrid_convoker") == []


class TestThePayments:
    def test_every_creature_pays_something(self):
        """A creature whose colour has no pip left and no generic to pay is not
        an outcome: it would be tapped for nothing."""
        cost = ManaCost.parse("{B}")
        assert convoke_payments(cost, [frozenset({W})], room=0) == []

    def test_the_split_is_exhaustive(self):
        cost = ManaCost.parse("{W}{B}")
        both = frozenset({W, B})
        outcomes = convoke_payments(cost, [both, frozenset({W})], room=0)
        assert [(o.colored[W], o.colored[B]) for o, _ in outcomes] == [(0, 0)]

    def test_generic_is_capped_by_room(self):
        """"Pays for {1}" only where there is a {1} to pay."""
        cost = ManaCost.parse("{1}{B}")
        colorless = frozenset()
        assert convoke_payments(cost, [colorless, colorless], room=1) == []
        [(left, generic)] = convoke_payments(cost, [colorless], room=1)
        assert (generic, left.colored[B]) == (1, 1)


class TestTheCreaturesThatConvoked:
    def test_each_connives(self, builder):
        game = position(builder, [BLACK] * 4, library=10)
        convokers = oids_of(game, BLACK, 0)[:4]
        cast_at_victim(game, convokers)
        item = game.state.stack[-1]
        assert sorted(item.bindings[CONVOKED_BINDING]) == sorted(convokers)
        library = len(game.state.players[0].library)
        resolve(game)
        assert len(game.state.players[0].library) == library - 4, "one draw each"

    def test_a_creature_that_did_not_convoke_does_not(self, builder):
        """Two Swamps and two black creatures: the two tapped connive, the
        untapped bystander does not."""
        game = position(builder, [BLACK] * 3, lands=["swamp"] * 2, library=10)
        convokers = oids_of(game, BLACK, 0)[:2]
        bystander = oids_of(game, BLACK, 0)[2]
        cast_at_victim(game, convokers)
        library = len(game.state.players[0].library)
        resolve(game)
        assert len(game.state.players[0].library) == library - 2
        assert not game.state.objects[bystander].tapped
        assert plus_one_counters(game, bystander) == 0

    def test_a_nonland_discard_grows_the_conniver(self, builder):
        """Each draws a creature card and, with nothing else in hand, discards
        it: a nonland discard, so each convoker gets its counter."""
        game = position(builder, [BLACK] * 4, library=4, top=GREEN)
        convokers = oids_of(game, BLACK, 0)
        cast_at_victim(game, convokers)
        resolve(game)
        assert [plus_one_counters(game, o) for o in convokers] == [1, 1, 1, 1]

    def test_one_that_left_before_resolution_does_not_connive(self, builder):
        game = position(builder, [BLACK] * 4, library=10)
        convokers = oids_of(game, BLACK, 0)
        cast_at_victim(game, convokers)
        gone = convokers[0]
        move_object(game.state, gone, Zone.GRAVEYARD)
        assert gone not in game.state.stack[-1].bindings[CONVOKED_BINDING]
        library = len(game.state.players[0].library)
        resolve(game)
        assert len(game.state.players[0].library) == library - 3

    def test_one_that_left_and_came_back_is_a_new_object(self, builder):
        """400.7: the oid survives the trip; the creature that convoked does not."""
        game = position(builder, [BLACK] * 4, library=10)
        convokers = oids_of(game, BLACK, 0)
        cast_at_victim(game, convokers)
        blinked = convokers[0]
        move_object(game.state, blinked, Zone.EXILE)
        move_object(game.state, blinked, Zone.BATTLEFIELD)
        library = len(game.state.players[0].library)
        resolve(game)
        assert len(game.state.players[0].library) == library - 3
        assert plus_one_counters(game, blinked) == 0

    def test_a_copy_was_convoked_by_nobody(self, builder):
        """702.51c asks who was tapped to *pay* for it, and a copy was never
        paid for: convoke is neither an additional nor an alternative cost, so
        707.10 does not carry it over."""
        game = position(builder, [BLACK] * 4, library=10)
        cast_at_victim(game, oids_of(game, BLACK, 0))
        copy = put_copy_on_stack(game.state, 0, game.state.stack[-1])
        assert CONVOKED_BINDING not in copy.bindings

    def test_without_convoking_nobody_connives(self, builder):
        game = position(builder, [BLACK] * 2, lands=["swamp"] * 4, library=10)
        cast_at_victim(game, [])
        assert game.state.stack[-1].bindings[CONVOKED_BINDING] == []
        library = len(game.state.players[0].library)
        resolve(game)
        assert len(game.state.players[0].library) == library


class TestTheLoaderKnowsIt:
    def probe(self, **fields):
        return CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "x",
                "mana_cost": "{2}{B}",
                "types": ["Sorcery"],
                **fields,
            }
        )

    def test_convoked_needs_convoke(self):
        with pytest.raises(DslError, match="convoke"):
            compile_card(
                self.probe(spell_effects=[{"op": "connive", "objects": {"convoked": True}}])
            )

    def test_convoked_is_true_only(self):
        with pytest.raises(DslError, match="convoked must be true"):
            compile_card(
                self.probe(
                    pay_generic_with="tap_creatures",
                    spell_effects=[{"op": "connive", "objects": {"convoked": False}}],
                )
            )

    def test_the_card_compiles(self, registry):
        assert registry.get(SCHEME).pay_generic_with == "tap_creatures"
