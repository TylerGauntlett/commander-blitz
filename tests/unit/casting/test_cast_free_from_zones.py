"""A free cast offered from more than one zone at once.

Kaya the Inexorable's emblem: "At the beginning of your upkeep, you may cast a
legendary spell from your hand, from your graveyard, or from among cards you own
in exile without paying its mana cost."

`cast_from_hand` already made the one-card free cast out of a hand, as an
optional choice at resolution. The emblem is the same choice over a wider pool:
one spell, picked from the union of three zones. It is one choice, not three
chances. Three `cast_from_hand`-shaped ops would each offer a spell, so a
player with a legend in each zone would cast three.

So the op takes `zones`, defaulting to `["hand"]` so no shipped card moved. The
exile half is **cards you own** in exile, which is the exile list the engine
keeps per owner. A legend an opponent owns that happens to be in exile is not
offered, and neither is a land, for `cast_from_hand`'s reason (305.9).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import pass_until

KAYA = {
    "op": "cast_from_hand",
    "zones": ["hand", "graveyard", "exile"],
    "selector": {"supertypes": ["Legendary"]},
}


def a_table(builder, *, hand=(), graveyard=(), exiled=(), their_exiled=()):
    """Player 0 with lands, the given cards in hand and graveyard, and ``exiled``
    moved from their graveyard into exile; ``their_exiled`` is player 1's."""
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * 3)
        .hand(0, list(hand))
        .graveyard(0, [*graveyard, *exiled])
        .graveyard(1, list(their_exiled))
        .build()
    )
    for pid, ids in ((0, exiled), (1, their_exiled)):
        for card_id in ids:
            oid = next(
                o
                for o in game.state.players[pid].graveyard
                if game.state.objects[o].def_id == card_id
            )
            move_object(game.state, oid, Zone.EXILE)
    return game


def offer(game, spec=KAYA, *, take: str | None = None) -> list[int]:
    """Resolve the op for player 0; return the oids offered, taking ``take`` if named."""
    ctx = EffectContext(state=game.state, controller=0)
    gen = OPS[spec["op"]](ctx, spec)
    offered: list[int] = []
    answer = None
    while True:
        try:
            decision = gen.send(answer)
        except StopIteration:
            break
        offered = [option.value for option in decision.options]
        wanted = [
            i
            for i, oid in enumerate(offered)
            if take is not None and game.state.objects[oid].def_id == take
        ]
        answer = wanted[:1]
    pass_until(game, lambda g: not g.state.stack)
    return offered


def ids(game, oids) -> set[str]:
    return {game.state.objects[oid].def_id for oid in oids}


class TestWhatIsOffered:
    def test_every_zone_is_one_pool(self, builder):
        game = a_table(builder, hand=["t_legend"], graveyard=["t_legend"], exiled=["t_legend"])
        offered = offer(game)
        zones = {game.state.objects[oid].zone for oid in offered}
        assert zones == {Zone.HAND, Zone.GRAVEYARD, Zone.EXILE}

    def test_only_legendary_spells(self, builder):
        game = a_table(builder, graveyard=["t_legend", "t_bear"])
        # One match is still a choice, because "you may" allows none.
        assert ids(game, offer(game)) == {"t_legend"}

    def test_not_a_card_an_opponent_owns_in_exile(self, builder):
        game = a_table(builder, graveyard=["t_legend"], their_exiled=["t_legend"])
        offered = offer(game)
        assert [game.state.objects[oid].owner for oid in offered] == [0]

    def test_the_default_is_still_the_hand(self, builder):
        game = a_table(builder, hand=["t_legend"], graveyard=["t_legend"])
        offered = offer(game, {k: v for k, v in KAYA.items() if k != "zones"})
        assert {game.state.objects[oid].zone for oid in offered} == {Zone.HAND}


class TestTheCast:
    def test_a_legend_is_cast_out_of_the_graveyard(self, builder):
        game = a_table(builder, graveyard=["t_legend"])
        offer(game, take="t_legend")
        assert any(
            game.state.objects[oid].def_id == "t_legend" for oid in game.state.battlefield
        )

    def test_a_legend_is_cast_out_of_exile(self, builder):
        game = a_table(builder, exiled=["t_legend"])
        offer(game, take="t_legend")
        assert any(
            game.state.objects[oid].def_id == "t_legend" for oid in game.state.battlefield
        )

    def test_declining_casts_nothing(self, builder):
        game = a_table(builder, graveyard=["t_legend"])
        offer(game, take=None)
        assert not any(
            game.state.objects[oid].def_id == "t_legend" for oid in game.state.battlefield
        )


class TestTheLoaderGuards:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_free_caster",
                "name": "Test Free Caster",
                "mana_cost": "{2}",
                "types": ["Sorcery"],
                "oracle_text": "You may cast a legendary spell from your hand, from your "
                "graveyard, or from among cards you own in exile without paying its mana cost.",
                "spell_effects": [effect],
            }
        )

    def test_the_three_zone_form_loads(self):
        compile_card(self._card(KAYA))

    def test_a_zone_nothing_is_cast_from_is_refused(self):
        with pytest.raises(DslError, match="zones"):
            compile_card(self._card({**KAYA, "zones": ["hand", "battlefield"]}))

    def test_an_empty_list_is_refused(self):
        with pytest.raises(DslError, match="zones"):
            compile_card(self._card({**KAYA, "zones": []}))
