"""A flashback cost with no mana half: the tapping is the whole price.

    Battle Screech -- "Create two 1/1 white Bird creature tokens with flying.
    Flashback—Tap three untapped white creatures you control."

Flashback's cost replaces the printed one (702.34a, 118.9), and nothing in
the rule says it must include mana. The loader refused a graveyard cost with
no mana so that no card could be cast from the graveyard for nothing; that
argument holds for a cost that charges nothing at all, not for one that
charges three creatures. `alternative_cost` draws the line the same way for
Force of Will's pitch, through `Cost.charges_nothing`.

What has to hold once the guard lets it through:

- **No mana is spent.** The printed {2}{W}{W} is replaced, so a player with
  no lands but three white creatures can flash it back.
- **The tapping is paid.** Three untapped white creatures you control, not
  two, not a green one, not one already tapped.
- **It is still flashback.** The spell is exiled as it resolves.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone

SCREECH = "t_battle_screech"
LIONS = "savannah_lions"  # a white creature
BEARS = "grizzly_bears"  # a green one
BIRD = "bird_1_1_w_flying"


def table(builder, creatures, *, lands=0, where="graveyard"):
    b = (
        builder(players=2)
        .battlefield(0, ["plains"] * lands + list(creatures))
        .library(0, ["plains"] * 10)
        .active(0)
        .max_turns(1)
    )
    b = b.graveyard(0, [SCREECH]) if where == "graveyard" else b.hand(0, [SCREECH])
    return b.build()


def casts(game):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == SCREECH
    ]


def settle(game) -> None:
    """Answer every cost or effect decision with its first legal choice and
    pass priority until the stack is empty."""
    for _ in range(40):
        decision = game.pending()
        if decision is None:
            return
        if decision.kind is DecisionKind.PRIORITY:
            if not game.state.stack:
                return
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
            continue
        game.apply(game.legal_actions()[0])


def screech_oid(game) -> int:
    return next(o for o, obj in game.state.objects.items() if obj.def_id == SCREECH)


def birds(game) -> int:
    return sum(1 for o in game.state.battlefield if game.state.objects[o].def_id == BIRD)


def tapped(game, def_id: str) -> int:
    state = game.state
    return sum(
        1 for o in state.battlefield if state.objects[o].def_id == def_id and state.objects[o].tapped
    )


class TestItIsOfferedWithoutMana:
    def test_three_white_creatures_and_no_lands(self, builder):
        assert casts(table(builder, [LIONS] * 3))

    def test_two_are_not_enough(self, builder):
        assert not casts(table(builder, [LIONS] * 2, lands=6))

    def test_a_green_creature_is_not_white(self, builder):
        assert not casts(table(builder, [LIONS, LIONS, BEARS], lands=6))

    def test_from_hand_it_still_costs_mana(self, builder):
        """The tapping is the flashback price only; the printed cost is the
        hand's, and with no lands it cannot be paid."""
        assert not casts(table(builder, [LIONS] * 3, where="hand"))


class TestCastingIt:
    def test_it_taps_three_and_makes_two_birds(self, builder):
        game = table(builder, [LIONS] * 3)
        game.apply(casts(game)[0])
        settle(game)
        assert tapped(game, LIONS) == 3
        assert birds(game) == 2

    def test_it_is_exiled(self, builder):
        game = table(builder, [LIONS] * 3)
        game.apply(casts(game)[0])
        settle(game)
        assert game.state.objects[screech_oid(game)].zone is Zone.EXILE

    def test_no_mana_is_spent(self, builder):
        game = table(builder, [LIONS] * 3, lands=4)
        game.apply(casts(game)[0])
        settle(game)
        assert tapped(game, "plains") == 0
