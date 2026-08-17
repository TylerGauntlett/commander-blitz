"""Addendum: a clause that reads the phase the spell was **cast** in.

"Addendum — If you cast this spell during your main phase, ..." (Ravnica
Allegiance). The condition is about rule 601's cast, not about resolution: what
it asks is where in the turn the spell was *put on the stack*, and by the time
`spell_effects` run that moment is over and the only witness is whatever the
engine wrote down.

Nothing in the condition language could ask it. The near miss is `is_your_turn`,
and it is wrong twice over -- which is why this is a new key rather than a
widening of that one:

- It compares `state.active_player` to the controller and says **nothing about
  the phase**, so an Unbreakable Formation flashed in during your own combat or
  your own end step -- exactly the times you cast it -- would collect the
  addendum it is not owed. `TestAddendumIsNotJustYourTurn` pins that: at the end
  step `is_your_turn` is `True` and `cast_during` is `False`, in the same
  position.
- It is evaluated when the condition is *read*, not when the spell was cast, so
  it cannot survive the gap between the two. `TestReadAtCastTimeNotResolution`
  reads the stamp from the end step and still gets the main phase, which is what
  an enters trigger or a delayed effect on an addendum card would need.

`has_flag` cannot stand in either: it is written by `set_flag` on a permanent's
own object and no effect runs at cast time to write one. `zone_is` reports the
source's *current* zone, which for any resolving instant is the stack.

So `stack.push_spell` stamps two facts on the object -- `cast_step`, and whether
the caster was the active player -- beside the `cast_kicked` / `cast_evoked` /
`cast_overloaded` / `cast_from_graveyard` stamps that already record cast-time
choices, and `{"cast_during": "your_main"}` reads them back. Both halves are
needed: "your main phase" is a phase *and* a turn, and the witness for the second
is an opponent flashing the same card in during your main phase -- their spell,
their creatures, no addendum (`TestWhoseMainPhase`).

The shipped witness is Unbreakable Formation; `t_addendum` is its shape.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.effects.conditions import CAST_DURING_NAMES, CONDITION_KEYS, evaluate_condition
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.errors import DslError
from tests.conftest import action_for_card, oids_of, pass_until

CARD = "t_addendum"  # the Unbreakable Formation shape, {1}{W}
BEAR = "t_bear"  # a plain 2/2, no printed keywords
ANCHOR = "t_plain_instant"  # {W}, gain 1 life -- a reason for priority to stop


def position(builder, *, step: Step = Step.PRECOMBAT_MAIN, caster: int = 0):
    """`t_addendum` in ``caster``'s hand, with a 2/2 apiece, frozen at ``step``.

    Turn 1 is player 0's, so `caster=1` is the opponent holding an instant during
    somebody else's main phase -- which is the whole of `TestWhoseMainPhase`.

    The *other* player holds `ANCHOR`, a castable instant, and that is load
    bearing rather than scenery: without a play available to somebody, the
    engine's auto-pass runs from the spell resolving straight through cleanup
    and into the next turn, which wipes every until-end-of-turn grant before it
    can be read. A test measuring an addendum after cleanup would pass whatever
    the card did -- the trap `verify.drive` documents at the other end of the
    pipeline.
    """
    game = (
        builder(players=2)
        .battlefield(0, [BEAR, "plains", "plains"])
        .battlefield(1, [BEAR, "plains", "plains"])
        .hand(caster, [CARD])
        .hand(1 - caster, [ANCHOR])
        .step(step)
        .build(advance=False)
    )
    game._advance()
    return game


def cast_it(game, pid: int = 0) -> int:
    """Cast `t_addendum` for ``pid`` and let it resolve. Returns the spell's oid."""
    pass_until(
        game,
        lambda g: g.pending() is not None
        and g.pending().player == pid
        and any(
            a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == CARD
            for a in g.legal_actions()
        ),
    )
    action = action_for_card(game, ActionKind.CAST, CARD)
    oid = action.source
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack)
    return oid


