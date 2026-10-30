"""`grant_miracle` -- miracle handed to cards in a hand by another permanent.

Witness: Molecule Man, "Nonland cards in your hand have miracle {0}." Rule
702.94a: miracle lets a player reveal the card *as it is drawn*, if it is the
first card they drew this turn, and cast it for the miracle cost. A granted
miracle is the same ability, so it is read by the same draw-time offer
(`replacements._miracle`) with the card already in hand -- the static must be
active then, and it reaches only its controller's hand.

Without this the offer read `card.miracle` alone, so a card that prints no
miracle was never offered one, whatever was on the battlefield. The near miss is
`grant_warp`/`granted_alternative_cost`: those are prices offered at any cast,
and a miracle cost is offered once, at the draw, and never again.

A card with its own miracle beside a granted one has two miracle abilities;
each is offered in turn, printed first, and one cast ends it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import AbilityModel, CardModel
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.replacements import draw as draw_with_replacements

GRANTER = "t_miracle_granter"  # Nonland cards in your hand have miracle {0}.
BEAR = "t_bear"                # {1}{G} creature, no miracle printed
WRATH = "t_miracle"            # {4}{W}{W}, miracle {W}
PLAINS = "plains"


def run(game, pid: int, answers: list[bool]) -> list:
    """Draw one card for ``pid``, answering yes/no questions in order; return them."""
    gen = draw_with_replacements(game.state, pid, 1)
    asked = []
    send = None
    queue = list(answers)
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return asked
        asked.append(decision)
        send = [0] if (queue.pop(0) if queue else False) else [1]


def position(builder, *, top: str, granter_seat: int | None = 0, drawn_already: int = 0,
             lands: int = 0, drawer: int = 0):
    b = builder(players=2)
    if granter_seat is not None:
        b = b.battlefield(granter_seat, [GRANTER])
    if lands:
        b = b.battlefield(drawer, [PLAINS] * lands)
    game = (
        b.library(drawer, [top] + [PLAINS] * 10)
        .library(1 - drawer, [top] + [PLAINS] * 10)
        .build(advance=False)
    )
    game.state.cards_drawn_this_turn[drawer] = drawn_already
    return game


def on_stack(game, def_id: str) -> bool:
    return any(item.kind == "spell" and item.def_id == def_id for item in game.state.stack)


class TestTheGrantOffersMiracle:
    def test_a_nonland_card_drawn_first_is_cast_for_zero(self, builder):
        game = position(builder, top=BEAR)
        asked = run(game, 0, [True])

        assert len(asked) == 1, "one miracle offer"
        assert on_stack(game, BEAR), "cast for {0} with no lands on the board"

    def test_declining_leaves_it_in_hand(self, builder):
        game = position(builder, top=BEAR)
        run(game, 0, [False])

        assert not game.state.stack
        assert any(game.state.objects[o].def_id == BEAR for o in game.state.players[0].hand)


class TestTheGrantsScope:
    def test_a_second_draw_is_not_offered(self, builder):
        """"…if it's the first card you drew this turn." The grant does not widen that."""
        game = position(builder, top=BEAR, drawn_already=1)
        assert run(game, 0, [True]) == []
        assert not game.state.stack

    def test_a_land_is_not_offered(self, builder):
        game = position(builder, top=PLAINS)
        assert run(game, 0, [True]) == []

    def test_without_the_granter_nothing_is_offered(self, builder):
        game = position(builder, top=BEAR, granter_seat=None)
        assert run(game, 0, [True]) == []

    def test_an_opponents_draw_is_unaffected(self, builder):
        """"…in **your** hand": the granter's controller only."""
        game = position(builder, top=BEAR, granter_seat=0, drawer=1)
        assert run(game, 1, [True]) == []
        assert not game.state.stack

    def test_an_opponents_granter_gives_you_nothing(self, builder):
        game = position(builder, top=BEAR, granter_seat=1, drawer=0)
        assert run(game, 0, [True]) == []


class TestPrintedAndGrantedMiracle:
    def test_the_granted_cost_is_offered_when_the_printed_one_cannot_be_paid(self, builder):
        """Miracle {W} with no white mana: the granted {0} is still a miracle ability."""
        game = position(builder, top=WRATH)
        asked = run(game, 0, [True])

        assert len(asked) == 1
        assert on_stack(game, WRATH)

    def test_declining_the_printed_cost_still_offers_the_granted_one(self, builder):
        game = position(builder, top=WRATH, lands=1)
        asked = run(game, 0, [False, True])

        assert len(asked) == 2, "printed {W}, then granted {0}"
        assert on_stack(game, WRATH)
        plains = [o for o in game.state.battlefield
                  if game.state.objects[o].def_id == PLAINS]
        assert plains and not any(game.state.objects[o].tapped for o in plains), (
            "cast for the granted {0}, not the printed {W}"
        )

    def test_one_cast_ends_the_offers(self, builder):
        game = position(builder, top=WRATH, lands=1)
        asked = run(game, 0, [True, True])
        assert len(asked) == 1


class TestTheLoaderRefusesTheSilentFailures:
    """Each of these would load clean and grant miracle the card does not print."""

    def _card(self, **grant):
        base = dict(
            kind="static",
            text="x",
            effect="grant_miracle",
            affects_player="you",
            miracle_cost="{0}",
            affects_spells={"not_types": ["Land"]},
        )
        base.update(grant)
        return CardModel(
            id="t_bad", name="Bad", mana_cost="{3}", types=["Creature"],
            power=1, toughness=1, abilities=[AbilityModel(**base)],
        )

    def test_the_well_formed_grant_loads(self):
        compile_card(self._card())

    def test_a_grant_with_no_filter_is_refused(self):
        with pytest.raises(DslError, match="affects_spells"):
            compile_card(self._card(affects_spells=None))

    def test_a_grant_with_no_price_is_refused(self):
        with pytest.raises(DslError, match="miracle_cost"):
            compile_card(self._card(miracle_cost=None))

    def test_a_filter_that_reads_board_state_is_refused(self):
        with pytest.raises(DslError, match="tapped"):
            compile_card(self._card(affects_spells={"tapped": True}))
