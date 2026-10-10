"""Gift (702.164a): a promise made to one chosen opponent, costing nothing.

"**Gift a tapped Fish** (You may promise an opponent a gift as you cast this
spell. If you do, they create a tapped 1/1 blue Fish creature token before its
other effects.) Exile target nontoken creature. If the gift wasn't promised,
return that card to the battlefield ... at the beginning of the next end step."
Parting Gust is the witness, and every clause of it is a separate claim:

**It is a choice, not a cost** (702.164a, made under 601.2b with the modes and
X). The caster pays nothing for it, which is exactly why it could not be spelled
as a `kicker`: the loader refuses a kicker whose mana value is 0, correctly,
because a kicker that costs nothing is one cast offered twice. Both gift lines
are priced at the printed cost, and the test that says so is the one that would
catch a gift smuggled in as a cost.

**It names a seat.** "*An* opponent", not each of them, so legality offers one
promised line **per opponent** and the chosen one rides on the action. A gift
implemented as a bool plus `each_opponent` is a three-times-worse card at a pod
and looks identical in a two-player game -- which is why the pod is tested.

**The card branches on it, and both branches must be reachable.** The measured
near-miss for this mechanic (`additional_cost: {}` with `additional_optional`)
loaded and passed all six authoring gates *with the gift branch never running
once*: `_additional_ceiling` offered times 0 and 1 at the same price, and
`verify.find_play` picks its line by `kicked`, which such a card does not set.
So the harness half is tested here too -- a flag legality can offer needs a flag
`find_play` can ask for, or gate 5 measures the half of the card that was
already going to work.

**And the promise outlives the spell.** The exiled creature's return is a
delayed trigger, and Parting Gust is in a graveyard by the time it fires; a
creature's gift clause is read by an enters trigger, later still. Both read the
object, which is why the flag is written there *before* `spell_effects` run.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer

GIFT = "t_gift"  # {1}{W} instant, gift a tapped Fish -- Parting Gust
GIFT_CREATURE = "t_gift_creature"  # {1}{U} 2/2, gift a card
FISH = "fish_1_1_u"
VICTIM = "grizzly_bears"


def a_gift_spell(builder, *, players: int = 2, lands: int = 4):
    """The gift card in hand, one nontoken creature per opponent, and a stop.

    Cast on the **opponent's** turn, and it has to be: the caster's own turn
    rolls through an untap step before the game hands priority back, so a token
    created tapped is untapped again before anything can look at it. This is an
    instant, so casting it in their main phase is a line the printed card has.

    The Bolt in hand is a permanent priority stop rather than a spell anybody
    casts: `full_control` only holds a window open when something other than
    Pass is legal, and "any target" is always legal. Without it the engine
    auto-passes the whole turn inside one `apply`, and the end step -- which is
    the thing under test -- has already happened by the time it returns.
    """
    position = (
        builder(players=players)
        .hand(0, [GIFT, "lightning_bolt"])
        .battlefield(0, ["plains"] * lands + ["mountain"])
        .active(1)
        .turn(2)
        .step(Step.PRECOMBAT_MAIN)
    )
    for pid in range(1, players):
        position = position.battlefield(pid, [VICTIM])
    game = position.build(advance=False)
    game.state.players[0].full_control = True
    game._advance()
    return game


def a_gift_creature(builder):
    """The gift *creature* in hand, on the caster's own turn.

    A creature spell is sorcery-speed, so it cannot borrow the opponent's turn
    the instant above does. Nothing here is tapped, so it does not need to.
    """
    game = (
        builder(players=2)
        .hand(0, [GIFT_CREATURE, "lightning_bolt"])
        .battlefield(0, ["island"] * 4 + ["mountain"])
        .turn(1)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game.state.players[0].full_control = True
    game._advance()
    return game


def gift_lines(game, card_id: str = GIFT):
    """Every way of casting the gift card right now, split by the promise."""
    casts = [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and (obj := game.state.objects.get(a.source)) is not None
        and obj.def_id == card_id
    ]
    return (
        [a for a in casts if a.gift_to is None],
        [a for a in casts if a.gift_to is not None],
    )


def cast(game, action):
    """Take ``action`` and pass priority until the spell has resolved."""
    game.apply(action)
    for _ in range(20):
        if not game.state.stack:
            break
        game.apply(_default_answer(game, game.pending()))
    return game


def next_turn(game):
    """Roll forward past the end step the delayed return is scheduled for."""
    for _ in range(300):
        if game.state.turn > 2 and game.state.step >= Step.PRECOMBAT_MAIN:
            return game
        decision = game.pending()
        if decision is None:
            return game
        game.apply(_default_answer(game, decision))
    raise AssertionError("the turn never ended")


def oid_of(game, def_id: str) -> int:
    return next(
        oid for oid, obj in game.state.objects.items() if obj.def_id == def_id
    )


def fish_count(game, pid: int) -> int:
    return sum(
        1
        for oid in game.state.battlefield
        if (obj := game.state.objects.get(oid)) is not None
        and obj.def_id == FISH
        and obj.controller == pid
    )


class TestBothLinesAreOffered:
    def test_the_unpromised_line_comes_first(self, builder):
        """The line that hands an opponent a creature is never the default."""
        game = a_gift_spell(builder)
        plain, promised = gift_lines(game)
        assert plain and promised
        casts = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == GIFT
        ]
        assert casts[0].gift_to is None

    def test_the_promise_is_free(self, builder):
        """601.2b, not 601.2g: both lines are castable on exactly {1}{W}.

        The whole reason gift could not be a `kicker` -- a cast-time flag in
        this engine came bundled with a price, and this one has none.
        """
        game = a_gift_spell(builder, lands=2)
        plain, promised = gift_lines(game)
        assert plain, "{1}{W} is affordable on two Plains"
        assert promised, "and so is the promised line, because it costs the same"

    def test_one_line_per_opponent(self, builder):
        """"*An* opponent" -- the caster picks which, and the seats differ."""
        game = a_gift_spell(builder, players=3)
        _plain, promised = gift_lines(game)
        assert {a.gift_to for a in promised} == {1, 2}

    def test_a_card_with_no_gift_is_offered_once(self, builder):
        """Nothing shipped moved: no `gift`, no extra line."""
        game = a_gift_spell(builder)
        bolts = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "lightning_bolt"
        ]
        assert bolts and all(a.gift_to is None for a in bolts)

    def test_the_label_says_what_and_to_whom(self, builder):
        """Neither half is guessable from the card name."""
        game = a_gift_spell(builder)
        _plain, promised = gift_lines(game)
        assert promised
        assert all("gift a tapped Fish to" in a.label for a in promised)


class TestThePromisedLine:
    def test_the_promised_opponent_gets_the_token(self, builder):
        game = a_gift_spell(builder)
        _plain, promised = gift_lines(game)
        cast(game, promised[0])
        assert fish_count(game, 1) == 1
        assert fish_count(game, 0) == 0, "the gift is theirs, not yours"

    def test_the_token_arrives_tapped(self, builder):
        """"They create a **tapped** 1/1 blue Fish" -- the whole downside."""
        game = a_gift_spell(builder)
        _plain, promised = gift_lines(game)
        cast(game, promised[0])
        assert game.state.objects[oid_of(game, FISH)].tapped

    def test_only_the_promised_seat_gets_one(self, builder):
        """At a pod, `each_opponent` would be twice the printed card."""
        game = a_gift_spell(builder, players=3)
        _plain, promised = gift_lines(game)
        cast(game, next(a for a in promised if a.gift_to == 2))
        assert fish_count(game, 2) == 1
        assert fish_count(game, 1) == 0

    def test_the_exiled_creature_never_comes_back(self, builder):
        """"If the gift **wasn't** promised" -- so the promise buys the exile."""
        game = a_gift_spell(builder)
        _plain, promised = gift_lines(game)
        victim = oid_of(game, VICTIM)
        cast(game, promised[0])

        assert game.state.objects[victim].zone is Zone.EXILE
        assert game.state.delayed_triggers == [], "nothing was scheduled at all"
        next_turn(game)
        assert game.state.objects[victim].zone is Zone.EXILE


class TestTheUnpromisedLine:
    def test_nobody_gets_a_token(self, builder):
        """`"gift_recipient"` resolves to nobody, so `create_token` makes none.

        The conditional half of the reward with no `if` around it, which is what
        lets "they create a token" mean exactly what it says.
        """
        game = a_gift_spell(builder)
        plain, _promised = gift_lines(game)
        cast(game, plain[0])
        assert fish_count(game, 0) == fish_count(game, 1) == 0

    def test_the_return_is_scheduled_rather_than_immediate(self, builder):
        """"At the beginning of the next end step" -- a delayed return that
        returns straight away is not a delayed return."""
        game = a_gift_spell(builder)
        plain, _promised = gift_lines(game)
        victim = oid_of(game, VICTIM)
        cast(game, plain[0])

        assert game.state.objects[victim].zone is Zone.EXILE
        assert [d.step for d in game.state.delayed_triggers] == ["end_step"]

    def test_it_comes_back_at_the_end_step_with_a_counter(self, builder):
        game = a_gift_spell(builder)
        plain, _promised = gift_lines(game)
        victim = oid_of(game, VICTIM)
        cast(game, plain[0])
        next_turn(game)

        obj = game.state.objects[victim]
        assert obj.zone is Zone.BATTLEFIELD
        assert obj.controller == 1, "under its owner's control"
        assert obj.counters.get("+1/+1") == 1


class TestThePromiseOutlivesTheSpell:
    """The StackItem is gone by the time an enters trigger asks."""

    def test_a_permanent_remembers_who_was_promised(self, builder):
        game = a_gift_creature(builder)
        _plain, promised = gift_lines(game, GIFT_CREATURE)
        cast(game, promised[0])
        assert game.state.objects[oid_of(game, GIFT_CREATURE)].cast_gift_to == 1

    def test_an_unpromised_permanent_remembers_that_too(self, builder):
        """`None` rather than a stale seat: the enters trigger's intervening-if
        has to read False, not "whoever was promised last time"."""
        game = a_gift_creature(builder)
        plain, _promised = gift_lines(game, GIFT_CREATURE)
        cast(game, plain[0])
        assert game.state.objects[oid_of(game, GIFT_CREATURE)].cast_gift_to is None

    def test_the_enters_trigger_fires_only_when_promised(self, builder):
        """"When this creature enters, **if the gift was promised**, draw."""
        drawn = {}
        for promise in (True, False):
            game = a_gift_creature(builder)
            plain, promised = gift_lines(game, GIFT_CREATURE)
            before = len(game.state.players[0].hand)
            cast(game, (promised if promise else plain)[0])
            # The gift card itself left the hand, so the delta is +1 per draw.
            drawn[promise] = len(game.state.players[0].hand) - (before - 1)
        assert drawn == {True: 1, False: 0}


