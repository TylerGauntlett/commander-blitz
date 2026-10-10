""""Whenever <event> **this turn**" -- a delayed ability that watches an event.

    Forth Eorlingas! -- "Create X 2/2 red Human Knight creature tokens with
    trample and haste. Whenever one or more creatures you control deal combat
    damage to one or more players this turn, you become the monarch."

Rule 603.7 has two shapes and the engine only had one. `delay` names a **moment**
-- "at the beginning of the next end step" -- and `turn.DELAY_STEPS` is the whole
of its vocabulary, so a delayed ability that waits for a *thing that happens*
could not be written at all. This is the other shape: a subscription created by a
resolving spell, with no permanent to hang itself on, that lives until the turn
ends.

Three things had to exist and each is a way this could be silently wrong:

1. **Somewhere to keep it.** `state.delayed_triggers`, beside the step-scoped
   form, because everything else about the two is the same -- bindings and
   controller captured when it is created, no source object at all when it
   fires. `turn._delay_due` refuses it explicitly rather than by accident.
2. **A hook where events are dispatched.** `triggers.collect`, the one funnel
   every fired event goes through. It *arms* rather than resolves, because
   `collect` is reached from inside `damage_player` where nothing can ask a
   question, so a copy waits on `state.armed_delays` and `game._advance`
   resolves it -- exactly the arrangement `pending_triggers` already has.
3. **A clear-down.** `turn._cleanup_step`, beside every other "this turn" clause
   that outlives the permanent that said it. Not "after it fires once": the
   printed line is "one or more creatures", and `extra_combat` gives a turn a
   second combat that triggers it again.

The batching is the fourth thing and it is why a new event exists.
`deals_combat_damage_to_player` is per *connection*, so a card built on it hands
out the monarchy once per Knight that got through. `EventType.CREATURES_DEALT_COMBAT_DAMAGE`
is fired once per damage batch per damaging player, off the same assignment list
`_monarch_transfer` reads and for the same reason (510.2 makes the damage
simultaneous, so the batch is knowable there and nowhere else).

`max_per_turn: 1` on the per-creature trigger is the tempting substitute and is
wrong one step out, which `TestASecondCombatTriggersItAgain` pins.

Why not a triggered ability on the card: it is a **Sorcery**. Its ability would
be watching from the graveyard, where it either never fires (the default
`active_zones`) or fires for the rest of the game (with `["graveyard"]`), and
neither of those is "this turn".
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.structs import DelayedTrigger
from tests.conftest import _default_answer, oids_of

BEAR = "t_bear"
#: "…this turn, you become the monarch." Forth Eorlingas!'s second line, alone.
MONARCH = "t_delayed_monarch"
#: "…this turn, you gain 1 life." The same subscription with a *counter* on the
#: end, because life is how often it fired and the monarchy is only whether.
GAIN = "t_delayed_gain"
#: The same with `controller: "any"` -- "whenever one or more creatures deal
#: combat damage", whoever is swinging them.
GAIN_ANY = "t_delayed_gain_any"
#: The same clause printed on a **permanent**, so the batch event can be pinned
#: without the delay machinery in the way.
WATCHER = "t_batch_damage_watcher"


def position(builder, *, caster: int = 0, bears: int = 1, hand=(), p0=(), p1=()):
    """Player 0 attacks; the spell under test is cast from ``caster``'s hand.

    Three players, because "one or more **players**" is a claim about a batch
    that spans seats, and a two-player game cannot tell one event covering two
    defenders from two events.
    """
    b = builder(players=3)
    b.battlefield(0, [*([BEAR] * bears), *p0])
    b.battlefield(caster, ["mountain"] * 4)
    if p1:
        b.battlefield(1, list(p1))
    if hand:
        b.hand(caster, list(hand))
    for pid in range(3):
        b.library(pid, ["swamp"] * 20)
    return b.active(0).step(Step.UNTAP).max_turns(3).build()


def to_kind(game, kind: DecisionKind, limit: int = 200):
    for _ in range(limit):
        decision = game.pending()
        if decision is None or decision.kind is kind:
            return game
        game.apply(_default_answer(game, decision))
    raise AssertionError(f"never reached {kind}")


def cast(game, card_id: str, player: int = 0, limit: int = 200):
    """Cast the spell from ``player``'s hand and let it resolve.

    Passing priority until the seat that holds it can act, because the seat that
    installs the subscription and the seat whose creatures connect have to be
    able to differ -- which is the whole of the ``controller`` clause.
    """
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            break
        if decision.kind is DecisionKind.PRIORITY and decision.player == player:
            action = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CAST
                    and game.state.objects[a.source].def_id == card_id
                ),
                None,
            )
            if action is not None:
                game.apply(action)
                run_to(game, lambda g: not g.state.stack)
                return
        game.apply(_default_answer(game, decision))
    raise AssertionError(f"never got to cast {card_id} as player {player}")


def swing(game, plan: dict[int, int]) -> None:
    """Send player 0's creatures at the seats in ``plan`` -- ``{defender: how many}``.

    Chosen by *available action* rather than by oid, because the second combat
    of a turn only has the creatures the first one left untapped.
    """
    to_kind(game, DecisionKind.DECLARE_ATTACKERS)
    used: set[int] = set()
    for defender, count in plan.items():
        for _ in range(count):
            action = next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source not in used
                and any(t.kind == "player" and t.id == defender for t in a.targets)
            )
            used.add(action.source)
            game.apply(action)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
    )
    # "Past the damage", not "resting at end of combat": a step nobody has
    # anything to do in is auto-passed and the game never *stops* there, so a
    # predicate naming one step would run the whole game out. The turn guard is
    # the other end of the same problem.
    turn = game.state.turn
    run_to(game, lambda g: g.state.turn != turn or g.state.step >= Step.END_OF_COMBAT)


def run_to(game, predicate, limit: int = 400) -> None:
    for _ in range(limit):
        if predicate(game) or game.over:
            return
        decision = game.pending()
        if decision is None:
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("run_to did not reach its condition")


def batches(game) -> list:
    """Every `creatures_dealt_combat_damage` in the log."""
    return [
        e for e in game.state.events if e.type == EventType.CREATURES_DEALT_COMBAT_DAMAGE
    ]


def watching(game) -> list[DelayedTrigger]:
    return [d for d in game.state.delayed_triggers if d.trigger is not None]


class TestItFiresOnTheEventAndNotBefore:
    def test_resolving_the_spell_does_nothing_by_itself(self, builder):
        """The whole difference from an immediate effect. A version that gave
        the crown away on resolution would pass every test below that only
        checks the end state."""
        game = position(builder, hand=[MONARCH])
        cast(game, MONARCH)

        assert game.state.monarch is None
        assert len(watching(game)) == 1

    def test_combat_damage_fires_it(self, builder):
        game = position(builder, hand=[MONARCH])
        cast(game, MONARCH)
        swing(game, {1: 1})

        assert game.state.monarch == 0

    def test_a_creature_that_was_blocked_fires_nothing(self, builder):
        """"…to one or more **players**". Damage to a blocker is combat damage
        and is not this, which is the half `dealt_damage` would get wrong."""
        game = position(builder, hand=[MONARCH], p1=[BEAR])
        cast(game, MONARCH)
        to_kind(game, DecisionKind.DECLARE_ATTACKERS)
        attacker = next(iter(oids_of(game, BEAR, 0)))
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER and a.source == attacker
            )
        )
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
        )
        to_kind(game, DecisionKind.DECLARE_BLOCKERS)
        blocker = next(iter(oids_of(game, BEAR, 1)))
        block = next(
            (
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_BLOCKER and a.source == blocker
            ),
            None,
        )
        if block is None:  # pragma: no cover - the seat that was attacked blocks
            pytest.skip("player 1 cannot block here")
        game.apply(block)
        run_to(game, lambda g: g.state.step is Step.END_OF_COMBAT)

        assert batches(game) == []
        assert game.state.monarch is None


class TestOncePerBatch:
    def test_three_creatures_connecting_fire_it_once(self, builder):
        """The whole reason the event exists. `deals_combat_damage_to_player`
        is per connection, so X Knights getting through would run the delayed
        ability X times -- three life here instead of one."""
        game = position(builder, bears=3, hand=[GAIN])
        cast(game, GAIN)
        before = game.state.players[0].life
        swing(game, {1: 3})

        assert len(batches(game)) == 1
        assert game.state.players[0].life == before + 1

    def test_two_seats_hit_in_one_batch_fire_it_once(self, builder):
        """"…to one or more **players**", which is where this batch stops being
        the shape `creatures_attack_player` has: that one is per defending seat,
        because its printed clause is "one of your opponents"."""
        game = position(builder, bears=2, hand=[GAIN])
        cast(game, GAIN)
        before = game.state.players[0].life
        swing(game, {1: 1, 2: 1})

        assert len(batches(game)) == 1
        assert sorted(batches(game)[0].data["damaged"]) == [1, 2]
        assert game.state.players[0].life == before + 1

    def test_the_batch_names_the_creatures_that_connected(self, builder):
        game = position(builder, bears=2, hand=[GAIN])
        cast(game, GAIN)
        swing(game, {1: 2})

        assert sorted(batches(game)[0].data["damagers"]) == sorted(oids_of(game, BEAR, 0))

    def test_the_same_clause_on_a_permanent_also_fires_once(self, builder):
        """The event is once-per-batch on its own, before any delay is involved.
        Pinned separately so a regression in the batching cannot hide behind the
        arming queue."""
        game = position(builder, bears=3, p0=[WATCHER])
        before = game.state.players[0].life
        swing(game, {1: 3})

        assert game.state.players[0].life == before + 1


class TestWhoseCreatures:
    def test_you_does_not_fire_for_an_opponents_batch(self, builder):
        """`controller: "you"` is "creatures **you control**", compared against
        the player captured when the spell resolved -- not against whoever the
        card ends up sitting under. A two-player game where the caster is also
        the attacker cannot tell the two apart."""
        game = position(builder, caster=1, hand=[GAIN])
        cast(game, GAIN, player=1)
        before = game.state.players[1].life
        swing(game, {2: 1})

        assert len(batches(game)) == 1, "player 0's creatures did connect"
        assert game.state.players[1].life == before

    def test_any_fires_for_an_opponents_batch(self, builder):
        game = position(builder, caster=1, hand=[GAIN_ANY])
        cast(game, GAIN_ANY, player=1)
        before = game.state.players[1].life
        swing(game, {2: 1})

        assert game.state.players[1].life == before + 1

    def test_the_controller_is_captured_not_read_off_the_card(self, builder):
        """603.7: the *resolving ability* creates the delayed one, so "you" is
        fixed then. The source is a sorcery in a graveyard by the time it fires,
        and `you gain 1 life` has to reach the caster and nobody else."""
        game = position(builder, caster=1, hand=[GAIN_ANY])
        cast(game, GAIN_ANY, player=1)
        installed = watching(game)[0]

        assert installed.controller == 1
        assert game.state.objects[installed.source_oid].zone.value == "graveyard"


class TestItLastsExactlyTheTurn:
    def test_a_second_combat_triggers_it_again(self, builder):
        """Why `max_per_turn: 1` on the per-creature trigger is not the same
        card: an extra combat this turn is a second batch and a second firing,
        and a per-turn cap would silently swallow it."""
        game = position(builder, bears=2, hand=[GAIN])
        cast(game, GAIN)
        before = game.state.players[0].life
        swing(game, {1: 1})
        assert game.state.players[0].life == before + 1

        from commanderblitz.engine.turn import grant_extra_phases

        grant_extra_phases(game.state, ["combat"])
        run_to(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
        swing(game, {1: 1})

        assert len(batches(game)) == 2
        assert game.state.players[0].life == before + 2

    def test_it_is_gone_after_cleanup(self, builder):
        """"**this turn**". A subscription left on the list would make the next
        turn's first attack hand out the monarchy all over again -- the same
        failure a trigger printed on the card in the graveyard would have, one
        turn later instead of forever."""
        game = position(builder, hand=[GAIN])
        cast(game, GAIN)
        assert watching(game)

        start = game.state.turn
        run_to(game, lambda g: g.state.turn > start)

        assert watching(game) == []

    def test_a_step_scoped_delay_survives_the_same_cleanup(self, builder):
        """The clear-down is keyed on the *kind* of delay and not on the list,
        because "at the beginning of the next upkeep" is scheduled across this
        very boundary. A blanket clear would throw Arcane Denial's draw away."""
        game = position(builder, hand=[GAIN])
        cast(game, GAIN)
        game.state.delayed_triggers.append(
            DelayedTrigger(
                step="upkeep",
                controller=0,
                effects=({"op": "gain_life", "player": "you", "amount": {"const": 7}},),
                turn=game.state.turn,
            )
        )
        before = game.state.players[0].life

        start = game.state.turn
        run_to(game, lambda g: g.state.turn > start + 2)

        assert watching(game) == []
        assert game.state.players[0].life >= before + 7


