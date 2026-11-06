"""`from_zone` / `not_from_zone` on a `spell_cost_reduction` -- where the spell is cast from.

    Emet-Selch of the Third Seat -- "Spells you cast from your graveyard cost
    {2} less to cast."
    Advanced Reconstruction (level 3) -- "Spells you cast from anywhere other
    than your hand cost {2} less to cast."

601.2a moves the card to the stack *before* 601.2f determines its total cost,
but the zone the sentence names is the one the card was cast **from**, so every
pricer -- the action list, `Game._cast` and a resolving `cast_card` -- hands
`cost_reduction` the object's zone as it stood when the cast was proposed. The
filter matches the printed face as before and, beside it, that zone.

Without the keys the line is an unfiltered `spell_cost_reduction`, which
discounts every hand cast -- a different and much stronger card -- and nothing
else in the vocabulary reads the origin of a spell being priced:
`free_cast_permission`'s ``from_zone`` frees rather than discounts, and the
card-level `cost_reduction`'s ``zone`` counts permanents.

A pricer that does not say where the cast comes from fails closed: a zone key
with no zone discounts nothing, so a new cast lane that forgets the plumbing
under-discounts rather than handing out the reduction everywhere.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.cost_reduction import cost_reduction
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import activations, find_action, only_oid, pass_until

GRAVEYARD = "t_czr_graveyard"  # from_zone: graveyard, {2} less
ELSEWHERE = "t_czr_elsewhere"  # not_from_zone: hand, {2} less
FLARE = "t_czr_flare"  # {3}{R} sorcery, flashback {3}{R}
RELIC = "t_czr_relic"  # {4} artifact
COMMANDER = "t_czr_commander"  # {4}{R} commander
MACHINIST = "t_untapped_machinist"  # you may cast artifact spells from your graveyard
CONDUIT = "t_cc_conduit"  # {T}: cast target permanent card from your graveyard

ORIGINS = (Zone.HAND, Zone.GRAVEYARD, Zone.EXILE, Zone.LIBRARY, Zone.COMMAND)


def table(builder, *, board=(), hand=(), graveyard=(), command=(), lands=2):
    """Player 0's main phase: ``board`` and ``lands`` Mountains in play.

    A Forest in hand and a library, so a priority window with nothing else
    affordable still has a play in it and the engine does not pass on the
    player's behalf -- an empty action list would pass "not castable" for the
    wrong reason."""
    b = (
        builder(players=2)
        .battlefield(0, ["mountain"] * lands + list(board))
        .hand(0, [*hand, "forest"])
        .graveyard(0, list(graveyard))
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .active(0)
        .max_turns(1)
    )
    if command:
        b = b.commander(0, list(command))
    return b.build()


def reduction(builder, board, zone, *, pid: int = 0, spell: str = FLARE) -> int:
    game = table(builder, board=board)
    return cost_reduction(game.state, pid, game.state.registry.get(spell), zone=zone)


def casts(game, def_id: str, zone: Zone | None = None) -> list:
    state = game.state
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and a.source is not None
        and state.objects[a.source].def_id == def_id
        and (zone is None or state.objects[a.source].zone is zone)
    ]


def tapped_mountains(game) -> int:
    state = game.state
    return sum(
        state.objects[oid].tapped
        for oid in state.battlefield
        if state.objects[oid].def_id == "mountain"
    )


class TestFromYourGraveyard:
    """Emet-Selch: the graveyard and nowhere else."""

    def test_a_graveyard_cast_is_discounted(self, builder):
        assert reduction(builder, [GRAVEYARD], Zone.GRAVEYARD) == 2

    @pytest.mark.parametrize("zone", [Zone.HAND, Zone.COMMAND, Zone.EXILE, Zone.LIBRARY])
    def test_no_other_zone_is(self, builder, zone):
        assert reduction(builder, [GRAVEYARD], zone) == 0

    def test_a_pricer_that_names_no_zone_gets_no_discount(self, builder):
        """Fail closed: a forgotten zone is a missing discount, not a free one."""
        assert reduction(builder, [GRAVEYARD], None) == 0

    def test_it_is_only_your_spells(self, builder):
        """"Spells **you** cast" -- an opponent's flashback pays full price."""
        assert reduction(builder, [GRAVEYARD], Zone.GRAVEYARD, pid=1) == 0

    def test_without_the_permanent_nothing_is_discounted(self, builder):
        """The wearing-off: the static lives on the battlefield."""
        assert reduction(builder, [], Zone.GRAVEYARD) == 0


class TestFromAnywhereOtherThanYourHand:
    """Advanced Reconstruction: the complement of the hand."""

    @pytest.mark.parametrize("zone", [Zone.GRAVEYARD, Zone.EXILE, Zone.LIBRARY, Zone.COMMAND])
    def test_every_other_origin_is_discounted(self, builder, zone):
        assert reduction(builder, [ELSEWHERE], zone) == 2

    def test_the_hand_is_not(self, builder):
        assert reduction(builder, [ELSEWHERE], Zone.HAND) == 0

    def test_a_pricer_that_names_no_zone_gets_no_discount(self, builder):
        assert reduction(builder, [ELSEWHERE], None) == 0

    def test_two_discounts_stack_on_the_zone_both_name(self, builder):
        assert reduction(builder, [GRAVEYARD, ELSEWHERE], Zone.GRAVEYARD) == 4
        assert reduction(builder, [GRAVEYARD, ELSEWHERE], Zone.EXILE) == 2


