"""Foretell on a permanent card: cast from exile, then an ordinary permanent.

    "Foretell {4}{U} (During your turn, you may pay {2} and exile this card
    from your hand face down. Cast it on a later turn for its foretell cost.)"

Rule 702.143a makes foretell a property of the *card*, not of instants and
sorceries: the special action exiles any card with it, and the later cast is a
cast like any other, so a foretold creature spell resolves onto the battlefield
(608.3) as the face-up creature it prints. Three claims follow.

**The cast is the creature's, at its own timing.** Foretell changes the price
and the zone, never the speed: a creature foretold is still cast only when a
sorcery could be (307.1/302.1), on a later turn, for the foretell cost.

**What arrives is an ordinary permanent.** Face down in exile is `revealed_to`,
a fact about a card nobody may interact with; the spell and the permanent are
public, with the card's own characteristics.

**The printed line is the price.** A permanent has no `spell_effects` to claim
"Foretell {4}{U}" wholesale, so the residual gate claims it off the card-level
`foretell` field, strictly: the declared cost must be the printed one.

**The foretelling is spent by the cast.** A foretold card that leaves exile is
a new object (400.7) that was never foretold. Without that, a foretold creature
cast, resolved and later exiled by a removal spell would be castable again from
exile for its foretell cost, and an instant exiled out of the graveyard the
same. `reset_permanent_state` clears `foretold_by` on every zone change for
that reason, and `foretell_card` writes it after its own move.

Witness: Sage of the Beyond (`sage_of_the_beyond` in `data/cards/auto/`).
"""

from __future__ import annotations

from commanderblitz.cards.authoring.verify import _covered
from commanderblitz.engine.carddef import CardDef
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.mana import ManaCost
from commanderblitz.engine.zones import exile
from tests.conftest import pass_until

DRAKE = "t_foretold_drake"  # {3}{U}{U} 3/3 flier, foretell {1}{U}
LINE = (
    "Foretell {4}{U} (During your turn, you may pay {2} and exile this card "
    "from your hand face down. Cast it on a later turn for its foretell cost.)"
)


def position(builder, islands: int = 2, hand: tuple[str, ...] = ()):
    """Player 0 holds the drake on `islands` Islands; turn 1 starts."""
    return (
        builder(players=2)
        .battlefield(0, ["island"] * islands)
        .hand(0, [DRAKE, *hand])
        .hand(1, ["island"])
        .library(0, ["island"] * 30)
        .library(1, ["island"] * 30)
        .build()
    )


def to_main(game, turn: int, pid: int = 0):
    pass_until(
        game,
        lambda g: (
            g.state.turn >= turn
            and g.state.step in (Step.PRECOMBAT_MAIN, Step.POSTCOMBAT_MAIN)
            and (d := g.pending()) is not None
            and d.player == pid
        ),
    )


def foretell_action(game):
    return next(
        (a for a in game.legal_actions() if a.kind is ActionKind.SUSPEND), None
    )


def foretold_casts(game):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == DRAKE
        and a.foretold
    ]


def foretold(builder, islands: int = 2, hand: tuple[str, ...] = ()):
    """(game, oid): the drake foretold on player 0's turn 3."""
    game = position(builder, islands=islands, hand=hand)
    to_main(game, 3)
    oid = next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == DRAKE)
    game.apply(foretell_action(game))
    return game, oid


class TestTheSpecialAction:
    def test_a_creature_card_can_be_foretold(self, builder):
        game, oid = foretold(builder)
        assert game.state.objects[oid].zone is Zone.EXILE
        assert game.state.objects[oid].foretold_by == 0
        assert game.state.objects[oid].revealed_to == {0}


class TestTheLaterCast:
    def test_not_on_the_turn_it_was_foretold(self, builder):
        game, _ = foretold(builder, islands=6)
        assert foretold_casts(game) == []

    def test_for_the_foretell_cost_on_a_later_turn(self, builder):
        """Two Islands pay {1}{U}; the printed {3}{U}{U} they could not."""
        game, _ = foretold(builder, islands=2)
        to_main(game, 5)
        assert foretold_casts(game)

    def test_at_sorcery_speed_only(self, builder):
        """Foretell moves the price and the zone, not the timing.

        Opt in hand so player 0 is asked for priority on the opponent's turn.
        """
        game, _ = foretold(builder, islands=3, hand=("opt",))
        pass_until(
            game,
            lambda g: g.state.turn >= 4 and (d := g.pending()) is not None and d.player == 0,
        )
        assert game.state.active_player == 1
        assert foretold_casts(game) == []


class TestWhatArrives:
    def _cast(self, builder):
        game, oid = foretold(builder, islands=2)
        to_main(game, 5)
        game.apply(foretold_casts(game)[0])
        return game, oid

    def test_it_resolves_onto_the_battlefield_face_up(self, builder):
        game, oid = self._cast(builder)
        pass_until(game, lambda g: not g.state.stack)
        obj = game.state.objects[oid]
        assert obj.zone is Zone.BATTLEFIELD
        assert obj.controller == 0
        assert not obj.face_down
        assert obj.revealed_to == set(), "the hidden-in-exile seat list is gone"

    def test_it_is_the_creature_it_prints(self, builder):
        from commanderblitz.engine.characteristics import chars

        game, oid = self._cast(builder)
        pass_until(game, lambda g: not g.state.stack)
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (3, 3)
        assert "flying" in c.keywords


class TestTheForetellingIsSpent:
    def test_a_resolved_creature_exiled_again_is_not_castable(self, builder):
        """400.7: the card back in exile is a new object nobody foretold."""
        game, oid = foretold(builder, islands=4)
        to_main(game, 5)
        game.apply(foretold_casts(game)[0])
        pass_until(game, lambda g: not g.state.stack)

        exile(game.state, oid)
        assert game.state.objects[oid].foretold_by is None
        to_main(game, 7)
        assert foretold_casts(game) == []

    def test_a_card_moved_out_of_exile_forgets_it(self, builder):
        """Bounced from exile to hand, it must be foretold again to be cheap."""
        from commanderblitz.engine.zones import move_object

        game, oid = foretold(builder)
        move_object(game.state, oid, Zone.HAND)
        assert game.state.objects[oid].foretold_by is None


def _sage(foretell: str | None) -> CardDef:
    return CardDef(
        id="sage_of_the_beyond",
        name="Sage of the Beyond",
        oracle_text=LINE,
        types=["Creature"],
        mana_cost=ManaCost.parse("{5}{U}"),
        foretell=ManaCost.parse(foretell) if foretell else None,
    )


class TestTheResidualGate:
    def test_the_line_is_claimed_by_the_matching_cost(self):
        assert _covered(_sage("{4}{U}"), LINE)

    def test_the_bare_line_is_claimed_too(self):
        assert _covered(_sage("{4}{U}"), "Foretell {4}{U}")

    def test_a_cheaper_cost_is_not_claimed(self):
        assert not _covered(_sage("{1}{U}"), LINE)

    def test_a_card_without_foretell_cannot_claim_it(self):
        assert not _covered(_sage(None), LINE)
