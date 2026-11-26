"""The Smoke Blessing token: an Aura whose one trigger names two players.

    Smoke Spirits' Aid -- "For each of up to X target creatures, create a red
    Aura enchantment token named Smoke Blessing attached to that creature.
    Those tokens have enchant creature and 'When enchanted creature dies, it
    deals 1 damage to its controller and you create a Treasure token.'"

The card is only right when each player is read from the right object:

- **"its controller"** is the dead creature's controller, the player who takes
  the 1 damage, read as the creature last existed on the battlefield (603.10a).
- **"you"** is the Smoke Blessing's controller (109.5), who gets the Treasure --
  not the creature's controller, when the spell put the token on an opponent's
  creature.

`create_token` with `attached_to` already makes an Aura token on somebody
else's creature (`test_contract_token.py`); this is the token itself, a `dies`
trigger filtered `attached`, a `damage` to `controller_of: "subject"` and a
`create_token` for `you`.
"""

from __future__ import annotations

from commanderblitz.cards.registry import CardRegistry
from commanderblitz.engine.enums import Step
from commanderblitz.engine.primitives import attach, create_token
from commanderblitz.engine.zones import destroy
from tests.conftest import oids_of, only_oid, settle

BLESSING = "smoke_blessing"
BEAR = "t_bear"  # vanilla 2/2
TREASURE = "treasure_token"


def board(builder):
    """Player 0's turn, player 1's bear wearing player 0's Smoke Blessing."""
    game = (
        builder(players=2)
        .battlefield(1, ["forest"] * 2 + [BEAR])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    bear = only_oid(game, BEAR, 1)
    (blessing,) = create_token(game.state, BLESSING, 0)
    attach(game.state, blessing, bear)
    return game, bear, blessing


def life(game) -> list[int]:
    return [p.life for p in game.state.players]


class TestTheToken:
    def test_it_is_a_red_aura_token_and_not_a_role(self, registry: CardRegistry):
        token = registry.get(BLESSING)
        assert token.is_token and token.is_aura
        assert token.name == "Smoke Blessing"
        assert set(token.types) == {"Enchantment"}
        assert list(token.subtypes) == ["Aura"]
        assert sorted(token.colors) == ["R"]
        assert [a.kind for a in token.abilities] == ["triggered"]

    def test_it_gives_no_static_bonus(self, builder):
        game, bear, blessing = board(builder)
        assert game.state.objects[blessing].attached_to == bear
        assert game.state.objects[blessing].controller == 0


class TestWhenTheEnchantedCreatureDies:
    def test_its_controller_takes_one_and_the_blessings_controller_gets_a_treasure(
        self, builder
    ):
        game, bear, _ = board(builder)
        destroy(game.state, bear)
        settle(game)
        assert life(game) == [40, 39]
        assert len(oids_of(game, TREASURE, 0)) == 1
        assert not oids_of(game, TREASURE, 1)

    def test_nothing_happens_while_the_creature_lives(self, builder):
        game, _, _ = board(builder)
        settle(game)
        assert life(game) == [40, 40]
        assert not oids_of(game, TREASURE, 0)
