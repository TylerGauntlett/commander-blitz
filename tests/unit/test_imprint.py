"""Imprint — an exile link that already existed, read from the other end.

    "Imprint — When this artifact enters, you may exile a creature card from
    your hand.
     {3}, {T}: Create a token that's a copy of the exiled card."

The census filed this as "exile attached to a permanent, with abilities reading
the exiled card". Both halves shipped for Oblivion Ring and Scute Swarm and had
never been put together:

- `exile` with `until_leaves` writes the link, and it points from the exiled
  card at the **exiler** — which is the direction imprint wants, unlike haunt.
  Imprint's abilities belong to the permanent, and the permanent is what has to
  find its own card.
- `{"zone": "exile", "controller": "any", "exiled_with": "self"}` reads it back,
  and `copy_permanent` takes any object rather than a battlefield one.

Two details that are easy to lose and are both O-Ring's, restated here because
imprint is where they bite differently:

- **`controller: "any"` is required.** An exiled card keeps its last controller,
  and the selector language defaults `controller` to `"you"` — which happens to
  be right for a card imprinted from your own hand and would silently stop
  working for any card that reaches exile from elsewhere.
- **A bare `{"zone": "exile"}` matches every card in exile from every source**,
  so the copy would be of somebody else's card.

The one genuinely imprint-shaped property is that the link outlives the *use*:
copying it does not spend it, and the artifact goes on copying the same card.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Zone
from tests.conftest import action_for_card, only_oid, pass_until

WASTE = "island"
FOUNDRY = "t_imprinter"
BEAR = "t_bear"
GIANT = "t_big"


def position(builder, hand: list[str]):
    return (
        builder(players=2)
        .battlefield(0, [WASTE] * 8)
        .hand(0, [FOUNDRY, *hand])
        .library(0, [WASTE] * 20)
        .library(1, [WASTE] * 20)
        .build()
    )


def play_the_foundry(game, *, imprint: bool = True):
    game.apply(action_for_card(game, ActionKind.CAST, FOUNDRY))
    pass_until(
        game,
        lambda g: (d := g.pending()) is not None and d.kind.value == "may",
        limit=60,
    )
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is (ActionKind.YES if imprint else ActionKind.NO)
        )
    )
    pass_until(game, lambda g: g.pending() is None or not g.state.stack)


def use_it(game):
    """Activate the Foundry, waiting for your own priority first.

    `legal_actions` answers for whoever currently holds priority, so a test that
    activated straight after the previous ability resolved would be reading the
    opponent's options and concluding the ability had vanished.
    """
    pass_until(
        game,
        lambda g: (d := g.pending()) is not None and d.player == 0,
        limit=200,
    )
    foundry = only_oid(game, FOUNDRY)
    action = next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == foundry
        ),
        None,
    )
    if action is None:
        return False
    game.apply(action)
    pass_until(game, lambda g: g.pending() is None or not g.state.stack)
    return True


class TestTheImprint:
    def test_the_card_is_exiled_and_linked(self, builder):
        game = position(builder, [BEAR])
        bear = game.state.players[0].hand[-1]
        play_the_foundry(game)

        assert game.state.objects[bear].zone is Zone.EXILE
        assert game.state.objects[bear].exiled_by == only_oid(game, FOUNDRY)

    def test_declining_exiles_nothing(self, builder):
        game = position(builder, [BEAR])
        bear = game.state.players[0].hand[-1]
        play_the_foundry(game, imprint=False)

        assert game.state.objects[bear].zone is Zone.HAND


class TestReadingItBack:
    def test_it_copies_the_imprinted_card(self, builder):
        game = position(builder, [BEAR])
        play_the_foundry(game)

        assert use_it(game)

        copies = [o for o in game.state.battlefield_objects(0) if o.def_id == BEAR]
        assert len(copies) == 1
        assert copies[0].is_token

    def test_the_link_is_not_spent_by_using_it(self, builder):
        """Imprint's own property: the artifact goes on copying the same card."""
        game = position(builder, [BEAR])
        play_the_foundry(game)
        use_it(game)
        # Untap and go again.
        for obj in game.state.battlefield_objects(0):
            obj.tapped = False
        game.state.bump_chars()

        assert use_it(game)

        copies = [o for o in game.state.battlefield_objects(0) if o.def_id == BEAR]
        assert len(copies) == 2

    def test_with_nothing_imprinted_it_copies_nothing(self, builder):
        game = position(builder, [BEAR])
        play_the_foundry(game, imprint=False)

        use_it(game)

        assert not [o for o in game.state.battlefield_objects(0) if o.def_id == BEAR]

    def test_it_copies_its_own_card_and_not_another_in_exile(self, builder):
        """A bare `{"zone": "exile"}` would copy somebody else's card."""
        from automtg.engine.zones import exile

        game = position(builder, [BEAR, GIANT])
        giant = next(
            o for o in game.state.players[0].hand if game.state.objects[o].def_id == GIANT
        )
        exile(game.state, giant)
        play_the_foundry(game)
        use_it(game)

        battlefield = [o.def_id for o in game.state.battlefield_objects(0)]
        assert BEAR in battlefield
        assert GIANT not in battlefield, "it was exiled by something else"


class TestTheDefaultThatWouldBite:
    def test_the_selector_names_controller_any(self, builder):
        """An exiled card keeps its last controller, and the default is "you".

        Right by accident for a card imprinted out of your own hand, and the
        first thing to break for one that reached exile any other way -- so the
        card says `"controller": "any"` and this pins that it still does.
        """
        game = position(builder, [BEAR])
        foundry = next(
            o for o in game.state.players[0].hand
            if game.state.objects[o].def_id == FOUNDRY
        )
        card = game.state.card_of(game.state.objects[foundry])
        selector = card.abilities[1].effects[0]["objects"]
        assert selector["controller"] == "any"
        assert selector["exiled_with"] == "self"
