"""Dracogenesis: a standing permission to cast a whole class of spell for nothing.

    You may cast Dragon spells without paying their mana costs.

Rules 601.2b and 107.3b are the whole of it, and they are two claims rather than
one. 601.2b's "without paying its mana cost" is a *replacement of the payment*,
not a reduction of it: no mana is paid at all, coloured pips included. 107.3b
then says what X is when nobody announced one -- zero -- which is the half a
discount gets wrong, because a cost reduced to nothing still has an X to
announce and this one does not.

`spell_cost_reduction` is the nearest existing static and cannot be turned into
this at any amount. `cost_reduction.cost_reduction` clamps every reduction to the
*generic* part of a cost (the comment at `engine/casting.py` records why), so a
reduction can never pay the ``{R}{R}`` of a Dragon, and on an ``{X}`` Dragon a
reduction and this permission disagree about the one number the card is made
of. `grant_playable` is the nearest existing *grant* and is wrong in the other
direction: its cards are "paid for at their printed price", and it marks a
snapshot of the objects it can see when it resolves, so a Dragon drawn a turn
later would never be covered. So this is a static, re-read every time legality
builds the cast lines -- which is what pins the repeatability and the
drawn-later card below.

The second claim is that it is a **permission and not a compulsion**. "You may"
means the printed line survives beside the free one, and a player who wants the
mana actually spent -- for an Aetherflux Reservoir, a converge count, a "spend
mana to cast a creature spell" trigger -- must still be able to pay it. The
free line is therefore an extra action carrying `Action.cast_free`, and which
line was taken is read off the *answer* rather than off the board, because the
board offers both.

Witness: Dracogenesis (`dracogenesis` in `data/cards/auto/`), whose only
line this is. Without it the card is a six-mana enchantment that does nothing.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.primitives import draw_cards
from automtg.engine.zones import destroy

AMNESTY = "t_dragon_amnesty"  # "You may cast Dragon spells without paying their mana costs."
WYRM = "t_cinder_wyrm"  # {4}{R}{R} Dragon 4/4
OGRE = "t_cinder_ogre"  # {4}{R}{R} Ogre 4/4 -- the same card, not a Dragon
X_WYRM = "t_swelling_wyrmling"  # {X}{R} Dragon 0/0, enters with X +1/+1 counters


def board(builder, *, hand=(), lands=(), library=(), amnesty=True, amnesty_seat=0):
    b = (
        builder(players=2)
        .hand(0, list(hand))
        .battlefield(0, list(lands))
        .life(0, 20)
        .library(0, list(library) + ["forest"] * 10)
    )
    if amnesty:
        b = b.battlefield(amnesty_seat, [AMNESTY])
    return b.build()


def casts(game, card_id):
    """Every cast line legality offers for the copy of ``card_id`` in hand."""
    oid = next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == card_id)
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


def free_line(game, card_id):
    return next(a for a in casts(game, card_id) if a.cast_free)


def paid_line(game, card_id):
    return next(a for a in casts(game, card_id) if not a.cast_free)


def battlefield_ids(game, pid=0):
    return [obj.def_id for obj in game.state.battlefield_objects(pid)]


def graveyard_ids(game, pid=0):
    return [game.state.objects[o].def_id for o in game.state.players[pid].graveyard]


def tapped_lands(game, pid=0):
    return sum(1 for o in game.state.battlefield_objects(pid) if o.tapped)


class TestItIsAPermissionNotADiscount:
    """601.2b: the spell is cast for no mana at all, pips included."""

    def test_a_dragon_is_castable_off_an_empty_board(self, builder):
        # Not "cheaper": there is nothing to be cheap with. A reduction clamped
        # to the generic part leaves {R}{R} owing and this line does not exist.
        game = board(builder, hand=[WYRM])
        assert [a.cast_free for a in casts(game, WYRM)] == [True]

    def test_casting_it_pays_nothing(self, builder):
        game = board(builder, hand=[WYRM], lands=["mountain"] * 6)
        game.apply(free_line(game, WYRM))
        assert WYRM in battlefield_ids(game)
        # Six untapped Mountains: the spell was affordable and none of it was
        # spent. A discounted cost would have taken the {R}{R} at least.
        assert tapped_lands(game) == 0
        assert game.state.players[0].mana_pool.total() == 0

    def test_without_the_permission_the_empty_board_offers_nothing(self, builder):
        game = board(builder, hand=[WYRM], amnesty=False)
        assert casts(game, WYRM) == []

    def test_x_is_zero_and_is_never_announced(self, builder):
        # 107.3b. The line is priced on `casting.FREE_COST`, which has no X in
        # it, so `_ask_x` returns 0 without asking -- and the 0/0 Dragon that
        # enters with X counters enters with none and is binned by a
        # state-based action. A reduction to zero would have stopped to ask.
        game = board(builder, hand=[X_WYRM], lands=["mountain"] * 3)
        game.apply(free_line(game, X_WYRM))
        assert game.pending().kind is DecisionKind.PRIORITY
        assert X_WYRM in graveyard_ids(game)
        assert X_WYRM not in battlefield_ids(game)

    def test_the_paid_line_still_announces_an_x(self, builder):
        # The same board, the other line: three Mountains buy X = 2. This is
        # the number a "costs {N} less" version would have got wrong in one
        # direction or the other, and it is the whole card.
        game = board(builder, hand=[X_WYRM], lands=["mountain"] * 3)
        game.apply(paid_line(game, X_WYRM))
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_X
        assert decision.context["max_x"] == 2


class TestItIsOptionalAndScoped:
    """ "You may", and "Dragon spells" -- the two words that bound it."""

    def test_the_printed_line_survives_beside_the_free_one(self, builder):
        # A player who wants the mana spent -- for an Aetherflux Reservoir, a
        # converge count, a "spend mana to cast a creature spell" trigger --
        # must still be able to spend it. Replacing the line would take that
        # away silently.
        game = board(builder, hand=[WYRM], lands=["mountain"] * 6)
        assert sorted(a.cast_free for a in casts(game, WYRM)) == [False, True]

    def test_the_two_lines_are_different_actions(self, builder):
        # Same source, same targets, same X: `cast_free` is the only thing
        # separating them, so it has to be part of the action's identity or a
        # lookup answers with whichever came first.
        game = board(builder, hand=[WYRM], lands=["mountain"] * 6)
        assert paid_line(game, WYRM) != free_line(game, WYRM)
        assert paid_line(game, WYRM).key() != free_line(game, WYRM).key()

    def test_they_are_two_rows_on_screen(self, builder):
        # The client groups the action list by `base_label`. Two identical
        # labels would collapse into one row and the choice would never be
        # offered.
        game = board(builder, hand=[WYRM], lands=["mountain"] * 6)
        assert paid_line(game, WYRM).base_label != free_line(game, WYRM).base_label

    def test_paying_normally_actually_pays(self, builder):
        game = board(builder, hand=[WYRM], lands=["mountain"] * 6)
        game.apply(paid_line(game, WYRM))
        assert WYRM in battlefield_ids(game)
        assert tapped_lands(game) == 6

    def test_a_non_dragon_is_untouched(self, builder):
        # The same mana cost, the same power, one subtype apart.
        game = board(builder, hand=[OGRE])
        assert casts(game, OGRE) == []

    def test_a_non_dragon_is_still_castable_at_its_printed_price(self, builder):
        game = board(builder, hand=[OGRE], lands=["mountain"] * 6)
        assert [a.cast_free for a in casts(game, OGRE)] == [False]

    def test_an_opponents_copy_grants_you_nothing(self, builder):
        # "You may cast": `affects_player` is read against the permanent's
        # controller, not against whoever holds a Dragon.
        game = board(builder, hand=[WYRM], amnesty_seat=1)
        assert casts(game, WYRM) == []


class TestItIsStanding:
    """A static re-read at every cast, not a snapshot taken once."""

    def test_a_dragon_drawn_afterwards_is_covered(self, builder):
        # The snapshot problem `grant_graveyard_cast` exists to fix:
        # `grant_playable` marks the objects it can see as it resolves, so a
        # card that reached hand later would be invisible to it.
        # The land in hand is the position's anchor, not part of the claim:
        # `GameBuilder.build` advances, and a seat with nothing to do rolls the
        # turn forward before legality is ever asked.
        game = board(builder, hand=["forest"], library=[WYRM])
        draw_cards(game.state, 0, 1)
        assert [a.cast_free for a in casts(game, WYRM)] == [True]

    def test_it_is_repeatable_within_one_turn(self, builder):
        # No rate limit is printed and none is imposed: the hand is the limit.
        game = board(builder, hand=[WYRM, WYRM])
        game.apply(free_line(game, WYRM))
        game.apply(free_line(game, WYRM))
        assert battlefield_ids(game).count(WYRM) == 2

    def test_it_stops_when_the_permanent_leaves(self, builder):
        # The boundary a `grant_playable` cannot have: the permission is the
        # permanent, so a Dragon still in hand goes back to its printed price.
        game = board(builder, hand=[WYRM])
        assert casts(game, WYRM)
        amnesty = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == AMNESTY)
        destroy(game.state, amnesty)
        assert casts(game, WYRM) == []
