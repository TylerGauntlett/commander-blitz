""""Add {C} for each card you've drawn this turn." -- Kydele, Chosen of Kruphix.

Every other multiplier in the value language is a question about the board: how
many Vampires, how many +1/+1 counters, how much life. Those are all readable
from the position, so they need no bookkeeping -- `count` walks a zone and
answers. This one is not readable from the position at all. A card drawn this
turn may have been played, discarded, bounced or drawn again; the hand at the
moment Kydele taps is a different number, and it is a different number in the
direction that matters, because the whole card is built around drawing a lot and
spending it.

So it is a tally of an *event*, and rule 121.1 says exactly which event: a player
draws a card by putting the top card of their library into their hand. Counted
in `draw_cards` rather than off the `draw` event, so there is no path by which a
card reaches a hand from a library without the tally seeing it.

The reset is the whole design, and getting it wrong produces a wrong number
rather than an error:

**The opening hand is not drawn during a turn.** Rule 103 sets the game up
before the first turn begins, and `_opening_sequence` draws seven cards through
the same `draw_cards` -- fourteen if somebody mulligans. The `damage_ledger`
that shipped just before this one clears at cleanup, and copying that here would
have left seven draws sitting in the tally for the whole of turn 1, so a Kydele
in an opening hand would tap for seven the moment she landed. Hence the untap
step: it is the first thing that happens inside a turn, and nothing before it
belongs to one.

**Cleanup is still this turn.** Rule 514.3a hands priority back when cleanup
triggers something, and a Kydele activated in that window has still drawn what
she drew. Clearing at cleanup would zero the count while the turn was running.

**You draw on other players' turns too.** `lands_played` is the engine's other
per-turn counter and it resets in the active player's own untap, which is right
for a land drop and wrong for this: a Kydele that forgot an instant-speed draw
from the opponent's end step would be quietly the wrong size on your own turn.
Hence a single dict on `GameState`, cleared once per turn, not once per seat.

The mana half of the card rides on machinery that already shipped -- see
`test_variable_mana_ability.py` for why `mana_amount` is threaded through
`mana_produced`, and for the failure that shape exists to prevent: an offer and a
payment that disagree strand a cast mid-payment with nothing on screen saying so.
The two tests here that re-check it do so because this multiplier can change
*between* the offer and the tap in a way a board count cannot -- drawing a card
is something a player can do at instant speed.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.costs import activate_mana_ability, mana_sources
from automtg.engine.enums import ActionKind, Step
from automtg.engine.game import create_game
from automtg.engine.primitives import draw_cards
from tests.conftest import action_for_card, only_oid, pass_until

KYDELE = "kydele_chosen_of_kruphix"
DRAW_SPELL = "t_draw_spell"  # {2}{U} sorcery, "Draw two cards."

COLORLESS = 5  # index of {C} in the six-tuple: WUBRG then colourless


def position(builder, *, drawn: int = 0, active: int = 0):
    """Kydele on player 0's battlefield, having drawn `drawn` cards this turn."""
    game = (
        builder(players=2)
        .battlefield(0, [KYDELE])
        .active(active)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    draw_cards(game.state, 0, drawn)
    return game, only_oid(game, KYDELE, 0)


def tally(game, pid: int = 0) -> int:
    return game.state.cards_drawn_this_turn.get(pid, 0)


def offered(game, oid: int) -> tuple[int, ...]:
    """What the payment solver believes this permanent can make."""
    source = next(s for s in mana_sources(game.state, 0) if s.oid == oid)
    assert len(source.options) == 1
    return source.options[0]


def paid(game, oid: int) -> tuple[int, ...]:
    """What actually lands in the pool."""
    before = tuple(game.state.players[0].mana_pool.amounts)
    activate_mana_ability(game.state, oid, 0, 0, 0)
    after = tuple(game.state.players[0].mana_pool.amounts)
    return tuple(a - b for a, b in zip(after, before, strict=True))


class TestTheTallyFollowsEveryDraw:
    @pytest.mark.parametrize("count", [0, 1, 3, 7])
    def test_a_draw_is_counted(self, builder, count):
        game, _ = position(builder, drawn=count)
        assert tally(game) == count

    def test_the_draw_step_counts(self, builder):
        """The turn-based draw, which is most turns' only one."""
        game = (
            builder(players=2)
            .battlefield(0, [KYDELE])
            .turn(3)  # not turn 1: the starting player skips that draw in a duel
            .step(Step.UNTAP)
            .build(advance=False)
        )
        assert tally(game) == 0
        game._advance()  # runs the turn-based actions up to the first priority
        assert tally(game) == 1

    def test_a_spell_that_draws_counts(self, builder):
        """Not a special case -- the point is that nothing routes around it."""
        game = (
            builder(players=2)
            .hand(0, [DRAW_SPELL])
            .battlefield(0, ["island", "island", "island"])
            .build()
        )
        assert tally(game) == 0
        game.apply(action_for_card(game, ActionKind.CAST, DRAW_SPELL))
        pass_until(game, lambda g: not g.state.stack)
        assert tally(game) == 2

    def test_an_empty_library_counts_nothing(self, builder):
        """Rule 104.3c: the attempt is recorded, but no card was drawn.

        Kydele is a ramp engine and the deck she is in mills itself out. If the
        failed attempt counted, she would tap for more the turn her controller
        is losing to it.
        """
        game = (
            builder(players=2)
            .battlefield(0, [KYDELE])
            .library(0, ["island"])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        draw_cards(game.state, 0, 3)
        assert game.state.players[0].attempted_draw_from_empty
        assert tally(game) == 1, "one card was there to draw, not three"


class TestItIsScopedToTheTurn:
    def test_the_opening_hand_does_not_count(self):
        """The boundary a cleanup-time reset gets wrong, and gets wrong silently.

        A real game rather than a sandbox position, because the sandbox deals
        its hands directly into the zone and would never exercise this. Rule 103
        draws these before turn 1 exists.
        """
        game = create_game(["aesi", "edgar"], seed=3, starting_player=0)
        pass_until(
            game,
            lambda g: g.state.turn == 1 and g.state.step is Step.PRECOMBAT_MAIN,
        )
        assert len(game.state.players[0].hand) >= 7, "the opening hand was drawn"
        assert sum(game.state.cards_drawn_this_turn.values()) == 0, (
            "seven cards drawn before the game began are not cards drawn this turn"
        )

    def test_it_lasts_the_whole_turn(self, builder):
        """"This turn" runs to the end of the turn, not to the end of the phase.

        Read in the postcombat main rather than the end step: with nothing to
        respond to, auto-pass never stops in the end step, so a predicate
        waiting there would sail into the *next* turn and read a cleared tally
        as if it had never been set.
        """
        game, _ = position(builder, drawn=4)
        game._advance()
        pass_until(
            game,
            lambda g: g.state.step is Step.POSTCOMBAT_MAIN and g.state.turn == 1,
        )
        assert tally(game) == 4

    def test_the_next_turn_starts_at_zero(self, builder):
        """Past the untap step, not merely past the turn number.

        `turn` is bumped before the untap step's turn-based actions run, so a
        predicate that stopped at the number alone would read the tally in the
        one window where it has not been cleared yet and pass either way.
        """
        game, _ = position(builder, drawn=4)
        game._advance()
        pass_until(
            game,
            lambda g: g.state.turn == 2 and g.state.step is Step.PRECOMBAT_MAIN,
        )
        assert tally(game) == 0, "a Kydele does not tap for what she drew yesterday"
        assert tally(game, 1) == 1, "the new turn's own draw step is counted"

    def test_a_draw_on_an_opponents_turn_counts_for_you(self, builder):
        """Why the tally is cleared once per turn and not once per seat."""
        game, oid = position(builder, drawn=2, active=1)
        assert tally(game) == 2
        assert paid(game, oid)[COLORLESS] == 2


class TestKydeleTapsForWhatSheHasDrawn:
    @pytest.mark.parametrize("count", [0, 1, 2, 5])
    def test_the_pool_gets_the_real_amount(self, builder, count):
        game, oid = position(builder, drawn=count)
        assert paid(game, oid)[COLORLESS] == count

    def test_she_makes_only_colourless(self, builder):
        game, oid = position(builder, drawn=3)
        assert paid(game, oid) == (0, 0, 0, 0, 0, 3)

    def test_no_draws_is_no_mana(self, builder):
        """The boundary. She is a 2/3 for four that does nothing on a dead turn."""
        game, oid = position(builder, drawn=0)
        assert paid(game, oid) == (0, 0, 0, 0, 0, 0)

    @pytest.mark.parametrize("count", [0, 1, 4])
    def test_the_offer_and_the_payment_agree(self, builder, count):
        game, oid = position(builder, drawn=count)
        promised = offered(game, oid)
        assert paid(game, oid) == promised, (
            "a spell offered on more mana than the tap actually makes strands "
            "the payment mid-cast, and nothing on screen would say why"
        )

    def test_a_draw_between_the_offer_and_the_tap_moves_the_number(self, builder):
        """Not a bug -- it is why the amount is read at activation, not at load.

        Drawing is something a player can do at instant speed, so unlike a board
        count this multiplier can genuinely change while a payment is open. What
        must hold is that the tap pays what the tally says *now*.
        """
        game, oid = position(builder, drawn=1)
        assert offered(game, oid)[COLORLESS] == 1
        draw_cards(game.state, 0, 2)
        assert offered(game, oid)[COLORLESS] == 3
        assert paid(game, oid)[COLORLESS] == 3


def probe(amount) -> dict:
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "{T}: Add {C} for each thing.",
        "mana_cost": "{G}",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
        "abilities": [
            {
                "kind": "activated",
                "text": "{T}: Add {C} for each thing.",
                "is_mana_ability": True,
                "cost": {"tap": True},
                "effects": [{"op": "add_mana", "mana": "{C}", "amount": amount}],
            }
        ],
    }


class TestTheLoaderAcceptsItInsideAManaAbility:
    def test_it_is_allowed_where_x_and_bindings_are_not(self):
        """`MANA_AMOUNT_FORBIDDEN` refuses the forms that would always read 0.

        A mana ability resolves during payment with nothing on the stack, so it
        has no X, no targets and no bindings -- and rule 605 says it may not stop
        to ask anything either. This one reads state and asks nothing, which is
        the same standing `counters_on` has, so it belongs on the allowed side.
        """
        compile_card(CardModel.model_validate(probe({"cards_drawn_this_turn": "you"})))
