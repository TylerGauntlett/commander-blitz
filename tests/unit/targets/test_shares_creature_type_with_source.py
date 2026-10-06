""""…a spell that shares a creature type with **this creature**."

    Folk Hero — Legendary Enchantment — Background
    "Commander creatures you own have "Whenever you cast a spell that shares a
    creature type with this creature, draw a card. This ability triggers only
    once each turn.""

`shares_a_creature_type_with: "self"` is a trigger-filter key comparing the cast
spell with the object that *has* the ability. On Folk Hero that object is the
commander creature the Background granted it to, never the Background: the
grant is appended to the recipient's ability list by `abilities_of`, so the
`ability_source` a trigger filter is matched against is the commander.

Two near misses loaded and were wrong, and each is a claim below.

* **`shares_a_type_with_commander`** unions the subtypes of *every* commander a
  player has. A partner pair's other half answers for this one, and a
  Background commander contributes "Background" -- so with Folk Hero itself in
  the command zone, casting another Background would draw. That is a broader
  card than the printed "this creature".
* **`shares_a_type_with`** intersects every subtype and reads a binding, and a
  trigger filter has no bindings. Even as an effect-side key it is the wrong
  question here: 205.3m says *creature* types, and a Background, an Aura or an
  Arcane is a subtype that is not one.

205.3m is also why a noncreature spell normally shares nothing (its subtypes are
spell, artifact or enchantment types) while a Kindred one does -- a Kindred
Instant -- Elf has the creature type Elf. Changeling needs nothing of its own: a
changeling's printed subtypes are the creature-type list, read off `chars`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.registry import CardRegistry, authored_card_paths
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import abilities_of, chars, creature_types_of
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import matches
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.primitives import change_control
from automtg.engine.sandbox import GameBuilder
from automtg.engine.zones import move_object
from tests.conftest import pass_until

FOLK_HERO = "folk_hero"
ELF_COMMANDER = "sct_elf_commander"
GOBLIN_COMMANDER = "sct_goblin_commander"
ELF_SPELL = "sct_elf"
GOBLIN_SPELL = "sct_goblin"
ELF_GOBLIN_SPELL = "sct_elf_goblin"
CHANGELING_SPELL = "sct_changeling"
KINDRED_ELF_INSTANT = "sct_kindred_elf_instant"
PLAIN_INSTANT = "sct_plain_instant"
BACKGROUND_SPELL = "sct_background"


def _creature(card_id: str, subtypes: list[str], *, legendary: bool = False) -> dict:
    return {
        "id": card_id,
        "name": card_id.replace("_", " ").title(),
        "mana_cost": "{G}",
        "types": ["Creature"],
        "supertypes": ["Legendary"] if legendary else [],
        "subtypes": subtypes,
        "power": 1,
        "toughness": 1,
    }


def _instant(card_id: str, subtypes: list[str]) -> dict:
    return {
        "id": card_id,
        "name": card_id.replace("_", " ").title(),
        "oracle_text": "You gain 1 life.",
        "mana_cost": "{G}",
        "types": ["Instant"],
        "subtypes": subtypes,
        "spell_effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
    }


QUOTED = (
    "Whenever you cast a spell that shares a creature type with this creature, "
    "draw a card. This ability triggers only once each turn."
)


def _folk_hero() -> dict:
    """Folk Hero, written here rather than read from `data/` -- the claim is that
    the DSL can say it -- and compiled through `compile_card`, so every loader
    guard a real card file meets is met."""
    return {
        "id": FOLK_HERO,
        "name": "Folk Hero",
        "oracle_text": f'Commander creatures you own have "{QUOTED}"',
        "mana_cost": "{1}{W}",
        "types": ["Enchantment"],
        "supertypes": ["Legendary"],
        "subtypes": ["Background"],
        "grantable_abilities": [
            {
                "kind": "triggered",
                "text": QUOTED,
                "trigger": {
                    "event": "spell_cast",
                    "controller": "you",
                    "filter": {"shares_a_creature_type_with": "self"},
                    "max_per_turn": 1,
                },
                "effects": [{"op": "draw", "player": "you"}],
            }
        ],
        "abilities": [
            {
                "kind": "static",
                "text": f'Commander creatures you own have "{QUOTED}"',
                "effect": "grant_ability",
                "ability": 0,
                "affects": {"types": ["Creature"], "is_commander": True, "owner": "you"},
            }
        ],
    }


#: Every creature type the engine's changeling stands for.
CHANGELING = [
    "Human", "Soldier", "Warrior", "Wizard", "Cleric", "Rogue", "Knight", "Elf",
    "Goblin", "Zombie", "Vampire", "Spirit", "Beast", "Elemental", "Dragon",
    "Angel", "Demon", "Sphinx", "Bird", "Cat", "Snake", "Insect", "Serpent",
    "Giant", "Orc", "Merfolk", "Druid", "Shaman", "Bear", "Wall",
]

SPECS = [
    _folk_hero(),
    _creature(ELF_COMMANDER, ["Elf", "Druid"], legendary=True),
    _creature(GOBLIN_COMMANDER, ["Goblin", "Shaman"], legendary=True),
    _creature(ELF_SPELL, ["Elf", "Warrior"]),
    _creature(GOBLIN_SPELL, ["Goblin"]),
    _creature(ELF_GOBLIN_SPELL, ["Elf", "Goblin"]),
    _creature(CHANGELING_SPELL, ["Shapeshifter", *CHANGELING]),
    # A Kindred Instant -- Elf, as the importer writes one: "Kindred" is dropped
    # from the types and the creature type stays in the subtypes.
    _instant(KINDRED_ELF_INSTANT, ["Elf"]),
    _instant(PLAIN_INSTANT, []),
    {
        "id": BACKGROUND_SPELL,
        "name": "Sct Background",
        "mana_cost": "{G}",
        "types": ["Enchantment"],
        "supertypes": ["Legendary"],
        "subtypes": ["Background"],
    },
]


@pytest.fixture(scope="module")
def pool() -> CardRegistry:
    cards = {
        card.id: card
        for card in CardRegistry.from_paths(authored_card_paths(Path("data/cards")))
    }
    for spec in SPECS:
        compiled = compile_card(CardModel.model_validate(spec))
        cards[compiled.id] = compiled
    return CardRegistry(cards)


def position(
    pool: CardRegistry,
    hand: list[str],
    *,
    commanders: tuple[str, ...] = (ELF_COMMANDER,),
    their_commander: str | None = None,
    caster: int = 0,
):
    """Folk Hero and commander creatures on seat 0; ``hand`` in ``caster``'s hand.

    Returns ``(game, commander_oids)``. A commander creature is an ordinary
    permanent with ``is_commander`` set, which is what one cast from the command
    zone is -- the Background's line is about the ones on the board.
    """
    builder = (
        GameBuilder(pool, players=2, seed=0)
        .battlefield(0, [FOLK_HERO, *commanders, *["forest"] * 6])
        .battlefield(1, [*([their_commander] if their_commander else []), *["forest"] * 6])
        .hand(caster, hand)
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(caster)
    )
    game = builder.build()
    ours = []
    for obj in game.state.battlefield_objects():
        if obj.def_id in (*commanders, their_commander):
            obj.is_commander = True
            if obj.owner == 0:
                ours.append(obj.oid)
    game.state.bump_chars()
    return game, ours


def library(game, pid: int = 0) -> int:
    return len(game.state.zone_list(Zone.LIBRARY, pid))


def cast(game, card_id: str) -> None:
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        )
    )
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def drawn(pool, spell: str, **kwargs) -> int:
    """How many cards seat 0 drew off one cast of ``spell``."""
    game, _ = position(pool, [spell], **kwargs)
    before = library(game)
    cast(game, spell)
    return before - library(game)


class TestItComparesAgainstTheCommander:
    """"This creature" is the commander that has the ability, not Folk Hero."""

    def test_a_spell_sharing_the_commanders_type_draws(self, pool):
        assert drawn(pool, ELF_SPELL) == 1

    def test_a_spell_sharing_none_does_not(self, pool):
        assert drawn(pool, GOBLIN_SPELL) == 0

    def test_a_background_does_not_share_with_folk_hero(self, pool):
        """Folk Hero is a Background, and Background is not a creature type.

        Compared against the granter's raw subtypes, this cast would draw.
        """
        assert drawn(pool, BACKGROUND_SPELL) == 0

    def test_each_commander_answers_for_itself(self, pool):
        """The partner case `shares_a_type_with_commander` gets wrong.

        Two commander creatures each have the ability. A Goblin shares a type
        with the Goblin commander only, so exactly one of them draws; an Elf
        Goblin shares with both, and both draw.
        """
        both = (ELF_COMMANDER, GOBLIN_COMMANDER)
        assert drawn(pool, GOBLIN_SPELL, commanders=both) == 1
        assert drawn(pool, ELF_GOBLIN_SPELL, commanders=both) == 2

    def test_no_commander_creature_means_nothing(self, pool):
        assert drawn(pool, ELF_SPELL, commanders=()) == 0


class TestCreatureTypesOnly:
    """205.3m -- creature types, and only the objects that have them."""

    def test_a_changeling_shares_with_anything(self, pool):
        assert drawn(pool, CHANGELING_SPELL, commanders=(GOBLIN_COMMANDER,)) == 1

    def test_a_kindred_instant_has_its_creature_type(self, pool):
        assert drawn(pool, KINDRED_ELF_INSTANT) == 1

    def test_an_ordinary_instant_shares_nothing(self, pool):
        assert drawn(pool, PLAIN_INSTANT) == 0

    def test_a_background_has_no_creature_types(self, pool):
        game, _ = position(pool, [])
        hero = next(o.oid for o in game.state.battlefield_objects() if o.def_id == FOLK_HERO)
        assert "Background" in chars(game.state, hero).subtypes
        assert creature_types_of(game.state, hero) == frozenset()

    def test_a_missing_object_has_none(self, pool):
        game, _ = position(pool, [])
        assert creature_types_of(game.state, None) == frozenset()
        assert creature_types_of(game.state, 10_000) == frozenset()


class TestOnceEachTurn:
    def test_a_second_matching_spell_draws_nothing(self, pool):
        game, _ = position(pool, [ELF_SPELL, ELF_GOBLIN_SPELL])
        before = library(game)
        cast(game, ELF_SPELL)
        cast(game, ELF_GOBLIN_SPELL)
        assert before - library(game) == 1


class TestWhoseCommander:
    """903.3 -- "you own", and "you" inside the quote is the recipient's controller."""

    def test_an_opponents_commander_gets_nothing(self, pool):
        game, _ = position(pool, [ELF_SPELL], commanders=(), their_commander=ELF_COMMANDER, caster=1)
        theirs = next(
            o.oid for o in game.state.battlefield_objects() if o.def_id == ELF_COMMANDER
        )
        assert not [a for a in abilities_of(game.state, theirs) if a.is_triggered]
        before = library(game, 1)
        cast(game, ELF_SPELL)
        assert library(game, 1) == before

    def test_a_stolen_commander_you_own_keeps_it_for_its_thief(self, pool):
        """Folk Hero still grants it -- you own the commander -- and the
        granted "you" is now the player who controls the creature."""
        game, ours = position(pool, [ELF_SPELL], caster=1)
        change_control(game.state, ours[0], 1)
        game.state.bump_chars()
        assert [a for a in abilities_of(game.state, ours[0]) if a.is_triggered]
        mine, theirs = library(game, 0), library(game, 1)
        cast(game, ELF_SPELL)
        assert library(game, 1) == theirs - 1, "the thief cast it and draws"
        assert library(game, 0) == mine


