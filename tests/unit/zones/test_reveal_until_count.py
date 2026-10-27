"""`reveal_until` with an ``amount``: "until you reveal that many creature cards".

    Mass Polymorph — "Exile all creatures you control, then reveal cards from
    the top of your library until you reveal that many creature cards. Put all
    creature cards revealed this way onto the battlefield, then shuffle the rest
    of the revealed cards into your library."

Three things the plain walk could not say, and each is the card:

- **The count.** The scan stops at the Nth match, N a value read once before
  it starts -- here the size of the `exile` op's `as` binding, which keeps the
  tokens it exiled (a token in exile has ceased to exist, but it was exiled
  this way and it counts). Wrapping the one-match walk in a `repeat` would
  bottom or shuffle between iterations and reveal N separate runs.
- **One arrival.** "Put all creature cards revealed this way onto the
  battlefield" is a single event, and 603.6a/603.10 make an enters ability look
  at the game after it: two Soul Wardens put down together each see the other.
  Moved one at a time with each event collected as it fires, the second Warden
  would hear nobody. `triggers.entering_together` holds collection until the
  group has moved.
- **Shuffle, not bottom.** "Shuffle the rest of the revealed cards into your
  library" randomizes the whole library; "the rest on the bottom in a random
  order" leaves the untouched cards on top in order. Different actions, so
  `shuffle_rest` replaces `rest_to_bottom` and the loader refuses both at once.

Synthetic Destiny is the same sentence inside a `delay` to the next end step,
reading the exile binding the delay carried forward; it is pinned here too.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute_one
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import battlefield_ids, hand_ids, library_ids, pass_until

FOREST = "forest"
BEAR = "t_bear"
GIANT = "t_big"
ELF = "t_elf"
WARDEN = "soul_warden"  # "Whenever another creature enters, you gain 1 life."

CREATURE = {"types": ["Creature"]}


def board(
    builder,
    library: list[str],
    battlefield: list[str] | None = None,
    seed: int = 0,
    advance: bool = False,
):
    """A position with a stacked library; the source is the first permanent."""
    game = (
        builder(players=2, seed=seed)
        .battlefield(0, battlefield or [FOREST])
        .library(0, library)
        .build(advance=advance)
    )
    src = next(o.oid for o in game.state.battlefield_objects(0))
    return game, src


def run(game, spec, source: int, bindings: dict | None = None) -> EffectContext:
    """Run the op and fail if it asks anything: "until" names its cards."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    ctx.bindings.update(bindings or {})
    for _ in execute_one(ctx, spec):  # pragma: no cover - the loop body is the failure
        raise AssertionError("reveal_until asked a decision; it takes none")
    return ctx


def polymorph(amount, **extra) -> dict:
    return {
        "op": "reveal_until",
        "objects": CREATURE,
        "amount": amount,
        "destination": "battlefield",
        "shuffle_rest": True,
        **extra,
    }


class TestItStopsAtTheNthMatch:
    def test_two_matches_are_taken_and_the_third_is_never_revealed(self, builder):
        game, src = board(builder, [FOREST, BEAR, FOREST, ELF, GIANT])

        ctx = run(
            game,
            {"op": "reveal_until", "objects": CREATURE, "amount": {"const": 2}, "as": "hits"},
            src,
        )

        assert sorted(hand_ids(game)) == sorted([BEAR, ELF])
        assert library_ids(game)[0] == GIANT, "the scan stopped at the second creature"
        assert len(ctx.bindings["hits"]) == 2

    def test_omitted_it_is_one(self, builder):
        game, src = board(builder, [BEAR, ELF])

        run(game, {"op": "reveal_until", "objects": CREATURE}, src)

        assert hand_ids(game) == [BEAR]

    def test_zero_reveals_nothing(self, builder):
        """Mass Polymorph with no creatures to exile: "that many" is none, and
        the library is not touched, let alone shuffled."""
        game, src = board(builder, [FOREST, BEAR, ELF])

        run(game, polymorph({"const": 0}), src)

        assert battlefield_ids(game, 0) == [FOREST]
        assert library_ids(game) == [FOREST, BEAR, ELF]

    def test_running_out_takes_every_match_there_was(self, builder):
        game, src = board(builder, [FOREST, BEAR, FOREST])

        run(game, polymorph({"const": 3}), src)

        assert sorted(battlefield_ids(game, 0)) == sorted([FOREST, BEAR])
        assert sorted(library_ids(game)) == [FOREST, FOREST]

    def test_the_amount_is_a_count_over_an_earlier_binding(self, builder):
        game, src = board(builder, [FOREST, BEAR, ELF, GIANT], battlefield=[FOREST, BEAR, ELF])
        exiled = [o.oid for o in game.state.battlefield_objects(0) if o.def_id != FOREST]

        run(game, polymorph({"count": {"binding": "exiled"}}), src, {"exiled": exiled})

        assert sorted(battlefield_ids(game, 0)) == sorted([FOREST, BEAR, ELF, BEAR, ELF])
        assert library_ids(game).count(GIANT) == 1


