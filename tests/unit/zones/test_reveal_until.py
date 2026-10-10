"""`reveal_until` — walking a library down to the first card that matches.

    Heirloom Blade — "Whenever equipped creature dies, you may reveal cards
    from the top of your library until you reveal a creature card that shares a
    creature type with it. Put that card into your hand and the rest on the
    bottom of your library in a random order."

The engine could already walk a library from the top twice over, and neither
walk could be asked this question. Cascade's stop test is hardcoded to "nonland
card with lesser mana value than this spell", ripple's to "the same name as this
spell", and neither takes a parameter a card could put a selector into. So the
scan is shared with them — `_bottom_in_random_order` is literally the same
function — and only the test is new.

`look_at_top` is the near miss worth naming, because it is the one an author
would reach for and it makes a **different card**:

- its window is `amount` cards, a constant known when the card is written.
  Naming a number large enough to fake "until" reveals and randomizes the whole
  library every time the trigger resolves.
- it offers every match inside that window and lets the player take the best
  one. "Until you reveal" takes the *first* one, and there is no choice at all,
  which is why this op is not even a generator.

Two outcomes carry the whole rules argument and both are covered below: the scan
stopping at the first hit rather than the best one, and the scan running the
library out with **no** hit — where everything revealed goes to the bottom and
nothing goes to hand. A card that crashed or that quietly kept a card in that
case would be wrong in the position an Equipment sees most.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute_one
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import hand_ids, library_ids

FOREST = "forest"
BEAR = "t_bear"    # Creature — Bear
GIANT = "t_big"    # Creature — Giant
ELF = "t_elf"      # Creature — Elf

CREATURE = {"types": ["Creature"]}


def board(builder, library: list[str], battlefield: list[str] | None = None, seed: int = 0):
    """A position with a stacked library and, optionally, something to bind to."""
    game = (
        builder(players=2, seed=seed)
        .battlefield(0, battlefield or ["forest"])
        .library(0, library)
        .build(advance=False)
    )
    src = next(o.oid for o in game.state.battlefield_objects(0))
    return game, src


def run(game, spec, source: int, bindings: dict | None = None) -> EffectContext:
    """Run the op, and fail if it ever asks a question.

    The assertion is the point rather than plumbing: "until you reveal" names
    the card it takes, so there is nothing for a player to decide, and an
    implementation that grew a decision would have grown `look_at_top`'s
    best-of-every-match choice by accident.
    """
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    ctx.bindings.update(bindings or {})
    for _ in execute_one(ctx, spec):  # pragma: no cover - the loop body is the failure
        raise AssertionError("reveal_until asked a decision; it takes none")
    return ctx


class TestItStopsAtTheFirstMatch:
    def test_the_first_hit_is_taken_and_the_scan_stops(self, builder):
        game, src = board(builder, [FOREST, FOREST, BEAR, GIANT])

        run(game, {"op": "reveal_until", "objects": CREATURE}, src)

        assert hand_ids(game) == [BEAR]
        # The Giant was never revealed, so it is still on top with the two
        # Forests underneath it.
        assert library_ids(game)[0] == GIANT

    def test_it_is_the_first_match_and_not_the_best_one(self, builder):
        """The whole difference from `look_at_top`, in one position.

        Written with `look_at_top` and an amount of 4 the player would be handed
        both creatures and would take the Giant every time. "Until you reveal"
        does not offer the choice: the Bear is on top, so the Bear is the card.
        """
        game, src = board(builder, [BEAR, GIANT, GIANT, GIANT])

        run(game, {"op": "reveal_until", "objects": CREATURE}, src)

        assert hand_ids(game) == [BEAR]
        assert library_ids(game) == [GIANT, GIANT, GIANT], "nothing else was touched"

    def test_a_card_the_selector_rejects_never_stops_it(self, builder):
        """"…until you reveal a **creature** card." Lands are walked past."""
        game, src = board(builder, [FOREST, FOREST, FOREST, ELF])

        run(game, {"op": "reveal_until", "objects": CREATURE}, src)

        assert hand_ids(game) == [ELF]
        assert sorted(library_ids(game)) == [FOREST, FOREST, FOREST]

    def test_the_top_card_can_be_the_match(self, builder):
        game, src = board(builder, [BEAR, FOREST])

        run(game, {"op": "reveal_until", "objects": CREATURE}, src)

        assert hand_ids(game) == [BEAR]
        assert library_ids(game) == [FOREST], "nothing was revealed past the hit"


class TestTheMatchCanBeTheLastCard:
    def test_the_bottom_card_still_gets_taken(self, builder):
        """The boundary the loop is most likely to be off by one on: the match is
        the last card in the library, so the scan reveals everything and still
        has to take it."""
        game, src = board(builder, [FOREST, FOREST, BEAR])

        run(game, {"op": "reveal_until", "objects": CREATURE}, src)

        assert hand_ids(game) == [BEAR]
        assert sorted(library_ids(game)) == [FOREST, FOREST]

    def test_a_one_card_library_that_matches(self, builder):
        game, src = board(builder, [BEAR])

        run(game, {"op": "reveal_until", "objects": CREATURE}, src)

        assert hand_ids(game) == [BEAR]
        assert library_ids(game) == []


class TestRunningTheLibraryOut:
    def test_no_match_takes_nothing_and_bottoms_everything(self, builder):
        """"Until" with nothing to find is an outcome, not an error.

        Every card in the library was revealed and every one of them goes back
        in a random order. Nothing reaches the hand -- an implementation that
        fell out of the loop holding the last card revealed would hand its
        controller a Forest that the printed card does not give them.
        """
        game, src = board(builder, [FOREST, FOREST, FOREST])

        run(game, {"op": "reveal_until", "objects": CREATURE}, src)

        assert hand_ids(game) == []
        assert sorted(library_ids(game)) == [FOREST, FOREST, FOREST]
        assert all(
            game.state.objects[o].zone is Zone.LIBRARY
            for o in game.state.players[0].library
        ), "the cards were revealed, not moved"

    def test_a_one_card_library_that_does_not_match(self, builder):
        game, src = board(builder, [FOREST])

        run(game, {"op": "reveal_until", "objects": CREATURE}, src)

        assert hand_ids(game) == []
        assert library_ids(game) == [FOREST]

    def test_an_empty_library_is_survivable(self, builder):
        game, src = board(builder, [])

        run(game, {"op": "reveal_until", "objects": CREATURE}, src)

        assert library_ids(game) == []
        assert hand_ids(game) == []


class TestSharesATypeWithTheDeadCreature:
    """Heirloom Blade's actual stop test, which is why the selector had to be the
    parameter: no constant written into the card can say "shares a creature type
    with the creature that just died"."""

    def test_it_walks_past_creatures_of_the_wrong_type(self, builder):
        game, src = board(builder, [BEAR, GIANT, ELF, BEAR], battlefield=["forest", ELF])
        subject = next(
            o.oid for o in game.state.battlefield_objects(0) if o.def_id == ELF
        )

        run(
            game,
            {
                "op": "reveal_until",
                "objects": {"types": ["Creature"], "shares_a_type_with": "subject"},
            },
            src,
            bindings={"subject": subject},
        )

        assert hand_ids(game) == [ELF]
        assert library_ids(game)[0] == BEAR, "the fourth card was never revealed"

    def test_no_creature_shares_a_type_so_nothing_is_found(self, builder):
        game, src = board(builder, [BEAR, GIANT], battlefield=["forest", ELF])
        subject = next(
            o.oid for o in game.state.battlefield_objects(0) if o.def_id == ELF
        )

        run(
            game,
            {
                "op": "reveal_until",
                "objects": {"types": ["Creature"], "shares_a_type_with": "subject"},
            },
            src,
            bindings={"subject": subject},
        )

        assert hand_ids(game) == []
        assert sorted(library_ids(game)) == sorted([BEAR, GIANT])


