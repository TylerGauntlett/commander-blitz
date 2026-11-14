"""A permanent that becomes an Aura: Necromancy.

    "When this enchantment enters, if it's on the battlefield, it becomes an
    Aura with 'enchant creature put onto the battlefield with Necromancy.' Put
    target creature card from a graveyard onto the battlefield under your
    control and attach this enchantment to it. When this enchantment leaves the
    battlefield, that creature's controller sacrifices it."   -- Necromancy

    704.5m If an Aura is attached to an illegal object or player, or is not
    attached to an object or player, that Aura is put into its owner's
    graveyard.

Necromancy is printed a plain enchantment, and the Aura subtype an effect gives
it is what puts it into the graveyard when the creature it animated leaves.
Animate Dead's shape alone -- `return_from_graveyard` with ``link`` and an
`attach` of ``{"returned_with": "self"}`` -- attaches it fine, but every Aura
reader asked the printed `CardDef.is_aura` (and bestow's flag), so the
enchantment stayed on the battlefield attached to nothing, was no Aura on its
type line, and "enchanted" did not see it.

`become_aura` sets `GameObject.became_aura`, read beside `is_aura` the way
bestow's `cast_bestowed` is: the type line (`characteristics._compute`), the
static filter's face, `aura_controllers` and `zones._auras_had`, and
`sba._tokens_and_attachments`. Unlike bestow's, the Aura-ness does not hang on
being attached. It ends with the object (400.7). The clause it gains is Animate
Dead's battlefield one, which nothing re-tests (`docs/rules-coverage.md`).

The witness is Necromancy; `t_ba_rite` is its second paragraph and
`t_ba_rite_no_aura` the near miss without the op.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.characteristics import aura_controllers, chars, enchanted_by
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import destroy, exile, move_object
from tests.conftest import action_for_card, pass_until, settle

RITE = "t_ba_rite"
NEAR_MISS = "t_ba_rite_no_aura"
BEAR = "t_bear"  # a vanilla 2/2
INSTANT = "t_plain_instant"  # {W}: you gain 1 life


def position(builder, *, rite=RITE, graveyard=(BEAR,), their_graveyard=()):
    """Player 0 with ``rite`` in hand and a Swamp to cast it, in a main phase."""
    b = (
        builder(players=2)
        .battlefield(0, ["swamp", "plains"])
        .hand(0, [rite, INSTANT])
    )
    if graveyard:
        b.graveyard(0, list(graveyard))
    if their_graveyard:
        b.graveyard(1, list(their_graveyard))
    return b.active(0).step(Step.PRECOMBAT_MAIN).build()


def oid_of(game, card_id: str, owner: int = 0) -> int:
    (oid,) = [o.oid for o in game.state.objects.values() if o.def_id == card_id and o.owner == owner]
    return oid


def cast(game, card_id: str):
    game.apply(action_for_card(game, ActionKind.CAST, card_id))


def trigger_waiting(game, rite: int) -> None:
    """Pass until the enchantment is on the battlefield with its trigger on the stack."""
    pass_until(
        game,
        lambda g: g.state.objects[rite].zone is Zone.BATTLEFIELD
        and any(item.source_oid == rite and not item.is_spell for item in g.state.stack),
    )


def animated(builder, rite=RITE, **kw):
    game = position(builder, rite=rite, **kw)
    aura, bear = oid_of(game, rite), oid_of(game, BEAR, 1 if kw.get("their_graveyard") else 0)
    cast(game, rite)
    settle(game)
    return game, aura, bear


class TestItBecomesAnAura:
    def test_attached_to_the_creature_it_returned(self, builder):
        game, aura, bear = animated(builder)

        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[bear].controller == 0
        assert game.state.objects[aura].attached_to == bear

    def test_the_type_line_reads_aura(self, builder):
        game, aura, _ = animated(builder)

        c = chars(game.state, aura)
        assert "Aura" in c.subtypes
        assert "Enchantment" in c.types

    def test_not_an_aura_until_the_trigger_resolves(self, builder):
        game = position(builder)
        aura = oid_of(game, RITE)
        cast(game, RITE)
        trigger_waiting(game, aura)

        assert "Aura" not in chars(game.state, aura).subtypes
        assert game.state.objects[aura].became_aura is False

    def test_an_opponents_creature_card_returns_under_your_control(self, builder):
        game, aura, bear = animated(builder, graveyard=(), their_graveyard=(BEAR,))

        obj = game.state.objects[bear]
        assert (obj.owner, obj.controller, obj.zone) == (1, 0, Zone.BATTLEFIELD)
        assert game.state.objects[aura].attached_to == bear

    def test_enchanted_sees_it(self, builder):
        game, _, bear = animated(builder)

        assert aura_controllers(game.state, bear) == [0]
        assert enchanted_by(game.state, bear, True, 0)

    def test_the_near_miss_attaches_a_non_aura(self, builder):
        game, aura, bear = animated(builder, rite=NEAR_MISS)

        assert game.state.objects[aura].attached_to == bear
        assert "Aura" not in chars(game.state, aura).subtypes
        assert aura_controllers(game.state, bear) == []


class TestStateBasedActions:
    def test_the_creature_leaving_puts_it_into_the_graveyard(self, builder):
        """704.5m: an Aura attached to nothing."""
        game, aura, bear = animated(builder)

        destroy(game.state, bear)
        sba.run(game.state)

        assert game.state.objects[aura].zone is Zone.GRAVEYARD

    def test_the_near_miss_stays_attached_to_nothing(self, builder):
        game, aura, bear = animated(builder, rite=NEAR_MISS)

        destroy(game.state, bear)
        sba.run(game.state)

        assert game.state.objects[aura].zone is Zone.BATTLEFIELD

    def test_it_leaving_sacrifices_the_creature(self, builder):
        game, aura, bear = animated(builder)

        destroy(game.state, aura)
        settle(game)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_the_target_gone_it_does_nothing(self, builder):
        """The target gone as the trigger resolves: 608.2b, the ability does
        nothing, and the enchantment stays a non-Aura on the battlefield."""
        game = position(builder)
        aura, bear = oid_of(game, RITE), oid_of(game, BEAR)
        cast(game, RITE)
        trigger_waiting(game, aura)
        exile(game.state, bear)
        settle(game)

        assert game.state.objects[aura].zone is Zone.BATTLEFIELD
        assert game.state.objects[aura].became_aura is False


class TestItEndsWithTheObject:
    def test_back_on_the_battlefield_it_is_no_aura(self, builder):
        """400.7: a new object was never made an Aura."""
        game, aura, _ = animated(builder)

        move_object(game.state, aura, Zone.HAND)
        settle(game)
        move_object(game.state, aura, Zone.BATTLEFIELD)

        assert game.state.objects[aura].became_aura is False
        assert "Aura" not in chars(game.state, aura).subtypes


def _probe(effects, **card) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_ba_probe",
            "name": "Probe",
            "oracle_text": "",
            "mana_cost": "{B}",
            "types": ["Enchantment"],
            **card,
            "abilities": [
                {
                    "kind": "triggered",
                    "trigger": {"event": "self_enters", "source": "self"},
                    "effects": effects,
                }
            ],
        }
    )


class TestLoadTime:
    def test_an_enchantment_loads(self):
        card = compile_card(_probe([{"op": "become_aura"}]))
        assert not card.is_aura

    @pytest.mark.parametrize(
        "card",
        [
            {"types": ["Creature"], "power": 2, "toughness": 2},
            {"types": ["Artifact"]},
            {"subtypes": ["Aura"]},
        ],
        ids=["creature", "artifact", "already_an_aura"],
    )
    def test_only_on_a_non_aura_enchantment(self, card):
        with pytest.raises(DslError, match="become_aura"):
            compile_card(_probe([{"op": "become_aura"}], **card))

    def test_it_takes_no_selector(self):
        with pytest.raises(DslError, match="become_aura"):
            compile_card(_probe([{"op": "become_aura", "objects": {"self_only": True}}]))
