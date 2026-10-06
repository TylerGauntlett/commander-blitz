"""Casting a spell out of your own hand without paying for it.

"You may cast a spell with mana value X or less from your hand without paying
its mana cost" — Electrodominance. "…you may cast an instant or sorcery spell
from your hand … without paying its mana cost" — Glamdring.

The engine could already cast for free from the **library top** (`look_at_top`'s
`cast_free`, cascade, Bolas's Citadel) and from **exile** (`play_exiled`,
foretell, plot). The one zone it could not reach was the one every card of this
shape names, which is why two unrelated cards filed the same gap.

`grant_playable` is the near miss and is a *different sentence*: it permits a
play from a zone that normally forbids one, at the card's printed cost. A card
in hand needs no permission to be cast — it needs the price waived — so reaching
for it here would have produced a card that does nothing at all.

The load-bearing test is `TestItIsActuallyFree`, and it is built so that it
cannot pass by accident: the caster is left with **no untapped lands**, so a
spell that reached the stack cannot have been paid for.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind, Zone
from tests.conftest import pass_until, settle_to_priority

DOMINANCE = "t_dominance"  # {R}; free cast of an instant/sorcery with MV <= 2
UNBOUNDED = "t_dominance_any"  # {R}; free cast of any card in hand
DRAW = "t_demo_draw"  # {R} instant, MV 1 -- draw a card
RITUAL = "pyretic_ritual"  # {1}{R} instant, MV 2 -- add {R}{R}{R}
BEAR = "t_bear"  # {1}{G} creature, MV 2 -- not an instant or sorcery
BIG = "t_stormbolt"  # {2}{R} instant, MV 3 -- over the mana-value bound


def position(builder, hand, *, lands=2):
    """``lands`` untapped Mountains, and everything else tapped.

    The count is exact on purpose: two Mountains pay for the {R} enabler and
    leave one, which is not enough to hard-cast anything the enabler offers.
    """
    return (
        builder(players=2)
        .battlefield(0, ["mountain"] * lands)
        .battlefield(0, ["swamp"] * 6, tapped=True)
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, hand)
        .build()
    )


def cast(game, card_id: str):
    """Cast ``card_id`` and let it RESOLVE, stopping at the offer if one comes.

    The resolution step is not optional here. Casting only puts the enabler on
    the stack, and with a castable card still in hand its controller holds
    priority rather than passing -- so a test that read `pending()` straight
    after the cast would see PRIORITY and conclude the op never asked.
    """
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    pass_until(
        game,
        lambda g: (
            g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_OBJECTS
        )
        or not g.state.stack,
    )


def take_the_offer(game, card_id: str):
    """Answer the "you may cast" prompt by choosing ``card_id``.

    Explicit rather than letting `pass_until` answer it: the prompt has a
    minimum of zero, so the default chooser declines -- and a test that leaned
    on it would pass while the op did nothing at all.
    """
    pending = game.pending()
    assert pending is not None and pending.kind is DecisionKind.CHOOSE_OBJECTS
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CHOOSE
        and a.targets
        and game.state.objects[a.targets[0].id].def_id == card_id
    )
    game.apply(action)


def zone_of(game, card_id: str) -> Zone | None:
    for obj in game.state.objects.values():
        if obj.def_id == card_id and obj.owner == 0:
            return obj.zone
    return None


class TestItOffersTheCast:
    def test_a_matching_card_is_offered(self, builder):
        game = position(builder, [DOMINANCE, DRAW])
        cast(game, DOMINANCE)

        pending = game.pending()
        assert pending is not None
        assert pending.kind is DecisionKind.CHOOSE_OBJECTS
        assert pending.min_count == 0, "'you may' -- declining must be legal"

    def test_the_chosen_spell_resolves(self, builder):
        game = position(builder, [DOMINANCE, DRAW])
        library_before = len(game.state.players[0].library)

        cast(game, DOMINANCE)
        take_the_offer(game, DRAW)
        settle_to_priority(game)

        assert len(game.state.players[0].library) == library_before - 1, "the draw happened"
        assert zone_of(game, DRAW) is Zone.GRAVEYARD


class TestItIsActuallyFree:
    def test_it_casts_with_no_mana_available(self, builder):
        """One Mountain left after the enabler cannot pay for a {1}{R} spell."""
        game = position(builder, [DOMINANCE, RITUAL])
        cast(game, DOMINANCE)
        untapped = [
            o
            for o in game.state.battlefield
            if not game.state.objects[o].tapped and game.state.objects[o].controller == 0
        ]
        assert len(untapped) <= 1, "not enough mana to hard-cast the ritual"

        take_the_offer(game, RITUAL)
        settle_to_priority(game)
        assert zone_of(game, RITUAL) is Zone.GRAVEYARD, "it was cast anyway, so it was free"


class TestTheSelectorRestricts:
    def test_a_creature_card_is_not_offered_to_an_instant_or_sorcery_filter(self, builder):
        """Asserted on the *offer*, not on the outcome.

        Checking only that the Bear stayed in hand would pass with the op
        broken, because the prompt's minimum is zero and the default chooser
        declines everything.
        """
        game = position(builder, [DOMINANCE, BEAR])
        cast(game, DOMINANCE)

        pending = game.pending()
        assert pending is None or pending.kind is DecisionKind.PRIORITY, "nothing to offer"

    def test_a_card_over_the_mana_value_bound_is_not_offered(self, builder):
        """"mana value 2 or less" -- the printed bound, not a suggestion."""
        game = position(builder, [DOMINANCE, BIG])
        cast(game, DOMINANCE)

        pending = game.pending()
        assert pending is None or pending.kind is DecisionKind.PRIORITY

    def test_with_no_selector_any_card_in_hand_qualifies(self, builder):
        game = position(builder, [UNBOUNDED, BEAR])
        cast(game, UNBOUNDED)
        take_the_offer(game, BEAR)
        settle_to_priority(game)

        assert zone_of(game, BEAR) is Zone.BATTLEFIELD, "a creature is 'a spell'"


class TestALandIsNotASpell:
    """305.9. A land is played, never cast, so it is never on offer.

    The printed restriction on every card of this shape is a mana value, and a
    land's is 0 -- so without an explicit exclusion the bare printed filter
    matches a Forest and the "spell" cast is a land drop out of nowhere. Gate 5
    caught it: the sandbox's spare Forest disappeared from hand.
    """

    def test_a_land_is_not_offered_even_with_no_selector(self, builder):
        game = position(builder, [UNBOUNDED, "forest"])
        cast(game, UNBOUNDED)

        pending = game.pending()
        assert pending is None or pending.kind is DecisionKind.PRIORITY

    def test_the_land_is_still_in_hand_afterwards(self, builder):
        game = position(builder, [UNBOUNDED, "forest"])
        cast(game, UNBOUNDED)
        settle_to_priority(game)

        # By hand contents, not `zone_of`: the library is twenty Forests, and a
        # lookup by def_id would happily find one of those and pass.
        in_hand = [game.state.objects[o].def_id for o in game.state.players[0].hand]
        assert in_hand == ["forest"]


class TestNothingToOffer:
    def test_an_empty_hand_asks_nothing_and_does_not_crash(self, builder):
        """The boundary. Not asked at all, rather than asked and declined."""
        game = position(builder, [DOMINANCE])
        cast(game, DOMINANCE)

        pending = game.pending()
        assert pending is None or pending.kind is DecisionKind.PRIORITY

        settle_to_priority(game)
        assert zone_of(game, DOMINANCE) is Zone.GRAVEYARD

    def test_a_hand_of_only_non_matching_cards_asks_nothing(self, builder):
        game = position(builder, [DOMINANCE, BEAR, BIG])
        cast(game, DOMINANCE)

        pending = game.pending()
        assert pending is None or pending.kind is DecisionKind.PRIORITY
