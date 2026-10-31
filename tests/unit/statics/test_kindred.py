"""Kindred: a card type whose subtypes are creature types (rule 308).

    Eldrazi Conscription — "Kindred Enchantment — Eldrazi Aura. Enchant
    creature. Enchanted creature gets +10/+10 and has trample and annihilator 2."

Without the type, the card could only be written as a plain Enchantment with an
Eldrazi subtype nothing explained: `build_type_line` printed "Enchantment -
Aura Eldrazi", a type-changing effect dropped the Eldrazi as the subtype of a
card type the object lacked, and "choose a card type: Kindred" protected from
nothing. 308.1 makes Kindred travel with another card type, which is how the
card is cast and resolves; 308.3 (and 205.3m) make its subtypes creature types,
so "Eldrazi you control" counts it; and it is never a creature by itself, so
"Eldrazi creatures you control" does not. It is not a permanent type (110.4a):
a Kindred artifact and a Kindred enchantment share no permanent type.

"Tribal" is Kindred's old name. The importer reads it as Kindred
(`tests/cards/test_proxy.py`); the loader refuses the old word.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.registry import CardRegistry
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import (
    chars,
    creature_types_of,
    is_creature,
    subtype_survives,
)
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.sandbox import GameBuilder
from tests.conftest import only_oid, pass_until

ENCHANTMENT = "t_kindred_eldrazi_enchantment"  # Kindred Enchantment -- Eldrazi
ARTIFACT = "t_kindred_shapeshifter_artifact"  # Kindred Artifact -- Shapeshifter
INSTANT = "t_kindred_goblin_instant"  # Kindred Instant -- Goblin
PLAIN_ARTIFACT = "t_toll_gate"
BEAR = "t_bear"


def _spec(card_id: str, types: list[str], subtypes: list[str], **extra) -> dict:
    return {
        "id": card_id,
        "name": card_id.replace("_", " ").title(),
        "oracle_text": "",
        "mana_cost": "{1}",
        "types": types,
        "subtypes": subtypes,
        **extra,
    }


SPECS = [
    _spec(ENCHANTMENT, ["Kindred", "Enchantment"], ["Eldrazi"]),
    _spec(ARTIFACT, ["Kindred", "Artifact"], ["Shapeshifter"]),
    _spec(
        INSTANT,
        ["Kindred", "Instant"],
        ["Goblin"],
        oracle_text="You gain 1 life.",
        spell_effects=[{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
    ),
]


@pytest.fixture(scope="module")
def pool(registry: CardRegistry) -> CardRegistry:
    cards = {card.id: card for card in registry}
    for spec in SPECS:
        compiled = compile_card(CardModel.model_validate(spec))
        cards[compiled.id] = compiled
    return CardRegistry(cards)


def position(pool: CardRegistry, mine=(ENCHANTMENT,), hand=()):
    """Seat 0's ``mine`` on the battlefield, ``hand`` in hand, in its main phase."""
    game = (
        GameBuilder(pool, players=2, seed=0)
        .battlefield(0, ["forest"] * 3 + list(mine))
        .hand(0, list(hand))
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    return game, (only_oid(game, mine[0], 0) if mine else None)


def matching(game, **selector) -> set[int]:
    ctx = EffectContext(state=game.state, controller=0, source_name="probe")
    return set(
        resolve_pool(
            ctx, {"zone": "battlefield", "controller": "you", "count": "all", **selector}
        )
    )


def sharing(game, subject: int) -> set[int]:
    """Everything `shares_permanent_type_with: "subject"` would offer."""
    ctx = EffectContext(state=game.state, controller=0, source_name="probe")
    ctx.bindings["subject"] = subject
    selector = {
        "zone": "battlefield",
        "controller": "you",
        "shares_permanent_type_with": "subject",
        "count": "all",
    }
    return set(resolve_pool(ctx, selector))


class TestTheTypeLine:
    def test_kindred_prints_first(self):
        card = compile_card(CardModel.model_validate(SPECS[0]))
        assert card.types == frozenset({"Kindred", "Enchantment"})
        assert card.type_line == "Kindred Enchantment - Eldrazi"

    def test_kindred_alone_is_refused(self):
        """308.1: every Kindred card has another card type."""
        with pytest.raises(DslError, match=r"308\.1"):
            compile_card(CardModel.model_validate(_spec("t_x", ["Kindred"], ["Eldrazi"])))

    def test_the_old_name_is_refused(self):
        """One spelling, so `types: ["Kindred"]` cannot miss a card."""
        with pytest.raises(DslError, match="'Kindred'"):
            compile_card(
                CardModel.model_validate(_spec("t_x", ["Tribal", "Enchantment"], ["Eldrazi"]))
            )


class TestItIsNeverACreature:
    def test_a_kindred_enchantment_is_not_a_creature(self, pool):
        game, oid = position(pool)
        assert not is_creature(game.state, oid)
        assert chars(game.state, oid).types == frozenset({"Kindred", "Enchantment"})

    def test_an_eldrazi_creature_selector_does_not_count_it(self, pool):
        """"Eldrazi creatures you control" is the printed sentence's own narrowing."""
        game, oid = position(pool)
        assert oid not in matching(game, types=["Creature"], subtypes=["Eldrazi"])

    def test_it_is_not_offered_as_an_attacker(self, pool):
        game, oid = position(pool, mine=(ENCHANTMENT, BEAR))
        game.state.objects[oid].summoning_sick = False
        pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
        assert not [
            a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER and a.source == oid
        ]

    def test_a_kindred_instant_resolves_as_an_instant(self, pool):
        """308.1: cast and resolved as its other card type -- to the graveyard."""
        game, _ = position(pool, mine=(), hand=(INSTANT,))
        life = game.state.players[0].life
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == INSTANT
            )
        )
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.players[0].life == life + 1
        (spell,) = (o for o in game.state.objects.values() if o.def_id == INSTANT)
        assert spell.zone is Zone.GRAVEYARD


