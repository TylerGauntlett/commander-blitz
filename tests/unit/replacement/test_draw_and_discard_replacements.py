"""Dredge, madness and miracle — the replacements that stop to ask.

Every replacement the engine had before these is applied synchronously and asks
nothing: enters tapped, enters with counters, the commander zone change, tokens
ceasing to exist. That is why they live in a whitelist and are applied inline.

These three cannot be, and the census was right that they cluster — but wrong
about what the cluster was waiting on. It is **not** the whitelist. It is that
drawing and discarding had to become things that can *suspend*, and the reason
that turned out to be tractable is that `turn.begin_step` was already run
through `Game._run`: the turn structure could carry a decision all along, and
only `_draw_step` beneath it could not.

`primitives.draw_cards` and `discard_cards` still ask nothing — that module's
contract is intact — and `engine/replacements.py` wraps them.

The three details worth pinning are the ones a plausible implementation gets
wrong without any board showing it:

- **Dredge replaces the draw.** The card comes back and *no card is drawn*, so a
  player who dredges into an empty library has not decked themselves.
- **Madness exiles whether or not you cast.** A declined madness card is in
  exile, not the graveyard — written the other way round every madness card
  would be a free graveyard-filler.
- **Miracle is the first card drawn this turn**, read *before* the draw bumps
  the tally, and it is offered however the card was drawn.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.replacements import discard as discard_with_replacements
from automtg.engine.replacements import draw as draw_with_replacements
from tests.conftest import _default_answer, only_oid

SWAMP = "swamp"
MOUNTAIN = "mountain"
PLAINS = "plains"
TROLL = "t_dredger"        # dredge 3
BOLT = "t_madness"         # {2}{R}, madness {R}
WRATH = "t_miracle"        # {4}{W}{W}, miracle {W}
BEAR = "t_bear"


def drive(game, gen, *, yes: bool = True, pick: bool = True):
    """Run one replacement generator, answering each question the same way."""
    send = None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration as stop:
            return stop.value
        if decision.kind is ActionKind.__class__:  # pragma: no cover - defensive
            raise AssertionError(decision)
        if decision.min_count == 1 and decision.max_count == 1 and len(decision.options) == 2:
            send = [0] if yes else [1]      # a yes/no
        else:
            send = [0] if pick else []      # a subset


class TestDredge:
    def _board(self, builder, library: int = 10):
        game = (
            builder(players=2)
            .battlefield(0, [SWAMP] * 3)
            .graveyard(0, [TROLL])
            .library(0, [SWAMP] * library)
            .build(advance=False)
        )
        return game, game.state.players[0].graveyard[0]

    def test_taking_it_returns_the_card_and_mills(self, builder):
        game, troll = self._board(builder)
        before = len(game.state.players[0].library)

        drive(game, draw_with_replacements(game.state, 0, 1), pick=True)

        assert game.state.objects[troll].zone is Zone.HAND
        assert len(game.state.players[0].library) == before - 3, "milled three"

    def test_no_card_is_drawn(self, builder):
        """It *replaces* the draw. Drawing as well would be a free card."""
        game, _ = self._board(builder)

        drive(game, draw_with_replacements(game.state, 0, 1), pick=True)

        drawn = [o for o in game.state.players[0].hand]
        assert len(drawn) == 1, "only the dredged card"
        assert game.state.objects[drawn[0]].def_id == TROLL

    def test_declining_draws_normally(self, builder):
        game, troll = self._board(builder)
        before = len(game.state.players[0].library)

        drive(game, draw_with_replacements(game.state, 0, 1), pick=False)

        assert game.state.objects[troll].zone is Zone.GRAVEYARD
        assert len(game.state.players[0].library) == before - 1

    def test_it_is_not_offered_with_too_few_cards_left(self, builder):
        """702.51a: the mill is the price, and a player who cannot pay is not asked."""
        game, troll = self._board(builder, library=2)

        gen = draw_with_replacements(game.state, 0, 1)
        asked = []
        send = None
        while True:
            try:
                asked.append(gen.send(send))
            except StopIteration:
                break
            send = []
        assert asked == [], "no question at all"
        assert game.state.objects[troll].zone is Zone.GRAVEYARD

    def test_dredging_into_an_empty_library_does_not_deck_you(self, builder):
        """The point of "replaces": nothing was drawn, so 104.3c never fires."""
        game, _ = self._board(builder, library=3)

        drive(game, draw_with_replacements(game.state, 0, 1), pick=True)

        assert game.state.players[0].library == []
        assert not game.state.players[0].attempted_draw_from_empty


class TestMadness:
    def _board(self, builder, lands: int = 1):
        game = (
            builder(players=2)
            .battlefield(0, [MOUNTAIN] * lands)
            .hand(0, [BOLT])
            .library(0, [MOUNTAIN] * 10)
            .build(advance=False)
        )
        return game, game.state.players[0].hand[0]

    def test_it_is_exiled_rather_than_binned(self, builder):
        game, bolt = self._board(builder)

        drive(game, discard_with_replacements(game.state, 0, [bolt]), yes=False)

        assert game.state.objects[bolt].zone is Zone.EXILE

    def test_declining_still_exiles_it(self, builder):
        """The half a naive version drops -- it must not reach the graveyard."""
        game, bolt = self._board(builder)

        drive(game, discard_with_replacements(game.state, 0, [bolt]), yes=False)

        assert game.state.objects[bolt].zone is not Zone.GRAVEYARD

    def test_accepting_puts_it_on_the_stack(self, builder):
        game, bolt = self._board(builder)

        drive(game, discard_with_replacements(game.state, 0, [bolt]), yes=True)

        assert [item.oid for item in game.state.stack] == [bolt]

    def test_it_is_cast_for_the_madness_cost(self, builder):
        """One Mountain: {R} is payable and the printed {2}{R} is not."""
        game, bolt = self._board(builder, lands=1)

        drive(game, discard_with_replacements(game.state, 0, [bolt]), yes=True)

        assert game.state.stack, "the one Mountain paid for it"
        assert all(o.tapped for o in game.state.battlefield_objects(0))

    def test_a_card_without_madness_is_binned_as_usual(self, builder):
        game = (
            builder(players=2)
            .hand(0, [BEAR])
            .library(0, [MOUNTAIN] * 10)
            .build(advance=False)
        )
        bear = game.state.players[0].hand[0]

        drive(game, discard_with_replacements(game.state, 0, [bear]))

        assert game.state.objects[bear].zone is Zone.GRAVEYARD


class TestMiracle:
    def _board(self, builder, lands: int = 1, drawn_already: int = 0):
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS] * lands)
            .battlefield(0, [BEAR])
            .library(0, [WRATH] + [PLAINS] * 10)
            .build(advance=False)
        )
        game.state.cards_drawn_this_turn[0] = drawn_already
        return game

    def test_the_first_card_drawn_offers_the_cast(self, builder):
        game = self._board(builder)
        drive(game, draw_with_replacements(game.state, 0, 1), yes=True)

        assert game.state.stack, "cast for {W}"

    def test_a_later_draw_does_not(self, builder):
        """"…if it's the first card you drew this turn." Read before the tally bumps."""
        game = self._board(builder, drawn_already=1)

        gen = draw_with_replacements(game.state, 0, 1)
        asked = []
        send = None
        while True:
            try:
                asked.append(gen.send(send))
            except StopIteration:
                break
            send = [1]
        assert asked == []
        assert not game.state.stack

    def test_declining_leaves_it_in_hand(self, builder):
        game = self._board(builder)
        drive(game, draw_with_replacements(game.state, 0, 1), yes=False)

        wrath = next(
            o for o in game.state.players[0].hand if game.state.objects[o].def_id == WRATH
        )
        assert game.state.objects[wrath].zone is Zone.HAND
        assert not game.state.stack

    def test_it_is_not_offered_without_the_mana(self, builder):
        game = self._board(builder, lands=0)

        gen = draw_with_replacements(game.state, 0, 1)
        asked = []
        send = None
        while True:
            try:
                asked.append(gen.send(send))
            except StopIteration:
                break
            send = [1]
        assert asked == [], "rule 118.4 -- a cost that cannot be paid is not offered"


class TestThroughTheTurnStructure:
    def test_the_draw_step_offers_a_miracle(self, builder):
        """The whole reason `_draw_step` became a generator."""
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS])
            .library(0, [WRATH] + [PLAINS] * 20)
            .library(1, [PLAINS] * 20)
            .build()
        )
        for _ in range(400):
            decision = game.pending()
            if decision is None:
                break
            if any(a.kind is ActionKind.YES for a in game.legal_actions()):
                assert game.state.step is Step.DRAW
                return
            game.apply(_default_answer(game, decision))
        raise AssertionError("the miracle was never offered")

    def test_the_cleanup_discard_offers_madness(self, builder):
        """Rule 702.35a does not care why the card was discarded."""
        game = (
            builder(players=2)
            .battlefield(0, [MOUNTAIN])
            .hand(0, [BOLT] + [MOUNTAIN] * 7)
            .library(0, [MOUNTAIN] * 20)
            .library(1, [MOUNTAIN] * 20)
            .build()
        )
        bolt = next(
            o for o in game.state.players[0].hand if game.state.objects[o].def_id == BOLT
        )
        for _ in range(600):
            decision = game.pending()
            if decision is None:
                break
            if (
                decision.kind.value == "choose_objects"
                and decision.context.get("purpose") == "discard"
            ):
                choose = next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE
                    and bolt in [t.id for t in a.targets]
                )
                game.apply(choose)
                continue
            game.apply(_default_answer(game, decision))
            if game.state.objects[bolt].zone is Zone.EXILE:
                return
        assert game.state.objects[bolt].zone is Zone.EXILE, "madness exiled it"


class TestTheOpeningHandIsNotRoutedThroughThis:
    def test_seven_cards_arrive_with_no_questions(self, builder):
        """Rule 103: no graveyard to dredge from and no turn to be first in."""
        game = (
            builder(players=2)
            .library(0, [WRATH] * 20)
            .library(1, [PLAINS] * 20)
            .build()
        )
        assert only_oid is not None
        assert not any(
            e.type == "spell_cast" for e in game.state.events[:20]
        ), "nothing was miracled out of the opening hand"