class TestTheHarnessCanCastThePromisedLine:
    """The hole the measured `additional_cost: {}` hack fell into.

    That card loaded and passed all six gates while its gift branch never ran,
    because `find_play` selects by flags and it set none. A promise legality can
    offer has to be a promise the verifier can ask for, or gate 5 measures the
    unpromised half and calls the card good.
    """

    def test_find_play_asks_for_the_promised_line(self, builder):
        from commanderblitz.cards.authoring.verify import find_play

        game = a_gift_spell(builder)
        assert find_play(game, GIFT, gifted=True).gift_to is not None

    def test_and_for_the_unpromised_one(self, builder):
        from commanderblitz.cards.authoring.verify import find_play

        game = a_gift_spell(builder)
        assert find_play(game, GIFT).gift_to is None

    def test_the_residual_gate_claims_the_printed_line(self, registry):
        from commanderblitz.cards.authoring.verify import _covered

        card = registry.get(GIFT)
        printed = (
            "Gift a tapped Fish (You may promise an opponent a gift as you cast "
            "this spell. If you do, they create a tapped 1/1 blue Fish creature "
            "token before its other effects.)"
        )
        assert _covered(card, printed)

    def test_but_not_a_line_promising_something_else(self, registry):
        """Strict like multikicker's claimant: what is promised is the whole of
        what the line says, so a cheaper promise cannot wear these words."""
        from commanderblitz.cards.authoring.verify import _covered

        assert not _covered(registry.get(GIFT), "Gift a card")