class TestWearingOff:
    def test_folk_hero_leaving_takes_the_ability_with_it(self, pool):
        game, ours = position(pool, [ELF_SPELL])
        hero = next(o.oid for o in game.state.battlefield_objects() if o.def_id == FOLK_HERO)
        move_object(game.state, hero, Zone.GRAVEYARD)
        game.state.bump_chars()
        assert not [a for a in abilities_of(game.state, ours[0]) if a.is_triggered]
        before = library(game)
        cast(game, ELF_SPELL)
        assert library(game) == before


class TestTheEffectSideAgrees:
    """The same key in an effect selector: `"self"` or a binding name."""

    def test_self_and_a_binding_read_the_named_object(self, pool):
        game, ours = position(pool, [], commanders=(ELF_COMMANDER, GOBLIN_COMMANDER))
        elf, goblin = ours
        ctx = EffectContext(
            state=game.state, controller=0, source_oid=elf, bindings={"it": goblin}
        )
        assert matches(ctx, elf, {"shares_a_creature_type_with": "self"})
        assert not matches(ctx, goblin, {"shares_a_creature_type_with": "self"})
        assert matches(ctx, goblin, {"shares_a_creature_type_with": "it"})
        assert not matches(ctx, elf, {"shares_a_creature_type_with": "unbound"})


class TestTheLoaderGuard:
    def test_a_trigger_filter_may_only_say_self(self):
        spec = _folk_hero()
        spec["grantable_abilities"][0]["trigger"]["filter"] = {
            "shares_a_creature_type_with": "subject"
        }
        with pytest.raises(DslError, match="shares_a_creature_type_with"):
            compile_card(CardModel.model_validate(spec))
