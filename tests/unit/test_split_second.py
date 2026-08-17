"""Split second (702.61a): the spell nobody may answer.

"As long as this spell is on the stack, players can't cast spells or activate
abilities that aren't mana abilities." The census routes it as "a flag
suppressing priority while the spell is on the stack", which is close and one
word off: priority is *not* suppressed. Players still get it, and still pass.
What is suppressed is almost everything they could do with it.

That distinction is why this is enforced by withholding actions rather than by
skipping the priority window. Skipping the window would also skip state-based
actions and trigger draining, and there would be no way for the player whose
turn it is to do the one thing they are still allowed to do.

**Mana abilities survive**, because 702.61a says so and because they are how a
player pays for the things they are about to not be able to cast. They are
filtered out of the full activated list rather than re-derived, so the two can
never disagree about what a mana ability is.

**Special actions survive too.** Playing a land and suspending are neither
casting nor activating, so the rule leaves them alone. They are unreachable in
practice -- both need sorcery speed and an empty stack -- but the code says
what the rule says rather than what happens to be reachable.

The condition is read off the stack rather than written as a flag when the
spell is cast, so it ends exactly when the spell leaves: countered, resolved or
fizzled alike, with nothing to remember to clear.
"""

from __future__ import annotations

from automtg.engine import legality
from automtg.engine import stack as stack_mod
from automtg.engine.enums import ActionKind, Zone
from tests.conftest import only_oid

SPLIT = "t_split_second"  # {1}{B} instant, split second: destroy target creature
BOLT = "t_bolt"
DORK = "t_dork"  # 1/1 with a mana ability
BEAR = "t_bear"


def position(builder, *, opponent_board=(DORK,)):
    return (
        builder(players=2)
        .hand(0, [SPLIT])
        .battlefield(0, ["swamp", "swamp"])
        .hand(1, [BOLT])
        .battlefield(1, ["mountain"])
        .battlefield(1, list(opponent_board))
        .build()
    )


def put_it_on_the_stack(game):
    """Cast it by hand.

    Driving a real cast would not do: with nothing else on the stack both
    players auto-pass and the spell resolves inside the same `apply`, so the
    window this keyword is entirely about never becomes observable.
    """
    oid = game.state.players[0].hand[0]
    stack_mod.push_spell(game.state, oid, 0)
    return oid


def kinds(actions) -> set[str]:
    return {a.kind.value for a in actions}


class TestWhatIsWithheld:
    def test_the_opponent_may_not_cast(self, builder):
        game = position(builder)
        assert "cast" in kinds(legality._priority_actions(game.state, 1))
        put_it_on_the_stack(game)
        assert "cast" not in kinds(legality._priority_actions(game.state, 1))

    def test_the_caster_may_not_cast_either(self, builder):
        """702.61a says *players*, not *opponents*."""
        game = position(builder)
        put_it_on_the_stack(game)
        assert "cast" not in kinds(legality._priority_actions(game.state, 0))

    def test_passing_is_always_available(self, builder):
        """Withholding everything would be a game that cannot continue."""
        game = position(builder)
        put_it_on_the_stack(game)
        assert kinds(legality._priority_actions(game.state, 1)) >= {"pass"}


class TestWhatSurvives:
    """`manual_mana` is on for player 1 throughout.

    A tap-only mana ability is not offered as an *action* by default -- the
    payment solver owns it, which is the documented auto-mana simplification --
    so without the toggle there would be no mana ability in the list to
    preserve, and the exemption would be untestable rather than absent.
    """

    def activations(self, game, pid: int = 1) -> list:
        game.state.players[pid].manual_mana = True
        return [
            a
            for a in legality._priority_actions(game.state, pid)
            if a.kind is ActionKind.ACTIVATE
        ]

    def test_mana_abilities_are_still_offered(self, builder):
        game = position(builder)
        put_it_on_the_stack(game)
        activations = self.activations(game)
        assert activations, "702.61a exempts mana abilities"
        for action in activations:
            card = game.state.card(action.source)
            assert card.abilities[action.ability_index].is_mana_ability

    def test_a_non_mana_ability_is_not(self, builder):
        """The sac outlet needs a creature to eat, which the bear supplies."""
        game = position(builder, opponent_board=("t_sac_outlet", BEAR))
        before = self.activations(game)
        assert any(
            not game.state.card(a.source).abilities[a.ability_index].is_mana_ability
            for a in before
        ), "the sac outlet is activatable to begin with"
        put_it_on_the_stack(game)
        after = self.activations(game)
        assert all(
            game.state.card(a.source).abilities[a.ability_index].is_mana_ability
            for a in after
        ), "only mana abilities survive"


class TestItEndsWithTheSpell:
    def test_it_is_off_before_the_spell_is_cast(self, builder):
        game = position(builder)
        assert not legality.split_second_active(game.state)

    def test_it_is_on_while_the_spell_is_on_the_stack(self, builder):
        game = position(builder)
        put_it_on_the_stack(game)
        assert legality.split_second_active(game.state)

    def test_it_is_off_once_the_spell_leaves(self, builder):
        """Read off the stack rather than latched, so countered, resolved and
        fizzled all end it with nothing to clear."""
        game = position(builder)
        put_it_on_the_stack(game)
        game.state.stack = []
        assert not legality.split_second_active(game.state)
        assert "cast" in kinds(legality._priority_actions(game.state, 1))

    def test_an_ordinary_spell_does_not_switch_it_on(self, builder):
        game = (
            builder(players=2)
            .hand(0, [BOLT])
            .battlefield(0, ["mountain"])
            .hand(1, [BOLT])
            .battlefield(1, ["mountain"])
            .build()
        )
        stack_mod.push_spell(game.state, game.state.players[0].hand[0], 0)
        assert not legality.split_second_active(game.state)
        assert "cast" in kinds(legality._priority_actions(game.state, 1))


class TestTheCardLoads:
    def test_the_flag_is_on_the_card(self, registry):
        assert registry.get(SPLIT).split_second

    def test_ordinary_cards_do_not_carry_it(self, registry):
        assert not registry.get(BOLT).split_second

    def test_it_is_still_an_ordinary_removal_spell(self, builder):
        """The keyword changes what others may do, not what the spell does."""
        game = position(builder, opponent_board=(BEAR,))
        oid = only_oid(game, BEAR, 1)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