class TestTheyEnterTogether:
    def test_two_wardens_each_see_the_other(self, builder):
        """603.6a: one arrival, so each Warden's ability sees the other enter."""
        game, src = board(builder, [WARDEN, FOREST, WARDEN, FOREST])

        run(game, polymorph({"const": 2}), src)

        assert battlefield_ids(game, 0).count(WARDEN) == 2
        heard = [t for t in game.state.pending_triggers if "Soul Warden" in t.description]
        assert len(heard) == 2, "the first Warden to arrive must hear the second"
        assert game.state.held_events is None, "collection is released after the group"

    def test_one_at_a_time_the_first_arrival_hears_nothing(self, builder):
        """The contrast: two separate one-match walks are two events, and the
        second Warden enters after the first, so only one trigger results."""
        game, src = board(builder, [WARDEN, FOREST, WARDEN, FOREST])

        for _ in range(2):
            run(game, polymorph({"const": 1}), src)

        heard = [t for t in game.state.pending_triggers if "Soul Warden" in t.description]
        assert len(heard) == 1


class TestTheRestIsShuffledIn:
    def test_misses_stay_in_the_library(self, builder):
        game, src = board(builder, [FOREST, FOREST, BEAR, GIANT])

        run(game, polymorph({"const": 1}), src)

        assert battlefield_ids(game, 0).count(BEAR) == 1
        assert sorted(library_ids(game)) == sorted([FOREST, FOREST, GIANT])
        assert all(game.state.objects[o].zone is Zone.LIBRARY for o in game.state.players[0].library)

    def test_the_whole_library_is_shuffled_not_just_the_revealed(self, builder):
        """`rest_to_bottom` would leave the untouched cards on top in order;
        a shuffle moves them too. Asserted over seeds: any single order is legal."""
        tops = set()
        for seed in range(12):
            game, src = board(builder, [BEAR, GIANT, ELF, FOREST, FOREST, FOREST], seed=seed)
            run(game, polymorph({"const": 1}), src)
            tops.add(library_ids(game)[0])
        assert tops != {GIANT}, "the never-revealed Giant was left on top every time"

    def test_bottoming_is_still_the_default(self, builder):
        game, src = board(builder, [FOREST, BEAR, GIANT, ELF])

        run(game, {"op": "reveal_until", "objects": CREATURE, "amount": {"const": 1}}, src)

        assert library_ids(game) == [GIANT, ELF, FOREST]


class TestTheDelayedHalf:
    """Synthetic Destiny: the count is read at the end step, off the binding the
    `delay` carried forward from the spell's exile."""

    def test_the_end_step_reveal_reads_the_spells_exile(self, builder):
        game, src = board(
            builder, [FOREST, BEAR, ELF, GIANT], battlefield=[FOREST, BEAR, ELF], advance=True
        )
        ctx = run(
            game,
            {
                "op": "exile",
                "objects": {"types": ["Creature"], "controller": "you", "count": "all"},
                "as": "exiled",
            },
            src,
        )
        assert battlefield_ids(game, 0) == [FOREST]

        for _ in execute_one(
            ctx,
            {
                "op": "delay",
                "step": "end_step",
                "effects": [polymorph({"count": {"binding": "exiled"}})],
            },
        ):  # pragma: no cover
            raise AssertionError("delay asked a decision")
        assert library_ids(game)[:2] == [FOREST, BEAR], "nothing is revealed yet"

        pass_until(
            game,
            lambda g: not g.state.delayed_triggers and not g.state.stack and not g.state.pending_triggers,
        )

        assert sorted(battlefield_ids(game, 0)) == sorted([FOREST, BEAR, ELF])


class TestTheLoader:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_reveal_until_count_probe",
                "name": "Reveal Until Count Probe",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )

    def test_mass_polymorphs_shape_loads(self):
        compile_card(self._card(polymorph({"count": {"binding": "exiled"}})))

    def test_shuffle_and_bottom_together_is_a_load_error(self):
        with pytest.raises(DslError, match="two dispositions of the rest"):
            compile_card(self._card(polymorph({"const": 1}, rest_to_bottom=True)))

    def test_shuffle_rest_is_a_boolean(self):
        with pytest.raises(DslError, match="'shuffle_rest' is a boolean"):
            compile_card(self._card(polymorph({"const": 1}, shuffle_rest="yes")))

    def test_as_is_accepted(self):
        compile_card(
            self._card(
                {"op": "reveal_until", "objects": CREATURE, "amount": {"const": 2}, "as": "found"}
            )
        )
