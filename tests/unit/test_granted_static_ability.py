"""Handing a *static* ability to another permanent, and saying "you own".

    Inspiring Leader — Legendary Enchantment — Background
    "Commander creatures you own have "Creature tokens you control get +2/+2.""

One printed sentence, two things the DSL could not say, and each one blocked the
card on its own.

**A granted static.** `grantable_abilities` refused anything but a triggered or
a mana ability, so the honest wording was a load error rather than a silent
no-op. The near miss that *did* load is a `buff` on the Background itself under
an `{"exists": {"is_commander": true}}` condition, and it is a different card
three ways: it does not stack per commander creature (a Background deck
routinely has two, which the printed card pays for and a condition does not), it
pumps the *Background controller's* tokens rather than each granted commander's
controller's, and it does not travel with a commander that changes hands. All
three are asserted below, because all three are the difference between this card
and one that merely looks like it.

**"You own".** `STATIC_FILTER_KEYS` had `controller` and no `owner`, and
`owner` lived in exactly one place the `affects` of a static could not reach.
Rule 903.3 is why the substitution is not close enough: on a commander,
ownership is the relation the rules use, and the two words part company on
precisely the boards commanders are played on — a commander an opponent stole is
still one you own, and one you stole is not.

**Why this cannot break layers-lite** (`docs/adr/0001-layers-lite.md`). A
granted static needs no new layer and gets none: `characteristics.abilities_of`
appends the ability to the *recipient's* list and `_battlefield_statics` walks
that list, so the copy arrives sourced on the recipient and is applied in the
same fixed layer as a printed one. The one edge that could have become a cycle —
a static granting a static — is severed where it already was: `_ability_statics`
gathers `grant_ability` and `lose_all_abilities` off **printed** faces, so a
granted one is never collected at all, and the loader refuses it by name rather
than letting the card load clean and do nothing. `TestWhatMayBeGranted` is that
refusal, and it is the load-bearing test in this file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.loader.vocabulary import (
    GRANTABLE_STATIC_EFFECTS,
    STATIC_EFFECTS,
    UNGRANTABLE_STATIC_EFFECTS,
)
from automtg.cards.registry import CardRegistry, authored_card_paths
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import ABILITY_STATICS, abilities_of, chars
from automtg.engine.enums import Keyword
from automtg.engine.errors import DslError
from automtg.engine.primitives import change_control, create_token
from automtg.engine.sandbox import GameBuilder

LEADER = "inspiring_leader"
BEAR = "granted_static_bear"
SOLDIER = "human_soldier_1_1_w"

#: The quoted half of the printed line — what a commander creature is given.
QUOTED_ANTHEM = {
    "kind": "static",
    "text": "Creature tokens you control get +2/+2.",
    "effect": "buff",
    "affects": {"types": ["Creature"], "is_token": True, "controller": "you"},
    "power": 2,
    "toughness": 2,
}


def leader(*, grantable: dict | None = None, **affects) -> dict:
    """Inspiring Leader, with its filter and its quoted ability both openable.

    Written here rather than in `data/cards/`: the claim under test is that the
    *DSL* can express the card, and a card file is the authoring pipeline's
    business. It still goes through `compile_card`, so every loader guard a real
    card file would meet is met here.
    """
    return {
        "id": LEADER,
        "name": "Inspiring Leader",
        "mana_cost": "{2}{W}",
        "types": ["Enchantment"],
        "supertypes": ["Legendary"],
        "subtypes": ["Background"],
        "oracle_text": (
            'Commander creatures you own have "Creature tokens you control get +2/+2."'
        ),
        "grantable_abilities": [grantable or QUOTED_ANTHEM],
        "abilities": [
            {
                "kind": "static",
                "text": (
                    "Commander creatures you own have "
                    '"Creature tokens you control get +2/+2."'
                ),
                "effect": "grant_ability",
                "affects": {
                    "types": ["Creature"],
                    "is_commander": True,
                    **(affects or {"owner": "you"}),
                },
                "ability": 0,
            }
        ],
    }


BEAR_CARD = {
    "id": BEAR,
    "name": "Granted Static Bear",
    "mana_cost": "{1}{G}",
    "types": ["Creature"],
    "subtypes": ["Bear"],
    "power": 2,
    "toughness": 2,
}


def pool_with(*specs: dict) -> CardRegistry:
    cards = {
        card.id: card
        for card in CardRegistry.from_paths(authored_card_paths(Path("data/cards")))
    }
    for spec in specs:
        compiled = compile_card(CardModel.model_validate(spec))
        cards[compiled.id] = compiled
    return CardRegistry(cards)


@pytest.fixture(scope="module")
def pool() -> CardRegistry:
    return pool_with(leader(), BEAR_CARD)


def board(pool: CardRegistry, *, commanders: int = 0, bears: int = 0):
    """A Background and some creatures on seat 0, and the token it is about.

    Returns ``(game, token_oid, commander_oids)``. The commander creatures are
    ordinary permanents with ``is_commander`` set, which is what a commander cast
    from the command zone is — `GameBuilder.commander` puts one in the command
    zone, and a Background's line is about the ones that made it to the board.
    """
    game = (
        GameBuilder(pool, players=2, seed=0)
        .battlefield(0, [LEADER, *[BEAR] * (commanders + bears)])
        .build(advance=False)
    )
    creatures = [o for o in game.state.battlefield_objects() if o.def_id == BEAR]
    for obj in creatures[:commanders]:
        obj.is_commander = True
    game.state.bump_chars()
    token = create_token(game.state, SOLDIER, 0, 1)[0]
    return game, token, [o.oid for o in creatures[:commanders]]


def size(game, oid: int) -> tuple[int, int]:
    c = chars(game.state, oid)
    return c.power, c.toughness


class TestTheQuotedAbilityIsTheRecipientS:
    """The granted static is applied as an ability *of the commander creature*."""

    def test_no_commander_creature_means_no_anthem(self, pool):
        game, token, _ = board(pool)
        assert size(game, token) == (1, 1), "the Background alone pumps nothing"

    def test_one_commander_creature_gives_the_tokens_plus_two(self, pool):
        game, token, _ = board(pool, commanders=1)
        assert size(game, token) == (3, 3)

    def test_two_commander_creatures_stack(self, pool):
        """The claim the near-miss condition cannot make.

        A `buff` on the Background under `{"exists": {"is_commander": true}}` is
        one anthem however many commanders are out. The printed card grants the
        ability to *each* of them, and two copies of an anthem are two anthems.
        """
        game, token, _ = board(pool, commanders=2)
        assert size(game, token) == (5, 5)

    def test_a_non_commander_creature_is_not_granted_it(self, pool):
        game, token, _ = board(pool, commanders=1, bears=2)
        assert size(game, token) == (3, 3), "only the commander creature grants it"

    def test_the_ability_appears_on_the_commander_creature(self, pool):
        game, _, commanders = board(pool, commanders=1)
        granted = abilities_of(game.state, commanders[0])
        assert [a.is_static for a in granted] == [True]
        assert granted[0].static["effect"] == "buff"

    def test_the_background_itself_does_not_gain_it(self, pool):
        """`affects` names Creatures, and the Background is an Enchantment."""
        game, _, _ = board(pool, commanders=1)
        leader_oid = next(
            o.oid for o in game.state.battlefield_objects() if o.def_id == LEADER
        )
        assert [a.static["effect"] for a in abilities_of(game.state, leader_oid)] == [
            "grant_ability"
        ]

    def test_it_stops_the_moment_the_creature_stops_being_a_commander(self, pool):
        """A static is on for exactly as long as its granter's filter matches."""
        game, token, commanders = board(pool, commanders=1)
        assert size(game, token) == (3, 3)
        game.state.objects[commanders[0]].is_commander = False
        game.state.bump_chars()
        assert size(game, token) == (1, 1)


