"""`playable_cost_reduction` -- "Spells you cast this way cost {2} less to cast."

    Urianger Augurelt, Play Arcanum -- "{T}: Until end of turn, you may play
    cards exiled with Urianger Augurelt. Spells you cast this way cost {2} less
    to cast."

"This way" names the permission, not a zone and not a permanent. The discount
reaches a spell only when it is cast *under* that grant (601.2f reduces the
cost of the spell being cast, whichever variant is paid), so it is a rider on
the grant -- `GameObject.playable_cost_reduction`, beside `playable_free` -- and
`casting.permission_cost_reduction` reads it on the lines that grant offers.

Each near miss is a different card. A `spell_cost_reduction` with
`from_zone: "exile"` discounts every exile cast, foretold and plotted cards and
other permissions included, and lasts while the permanent is out rather than
until end of turn. Dropping the clause makes Urianger strictly worse than
printed. And a card the same grant covers that is also castable some other way
-- flashback out of a graveyard the permission reaches -- pays full price on the
other lane, because that cast is not "this way".
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.casting import permission_cost_reduction
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import link_exiled, move_object
from tests.conftest import activations, only_oid, settle

ARCANUM = "t_pcr_arcanum"  # {T}: play cards exiled with this; {2} less
PLAIN = "t_pcr_plain_arcanum"  # the same permission, no discount
RECALL = "t_pcr_recall"  # {T}: cast target graveyard sorcery this turn; {2} less
HEIST = "t_pcr_heist"  # {R}: exile an opponent's artifact, cast it this turn; {2} less
RELIC = "t_czr_relic"  # {4} artifact
FLARE = "t_czr_flare"  # {3}{R} sorcery, flashback {3}{R}


def table(builder, *, board=(), exiled=(), graveyard=(), opp_graveyard=(), hand=(), lands=2):
    """Player 0's main phase with ``lands`` Mountains and ``board`` in play.

    ``exiled`` cards are moved to player 0's exile and linked to the first
    permanent on ``board`` -- what Draw Arcanum leaves behind. A Forest in hand
    keeps the priority window open when nothing else is affordable."""
    game = (
        builder(players=2)
        .battlefield(0, ["mountain"] * lands + list(board))
        .hand(0, [*hand, "forest"])
        .graveyard(0, list(graveyard) + list(exiled))
        .graveyard(1, list(opp_graveyard))
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .active(0)
        .max_turns(1)
        .build()
    )
    state = game.state
    if exiled:
        source = only_oid(game, board[0], 0)
        for oid in [o for o in state.players[0].graveyard if state.objects[o].def_id in exiled]:
            move_object(state, oid, Zone.EXILE)
            link_exiled(state, oid, source)
    return game


def activate(game, card_id: str) -> None:
    game.apply(activations(game, only_oid(game, card_id, 0))[0])
    settle(game)


def casts(game, def_id: str, *, flashback: bool | None = None) -> list:
    state = game.state
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and a.source is not None
        and state.objects[a.source].def_id == def_id
        and (flashback is None or a.flashback is flashback)
    ]


def tapped_mountains(game) -> int:
    state = game.state
    return sum(
        state.objects[oid].tapped
        for oid in state.battlefield
        if state.objects[oid].def_id == "mountain"
    )


def exiled_oid(game, def_id: str) -> int:
    state = game.state
    return next(
        oid
        for p in state.players
        for oid in p.exile
        if state.objects[oid].def_id == def_id
    )


class TestSpellsCastThisWay:
    def test_the_exiled_card_costs_two_less(self, builder):
        """A {4} artifact off two Mountains."""
        game = table(builder, board=[ARCANUM], exiled=[RELIC])
        activate(game, ARCANUM)
        assert casts(game, RELIC)

    def test_without_the_rider_it_costs_full_price(self, builder):
        """The near miss: the same permission, printed without the second sentence."""
        game = table(builder, board=[PLAIN], exiled=[RELIC])
        activate(game, PLAIN)
        assert game.state.objects[exiled_oid(game, RELIC)].playable_by == 0
        assert casts(game, RELIC) == []

    def test_it_is_charged_what_it_was_offered_at(self, builder):
        """`Game._cast` charges the same discount `_cast_variant` priced."""
        game = table(builder, board=[ARCANUM], exiled=[RELIC], lands=3)
        activate(game, ARCANUM)
        oid = exiled_oid(game, RELIC)
        game.apply(casts(game, RELIC)[0])
        assert tapped_mountains(game) == 2
        settle(game)
        assert oid in game.state.battlefield

    def test_the_discount_reaches_only_generic_mana(self, builder):
        """{3}{R} under the permission is {1}{R}; the red pip is still owed."""
        game = table(builder, board=[ARCANUM], exiled=[FLARE], lands=2)
        activate(game, ARCANUM)
        game.apply(casts(game, FLARE)[0])
        assert tapped_mountains(game) == 2

    def test_the_exile_op_carries_the_rider_too(self, builder):
        game = table(builder, hand=[HEIST], opp_graveyard=[RELIC], lands=3)
        game.apply(casts(game, HEIST)[0])
        settle(game)
        oid = exiled_oid(game, RELIC)
        assert game.state.objects[oid].playable_cost_reduction == 2
        assert casts(game, RELIC), "{4} off the two Mountains left"


class TestOnlyThisWay:
    def test_another_exile_permission_is_not_discounted(self, builder):
        """A second {4} card in exile under an undiscounted impulse permission."""
        game = table(builder, board=[ARCANUM], graveyard=[RELIC])
        state = game.state
        stray = next(o for o in state.players[0].graveyard if state.objects[o].def_id == RELIC)
        move_object(state, stray, Zone.EXILE)
        state.objects[stray].playable_by = 0
        state.objects[stray].playable_turn = state.turn
        activate(game, ARCANUM)
        assert permission_cost_reduction(state, 0, stray) == 0
        assert casts(game, RELIC) == [], "{4} off two Mountains: not this way"

    def test_flashback_out_of_a_permitted_graveyard_pays_full_price(self, builder):
        """Two lanes for one card: the permission's is {1}{R}, flashback's {3}{R}."""
        game = table(builder, board=[RECALL], graveyard=[FLARE], lands=3)
        activate(game, RECALL)
        assert casts(game, FLARE, flashback=False), "the permission's line, discounted"
        assert casts(game, FLARE, flashback=True) == [], "flashback is not this way"

    def test_flashback_is_charged_its_own_price(self, builder):
        game = table(builder, board=[RECALL], graveyard=[FLARE], lands=4)
        activate(game, RECALL)
        game.apply(casts(game, FLARE, flashback=True)[0])
        assert tapped_mountains(game) == 4

    def test_the_lane_flags_refuse_it(self, builder):
        game = table(builder, board=[ARCANUM], exiled=[RELIC])
        activate(game, ARCANUM)
        oid = exiled_oid(game, RELIC)
        state = game.state
        for flag in ("flashback", "foretold", "from_library_top", "prepared", "fused",
                     "second_face"):
            assert permission_cost_reduction(state, 0, oid, **{flag: True}) == 0, flag

    def test_it_is_the_grantees_discount(self, builder):
        game = table(builder, board=[ARCANUM], exiled=[RELIC])
        activate(game, ARCANUM)
        assert permission_cost_reduction(game.state, 1, exiled_oid(game, RELIC)) == 0


class TestWearingOff:
    def test_before_the_activation_nothing_is_castable(self, builder):
        game = table(builder, board=[ARCANUM], exiled=[RELIC], lands=4)
        assert casts(game, RELIC) == []

    def test_it_ends_with_the_turn(self, builder):
        """"Until end of turn": the permission and its discount lapse together."""
        game = table(builder, board=[ARCANUM], exiled=[RELIC])
        activate(game, ARCANUM)
        state = game.state
        oid = exiled_oid(game, RELIC)
        state.turn += 1
        assert permission_cost_reduction(state, 0, oid) == 0

    def test_it_leaves_with_the_card(self, builder):
        """400.7: a card that changes zones is a new object with no grant."""
        game = table(builder, board=[ARCANUM], exiled=[RELIC])
        activate(game, ARCANUM)
        state = game.state
        oid = exiled_oid(game, RELIC)
        move_object(state, oid, Zone.GRAVEYARD)
        assert state.objects[oid].playable_cost_reduction == 0


def _probe(effect: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_probe",
            "name": "Probe",
            "oracle_text": "",
            "mana_cost": "{1}",
            "types": ["Sorcery"],
            "colors": [],
            "color_identity": [],
            "spell_effects": [effect],
        }
    )


GRANT = {"op": "grant_playable", "objects": {"zone": "exile", "exiled_with": "self"}}


class TestTheLoaderRefuses:
    def test_the_witness_shape_loads(self):
        compile_card(_probe({**GRANT, "playable_cost_reduction": 2}))

    def test_a_bare_exile(self):
        """No permission, so nothing for the discount to ride on."""
        with pytest.raises(DslError, match="needs one"):
            compile_card(
                _probe({"op": "exile", "objects": {"zone": "graveyard"}, "playable_cost_reduction": 2})
            )

    @pytest.mark.parametrize("amount", [0, -1, True, "2", {"const": 2}])
    def test_anything_but_a_positive_integer(self, amount):
        with pytest.raises(DslError, match="positive integer"):
            compile_card(_probe({**GRANT, "playable_cost_reduction": amount}))

    def test_beside_playable_free(self):
        with pytest.raises(DslError, match="no mana cost to reduce"):
            compile_card(
                _probe({**GRANT, "playable_cost_reduction": 2, "playable_free": True})
            )
