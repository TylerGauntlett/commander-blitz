"""Negative Zone Portal, past what the behaviour gate can see.

    "{2}, {T}: Exile target card from an opponent's graveyard. If it's a
    creature card, draw a card.
    At the beginning of your upkeep, if there are four or more creature cards
    exiled with this artifact, flip a coin. If you lose the flip, sacrifice this
    artifact and return a card exiled with it at random to its owner's hand."

The gate casts the artifact and stops, so neither line ever runs there. Each is
asserted here with its near miss: the draw is for a creature card only, the
count reads cards exiled *with this artifact* and creature cards only, and the
flip decides the sacrifice through `flip_coin` rather than happening every
upkeep.
"""

from __future__ import annotations

from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.rng import Rng
from commanderblitz.engine.state import new_object
from tests.conftest import activations, oids_of, only_oid, settle

PORTAL = "negative_zone_portal"
BEAR = "t_bear"  # a creature card
SPELL = "t_plain_instant"  # a noncreature card


def seed_that(won: bool) -> int:
    """A seed whose first coin flip comes down the way asked."""
    return next(s for s in range(100) if (Rng(s).randint(0, 1) == 1) is won)


class TestTheActivation:
    def board(self, builder, yard):
        return (
            builder(players=2)
            .battlefield(0, [PORTAL, "island", "island"])
            .graveyard(1, list(yard))
            .build()
        )

    def activate_on(self, game, oid: int) -> None:
        portal = only_oid(game, PORTAL)
        action = next(
            a for a in activations(game, portal) if any(t.id == oid for t in a.targets)
        )
        game.apply(action)
        settle(game)

    def test_a_creature_card_is_exiled_with_it_and_draws(self, builder):
        game = self.board(builder, [BEAR])
        target = game.state.players[1].graveyard[0]
        hand = len(game.state.players[0].hand)
        self.activate_on(game, target)
        exiled = [game.state.objects[o] for o in game.state.players[1].exile]
        assert [o.def_id for o in exiled] == [BEAR]
        assert exiled[0].exiled_by == only_oid(game, PORTAL)
        assert len(game.state.players[0].hand) == hand + 1

    def test_a_noncreature_card_draws_nothing(self, builder):
        game = self.board(builder, [SPELL])
        target = game.state.players[1].graveyard[0]
        hand = len(game.state.players[0].hand)
        self.activate_on(game, target)
        assert len(game.state.players[1].exile) == 1
        assert len(game.state.players[0].hand) == hand


class TestTheUpkeep:
    def board(self, builder, *, creatures: int, seed: int, others: int = 0):
        game = (
            builder(players=2, seed=seed)
            .battlefield(0, [PORTAL])
            .hand(0, ["forest"])
            .active(0)
            .step(Step.UNTAP)
            .build(advance=False)
        )
        game.state.rng = Rng(seed)
        portal = only_oid(game, PORTAL)
        for card_id, n in ((BEAR, creatures), (SPELL, others)):
            for _ in range(n):
                card = new_object(game.state, card_id, owner=1, zone=Zone.EXILE)
                card.exiled_by = portal
                game.state.players[1].exile.append(card.oid)
        game._advance()
        settle(game)
        return game

    def test_a_lost_flip_sacrifices_it_and_returns_one_at_random(self, builder):
        game = self.board(builder, creatures=4, seed=seed_that(False))
        assert not oids_of(game, PORTAL)
        assert [game.state.objects[o].def_id for o in game.state.players[1].hand] == [BEAR]
        assert len(game.state.players[1].exile) == 3

    def test_a_won_flip_keeps_it(self, builder):
        game = self.board(builder, creatures=4, seed=seed_that(True))
        assert oids_of(game, PORTAL)
        assert len(game.state.players[1].exile) == 4

    def test_three_creature_cards_flip_nothing(self, builder):
        """Noncreature cards exiled with it do not count toward the four."""
        game = self.board(builder, creatures=3, others=2, seed=seed_that(False))
        assert oids_of(game, PORTAL)
        assert not [e for e in game.state.events if e.type == "coin_flipped"]