class TestWhoseTokensGetPumped:
    """"You" inside the quoted ability is the *commander creature's* controller."""

    def test_an_opponents_tokens_are_not_pumped(self, pool):
        game, token, _ = board(pool, commanders=1)
        theirs = create_token(game.state, SOLDIER, 1, 1)[0]
        assert size(game, token) == (3, 3)
        assert size(game, theirs) == (1, 1)

    def test_a_stolen_commander_creature_pumps_its_thiefs_tokens(self, pool):
        """The claim that separates a granted ability from an anthem on the granter.

        The Background stays on your side of the table and goes on granting —
        you still *own* the commander — but the ability now belongs to a
        permanent your opponent controls, so its "you" is them.
        """
        game, token, commanders = board(pool, commanders=1)
        theirs = create_token(game.state, SOLDIER, 1, 1)[0]
        change_control(game.state, commanders[0], 1)
        game.state.bump_chars()

        assert size(game, theirs) == (3, 3), "the anthem went with the creature"
        assert size(game, token) == (1, 1), "and stopped applying to yours"


class TestOwnerIsNotController:
    """903.3 — on a commander, ownership is the relation, and it is not control."""

    def test_a_commander_you_own_still_counts_once_stolen(self, pool):
        game, _token, commanders = board(pool, commanders=1)
        change_control(game.state, commanders[0], 1)
        game.state.bump_chars()
        theirs = create_token(game.state, SOLDIER, 1, 1)[0]
        assert size(game, theirs) == (3, 3), "still a commander creature you own"

    def test_a_commander_you_merely_control_is_not_granted_it(self, pool):
        """The case `controller: "you"` gets wrong, in the other direction."""
        game = (
            GameBuilder(pool, players=2, seed=0)
            .battlefield(0, [LEADER])
            .battlefield(1, [BEAR])
            .build(advance=False)
        )
        theirs = next(
            o for o in game.state.battlefield_objects() if o.def_id == BEAR
        )
        theirs.is_commander = True
        change_control(game.state, theirs.oid, 0)
        game.state.bump_chars()
        token = create_token(game.state, SOLDIER, 0, 1)[0]

        assert theirs.controller == 0 and theirs.owner == 1
        assert size(game, token) == (1, 1), (
            "you control it, you do not own it -- `controller: \"you\"` is the "
            "near miss and would read (3, 3) here"
        )

    def test_controller_you_is_the_near_miss_and_reads_the_other_way(self, pool):
        """Both directions in one place, so the two words cannot be conflated."""
        controller_pool = pool_with(leader(controller="you"), BEAR_CARD)
        game = (
            GameBuilder(controller_pool, players=2, seed=0)
            .battlefield(0, [LEADER])
            .battlefield(1, [BEAR])
            .build(advance=False)
        )
        theirs = next(o for o in game.state.battlefield_objects() if o.def_id == BEAR)
        theirs.is_commander = True
        change_control(game.state, theirs.oid, 0)
        game.state.bump_chars()
        token = create_token(game.state, SOLDIER, 0, 1)[0]
        assert size(game, token) == (3, 3)

    def test_owner_opponent_is_the_mirror(self, pool):
        opponent_pool = pool_with(leader(owner="opponent"), BEAR_CARD)
        game = (
            GameBuilder(opponent_pool, players=2, seed=0)
            .battlefield(0, [LEADER])
            .battlefield(1, [BEAR])
            .build(advance=False)
        )
        theirs = next(o for o in game.state.battlefield_objects() if o.def_id == BEAR)
        theirs.is_commander = True
        game.state.bump_chars()
        token = create_token(game.state, SOLDIER, 1, 1)[0]
        assert size(game, token) == (3, 3)

    def test_owner_does_not_quietly_impose_a_control_clause(self, pool):
        """Writing `owner` switches the defaulted `controller: "you"` off.

        Read the other way round -- `owner` *plus* the default -- the filter
        would mean "you own it and you control it", which drops the stolen
        commander, i.e. the only case the key was written for. Asserted as a
        filter fact rather than through a card, so it stays true of every static
        that ever writes `owner`.
        """
        game, _token, commanders = board(pool, commanders=1)
        change_control(game.state, commanders[0], 1)
        game.state.bump_chars()
        assert abilities_of(game.state, commanders[0])[-1].static["effect"] == "buff"

    def test_an_unknown_owner_is_a_load_error(self):
        with pytest.raises(DslError, match="owner"):
            compile_card(CardModel.model_validate(leader(owner="anybody")))


