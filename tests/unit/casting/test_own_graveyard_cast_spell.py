""""You may cast this card from your graveyard." -- on an instant or a sorcery.

Their Number Is Legion. The card's own permission at its printed price, the
shape Gravecrawler's `cast_from_graveyard` static with ``active_zones:
["graveyard"]`` already has (`test_conditional_graveyard_cast.py`), printed on a
nonpermanent. It is not flashback (702.34a) or jump-start: there is no
alternative cost and no exile rider, so the spell is cast for its mana cost, X
announced as usual (601.2b), at the card's normal timing (an instant may be
cast whenever it has priority, a sorcery only in its owner's main phase with
the stack empty, 307.1), and it goes where an instant or sorcery normally goes
(608.2n): its owner's graveyard, from which it may be cast again. "Exile Their
Number Is Legion" is the card's own `exiles_itself`, and the only thing that
sends the Legion to exile.

Without this, the near miss is `graveyard_cost` with the printed mana: an
alternative cost (118.9), so a free-cast or other-alternative-cost effect would
treat the graveyard cast differently from the printed one, and the spell would
be exiled by the flashback rider whether or not the card said so.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.conftest import count_on_battlefield, settle_to_priority

LEGION = "t_gy_legion"  # {X}{B}{B} sorcery, X tapped Necron Warriors, life per artifact, exiles itself
RECUR = "t_gy_recur"  # {1}{B} sorcery, draw a card
QUICK = "t_gy_quick"  # {B} instant, gain 1 life
TOKEN = "necron_warrior_2_2_b_artifact"
ANCHOR = "t_plain_instant"  # {W}, gain 1 life


def position(builder, graveyard, *, hand=(), opponent_graveyard=(), step=Step.PRECOMBAT_MAIN):
    game = (
        builder(players=2)
        .battlefield(0, ["swamp"] * 6)
        .battlefield(1, ["plains"])
        .hand(0, list(hand))
        # Something the opponent could respond with, so neither seat's priority
        # window is skipped as one with nothing to do in it.
        .hand(1, [ANCHOR])
        .graveyard(0, list(graveyard))
        .graveyard(1, list(opponent_graveyard))
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(step)
        .build(advance=False)
    )
    # Every priority window is a stop, so a step outside the main phase is one
    # a test can stand in rather than be advanced past.
    for player in game.state.players:
        player.full_control = True
    game._advance()
    return game


def in_graveyard(game, card_id: str, seat: int = 0) -> int:
    found = [o for o in game.state.players[seat].graveyard if game.state.objects[o].def_id == card_id]
    assert len(found) == 1, f"expected one {card_id} in seat {seat}'s graveyard"
    return found[0]


def casts(game, oid: int) -> list:
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


def answer_x(game, x: int) -> None:
    decision = game.pending()
    if decision is not None and decision.kind is DecisionKind.CHOOSE_X:
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == x)
        )


def resolve(game) -> None:
    settle_to_priority(game)
    while game.state.stack:
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
        settle_to_priority(game)


def untapped_swamps(game) -> int:
    return sum(
        1
        for o in game.state.battlefield
        if game.state.objects[o].def_id == "swamp" and not game.state.objects[o].tapped
    )


class TestTheLine:
    def test_a_sorcery_is_castable_from_its_owners_graveyard(self, builder):
        game = position(builder, [RECUR])
        assert casts(game, in_graveyard(game, RECUR))

    def test_one_line_not_two(self, builder):
        game = position(builder, [RECUR])
        assert len(casts(game, in_graveyard(game, RECUR))) == 1

    def test_not_from_an_opponents_graveyard(self, builder):
        """ "Your graveyard" -- the permission is its owner's alone."""
        game = position(builder, [], opponent_graveyard=[RECUR])
        assert not casts(game, in_graveyard(game, RECUR, seat=1))


class TestTiming:
    """The permission says where from, not when: 307.1 and 304.1 still hold."""

    def test_a_sorcery_waits_for_an_empty_stack(self, builder):
        # A second instant in hand keeps the caster's window open while the
        # stack is full, so the question is asked of a live priority.
        game = position(builder, [RECUR, QUICK], hand=[QUICK])
        recur = in_graveyard(game, RECUR)
        game.apply(casts(game, in_graveyard(game, QUICK))[0])
        decision = game.pending()
        assert decision.kind is DecisionKind.PRIORITY and decision.player == 0
        assert len(game.state.stack) == 1
        assert not casts(game, recur)
        assert any(a.kind is ActionKind.CAST for a in game.legal_actions())

    def test_a_sorcery_is_not_cast_outside_a_main_phase(self, builder):
        game = position(builder, [RECUR], step=Step.UPKEEP)
        assert game.state.step is Step.UPKEEP
        assert not casts(game, in_graveyard(game, RECUR))

    def test_an_instant_is_cast_outside_a_main_phase(self, builder):
        game = position(builder, [QUICK], step=Step.UPKEEP)
        assert game.state.step is Step.UPKEEP
        assert casts(game, in_graveyard(game, QUICK))


class TestTheCast:
    def test_it_costs_the_printed_mana(self, builder):
        game = position(builder, [RECUR])
        before = untapped_swamps(game)
        game.apply(casts(game, in_graveyard(game, RECUR))[0])
        resolve(game)
        assert before - untapped_swamps(game) == 2

    def test_it_resolves_and_goes_back_to_the_graveyard(self, builder):
        """608.2n: an instant or sorcery goes to its owner's graveyard. Nothing
        printed exiles it, so it is there to be cast again."""
        game = position(builder, [RECUR])
        hand_before = len(game.state.players[0].hand)
        game.apply(casts(game, in_graveyard(game, RECUR))[0])
        resolve(game)
        assert len(game.state.players[0].hand) == hand_before + 1
        again = in_graveyard(game, RECUR)
        assert casts(game, again)

    def test_an_instant_resolves_and_comes_back(self, builder):
        game = position(builder, [QUICK])
        life = game.state.players[0].life
        game.apply(casts(game, in_graveyard(game, QUICK))[0])
        resolve(game)
        assert game.state.players[0].life == life + 1
        assert game.state.objects[in_graveyard(game, QUICK)].zone is Zone.GRAVEYARD

    def test_cast_from_hand_it_is_an_ordinary_spell(self, builder):
        game = position(builder, [], hand=[RECUR])
        oid = game.state.players[0].hand[0]
        assert casts(game, oid)


class TestTheLegion:
    def test_x_is_announced_and_paid(self, builder):
        game = position(builder, [LEGION])
        legion = in_graveyard(game, LEGION)
        life = game.state.players[0].life
        game.apply(casts(game, legion)[0])
        answer_x(game, 3)
        resolve(game)

        assert count_on_battlefield(game, TOKEN, 0) == 3
        tokens = [o for o in game.state.battlefield if game.state.objects[o].def_id == TOKEN]
        assert all(game.state.objects[o].tapped for o in tokens)
        assert game.state.players[0].life == life + 3
        assert untapped_swamps(game) == 1

    def test_it_exiles_itself(self, builder):
        """The printed "Exile Their Number Is Legion", and only that: one
        graveyard cast, then it is gone."""
        game = position(builder, [LEGION])
        legion = in_graveyard(game, LEGION)
        game.apply(casts(game, legion)[0])
        answer_x(game, 1)
        resolve(game)

        obj = game.state.objects[legion]
        assert obj.zone is Zone.EXILE
        assert not [
            o for o in game.state.players[0].graveyard if game.state.objects[o].def_id == LEGION
        ]
