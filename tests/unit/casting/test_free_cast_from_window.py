"""A free cast out of a bounded "look at the top N" window.

    Perception Bobblehead — "{3}, {T}: Look at the top X cards of your library,
    where X is the number of Bobbleheads you control. **You may cast a spell
    with mana value 3 or less from among them without paying its mana cost.**
    Put the rest on the bottom of your library in a random order."

The census filed the middle sentence as blocked, and the interesting part is
that every spelling the DSL already had is a *different card*:

- `look_at_top` `{"destination": "exile"}` followed by `play_exiled` is the
  natural pairing and it **silently does nothing**. `play_exiled` defaults its
  selector to `exiled_with: "self"`, which is answered by `obj.exiled_by`;
  `look_at_top`'s exile goes through `_move_found` → `move_object` →
  `reset_permanent_state`, which clears that field. The pool comes back empty
  and the ability resolves having done nothing at all.
- `playable_this_turn` is the **impulse** permission — play it later, at its
  printed cost, expiring with the turn. "Without paying its mana cost" is not
  that, and `docs/card-dsl.md` keeps the two apart on purpose.
- `hideaway` has the right shape but its exile is mandatory and unfiltered: it
  forces a card out of the window even when nothing there is castable, and a
  card exiled and then not cast is gone from the library for good instead of
  going to the bottom with the rest.
- `cascade` and `ripple` free-cast, but their tests are hardcoded ("lesser mana
  value than this spell", "the same name as this spell") with no parameter a
  card can substitute a selector into.

So `cast_free` is a key on `look_at_top`: ripple's shape, with ripple's fixed
test replaced by the selector `look_at_top` already accepts. Two claims carry
the whole thing and neither is visible from "did the spell resolve":

1. **Free.** Rule 601.2b — casting without paying is still casting, so the card
   goes on the *stack* (it can be countered, its cast triggers fire) and the
   caster pays nothing. A no-op implementation and a full-price implementation
   both leave a satisfied-looking board, so the test asserts on the
   ``SPELL_CAST`` event's ``free`` flag and on an untouched mana pool.
2. **The rest reach the bottom.** A declined offer, a card the selector filtered
   out, and a land in the window all have to end up at the bottom of the library
   — not in exile, which is where every alternative spelling would strand them.

The bottoming order comes from ``state.rng`` and never from :mod:`random`;
``tests/unit/engine/test_determinism_hygiene.py`` scans the source for the latter, and
``TestTheOrderComesFromTheGameRng`` here pins the former from the outside.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from tests.conftest import library_ids

FOREST = "forest"         # land, mana value 0
BEAR = "t_bear"           # {1}{G}, mana value 2
BOLT = "t_bolt"           # {R}, mana value 1
GIANT = "t_big"           # {5}{G}, mana value 6
SOURCE = "t_dork"         # the permanent whose ability is resolving

#: Perception Bobblehead's second sentence, written in the DSL.
BOBBLEHEAD = {
    "op": "look_at_top",
    "amount": {"const": 3},
    "objects": {"mana_value": {"op": "<=", "value": 3}, "count": 1, "optional": True},
    "cast_free": True,
    "rest_to_bottom": True,
}


def board(builder, library: list[str], *, seed: int = 0):
    """A controller with a stacked library, an empty mana pool and no lands."""
    game = (
        builder(players=2, seed=seed)
        .battlefield(0, [SOURCE])
        .library(0, library)
        .build(advance=False)
    )
    src = next(o.oid for o in game.state.battlefield_objects(0))
    return game, src


def run(game, src, spec=None, *, want: str | None = BEAR, cast: bool = True):
    """Resolve the op, answering the pick with ``want`` and the offer with ``cast``.

    Returns the decisions it asked, so a test can assert that the offer was made
    (or that it never was, which is the claim for a land or an overpriced card).
    """
    ctx = EffectContext(state=game.state, controller=0, source_oid=src)
    gen = OPS["look_at_top"](ctx, dict(spec or BOBBLEHEAD))
    asked = []
    send = None
    for _ in range(50):
        try:
            decision = gen.send(send)
        except StopIteration:
            return asked
        asked.append(decision)
        if decision.kind is DecisionKind.MAY:
            send = [0] if cast else [1]
            continue
        offered = [game.state.objects[option.value].def_id for option in decision.options]
        send = [] if want is None else [offered.index(want)]
    raise AssertionError("the op never finished")


def stack_ids(game):
    return [item.def_id for item in game.state.stack]


def free_casts(game):
    """The ``SPELL_CAST`` events that were cast without paying (601.2b)."""
    return [
        event
        for event in game.state.events
        if event.type == EventType.SPELL_CAST and event.data.get("free")
    ]


class TestTheSpellIsCastAndItIsFree:
    def test_the_picked_card_reaches_the_stack(self, builder):
        """601.2b: it is a *cast*, so it uses the stack and can be countered —
        it does not simply appear on the battlefield."""
        game, src = board(builder, [BEAR, FOREST, GIANT, BOLT])

        run(game, src)

        assert stack_ids(game) == [BEAR]
        assert all(o.def_id != BEAR for o in game.state.battlefield_objects(0))

    def test_nothing_was_paid_for_it(self, builder):
        """The controller has no lands and an empty pool. A `look_at_top` that
        charged the printed cost — which is what `playable_this_turn` does — could
        not have put a {1}{G} creature on the stack from this board at all."""
        game, src = board(builder, [BEAR, FOREST, GIANT, BOLT])
        assert game.state.players[0].mana_pool.total() == 0

        run(game, src)

        assert stack_ids(game) == [BEAR]
        assert game.state.players[0].mana_pool.total() == 0
        assert [event.data.get("card") for event in free_casts(game)] == [BEAR]

    def test_the_cast_is_announced_as_free(self, builder):
        """`cast_for_free` fires `SPELL_CAST` with `free=1`, which is what a
        "whenever you cast" trigger and the log both read. A card put onto the
        stack by hand would look identical on the board and fire nothing."""
        game, src = board(builder, [BEAR, FOREST, GIANT, BOLT])

        run(game, src)

        assert len(free_casts(game)) == 1
        assert free_casts(game)[0].player == 0

    def test_it_gets_no_haste(self, builder):
        """Haste belongs to suspend. A creature cast this way that could attack
        immediately would be a strictly better card than the printed one."""
        game, src = board(builder, [BEAR, FOREST, GIANT, BOLT])

        run(game, src)

        bear = next(o for o in game.state.objects.values() if o.def_id == BEAR)
        assert not bear.hasted_by_suspend


class TestTheSelectorBoundsWhatMayBeCast:
    def test_an_overpriced_card_is_never_offered(self, builder):
        """"mana value 3 or less". The Giant costs 6 and the offer is not made —
        not made and declined, so no decision is asked at all."""
        game, src = board(builder, [GIANT, GIANT, GIANT, BOLT])

        asked = run(game, src)

        assert asked == []
        assert stack_ids(game) == []

    def test_a_land_is_never_offered(self, builder):
        """"cast **a spell**". A land is played, never cast (601.2), and every
        land ever printed has mana value 0 — so the printed selector alone would
        have offered a free Forest onto the stack."""
        game, src = board(builder, [FOREST, FOREST, FOREST, BOLT])

        asked = run(game, src)

        assert asked == []
        assert stack_ids(game) == []
        assert sorted(library_ids(game)[1:]) == sorted([FOREST] * 3)

    def test_only_one_spell_is_taken(self, builder):
        """"a spell", singular — `count: 1` on the selector. The second castable
        card in the window is not a second free spell."""
        game, src = board(builder, [BEAR, BOLT, GIANT, BOLT])

        run(game, src, want=BEAR)

        assert stack_ids(game) == [BEAR]
        assert BOLT in library_ids(game)

    def test_the_window_is_bounded_by_amount(self, builder):
        """The depth is the card — X Bobbleheads. A castable card one card too
        deep was never looked at and cannot be cast."""
        game, src = board(builder, [GIANT, GIANT, GIANT, BEAR])

        asked = run(game, src)

        assert asked == []
        assert stack_ids(game) == []
        assert library_ids(game)[0] == BEAR, "the fourth card was never looked at"


class TestTheRestGoToTheBottom:
    def test_the_cast_card_is_not_among_the_rest(self, builder):
        """The spell is on the stack, so it is not "the rest" — bottoming it
        would drag it back off the stack."""
        game, src = board(builder, [BEAR, FOREST, GIANT, BOLT])

        run(game, src)

        assert BEAR not in library_ids(game)
        assert library_ids(game)[0] == BOLT, "the fourth card was never looked at"
        assert sorted(library_ids(game)[1:]) == sorted([FOREST, GIANT])

    def test_declining_folds_the_card_back_into_the_rest(self, builder):
        """"You **may** cast" (601.2b). A refused card was still only ever looked
        at, so it goes to the bottom with everything else — this is the whole
        difference from `hideaway`, which would leave it in exile for good."""
        game, src = board(builder, [BEAR, FOREST, GIANT, BOLT])

        run(game, src, cast=False)

        assert stack_ids(game) == []
        assert library_ids(game)[0] == BOLT
        assert sorted(library_ids(game)[1:]) == sorted([BEAR, FOREST, GIANT])

    def test_declining_the_pick_bottoms_everything(self, builder):
        """`optional: true` — the pick itself can be declined, before any offer."""
        game, src = board(builder, [BEAR, BOLT, GIANT, FOREST])

        run(game, src, want=None)

        assert stack_ids(game) == []
        assert library_ids(game)[0] == FOREST
        assert sorted(library_ids(game)[1:]) == sorted([BEAR, BOLT, GIANT])

    @pytest.mark.parametrize("cast", [True, False])
    def test_nothing_is_ever_exiled(self, builder, cast):
        """The card says *look at*. Every alternative spelling reaches the free
        cast through exile, and a card that ends the ability in exile is a
        different — and worse — card."""
        game, src = board(builder, [BEAR, FOREST, GIANT, BOLT])

        run(game, src, cast=cast)

        assert game.state.players[0].exile == []
        assert all(
            game.state.objects[o].zone is Zone.LIBRARY
            for o in game.state.players[0].library
        )

    def test_the_untouched_library_keeps_its_order(self, builder):
        """Bottoming is not shuffling: the cards under the window are in the
        order somebody may be counting on."""
        game, src = board(builder, [BEAR, FOREST, GIANT, BOLT, GIANT, FOREST])

        run(game, src)

        assert library_ids(game)[:3] == [BOLT, GIANT, FOREST]

    def test_without_rest_to_bottom_the_rest_stay_on_top(self, builder):
        """`rest_to_bottom` is opt-in on `look_at_top`, and "look at" means the
        cards you did not take stay where they were, in order."""
        spec = dict(BOBBLEHEAD)
        spec.pop("rest_to_bottom")
        game, src = board(builder, [BEAR, FOREST, GIANT, BOLT])

        run(game, src, spec)

        assert stack_ids(game) == [BEAR]
        assert library_ids(game) == [FOREST, GIANT, BOLT]


class TestTheOrderComesFromTheGameRng:
    def test_the_game_rng_is_what_was_consumed(self, builder):
        """Not :mod:`random`. If the shuffle came from anywhere else the game's
        own stream would be untouched and every replay would diverge."""
        game, src = board(builder, [BEAR, FOREST, GIANT, BOLT])
        before = game.state.rng.getstate()

        run(game, src)

        assert game.state.rng.getstate() != before

    def test_the_same_seed_gives_the_same_bottom(self, builder):
        orders = []
        for _ in range(2):
            game, src = board(builder, [BEAR, FOREST, GIANT, BOLT], seed=7)
            run(game, src, cast=False)
            orders.append(library_ids(game))

        assert orders[0] == orders[1]

    def test_a_different_seed_can_reach_a_different_bottom(self, builder):
        """Otherwise "in a random order" is decoration on a fixed order."""
        orders = set()
        for seed in range(12):
            game, src = board(builder, [BEAR, FOREST, GIANT, BOLT], seed=seed)
            run(game, src, cast=False)
            orders.add(tuple(library_ids(game)[1:]))

        assert len(orders) > 1


class TestTheLoaderRefusesTheContradictions:
    """Each of these loads clean without a guard and plays as a different card."""

    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_window",
                "name": "Test Window",
                "mana_cost": "{2}",
                "types": ["Artifact"],
                "oracle_text": (
                    "{3}, {T}: Look at the top three cards of your library. You may "
                    "cast a spell with mana value 3 or less from among them without "
                    "paying its mana cost. Put the rest on the bottom of your library "
                    "in a random order."
                ),
                "spell_effects": [effect],
            }
        )

    def test_the_printed_shape_compiles(self):
        compile_card(self._card(dict(BOBBLEHEAD)))

    def test_a_destination_beside_the_free_cast_is_refused(self):
        """The picked card goes to the stack; a destination would be read by
        nobody and the card would look like it moved cards to a zone."""
        with pytest.raises(DslError, match="goes to the stack"):
            compile_card(self._card({**BOBBLEHEAD, "destination": "exile"}))

    def test_the_impulse_permission_beside_the_free_cast_is_refused(self):
        """`playable_this_turn` is "later, at its printed cost" — the opposite
        card from "now, for free", and silently dropped if written here."""
        with pytest.raises(DslError, match="goes to the stack"):
            compile_card(self._card({**BOBBLEHEAD, "playable_this_turn": True}))

    def test_tapped_beside_the_free_cast_is_refused(self):
        with pytest.raises(DslError, match="goes to the stack"):
            compile_card(self._card({**BOBBLEHEAD, "tapped": True}))

    def test_the_key_on_another_op_is_refused(self):
        """`exile` ignores unknown keys, so the card would load and charge full
        price for a spell the printing gives away."""
        with pytest.raises(DslError, match="only it reads the free cast"):
            compile_card(
                self._card({"op": "exile", "objects": {"zone": "hand"}, "cast_free": True})
            )
