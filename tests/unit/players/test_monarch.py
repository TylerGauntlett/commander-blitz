"""The monarch (rule 721): a designation exactly one player holds at a time.

"You become the monarch." Eight cards in the pool print it -- Palace Jailer,
Aragorn King of Gondor, Faramir Steward of Gondor, Champions of Minas Tirith,
Crown of Gondor, Éomer King of Rohan, Forth Eorlingas! and Oath of Eorl -- and
Faramir is the shipped witness, since he is the one the rest of the DSL can
already say in full.

**This reverses a documented decision.** `docs/rules-coverage.md` listed "the
monarch, initiative and the other designated-player mechanics" under Not
implemented, with the note that the city's blessing and day/night *are*. That was
a decision, and the thing it was waiting on was a place to keep a designation.
Day/night found the place -- `GameState`, beside `turn` and `step` -- so this is
the same field with two rules hung off it.

**The word is worth nothing; the two rules are the mechanic.** A card that only
printed "you become the monarch" would load, resolve, change one integer and
never do anything again. What makes the monarch a card-a-turn engine and a
five-mana 2/2 body a fair rate is 721.3's pair of inherent triggered abilities:
the monarch draws at the beginning of their own end step, and any creature that
deals combat damage to the monarch hands the crown to its controller. Neither has
a source and neither belongs to a card, so they live in the turn machine and in
combat, beside the day/night switch. The second is what the printed cards are
*balanced against* -- it is the only ordinary way the crown ever moves -- and it
is the only thing that can ever end Palace Jailer's exile.

**Exclusivity is the representation, not a rule** (721.4). `state.monarch` is one
optional player id, so giving the crown away takes it off the previous holder
with nothing written to do so. `has_city_s_blessing` is the right *shape* for a
player-level designation and the wrong semantics: it is one-way and
non-exclusive, so a monarch built that way would let two players hold it and
would need every write site to remember to clear the others.

**`None` is a third state.** "If there is no monarch" (Crown of Gondor) is *not*
`{"not": {"is_monarch": "you"}}` -- that negation is also true while an opponent
holds the crown, which is precisely the case that card must not fire in. Two
condition keys, because they are two questions.

The boundaries worth pinning are the ones that would each ship a quietly
different card: the draw is the monarch's *own* end step and not every end step;
the transfer reads who was the monarch when the damage was *dealt*, not one hit
at a time; re-designating the player who already holds it fires nothing, because
"until an opponent becomes the monarch" is a question about the crown moving; and
a monarch who leaves the game hands it on rather than leaving it on a dead seat.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.conditions import evaluate_condition
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.primitives import become_monarch
from commanderblitz.engine.structs import TargetRef
from tests.conftest import _default_answer, find_action, only_oid, pass_until

BEARER = "t_crown_bearer"  # 2/2; "when this enters, you become the monarch"
WATCHER = "t_crown_watcher"  # 1/3; "whenever an opponent becomes the monarch, draw"
BEAR = "t_bear"


def board(builder, *, players: int = 2, cards=(BEARER,), step: Step = Step.PRECOMBAT_MAIN):
    """A position with ``cards`` on player 0's battlefield, and the first oid.

    Built with ``advance=False`` and left frozen: every assertion below is about
    a designation nobody has to play a turn to see, and advancing runs the
    engine's auto-pass, which rolls the position into turns this file then has to
    reason about.
    """
    game = (
        builder(players=players)
        .battlefield(0, list(cards))
        .battlefield(1, [BEAR])
        .turn(3)
        .step(step)
        .build(advance=False)
    )
    oid = only_oid(game, cards[0]) if cards else None
    return game, oid


def run_op(game, spec: dict, *, controller: int = 0, source: int | None = None) -> None:
    """Resolve one effect op with no card in the way."""
    ctx = EffectContext(state=game.state, controller=controller, source_oid=source)
    gen = execute(ctx, [spec])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def monarch_events(game) -> list:
    return [e for e in game.state.events if e.type == EventType.BECAME_MONARCH]


def asks(game, cond, *, controller: int = 0) -> bool:
    return evaluate_condition(game.state, cond, controller=controller)


def settle(game, limit: int = 40) -> None:
    """Resolve whatever is waiting, advancing when nobody has priority."""
    for _ in range(limit):
        if not game.state.pending_triggers and not game.state.stack:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the trigger never resolved")


class TestTheDesignationItself:
    def test_no_monarch_at_the_start_of_the_game(self, builder):
        """721.2: there is no monarch as a game begins.

        `None` rather than the starting player, for the reason day/night starts
        as neither day nor night: a game nobody granted it in has no monarch, and
        "if there is no monarch" must say yes.
        """
        game, _ = board(builder)
        assert game.state.monarch is None

    def test_becoming_the_monarch_sets_it(self, builder):
        game, _ = board(builder)
        assert become_monarch(game.state, 0)
        assert game.state.monarch == 0

    def test_only_one_player_holds_it(self, builder):
        """721.4. One field, so giving it away is also taking it away."""
        game, _ = board(builder)
        become_monarch(game.state, 0)
        become_monarch(game.state, 1)
        assert game.state.monarch == 1
        assert asks(game, {"is_monarch": "you"}, controller=1)
        assert not asks(game, {"is_monarch": "you"}, controller=0), (
            "a per-player boolean would leave both holding it, and nothing in "
            "the shape of the field would say that is wrong"
        )

    def test_re_designating_the_holder_is_a_no_op(self, builder):
        """The event means the crown *moved*.

        Palace Jailer's exile lasts "until an opponent becomes the monarch". If
        becoming the monarch while already the monarch fired, the Jailer's own
        controller re-crowning themselves would hand the creature back.
        """
        game, _ = board(builder)
        become_monarch(game.state, 0)
        fired = len(monarch_events(game))
        assert not become_monarch(game.state, 0)
        assert len(monarch_events(game)) == fired

    def test_the_event_names_the_new_monarch_and_the_old(self, builder):
        game, _ = board(builder)
        become_monarch(game.state, 0)
        become_monarch(game.state, 1)
        latest = monarch_events(game)[-1]
        assert latest.player == 1
        assert latest.data["previous"] == 0

    def test_a_player_who_has_left_cannot_become_the_monarch(self, builder):
        game, _ = board(builder, players=3)
        game.state.players[2].has_lost = True
        assert not become_monarch(game.state, 2)
        assert game.state.monarch is None


class TestTheEndStepDraw:
    """721.3: "At the beginning of the monarch's end step, that player draws a card.\""""

    def at_end_step(self, game):
        """Run the end step's turn-based actions, and nothing after them.

        `GameBuilder.build` leaves `step_started` true -- the position *is* in
        that step rather than about to enter it -- so the actions have notionally
        happened and something has to ask for them. `test_becomes_untapped.py`
        arms the untap step the same way.

        Driven directly rather than through `game._advance()`, which keeps
        auto-passing: from an end step it crosses cleanup into the next turn and
        the *next* player's draw step, so a hand-size assertion would be reading
        an ordinary turn draw and would pass whatever this step did.
        """
        from commanderblitz.engine import turn

        game.state.step_started = False
        gen = turn.begin_step(game.state)
        with contextlib.suppress(StopIteration):
            while True:
                next(gen)

    def test_the_monarch_draws(self, builder):
        game, _ = board(builder, step=Step.END_STEP)
        become_monarch(game.state, 0)
        before = len(game.state.players[0].hand)
        self.at_end_step(game)
        assert len(game.state.players[0].hand) == before + 1

    def test_nobody_draws_when_there_is_no_monarch(self, builder):
        game, _ = board(builder, step=Step.END_STEP)
        before = [len(p.hand) for p in game.state.players]
        self.at_end_step(game)
        assert [len(p.hand) for p in game.state.players] == before

    def test_it_is_the_monarch_s_own_end_step(self, builder):
        """"**The monarch's** end step", not everybody's.

        The whole value of the mechanic is one extra card per round. A version
        that drew on every end step would draw one per opponent per round, which
        at a pod is three or four cards a turn cycle from a two-mana creature.
        """
        game, _ = board(builder, step=Step.END_STEP)
        become_monarch(game.state, 1)
        before = len(game.state.players[1].hand)
        self.at_end_step(game)
        assert len(game.state.players[1].hand) == before, (
            "player 1 is the monarch but it is player 0's end step"
        )

    def test_a_monarch_who_left_the_game_draws_nothing(self, builder):
        game, _ = board(builder, players=3, step=Step.END_STEP)
        become_monarch(game.state, 0)
        game.state.players[0].has_lost = True
        before = len(game.state.players[0].hand)
        self.at_end_step(game)
        assert len(game.state.players[0].hand) == before


