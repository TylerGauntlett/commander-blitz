"""A sacrifice cost that names the creature it sacrificed.

    Ghoulcaller Gisa: "{B}, {T}, Sacrifice another creature: Create X 2/2 black
    Zombie creature tokens, where X is the sacrificed creature's power."

`sacrifice` already charged "sacrifice another creature", but it was write-only:
the creature went to the graveyard and nothing the ability did could ask how big
it had been. The capability is `as` on that cost, the sacrifice twin of
`tap_permanents`' `as` (Station).

What the binding holds is the rules argument. The creature is sacrificed while
the cost is paid (601.2h, via 602.2b), so by the time the ability resolves it is
not on the battlefield and X is its **last-known information** -- its power as
it last existed there (608.2h). That number is fixed the moment it leaves, so a
snapshot taken just before the sacrifice is exact, and it is the only thing that
is: the oid afterwards names a graveyard card answering with its printed power
(a pumped or countered creature reads too low), and a token has no object left
at all once state-based actions clean it up (704.5d), so it reads 0.

The near miss is the `sacrifice` **op** with `snapshot` in the effects. That
pays on resolution, so Gisa could be activated with no other creature and
responded to before anything had died -- a different card.

The witness is Ghoulcaller Gisa (`ghoulcaller_gisa` in `data/cards/auto/`);
`t_gisa_outlet` is her shape.
"""

from __future__ import annotations

import copy

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, pump
from tests.conftest import count_on_battlefield, oids_of, only_oid, pass_until

GISA = "t_gisa_outlet"
BEAR = "t_bear"  # 2/2
GIANT = "t_big"  # 6/6
ZOMBIE = "zombie_2_2_b"