class TestTheRestGoesToTheBottomInARandomOrder:
    def test_the_revealed_cards_end_up_under_the_untouched_ones(self, builder):
        game, src = board(builder, [FOREST, FOREST, BEAR, GIANT, GIANT])

        run(game, {"op": "reveal_until", "objects": CREATURE}, src)

        assert library_ids(game)[:2] == [GIANT, GIANT], "never revealed, never moved"
        assert library_ids(game)[2:] == [FOREST, FOREST]

    def test_the_untouched_part_of_the_library_keeps_its_order(self, builder):
        """A shuffle would reorder the whole deck, which is a different game
        action -- and here it would be a free one, because the trigger is a
        `may` that costs nothing to accept."""
        game, src = board(builder, [BEAR, GIANT, FOREST, ELF, FOREST])

        run(game, {"op": "reveal_until", "objects": CREATURE}, src)

        assert hand_ids(game) == [BEAR]
        assert library_ids(game) == [GIANT, FOREST, ELF, FOREST]

    def test_the_order_of_the_rest_really_is_random(self, builder):
        """"…in a random order", not "in the order revealed".

        The difference is knowledge: after a failed scan the controller has seen
        every card in their library, and leaving them in the revealed order
        would hand them a fully known deck for the rest of the game. Asserted
        over seeds rather than over one run, because any single ordering is a
        legal one.
        """
        orders = set()
        for seed in range(12):
            game, src = board(builder, [FOREST, BEAR, GIANT, ELF], seed=seed)
            run(game, {"op": "reveal_until", "objects": {"subtypes": ["Elf"]}}, src)
            assert hand_ids(game) == [ELF]
            orders.add(tuple(library_ids(game)))
        assert len(orders) > 1, f"the bottomed cards came back in one fixed order: {orders}"