class TestFlashbackIsOfferedAndChargedDiscounted:
    """Legality and `Game._cast` read the same zone, so the offer is the charge.

    Flashback {3}{R} on two Mountains is two short; {2} less closes the gap."""

    def test_flashback_off_two_lands_needs_the_discount(self, builder):
        assert not casts(table(builder, graveyard=[FLARE]), FLARE)
        assert casts(table(builder, board=[GRAVEYARD], graveyard=[FLARE]), FLARE)

    def test_the_same_card_in_hand_is_not_discounted(self, builder):
        assert not casts(table(builder, board=[GRAVEYARD], hand=[FLARE]), FLARE)

    def test_the_cast_charges_the_discounted_price(self, builder):
        """Four Mountains open, two spent: {1}{R}, not {3}{R}."""
        game = table(builder, board=[GRAVEYARD], graveyard=[FLARE], lands=4)
        game.apply(casts(game, FLARE, Zone.GRAVEYARD)[0])
        assert tapped_mountains(game) == 2

    def test_a_hand_cast_beside_it_pays_full_price(self, builder):
        game = table(builder, board=[GRAVEYARD], hand=[FLARE], lands=4)
        game.apply(casts(game, FLARE, Zone.HAND)[0])
        assert tapped_mountains(game) == 4


class TestAGrantedGraveyardCast:
    """A permission from another permanent is a graveyard cast too."""

    def test_the_relic_is_castable_off_two_lands(self, builder):
        assert not casts(table(builder, board=[MACHINIST], graveyard=[RELIC]), RELIC)
        assert casts(table(builder, board=[MACHINIST, GRAVEYARD], graveyard=[RELIC]), RELIC)


class TestCastCardFromTheGraveyard:
    """A resolving `cast_card` prices the card from the zone it found it in."""

    def resolve_conduit(self, builder, board):
        game = table(builder, board=[CONDUIT, *board], graveyard=[RELIC])
        game.apply(activations(game, only_oid(game, CONDUIT, 0))[0])
        pass_until(
            game,
            lambda g: not g.state.stack
            or (g.pending() is not None and g.pending().kind is not DecisionKind.PRIORITY),
        )
        return game

    def test_without_the_discount_the_relic_is_not_offered(self, builder):
        game = self.resolve_conduit(builder, [])
        assert game.pending().kind is not DecisionKind.MAY

    def test_with_it_the_cast_is_offered_and_paid(self, builder):
        game = self.resolve_conduit(builder, [GRAVEYARD])
        assert game.pending().kind is DecisionKind.MAY
        game.apply(find_action(game, ActionKind.YES))
        assert tapped_mountains(game) == 2


class TestTheCommandZone:
    """A commander is cast from the command zone -- not the graveyard, and not
    the hand."""

    def test_a_graveyard_discount_leaves_the_commander_alone(self, builder):
        game = table(builder, board=[GRAVEYARD], command=[COMMANDER], lands=3)
        assert not casts(game, COMMANDER)

    def test_an_anywhere_but_hand_discount_reaches_it(self, builder):
        """{4}{R} less {2} on three Mountains."""
        game = table(builder, board=[ELSEWHERE], command=[COMMANDER], lands=3)
        assert casts(game, COMMANDER, Zone.COMMAND)


class TestTheLoader:
    def _card(self, filt) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_czr_probe",
                "name": "Zone Discount Probe",
                "mana_cost": "{1}",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "static",
                        "effect": "spell_cost_reduction",
                        "affects_spells": filt,
                        "amount": 1,
                    }
                ],
            }
        )

    @pytest.mark.parametrize(
        "filt",
        [
            {"from_zone": "graveyard"},
            {"from_zone": ["graveyard", "exile"]},
            {"not_from_zone": "hand"},
            {"from_zone": "exile", "not_from_zone": "hand", "types": ["Creature"]},
        ],
    )
    def test_it_accepts_a_zone_or_a_list(self, filt):
        compile_card(self._card(filt), source="test")

    @pytest.mark.parametrize(
        "filt",
        [
            {"from_zone": "battlefield"},
            {"from_zone": "graveyards"},
            {"from_zone": []},
            {"not_from_zone": ["hand", 3]},
            {"from_zone": {"zone": "graveyard"}},
        ],
    )
    def test_it_refuses_a_zone_nothing_is_cast_from(self, filt):
        with pytest.raises(DslError, match="zone a card is cast from"):
            compile_card(self._card(filt), source="test")

    def test_it_refuses_a_zone_on_both_sides(self):
        with pytest.raises(DslError, match="both"):
            compile_card(
                self._card({"from_zone": ["graveyard"], "not_from_zone": "graveyard"}),
                source="test",
            )

    def test_every_origin_is_sayable(self):
        for zone in ORIGINS:
            compile_card(self._card({"from_zone": zone.value}), source="test")
