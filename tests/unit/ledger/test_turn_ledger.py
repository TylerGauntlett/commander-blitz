"""The per-turn ledger: morbid, raid, bloodthirst, spectacle, storm, gravestorm.

Every one of those keywords asks a question the board cannot answer. "If a
creature died this turn" is not "is there a creature in a graveyard" -- a
creature can reach a graveyard by being discarded, milled or sacrificed as a
cost, and one that died last turn is still lying there. "If you attacked this
turn" is unanswerable the moment combat ends, because nothing on the board
records that it happened. They are tallies of *events*, which is the same
standing `cards_drawn_this_turn` has and the same reason it exists.

Six tallies rather than six pieces of state, because the argument in
`docs/keywords.md` is that they are one capability: the census marks morbid,
raid, bloodthirst, spectacle, prowl, storm and gravestorm as waiting on "a
per-turn ledger", and a design driven by only morbid would be rebuilt by raid.

**The fold is in `GameState.emit`, and that is the claim most of this file
tests.** Every tally counts something that already emits an event, and `emit` is
the one function all of them pass through -- so a new way to kill a creature, or
a new source of damage, is counted without anybody remembering to count it. The
failure mode this prevents is silent and it is a wrong *number*, not an error:
a bloodthirst creature that quietly enters without its counters looks exactly
like one whose condition was correctly false. So the tests here that matter most
are the ones that drive a real game and never touch a primitive directly.

Two boundaries carry the design:

**Damage to a player is life loss** (rule 118.2). Spectacle asks whether an
opponent lost life, and it is printed on cards you cast after hitting somebody
with a Lightning Bolt. A ledger that counted only `lose_life` would read false
there, which is the one case the mechanic was designed for.

**Cleared at cleanup, not at untap.** `cards_drawn_this_turn` clears at untap
because the opening hand is drawn before turn 1 exists and would otherwise sit
in the tally all of turn 1. Nothing counted here can happen before the game
starts, so it clears with `damage_ledger` -- and it must, because "a creature
died this turn" has to stay true through the end step it is read in.
"""

from __future__ import annotations

import pytest

from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.game import create_game
from automtg.engine.primitives import damage_player, lose_life
from automtg.engine.structs import TargetRef
from automtg.engine.zones import move_object
from tests.conftest import (
    _default_answer,
    action_for_card,
    attack_with,
    find_action,
    only_oid,
    pass_until,
)

BEAR = "t_bear"  # {1}{G} 2/2
BOLT = "t_bolt"  # {R} instant, "deals 3 damage to any target"
DRAW_SPELL = "t_draw_spell"  # {2}{U} sorcery, "Draw two cards."


def responsive(builder):
    """A two-player game where player 0 always has a legal instant to cast.

    Not decoration: it is what makes the late steps of a turn observable at
    all. See `within_this_turn`.
    """
    return builder(players=2).hand(0, [BOLT]).battlefield(0, ["mountain"])


# The combat idiom of `test_combat.py`, repeated rather than imported: these
# four lines are what "a real game attacked" means, and the point of the tests
# below is that nothing in that path knows the ledger exists.
def to_attackers(game):
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)


def to_blockers(game):
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS)


def block_with(game, blocker_oid: int, attacker_oid: int):
    game.apply(
        find_action(
            game,
            ActionKind.ADD_BLOCKER,
            source=blocker_oid,
            targets=(TargetRef.obj(attacker_oid),),
        )
    )


def done(game):
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def within_this_turn(game, predicate, limit: int = 200):
    """Pass priority to ``predicate``, failing if the turn rolls over first.

    Every assertion in this file is about a tally *during* the turn that wrote
    it, and reaching a late step in that turn is harder than it looks: with
    nothing to respond to, the engine auto-passes from combat damage straight
    into the next turn, so a test waiting for the postcombat main arrives after
    cleanup has correctly emptied the ledger and reports the clearing as a
    failure to count. `test_combat.resolve_combat` documents the same problem.

    Two things prevent it. This helper asserts the turn boundary rather than
    hoping for it, and every position that uses it holds an instant and a
    land -- with a legal cast available, priority genuinely stops in each step
    and the steps become observable.
    """
    turn = game.state.turn
    for _ in range(limit):
        if predicate(game):
            return
        assert not game.over, "the game ended before the assertion"
        assert game.state.turn == turn, "the turn rolled over before the assertion"
        decision = game.pending()
        assert decision is not None, "nothing left to pass with"
        game.apply(_default_answer(game, decision))
    raise AssertionError("did not reach the condition inside one turn")


