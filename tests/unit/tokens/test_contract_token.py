"""The Contract token: an Aura one player puts on another player's creature.

    Scriv, the Obligator -- "Whenever Scriv enters or attacks, create a white
    Aura enchantment token named Contract attached to target creature an
    opponent controls. The token has enchant creature and 'Whenever enchanted
    creature attacks, it gets +2/+0 until end of turn if it's attacking one of
    your opponents. Otherwise, its controller loses 2 life.'"

Two different players are named inside the token's one trigger, and the card is
only right when each is read from the right object:

- **"your opponents"** is the opponents of the *Contract's* controller (109.5:
  "you" in an ability is the controller of its source), who is Scriv's
  controller -- not the enchanted creature's controller, whose opponents
  include Scriv's controller. Read the other way, the creature would be pumped
  for attacking the very player the Contract exists to protect.
- **"its controller"** is the enchanted creature's controller, the player the
  trigger punishes, never the Contract's.

And "attacking one of your opponents" is attacking a *player* (506.2): a
creature sent at a planeswalker or a battle attacks that permanent, not its
controller, so it falls into "otherwise".

`create_token` with `attached_to` already makes an Aura token on somebody
else's creature (`test_wicked_role.py`); this is the token itself, an
`attacks` trigger filtered `attached`, an `if` on the bound attacker's
`attacking_player: "opponent"`, and `controller_of: "subject"` for the loss.
"""

from __future__ import annotations

from commanderblitz.cards.registry import CardRegistry
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.primitives import attach, create_token
from commanderblitz.engine.structs import TargetRef
from tests.conftest import find_action, only_oid, pass_until, pt, settle

CONTRACT = "contract"
BEAR = "t_bear"  # vanilla 2/2
WALKER = "t_walker"


def board(builder, *, walker: bool = False):
    """Player 1's turn in a three-seat pod, its bear wearing player 0's Contract.

    Player 0 is the Contract's controller; player 2 is an opponent of both.
    """
    game = (
        builder(players=3)
        .battlefield(1, ["forest"] * 2 + [BEAR])
        .battlefield(2, [WALKER] if walker else [])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .library(2, ["forest"] * 10)
        .active(1)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    bear = only_oid(game, BEAR, 1)
    (contract,) = create_token(game.state, CONTRACT, 0)
    attach(game.state, contract, bear)
    return game, bear, contract


def swing(game, bear: int, at: TargetRef) -> None:
    """Declare the bear at ``at`` and let the Contract's trigger resolve."""
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=bear, targets=(at,)))
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    settle(game)


def life(game) -> list[int]:
    return [p.life for p in game.state.players]


class TestTheToken:
    def test_it_is_a_white_aura_token_and_not_a_role(self, registry: CardRegistry):
        token = registry.get(CONTRACT)
        assert token.is_token and token.is_aura
        assert set(token.types) == {"Enchantment"}
        assert set(token.subtypes) == {"Aura"}
        assert sorted(token.colors) == ["W"]

    def test_it_gives_no_static_bonus(self, builder):
        game, bear, contract = board(builder)
        assert game.state.objects[contract].attached_to == bear
        assert game.state.objects[contract].controller == 0
        assert pt(game, bear) == (2, 2)


class TestYourOpponentsAreTheContractControllers:
    def test_attacking_a_third_player_pumps_and_costs_nothing(self, builder):
        game, bear, _ = board(builder)
        swing(game, bear, TargetRef.player(2))
        assert pt(game, bear) == (4, 2)
        assert life(game) == [40, 40, 40]

    def test_attacking_the_contracts_controller_costs_its_controller_two(self, builder):
        """Player 0 is an opponent of the bear's controller, but not of the
        Contract's controller -- so this is the "otherwise"."""
        game, bear, _ = board(builder)
        swing(game, bear, TargetRef.player(0))
        assert pt(game, bear) == (2, 2)
        assert life(game) == [40, 38, 40]


class TestAPlaneswalkerIsNotAnOpponent:
    def test_attacking_an_opponents_planeswalker_is_the_otherwise(self, builder):
        game, bear, _ = board(builder, walker=True)
        swing(game, bear, TargetRef.obj(only_oid(game, WALKER, 2)))
        assert pt(game, bear) == (2, 2)
        assert life(game) == [40, 38, 40]


class TestItWearsOff:
    def test_the_pump_ends_with_the_turn(self, builder):
        game, bear, _ = board(builder)
        swing(game, bear, TargetRef.player(2))
        pass_until(game, lambda g: g.state.active_player != 1)
        assert pt(game, bear) == (2, 2)
