"""A cost-time number taken from the command zone, and taken as a maximum.

    Visions of Glory — "Flashback {8}{W}{W}. This spell costs {X} less to cast
    this way, where X is the greatest mana value of a commander you own on the
    battlefield **or in the command zone**."

Rule 903.6 and 601.2f: a commander sits in the command zone, which is a public
zone the whole game is played around, and a cost reduction is computed while the
game decides what is castable. Both halves of that sentence were out of reach,
and each fails silently rather than loudly.

**It could not see the command zone.** `costs._reduction_matches` walked
`state.battlefield` and nothing else, and read `controller`, `types` and
`subtypes` — `is_commander` was not even one of the keys it honoured. So the
reduction on a card written about a commander read zero for the whole of a
normal game, because the commander is in the command zone for most of it. Not an
error: a nine-mana sorcery that was supposed to cost four, offered at nine, with
nothing on screen to say why.

**It could only sum.** The three shapes `costs.reduction_amount` took were
`{"amount": N}`, `{"count": filter}` and `{"total_power": filter}`, and the two
that read a board add over their matches. "The **greatest** mana value of a
commander you own" written as a `count` or a `total_power` gives a player with
two partner commanders their mana values added together — a different and larger
discount, on a card that reads as though it were right. So
`greatest_mana_value` is a fourth arithmetic key rather than a filter on an
existing one: max and sum are not the same operation and no filter turns one
into the other.

**It is a pricing-time value, so it lives in `costs.py`.** The richer effect
language cannot answer it and is not asked to: `max` takes a fixed list of
expressions written into the card, `mana_value_of` takes a ref rather than a
selector, and `selectors.resolve_pool` draws from exactly one `zone` — and none
of it is reachable before the spell is on the stack, where there is no
`EffectContext` at all.

**"Own", not "control".** The two part company on precisely the boards
commanders are played on. In the command zone they agree; on the battlefield a
commander an opponent has stolen is still one you own and still counts. `owner`
is therefore a reduction-filter key and deliberately not a static-filter one — a
static applies to permanents, where control is the question.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.cost_reduction import cost_reduction, variant_reduction
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object

SPELL = "t_commander_flashback"   # {4}{W}; flashback {8}{W}, less the greatest mv
BIG = "t_commander_five"          # {3}{W}{W} — mana value 5
SMALL = "t_commander_two"         # {1}{W} — mana value 2
PLAINS = "plains"


# --------------------------------------------------------------------------- #
# positions
# --------------------------------------------------------------------------- #


def graveyard_spell(builder, *, commanders=(), opponent_commanders=(), lands: int = 9):
    """``SPELL`` in the graveyard, with ``commanders`` in player 0's command zone.

    Nine lands by default: exactly the printed flashback {8}{W}, so a position
    that is *not* discounted can still cast it and the tests below distinguish
    "the discount is zero" from "the line vanished for some other reason".
    """
    position = (
        builder(players=2)
        .battlefield(0, [PLAINS] * lands)
        .graveyard(0, [SPELL])
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .turn(3)
        .step(Step.PRECOMBAT_MAIN)
    )
    if commanders:
        position = position.commander(0, list(commanders))
    if opponent_commanders:
        position = position.commander(1, list(opponent_commanders))
    game = position.build()
    return game, game.state.players[0].graveyard[0]


def hand_spell(builder, *, commanders=(), lands: int = 5):
    position = (
        builder(players=2)
        .battlefield(0, [PLAINS] * lands)
        .hand(0, [SPELL])
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .turn(3)
        .step(Step.PRECOMBAT_MAIN)
    )
    if commanders:
        position = position.commander(0, list(commanders))
    game = position.build()
    return game, game.state.players[0].hand[0]


def discount(game, oid: int) -> int:
    """The flashback node's rider, priced against the board as it stands."""
    return variant_reduction(game.state, 0, game.state.card(oid).flashback, oid)


def cast_line(game, oid: int):
    return next(
        (a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid),
        None,
    )


def lands_left(game, pid: int = 0) -> int:
    return sum(
        1
        for oid in game.state.battlefield
        if game.state.objects[oid].controller == pid
        and not game.state.objects[oid].tapped
        and game.state.card(oid).is_land
    )


def onto_battlefield(game, oid: int) -> None:
    """Put a command-zone commander into play, keeping its `is_commander` flag."""
    move_object(game.state, oid, Zone.BATTLEFIELD)


# --------------------------------------------------------------------------- #
# the command zone is the point
# --------------------------------------------------------------------------- #


