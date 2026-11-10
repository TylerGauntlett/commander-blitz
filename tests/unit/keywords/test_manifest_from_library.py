"""`manifest` with ``controller: "you"`` -- "you manifest the top card of that
player's library".

Rule 701.34a: to manifest a card, *you* put it onto the battlefield face down
as a 2/2 creature -- under your control, whichever library it came from. The
library's player stays its owner (108.3), so the card goes to their graveyard,
hand or library when it leaves. Orochi Soul-Reaver (the damaged player's
library) and Thieving Amalgam (the upkeeping opponent's) are the witnesses.

Without the key `manifest` uses its one ``player`` both as the library and as
the manifesting player, so binding it to the opponent hands *them* the 2/2:
the printed card's whole payoff given to the wrong seat, and a card that loads,
resolves and looks right.

The rules arguments the tests below make:

* **Whose library, whose creature.** The card leaves the named player's
  library and enters under the effect's controller; the owner is unchanged,
  and the manifester -- not the owner -- may look at it (708.5).
* **Turning it face up** is the controller's, for the hidden card's own mana
  cost, paid from the controller's pool (701.34c); the turned-up creature stays
  theirs and is still owned by the library's player.
* **When it leaves** it goes to its owner's graveyard, and Thieving Amalgam's
  "a creature you control but don't own dies" (``controller: "you"`` beside
  ``owner: "opponent"``) hears it -- while a creature you both control and own
  does not.
* **The near miss**, the same trigger without the key, manifests the upkeeping
  player's card under that player; and the loader refuses any other value.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.legality import _priority_actions
from tests.conftest import activations, pass_until, pt, settle_completely

THIEF = "t_mfl_thief"  # "...each opponent's upkeep, you manifest the top card of that player's library."
GIFT = "t_mfl_gift"  # the same trigger without `controller`: that player manifests their own
TOLL = "t_mfl_toll"  # "Whenever a creature you control but don't own dies, its owner loses 2..."
BEAR = "grizzly_bears"
FOREST = "forest"


def board(builder, card=THIEF, *, top=BEAR, players=2, mine=()):
    """Player 0 with ``card``, Forests and ``mine``; every opponent's library
    is ``top`` over Forests. Player 0's turn, so the next upkeep is player 1's.
    Frozen before the auto-pass, so ``top`` is still player 1's top card."""
    b = (
        builder(players=players)
        .battlefield(0, [card] + [FOREST] * 4 + list(mine))
        .library(0, [FOREST] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
    )
    for pid in range(1, players):
        b = b.library(pid, [top] + [FOREST] * 20).battlefield(pid, [FOREST] * 4)
    game = b.build(advance=False)
    return game, game.state.players[1].library[0]


def to_upkeep_of(game) -> None:
    """Run the frozen position on through the next upkeep -- player 1's -- and
    let its triggers resolve."""
    game._advance()
    settle_completely(game)


def to_my_main(game) -> None:
    pass_until(
        game, lambda g: g.state.active_player == 0 and g.state.step is Step.PRECOMBAT_MAIN
    )


def manifested(game) -> list:
    return [o for o in game.state.objects.values() if o.zone is Zone.BATTLEFIELD and o.face_down]


class TestWhoseLibraryWhoseCreature:
    def test_the_card_leaves_the_named_players_library(self, builder):
        game, top = board(builder)

        to_upkeep_of(game)

        assert top not in game.state.players[1].library
        assert game.state.objects[top].zone is Zone.BATTLEFIELD

    def test_it_enters_under_the_effects_controller(self, builder):
        game, top = board(builder)

        to_upkeep_of(game)

        obj = game.state.objects[top]
        assert obj.face_down
        assert obj.controller == 0
        assert top in [o.oid for o in game.state.battlefield_objects(0)]
        c = chars(game.state, top)
        assert (c.power, c.toughness) == (2, 2)

    def test_its_owner_is_unchanged(self, builder):
        game, top = board(builder)

        to_upkeep_of(game)

        assert game.state.objects[top].owner == 1

    def test_the_manifester_may_look_at_it_and_the_owner_may_not(self, builder):
        """708.5: the controller of a face-down permanent may look at it."""
        game, top = board(builder)

        to_upkeep_of(game)

        assert 0 in game.state.objects[top].revealed_to
        assert 1 not in game.state.objects[top].revealed_to

    def test_only_the_upkeeping_players_library(self, builder):
        """"That player" is the one whose upkeep it is, not each opponent."""
        game, _ = board(builder, players=3)
        tops = {pid: game.state.players[pid].library[0] for pid in (1, 2)}

        to_upkeep_of(game)

        assert game.state.objects[tops[1]].zone is Zone.BATTLEFIELD
        assert game.state.objects[tops[2]].zone is Zone.LIBRARY

    def test_an_empty_library_manifests_nothing(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [THIEF])
            .library(0, [FOREST] * 20)
            .library(1, [])
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build(advance=False)
        )

        to_upkeep_of(game)

        assert manifested(game) == []