class TestTheLoaderRefusesHalfAGift:
    """Half a gift is quieter than half a kicker: it is not even more expensive
    than the card it pretends to be, just a second line that does the same
    thing."""

    def a_spell(self, **extra) -> CardModel:
        base = {
            "id": "t_half_gift",
            "name": "Half Gift",
            "mana_cost": "{1}{W}",
            "types": ["Instant"],
            "spell_effects": [
                {"op": "gain_life", "player": "you", "amount": {"const": 1}}
            ],
        }
        base.update(extra)
        return CardModel(**base)

    def test_a_promise_nothing_reads(self):
        with pytest.raises(DslError, match="nothing reads"):
            compile_card(self.a_spell(gift="a tapped Fish"))

    def test_a_condition_with_no_promise(self):
        model = self.a_spell(
            spell_effects=[
                {
                    "op": "if",
                    "condition": {"gift_promised": True},
                    "then": [
                        {"op": "gain_life", "player": "you", "amount": {"const": 1}}
                    ],
                }
            ]
        )
        with pytest.raises(DslError, match="no 'gift' declaration"):
            compile_card(model)

    def test_a_recipient_with_no_promise(self):
        model = self.a_spell(
            spell_effects=[
                {"op": "draw", "player": "gift_recipient", "amount": {"const": 1}}
            ]
        )
        with pytest.raises(DslError, match="no 'gift' declaration"):
            compile_card(model)

    def test_an_empty_promise(self):
        model = self.a_spell(
            gift="  ",
            spell_effects=[
                {"op": "draw", "player": "gift_recipient", "amount": {"const": 1}}
            ],
        )
        with pytest.raises(DslError, match="must name what is promised"):
            compile_card(model)

    def test_naming_the_recipient_is_enough(self):
        """"Gift a card (they draw a card)" branches on nothing and is a real
        printed shape, so the guard must not demand `gift_promised` as well."""
        model = self.a_spell(
            gift="a card",
            spell_effects=[
                {"op": "draw", "player": "gift_recipient", "amount": {"const": 1}}
            ],
        )
        assert compile_card(model).gift == "a card"

    def test_a_misspelled_token_controller_is_caught_at_load(self):
        """`create_token`'s `controller` is a player spec, and it went
        unvalidated until a gift had to aim one at a particular seat."""
        model = self.a_spell(
            spell_effects=[
                {
                    "op": "create_token",
                    "token": FISH,
                    "controller": "gift_reciptient",
                }
            ]
        )
        with pytest.raises(DslError, match="unknown player spec"):
            compile_card(model)