def position(builder, *creatures: str):
    """Gisa, a Swamp to pay {B}, her fodder, and an opponent holding a Bolt.

    The Bolt is never cast. It keeps the opponent from having a priority window
    with nothing in it but "pass", which would be passed automatically and let
    the ability resolve before a test could look at the stack.
    """
    game = (
        builder(players=2)
        .battlefield(0, [GISA, "swamp", "swamp"])
        .battlefield(0, list(creatures))
        .hand(1, ["t_bolt"])
        .battlefield(1, ["mountain"])
        .library(0, ["island"] * 20)
        .library(1, ["island"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    return game, only_oid(game, GISA)


def gisa_action(game, gisa: int):
    return next(
        (a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == gisa),
        None,
    )


def activate(game, gisa: int, creature: int) -> None:
    """Activate Gisa, sacrificing ``creature`` when the engine asks which."""
    action = gisa_action(game, gisa)
    assert action is not None, "Gisa's ability was not offered"
    game.apply(action)
    choose = next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE and creature in [t.id for t in a.targets]
        ),
        None,
    )
    if choose is not None:
        game.apply(choose)


def resolve(game) -> None:
    pass_until(game, lambda g: not g.state.stack)


def zombies(game) -> int:
    return count_on_battlefield(game, ZOMBIE, 0)


class TestWhenItIsOffered:
    def test_another_creature_makes_it_offered(self, builder):
        game, gisa = position(builder, BEAR)
        assert gisa_action(game, gisa) is not None

    def test_with_no_other_creature_it_is_not_offered(self, builder):
        """A cost gates the activation: Gisa cannot eat herself, and with nothing
        else to eat there is no activation -- the op spelling would offer one."""
        game, gisa = position(builder)
        assert gisa_action(game, gisa) is None


class TestPayingIt:
    def test_the_creature_is_gone_before_the_ability_resolves(self, builder):
        game, gisa = position(builder, BEAR)
        bear = only_oid(game, BEAR)

        activate(game, gisa, bear)

        assert game.state.stack, "the ability should still be on the stack"
        assert not game.state.objects[bear].on_battlefield
        assert zombies(game) == 0

    def test_it_makes_zombies_equal_to_the_sacrificed_creatures_power(self, builder):
        game, gisa = position(builder, GIANT)

        activate(game, gisa, only_oid(game, GIANT))
        resolve(game)

        assert zombies(game) == 6

    def test_it_reads_the_creature_that_was_sacrificed_not_another(self, builder):
        """The Bear was sacrificed; the Giant still beside Gisa is not X."""
        game, gisa = position(builder, BEAR, GIANT)

        activate(game, gisa, only_oid(game, BEAR))
        resolve(game)

        assert zombies(game) == 2
        assert game.state.objects[only_oid(game, GIANT)].on_battlefield

    def test_nothing_is_left_in_the_paid_object_records(self, builder):
        """A snapshot rides in the stack item's bindings; unlike Station's
        record it has nothing to fill in later and nothing to prune."""
        game, gisa = position(builder, BEAR)

        activate(game, gisa, only_oid(game, BEAR))

        assert not game.state.paid_objects


class TestXIsTheLastKnownPower:
    def test_a_pump_before_the_sacrifice_counts(self, builder):
        """608.2h: power as it last existed on the battlefield. Read off the
        graveyard card it would be the printed 2."""
        game, gisa = position(builder, BEAR)
        bear = only_oid(game, BEAR)
        pump(game.state, bear, 3, 3)

        activate(game, gisa, bear)
        resolve(game)

        assert zombies(game) == 5

    def test_counters_on_it_count(self, builder):
        """`reset_permanent_state` clears counters on the way out, so only a
        value taken before the move still has them."""
        game, gisa = position(builder, BEAR)
        bear = only_oid(game, BEAR)
        add_counters(game.state, bear, "+1/+1", 2)

        activate(game, gisa, bear)
        resolve(game)

        assert zombies(game) == 4

    def test_a_sacrificed_token_still_has_a_power(self, builder):
        """A token leaving the battlefield ceases to exist (704.5d); read
        through its oid afterwards it would make no Zombies at all."""
        game, gisa = position(builder, GIANT)
        activate(game, gisa, only_oid(game, GIANT))
        resolve(game)
        game.state.objects[gisa].tapped = False
        token = oids_of(game, ZOMBIE, 0)[0]
        pass_until(game, lambda g: gisa_action(g, gisa) is not None)

        activate(game, gisa, token)
        resolve(game)

        assert token not in game.state.objects
        assert zombies(game) == 5 + 2

    def test_a_negative_power_makes_no_zombies(self, builder):
        """107.1b: a negative number of tokens is zero."""
        game, gisa = position(builder, BEAR)
        bear = only_oid(game, BEAR)
        pump(game.state, bear, -5, 0)

        activate(game, gisa, bear)
        resolve(game)

        assert zombies(game) == 0


GISA_MODEL = {
    "id": "t_gisa_guard",
    "name": "Test Gisa Guard",
    "oracle_text": "Sacrifice another creature: Create X Zombies.",
    "types": ["Creature"],
    "power": 1,
    "toughness": 1,
    "abilities": [
        {
            "kind": "activated",
            "text": "Sacrifice another creature: Create X Zombies.",
            "cost": {"sacrifice": {"types": ["Creature"], "exclude_self": True, "as": "eaten"}},
            "effects": [
                {
                    "op": "create_token",
                    "token": ZOMBIE,
                    "amount": {"power_of": {"binding": "eaten"}},
                }
            ],
        }
    ],
}


def _with_sacrifice(selector: dict) -> dict:
    card = copy.deepcopy(GISA_MODEL)
    card["abilities"][0]["cost"]["sacrifice"] = selector
    return card


class TestLoadTimeGuards:
    def test_the_named_cost_loads(self):
        card = compile_card(CardModel.model_validate(GISA_MODEL))
        assert card.abilities[0].cost.sacrifice["as"] == "eaten"

    def test_an_empty_name_is_refused(self):
        with pytest.raises(DslError, match="a binding name"):
            compile_card(CardModel.model_validate(_with_sacrifice({"types": ["Creature"], "as": ""})))

    def test_naming_one_of_several_sacrificed_permanents_is_refused(self):
        """"The sacrificed creature" is one creature."""
        with pytest.raises(DslError, match="exactly one"):
            compile_card(
                CardModel.model_validate(
                    _with_sacrifice({"types": ["Creature"], "count": 2, "as": "eaten"})
                )
            )

    def test_naming_it_on_a_spells_additional_cost_is_refused(self):
        """Only an activated ability's effects receive what its cost named; on
        a spell the name would bind nothing and every read of it would be 0."""
        spell = {
            "id": "t_gisa_spell",
            "name": "Test Gisa Spell",
            "oracle_text": "As an additional cost, sacrifice a creature.",
            "mana_cost": "{B}",
            "types": ["Sorcery"],
            "additional_cost": {"sacrifice": {"types": ["Creature"], "as": "eaten"}},
            "spell_effects": [
                {
                    "op": "create_token",
                    "token": ZOMBIE,
                    "amount": {"power_of": {"binding": "eaten"}},
                }
            ],
        }
        with pytest.raises(DslError, match="only an activated ability"):
            compile_card(CardModel.model_validate(spell))
