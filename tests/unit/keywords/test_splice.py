"""Splice — the only keyword that changes what a *different* card does.

    "Splice onto Arcane {1}{W} (As you cast an Arcane spell, you may reveal this
    card from your hand and pay its splice cost. If you do, add this card's
    effects to that spell.)"

Every other cost in the engine belongs to the card that prints it. Splice is
paid out of one card to alter another, as that other one goes on the stack — so
it is offered in `Game._cast`, between the host's own costs and `push_spell`,
which is exactly where the printed line puts it.

Three properties, each of which a naive version loses:

- **The card is revealed, not spent.** It stays in hand and can be spliced again
  next turn. Discarding or exiling it is the obvious shortcut and it deletes the
  whole economy of the mechanic.
- **The effects belong to the host spell.** They run through the same
  `EffectContext` after the host's own, which is what makes them one spell
  rather than two — countering the host stops all of it.
- **Only the named subtype.** `splice_onto` is checked against the host's
  subtypes, so a Rite cannot be spliced onto an ordinary instant.

A spliced card may not declare its own targets, and the loader refuses one. Its
effects run in the host's context, so a target id written there would either be
missing or — worse — collide with one of the host's and quietly point somewhere
else. Recorded as a divergence rather than approximated.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer, action_for_card, pass_until

PLAINS = "plains"
ARCANE = "t_arcane"          # {W} Arcane instant, gain 1
SPLICER = "t_splicer"        # {2}{W} Arcane instant, gain 3, splice {1}{W}
PLAIN = "t_plain_instant"    # {W} instant, gain 1, not Arcane


def position(builder, host: str, lands: int = 6):
    return (
        builder(players=2)
        .battlefield(0, [PLAINS] * lands)
        .hand(0, [host, SPLICER])
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .build()
    )


def cast_host(game, host: str, *, splice: bool):
    game.apply(action_for_card(game, ActionKind.CAST, host))
    for _ in range(60):
        decision = game.pending()
        if decision is None:
            break
        want = ActionKind.YES if splice else ActionKind.NO
        offer = [a for a in game.legal_actions() if a.kind is want]
        if offer and decision.kind.value == "may":
            game.apply(offer[0])
            continue
        if not game.state.stack:
            break
        game.apply(_default_answer(game, decision))
    pass_until(game, lambda g: g.pending() is None or not g.state.stack)


class TestTheOffer:
    def test_an_arcane_host_offers_the_splice(self, builder):
        game = position(builder, ARCANE)
        game.apply(action_for_card(game, ActionKind.CAST, ARCANE))

        decision = game.pending()
        assert decision is not None and decision.kind.value == "may"
        assert "Splice" in decision.prompt

    def test_a_non_arcane_host_does_not(self, builder):
        """`splice_onto` is checked against the host's subtypes."""
        game = position(builder, PLAIN)
        game.apply(action_for_card(game, ActionKind.CAST, PLAIN))

        decision = game.pending()
        assert decision is None or decision.kind.value != "may"

    def test_it_is_not_offered_without_the_splice_cost(self, builder):
        game = position(builder, ARCANE, lands=1)
        game.apply(action_for_card(game, ActionKind.CAST, ARCANE))

        decision = game.pending()
        assert decision is None or decision.kind.value != "may"


class TestWhatItDoes:
    def test_the_spliced_effects_run(self, builder):
        game = position(builder, ARCANE)
        life = game.state.players[0].life

        cast_host(game, ARCANE, splice=True)

        assert game.state.players[0].life == life + 4, "1 from the host, 3 spliced"

    def test_declining_runs_only_the_host(self, builder):
        game = position(builder, ARCANE)
        life = game.state.players[0].life

        cast_host(game, ARCANE, splice=False)

        assert game.state.players[0].life == life + 1

    def test_the_spliced_card_stays_in_hand(self, builder):
        """Revealed, not spent -- the whole economy of the mechanic."""
        game = position(builder, ARCANE)
        splicer = next(
            o for o in game.state.players[0].hand
            if game.state.objects[o].def_id == SPLICER
        )

        cast_host(game, ARCANE, splice=True)

        assert game.state.objects[splicer].zone is Zone.HAND

    def test_only_the_host_goes_to_the_graveyard(self, builder):
        game = position(builder, ARCANE)
        cast_host(game, ARCANE, splice=True)

        graveyard = [
            game.state.objects[o].def_id for o in game.state.players[0].graveyard
        ]
        assert graveyard == [ARCANE]


class TestTheLoaderGuard:
    def test_a_spliced_card_may_not_target(self):
        """Its effects run in the host's context, so a target id there is a lie."""
        card = CardModel.model_validate(
            {
                "id": "t_splice_probe",
                "name": "Splice Probe",
                "mana_cost": "{2}{W}",
                "types": ["Instant"],
                "subtypes": ["Arcane"],
                "splice": "{1}{W}",
                "targets": [
                    {
                        "id": "t1",
                        "kind": "permanent",
                        "count": 1,
                        "selector": {"zone": "battlefield", "types": ["Creature"]},
                    }
                ],
                "spell_effects": [{"op": "draw", "player": "you"}],
            }
        )
        with pytest.raises(DslError, match="may not declare its own targets"):
            compile_card(card)