def swing(game, oid: int, defender: int = 1) -> None:
    """Attack ``defender`` with one creature and run combat out."""
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    game.apply(
        find_action(
            game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(defender),)
        )
    )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    start = game.state.turn
    for _ in range(80):
        if game.over:
            return
        if game.state.turn != start or int(game.state.step) > int(Step.COMBAT_DAMAGE):
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))


class TestTheCombatDamageTransfer:
    """721.3: "Whenever a creature deals combat damage to the monarch, that
    creature's controller becomes the monarch.\"

    The half that makes the designation *contestable*, and the reason a monarch
    card is priced the way it is. Without it the first player to say the word
    keeps the crown for the rest of the game and Palace Jailer is a strictly
    better Journey to Nowhere.
    """

    def test_connecting_with_the_monarch_takes_the_crown(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR])
            .battlefield(1, ["plains"])
            .turn(3)
            .build()
        )
        become_monarch(game.state, 1)
        swing(game, only_oid(game, BEAR, 0))
        assert game.state.monarch == 0

    def test_connecting_with_somebody_who_is_not_the_monarch_does_nothing(self, builder):
        game = (
            builder(players=3)
            .battlefield(0, [BEAR])
            .battlefield(1, ["plains"])
            .battlefield(2, ["plains"])
            .turn(3)
            .build()
        )
        become_monarch(game.state, 2)
        swing(game, only_oid(game, BEAR, 0), defender=1)
        assert game.state.monarch == 2, (
            "the crown moves only when the damage lands on the monarch"
        )

    def test_it_does_nothing_when_there_is_no_monarch(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR])
            .battlefield(1, ["plains"])
            .turn(3)
            .build()
        )
        swing(game, only_oid(game, BEAR, 0))
        assert game.state.monarch is None, (
            "there is no crown to take, and creating one out of a hit would give "
            "every combat deck a monarch it never paid for"
        )

    def test_two_creatures_connecting_do_not_cancel_each_other(self, builder):
        """The reason this is not folded into `damage_player`.

        Combat damage is dealt simultaneously (510.2). Read one hit at a time,
        the second creature would find the crown already moved by the first and
        transfer nothing -- and with two attackers belonging to the same player
        that is invisible, because the answer happens to come out right. It is
        the *snapshot* being right that keeps it right, so this pins the
        snapshot.
        """
        game = (
            builder(players=2)
            .battlefield(0, [BEAR, BEAR])
            .battlefield(1, ["plains"])
            .turn(3)
            .build()
        )
        become_monarch(game.state, 1)
        pass_until(
            game,
            lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
        )
        bears = [obj.oid for obj in game.state.battlefield_objects(0)]
        assert len(bears) == 2
        for oid in bears:
            game.apply(
                find_action(
                    game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(1),)
                )
            )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        start = game.state.turn
        for _ in range(80):
            if game.over or game.state.turn != start:
                break
            if int(game.state.step) > int(Step.COMBAT_DAMAGE):
                break
            decision = game.pending()
            if decision is None:
                game._advance()
                continue
            game.apply(_default_answer(game, decision))
        assert game.state.monarch == 0
        # One transfer, not two: both hits are in the same batch and the crown
        # only moved once, so a watcher hears one event rather than one per
        # attacker.
        assert [e.player for e in monarch_events(game)[1:]] == [0]

    def test_the_transfer_fires_the_event(self, builder):
        """So a watcher woken by the designation moving hears the commonest route.

        Palace Jailer's exile ends far more often by somebody connecting than by
        anybody casting anything, so an event fired only from the op would miss
        the case the card is about.
        """
        game = (
            builder(players=2)
            .battlefield(0, [BEAR])
            .battlefield(1, ["plains"])
            .turn(3)
            .build()
        )
        become_monarch(game.state, 1)
        before = len(monarch_events(game))
        swing(game, only_oid(game, BEAR, 0))
        fired = monarch_events(game)[before:]
        assert [e.player for e in fired] == [0]