class TestTheKeysTheCardWrites:
    def test_the_destination_is_not_always_the_hand(self, builder):
        game, src = board(builder, [FOREST, BEAR, GIANT])

        run(
            game,
            {"op": "reveal_until", "objects": CREATURE, "destination": "graveyard"},
            src,
        )

        assert hand_ids(game) == []
        assert [
            game.state.objects[o].def_id for o in game.state.players[0].graveyard
        ] == [BEAR]

    def test_rest_to_bottom_can_be_turned_off(self, builder):
        """Off, the revealed misses stay where they were -- on top, in order.

        No printed "reveal until" does this, which is why the default is on;
        the key exists so that a card which wanted it would not have to be a
        second op.
        """
        game, src = board(builder, [FOREST, FOREST, BEAR, GIANT])

        run(
            game,
            {"op": "reveal_until", "objects": CREATURE, "rest_to_bottom": False},
            src,
        )

        assert hand_ids(game) == [BEAR]
        assert library_ids(game) == [FOREST, FOREST, GIANT]

    def test_the_default_is_to_bottom_them(self, builder):
        """`look_at_top` defaults the same key to *off*, because "look at" means
        the cards you did not take stay on top. An omitted key here has to mean
        the opposite, or Heirloom Blade would leave its whole failed scan face
        up on top of the deck."""
        game, src = board(builder, [FOREST, FOREST, BEAR, GIANT])

        run(game, {"op": "reveal_until", "objects": CREATURE}, src)

        assert library_ids(game) == [GIANT, FOREST, FOREST]


class TestTheLoaderRefusesTheCardsThatWouldBeWrong:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_reveal_until_probe",
                "name": "Reveal Until Probe",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )

    def test_a_well_formed_effect_loads(self):
        compile_card(self._card({"op": "reveal_until", "objects": CREATURE}))

    def test_a_missing_selector_is_a_load_error(self):
        """An empty selector matches the first card revealed, which is a
        different card: "put the top card of your library into your hand"."""
        with pytest.raises(DslError, match="reveal_until needs a non-empty 'objects'"):
            compile_card(self._card({"op": "reveal_until"}))

    def test_an_amount_is_a_load_error(self):
        """A bounded window is `look_at_top`'s job. A card that wrote an amount
        here would believe the scan stopped there, and nothing would read it."""
        with pytest.raises(DslError, match="reveal_until takes no 'amount'"):
            compile_card(
                self._card(
                    {"op": "reveal_until", "objects": CREATURE, "amount": {"const": 5}}
                )
            )

    def test_an_unknown_destination_is_a_load_error(self):
        with pytest.raises(DslError, match="unknown reveal_until destination"):
            compile_card(
                self._card(
                    {"op": "reveal_until", "objects": CREATURE, "destination": "the_moon"}
                )
            )