def creature(game, pid: int) -> int:
    oids = oids_of(game, BEAR, pid)
    assert len(oids) == 1
    return oids[0]


def keywords_of(game, oid: int) -> set[str]:
    return {str(k) for k in chars(game.state, oid).keywords}


def asks(game, oid: int, spec: str, *, controller: int = 0) -> bool:
    """`{"cast_during": spec}` about ``oid``, outside any resolving effect."""
    return evaluate_condition(
        game.state, {"cast_during": spec}, controller=controller, source=oid
    )


class TestAddendumFiresInAMainPhase:
    """Cast in a main phase of your own turn, the whole card happens."""

    @pytest.mark.parametrize("step", [Step.PRECOMBAT_MAIN, Step.POSTCOMBAT_MAIN])
    def test_both_main_phases_count(self, builder, step):
        # "Main phase" is both of them -- the addendum cards say "your main
        # phase" and not "your first main phase", so a key that only knew
        # `precombat_main` would silently drop the postcombat cast.
        game = position(builder, step=step)
        cast_it(game)
        bear = creature(game, 0)
        assert "vigilance" in keywords_of(game, bear)
        assert "indestructible" in keywords_of(game, bear)
        assert game.state.objects[bear].counter("+1/+1") == 1

    def test_the_stamp_says_which_phase(self, builder):
        game = position(builder, step=Step.PRECOMBAT_MAIN)
        oid = cast_it(game)
        assert asks(game, oid, "your_main")
        assert asks(game, oid, "your_precombat_main")
        # ...and not the phase it is not. The generated vocabulary makes this a
        # question the card is allowed to ask, so it has to answer honestly.
        assert not asks(game, oid, "your_postcombat_main")
        assert not asks(game, oid, "your_combat")

    def test_the_first_line_is_not_conditional(self, builder):
        # The indestructible half is an ordinary `grant_keyword` and was never
        # blocked; this is here so a regression in the `if` cannot take the
        # unconditional line down with it.
        game = position(builder, step=Step.END_STEP)
        cast_it(game)
        assert "indestructible" in keywords_of(game, creature(game, 0))


class TestAddendumIsNotJustYourTurn:
    """The near miss, in the position where it is wrong."""

    @pytest.mark.parametrize("step", [Step.BEGIN_COMBAT, Step.END_STEP, Step.UPKEEP])
    def test_your_turn_is_not_your_main_phase(self, builder, step):
        game = position(builder, step=step)
        oid = cast_it(game)
        bear = creature(game, 0)

        # `is_your_turn` -- what a card would have had to be written with --
        # is true here, and would have handed out the addendum.
        assert evaluate_condition(
            game.state, {"is_your_turn": True}, controller=0, source=oid
        )
        assert not asks(game, oid, "your_main")

        assert "vigilance" not in keywords_of(game, bear)
        assert game.state.objects[bear].counter("+1/+1") == 0

    def test_a_combat_cast_still_answers_its_own_phase(self, builder):
        game = position(builder, step=Step.BEGIN_COMBAT)
        oid = cast_it(game)
        assert asks(game, oid, "your_combat")
        assert asks(game, oid, "combat")


class TestReadAtCastTimeNotResolution:
    """The stamp outlives the step it was written in."""

    def test_the_end_step_still_reports_the_main_phase(self, builder):
        game = position(builder, step=Step.PRECOMBAT_MAIN)
        oid = cast_it(game)
        pass_until(game, lambda g: g.state.step is Step.END_STEP)
        assert game.state.step is Step.END_STEP

        # Anything reading the *current* phase now gets `ending`. The condition
        # is about the cast, so it still says main phase -- which is what an
        # enters trigger or a delayed effect on an addendum card would need, and
        # what `is_your_turn`, evaluated where it is read, could never give.
        assert asks(game, oid, "your_main")
        assert not asks(game, oid, "your_ending")

    def test_the_stamp_survives_the_stack(self, builder):
        game = position(builder, step=Step.PRECOMBAT_MAIN)
        oid = cast_it(game)
        # In the graveyard, the spell having resolved: the object is the same
        # object, so the fact is still there to be asked about.
        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        assert game.state.objects[oid].cast_step is Step.PRECOMBAT_MAIN
        assert asks(game, oid, "your_main")