class TestTheOp:
    def test_it_defaults_to_you(self, builder):
        game, _ = board(builder)
        run_op(game, {"op": "become_monarch"})
        assert game.state.monarch == 0

    def test_it_takes_a_player_spec(self, builder):
        """Éomer's "target player becomes the monarch" is the reason.

        Written with an implicit controller the op reads perfectly and gives the
        crown to the wrong player, which on a card whose drawback is handing an
        opponent a card a turn is most of the card.
        """
        game, _ = board(builder)
        run_op(game, {"op": "become_monarch", "player": "opponent"})
        assert game.state.monarch == 1

    def test_a_card_can_grant_it(self, builder):
        """The op reached through a real ability, not just through `execute`."""
        game = (
            builder(players=2)
            .hand(0, [BEARER])
            .battlefield(0, ["plains"] * 3)
            .battlefield(1, [BEAR])
            .turn(3)
            .build()
        )
        game.apply(find_action(game, ActionKind.CAST, source=only_oid_in_hand(game, BEARER)))
        settle(game)
        assert game.state.monarch == 0

    def test_the_designation_survives_its_source_leaving(self, builder):
        """It is the player's, not the permanent's -- Oath of Eorl sacrifices
        itself as its own final chapter resolves, and Forth Eorlingas! is a
        sorcery in a graveyard by the time the crown arrives."""
        game, oid = board(builder)
        run_op(game, {"op": "become_monarch"}, source=oid)
        from commanderblitz.engine.zones import destroy

        destroy(game.state, oid)
        sba.run(game.state)
        assert game.state.monarch == 0