class TestTheLoaderRefusesWhatCannotWork:
    def compile(self, effect: dict):
        model = CardModel.model_validate(
            {
                "id": "t_probe_delayed",
                "name": "Probe",
                "mana_cost": "{R}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )
        return compile_card(model)

    def base(self, **trigger):
        spec = {"event": "creatures_deal_combat_damage"}
        spec.update(trigger)
        return {
            "op": "delayed_trigger",
            "trigger": spec,
            "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
        }

    def test_it_loads(self):
        card = self.compile(self.base(controller="you"))
        assert card.spell_effects[0]["trigger"]["event"] == "creatures_deal_combat_damage"

    def test_an_unknown_event_is_refused(self):
        """`delay`'s misspelled-step failure exactly: the subscription installs,
        nothing ever satisfies it, and the card reads as printed for ever."""
        with pytest.raises(DslError, match="unknown trigger event"):
            self.compile(self.base(event="creatures_deal_combat_damage_to_a_player"))

    def test_a_trigger_with_no_event_is_refused(self):
        with pytest.raises(DslError, match="needs a 'trigger'"):
            self.compile(
                {
                    "op": "delayed_trigger",
                    "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
                }
            )

    def test_no_effects_is_refused(self):
        with pytest.raises(DslError, match="needs 'effects'"):
            self.compile(
                {
                    "op": "delayed_trigger",
                    "trigger": {"event": "creatures_deal_combat_damage"},
                    "effects": [],
                }
            )

    def test_source_self_is_refused(self):
        """It is read off the permanent hosting the ability, and a delayed one
        has none -- so it would load, look like a restriction, and be ignored."""
        with pytest.raises(DslError, match="not supported on a delayed trigger"):
            self.compile(self.base(source="self"))

    def test_a_filter_is_refused(self):
        with pytest.raises(DslError, match="not supported on a delayed trigger"):
            self.compile(self.base(filter={"types": ["Creature"]}))

    def test_a_target_inside_it_is_refused(self):
        """The same refusal `delay` carries: 603.7's delayed ability never chose
        a target, so `run_armed_delays` builds its context with `targets={}` and
        the selector would resolve to nothing."""
        with pytest.raises(DslError, match="resolves to nothing"):
            self.compile(
                {
                    "op": "delayed_trigger",
                    "trigger": {"event": "creatures_deal_combat_damage"},
                    "effects": [{"op": "destroy", "objects": {"target": "t1"}}],
                }
            )
