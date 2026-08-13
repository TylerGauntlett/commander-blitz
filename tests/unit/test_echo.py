"""Echo — a per-object flag the engine already had.

    "Echo {2}{G} (At the beginning of your upkeep, if this came under your
    control since the beginning of your last upkeep, sacrifice it unless you
    pay its echo cost.)"

The census filed this as routed on "'came under your control since your last
upkeep' is the missing per-object flag". It is not missing: `set_flag` and
`has_flag` shipped for renown, and echo is the same shape with the flag written
*by* the ability that reads it.

    upkeep trigger, intervening-if `{"not": {"has_flag": "echo_paid"}}`
    → `set_flag` "echo_paid"
    → `may` with a `pay`, and a `sacrifice` in the `else`

Three properties fall out of `set_flag`'s existing contract rather than being
arranged, and each is the printed card:

- **It fires once.** The flag is one-way and nothing clears it at end of turn,
  so a creature that survives its echo upkeep is never asked again.
- **It fires on the first of *your* upkeeps.** A creature that arrived on an
  opponent's turn is asked on your next one, because the trigger is
  `controller: "you"` and the flag is still unset.
- **A creature that leaves and returns pays again.** `reset_permanent_state`
  clears `flags` on a zone change, which is rule 400.7 and is exactly right
  here — the returning permanent is a new object that came under your control
  since your last upkeep.

The flag is set *before* the payment, and that matters: it is "was this asked",
not "was this paid". Setting it in the paid branch would ask again next upkeep
of anybody who declined — and they have already sacrificed the creature, so
nothing would show it.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Step, Zone
from tests.conftest import find_action, only_oid, pass_until

FOREST = "forest"
OX = "t_echoer"


def position(builder, lands: int = 4):
    game = (
        builder(players=2)
        .battlefield(0, [FOREST] * lands)
        .battlefield(0, [OX])
        .library(0, [FOREST] * 20)
        .library(1, [FOREST] * 20)
        .build()
    )
    return game, only_oid(game, OX)


def to_echo_question(game, *, until_turn: int = 6):
    """Run until the echo "pay?" is offered, or ``until_turn`` passes without it.

    The Ox is on the battlefield before turn 1's upkeep has finished being
    advanced past, so the first of *your* upkeeps that it sees is turn 3's --
    which is itself part of what the card says, and why this waits rather than
    asserting on a fixed turn.
    """
    from tests.conftest import _default_answer

    for _ in range(600):
        decision = game.pending()
        if decision is None or game.state.turn > until_turn:
            return None
        if any(a.kind is ActionKind.YES for a in game.legal_actions()):
            return decision
        game.apply(_default_answer(game, decision))
    return None


class TestItAsksOnce:
    def test_the_upkeep_asks_for_the_echo_cost(self, builder):
        game, _ = position(builder)
        assert to_echo_question(game) is not None, "the echo question"

    def test_paying_keeps_the_creature(self, builder):
        game, ox = position(builder)
        to_echo_question(game)
        game.apply(find_action(game, ActionKind.YES))
        pass_until(game, lambda g: g.state.step is Step.PRECOMBAT_MAIN)

        assert game.state.objects[ox].zone is Zone.BATTLEFIELD

    def test_declining_sacrifices_it(self, builder):
        game, ox = position(builder)
        to_echo_question(game)
        game.apply(find_action(game, ActionKind.NO))
        pass_until(game, lambda g: g.state.objects[ox].zone is not Zone.BATTLEFIELD)

        assert game.state.objects[ox].zone is Zone.GRAVEYARD

    def test_it_never_asks_again(self, builder):
        """The whole of echo. `set_flag` is one-way and nothing clears it."""
        game, ox = position(builder)
        to_echo_question(game)
        game.apply(find_action(game, ActionKind.YES))
        assert "echo_paid" in game.state.objects[ox].flags

        pass_until(game, lambda g: g.state.turn >= 3 and g.state.step is Step.UPKEEP)
        assert to_echo_question(game) is None, "asked once, in the whole game"
        assert game.state.objects[ox].zone is Zone.BATTLEFIELD


class TestTheFlagIsWrittenBeforeThePayment:
    def test_it_is_already_marked_while_the_question_is_open(self, builder):
        """"Was this asked", not "was this paid".

        The mark is what makes echo once-only, so it must not depend on the
        answer. Written in the paid branch instead, a player who declined would
        be asked again — and having declined they have no creature left, so
        nothing on the board would ever show it.
        """
        game, ox = position(builder)
        to_echo_question(game)

        assert "echo_paid" in game.state.objects[ox].flags, "set before the may"