class TestTheTriggerEvent:
    def test_an_opponent_taking_the_crown_wakes_a_watcher(self, builder):
        game, _ = board(builder, cards=(WATCHER,))
        before = len(game.state.players[0].hand)
        become_monarch(game.state, 1)
        settle(game)
        assert len(game.state.players[0].hand) == before + 1

    def test_the_controller_clause_reads_the_new_monarch(self, builder):
        """Not the previous holder.

        `_actor` returns the player who *became* the monarch, so
        `controller: "opponent"` means "an opponent becomes the monarch". Reading
        the crown's previous holder instead would make Palace Jailer's exile end
        when the Jailer's own controller took the crown from an opponent, which
        is the moment it must not.
        """
        game, _ = board(builder, cards=(WATCHER,))
        before = len(game.state.players[0].hand)
        become_monarch(game.state, 0)
        settle(game)
        assert len(game.state.players[0].hand) == before


class TestTheConditionLanguage:
    def test_is_monarch_reads_the_designation(self, builder):
        game, _ = board(builder)
        assert not asks(game, {"is_monarch": "you"})
        become_monarch(game.state, 0)
        assert asks(game, {"is_monarch": "you"})

    def test_is_monarch_can_ask_about_somebody_else(self, builder):
        game, _ = board(builder)
        become_monarch(game.state, 1)
        assert asks(game, {"is_monarch": "opponent"})
        assert not asks(game, {"is_monarch": "you"})

    def test_no_monarch_is_not_the_negation_of_is_monarch(self, builder):
        """Crown of Gondor's clause, and the reason there are two keys.

        "When a legendary creature you control enters, **if there is no
        monarch**, you become the monarch." Written as `{"not": {"is_monarch":
        "you"}}` the card would also fire while an *opponent* held the crown --
        which is a repeatable steal rather than a way to claim a vacant one, and
        is a materially better card.
        """
        game, _ = board(builder)
        assert asks(game, {"no_monarch": True})
        assert asks(game, {"not": {"is_monarch": "you"}})

        become_monarch(game.state, 1)
        assert not asks(game, {"no_monarch": True}), "an opponent holds it"
        assert asks(game, {"not": {"is_monarch": "you"}}), (
            "the negation is still true, which is exactly why it cannot stand in"
        )

    def test_no_monarch_false_is_the_other_half(self, builder):
        game, _ = board(builder)
        assert not asks(game, {"no_monarch": False})
        become_monarch(game.state, 0)
        assert asks(game, {"no_monarch": False})


def probe(**card) -> dict:
    base = {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "When Probe enters, you become the monarch.",
        "mana_cost": "{W}",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
    }
    base.update(card)
    return base


def enters(effects, *, text="When Probe enters, you become the monarch.") -> dict:
    return {"kind": "triggered", "text": text, "trigger": {"event": "self_enters"}, "effects": effects}