class TestTheCommandZoneIsReachable:
    def test_a_commander_in_the_command_zone_discounts_the_spell(self, builder):
        """The case the printed card is written for, and the one a battlefield
        walk answered zero to."""
        game, oid = graveyard_spell(builder, commanders=[BIG])
        assert game.state.players[0].command, "the commander really is in the zone"
        assert discount(game, oid) == 5

    def test_the_same_commander_on_the_battlefield_discounts_it_too(self, builder):
        """"…on the battlefield **or** in the command zone" is one pool with one
        maximum over it, so moving the general does not change the number."""
        game, oid = graveyard_spell(builder, commanders=[BIG])
        onto_battlefield(game, game.state.players[0].commanders[0])
        assert discount(game, oid) == 5

    def test_no_commander_is_no_discount(self, builder):
        """A real answer rather than a missing one: `max(..., default=0)`. The
        card prints a price for the player who has nothing to reduce it by."""
        game, oid = graveyard_spell(builder)
        assert discount(game, oid) == 0
        assert cast_line(game, oid) is not None, "nine lands still pay the printed {8}{W}"

    def test_an_opponents_commander_is_not_yours(self, builder):
        """The command zone is walked for every seat, so the ownership keys are
        the only thing keeping the pod's other generals out of your discount."""
        game, oid = graveyard_spell(builder, opponent_commanders=[BIG])
        assert discount(game, oid) == 0


class TestItIsAMaximumAndNotASum:
    def test_two_partners_give_the_greater_not_the_total(self, builder):
        """The whole reason this is a fourth arithmetic key. Written as a
        `count` or a `total_power` this board reads seven, and seven is a
        discount the card never offered."""
        game, oid = graveyard_spell(builder, commanders=[SMALL, BIG])
        assert discount(game, oid) == 5

    def test_the_order_they_were_named_in_does_not_matter(self, builder):
        game, oid = graveyard_spell(builder, commanders=[BIG, SMALL])
        assert discount(game, oid) == 5

    def test_one_small_commander_gives_its_own_mana_value(self, builder):
        game, oid = graveyard_spell(builder, commanders=[SMALL])
        assert discount(game, oid) == 2

    def test_the_maximum_spans_the_two_zones(self, builder):
        """The greater is in play and the lesser is in the zone, so a reduction
        that had only learned one zone would answer with the wrong one of them."""
        game, oid = graveyard_spell(builder, commanders=[SMALL, BIG])
        big = game.state.players[0].commanders[1]
        onto_battlefield(game, big)
        assert discount(game, oid) == 5

    def test_it_is_read_off_the_board_every_time(self, builder):
        """Never stored -- the property that makes Ghalta a twelve-drop again."""
        game, oid = graveyard_spell(builder, commanders=[SMALL])
        assert discount(game, oid) == 2
        game.state.players[0].command.remove(game.state.players[0].commanders[0])
        assert discount(game, oid) == 0


class TestOwnershipRatherThanControl:
    def test_a_commander_an_opponent_stole_is_still_one_you_own(self, builder):
        """903.6 / "a commander you own": control changed, ownership did not,
        and the printed line asks the question that did not change."""
        game, oid = graveyard_spell(builder, commanders=[BIG])
        commander = game.state.players[0].commanders[0]
        onto_battlefield(game, commander)
        game.state.objects[commander].controller = 1
        game.state.bump_chars()
        assert discount(game, oid) == 5

    def test_a_permanent_that_is_not_a_commander_does_not_count(self, builder):
        """`is_commander` is honoured, and it is the only thing separating a
        general from the identical legend somebody else cast."""
        game, oid = graveyard_spell(builder, lands=9)
        impostor = _plain_copy(game, BIG)
        game.state.battlefield.append(impostor)
        game.state.bump_chars()
        assert not game.state.objects[impostor].is_commander
        assert discount(game, oid) == 0


def _plain_copy(game, card_id: str) -> int:
    """``card_id`` onto the battlefield as an ordinary permanent, not a general."""
    from commanderblitz.engine.state import new_object

    obj = new_object(game.state, card_id, owner=0, zone=Zone.BATTLEFIELD)
    obj.entered_turn = game.state.turn - 1
    return obj.oid


# --------------------------------------------------------------------------- #
# legality and payment see one number
# --------------------------------------------------------------------------- #


class TestLegalityAndPaymentAgree:
    def test_the_flashback_is_out_of_reach_without_a_general(self, builder):
        game, oid = graveyard_spell(builder, lands=4)
        assert cast_line(game, oid) is None, "four lands cannot pay {8}{W}"

    def test_a_five_drop_general_brings_it_into_reach(self, builder):
        """{8}{W} less five is {3}{W}: four lands, exactly."""
        game, oid = graveyard_spell(builder, commanders=[BIG], lands=4)
        assert discount(game, oid) == 5
        assert cast_line(game, oid) is not None

    def test_a_two_drop_general_does_not(self, builder):
        game, oid = graveyard_spell(builder, commanders=[SMALL], lands=4)
        assert discount(game, oid) == 2
        assert cast_line(game, oid) is None, "{8}{W} less two is still seven mana"

    def test_the_charge_is_the_price_that_was_offered(self, builder):
        """`_cast_variant` offered it and `game._cast` must charge the same
        number -- four lands and not a pip more, so a cast path that ignored the
        rider would strand the payment rather than quietly overcharge."""
        game, oid = graveyard_spell(builder, commanders=[BIG], lands=4)
        before = lands_left(game)

        game.apply(cast_line(game, oid))
        _resolve(game)

        assert before - lands_left(game) == 4, "{8}{W} less five"
        assert len(game.state.players[0].hand) == 1, "and the spell resolved"


