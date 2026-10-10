"""Exiling a card from your hand as a cost -- the free-spell pitch.

Rule 118.9 lets a spell offer an alternative cost, and 601.2f-h charges it as the
spell is cast; rule 601.2a puts the spell on the stack *before* any of that, so a
card can never be its own fodder. Force of Will is blue and sits in the same hand
it is pitching from, which makes that last clause the difference between a card
that costs something and one that costs nothing.

The zone is the other half, and it is not a detail. `discard_selector` already
picked a card out of hand by exactly this kind of filter, and it puts the card in
the **graveyard** -- where delirium, threshold, Tarmogoyf and every reanimation
spell can still see it. The printed pitch costs *exile*, and that difference is
the whole reason these spells are priced at nothing.

Two shipped cards are the witnesses, one for each half:

* **Force of Will** -- "You may pay 1 life and exile a blue card from your hand
  rather than pay this spell's mana cost." A selector pitch, inside a card-level
  `alternative_cost` that charges no mana at all. Before this the loader hard
  required an `alternative_cost` to be a bare mana string, so there was nowhere
  on the card for a non-mana payment to live. **Daze** is the same claim with a
  return instead of an exile, and is asserted here for that reason.
* **Simian Spirit Guide** -- "Exile this card from your hand: Add {R}." An
  activated mana ability whose cost is the source leaving the hand. `exile_self`
  could not do it: `costs.can_pay` requires that one's source to be on the
  battlefield -- Phoenix Down's "exile this artifact" -- so a Spirit Guide
  written with it loaded clean and could never be activated, which is worse than
  not shipping it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.stack import push_spell
from commanderblitz.engine.state import new_object
from tests.conftest import _default_answer, only_oid


def hand_oid(game, card_id: str, pid: int = 0) -> int:
    """The one copy of ``card_id`` in a player's hand.

    `conftest.only_oid` walks the battlefield, and every card this file is about
    is being paid *out of hand* -- which is the whole point of the cost.
    """
    found = [
        oid
        for oid in game.state.players[pid].hand
        if game.state.objects[oid].def_id == card_id
    ]
    assert len(found) == 1, f"expected exactly one {card_id} in hand, found {len(found)}"
    return found[0]


def pitch_position(builder, *, hand: list[str], lands: int = 0):
    """Force of Will in hand with ``hand`` beside it, and a spell to counter.

    An opponent's spell is pushed onto the stack directly rather than cast: the
    claim under test is about the *cost*, and "counter target spell" is simply
    not offered at all without a target, so a position with an empty stack would
    make every assertion here vacuously true.

    Built frozen and advanced only once the spell is on the stack, the order
    `verify.build_sandbox` uses. Advancing first auto-passes a player who has
    nothing to do, and a hand of one uncastable spell is exactly that -- so
    priority reached the opponent and `legal_actions` answered the wrong
    player's question.
    """
    game = (
        builder(players=2)
        .hand(0, ["force_of_will", *hand])
        .battlefield(0, ["island"] * lands)
        .build(advance=False)
    )
    obj = new_object(game.state, "lightning_bolt", owner=1, zone=Zone.HAND)
    game.state.players[1].hand.append(obj.oid)
    push_spell(game.state, obj.oid, 1)
    game._advance()
    return game, hand_oid(game, "force_of_will")


def pitch_lines(game) -> list:
    return [
        a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.alternative
    ]


def printed_lines(game) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and not a.alternative
    ]


def settle(game, limit: int = 60) -> None:
    for _ in range(limit):
        if not game.state.stack and not game.state.pending_triggers:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))


def untapped_lands(game, pid: int = 0) -> int:
    return sum(
        1
        for o in game.state.battlefield_objects(pid)
        if not o.tapped and "Land" in game.state.card_of(o).types
    )


class TestWhenTheLineIsOffered:
    def test_a_blue_card_in_hand_buys_the_line(self, builder):
        game, _ = pitch_position(builder, hand=["island", "counterspell"])
        assert pitch_lines(game), "a blue card is the price and one is in hand"

    def test_a_hand_of_the_wrong_colour_does_not(self, builder):
        """"a **blue** card" -- the selector is the cost, not decoration."""
        game, _ = pitch_position(builder, hand=["mountain", "lightning_bolt"])
        assert pitch_lines(game) == []

    def test_the_spell_may_not_pitch_itself(self, builder):
        """601.2a: the spell is on the stack before its costs are paid.

        Force of Will is itself a blue card, and legality prices the line while
        it is still sitting in hand -- so without the exclusion it pays for
        itself, is exiled by its own cost, and never resolves.
        """
        game, _ = pitch_position(builder, hand=["mountain"])
        assert pitch_lines(game) == [], "the only blue card in hand is the spell"

    def test_an_empty_hand_beside_it_does_not_offer_the_line(self, builder):
        game, _ = pitch_position(builder, hand=[])
        assert pitch_lines(game) == []

    def test_the_printed_price_is_still_offered_beside_it(self, builder):
        """Two prices for one card are two actions; the player chooses."""
        game, _ = pitch_position(builder, hand=["counterspell"], lands=5)
        assert printed_lines(game) and pitch_lines(game)

    def test_life_is_part_of_the_price(self, builder):
        """118.4 lets a player pay life down to exactly 0, and no further."""
        game, _ = pitch_position(builder, hand=["counterspell"])
        game.state.players[0].life = 1
        assert pitch_lines(game), "1 life is payable at 1 life"
        game.state.players[0].life = 0
        assert pitch_lines(game) == []


class TestWhatItCharges:
    def test_the_pitched_card_is_exiled_not_discarded(self, builder):
        """The whole difference from `discard_selector`."""
        game, _ = pitch_position(builder, hand=["counterspell"])
        pitched = hand_oid(game, "counterspell")
        game.apply(pitch_lines(game)[0])
        settle(game)
        assert game.state.objects[pitched].zone is Zone.EXILE

    def test_one_life_is_paid(self, builder):
        game, _ = pitch_position(builder, hand=["counterspell"])
        before = game.state.players[0].life
        game.apply(pitch_lines(game)[0])
        settle(game)
        assert game.state.players[0].life == before - 1

    def test_no_mana_is_spent(self, builder):
        """"…rather than pay this spell's mana cost." The alternative cost
        replaces the printed {3}{U}{U} outright rather than reducing it."""
        game, _ = pitch_position(builder, hand=["counterspell"], lands=5)
        before = untapped_lands(game)
        game.apply(pitch_lines(game)[0])
        settle(game)
        assert untapped_lands(game) == before

    def test_the_printed_price_still_charges_mana_and_no_life(self, builder):
        game, _ = pitch_position(builder, hand=["counterspell"], lands=5)
        life = game.state.players[0].life
        pitched = hand_oid(game, "counterspell")
        game.apply(printed_lines(game)[0])
        settle(game)
        assert untapped_lands(game) == 0, "{3}{U}{U} off five Islands"
        assert game.state.players[0].life == life
        assert game.state.objects[pitched].zone is Zone.HAND

    def test_the_spell_still_counters(self, builder):
        """A cost that got paid and a spell that did nothing is not the card."""
        game, _ = pitch_position(builder, hand=["counterspell"])
        countered = game.state.stack[0].oid
        game.apply(pitch_lines(game)[0])
        settle(game)
        assert game.state.objects[countered].zone is Zone.GRAVEYARD
        assert not game.state.stack


class TestExilingTheSourceItself:
    """Simian Spirit Guide -- `exile_self_from_hand`, cycling's shape one zone over."""

    def position(self, builder, *, in_hand: bool = True):
        """The Guide, and a Lightning Bolt with no land to cast it off.

        The Bolt is the meter: this position has no mana at all, so a Bolt that
        becomes castable did so on mana the Guide made. It also keeps priority
        where it belongs -- a player with nothing to do is auto-passed, and the
        floating mana empties with the step.
        """
        make = builder(players=2).hand(0, ["lightning_bolt"])
        if in_hand:
            make.hand(0, ["simian_spirit_guide"])
        else:
            make.battlefield(0, ["simian_spirit_guide"])
        game = make.build()
        if in_hand:
            return game, hand_oid(game, "simian_spirit_guide")
        return game, only_oid(game, "simian_spirit_guide")

    def can_cast_bolt(self, game) -> bool:
        return any(
            a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "lightning_bolt"
            for a in game.legal_actions()
        )

    def activation(self, game, oid: int):
        return next(
            (
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ACTIVATE and a.source == oid
            ),
            None,
        )

    def test_it_is_activatable_from_hand(self, builder):
        """The bug `exile_self` left behind: the card loaded and the ability was
        never once offered, because `can_pay` demanded the battlefield."""
        game, oid = self.position(builder)
        assert self.activation(game, oid) is not None

    def test_it_is_not_activatable_from_the_battlefield(self, builder):
        """`active_zones` is the permission and it says hand. A 2/2 Ape on the
        battlefield has no printed ability at all."""
        game, oid = self.position(builder, in_hand=False)
        assert self.activation(game, oid) is None

    def test_activating_it_exiles_the_card(self, builder):
        game, oid = self.position(builder)
        game.apply(self.activation(game, oid))
        assert game.state.objects[oid].zone is Zone.EXILE
        assert oid not in game.state.players[0].hand

    def test_the_mana_it_makes_can_pay_for_a_spell(self, builder):
        """A mana ability that produced nothing spendable would be a card that
        exiles itself for free, and no assertion on the pool alone would say so
        -- floating mana empties with the step."""
        game, oid = self.position(builder)
        assert not self.can_cast_bolt(game), "no lands: {R} is out of reach"
        game.apply(self.activation(game, oid))
        assert self.can_cast_bolt(game)

    def test_it_cannot_be_activated_twice(self, builder):
        """The cost is the card, so there is no second activation to price --
        which is the property that makes an ability in hand safe at all."""
        game, oid = self.position(builder)
        game.apply(self.activation(game, oid))
        assert self.activation(game, oid) is None


