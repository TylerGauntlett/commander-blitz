"""601.2f — every way of casting a spell owes its additional cost.

Laughing Mad:

    As an additional cost to cast this spell, discard a card.
    Draw two cards.
    Flashback {3}{R} (You may cast this card from your graveyard for its
    flashback cost **and any additional costs**. Then exile it.)

Flashback's own reminder text spells the rule out, and the engine broke it. The
additional-cost block lived inside `_cast_options` behind
`state.objects[oid].zone is Zone.HAND`, while the flashback line was built by
calling `_cast_variant(..., flashback=True)` straight from the graveyard loop
with `additional_times` left at its default of 0. `Game._cast` pays the non-mana
half only when that count is nonzero, so a flashed-back Laughing Mad paid
{3}{R}, discarded nothing and drew two — a strictly better card than the printed
one, and one that looks entirely normal on screen.

The same hole ran under **foretell**, which casts from exile by the same direct
call, and under **retrace** and a **commander** cast, which reach
`_cast_options` from a zone that is not the hand. So the fix is one helper,
`_charge_additional_cost`, applied at every cast line rather than a second copy
of the block bolted onto flashback.

Moving the discard into `spell_effects` is not a substitute and is the reason
this is engine work rather than card work: an effect is paid at resolution, so
the spell could be cast when the price could not be paid at all.

`t_plain_laughter` is the counterfactual — the same card, same flashback, no
additional cost — so every difference asserted below is that one field.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone

MAD = "t_mad_laughter"
PLAIN = "t_plain_laughter"


def from_graveyard(builder, card_id: str, *, hand: int = 2):
    """The card in the graveyard, lands to flash it back, cards to discard."""
    return (
        builder(players=2)
        .graveyard(0, [card_id])
        .hand(0, ["forest"] * hand)
        .battlefield(0, ["mountain"] * 6)
        .library(0, ["forest"] * 20)
        .build()
    )


def from_hand(builder, card_id: str, *, hand_extra: int = 1):
    return (
        builder(players=2)
        .hand(0, [card_id, *["forest"] * hand_extra])
        .battlefield(0, ["mountain"] * 6)
        .library(0, ["forest"] * 20)
        .build()
    )


def cast_lines(game, card_id: str):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    ]


class TestTheFlashbackLineIsCharged:
    """The bug, and the card that found it."""

    def test_flashing_it_back_costs_the_discard(self, builder):
        game = from_graveyard(builder, MAD)
        lines = cast_lines(game, MAD)
        assert lines, "no flashback line at all"
        assert all(a.additional_times == 1 for a in lines), (
            "a flashed-back spell must still owe its additional cost (601.2f)"
        )

    def test_the_free_line_is_not_offered(self, builder):
        """A mandatory cost withdraws the uncharged line everywhere."""
        game = from_graveyard(builder, MAD)
        assert not [a for a in cast_lines(game, MAD) if a.additional_times == 0]

    def test_without_an_additional_cost_nothing_is_charged(self, builder):
        """The counterfactual: flashback alone adds no price."""
        game = from_graveyard(builder, PLAIN)
        lines = cast_lines(game, PLAIN)
        assert lines
        assert all(a.additional_times == 0 for a in lines)

    def test_an_empty_hand_makes_it_uncastable(self, builder):
        """Nothing to discard, so the cost cannot be paid and no line survives.

        This is the half that a "charge it only when convenient" fix would get
        wrong in the other direction, so it is asserted rather than assumed.
        """
        game = from_graveyard(builder, MAD, hand=0)
        assert cast_lines(game, MAD) == []

    def test_the_plain_card_is_still_castable_with_an_empty_hand(self, builder):
        game = from_graveyard(builder, PLAIN, hand=0)
        assert cast_lines(game, PLAIN)


class TestTheHandLineStillWorks:
    """The behaviour that was already right must not have moved."""

    def test_casting_from_hand_is_charged(self, builder):
        game = from_hand(builder, MAD)
        lines = cast_lines(game, MAD)
        assert lines
        assert all(a.additional_times == 1 for a in lines)

    def test_the_card_is_in_hand_not_the_graveyard(self, builder):
        """Guards the fixture itself, so the test above cannot pass by accident."""
        game = from_hand(builder, MAD)
        oid = cast_lines(game, MAD)[0].source
        assert game.state.objects[oid].zone is Zone.HAND


def flash_it_back(game, card_id: str):
    """Cast the card from the graveyard, answering the discard if asked."""
    game.apply(cast_lines(game, card_id)[0])
    decision = game.pending()
    if decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS:
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE))
    return game


def graveyard_ids(game, pid: int = 0):
    state = game.state
    return [state.card_of(state.objects[o]).id for o in state.players[pid].graveyard]


class TestPayingIt:
    """Offering the line is half the fix; charging it is the other half.

    Measured on the **graveyard**, not the hand. Laughing Mad draws two, so the
    hand ends up *larger* than it started whether or not the discard happened --
    2 - 1 + 2 = 3 against 2 + 2 = 4. Asserting on hand size alone would be a
    test that passes for the wrong reason, so the discarded card is located
    instead.
    """

    def test_the_discarded_card_is_in_the_graveyard(self, builder):
        game = flash_it_back(from_graveyard(builder, MAD), MAD)
        assert graveyard_ids(game) == ["forest"], (
            "the additional cost was offered but never actually charged"
        )

    def test_the_counterfactual_discards_nothing(self, builder):
        game = flash_it_back(from_graveyard(builder, PLAIN), PLAIN)
        assert graveyard_ids(game) == []

    def test_the_spell_still_flashes_back_and_exiles(self, builder):
        """The cost is charged without breaking what flashback is for."""
        game = flash_it_back(from_graveyard(builder, MAD), MAD)
        state = game.state
        exiled = [state.card_of(state.objects[o]).id for o in state.players[0].exile]
        assert exiled == [MAD]

    def test_it_still_draws_two(self, builder):
        """2 in hand, minus the discard, plus the draw."""
        game = flash_it_back(from_graveyard(builder, MAD), MAD)
        assert len(game.state.players[0].hand) == 3
