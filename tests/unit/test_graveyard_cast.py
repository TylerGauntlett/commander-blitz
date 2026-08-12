"""Escape and jump-start: casting from the graveyard, generalised past flashback.

`docs/keywords.md` grouped flashback, escape, jump-start, embalm, unearth and
disturb as one cluster waiting on "casting from the graveyard, generalised past
`retrace`". Three of those shipped separately, and the interesting result of
looking at what was left is how little of it there was.

**Jump-start needed nothing at all.** "Cast this from your graveyard by
discarding a card in addition to paying its other costs, then exile it" is a
graveyard cost whose mana half happens to equal the printed cost, plus a
discard, plus the exile rider flashback already had. It was expressible the day
flashback shipped and nobody noticed, because it was filed under a different
keyword.

**Escape needed exactly one bit.** Same alternative cost, same legality
widening, same `exile_from_graveyard` cost kind -- and one difference: the card
comes back. Escape is reusable and flashback is not, and that whole distinction
is where the spell goes when it finishes.

So the generalisation is a destination and a rename. `graveyard_cost` is the
field's real name, `flashback` stays as the spelling the first keyword shipped
under, and `graveyard_cast` says where the card goes. Giving both names at once
is refused rather than resolved, because a card with two prices from the
graveyard has no answer to what it costs from there.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.errors import DslError
from tests.conftest import _default_answer

ESCAPIST = "t_escapist"  # {2}{R} instant, 2 damage; escape {1}{R} + exile two
JUMPSTART = "t_jumpstarter"  # {2}{U} sorcery, draw two; jump-start
FLASHBACK = "deep_analysis"  # the shipped witness for the old spelling


def cast_from_graveyard(game, card_id: str, pid: int = 0):
    """Find and apply the cast of a card sitting in a graveyard."""
    for action in game.legal_actions():
        if action.kind is not ActionKind.CAST or action.source is None:
            continue
        obj = game.state.objects.get(action.source)
        if obj is not None and obj.def_id == card_id and obj.zone is Zone.GRAVEYARD:
            game.apply(action)
            return action
    raise AssertionError(
        f"no cast of {card_id} from the graveyard; legal: "
        f"{[a.label for a in game.legal_actions()]}"
    )


def settle(game, limit: int = 40) -> None:
    """Finish the cast, including the decisions its *cost* raises.

    `pass_until(not stack)` cannot be used: escape pays by exiling cards the
    player chooses, so the cast stops on a `choose_objects` decision *before*
    the spell is ever pushed. The stack is empty at that moment, so a predicate
    watching the stack returns immediately and nothing has happened at all.
    """
    for _ in range(limit):
        decision = game.pending()
        # Cost and effect decisions first, always. Waiting for `pending()` to
        # go None instead would never return: once the spell has resolved there
        # is still a priority decision sitting there, forever.
        if decision is not None and decision.kind is not DecisionKind.PRIORITY:
            game.apply(_default_answer(game, decision))
            continue
        if not game.state.stack and not game.state.pending_triggers:
            return
        if decision is None:
            game._advance()
        else:
            game.apply(_default_answer(game, decision))
    raise AssertionError("the spell never finished resolving")


def total_life(game) -> int:
    """Both seats. The escapist targets "any player", and which one the
    enumeration offers first is not the claim under test."""
    return sum(p.life for p in game.state.players)


def zone_of(game, card_id: str) -> Zone:
    (obj,) = [o for o in game.state.objects.values() if o.def_id == card_id]
    return obj.zone


def escape_position(builder, *, fodder: int = 3, lands: int = 3):
    """The escapist in the graveyard, with cards to exile and mana to pay."""
    return (
        builder(players=2)
        .graveyard(0, [ESCAPIST] + ["t_bear"] * fodder)
        .battlefield(0, ["mountain"] * lands)
        .build()
    )


class TestEscape:
    def test_it_is_castable_from_the_graveyard(self, builder):
        game = escape_position(builder)
        before = total_life(game)
        cast_from_graveyard(game, ESCAPIST)
        settle(game)
        assert total_life(game) == before - 2

    def test_it_pays_by_exiling_other_cards(self, builder):
        game = escape_position(builder)
        before = len(game.state.players[0].graveyard)
        cast_from_graveyard(game, ESCAPIST)
        settle(game)
        # Two exiled as the cost, and the spell itself left the graveyard to be
        # cast -- then came back, which is the next test.
        assert len(game.state.players[0].exile) == 2
        assert before - len(game.state.players[0].graveyard) == 2

    def test_it_goes_back_to_the_graveyard(self, builder):
        """The whole difference from flashback, and the reason escape is a
        card you build a deck around."""
        game = escape_position(builder)
        cast_from_graveyard(game, ESCAPIST)
        settle(game)
        assert zone_of(game, ESCAPIST) is Zone.GRAVEYARD, (
            "escape is reusable; exiling it here would make it flashback"
        )

    def test_it_can_be_cast_again(self, builder):
        """The claim behind the previous one, made in play."""
        # Six lands, not three: the mana for the first cast is spent and does
        # not untap in the same turn, so a second escape needs its own.
        game = escape_position(builder, fodder=5, lands=6)
        before = total_life(game)
        cast_from_graveyard(game, ESCAPIST)
        settle(game)
        assert total_life(game) == before - 2
        cast_from_graveyard(game, ESCAPIST)
        settle(game)
        assert total_life(game) == before - 4, "the same card, cast twice"

    def test_without_enough_fodder_it_is_not_offered(self, builder):
        """The boundary: the exile cost is a real cost, not decoration."""
        game = escape_position(builder, fodder=1)
        with pytest.raises(AssertionError):
            cast_from_graveyard(game, ESCAPIST)


class TestJumpStart:
    def test_it_is_castable_from_the_graveyard_by_discarding(self, builder):
        game = (
            builder(players=2)
            .graveyard(0, [JUMPSTART])
            .hand(0, ["t_bear"])
            .battlefield(0, ["island", "island", "island"])
            .build()
        )
        cast_from_graveyard(game, JUMPSTART)
        settle(game)
        assert len(game.state.players[0].hand) == 2, "discarded one, drew two"

    def test_it_exiles_afterwards(self, builder):
        """Once only -- the rider flashback already had."""
        game = (
            builder(players=2)
            .graveyard(0, [JUMPSTART])
            .hand(0, ["t_bear"])
            .battlefield(0, ["island", "island", "island"])
            .build()
        )
        cast_from_graveyard(game, JUMPSTART)
        settle(game)
        assert zone_of(game, JUMPSTART) is Zone.EXILE

    def test_with_an_empty_hand_it_is_not_offered(self, builder):
        game = (
            builder(players=2)
            .graveyard(0, [JUMPSTART])
            .battlefield(0, ["island", "island", "island"])
            .build()
        )
        with pytest.raises(AssertionError):
            cast_from_graveyard(game, JUMPSTART)


class TestFlashbackIsUnchanged:
    def test_a_flashback_card_still_exiles(self, registry):
        """The rename is a rename. `graveyard_cast` defaults to exile, so every
        card written against the old spelling behaves exactly as before."""
        card = registry.get(FLASHBACK)
        assert card.flashback is not None
        assert card.graveyard_cast_exiles


class TestTheLoaderGuardsTheNewField:
    def base(self, **extra) -> dict:
        return {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "Draw a card.",
            "mana_cost": "{1}{U}",
            "types": ["Sorcery"],
            "spell_effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
            **extra,
        }

    def test_both_names_at_once_are_refused(self):
        with pytest.raises(DslError, match="not both"):
            compile_card(
                CardModel.model_validate(
                    self.base(
                        flashback={"mana": "{U}"},
                        graveyard_cost={"mana": "{2}{U}"},
                    )
                )
            )

    def test_a_destination_with_no_cost_is_refused(self):
        """Otherwise a card claims to escape and is never castable at all."""
        with pytest.raises(DslError, match="needs a 'graveyard_cost'"):
            compile_card(CardModel.model_validate(self.base(graveyard_cast="graveyard")))

    def test_a_graveyard_cost_still_needs_mana(self):
        with pytest.raises(DslError, match="needs mana"):
            compile_card(
                CardModel.model_validate(self.base(graveyard_cost={"pay_life": 3}))
            )

    def test_the_new_name_compiles(self):
        card = compile_card(
            CardModel.model_validate(
                self.base(graveyard_cost={"mana": "{2}{U}"}, graveyard_cast="graveyard")
            )
        )
        assert card.flashback is not None
        assert not card.graveyard_cast_exiles