class TestWhatMayBeGranted:
    """The gate is exactly "statics read through `_battlefield_statics`"."""

    def test_the_three_families_partition_the_static_effects(self):
        assert GRANTABLE_STATIC_EFFECTS | UNGRANTABLE_STATIC_EFFECTS == STATIC_EFFECTS
        assert not (GRANTABLE_STATIC_EFFECTS & UNGRANTABLE_STATIC_EFFECTS)

    def test_the_ability_statics_are_refused(self):
        """A granted `grant_ability` is the cycle layers-lite exists not to have.

        `_ability_statics` reads printed faces -- it must, or it and
        `abilities_of` would call each other forever -- so a granted one would
        never be collected and the card would load clean and do nothing.
        """
        assert set(ABILITY_STATICS) <= UNGRANTABLE_STATIC_EFFECTS
        for effect in ABILITY_STATICS:
            spec = leader(
                grantable={
                    "kind": "static",
                    "text": "granted grant",
                    "effect": effect,
                    "affects": {"types": ["Creature"]},
                    **({"ability": 0} if effect == "grant_ability" else {}),
                }
            )
            with pytest.raises(DslError, match="printed faces"):
                compile_card(CardModel.model_validate(spec))

    def test_a_player_wide_static_is_refused(self):
        """`_active_player_statics` walks printed faces too."""
        spec = leader(
            grantable={
                "kind": "static",
                "text": "You have no maximum hand size.",
                "effect": "no_hand_limit",
                "affects_player": "you",
            }
        )
        with pytest.raises(DslError, match="printed faces"):
            compile_card(CardModel.model_validate(spec))

    def test_an_ordinary_layer_static_is_accepted(self):
        """`grant_keyword` sits in layer 2 whoever is sourcing it."""
        spec = leader(
            grantable={
                "kind": "static",
                "text": "Creatures you control have flying.",
                "effect": "grant_keyword",
                "affects": {"types": ["Creature"], "controller": "you"},
                "keywords": [Keyword.FLYING.value],
            }
        )
        card = compile_card(CardModel.model_validate(spec))
        assert card.grantable_abilities[0].static["effect"] == "grant_keyword"

    def test_of_the_chosen_type_is_refused(self):
        """The substitution reads the *source*, and a grant moves the source.

        An author writing it means the granter; the engine would read the
        recipient, which has chosen nothing, so the filter matches nobody.
        """
        spec = leader(
            grantable={
                "kind": "static",
                "text": "Creatures of the chosen type get +1/+1.",
                "effect": "buff",
                "affects": {
                    "types": ["Creature"],
                    "subtypes": [{"chosen_type_of": "self"}],
                },
                "power": 1,
                "toughness": 1,
            }
        )
        with pytest.raises(DslError, match="chosen_type_of"):
            compile_card(CardModel.model_validate(spec))