class TestWhoseMainPhase:
    """"**Your** main phase" is a turn as well as a phase."""

    def test_an_opponent_flashing_it_in_gets_no_addendum(self, builder):
        # Turn 1 is player 0's, so this is the opponent casting an instant during
        # somebody else's main phase. It is *a* main phase -- so a key that only
        # asked about the phase would fire -- and it is not theirs.
        game = position(builder, step=Step.PRECOMBAT_MAIN, caster=1)
        oid = cast_it(game, pid=1)

        assert asks(game, oid, "main", controller=1)
        assert not asks(game, oid, "your_main", controller=1)

        their_bear = creature(game, 1)
        assert "indestructible" in keywords_of(game, their_bear)
        assert "vigilance" not in keywords_of(game, their_bear)
        assert game.state.objects[their_bear].counter("+1/+1") == 0

    def test_and_takes_nothing_from_the_active_player(self, builder):
        game = position(builder, step=Step.PRECOMBAT_MAIN, caster=1)
        cast_it(game, pid=1)
        mine = creature(game, 0)
        assert keywords_of(game, mine) == set()
        assert game.state.objects[mine].counter("+1/+1") == 0


class TestNothingWasCast:
    """A permanent nobody cast has no cast-time phase to report."""

    def test_a_permanent_put_onto_the_battlefield_answers_false(self, builder):
        game = position(builder, step=Step.PRECOMBAT_MAIN)
        bear = creature(game, 0)
        assert game.state.objects[bear].cast_step is None
        # Every name in the vocabulary, because "false by default" is the claim:
        # "if you cast this spell" is not true of a token or of a permanent an
        # effect put onto the battlefield.
        assert not any(asks(game, bear, name) for name in sorted(CAST_DURING_NAMES))


class TestLoadTime:
    """A phase name the turn structure does not have is a load error."""

    def _card(self, spec):
        return {
            "id": "t_addendum_bad",
            "name": "Bad Addendum",
            "mana_cost": "{W}",
            "types": ["Instant"],
            "spell_effects": [
                {
                    "op": "if",
                    "condition": {"cast_during": spec},
                    "then": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }

    def test_it_is_a_known_condition(self):
        assert "cast_during" in CONDITION_KEYS

    @pytest.mark.parametrize("spec", ["main phase", "precombat", "your_main_phase", "", True, 3])
    def test_an_unknown_phase_is_refused(self, spec):
        # It would match nothing, so the addendum clause would never fire on a
        # card that prints one -- the silent failure the loader exists to catch.
        with pytest.raises(DslError, match="cast_during"):
            compile_card(CardModel.model_validate(self._card(spec)))

    def test_the_real_names_load(self):
        for spec in sorted(CAST_DURING_NAMES):
            compile_card(CardModel.model_validate(self._card(spec)))

    def test_a_cost_reduction_may_not_ask_it(self):
        # A reduction is priced before the spell is on the stack, so the stamp
        # has not been written -- and on a *second* cast of the same card the
        # stamp from the first is still there, so this would not read a harmless
        # False, it would read a stale True. Refused with the other four
        # cast-variant flags.
        payload = {
            "id": "t_addendum_cheap",
            "name": "Cheap Addendum",
            "mana_cost": "{4}{W}",
            "types": ["Instant"],
            "cost_reduction": {
                "amount": 2,
                "condition": {"cast_during": "your_main"},
            },
            "spell_effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
        }
        with pytest.raises(DslError, match="cannot be answered while a cost is being priced"):
            compile_card(CardModel.model_validate(payload))
