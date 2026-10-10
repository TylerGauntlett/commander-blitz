"""Combat damage dealt to a planeswalker, as something a card can hear.

    "Whenever that creature deals combat damage to a player **or
    planeswalker** this turn, draw that many cards."
                                            -- Hunter's Insight

306.8's damage has always worked -- `damage_permanent` takes the loyalty
counters off -- and nothing could trigger on it. `deals_combat_damage_to_player`
is fired from `damage_player`, which a planeswalker hit never reaches, and
`dealt_damage` is about the permanent *being* hurt rather than the one
connecting.

**Its own event, not a widening.** "Whenever this creature deals combat damage
to a player" is printed on dozens of cards that say nothing about planeswalkers;
firing that event here would make every saboteur in the pool trigger off a
planeswalker hit -- a strictly better card than any of them, and silent. The
cards that mean both print "a player **or planeswalker**", which is a
disjunction, and the engine's idiom for a printed disjunction is two abilities
claiming one line: Winged Boots' "flying and ward {4}", magecraft's cast-or-copy,
Tanuki Transplanter's "this creature or equipped creature attacks".

**The subject is the dealer.** The event carries the walker as `planeswalker`
rather than `oid`, because `_subject_oid` reads `oid` first and would make the
permanent *being hit* the trigger's subject -- so `source: "self"` would scope
the ability to the planeswalker instead of the creature connecting, the exact
opposite of every card that prints this line. Left off, the subject falls
through to `event.source`, which is the dealer, exactly as on the player half.
"""

from __future__ import annotations

from commanderblitz.engine.enums import Step
from commanderblitz.engine.primitives import damage_permanent
from tests.conftest import only_oid, pass_until

BOTH = "t_cdpw_saboteur"  # both halves, two abilities, one line
PLAYER_ONLY = "t_cdpw_player_only"  # the player half alone
BYSTANDER = "t_cdpw_bystander"  # the planeswalker half, watching
COUNTER = "t_cdpw_counter"  # draws *that many*
WALKER = "t_walker"  # a 4-loyalty planeswalker


def board(builder, mine=(), theirs=(WALKER,)):
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def connect(game, dealer: str, amount: int = 3, *, target: str = WALKER, combat: bool = True):
    """Deal ``amount`` combat damage from ``dealer`` to ``target``."""
    damage_permanent(
        game.state,
        only_oid(game, target),
        amount,
        only_oid(game, dealer),
        is_combat=combat,
    )
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def drawn(game, before: int, pid: int = 0) -> int:
    return before - len(game.state.players[pid].library)


class TestItFires:
    def test_the_planeswalker_half_triggers(self, builder):
        game = board(builder, mine=[BOTH])
        before = len(game.state.players[0].library)
        connect(game, BOTH)
        assert drawn(game, before) == 1

    def test_the_loyalty_still_comes_off(self, builder):
        """The trigger is added beside 306.8, not instead of it."""
        game = board(builder, mine=[BOTH])
        walker = only_oid(game, WALKER)
        connect(game, BOTH)
        assert game.state.objects[walker].counter("loyalty") == 1

    def test_the_amount_is_carried(self, builder):
        """"draw **that many** cards" -- the payload the whole card turns on."""
        game = board(builder, mine=[COUNTER])
        before = len(game.state.players[0].library)
        connect(game, COUNTER, amount=3)
        assert drawn(game, before) == 3


class TestItDoesNotFireOtherwise:
    def test_a_player_saboteur_is_untouched_by_a_planeswalker_hit(self, builder):
        """The control, and the reason this is its own event: widening the
        player event would have made this card draw."""
        game = board(builder, mine=[PLAYER_ONLY])
        before = len(game.state.players[0].library)
        connect(game, PLAYER_ONLY)
        assert drawn(game, before) == 0

    def test_noncombat_damage_does_not_fire_it(self, builder):
        """"**combat** damage" -- a burn spell at a planeswalker is not this."""
        game = board(builder, mine=[BOTH])
        before = len(game.state.players[0].library)
        connect(game, BOTH, combat=False)
        assert drawn(game, before) == 0

    def test_damage_to_an_ordinary_creature_does_not(self, builder):
        game = board(builder, mine=[BOTH], theirs=[WALKER, "grizzly_bears"])
        before = len(game.state.players[0].library)
        connect(game, BOTH, target="grizzly_bears")
        assert drawn(game, before) == 0

    def test_a_bystander_does_not_fire_for_somebody_elses_hit(self, builder):
        """`source: "self"` scopes it to the creature that connected, which is
        what carrying the walker as `planeswalker` rather than `oid` buys."""
        game = board(builder, mine=[BOTH, BYSTANDER])
        before = len(game.state.players[0].library)
        connect(game, BOTH)
        assert drawn(game, before) == 1, "the saboteur's, and not the bystander's"
