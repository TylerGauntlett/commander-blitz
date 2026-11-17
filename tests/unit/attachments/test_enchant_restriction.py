"""An Aura's enchant clause is a standing restriction (303.4d, 704.5m).

"Enchant creature with another Aura attached to it" (Daybreak Coronet) limits
what the Aura may be attached to for as long as it is on the battlefield, not
only what its spell may target. 704.5m puts an Aura attached to an illegal
object or player into its owner's graveyard, and the clause the state-based
action reads is the one the cast reads: the Aura's first target spec, asked
of its one host for its controller now (`zones.enchant_clause_holds`).

Without the standing check the Coronet stayed on, granting +3/+3, first
strike, vigilance and lifelink, after the Aura that let it be cast was
destroyed; "enchant creature you control" stayed on a creature an opponent
stole; and "enchant opponent" stayed on the seat that had taken control of it.

"Another" is `enchanted_by: {"exclude_self": true}`: an attached Coronet is an
Aura on its own host, and without the exclusion it would satisfy its own
clause for ever. Only the effect selector may write the key, because only it
knows the source; the static, trigger and cost-reduction filters refuse it.

The witness is Daybreak Coronet (`t_er_coronet`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import attach, attach_to_player, change_control
from commanderblitz.engine.zones import destroy
from tests.conftest import keywords, only_oid, pt, settle, static_probe

CORONET = "t_er_coronet"  # Enchant creature with another Aura attached to it; +3/+3 and more
MANTLE = "t_er_mantle"  # Enchant creature you control
CURSE = "t_er_curse"  # Enchant opponent
AURA = "t_eb_aura"  # Enchant creature, and nothing else
BEAR = "t_eb_bear"  # a vanilla 2/2
CUB = "t_eb_cub"  # another vanilla creature
PLAINS = "plains"


def position(builder, *, auras_on_bear=1, extra=(), attach_extra=None):
    """Player 0's Bear wearing ``auras_on_bear`` plain Auras, beside a bare Cub,
    with the Coronet in hand and two Plains to cast it. ``extra`` is anything
    else player 0 controls, and ``attach_extra(game, bear)`` attaches it.
    Attached before the position advances, so the state-based action that bins
    an unattached Aura never sees one. Returns ``(game, bear, cub)``.
    """
    b = builder(players=2).battlefield(
        0, [BEAR, CUB, PLAINS, PLAINS, *[AURA] * auras_on_bear, *extra]
    )
    b.hand(0, [CORONET])
    for pid in range(2):
        b.library(pid, [PLAINS] * 20)
    game = b.active(0).step(Step.PRECOMBAT_MAIN).build(advance=False)
    bear, cub = only_oid(game, BEAR, 0), only_oid(game, CUB, 0)
    for oid in [o for o in game.state.battlefield if game.state.objects[o].def_id == AURA]:
        assert attach(game.state, oid, bear)
    if attach_extra is not None:
        attach_extra(game, bear)
    game._advance()
    settle(game)
    return game, bear, cub


def hosts_offered(game) -> set[int]:
    """Every permanent a cast of the Coronet may target."""
    return {
        getattr(ref, "id", None)
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == CORONET
        for ref in a.targets
    }


def cast_onto(game, host):
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == CORONET
        and any(getattr(ref, "id", None) == host for ref in a.targets)
    )
    game.apply(action)
    settle(game)
    return only_oid(game, CORONET, 0)


def check_sbas(game) -> None:
    """State-based actions now: `settle` returns at once on an empty stack."""
    sba.run(game.state)


def plain_auras(game) -> list[int]:
    return [o for o in game.state.battlefield if game.state.objects[o].def_id == AURA]


class TestTheCast:
    def test_only_a_creature_wearing_an_aura_is_a_target(self, builder):
        """The bare Cub beside it is not."""
        game, bear, cub = position(builder)
        assert hosts_offered(game) == {bear}
        assert cub not in hosts_offered(game)

    def test_no_enchanted_creature_no_cast(self, builder):
        game, _, _ = position(builder, auras_on_bear=0)
        assert hosts_offered(game) == set()

    def test_it_resolves_onto_the_creature_and_grants_everything(self, builder):
        game, bear, _ = position(builder)
        coronet = cast_onto(game, bear)
        assert game.state.objects[coronet].attached_to == bear
        assert pt(game, bear) == (5, 5)
        assert {"first_strike", "vigilance", "lifelink"} <= keywords(game, bear)


class TestAnotherAura:
    def test_the_coronet_is_not_another_aura_to_itself(self, builder):
        """Once attached, the Coronet is an Aura on the Bear; the clause still
        asks for one other than it."""
        game, bear, _ = position(builder)
        coronet = cast_onto(game, bear)
        ctx = EffectContext(game.state, controller=0, source_oid=coronet)
        spec = {"zone": "battlefield", "types": ["Creature"], "enchanted_by": {"exclude_self": True}}
        assert resolve_pool(ctx, spec) == [bear]
        destroy(game.state, plain_auras(game)[0])
        assert resolve_pool(ctx, spec) == []

    def test_without_a_source_every_aura_counts(self, builder):
        """No ability source to exclude: the key reads as any Aura."""
        game, bear, _ = position(builder)
        ctx = EffectContext(game.state, controller=0, source_oid=None)
        spec = {"zone": "battlefield", "types": ["Creature"], "enchanted_by": {"exclude_self": True}}
        assert resolve_pool(ctx, spec) == [bear]


class TestTheStandingCheck:
    def test_the_other_aura_leaving_puts_the_coronet_away(self, builder):
        game, bear, _ = position(builder)
        coronet = cast_onto(game, bear)
        destroy(game.state, plain_auras(game)[0])
        check_sbas(game)
        assert game.state.objects[coronet].zone is Zone.GRAVEYARD
        assert pt(game, bear) == (2, 2)
        assert "lifelink" not in keywords(game, bear)

    def test_one_of_two_other_auras_leaving_is_not_enough(self, builder):
        """The boundary: "another Aura" is one or more, so one left suffices."""
        game, bear, _ = position(builder, auras_on_bear=2)
        coronet = cast_onto(game, bear)
        destroy(game.state, plain_auras(game)[0])
        check_sbas(game)
        assert game.state.objects[coronet].attached_to == bear
        assert pt(game, bear) == (5, 5)

    def test_enchant_creature_you_control_falls_off_a_stolen_creature(self, builder):
        game, bear, _ = position(
            builder,
            auras_on_bear=0,
            extra=[MANTLE],
            attach_extra=lambda g, bear: attach(g.state, only_oid(g, MANTLE, 0), bear),
        )
        mantle = only_oid(game, MANTLE, 0)
        assert game.state.objects[mantle].attached_to == bear
        change_control(game.state, bear, 1)
        check_sbas(game)
        assert game.state.objects[mantle].zone is Zone.GRAVEYARD

    def test_a_plain_enchant_creature_stays_on_a_stolen_creature(self, builder):
        """The near miss: "enchant creature" names no controller, so a change
        of control leaves its Aura legal."""
        game, bear, _ = position(builder)
        change_control(game.state, bear, 1)
        check_sbas(game)
        assert game.state.objects[plain_auras(game)[0]].attached_to == bear

    def test_enchant_opponent_falls_off_the_seat_that_controls_it(self, builder):
        game, _, _ = position(
            builder,
            auras_on_bear=0,
            extra=[CURSE],
            attach_extra=lambda g, _: attach_to_player(g.state, only_oid(g, CURSE, 0), 1),
        )
        curse = only_oid(game, CURSE, 0)
        assert game.state.objects[curse].attached_to_player == 1
        change_control(game.state, curse, 1)
        check_sbas(game)
        assert game.state.objects[curse].zone is Zone.GRAVEYARD


class TestTheKeyIsRefusedWhereNoSourceIsRead:
    def test_a_static_filter_may_not_write_it(self):
        model = static_probe(
            {
                "effect": "buff",
                "affects": {"types": ["Creature"], "enchanted_by": {"exclude_self": True}},
                "power": {"const": 1},
                "toughness": {"const": 1},
            }
        )
        with pytest.raises(DslError, match="exclude_self"):
            compile_card(CardModel.model_validate(model))

    def test_it_is_true_only(self):
        card = {
            "id": "t_er_bad",
            "name": "Test Bad Coronet",
            "oracle_text": "",
            "types": ["Enchantment"],
            "subtypes": ["Aura"],
            "targets": [
                {
                    "id": "enchanted",
                    "kind": "permanent",
                    "selector": {"types": ["Creature"], "enchanted_by": {"exclude_self": False}},
                }
            ],
        }
        with pytest.raises(DslError, match="exclude_self"):
            compile_card(CardModel.model_validate(card))