class TestTheGrantMustPointAtSomething:
    """Both readers index the list and both skip a miss, so both are checked."""

    def test_an_out_of_range_static_grant_is_a_load_error(self):
        spec = leader()
        spec["abilities"][0]["ability"] = 1
        with pytest.raises(DslError, match="grantable_abilities"):
            compile_card(CardModel.model_validate(spec))

    def test_the_one_shot_op_may_hand_over_a_static(self):
        """It may **now**. This used to be refused, and the reason given was
        that "the op's grants are pointers `_battlefield_statics` never walks".

        That walk reads the derived list, and `_op_granted_abilities` puts an
        op-granted static on it -- so the premise is gone and the refusal with
        it. The Irencrag is the card that needed the one-shot form, and
        `tests/unit/test_grant_static_op.py` measures that the granted static
        actually applies rather than merely loading.
        """
        spec = leader()
        spec["abilities"].append(
            {
                "kind": "activated",
                "text": "{1}: Target creature gains the anthem.",
                "cost": {"mana": "{1}"},
                "targets": [
                    {
                        "id": "t1",
                        "kind": "permanent",
                        "selector": {"zone": "battlefield", "types": ["Creature"]},
                        "count": 1,
                    }
                ],
                "effects": [
                    {"op": "grant_ability", "ability": 0, "objects": {"target": "t1"}}
                ],
            }
        )
        compile_card(CardModel.model_validate(spec))