class TestTurningItFaceUp:
    def test_the_controller_may_turn_a_creature_card_up_for_its_cost(self, builder):
        game, top = board(builder)
        to_upkeep_of(game)
        to_my_main(game)

        offers = activations(game, top, 0)
        assert offers, "player 0 controls it, so player 0 may turn it up"
        game.apply(offers[0])
        settle_completely(game)

        obj = game.state.objects[top]
        assert not obj.face_down
        assert obj.controller == 0 and obj.owner == 1
        assert game.state.card_of(obj).name == "Grizzly Bears"
        assert pt(game, top) == (2, 2)
        assert "Bear" in chars(game.state, top).subtypes

    def test_the_owner_may_not(self, builder):
        """Player 1 owns it and has the mana, but does not control it."""
        game, top = board(builder)
        to_upkeep_of(game)

        offers = _priority_actions(game.state, 1)
        assert not [a for a in offers if a.source == top]
        assert [a for a in _priority_actions(game.state, 0) if a.source == top]

    def test_a_non_creature_card_stays_down(self, builder):
        game, top = board(builder, top=FOREST)
        to_upkeep_of(game)
        to_my_main(game)

        assert game.state.objects[top].face_down
        assert activations(game, top, 0) == []


class TestWhenItLeaves:
    def kill(self, game, oid: int) -> None:
        from commanderblitz.engine.zones import move_object

        move_object(game.state, oid, Zone.GRAVEYARD, cause="destroyed")
        settle_completely(game)

    def test_it_goes_to_its_owners_graveyard(self, builder):
        game, top = board(builder)
        to_upkeep_of(game)

        self.kill(game, top)

        assert top in game.state.players[1].graveyard
        assert top not in game.state.players[0].graveyard

    def test_a_creature_you_control_but_dont_own_dying_is_heard(self, builder):
        game, top = board(builder, mine=[TOLL])
        to_upkeep_of(game)
        lives = (game.state.players[0].life, game.state.players[1].life)

        self.kill(game, top)

        assert game.state.players[0].life == lives[0] + 2
        assert game.state.players[1].life == lives[1] - 2

    def test_a_creature_you_own_dying_is_not(self, builder):
        game, _ = board(builder, mine=[TOLL, BEAR])
        game._advance()
        bear = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEAR)
        lives = (game.state.players[0].life, game.state.players[1].life)

        self.kill(game, bear)

        assert (game.state.players[0].life, game.state.players[1].life) == lives


class TestTheNearMiss:
    def test_without_the_key_the_library_player_manifests_it(self, builder):
        game, top = board(builder, card=GIFT)

        to_upkeep_of(game)

        obj = game.state.objects[top]
        assert obj.face_down
        assert obj.controller == 1


def _card(effect: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_mfl_probe",
            "name": "Probe",
            "mana_cost": "{U}",
            "types": ["Sorcery"],
            "spell_effects": [effect],
        }
    )


class TestTheLoader:
    def test_controller_you_loads(self):
        compile_card(_card({"op": "manifest", "player": "each_opponent", "controller": "you"}))

    @pytest.mark.parametrize("value", ["opponent", "each_opponent", {"binding": "event_player"}])
    def test_any_other_controller_is_refused(self, value):
        with pytest.raises(DslError, match="manifest 'controller'"):
            compile_card(_card({"op": "manifest", "player": "each_opponent", "controller": value}))

    def test_manifest_dread_refuses_it(self):
        """701.62a: manifest dread is always your own top two."""
        with pytest.raises(DslError, match="manifest_dread"):
            compile_card(_card({"op": "manifest_dread", "controller": "you"}))
