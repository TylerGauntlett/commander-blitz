"""`link` on `look_at_top`: cards exiled off the top remember who exiled them.

    Ashiok, Nightmare Weaver — "+2: Exile the top three cards of target
    opponent's library." … "-X: Put a creature card with mana value X exiled
    with Ashiok onto the battlefield under your control."

The -X is a *later* activation, so the only thing that can find "a card exiled
with Ashiok" is the `exiled_by` record a `{"zone": "exile", "exiled_with":
"self"}` selector reads. The `exile` op writes it under `link`; `look_at_top`
never did, on purpose -- writing it unasked would strand Florian's declined
cards in exile -- so the +2 exiled three cards nothing could ever name again.

The claims: with `link` the exiled cards carry the source and the selector finds
them; without it nothing is recorded (the Florian guarantee holds); and the
loader refuses `link` anywhere but an exile destination, where it would load
and link nothing.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import resolve_pool
from automtg.engine.enums import Step, Zone
from automtg.engine.errors import DslError

EXILE_TOP_THREE = {
    "op": "look_at_top",
    "amount": 3,
    "objects": {"count": 3},
    "destination": "exile",
}


def a_board(builder):
    game = (
        builder(players=2)
        .battlefield(0, ["t_bear"])
        .library(0, ["t_bear", "island", "forest", "island", "island"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    source = game.state.battlefield[0]
    top = list(game.state.players[0].library[:3])
    return game, source, top


def run(game, source, spec):
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    gen = execute(ctx, [spec])
    try:
        decision = next(gen)
        while True:
            decision = gen.send(list(range(decision.max_count)))
    except StopIteration:
        pass
    return ctx


class TestALinkedExileRemembersItsSource:
    def test_the_three_cards_are_exiled_with_the_source(self, builder):
        game, source, top = a_board(builder)
        run(game, source, {**EXILE_TOP_THREE, "link": True})
        for oid in top:
            assert game.state.objects[oid].zone is Zone.EXILE
            assert game.state.objects[oid].exiled_by == source

    def test_exiled_with_self_finds_exactly_them(self, builder):
        game, source, top = a_board(builder)
        ctx = run(game, source, {**EXILE_TOP_THREE, "link": True})
        found = resolve_pool(ctx, {"zone": "exile", "exiled_with": "self"})
        assert sorted(found) == sorted(top)


class TestWithoutTheKeyNothingIsRecorded:
    def test_an_unlinked_look_writes_no_record(self, builder):
        game, source, top = a_board(builder)
        ctx = run(game, source, EXILE_TOP_THREE)
        assert all(game.state.objects[oid].exiled_by is None for oid in top)
        assert resolve_pool(ctx, {"zone": "exile", "exiled_with": "self"}) == []


class TestTheLoaderGuard:
    def _card(self, effect):
        return CardModel.model_validate(
            {
                "id": "t_link_probe",
                "name": "Test Link Probe",
                "oracle_text": "Exile the top three cards of your library.",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )

    def test_link_on_exile_loads(self):
        compile_card(self._card({**EXILE_TOP_THREE, "link": True}))

    def test_link_anywhere_else_is_refused(self):
        with pytest.raises(DslError, match="link"):
            compile_card(self._card({**EXILE_TOP_THREE, "destination": "hand", "link": True}))

    def test_link_is_a_flag(self):
        with pytest.raises(DslError, match="link"):
            compile_card(self._card({**EXILE_TOP_THREE, "link": "yes"}))
