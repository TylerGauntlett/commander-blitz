"""Replacing the graveyard itself — "exile it instead", from anywhere.

    Rest in Peace — "When this enchantment enters, exile all graveyards. If a card
    or token would be put into a graveyard from anywhere, exile it instead."

`docs/rules-coverage.md` recorded this as unbuilt in the strongest terms it uses:
"There is still no rule-616 machinery: no event object, no 'replaced by' chain,
and no asking the affected player which of two applicable replacements to apply
first", and "a replacement of anything other than those four is engine work
rather than a new key in a card file."

So this is the **fifth named hook**, not the start of a system, and that is a
deliberate scope choice rather than a shortcut — recorded in the commit under the
import-moxfield skill's rule 2, which permits a subsystem when the deck is the
deliverable provided it is said out loud first.

### "From anywhere" is the whole clause, and it is what `dies_to` cannot say

The engine already had `obj.dies_to` — "if it would die this turn, exile it
instead" — and it is gated on `from_zone is Zone.BATTLEFIELD`. Rest in Peace says
**from anywhere**, so it has to catch a milled card, a discard, a spell leaving
the stack, a token dying, a card put there from exile or the command zone, and a
permanent dying, for every player at once. `TestFromAnywhere` walks those routes,
because a version gated on the battlefield would pass a death test and let every
mill through.

It is also a one-shot's opposite: `replace_deaths` the op snapshots object ids and
sets `dies_to` on each, so it reaches nothing that arrives later and cannot be a
permanent's ongoing static.

### Ordering against the commander replacement

616.1 gives the choice between two applicable replacements to the affected
player, and this engine does not ask — it already does not ask for the commander
case, which `rules-coverage.md` records as "the owner always chooses the command
zone". So this hook runs **after** it, and a commander dying under Rest in Peace
reaches its command zone: by the time this runs `to_zone` is no longer a
graveyard. Ordered the other way round it would exile people's commanders, which
is why `TestTheCommanderStillGoesHome` exists.

### Owner, not controller

`affects_player` is read against the object's **owner**. That is the printed
relation — Leyline of the Void says "an opponent's graveyard" — and 404.1 puts a
card in its owner's graveyard however control changed. Reading the controller
would exile a stolen card that should go to its owner's pile untouched.

Witness: Rest in Peace (`data/authoring/answers/rest_in_peace.json`).
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import Zone
from automtg.engine.state import new_object
from automtg.engine.zones import move_object
from tests.conftest import only_oid

RIP = "t_rip"  # every card and token, every graveyard, from anywhere
LEYLINE = "t_leyline_like"  # an opponent's cards only
PLANAR = "t_planar_void_like"  # creature cards only
LIBRARY_VOID = "t_library_void"  # redirects to a library instead of exile
BEAR = "t_bear"
BOLT = "t_bolt"  # an instant, for the type filter
PLAINS = "plains"


def board(builder, mine=(RIP,), lands=2):
    return (
        builder(players=2)
        .battlefield(0, [PLAINS] * lands + list(mine))
        .battlefield(1, [PLAINS])
        .hand(0, [PLAINS])
        .hand(1, [PLAINS])
        .library(0, [PLAINS] * 10)
        .library(1, [PLAINS] * 10)
        .build(advance=False)
    )


def put_in(game, card_id: str, zone: Zone, pid: int = 0) -> int:
    """Create a card in ``zone`` and return its oid.

    The stack is not a player-owned zone -- it is shared and ordered -- so an
    object there is placed by setting its zone alone, which is what
    `push_spell` leaves behind once it has removed the card from a hand.
    """
    obj = new_object(game.state, card_id, owner=pid, zone=zone)
    if zone is Zone.BATTLEFIELD:
        game.state.battlefield.append(obj.oid)
    elif zone is not Zone.STACK:
        game.state.players[pid].zone_list(zone).append(obj.oid)
    return obj.oid


def send_to_graveyard(game, oid: int) -> Zone:
    move_object(game.state, oid, Zone.GRAVEYARD)
    return game.state.objects[oid].zone


class TestFromAnywhere:
    """The clause `dies_to` cannot express, route by route.

    A version gated on the battlefield passes the first of these and lets every
    other one through.
    """

    def test_a_permanent_dying(self, builder):
        game = board(builder)
        assert send_to_graveyard(game, put_in(game, BEAR, Zone.BATTLEFIELD)) is Zone.EXILE

    def test_a_card_milled_from_a_library(self, builder):
        game = board(builder)
        assert send_to_graveyard(game, put_in(game, BEAR, Zone.LIBRARY)) is Zone.EXILE

    def test_a_card_discarded_from_hand(self, builder):
        game = board(builder)
        assert send_to_graveyard(game, put_in(game, BEAR, Zone.HAND)) is Zone.EXILE

    def test_a_spell_leaving_the_stack(self, builder):
        game = board(builder)
        assert send_to_graveyard(game, put_in(game, BOLT, Zone.STACK)) is Zone.EXILE

    def test_a_card_put_there_from_exile(self, builder):
        game = board(builder)
        assert send_to_graveyard(game, put_in(game, BEAR, Zone.EXILE)) is Zone.EXILE

    def test_the_graveyard_stays_empty(self, builder):
        """The observable consequence, which is the whole of the card: nothing
        accumulates for anybody to reanimate or delve."""
        game = board(builder)
        for zone in (Zone.BATTLEFIELD, Zone.LIBRARY, Zone.HAND):
            send_to_graveyard(game, put_in(game, BEAR, zone))
        assert game.state.players[0].graveyard == []

    def test_without_the_static_everything_lands_normally(self, builder):
        """Pins that the redirection is the static's and not the harness's."""
        game = board(builder, mine=())
        assert send_to_graveyard(game, put_in(game, BEAR, Zone.LIBRARY)) is Zone.GRAVEYARD


class TestItCatchesBothSides:
    def test_an_opponents_card_too(self, builder):
        """"a graveyard", unqualified -- Rest in Peace is symmetric, which is the
        drawback the card is built around."""
        game = board(builder)
        oid = put_in(game, BEAR, Zone.LIBRARY, pid=1)
        assert send_to_graveyard(game, oid) is Zone.EXILE

    def test_a_token_is_caught(self, builder):
        """"a card **or token**" -- the default, because every printed card in
        this family says it."""
        game = board(builder)
        oid = put_in(game, BEAR, Zone.BATTLEFIELD)
        game.state.objects[oid].is_token = True
        assert send_to_graveyard(game, oid) is Zone.EXILE


class TestTheFiltersNarrowIt:
    def test_leyline_spares_its_controllers_own_cards(self, builder):
        """"an **opponent's** graveyard" -- read against the owner, and the half
        that makes Leyline of the Void a different card from Rest in Peace."""
        game = board(builder, mine=(LEYLINE,))
        mine = put_in(game, BEAR, Zone.LIBRARY, pid=0)
        theirs = put_in(game, BEAR, Zone.LIBRARY, pid=1)

        assert send_to_graveyard(game, mine) is Zone.GRAVEYARD
        assert send_to_graveyard(game, theirs) is Zone.EXILE

    def test_planar_void_narrows_by_card_type(self, builder):
        game = board(builder, mine=(PLANAR,))
        creature = put_in(game, BEAR, Zone.LIBRARY)
        instant = put_in(game, BOLT, Zone.LIBRARY)

        assert send_to_graveyard(game, creature) is Zone.EXILE
        assert send_to_graveyard(game, instant) is Zone.GRAVEYARD

    def test_the_destination_is_a_field(self, builder):
        """The Kozilek/Ulamog shape -- "put it into its owner's library instead"
        -- and the reason `destination` is not a hard-coded exile."""
        game = board(builder, mine=(LIBRARY_VOID,))
        assert send_to_graveyard(game, put_in(game, BEAR, Zone.HAND)) is Zone.LIBRARY


class TestTheCommanderStillGoesHome:
    """616.1's choice, which this engine settles the same way it already settles
    the commander case: the owner takes the command zone.

    Ordered the other way round, Rest in Peace would exile people's commanders --
    which is why the hook runs after that replacement rather than before it.
    """

    def test_a_dying_commander_reaches_the_command_zone(self, builder):
        game = board(builder)
        oid = put_in(game, BEAR, Zone.BATTLEFIELD)
        game.state.objects[oid].is_commander = True

        assert send_to_graveyard(game, oid) is Zone.COMMAND

    def test_an_ordinary_creature_on_the_same_board_is_exiled(self, builder):
        """The contrast: the hook is live, it simply does not reach a card whose
        destination is no longer a graveyard."""
        game = board(builder)
        assert send_to_graveyard(game, put_in(game, BEAR, Zone.BATTLEFIELD)) is Zone.EXILE


class TestTheLoaderRefusals:
    def _card(self, **static) -> CardModel:
        base = {
            "kind": "static",
            "text": "If a card or token would be put into a graveyard from anywhere, "
            "exile it instead.",
            "effect": "replace_graveyard",
            "affects_player": "any",
            "destination": "exile",
        }
        base.update(static)
        return CardModel.model_validate(
            {
                "id": "t_rip_probe",
                "name": "RIP Probe",
                "mana_cost": "{2}{W}",
                "oracle_text": "If a card or token would be put into a graveyard from "
                "anywhere, exile it instead.",
                "types": ["Enchantment"],
                "abilities": [base],
            }
        )

    def test_the_printed_shape_loads(self):
        assert compile_card(self._card()) is not None

    def test_no_filter_is_allowed(self):
        """Rest in Peace names nothing, so `affects` really is optional here --
        the exception in a family where Leyline and Planar Void both narrow."""
        assert compile_card(self._card(affects=None)) is not None

    def test_a_missing_affects_player_is_refused(self):
        """There is no honest default: a silent "any" would turn Leyline of the
        Void into Rest in Peace."""
        with pytest.raises(DslError, match="needs 'affects_player'"):
            compile_card(self._card(affects_player=None))

    def test_an_unreachable_destination_is_refused(self):
        with pytest.raises(DslError, match="is not a zone a printed card"):
            compile_card(self._card(destination="command"))


class TestTheReaderHasNoDefaultEither:
    """`affects_player` is refused by the loader *and* has no default in the
    reader, which are two separate guarantees.

    `TestTheLoaderRefusals.test_a_missing_affects_player_is_refused` covers the
    only path a printed card can take today, so this class is defence in depth
    rather than a live bug -- but it is worth holding, because the default that
    suggests itself in `_graveyard_replacement` is `"any"`, and `"any"` is
    exactly what turns Leyline of the Void into Rest in Peace. A malformed
    static arriving by some future route -- a granted one, say, which the
    loader's own comment says works -- should do nothing anybody can mistake for
    the card working.

    Both tests go through the same seam, so the second is the control that shows
    the seam is real and the first is not passing for want of being reached.
    """

    def _static_from(self, game, static):
        """Yield one hand-made static off the Rest in Peace already in play."""
        source = game.state.objects[only_oid(game, RIP)]

        def fake(state):
            yield source, static

        return fake

    def test_a_static_without_affects_player_does_nothing(self, builder, monkeypatch):
        from automtg.engine import characteristics

        game = board(builder)
        monkeypatch.setattr(
            characteristics,
            "_battlefield_statics",
            self._static_from(game, {"effect": "replace_graveyard", "destination": "exile"}),
        )

        assert send_to_graveyard(game, put_in(game, BEAR, Zone.LIBRARY)) is Zone.GRAVEYARD

    def test_and_the_same_static_with_it_exiles(self, builder, monkeypatch):
        from automtg.engine import characteristics

        game = board(builder)
        monkeypatch.setattr(
            characteristics,
            "_battlefield_statics",
            self._static_from(
                game,
                {
                    "effect": "replace_graveyard",
                    "affects_player": "any",
                    "destination": "exile",
                },
            ),
        )

        assert send_to_graveyard(game, put_in(game, BEAR, Zone.LIBRARY)) is Zone.EXILE