class TestItsSubtypesAreCreatureTypes:
    def test_an_eldrazi_selector_counts_it(self, pool):
        """"Eldrazi you control": a subtype filter does not ask for a creature."""
        game, oid = position(pool)
        assert oid in matching(game, subtypes=["Eldrazi"])

    def test_creature_types_of_reads_it(self, pool):
        """205.3m and 308.3 -- what `shares_a_creature_type_with` and the
        chosen-type counts read."""
        game, oid = position(pool)
        assert creature_types_of(game.state, oid) == frozenset({"Eldrazi"})

    def test_a_type_change_that_keeps_kindred_keeps_them(self):
        """205.1b's "the subtypes go with the card type": Creature *or* Kindred."""
        assert subtype_survives("Eldrazi", {"Kindred", "Enchantment"})
        assert subtype_survives("Aura", {"Kindred", "Enchantment"})
        assert not subtype_survives("Eldrazi", {"Enchantment"})
        assert not subtype_survives("Eldrazi", {"Land"})
        assert subtype_survives("Eldrazi", {"Creature"})


class TestItIsNotAPermanentType:
    def test_two_kindred_permanents_of_different_types_share_none(self, pool):
        """110.4a: Kindred is a card type, not a permanent type -- Cloudstone
        Curio's "shares a permanent type" must not pair these two."""
        game, enchantment = position(pool, mine=(ENCHANTMENT, ARTIFACT, PLAIN_ARTIFACT))
        found = sharing(game, enchantment)
        assert only_oid(game, ARTIFACT, 0) not in found
        assert enchantment in found

    def test_the_other_card_type_still_pairs(self, pool):
        game, artifact = position(pool, mine=(ARTIFACT, PLAIN_ARTIFACT))
        assert only_oid(game, PLAIN_ARTIFACT, 0) in sharing(game, artifact)
