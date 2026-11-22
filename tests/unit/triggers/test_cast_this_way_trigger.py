"""`playable_cast_trigger` -- "When you cast a spell this way, …" off a play permission.

    The Ruinous Powers -- "At the beginning of your upkeep, choose an opponent
    at random. Exile the top card of that player's library. Until end of turn,
    you may play that card and you may spend mana as though it were mana of any
    color to cast it. When you cast a spell this way, its owner loses life
    equal to its mana value."

"This way" names the permission, not a zone or an event. A `spell_cast` trigger
filtered to spells cast from exile is the near miss: it fires for a foretold or
plotted card and for a card another effect let you cast, and it cannot be
scoped to *this* grant. So the trigger is linked to the grant (603.12's shape --
the effect says what happens when the thing it allowed is done): the permission
names a ``kind: "reflexive"`` ability on its card, and the cast made under it
puts that ability on the stack above the spell (603.3), bound to the spell as
``subject``.

What must hold:

- casting the card under the permission triggers it, once, and its owner -- the
  opponent whose library it came from, not the caster -- loses its mana value;
- the same permission without the key, a land played under it (a land is
  played, never cast), and a spell cast from hand all trigger nothing;
- it rides on all three grant sites: `look_at_top`, `exile` and
  `grant_playable`;
- the loader refuses the key off a permission, an id naming no reflexive
  ability, and a permission handed to the card's owner ("when **you** cast").
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from tests.conftest import settle

RAID = "t_ctw_raid"  # look_at_top's permission with the trigger
PLAIN = "t_ctw_plain_raid"  # the same permission without it
HEIST = "t_ctw_heist"  # the trigger on exile's own permission
GRANT = "t_ctw_grant"  # the trigger on grant_playable
BEAR = "t_bear"  # {1}{G}, mana value 2


def raid(builder, theirs: str = BEAR, *, spell: str = RAID, hand=(), lands=("swamp",) * 5):
    """Player 0 casts ``spell`` off a Swamp and lets it resolve, the rest left."""
    game = (
        builder(players=2)
        .battlefield(0, list(lands))
        .hand(0, [spell, *hand])
        .library(1, [theirs] + ["island"] * 8)
        .active(0)
        .max_turns(1)
        .build()
    )
    game.apply(casts(game, spell)[0])
    settle(game)
    return game


def casts(game, def_id: str) -> list:
    state = game.state
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and a.source is not None
        and state.objects[a.source].def_id == def_id
    ]


def lives(game) -> tuple[int, int]:
    return game.state.players[0].life, game.state.players[1].life


def cast_and_settle(game, def_id: str) -> None:
    game.apply(casts(game, def_id)[0])
    settle(game)


class TestCastingThisWay:
    def test_its_owner_loses_its_mana_value(self, builder):
        game = raid(builder)
        before = lives(game)
        cast_and_settle(game, BEAR)
        assert lives(game) == (before[0], before[1] - 2), (
            "the bear is player 1's card: its owner loses 2, the caster nothing"
        )

    def test_it_resolves_before_the_spell(self, builder):
        """603.3: on the stack above the spell, so the life is lost first."""
        game = raid(builder)
        mark = len(game.state.events)
        cast_and_settle(game, BEAR)
        kinds = [e.type for e in game.state.events[mark:]]
        fired = [
            e for e in game.state.events[mark:]
            if e.type == EventType.ABILITY_TRIGGERED and e.data.get("trigger") == "cast_this_way"
        ]
        assert len(fired) == 1 and fired[0].player == 0, "'you' cast it: the trigger is yours"
        assert kinds.index(EventType.LIFE_LOST) < kinds.index(EventType.ENTERS_BATTLEFIELD)

    def test_it_fires_once_per_cast(self, builder):
        game = raid(builder)
        before = lives(game)
        cast_and_settle(game, BEAR)
        settle(game)
        assert lives(game)[1] == before[1] - 2


class TestNotThisWay:
    def test_the_plain_permission_triggers_nothing(self, builder):
        game = raid(builder, spell=PLAIN)
        before = lives(game)
        cast_and_settle(game, BEAR)
        assert lives(game) == before

    def test_a_land_played_this_way_is_not_cast(self, builder):
        game = raid(builder, theirs="forest")
        before = lives(game)
        land = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.PLAY_LAND and game.state.objects[a.source].def_id == "forest"
        )
        game.apply(land)
        settle(game)
        assert lives(game) == before, "601: a land is played, never cast"

    def test_a_spell_from_hand_is_not_cast_this_way(self, builder):
        game = raid(builder, theirs="island", hand=(BEAR,), lands=("swamp", "forest", "forest"))
        before = lives(game)
        cast_and_settle(game, BEAR)
        assert lives(game) == before


class TestEveryGrantSite:
    def test_on_exile(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["swamp"] * 5)
            .hand(0, [HEIST])
            .graveyard(1, [BEAR])
            .active(0)
            .max_turns(1)
            .build()
        )
        game.apply(casts(game, HEIST)[0])
        settle(game)
        before = lives(game)
        cast_and_settle(game, BEAR)
        assert lives(game) == (before[0], before[1] - 2)

    def test_on_grant_playable(self, builder):
        game = raid(builder, spell=GRANT)
        before = lives(game)
        cast_and_settle(game, BEAR)
        assert lives(game) == (before[0], before[1] - 2)


def _raid_card(**permission) -> dict:
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "Probe. When you cast a spell this way, probe.",
        "mana_cost": "{B}",
        "types": ["Sorcery"],
        "spell_effects": [
            {"op": "look_at_top", "player": "each_opponent", "amount": {"const": 1},
             "objects": {"count": "all"}, "destination": "exile", **permission}
        ],
        "abilities": [
            {"kind": "reflexive", "id": "ruin",
             "text": "When you cast a spell this way, probe.",
             "effects": [{"op": "lose_life", "player": "you", "amount": {"const": 1}}]}
        ],
    }


class TestTheLoader:
    def test_it_needs_a_permission(self):
        with pytest.raises(DslError, match="needs one"):
            compile_card(CardModel.model_validate(_raid_card(playable_cast_trigger="ruin")))

    def test_it_must_name_a_reflexive_ability(self):
        card = _raid_card(playable="this_turn", playable_cast_trigger="other")
        with pytest.raises(DslError, match="no reflexive ability"):
            compile_card(CardModel.model_validate(card))

    def test_the_reflexive_ability_is_wired(self):
        compile_card(
            CardModel.model_validate(_raid_card(playable="this_turn", playable_cast_trigger="ruin"))
        )

    def test_not_beside_a_permission_for_the_owner(self):
        card = {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "x",
            "mana_cost": "{B}",
            "types": ["Sorcery"],
            "targets": [
                {"id": "t1", "kind": "card_in_graveyard", "count": 1,
                 "selector": {"zone": "graveyard", "player": "opponent"}}
            ],
            "spell_effects": [
                {"op": "exile", "objects": {"target": "t1"}, "playable": "while_exiled",
                 "playable_by": "owner", "playable_cast_only": True,
                 "playable_cast_trigger": "ruin"}
            ],
            "abilities": [
                {"kind": "reflexive", "id": "ruin", "text": "x",
                 "effects": [{"op": "lose_life", "player": "you", "amount": {"const": 1}}]}
            ],
        }
        with pytest.raises(DslError, match="playable_by: owner"):
            compile_card(CardModel.model_validate(card))
