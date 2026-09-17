"""The Markov Chains deck, card by card, doing what it prints.

Every card here already cleared the six authoring gates, and that is why this
file exists. Gate 5 casts a card once in a fixed sandbox and reads the board,
and it **declines combat** -- so a pillowfort, whose entire rules text is about
somebody else's attack, reaches the pool with the weakest honest expectation
there is: "it is on the battlefield". That is a statement that the card did not
misfire, not that it works.

So the authoring expectation is a floor, and these are the observations. Each
class is one card and asserts the printed sentence the gate could not reach.
"""

from __future__ import annotations

from automtg.engine import zones
from automtg.engine.enums import ActionKind, Step
from tests.conftest import advance_to_step, only_oid

BEAR = "grizzly_bears"  # a plain 2/2
WALKER = "t_walker"  # a loyalty-4 planeswalker with no static of its own
PRISON = "ghostly_prison"


def attack_actions(game, oid: int | None = None):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_ATTACKER and (oid is None or a.source == oid)
    ]


def player_attacks(game, oid: int) -> dict[int, str]:
    """Each *player* this creature is offered against, with the action's label."""
    return {
        a.targets[0].id: a.label or ""
        for a in attack_actions(game, oid)
        if a.targets[0].kind == "player"
    }


def walker_attacks(game, oid: int) -> dict[int, str]:
    """Each *planeswalker* this creature is offered against, with the label."""
    return {
        a.targets[0].id: a.label or ""
        for a in attack_actions(game, oid)
        if a.targets[0].kind == "object"
    }


def untapped_forests(game, pid: int = 0) -> int:
    return sum(
        1
        for oid in game.state.battlefield
        if game.state.objects[oid].def_id == "forest"
        and game.state.objects[oid].controller == pid
        and not game.state.objects[oid].tapped
    )


class TestGhostlyPrison:
    """"Creatures can't attack you unless their controller pays {2} for each
    creature they control that's attacking you."

    The same sentence as Propaganda, on a white enchantment. The near misses a
    mis-written card would land on are each visible here: a `cant_attack`
    static locks the attack instead of pricing it, a `controller: "you"` filter
    taxes only the Prison's own creatures (which never attack its controller),
    and a tax charged against the seat rather than the player would reach the
    planeswalkers 506.2 leaves out.
    """

    def position(self, builder, *, lands: int, bears: int = 1, walker: bool = False):
        """Player 0 attacks; player 1 sits behind a Ghostly Prison."""
        b = (
            builder(players=2)
            .battlefield(0, [BEAR] * bears)
            .battlefield(0, ["forest"] * lands)
            .battlefield(1, [PRISON] + ([WALKER] if walker else []))
        )
        game = b.build()
        advance_to_step(game, Step.DECLARE_ATTACKERS)
        return game

    def test_an_opponents_attack_is_priced_at_two(self, builder):
        """The filter is `controller: any`: the creatures taxed are the ones
        the Prison's controller does *not* control."""
        game = self.position(builder, lands=2)
        bear = only_oid(game, BEAR, 0)
        assert "pay {2}" in player_attacks(game, bear)[1]

    def test_paying_it_taps_the_mana_and_the_creature_attacks(self, builder):
        game = self.position(builder, lands=2)
        bear = only_oid(game, BEAR, 0)
        game.apply(next(a for a in attack_actions(game, bear) if a.targets[0].kind == "player"))
        assert untapped_forests(game) == 0
        assert game.state.combat.attackers[bear] == 1

    def test_it_is_a_price_not_a_wall(self, builder):
        """An unpayable tax withholds the attack (508.1g); a payable one does
        not. A Prison written as `cant_attack` fails the second half."""
        poor = self.position(builder, lands=1)
        assert player_attacks(poor, only_oid(poor, BEAR, 0)) == {}
        rich = self.position(builder, lands=2)
        assert 1 in player_attacks(rich, only_oid(rich, BEAR, 0))

    def test_it_is_two_for_each_attacking_creature(self, builder):
        """Four Forests fund two attackers and not a third."""
        game = self.position(builder, lands=4, bears=3)
        for _ in range(2):
            game.apply(next(a for a in attack_actions(game) if a.targets[0].kind == "player"))
        assert untapped_forests(game) == 0
        assert len(game.state.combat.attackers) == 2
        assert attack_actions(game) == []

    def test_attacking_its_controllers_planeswalker_is_free(self, builder):
        """The near miss. "Can't attack **you**" is about the player; attacking
        a planeswalker they control is a different thing being attacked (506.2),
        so the walker is offered with no price and even with no mana at all."""
        game = self.position(builder, lands=0, walker=True)
        bear = only_oid(game, BEAR, 0)
        walker = only_oid(game, WALKER, 1)
        assert player_attacks(game, bear) == {}, "no mana: the player is out of reach"
        assert walker in walker_attacks(game, bear)
        assert "pay" not in walker_attacks(game, bear)[walker]

    def test_the_tax_ends_when_the_prison_leaves(self, builder):
        """Read live off the battlefield, so there is nothing left to wear off."""
        game = self.position(builder, lands=0)
        bear = only_oid(game, BEAR, 0)
        assert player_attacks(game, bear) == {}
        zones.destroy(game.state, only_oid(game, PRISON, 1))
        offered = player_attacks(game, bear)
        assert 1 in offered
        assert "pay" not in offered[1]
