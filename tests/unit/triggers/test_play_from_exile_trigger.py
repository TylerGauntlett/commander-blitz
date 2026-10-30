"""A cast or land-drop trigger that cares where the card was played from.

    Whenever you play a card from exile, Klaw gains indestructible until end of
    turn.  (Klaw, Master of Sound)

"Play" is cast a spell **or** play a land (rules 601 and 305.1), so the line is two
abilities claiming one printed sentence -- `spell_cast` and `land_played` --
the shape magecraft uses for "cast or copy". A single play is never both, so
the two never fire together.

Each takes `from_zones: ["exile"]`, and each answers it from a different place
because the card has already left by the time its event fires:

* A spell is on the stack when SPELL_CAST fires: 601.2a moves the card there
  first. `stack.push_spell` stamps `cast_from_zone` on the object beside
  `cast_from_hand`, at the one moment the origin is knowable.
* A land is already on the battlefield when LAND_PLAYED fires, so the drop
  carries `from_zone` on its payload, read before the move.

The near misses: a trigger filter's `zone` key reads the subject's *current*
zone (the stack, the battlefield), so `zone: "exile"` never matches; and a
bare `spell_cast` fires on every spell while missing every land.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import action_for_card, only_oid, settle_completely

WATCHER = "t_exile_player"  # "Whenever you play a card from exile, draw a card."
SPELL = "t_plain_instant"  # {W}: gain 1 life
LAND = "mountain"


def position(builder, *, watcher_seat: int = 0, active: int = 0):
    """``active`` holds a Plains-paid instant and a Mountain in hand; the watcher is ``watcher_seat``'s."""
    game = (
        builder(players=2)
        .battlefield(watcher_seat, [WATCHER])
        .battlefield(active, ["plains"])
        .hand(active, [SPELL, LAND])
        .active(active)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def make_playable_from(game, card_id: str, zone: Zone, pid: int) -> int:
    """Move ``pid``'s card to ``zone`` with a standing permission to play it there."""
    state = game.state
    oid = only_oid(game, card_id, pid) if zone is Zone.BATTLEFIELD else next(
        o.oid for o in state.objects.values() if o.def_id == card_id and o.owner == pid
    )
    move_object(state, oid, zone)
    obj = state.objects[oid]
    obj.playable_by = pid
    obj.playable_turn = state.turn
    obj.playable_duration = "while_exiled" if zone is Zone.EXILE else "this_turn"
    return oid


def draws(game, play) -> int:
    """How many cards the watcher's controller drew while ``play`` happened and settled."""
    library = game.state.players[0].library
    before = len(library)
    play()
    settle_completely(game)
    return before - len(library)


def cast(game, card_id: str):
    return lambda: game.apply(action_for_card(game, ActionKind.CAST, card_id))


def play_land(game, card_id: str):
    return lambda: game.apply(action_for_card(game, ActionKind.PLAY_LAND, card_id))


class TestItFires:
    def test_on_a_spell_cast_from_exile(self, builder):
        game = position(builder)
        oid = make_playable_from(game, SPELL, Zone.EXILE, 0)
        assert draws(game, cast(game, SPELL)) == 1
        assert game.state.objects[oid].cast_from_zone == "exile"

    def test_on_a_land_played_from_exile(self, builder):
        game = position(builder)
        oid = make_playable_from(game, LAND, Zone.EXILE, 0)
        assert draws(game, play_land(game, LAND)) == 1
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD


class TestItDoesNotFire:
    def test_on_a_spell_cast_from_hand(self, builder):
        game = position(builder)
        assert draws(game, cast(game, SPELL)) == 0

    def test_on_a_land_played_from_hand(self, builder):
        game = position(builder)
        assert draws(game, play_land(game, LAND)) == 0

    def test_on_a_spell_cast_from_a_graveyard(self, builder):
        game = position(builder)
        make_playable_from(game, SPELL, Zone.GRAVEYARD, 0)
        assert draws(game, cast(game, SPELL)) == 0

    def test_on_an_opponents_spell_cast_from_exile(self, builder):
        game = position(builder, watcher_seat=0, active=1)
        make_playable_from(game, SPELL, Zone.EXILE, 1)
        assert draws(game, cast(game, SPELL)) == 0

    def test_on_an_opponents_land_played_from_exile(self, builder):
        game = position(builder, watcher_seat=0, active=1)
        make_playable_from(game, LAND, Zone.EXILE, 1)
        assert draws(game, play_land(game, LAND)) == 0


class TestTheLoaderGuards:
    def _card(self, trigger: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_from_where",
                "name": "Test From Where",
                "mana_cost": "{1}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "oracle_text": "Whenever you play a card from exile, draw a card.",
                "abilities": [
                    {
                        "kind": "triggered",
                        "text": "Whenever you play a card from exile, draw a card.",
                        "trigger": trigger,
                        "effects": [{"op": "draw", "amount": {"const": 1}}],
                    }
                ],
            }
        )

    @pytest.mark.parametrize("event", ["spell_cast", "land_played"])
    def test_it_loads_on_a_cast_or_a_land_drop(self, event):
        card = compile_card(self._card({"event": event, "from_zones": ["exile"]}))
        assert card.abilities[0].trigger.from_zones == ("exile",)

    def test_it_is_refused_on_another_event(self):
        with pytest.raises(DslError, match="from_zones"):
            compile_card(self._card({"event": "permanent_enters", "from_zones": ["exile"]}))

    @pytest.mark.parametrize("zones", [[], ["battlefield"], ["stack"]])
    def test_a_zone_nothing_is_played_from_is_refused(self, zones):
        with pytest.raises(DslError, match="from_zones"):
            compile_card(self._card({"event": "spell_cast", "from_zones": zones}))
