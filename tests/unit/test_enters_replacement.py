"""A permanent whose own arrival is replaced.

    "If this artifact **would enter**, you may discard a land card instead.
    If you do, put this artifact onto the battlefield. If you don't, put it
    into its owner's graveyard."                        -- Mox Diamond

614.1a, and the sixth entry on the enters-the-battlefield replacement whitelist.
The first five -- `self_enters`, `self_enters_tapped`,
`self_enters_with_counters`, `self_enters_prepared`, `self_enters_as_copy` --
every one of them decorates a permanent that is **already arriving**, and
`zones._enter_battlefield` reads nothing from them but `tapped`, `counters`,
`prepared` and `copying`. None can charge a price and none has a destination
other than the battlefield, because by the time that function runs the object is
already on it.

**Not a `self_enters` trigger running `may` + `discard` + `sacrifice`.** That is
the approximation the rules forbid and the reason this test exists: written that
way the artifact really does enter, every enters trigger on the table sees it, an
opponent gets priority with it on the battlefield, and it reaches the graveyard
*from* the battlefield -- so it dies, feeds a death trigger, and can be responded
to. The printed card says it was never there.

**The price is not `unless_cost` either.** That one is paid to *avoid* a
modification -- "as this land enters, you may pay 3 life; if you don't it enters
tapped" -- and the land arrives on either answer. Here the payment is what buys
the arrival, so the two keys mean opposite things and are deliberately two keys.

**However it arrives, not only when it is cast.** The card says "if this artifact
**would enter**", which is any arrival from any zone, so the offer is made by
every path that can stop to ask -- the cast line, the land drop,
`put_onto_battlefield`, `return_from_graveyard` and the exile-and-return blink --
and `move_object` treats an arrival nobody was asked about as unpaid rather than
letting it enter for free. A replacement wired into the cast path alone passes a
naive test and is wrong for every blink and reanimation in the format, so the
non-cast arrivals are pinned here beside the cast one.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.errors import DslError
from tests.conftest import pass_until

MOX = "t_er_mox"  # {0} artifact, arrival replaced by a land discard
EXILING = "t_er_exiled"  # the same, but `instead_zone: exile`
PLAIN = "t_er_plain"  # the same artifact with no clause -- the control
WATCHER = "t_er_watcher"  # gains 1 life whenever an artifact you control enters
REANIMATE = "t_er_reanimate"  # returns an artifact from your graveyard
CHEAT = "t_er_cheat"  # puts an artifact from your hand onto the battlefield


def position(builder, hand, *, graveyard=(), board=()):
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 6)
        .battlefield(0, list(board))
        .hand(0, list(hand))
        .graveyard(0, list(graveyard))
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def cast(game, card_id: str, *, say_yes: bool = True):
    """Cast ``card_id``, answering the replacement's question on the way in.

    The question arrives as an ordinary pending decision *during the
    resolution*, before anything is on the battlefield -- which is the whole
    point of the clause and the thing a `self_enters` trigger could not do.
    """
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    _answer(game, say_yes=say_yes)


def _answer(game, *, say_yes: bool):
    for _ in range(40):
        pending = game.pending()
        if pending is None or pending.kind is DecisionKind.PRIORITY:
            break
        if pending.kind is DecisionKind.MAY:
            want = ActionKind.YES if say_yes else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is want))
            continue
        choices = [a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]
        if not choices:
            break
        game.apply(choices[0])
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def find(game, def_id: str):
    """The one object with this def id, wherever it now is."""
    return next(o for o in game.state.objects.values() if o.def_id == def_id)


def spare_land(game) -> int:
    """The Forest sitting in hand as the price. Read *before* casting.

    Named rather than counted, because the artifact draws a card as it enters:
    a hand that lost the land and gained a card is the same size as one that
    paid nothing, and only the land's own zone tells the two apart.
    """
    return next(
        oid
        for oid in game.state.players[0].hand
        if game.state.objects[oid].def_id == "forest"
    )


def asked(game) -> bool:
    """Whether a yes/no question is on the table right now."""
    pending = game.pending()
    return pending is not None and pending.kind is DecisionKind.MAY


class TestPayingLetsItEnter:
    def test_it_is_on_the_battlefield(self, builder):
        game = position(builder, [MOX, "forest"])
        cast(game, MOX)
        assert find(game, MOX).zone is Zone.BATTLEFIELD

    def test_the_land_is_discarded(self, builder):
        """"you may **discard a land card**" -- a real payment, taken out of
        hand and into the graveyard, not a flag."""
        game = position(builder, [MOX, "forest"])
        land = spare_land(game)
        cast(game, MOX)
        assert game.state.objects[land].zone is Zone.GRAVEYARD
        assert land in game.state.players[0].graveyard

    def test_the_enters_trigger_fires(self, builder):
        """It really entered, so everything that watches an arrival saw it."""
        game = position(builder, [MOX, "forest"], board=[WATCHER])
        life = game.state.players[0].life
        cast(game, MOX)
        assert game.state.players[0].life == life + 1

    def test_only_a_land_may_be_discarded(self, builder):
        """`discard_selector` narrows the price. With a hand of one non-land
        the cost is unpayable, so the question is never asked."""
        game = position(builder, [MOX, PLAIN])
        cast(game, MOX)
        assert find(game, MOX).zone is Zone.GRAVEYARD
        assert find(game, PLAIN).zone is Zone.HAND


class TestDecliningNeverEnters:
    def test_it_goes_to_its_owners_graveyard(self, builder):
        game = position(builder, [MOX, "forest"])
        cast(game, MOX, say_yes=False)
        assert find(game, MOX).zone is Zone.GRAVEYARD

    def test_it_was_never_on_the_battlefield(self, builder):
        """The difference between this and a trigger that sacrifices: nothing
        of the artifact is on the battlefield at any point, so no opponent ever
        held priority with it there."""
        game = position(builder, [MOX, "forest"])
        cast(game, MOX, say_yes=False)
        assert find(game, MOX).oid not in game.state.battlefield

    def test_no_enters_trigger_saw_it(self, builder):
        """The whole rules argument. A `self_enters` trigger running `may` +
        `discard` + `sacrifice` would have fired this watcher and the Mox's own
        draw; a replacement of the arrival fires neither."""
        game = position(builder, [MOX, "forest"], board=[WATCHER])
        life = game.state.players[0].life
        library = len(game.state.players[0].library)
        cast(game, MOX, say_yes=False)
        assert game.state.players[0].life == life
        assert len(game.state.players[0].library) == library

    def test_the_land_is_kept(self, builder):
        """Declined means nothing was paid."""
        game = position(builder, [MOX, "forest"])
        land = spare_land(game)
        cast(game, MOX, say_yes=False)
        assert game.state.objects[land].zone is Zone.HAND

    def test_instead_zone_is_honoured(self, builder):
        """"If you don't, **exile it**" -- the destination is the card's, not
        a hardcoded graveyard."""
        game = position(builder, [EXILING, "forest"])
        cast(game, EXILING, say_yes=False)
        assert find(game, EXILING).zone is Zone.EXILE


class TestAnUnpayablePriceIsNotOffered:
    def test_no_question_with_no_land_in_hand(self, builder):
        """`can_pay` first, exactly as `offer_enters_costs` asks it: a player
        with nothing to discard is not shown a question whose yes cannot be
        honoured."""
        game = position(builder, [MOX])
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == MOX
        )
        game.apply(action)
        assert not asked(game), "asked to discard a land with none in hand"
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert find(game, MOX).zone is Zone.GRAVEYARD

    def test_it_cannot_discard_itself(self, builder):
        """601.2a keeps a card from paying with itself, and `_discard_pool`
        drops the source for that reason. The artifact is on the stack when the
        question is asked, so a hand of only the Mox has no fodder at all."""
        game = position(builder, [MOX])
        cast(game, MOX)
        assert find(game, MOX).zone is Zone.GRAVEYARD


class TestEveryArrivalIsAsked:
    """The point of the whole design. "If this artifact **would enter**" is any
    arrival from any zone, and a replacement wired into the cast path alone
    passes every test above and is wrong for the rest of the format."""

    def test_reanimation_offers_the_price(self, builder):
        game = position(builder, [REANIMATE, "forest"], graveyard=[MOX])
        land = spare_land(game)
        cast(game, REANIMATE)
        assert find(game, MOX).zone is Zone.BATTLEFIELD
        assert game.state.objects[land].zone is Zone.GRAVEYARD, "the land paid for it"

    def test_declining_leaves_it_in_the_graveyard(self, builder):
        game = position(builder, [REANIMATE, "forest"], graveyard=[MOX])
        land = spare_land(game)
        cast(game, REANIMATE, say_yes=False)
        assert find(game, MOX).zone is Zone.GRAVEYARD
        assert game.state.objects[land].zone is Zone.HAND

    def test_a_reanimated_arrival_fires_no_trigger_when_declined(self, builder):
        game = position(builder, [REANIMATE, "forest"], graveyard=[MOX], board=[WATCHER])
        life = game.state.players[0].life
        cast(game, REANIMATE, say_yes=False)
        assert game.state.players[0].life == life

    def test_put_onto_battlefield_offers_the_price(self, builder):
        """The generic cheat-into-play route -- reanimation's cousin and the
        one every blink effect shares."""
        game = position(builder, [CHEAT, MOX, "forest"])
        cast(game, CHEAT)
        assert find(game, MOX).zone is Zone.BATTLEFIELD

    def test_put_onto_battlefield_honours_a_decline(self, builder):
        game = position(builder, [CHEAT, MOX, "forest"])
        cast(game, CHEAT, say_yes=False)
        assert find(game, MOX).zone is Zone.GRAVEYARD
        assert find(game, MOX).oid not in game.state.battlefield


class TestWithoutTheClause:
    """The control: the same artifact with no replacement is asked nothing and
    enters for free."""

    def test_it_enters_and_triggers(self, builder):
        game = position(builder, [PLAIN, "forest"], board=[WATCHER])
        life = game.state.players[0].life
        land = spare_land(game)
        cast(game, PLAIN)
        assert find(game, PLAIN).zone is Zone.BATTLEFIELD
        assert game.state.players[0].life == life + 1
        assert game.state.objects[land].zone is Zone.HAND, "never asked for"


class TestTheLoaderRefusesTheNearMisses:
    def _card(self, replacement):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "types": ["Artifact"],
                "mana_cost": "{0}",
                "replacements": [replacement],
            }
        )

    def test_a_price_is_required(self):
        """With no price there is nothing to pay, so the permanent could never
        enter -- a card that is only ever a way of putting itself in a
        graveyard."""
        with pytest.raises(DslError, match="instead_cost"):
            compile_card(self._card({"event": "self_enters_replaced"}))

    def test_the_price_keys_are_checked_at_load(self):
        """`CostModel`'s vocabulary, so a typo is a load error rather than a
        price silently dropped into a free arrival."""
        with pytest.raises(DslError, match="instead_cost"):
            compile_card(
                self._card(
                    {
                        "event": "self_enters_replaced",
                        "instead_cost": {"discrad": 1},
                    }
                )
            )

    def test_the_price_is_refused_on_another_event(self):
        """`instead_cost` and `unless_cost` are one typo apart and mean
        opposite things, so neither is readable by the other's event."""
        with pytest.raises(DslError, match="instead_cost"):
            compile_card(
                self._card(
                    {
                        "event": "self_enters_tapped",
                        "instead_cost": {"pay_life": 3},
                    }
                )
            )