class TestTheDiscountBelongsToTheFlashback:
    def test_the_printed_hand_cast_is_not_discounted(self, builder):
        """A card-level `cost_reduction` is variant-blind. This rider is on the
        flashback node, which the hand cast never reads -- so a five-drop
        general does not make a {4}{W} sorcery free."""
        game, oid = hand_spell(builder, commanders=[BIG], lands=4)
        assert cast_line(game, oid) is None, "four lands cannot pay the printed {4}{W}"
        assert cost_reduction(game.state, 0, game.state.card(oid)) == 0

    def test_the_hand_cast_is_charged_the_printed_price(self, builder):
        game, oid = hand_spell(builder, commanders=[BIG], lands=5)
        before = lands_left(game)

        game.apply(cast_line(game, oid))
        _resolve(game)

        assert before - lands_left(game) == 5, "the printed {4}{W}, all of it"


def _resolve(game) -> None:
    from tests.conftest import pass_until

    pass_until(game, lambda g: not g.state.stack)


# --------------------------------------------------------------------------- #
# what the loader refuses, and why each one would otherwise be silent
# --------------------------------------------------------------------------- #


def compile_spec(spec: dict):
    return compile_card(CardModel.model_validate(spec))


def flashback_card(reduction: dict) -> dict:
    return {
        "id": "x_probe",
        "name": "Probe",
        "mana_cost": "{1}{W}",
        "types": ["Sorcery"],
        "flashback": {"mana": "{8}{W}", "mana_reduction": reduction},
        "spell_effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
    }


COMMANDERS = {"is_commander": True, "owner": "you", "zone": ["battlefield", "command"]}


class TestTheLoaderRefusesTheSilentShapes:
    def test_the_card_this_was_built_for_loads(self):
        card = compile_spec(flashback_card({"greatest_mana_value": COMMANDERS}))
        assert card.flashback.mana_reduction["greatest_mana_value"] == COMMANDERS

    def test_it_needs_no_condition_the_way_a_flat_amount_does(self):
        """An ungated `amount` is a cheaper printed cost; an ungated maximum over
        a board is a number that changes, which is the opposite problem."""
        assert compile_spec(flashback_card({"greatest_mana_value": {}})) is not None

    def test_a_zone_nothing_walks_is_refused(self):
        """`costs._reduction_matches` walks the battlefield, the command zone
        and the graveyard. Anything else would load clean and match nothing.

        The graveyard was the example here until Cyan, Vengeful Samurai needed
        it counted; the **hand** replaced it, and is the better example anyway
        -- it is hidden, where all three walked zones are public and readable
        before anything is on the stack.
        """
        with pytest.raises(
            DslError,
            match="counts \\['battlefield', 'command', 'graveyard'\\] only",
        ):
            compile_spec(
                flashback_card({"greatest_mana_value": {"zone": ["command", "hand"]}})
            )

    def test_an_empty_zone_list_is_refused(self):
        with pytest.raises(DslError, match="names no zone at all"):
            compile_spec(flashback_card({"greatest_mana_value": {"zone": []}}))

    def test_total_power_may_not_read_the_command_zone(self):
        """Power is a characteristic of a permanent. A card in the command zone
        has none, and summing its printed face would be answering a question the
        characteristics pipeline was never asked."""
        with pytest.raises(DslError, match="battlefield only"):
            compile_spec(
                flashback_card(
                    {"total_power": {"types": ["Creature"], "zone": ["battlefield", "command"]}}
                )
            )

    def test_a_bad_owner_is_refused(self):
        with pytest.raises(DslError, match=r"owner: must be one of"):
            compile_spec(flashback_card({"greatest_mana_value": {"owner": "anyone"}}))

    def test_two_kinds_of_arithmetic_are_still_refused(self):
        """Max and sum would be paid at whichever the code read first."""
        with pytest.raises(DslError, match="exactly one"):
            compile_spec(
                flashback_card(
                    {"greatest_mana_value": COMMANDERS, "count": {"types": ["Creature"]}}
                )
            )

    def test_a_condition_still_gates_it(self):
        card = compile_spec(
            flashback_card(
                {"greatest_mana_value": COMMANDERS, "condition": {"is_your_turn": True}}
            )
        )
        assert card.flashback.mana_reduction["condition"] == {"is_your_turn": True}


class TestTheGateStillHoldsForEveryoneElse:
    def test_an_existing_filter_still_defaults_to_what_you_control(self, builder):
        """`owner` is new and `controller` defaults only while nothing has been
        said about ownership -- so every reduction written before this change
        means exactly what it always meant."""
        card = compile_spec(flashback_card({"count": {"types": ["Creature"]}}))
        game = (
            builder(players=2)
            .battlefield(0, ["t_bear"])
            .battlefield(1, ["t_bear", "t_bear"])
            .build()
        )
        from commanderblitz.engine.cost_reduction import reduction_amount

        assert reduction_amount(game.state, 0, card.flashback.mana_reduction) == 1
