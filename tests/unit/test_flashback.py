"""Flashback: an alternative cost from the graveyard, and a once-only rider.

"Flashback—{1}{U}, Pay 3 life. (You may cast this card from your graveyard for
its flashback cost. Then exile it.)" Deep Analysis and Increasing Devotion are
the shipped witnesses, and between them they need all three pieces.

`docs/rules-coverage.md` listed "flashback and other graveyard casting" under
Not implemented; that line is retired by this.

`retrace` is the near miss and is wrong in every particular. It is the only
field that widens legality to the graveyard, but it is a bare boolean whose cost
is hardcoded to a discarded land and charged *in addition* to the printed cost,
so it can name no alternative price at all — Increasing Devotion would cost
`{3}{W}{W}` plus a land instead of `{7}{W}{W}`. It is also deliberately
reusable, returning the card to the graveyard, which is the opposite of
flashback.

Three pieces, and the third does not fall out of the first two:

1. **The cost.** A full `Cost`, not a `ManaCost` like `evoke`, because Deep
   Analysis charges life as well. The mana half *replaces* the printed cost;
   everything else is an additional cost paid after it, exactly as
   `retrace_cost` is, and in the order rule 601.2g gives.

2. **The once-only rider.** "Then exile it." A spell cast this way goes to exile
   instead of the graveyard when it resolves *or* is countered/fizzles —
   otherwise it could be flashed back forever, which is a different card
   entirely and one that wins the game.

3. **`cast_from_graveyard`.** An engine could implement flashback casting
   perfectly and Increasing Devotion would still be wrong, making five tokens
   where it prints ten. `zone_is` cannot answer it: it reports the source's
   *current* zone, which for any resolving sorcery is the stack, identically
   whether it was cast from hand or from a graveyard. So it is a flag on the
   object, following the `cast_x` / `cast_kicked` / `cast_evoked` precedent —
   and set **before** `spell_effects` run, because that is when it is read.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.errors import DslError

ANALYSIS = "deep_analysis"  # {3}{U}; flashback {1}{U}, pay 3 life
DEVOTION = "increasing_devotion"  # {3}{W}{W}; flashback {7}{W}{W}


def table(builder, card: str, *, where: str, lands=10, land="island"):
    b = (
        builder(players=2)
        .battlefield(0, [land] * lands)
        .library(0, ["forest"] * 10)
        .active(0)
        .max_turns(1)
    )
    b = b.hand(0, [card]) if where == "hand" else b.graveyard(0, [card])
    return b.build()


def casts(game, card: str):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card
    ]


def resolve(game) -> None:
    for _ in range(20):
        decision = game.pending()
        if (
            decision is None
            or decision.kind is not DecisionKind.PRIORITY
            or not game.state.stack
        ):
            return
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))


def only(game, card: str) -> int:
    return next(o for o, obj in game.state.objects.items() if obj.def_id == card)


def tokens(game) -> int:
    return sum(1 for o in game.state.battlefield if game.state.objects[o].is_token)


class TestCastingFromTheGraveyard:
    def test_it_is_offered(self, builder):
        game = table(builder, ANALYSIS, where="graveyard")
        assert casts(game, ANALYSIS), "a graveyard is a third place a card is cast from"
        assert all(a.flashback for a in casts(game, ANALYSIS))

    def test_it_is_not_offered_without_the_life(self, builder):
        game = table(builder, ANALYSIS, where="graveyard")
        game.state.players[0].life = 2
        assert not casts(game, ANALYSIS), (
            "the life is part of the cost, so 2 life cannot pay 3"
        )

    def test_the_alternative_cost_replaces_the_printed_one(self, builder):
        # Two Islands: {1}{U} is payable, the printed {3}{U} is not.
        game = table(builder, ANALYSIS, where="graveyard", lands=2)
        assert casts(game, ANALYSIS)

    def test_and_the_life_is_actually_paid(self, builder):
        game = table(builder, ANALYSIS, where="graveyard")
        before = game.state.players[0].life
        game.apply(casts(game, ANALYSIS)[0])
        resolve(game)
        assert game.state.players[0].life == before - 3

    def test_the_spell_still_does_what_it_says(self, builder):
        game = table(builder, ANALYSIS, where="graveyard")
        before = len(game.state.players[0].hand)
        game.apply(casts(game, ANALYSIS)[0])
        resolve(game)
        assert len(game.state.players[0].hand) == before + 2


class TestTheOnceOnlyRider:
    def test_it_goes_to_exile_not_the_graveyard(self, builder):
        game = table(builder, ANALYSIS, where="graveyard")
        game.apply(casts(game, ANALYSIS)[0])
        resolve(game)
        assert game.state.objects[only(game, ANALYSIS)].zone is Zone.EXILE

    def test_so_it_cannot_be_flashed_back_twice(self, builder):
        game = table(builder, ANALYSIS, where="graveyard", lands=12)
        game.apply(casts(game, ANALYSIS)[0])
        resolve(game)
        assert not casts(game, ANALYSIS), (
            "reusable flashback is a different card, and one that wins the game"
        )

    def test_an_ordinary_cast_still_goes_to_the_graveyard(self, builder):
        game = table(builder, DEVOTION, where="hand", land="plains")
        game.apply(casts(game, DEVOTION)[0])
        resolve(game)
        assert game.state.objects[only(game, DEVOTION)].zone is Zone.GRAVEYARD, (
            "the rider is on the flashback cast only"
        )


class TestCastFromGraveyard:
    """The third piece, which does not fall out of the other two."""

    def test_from_hand_it_is_false(self, builder):
        game = table(builder, DEVOTION, where="hand", land="plains")
        game.apply(casts(game, DEVOTION)[0])
        resolve(game)
        assert tokens(game) == 5, "the printed five"

    def test_from_the_graveyard_it_is_true(self, builder):
        game = table(builder, DEVOTION, where="graveyard", land="plains")
        game.apply(casts(game, DEVOTION)[0])
        resolve(game)
        assert tokens(game) == 10, (
            "'create ten of those tokens instead' -- an engine with flashback "
            "casting but no way to ask this still makes five"
        )

    def test_the_flag_outlives_the_spell(self, builder):
        game = table(builder, DEVOTION, where="graveyard", land="plains")
        game.apply(casts(game, DEVOTION)[0])
        resolve(game)
        assert game.state.objects[only(game, DEVOTION)].cast_from_graveyard is True


def probe(**card) -> dict:
    base = {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "Draw a card.",
        "mana_cost": "{2}{U}",
        "types": ["Sorcery"],
        "spell_effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
    }
    base.update(card)
    return base


class TestTheLoader:
    def test_the_shipped_shape_loads(self):
        compile_card(CardModel.model_validate(probe(flashback={"mana": "{1}{U}", "pay_life": 3})))

    def test_a_flashback_cost_needs_mana(self):
        """Without it the card is castable from the graveyard for free."""
        with pytest.raises(DslError, match="needs mana"):
            compile_card(CardModel.model_validate(probe(flashback={"pay_life": 3})))

    def test_flashback_and_retrace_are_exclusive(self):
        """Both widen legality to the graveyard and each answers the price."""
        with pytest.raises(DslError, match="both 'flashback' and 'retrace'"):
            compile_card(
                CardModel.model_validate(
                    probe(flashback={"mana": "{1}{U}"}, retrace=True)
                )
            )

    def test_the_condition_needs_a_flashback_cost(self):
        """Otherwise it could never be true, and the card silently does less."""
        payload = probe(
            spell_effects=[
                {
                    "op": "if",
                    "condition": {"cast_from_graveyard": True},
                    "then": [{"op": "draw", "player": "you", "amount": {"const": 2}}],
                }
            ]
        )
        with pytest.raises(DslError, match="could never be true"):
            compile_card(CardModel.model_validate(payload))
