""""That ability triggers an additional time" — scoped two different ways.

Harmonic Prodigy and Veyran print the same *effect* and disagree completely
about what it applies to, which is why `double_triggers` carries two filters
rather than one:

- **Harmonic Prodigy** — "if a triggered ability of **a Shaman or another
  Wizard you control** triggers". The scope is the permanent whose ability
  fired. Any cause at all counts: an upkeep trigger doubles as readily as a
  cast trigger.
- **Veyran** — "if **you casting or copying an instant or sorcery spell**
  causes a triggered ability of a permanent you control to trigger". The scope
  is the *cause*. Any permanent you control counts, Goblins included; what
  matters is what set the ability off.

Read either card's line as the other's and you get a card that is wrong in both
directions at once, so both axes are asserted here, and each is asserted to
*not* fire on the other's case: `TestProdigyIgnoresTheCause` doubles an upkeep
trigger, and `TestVeyranIgnoresTheSubtype` doubles a Goblin's.

`double_land_triggers` is left alone. It is player-wide, land-only, and reads
its "as long as" gate through `players_doubling_land_triggers`, which is the
single place every player-wide static is gated; folding it in would move it out
of that path for no gain.

The count is asserted through cards drawn rather than through queued abilities,
because "an additional time" is a claim about how many times the ability
*happens*, and a second queue entry that never resolved would satisfy a weaker
test.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import pass_until

PRODIGY = "t_prodigy"  # doubles a Shaman or another Wizard you control
VEYRAN = "t_veyran"  # doubles what your instant or sorcery caused
WIZARD = "t_wizard_drawer"  # a Wizard: "whenever you cast an instant or sorcery, draw"
GOBLIN = "t_goblin_drawer"  # the same trigger on a Goblin
UPKEEP = "t_upkeep_wizard"  # a Wizard whose upkeep trigger GAINS LIFE, not draws
RITUAL = "pyretic_ritual"  # {1}{R} instant -- a targetless cause
ANCHOR = "t_plain_instant"  # a reason for the opponent to hold priority


def position(builder, board, *, hand=(RITUAL,)):
    return (
        builder(players=2)
        .battlefield(0, [*board, "mountain", "mountain", "mountain", "island"])
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 20)
        .hand(0, list(hand))
        .hand(1, [ANCHOR])
        .build()
    )


def cast_and_count_draws(game, card_id: str = RITUAL) -> int:
    """Cast ``card_id`` and report how many cards left player 0's library."""
    before = len(game.state.players[0].library)
    pass_until(
        game,
        lambda g: g.pending() is not None
        and g.pending().player == 0
        and any(
            a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == card_id
            for a in g.legal_actions()
        ),
    )
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )
    return before - len(game.state.players[0].library)


class TestTheBaselineIsOne:
    def test_a_lone_wizard_draws_once(self, builder):
        assert cast_and_count_draws(position(builder, [WIZARD])) == 1

    def test_a_lone_goblin_draws_once(self, builder):
        assert cast_and_count_draws(position(builder, [GOBLIN])) == 1


class TestHarmonicProdigyScopesBySubtype:
    def test_it_doubles_another_wizards_trigger(self, builder):
        assert cast_and_count_draws(position(builder, [PRODIGY, WIZARD])) == 2

    def test_it_does_not_double_a_goblins_trigger(self, builder):
        """"a Shaman or another Wizard" is a restriction, not decoration."""
        assert cast_and_count_draws(position(builder, [PRODIGY, GOBLIN])) == 1

    def test_it_does_not_double_an_opponents_wizard(self, builder):
        """"you control"."""
        game = (
            builder(players=2)
            .battlefield(0, [PRODIGY, "mountain", "mountain", "mountain", "island"])
            .battlefield(1, [WIZARD, "plains"])
            .library(0, ["forest"] * 30)
            .library(1, ["forest"] * 20)
            .hand(0, [RITUAL])
            .hand(1, [ANCHOR])
            .build()
        )
        assert cast_and_count_draws(game) == 0, "their Wizard, their draw"


def life_gained_over_next_upkeep(builder, board) -> int:
    """Life gained during player 0's next upkeep, doublers included.

    Life rather than cards: the upkeep is one step away from the turn's own
    draw, and a draw-counting version of this read 2 for a single trigger
    because the window caught it. A life total has nothing else moving it.

    Three things this has to get right, and each was wrong first:

    - Advance *into* the upkeep rather than build standing in it. The trigger
      fires as the step begins, and a position built at that step has missed it.
    - Advance to **player 0's** upkeep specifically. `build()` has already run
      past turn one's, so the next upkeep reached is the opponent's -- where a
      `controller: "you"` trigger correctly does nothing, and a test reading
      zero would blame the doubler.
    """
    game = (
        builder(players=2)
        .battlefield(0, [*board, "island"])
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 20)
        .hand(1, [ANCHOR])
        .build()
    )
    pass_until(
        game,
        lambda g: g.state.step is Step.UPKEEP and g.state.active_player == 0,
        limit=800,
    )
    before = game.state.players[0].life
    pass_until(game, lambda g: g.state.step is not Step.UPKEEP, limit=800)
    return game.state.players[0].life - before


class TestProdigyIgnoresTheCause:
    def test_it_doubles_an_upkeep_trigger_too(self, builder):
        """No `cause_events`, so any cause counts -- unlike Veyran."""
        assert life_gained_over_next_upkeep(builder, [PRODIGY, UPKEEP]) == 2


class TestVeyranScopesByCause:
    def test_it_doubles_a_wizards_cast_trigger(self, builder):
        assert cast_and_count_draws(position(builder, [VEYRAN, WIZARD])) == 2

    def test_it_doubles_a_goblins_cast_trigger_too(self, builder):
        """"a permanent you control" -- Veyran does not care about subtypes."""
        assert cast_and_count_draws(position(builder, [VEYRAN, GOBLIN])) == 2


class TestVeyranIgnoresTheSubtype:
    def test_it_does_not_double_an_upkeep_trigger(self, builder):
        """The cause must be a spell you cast or copied, and an upkeep is not."""
        assert life_gained_over_next_upkeep(builder, [VEYRAN, UPKEEP]) == 1

    def test_the_upkeep_trigger_alone_is_the_same_one(self, builder):
        """The control, so the test above cannot pass by the trigger not firing."""
        assert life_gained_over_next_upkeep(builder, [UPKEEP]) == 1


class TestTheyStack:
    def test_two_doublers_each_add_one(self, builder):
        """Not four. Each doubler queues ONE extra copy of the one ability that
        fired, so a Wizard under both is 1 + 1 + 1 -- "triggers an additional
        time" twice over, not "twice, twice"."""
        assert cast_and_count_draws(position(builder, [PRODIGY, VEYRAN, WIZARD])) == 3