class TestANonManaAlternativeCost:
    """Daze: the same widened `alternative_cost` slot, paying a bounce."""

    def position(self, builder, *, islands: int):
        game = (
            builder(players=2)
            .hand(0, ["daze"])
            .battlefield(0, ["island"] * islands)
            .build(advance=False)
        )
        obj = new_object(game.state, "lightning_bolt", owner=1, zone=Zone.HAND)
        game.state.players[1].hand.append(obj.oid)
        push_spell(game.state, obj.oid, 1)
        game._advance()
        return game

    def test_no_island_means_no_free_line(self, builder):
        """The near-miss this replaces -- `condition: {exists: Island}` with a
        mana cost of `{0}` -- would be free here *and* keep the Island."""
        game = self.position(builder, islands=0)
        assert pitch_lines(game) == []

    def test_an_island_buys_the_line_and_goes_back_to_hand(self, builder):
        game = self.position(builder, islands=1)
        island = only_oid(game, "island")
        assert pitch_lines(game)
        game.apply(pitch_lines(game)[0])
        settle(game)
        assert game.state.objects[island].zone is Zone.HAND


class TestTheLoaderGuardsIt:
    def base(self, **card) -> dict:
        return {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "Draw a card.",
            "mana_cost": "{2}{U}",
            "types": ["Sorcery"],
            "spell_effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
            **card,
        }

    def test_an_alternative_cost_that_charges_nothing_is_refused(self):
        """It *replaces* the printed cost, so an empty node is a free spell."""
        with pytest.raises(DslError, match="needs 'mana' or a non-mana payment"):
            compile_card(
                CardModel.model_validate(
                    self.base(alternative_cost={"condition": {"is_your_turn": True}})
                )
            )

    def test_an_unconditional_mana_only_alternative_cost_is_still_evoke(self):
        """The guard `alternative_cost` shipped with, unchanged: a cheaper mana
        price with no gate is `evoke` under a second name."""
        with pytest.raises(DslError, match="needs a 'condition'"):
            compile_card(
                CardModel.model_validate(self.base(alternative_cost={"mana": "{U}"}))
            )

    def test_a_non_mana_payment_needs_no_condition(self):
        """Force of Will's line is unconditional and printed, and it is not
        evoke: there is no mana price on it at all."""
        card = compile_card(
            CardModel.model_validate(
                self.base(
                    alternative_cost={"pay_life": 1, "exile_from_hand": {"colors": ["U"]}}
                )
            )
        )
        assert card.alternative_cost is not None
        assert card.alternative_condition is None

    def test_a_zone_on_the_pool_is_refused(self):
        """The pool is the payer's own hand and nothing else -- a hidden zone,
        so an opponent's card must never become fodder. A knob that reads as if
        it worked would be overwritten in silence."""
        with pytest.raises(DslError, match="'zone' is implied"):
            compile_card(
                CardModel.model_validate(
                    self.base(
                        alternative_cost={"exile_from_hand": {"zone": "graveyard"}}
                    )
                )
            )

    def test_a_cost_that_charges_the_source_permanent_is_refused(self):
        """The source of a cast-time cost is the spell, on its way from hand to
        stack. `can_pay` refuses a tap there, so the line would load and never
        once be offered -- the silently inert card this whole capability exists
        to stop shipping."""
        with pytest.raises(DslError, match="charge the source permanent"):
            compile_card(
                CardModel.model_validate(
                    self.base(alternative_cost={"mana": "{U}", "tap": True})
                )
            )

    def test_a_bad_selector_key_is_refused(self):
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    self.base(alternative_cost={"exile_from_hand": {"nonsense": 1}})
                )
            )

    def test_the_two_self_exiles_may_not_both_be_written(self):
        """One source, two zones: whichever `can_pay` checked first would decide
        where the card had to be, and the other half would be dead text."""
        with pytest.raises(DslError, match="not both"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "guide",
                        "name": "Guide",
                        "oracle_text": "Exile this card from your hand: Add {R}.",
                        "mana_cost": "{2}{R}",
                        "types": ["Creature"],
                        "subtypes": ["Ape"],
                        "power": 2,
                        "toughness": 2,
                        "abilities": [
                            {
                                "kind": "activated",
                                "text": "Exile this card from your hand: Add {R}.",
                                "active_zones": ["hand"],
                                "cost": {
                                    "exile_self_from_hand": True,
                                    "exile_self": True,
                                },
                                "effects": [{"op": "add_mana", "mana": "{R}"}],
                            }
                        ],
                    }
                )
            )

    def test_the_shipped_cards_compile(self, registry):
        will = registry.get("force_of_will")
        assert will.alternative_cost is not None
        assert will.alternative_cost.exile_from_hand == {"colors": ["U"]}
        assert will.alternative_cost.pay_life == 1
        assert not will.alternative_cost.mana.text, "no mana at all"
        guide = registry.get("simian_spirit_guide")
        assert guide.abilities[0].cost.exile_self_from_hand
