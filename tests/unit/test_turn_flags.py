"""A word written onto a permanent that wears off at the turn boundary.

"If this creature hasn't been **exerted this turn**, you may exert it as it
attacks" -- Combat Celebrant, rule 701.40b ("a permanent has been exerted if it
was exerted this turn"). Exert itself needs no engine support and never did:
`test_exert.py` cashes it as an `attacks` trigger, a `may` and `skip_untap`.
What had no home was the *record* of the choice.

`obj.flags` is the nearest shape and is one-way **on purpose**: renown must never
be re-earned, so `op_set_flag` writes into a plain `set` that nothing in the
engine ever removes from and `clear_until_eot` does not touch. A guard written
there reads "hasn't been exerted this **game**" -- which passes every one-turn
test and makes the card work exactly once per game.

Every other near miss answers a different question, and each is wrong in the
common case rather than an edge case:

- `once_each_turn` restricts *activating*, and the loader refuses it on anything
  that is not an activated ability. This is a triggered one.
- `max_per_turn` on the trigger counts where the ability **queues**, so a
  declined `may` spends the turn's one offer. Declining exerts nothing.
- `resolutions_this_turn` counts resolutions, and the ability resolves whether
  you take the `may` or not -- the same mistake one layer down.
- `attacked_this_turn` is about attacking, which the creature did either way.

So `TurnLedger.object_flags`, written by `set_turn_flag` and read by
`{"has_turn_flag": ...}`: the turn-scoped twin of `set_flag`/`has_flag`, kept as
a separate op and a separate key for the reason `skip_untap` and `freeze` are
separate ops -- the two lifetimes are different rules objects and reaching for
the wrong one is invisible until the second turn.

The witness is `t_celebrant`, Combat Celebrant's shape with vigilance added so
it can be in the second combat it grants itself. Without the guard that second
attack grants a third combat, and the turn runs to `MAX_EXTRA_PHASES_PER_TURN`.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.events import EventType
from automtg.engine.state import MAX_EXTRA_PHASES_PER_TURN
from automtg.engine.turn import grant_extra_phases
from tests.conftest import _default_answer, find_action, only_oid, pass_until

CELEBRANT = "t_celebrant"  # 2/2 vigilance; once a turn, exert for an extra combat
BEAR = "t_bear"


def position(builder, *, others: list[str] | None = None, step: Step | None = None):
    """`t_celebrant` on the battlefield, plus whatever else the claim needs."""
    build = builder(players=2).battlefield(0, [CELEBRANT, *(others or [])])
    if step is not None:
        build = build.step(step)
    game = build.build(advance=step is None)
    return game, only_oid(game, CELEBRANT, 0)


def attack_with(game, oid: int) -> None:
    """Declare ``oid`` as an attacker in the next declare-attackers step."""
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=oid))
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def play_out_attacking_and_exerting(game) -> None:
    """Finish the turn, attacking with everything and taking every `may`.

    The greediest legal line, which is the only one the loop claim can be made
    against: a driver that declines the offer would end the turn at two combats
    whether the guard exists or not.
    """
    turn = game.state.turn
    for _ in range(600):
        decision = game.pending()
        if game.over or decision is None or game.state.turn != turn:
            return
        if decision.kind is DecisionKind.DECLARE_ATTACKERS:
            for add in [a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER]:
                game.apply(add)
            game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        elif decision.kind is DecisionKind.MAY:
            game.apply(find_action(game, ActionKind.YES))
        else:
            game.apply(_default_answer(game, decision))


def combats_in(game, turn: int) -> int:
    """How many combat phases that turn entered, off the event log."""
    return [
        str(event.data["step"])
        for event in game.state.events
        if event.type == EventType.STEP_ENDED and event.turn == turn
    ].count("BEGIN_COMBAT")


def exerted(game, oid: int) -> bool:
    return game.state.turn_ledger.has_object_flag(oid, "exerted")


class TestTheRecordIsWrittenByTheChoice:
    """Only taking the `may` exerts, which is the whole of what was missing."""

    def test_taking_it_records_the_word(self, builder):
        game, oid = position(builder)
        attack_with(game, oid)
        game.apply(find_action(game, ActionKind.YES))

        assert exerted(game, oid)
        assert game.state.objects[oid].skip_next_untap, "and it really was exerted"

    def test_declining_records_nothing(self, builder):
        """The trigger fired and the ability resolved; neither is an exert.

        This is the assertion that rules out `max_per_turn` and
        `resolutions_this_turn`, both of which would have counted this.
        """
        game, oid = position(builder)
        attack_with(game, oid)
        game.apply(find_action(game, ActionKind.NO))

        assert not exerted(game, oid)
        assert not game.state.objects[oid].skip_next_untap

    def test_it_is_not_written_onto_the_permanent(self, builder):
        """`set_turn_flag` and `set_flag` are two stores, not one with a switch.

        Nothing empties `obj.flags`, so a word that has to wear off must never
        land there -- and `has_flag` must not start answering for it.
        """
        game, oid = position(builder)
        attack_with(game, oid)
        game.apply(find_action(game, ActionKind.YES))

        assert game.state.objects[oid].flags == set()


class TestTheGuardBites:
    def test_a_second_attack_in_the_same_turn_is_not_offered_the_choice(self, builder):
        game, oid = position(builder)
        attack_with(game, oid)
        game.apply(find_action(game, ActionKind.YES))

        attack_with(game, oid)  # the extra combat it just granted itself
        decision = game.pending()
        assert decision is None or decision.kind is not DecisionKind.MAY

    def test_the_turn_gets_one_extra_combat_and_not_twenty(self, builder):
        """The guard is what ends the loop, so the count is the whole claim.

        Combat Celebrant untaps its team and takes another combat; with no
        record of having been exerted it does that again in the combat it made,
        and the turn runs until `MAX_EXTRA_PHASES_PER_TURN` stops it.
        """
        game, _oid = position(builder, others=[BEAR])
        turn = game.state.turn
        play_out_attacking_and_exerting(game)

        assert combats_in(game, turn) == 2
        assert combats_in(game, turn) < MAX_EXTRA_PHASES_PER_TURN, "not merely capped"

    def test_declining_leaves_the_choice_open_later_in_the_turn(self, builder):
        """Two combats from elsewhere: decline in the first, get asked in the second.

        The distinguishing test. Every rejected near miss is spent by the first
        *offer*; the printed clause is spent only by the first *exert*.
        """
        game, oid = position(builder, step=Step.UPKEEP)
        grant_extra_phases(game.state, ["combat"])
        game._advance()

        attack_with(game, oid)
        game.apply(find_action(game, ActionKind.NO))

        attack_with(game, oid)
        decision = game.pending()
        assert decision is not None and decision.kind is DecisionKind.MAY


class TestItWearsOffAtTheTurnBoundary:
    """The half `set_flag` cannot do, and the half a one-turn test never sees."""

    def test_the_record_does_not_survive_the_turn(self, builder):
        game, oid = position(builder)
        turn = game.state.turn
        attack_with(game, oid)
        game.apply(find_action(game, ActionKind.YES))
        assert exerted(game, oid)

        pass_until(game, lambda g: g.state.turn > turn)
        assert not exerted(game, oid)
        assert game.state.turn_ledger.object_flags == {}

    def test_it_can_be_exerted_again_on_a_later_turn(self, builder):
        """The behavioural half: the card is a once-per-turn card, not a once-per-game one."""
        game, oid = position(builder)
        turn = game.state.turn
        attack_with(game, oid)
        game.apply(find_action(game, ActionKind.YES))
        pass_until(game, lambda g: g.state.turn >= turn + 2 and g.state.step >= Step.PRECOMBAT_MAIN)

        attack_with(game, oid)
        decision = game.pending()
        assert decision is not None and decision.kind is DecisionKind.MAY
        game.apply(find_action(game, ActionKind.YES))
        pass_until(game, lambda g: g.state.turn > turn + 2)
        assert combats_in(game, turn + 2) == 2, "a fresh extra combat, two turns later"


class TestTheLoaderGuardsIt:
    def sorcery(self, effect: dict) -> dict:
        return {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "x",
            "mana_cost": "{1}",
            "types": ["Sorcery"],
            "spell_effects": [effect],
        }

    def test_a_flagless_write_is_refused(self):
        """It writes nothing, so the guard reading it back never bites."""
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(self.sorcery({"op": "set_turn_flag"})))

    def test_a_duration_is_refused(self):
        """The duration is in the op's name; `set_flag` is the other one."""
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    self.sorcery(
                        {"op": "set_turn_flag", "flag": "exerted", "duration": "permanent"}
                    )
                )
            )

    def test_a_flag_name_that_is_not_a_name_is_refused(self):
        """`true` stringifies to `"True"`, which no `set_turn_flag` ever wrote."""
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "probe",
                        "name": "Probe",
                        "oracle_text": "x",
                        "mana_cost": "{1}",
                        "types": ["Sorcery"],
                        "spell_effects": [
                            {
                                "op": "draw",
                                "amount": {"const": 1},
                                "condition": {"has_turn_flag": True},
                            }
                        ],
                    }
                )
            )

    def test_the_card_loads_as_an_intervening_if(self, registry):
        card = registry.get(CELEBRANT)
        (ability,) = [a for a in card.abilities if a.is_triggered]
        assert ability.trigger is not None
        assert ability.trigger.condition == {"not": {"has_turn_flag": "exerted"}}
        (may,) = ability.effects
        assert [e["op"] for e in may["effects"]] == [
            "set_turn_flag",
            "skip_untap",
            "untap",
            "extra_combat",
        ]