class TestTheLoadTimeGuards:
    def test_a_plain_become_monarch_loads(self):
        compile_card(
            CardModel.model_validate(probe(abilities=[enters([{"op": "become_monarch"}])]))
        )

    def test_an_unknown_player_spec_is_refused(self):
        """A misspelling would otherwise raise only once the ability resolved --
        mid-game, from a card that loaded and looked fine."""
        with pytest.raises(DslError, match="unknown player spec"):
            compile_card(
                CardModel.model_validate(
                    probe(
                        abilities=[
                            enters([{"op": "become_monarch", "player": "the_monarch"}])
                        ]
                    )
                )
            )

    def test_an_undeclared_target_is_refused(self):
        """Éomer's shape, mistyped. `select_players` would resolve it to nobody,
        so the printed line would do nothing at all and nothing would say so."""
        with pytest.raises(DslError, match="does not declare"):
            compile_card(
                CardModel.model_validate(
                    probe(
                        abilities=[
                            enters([{"op": "become_monarch", "player": {"target": "t1"}}])
                        ]
                    )
                )
            )

    def test_no_monarch_must_be_a_boolean(self):
        """`{"no_monarch": "false"}` is a non-empty string and would read as
        `true`, firing Crown of Gondor in the one case it must not."""
        with pytest.raises(DslError, match="no_monarch"):
            compile_card(
                CardModel.model_validate(
                    probe(
                        abilities=[
                            enters(
                                [
                                    {
                                        "op": "if",
                                        "condition": {"no_monarch": "false"},
                                        "then": [{"op": "become_monarch"}],
                                    }
                                ]
                            )
                        ]
                    )
                )
            )

    def test_an_unknown_is_monarch_player_is_refused(self):
        with pytest.raises(DslError, match="is_monarch"):
            compile_card(
                CardModel.model_validate(
                    probe(
                        abilities=[
                            enters(
                                [
                                    {
                                        "op": "if",
                                        "condition": {"is_monarch": "the_king"},
                                        "then": [{"op": "become_monarch"}],
                                    }
                                ]
                            )
                        ]
                    )
                )
            )

    def test_the_monarch_is_not_a_static_condition(self):
        """Deliberately absent from `STATIC_CONDITION_HEADS`.

        It would be *safe* there -- the designation is a pipeline input, like a
        counter or a life total -- but no card in the pool asks it from a static,
        and `has_city_s_blessing` is in both languages only because a card needed
        both. Vocabulary with no card behind it is what this repo's load-time
        checks exist to keep out.
        """
        with pytest.raises(DslError, match="static condition"):
            compile_card(
                CardModel.model_validate(
                    probe(
                        abilities=[
                            {
                                "kind": "static",
                                "text": "Probe has flying as long as you're the monarch.",
                                "effect": "grant_keyword",
                                "affects": {"self_only": True},
                                "keywords": ["flying"],
                                "condition": {"is_monarch": "you"},
                            }
                        ]
                    )
                )
            )


class TestLeavingTheGame:
    def test_the_crown_passes_to_the_active_player(self, builder):
        """721.5. Unreachable at two players -- the monarch losing ends the game
        -- so this is for the pod, and it is the boundary that is silent when it
        is wrong: a crown left on a dead seat draws for nobody and makes "there
        is no monarch" read False for the rest of the game.
        """
        game, _ = board(builder, players=3)
        become_monarch(game.state, 1)
        game.state.players[1].life = 0
        sba.run(game.state)
        assert game.state.monarch == game.state.active_player == 0

    def test_a_monarch_eliminated_on_their_own_turn_hands_it_on(self, builder):
        game = (
            builder(players=3)
            .battlefield(0, [BEAR])
            .turn(3)
            .active(1)
            .build(advance=False)
        )
        become_monarch(game.state, 1)
        game.state.players[1].life = 0
        sba.run(game.state)
        assert game.state.monarch == 2, "the next seat in turn order"


def only_oid_in_hand(game, card_id: str, pid: int = 0) -> int:
    found = [
        oid for oid in game.state.players[pid].hand if game.state.objects[oid].def_id == card_id
    ]
    assert len(found) == 1, f"expected exactly one {card_id} in hand, found {len(found)}"
    return found[0]
