"""Adding a token to a token creation: "those tokens plus an additional …".

    Stridehangar Automaton: "If one or more artifact tokens would be created
    under your control, those tokens plus an additional 1/1 colorless Thopter
    artifact creature token with flying are created instead."

A 614.1a replacement of the creation, and the third mode of the
`replace_token_creation` static beside `create_instead` (which tokens) and
`token_multiplier` (how many of those tokens): `and_create` keeps every token
about to be made and adds one of each listed id. Neither existing mode says it:
a doubler turns a Treasure into two Treasures, not a Treasure and a Thopter, and
a substitution loses the Treasure. The near miss is a `token_created` trigger,
which uses the stack, makes the Thopter later, makes one per token rather than
one per creation, and -- the Thopter being an artifact token -- re-triggers on
its own output forever.

The rules claims:

* **Once per creation event, not per token.** "One or more artifact tokens" is
  the event; three Treasures bring one Thopter.
* **Part of the same event, not a trigger.** The Thopter arrives inside the one
  `create_token` call, in the same `token_created` batch, and nothing goes on
  the stack.
* **614.5.** A Thopter being created is an artifact token creation, so the
  Automaton adds one more -- once, and then the event is finished. Two
  Automatons are two replacements, each applied once: two extra Thopters.
* **616.1, the controller's order.** Against Anointed Procession / Doubling
  Season the order shows (the printed ruling: Thopter first gives two Treasures
  and two Thopters, doubling first two Treasures and one Thopter). The engine
  cannot ask from inside `create_token`, so the addition always goes first, the
  order that never leaves fewer tokens, and battlefield order does not change it.
* **The rulings on what the Thopter shares.** It has none of the abilities the
  other tokens were created with (an embalm-style override is dropped), but it
  is tapped and attacking when they are, and a later "that token" names it too.
* **Under your control.** Only the Automaton's controller's tokens.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.loader.linking import validate_token_references
from commanderblitz.cards.registry import CardRegistry, authored_card_paths
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import create_token
from commanderblitz.engine.sandbox import GameBuilder
from commanderblitz.engine.structs import CombatState
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid

AUTOMATON = "stridehangar_probe"
SECOND = "stridehangar_probe_two"
DOUBLING_SEASON = "doubling_season"
VISITATION = "divine_visitation"
MANUFACTOR = "academy_manufactor"
THOPTER = "thopter_1_1_c_flying"
TREASURE = "treasure_token"
CLUE = "clue_token"
FOOD = "food_token"
SOLDIER = "human_soldier_1_1_w"
ANGEL = "angel_4_4_w_flying_vigilance"

LINE = (
    "If one or more artifact tokens would be created under your control, those "
    "tokens plus an additional 1/1 colorless Thopter artifact creature token with "
    "flying are created instead."
)


def automaton(card_id: str = AUTOMATON, **extra) -> dict:
    static = {
        "kind": "static",
        "text": LINE,
        "effect": "replace_token_creation",
        "affects_token": {"types": ["Artifact"]},
        "and_create": [THOPTER],
        **extra,
    }
    return {
        "id": card_id,
        "name": "Stridehangar Automaton",
        "mana_cost": "{3}",
        "types": ["Artifact", "Creature"],
        "subtypes": ["Construct"],
        "power": 2,
        "toughness": 2,
        "abilities": [static],
    }


def with_cards(*specs: dict) -> CardRegistry:
    cards = {
        card.id: card for card in CardRegistry.from_paths(authored_card_paths(Path("data/cards")))
    }
    for spec in specs:
        compiled = compile_card(CardModel.model_validate(spec))
        cards[compiled.id] = compiled
    validate_token_references(cards)
    return CardRegistry(cards)


@pytest.fixture(scope="module")
def pool() -> CardRegistry:
    """The shipped pool (Doubling Season, Divine Visitation, Academy Manufactor)
    plus two Automatons compiled through every loader guard a card file meets."""
    return with_cards(automaton(), automaton(SECOND))


def board(pool: CardRegistry, mine: list[str], theirs: list[str] = ()):
    builder = GameBuilder(pool, players=2, seed=0).battlefield(0, list(mine))
    if theirs:
        builder = builder.battlefield(1, list(theirs))
    return builder.build(advance=False)


def tokens(game, pid: int | None = None) -> Counter:
    return Counter(obj.def_id for obj in game.state.battlefield_objects(pid) if obj.is_token)


class TestThoseTokensPlusAThopter:
    def test_a_treasure_brings_a_thopter(self, pool):
        game = board(pool, [AUTOMATON])
        create_token(game.state, TREASURE, 0, 1)
        assert tokens(game) == {TREASURE: 1, THOPTER: 1}

    def test_one_thopter_per_creation_not_per_token(self, pool):
        game = board(pool, [AUTOMATON])
        create_token(game.state, TREASURE, 0, 3)
        assert tokens(game) == {TREASURE: 3, THOPTER: 1}

    def test_two_creations_are_two_thopters(self, pool):
        game = board(pool, [AUTOMATON])
        create_token(game.state, TREASURE, 0, 1)
        create_token(game.state, CLUE, 0, 1)
        assert tokens(game) == {TREASURE: 1, CLUE: 1, THOPTER: 2}

    def test_a_nonartifact_token_brings_nothing(self, pool):
        game = board(pool, [AUTOMATON])
        create_token(game.state, SOLDIER, 0, 2)
        assert tokens(game) == {SOLDIER: 2}

    def test_without_the_automaton_nothing_is_added(self, pool):
        game = board(pool, [])
        create_token(game.state, TREASURE, 0, 1)
        assert tokens(game) == {TREASURE: 1}


class TestPartOfTheSameEvent:
    def test_the_thopter_is_in_the_same_token_created_batch(self, pool):
        game = board(pool, [AUTOMATON])
        mark = len(game.state.events)
        create_token(game.state, TREASURE, 0, 1)
        made = [e for e in game.state.events[mark:] if e.type == "token_created"]
        assert [e.data.get("card") for e in made] == [TREASURE, THOPTER]
        assert len({e.data.get("batch") for e in made}) == 1

    def test_nothing_goes_on_the_stack(self, pool):
        game = board(pool, [AUTOMATON])
        create_token(game.state, TREASURE, 0, 1)
        assert not game.state.stack
        assert not game.state.pending_triggers


class TestOncePerReplacement:
    """614.5: each Automaton applies once to the event as the last one left it."""

    def test_a_thopter_creation_brings_one_more_thopter_and_stops(self, pool):
        game = board(pool, [AUTOMATON])
        create_token(game.state, THOPTER, 0, 1)
        assert tokens(game) == {THOPTER: 2}

    def test_two_automatons_add_two_thopters(self, pool):
        game = board(pool, [AUTOMATON, SECOND])
        create_token(game.state, TREASURE, 0, 1)
        assert tokens(game) == {TREASURE: 1, THOPTER: 2}


class TestTheControllersOrder:
    """616.1, decided the way that never leaves fewer tokens: the addition first."""

    @pytest.mark.parametrize(
        "order", [[AUTOMATON, DOUBLING_SEASON], [DOUBLING_SEASON, AUTOMATON]]
    )
    def test_beside_a_doubler_the_thopter_is_doubled_too(self, pool, order):
        game = board(pool, order)
        create_token(game.state, TREASURE, 0, 1)
        assert tokens(game) == {TREASURE: 2, THOPTER: 2}

    @pytest.mark.parametrize("order", [[AUTOMATON, VISITATION], [VISITATION, AUTOMATON]])
    def test_a_visitation_turns_the_thopter_into_an_angel(self, pool, order):
        game = board(pool, order)
        create_token(game.state, TREASURE, 0, 1)
        assert tokens(game) == {TREASURE: 1, ANGEL: 1}

    @pytest.mark.parametrize("order", [[AUTOMATON, VISITATION], [VISITATION, AUTOMATON]])
    def test_a_thopter_into_a_visitation_is_two_angels(self, pool, order):
        """Visitation first would leave one Angel and no artifact token for the
        Automaton to see; the addition first gives two."""
        game = board(pool, order)
        create_token(game.state, THOPTER, 0, 1)
        assert tokens(game) == {ANGEL: 2}

    @pytest.mark.parametrize("order", [[AUTOMATON, MANUFACTOR], [MANUFACTOR, AUTOMATON]])
    def test_beside_a_manufactor_one_of_each_and_one_thopter(self, pool, order):
        game = board(pool, order)
        create_token(game.state, TREASURE, 0, 1)
        assert tokens(game) == {CLUE: 1, FOOD: 1, TREASURE: 1, THOPTER: 1}


class TestWhatTheThopterShares:
    def test_tapped_and_attacking_like_the_rest(self, pool):
        game = board(pool, [AUTOMATON])
        game.state.combat = CombatState(declaring_player=0)
        made = create_token(game.state, TREASURE, 0, 1, tapped=True, attacking=1)
        thopter = next(oid for oid in made if game.state.objects[oid].def_id == THOPTER)
        assert game.state.objects[thopter].tapped
        assert game.state.combat.attackers.get(thopter) == 1

    def test_not_the_overrides_the_other_tokens_were_created_with(self, pool):
        game = board(pool, [AUTOMATON])
        made = create_token(game.state, TREASURE, 0, 1, overrides={"colors": ["W"]})
        by_id = {game.state.objects[oid].def_id: oid for oid in made}
        assert chars(game.state, by_id[TREASURE]).colors == frozenset({"W"})
        assert chars(game.state, by_id[THOPTER]).colors == frozenset()

    def test_that_token_names_the_thopter_too(self, pool):
        """ "Exile that token at end of combat" applies to both (the ruling)."""
        game = board(pool, [AUTOMATON])
        ctx = EffectContext(state=game.state, controller=0, source_oid=None)
        list(execute(ctx, [{"op": "create_token", "token": TREASURE, "as": "made"}]))
        named = {game.state.objects[oid].def_id for oid in ctx.bindings["made"]}
        assert named == {TREASURE, THOPTER}


class TestUnderYourControl:
    def test_an_opponents_artifact_token_brings_nothing(self, pool):
        game = board(pool, [AUTOMATON])
        create_token(game.state, TREASURE, 1, 1)
        assert tokens(game, 1) == {TREASURE: 1}
        assert tokens(game, 0) == {}

    def test_an_opponents_effect_giving_you_a_treasure_brings_you_a_thopter(self, pool):
        game = board(pool, [AUTOMATON])
        ctx = EffectContext(state=game.state, controller=1, source_oid=None)
        list(execute(ctx, [{"op": "create_token", "token": TREASURE, "controller": "opponent"}]))
        assert tokens(game, 0) == {TREASURE: 1, THOPTER: 1}

    def test_it_stops_when_the_automaton_leaves(self, pool):
        game = board(pool, [AUTOMATON])
        move_object(game.state, only_oid(game, AUTOMATON), Zone.GRAVEYARD, to_player=0)
        create_token(game.state, TREASURE, 0, 1)
        assert tokens(game) == {TREASURE: 1}


class TestTheCardFileMustSayWhatItMeans:
    def test_it_compiles(self):
        with_cards(automaton())

    @pytest.mark.parametrize(
        "extra", [{"token_multiplier": 2}, {"create_instead": [TREASURE]}]
    )
    def test_a_second_mode_is_refused(self, extra):
        with pytest.raises(DslError, match="not both"):
            compile_card(CardModel.model_validate(automaton(**extra)))

    def test_an_unknown_token_is_refused(self):
        spec = automaton(and_create=["no_such_token"])
        with pytest.raises(DslError, match="and_create references unknown card"):
            with_cards(spec)

    def test_a_real_card_is_refused(self):
        spec = automaton(and_create=["grizzly_bears"])
        with pytest.raises(DslError, match="not marked as a token"):
            with_cards(spec)