def position(builder, *, players: int = 2, active: int = 0):
    """A frozen mid-turn position with a bear each and nothing having happened."""
    game = (
        builder(players=players)
        .battlefield(0, [BEAR])
        .battlefield(1, [BEAR])
        .active(active)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    return game, game.state.turn_ledger


class TestNothingHappenedYet:
    """The boundary every one of these is read against: an empty turn."""

    def test_every_tally_starts_empty(self, builder):
        _, ledger = position(builder)
        assert ledger.creatures_died == {}
        assert ledger.attacked == set()
        assert ledger.damage_taken == {}
        assert ledger.life_lost == {}
        assert ledger.spells_cast == {}
        assert ledger.cards_to_graveyard == 0


class TestCreaturesDying:
    def test_a_creature_dying_is_counted_under_its_controller(self, builder):
        game, ledger = position(builder)
        move_object(game.state, only_oid(game, BEAR, 1), Zone.GRAVEYARD)
        assert ledger.creatures_died == {1: 1}, "the bear died under player 1"

    def test_a_noncreature_dying_is_not(self, builder):
        """Morbid says *creature*, and the DIES event fires for any permanent."""
        game = (
            builder(players=2)
            .battlefield(0, ["island"])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        move_object(game.state, only_oid(game, "island", 0), Zone.GRAVEYARD)
        assert game.state.turn_ledger.creatures_died == {}

    def test_a_creature_leaving_for_exile_is_not_a_death(self, builder):
        """Rule 700.4: only the battlefield-to-graveyard move is dying."""
        game, ledger = position(builder)
        move_object(game.state, only_oid(game, BEAR, 0), Zone.EXILE)
        assert ledger.creatures_died == {}

    def test_a_creature_discarded_from_hand_is_not_a_death(self, builder):
        """The trap a "creature card in a graveyard" count would fall into."""
        game = (
            builder(players=2)
            .hand(0, [BEAR])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        oid = game.state.players[0].hand[0]
        move_object(game.state, oid, Zone.GRAVEYARD)
        assert game.state.turn_ledger.creatures_died == {}
        assert game.state.turn_ledger.cards_to_graveyard == 1, "still a card, though"

    def test_deaths_accumulate(self, builder):
        game, ledger = position(builder)
        for pid in (0, 1):
            move_object(game.state, only_oid(game, BEAR, pid), Zone.GRAVEYARD)
        assert ledger.creatures_died == {0: 1, 1: 1}


class TestCombatDeathsCountWithoutAnyoneCountingThem:
    """The claim the whole `emit` design exists to make."""

    def test_a_creature_dying_in_combat_is_counted(self, builder):
        game = responsive(builder).battlefield(0, [BEAR]).battlefield(1, [BEAR]).build()
        attacker = only_oid(game, BEAR, 0)
        blocker = only_oid(game, BEAR, 1)
        to_attackers(game)
        attack_with(game, attacker)
        done(game)
        to_blockers(game)
        block_with(game, blocker, attacker)
        done(game)
        within_this_turn(game, lambda g: g.state.step >= Step.END_OF_COMBAT)
        assert game.state.turn_ledger.creatures_died == {0: 1, 1: 1}, (
            "two 2/2s traded; nothing in combat.py had to know the ledger exists"
        )


class TestAttacking:
    def test_declaring_an_attacker_records_the_attacking_player(self, builder):
        game = builder().battlefield(0, [BEAR]).build()
        to_attackers(game)
        assert game.state.turn_ledger.attacked == set(), "not yet declared"
        attack_with(game, only_oid(game, BEAR, 0))
        done(game)
        assert game.state.turn_ledger.attacked == {0}

    def test_declining_to_attack_records_nothing(self, builder):
        """Raid's boundary, and why the event fires only when there are attackers."""
        game = responsive(builder).battlefield(0, [BEAR]).build()
        to_attackers(game)
        done(game)
        within_this_turn(game, lambda g: g.state.step >= Step.END_OF_COMBAT)
        assert game.state.turn_ledger.attacked == set()

    def test_it_survives_the_end_of_combat(self, builder):
        """Raid is read after combat, when nothing on the board records it."""
        game = responsive(builder).battlefield(0, [BEAR]).build()
        to_attackers(game)
        attack_with(game, only_oid(game, BEAR, 0))
        done(game)
        within_this_turn(game, lambda g: g.state.step >= Step.POSTCOMBAT_MAIN)
        assert not (game.state.combat and game.state.combat.attackers), (
            "combat is over, so the board no longer says anybody attacked"
        )
        assert game.state.turn_ledger.attacked == {0}


class TestDamageAndLifeLoss:
    def test_damage_to_a_player_is_counted(self, builder):
        game, ledger = position(builder)
        damage_player(game.state, 1, 3, None)
        assert ledger.damage_taken == {1: 3}

    def test_damage_to_a_player_is_also_life_loss(self, builder):
        """Rule 118.2, and the whole of spectacle."""
        game, ledger = position(builder)
        damage_player(game.state, 1, 3, None)
        assert ledger.life_lost == {1: 3}, (
            "a spectacle spell is cast after bolting somebody, and a ledger that "
            "counted only `lose_life` would read false there"
        )

    def test_life_loss_without_damage_is_counted(self, builder):
        game, ledger = position(builder)
        lose_life(game.state, 0, 2)
        assert ledger.life_lost == {0: 2}
        assert ledger.damage_taken == {}, "a drain is not damage"

    def test_damage_to_a_permanent_is_neither(self, builder):
        """The two shapes share one event; only the player form is life loss."""
        game, ledger = position(builder)
        game.state.players[1].life = 40
        bolt_a_bear(game, only_oid(game, BEAR, 1))
        assert ledger.damage_taken == {}
        assert ledger.life_lost == {}

    def test_amounts_accumulate(self, builder):
        game, ledger = position(builder)
        damage_player(game.state, 1, 2, None)
        lose_life(game.state, 1, 5)
        assert ledger.damage_taken == {1: 2}
        assert ledger.life_lost == {1: 7}

    def test_gaining_life_is_not_losing_it(self, builder):
        game, ledger = position(builder)
        lose_life(game.state, 0, 0)
        assert ledger.life_lost == {}, "a zero is not an entry"


def bolt_a_bear(game, oid: int) -> None:
    from automtg.engine.primitives import damage_permanent

    damage_permanent(game.state, oid, 3, None)


class TestSpellsCast:
    def test_casting_a_spell_is_counted(self, builder):
        game = (
            builder(players=2)
            .hand(0, [DRAW_SPELL])
            .battlefield(0, ["island", "island", "island"])
            .build()
        )
        assert game.state.turn_ledger.spells_cast == {}
        game.apply(action_for_card(game, ActionKind.CAST, DRAW_SPELL))
        assert game.state.turn_ledger.spells_cast == {0: 1}, (
            "storm counts on cast, not on resolution -- a countered spell was "
            "still cast"
        )

    def test_it_is_counted_per_caster(self, builder):
        """Storm counts every spell cast this turn *by anybody*, which is the sum.

        So the tally is keyed by caster and read with `"all"` -- a single
        counter would answer storm and nothing else, and the very next card
        that wants "spells you've cast this turn" would have to rebuild it.
        """
        game = (
            builder(players=2)
            .hand(0, [DRAW_SPELL])
            .battlefield(0, ["island", "island", "island"])
            .hand(1, [BOLT])
            .battlefield(1, ["mountain"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, DRAW_SPELL))
        game.apply(action_for_card(game, ActionKind.CAST, BOLT))
        assert game.state.turn_ledger.spells_cast == {0: 1, 1: 1}
        assert sum(game.state.turn_ledger.spells_cast.values()) == 2


class TestCardsToGraveyard:
    def test_a_card_dying_counts(self, builder):
        game, ledger = position(builder)
        move_object(game.state, only_oid(game, BEAR, 0), Zone.GRAVEYARD)
        assert ledger.cards_to_graveyard == 1

    def test_a_token_does_not(self, builder):
        """Gravestorm counts *cards*, and a token is the commonest non-card."""
        from automtg.engine.primitives import create_token

        game, ledger = position(builder)
        (oid,) = create_token(game.state, "t_warrior_token", 0)
        move_object(game.state, oid, Zone.GRAVEYARD)
        assert ledger.cards_to_graveyard == 0

    def test_a_card_reaching_exile_does_not(self, builder):
        game, ledger = position(builder)
        move_object(game.state, only_oid(game, BEAR, 0), Zone.EXILE)
        assert ledger.cards_to_graveyard == 0


class TestItIsScopedToTheTurn:
    def test_it_lasts_the_whole_turn(self, builder):
        """"This turn" runs to the end of the turn, not to the end of the phase.

        Morbid is printed on cards cast in a second main phase, off a creature
        that died in combat -- so the tally has to cross the whole back half of
        the turn it was written in.
        """
        game = responsive(builder).battlefield(0, [BEAR]).battlefield(1, [BEAR]).build()
        move_object(game.state, only_oid(game, BEAR, 1), Zone.GRAVEYARD)
        within_this_turn(game, lambda g: g.state.step >= Step.END_STEP)
        assert game.state.turn_ledger.creatures_died == {1: 1}

    def test_the_next_turn_starts_empty(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR])
            .battlefield(1, [BEAR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        move_object(game.state, only_oid(game, BEAR, 1), Zone.GRAVEYARD)
        damage_player(game.state, 1, 3, None)
        pass_until(
            game,
            lambda g: g.state.turn == 2 and g.state.step is Step.PRECOMBAT_MAIN,
        )
        ledger = game.state.turn_ledger
        assert ledger.creatures_died == {}
        assert ledger.damage_taken == {}
        assert ledger.life_lost == {}
        assert ledger.cards_to_graveyard == 0

    def test_a_real_game_starts_with_an_empty_ledger(self):
        """Nothing counted here happens before turn 1 -- the claim behind
        clearing at cleanup rather than at untap."""
        game = create_game(["aesi", "edgar"], seed=3, starting_player=0)
        pass_until(
            game,
            lambda g: g.state.turn == 1 and g.state.step is Step.PRECOMBAT_MAIN,
        )
        ledger = game.state.turn_ledger
        assert ledger.creatures_died == {}
        assert ledger.attacked == set()
        assert ledger.cards_to_graveyard == 0


class TestTheValueLanguageReadsIt:
    """Six value expressions, so no new condition vocabulary was needed."""

    @pytest.mark.parametrize(
        ("expr", "expected"),
        [
            ({"creatures_died_this_turn": "all"}, 1),
            ({"creatures_died_this_turn": "you"}, 0),
            ({"creatures_died_this_turn": "each_opponent"}, 1),
            ({"attacked_this_turn": "you"}, 0),
            ({"damage_taken_this_turn": "each_opponent"}, 3),
            ({"life_lost_this_turn": "each_opponent"}, 3),
            ({"cards_to_graveyard_this_turn": True}, 1),
        ],
    )
    def test_each_form_reads_the_ledger(self, builder, expr, expected):
        from automtg.engine.effects.context import EffectContext
        from automtg.engine.effects.values import evaluate_value

        game, _ = position(builder)
        move_object(game.state, only_oid(game, BEAR, 1), Zone.GRAVEYARD)
        damage_player(game.state, 1, 3, None)
        ctx = EffectContext(state=game.state, controller=0)
        assert evaluate_value(ctx, expr) == expected

    def test_morbid_is_an_ordinary_comparison(self, builder):
        """The reason these are values and not condition leaves."""
        from automtg.engine.effects.conditions import evaluate_condition

        game, _ = position(builder)
        morbid = {"cmp": ">=", "left": {"creatures_died_this_turn": "all"}, "right": 1}
        assert not evaluate_condition(game.state, morbid, controller=0)
        move_object(game.state, only_oid(game, BEAR, 1), Zone.GRAVEYARD)
        assert evaluate_condition(game.state, morbid, controller=0)

    def test_an_unknown_tally_is_refused_at_load_time(self):
        from automtg.engine.effects.values import validate_value
        from automtg.engine.errors import DslError

        with pytest.raises(DslError):
            validate_value({"creatures_died_last_turn": "all"}, "test")
