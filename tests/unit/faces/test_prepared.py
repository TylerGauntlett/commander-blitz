"""Emeritus of Woe // Demonic Tutor — **prepared**.

    This creature enters prepared. (While it's prepared, you may cast a copy of
    its spell. Doing so unprepares it.)
    At the beginning of your end step, if two or more creatures died this turn,
    this creature becomes prepared.

A per-permanent state that is itself a **casting permission**, and every piece
the engine already had was one step off.

**Not `second_face`.** That models a card with a second castable half and is
almost this — but its whole invariant is the one prepared breaks: casting a
second face takes the object out of its zone. Here the permanent stays exactly
where it is and a **copy** goes on the stack. One card, two objects, which no
other face relationship in the engine has. `second_face_zone` is `hand` or
`graveyard` for the same reason: those are zones a spell leaves.

**Not `set_flag`.** A flag is inert bookkeeping — renown is stored that way —
and nothing in the casting-permission path reads `obj.flags`, so a permanent
flagged "prepared" would gain no ability to cast anything and the card would
silently do nothing. `set_flag` has no counterpart that clears one either, and
`set_turn_flag` expires at the turn boundary rather than on use, which is a
different card again: prepared survives until it is spent.

**Not a counter.** The reminder text is the whole mechanic and says nothing
about a number: a permanent is prepared or it is not.

**Entering prepared is a replacement**, in the slot enters-tapped occupies, not
a trigger. The permanent is never seen unprepared, so nothing can respond in the
window between its arriving and its state being set — and two `self_enters`
triggers reading it would answer differently depending on the order their
controller put them on the stack.

The cast is offered from the **battlefield**, which no other cast line is: every
zone `_cast_actions` walks is one the spell then leaves. Priced, timed and
targeted off the spell face, the way an Adventure half is.

"Doing so unprepares it" is the rules' own sentence, so `Game._cast` clears the
state and no card writes it — which is also why the permission needs no rate
limit: it is spent by being used.

`t_unprepared` is the counterfactual, the same creature without the entering
clause.
"""

from __future__ import annotations

import pytest

from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.conftest import only_oid

EMERITUS = "t_emeritus"
UNPREPARED = "t_unprepared"
TUTOR = "t_tutor"


def board(builder, card: str = EMERITUS, *, prepared: bool = True):
    game = (
        builder(players=2)
        .battlefield(0, [card])
        .battlefield(0, ["swamp"] * 4)
        .hand(0, ["forest"])
        .library(0, ["forest"] * 10)
        .build()
    )
    # `.battlefield()` places a permanent rather than resolving it, so the
    # entering replacement never ran -- these tests assert on the replacement
    # separately, in `TestEnteringPrepared`.
    if prepared:
        game.state.objects[only_oid(game, card)].prepared = True
    return game


def castable(game):
    """The cards on offer, naming the **face** a prepared line would cast.

    The action's `source` is the permanent, because that is what `Game._cast`
    has to find again to unprepare it -- so the card being cast has to be read
    off `prepared_face` rather than off the source.
    """
    state = game.state
    out = []
    for action in game.legal_actions():
        if action.kind is not ActionKind.CAST:
            continue
        card = state.card(action.source)
        out.append(card.prepared_face if action.prepared else card.id)
    return sorted(out)


def cast_the_copy(game, *, settle: bool = False):
    """Cast the prepared line, optionally letting the copy resolve.

    Without ``settle`` the spell is left mid-resolution -- the search it does
    asks a question -- which is where the state of the *permanent* is worth
    reading.
    """
    action = next(a for a in game.legal_actions() if a.kind is ActionKind.CAST)
    game.apply(action)
    if settle:
        for _ in range(20):
            decision = game.pending()
            if decision is None or decision.kind is DecisionKind.PRIORITY:
                break
            actions = game.legal_actions()
            if not actions:
                break
            game.apply(actions[0])
    return game


class TestThePermissionIsTheState:
    def test_a_prepared_permanent_offers_its_spell(self, builder):
        assert castable(board(builder)) == [TUTOR]

    def test_an_unprepared_one_does_not(self, builder):
        assert castable(board(builder, prepared=False)) == []

    def test_the_creature_itself_is_not_on_offer(self, builder):
        """It is on the battlefield; what the state offers is its spell."""
        assert EMERITUS not in castable(board(builder))


class TestItIsACopy:
    def test_the_permanent_stays_on_the_battlefield(self, builder):
        """The invariant `second_face` cannot hold: casting a second face takes
        the object out of its zone."""
        game = board(builder)
        oid = only_oid(game, EMERITUS)
        cast_the_copy(game)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD

    def test_the_spell_is_a_second_object(self, builder):
        """One card, two objects -- which no other face relationship in the
        engine has."""
        game = board(builder)
        oid = only_oid(game, EMERITUS)
        cast_the_copy(game)
        copies = [o for o in game.state.objects.values() if o.def_id == TUTOR]
        assert len(copies) == 1
        assert copies[0].oid != oid
        assert copies[0].zone is Zone.STACK

    def test_the_copy_is_a_token(self, builder):
        game = board(builder)
        cast_the_copy(game)
        copy = next(o for o in game.state.objects.values() if o.def_id == TUTOR)
        assert copy.is_token

    def test_it_actually_resolves(self, builder):
        """The spell face's own effect: "search your library for a card"."""
        game = board(builder)
        before = len(game.state.players[0].hand)
        cast_the_copy(game, settle=True)
        assert len(game.state.players[0].hand) == before + 1

    def test_the_copy_ceases_to_exist(self, builder):
        """111.7. It must be a token, and this is why: the card that would
        otherwise land in a graveyard is not the one that was cast, and Emeritus
        is standing on the battlefield."""
        game = board(builder)
        cast_the_copy(game, settle=True)
        assert not [o for o in game.state.objects.values() if o.def_id == TUTOR]
        assert game.state.players[0].graveyard == []


class TestCastingItUnpreparesIt:
    def test_the_state_is_spent(self, builder):
        game = board(builder)
        oid = only_oid(game, EMERITUS)
        cast_the_copy(game)
        assert not game.state.objects[oid].prepared

    def test_a_second_copy_is_not_offered(self, builder):
        """No rate limit is written anywhere, and none is needed: the
        permission is spent by being used."""
        game = board(builder)
        cast_the_copy(game)
        assert castable(game) == []


class TestEnteringPrepared:
    def test_a_resolved_creature_arrives_prepared(self, builder):
        from automtg.engine.zones import move_object

        game = (
            builder(players=2)
            .hand(0, [EMERITUS])
            .battlefield(0, ["swamp"] * 4)
            .library(0, ["forest"] * 10)
            .build(advance=False)
        )
        oid = game.state.players[0].hand[0]
        move_object(game.state, oid, Zone.BATTLEFIELD, to_player=0, cause="resolved")
        assert game.state.objects[oid].prepared

    def test_the_counterfactual_does_not(self, builder):
        from automtg.engine.zones import move_object

        game = (
            builder(players=2)
            .hand(0, [UNPREPARED])
            .battlefield(0, ["swamp"] * 4)
            .library(0, ["forest"] * 10)
            .build(advance=False)
        )
        oid = game.state.players[0].hand[0]
        move_object(game.state, oid, Zone.BATTLEFIELD, to_player=0, cause="resolved")
        assert not game.state.objects[oid].prepared

    def test_a_permanent_that_leaves_is_no_longer_prepared(self, builder):
        """400.7 makes it a new object, and the printed line is what puts the
        state on."""
        from automtg.engine.zones import move_object

        game = board(builder)
        oid = only_oid(game, EMERITUS)
        move_object(game.state, oid, Zone.GRAVEYARD, to_player=0, cause="test")
        assert not game.state.objects[oid].prepared


class TestBecomingPrepared:
    def test_the_op_turns_it_on(self, builder):
        from automtg.engine.effects import execute
        from automtg.engine.effects.context import EffectContext

        game = board(builder, prepared=False)
        state = game.state
        oid = only_oid(game, EMERITUS)
        ctx = EffectContext(state=state, controller=0, source_oid=oid)
        gen = execute(ctx, state.card_of(state.objects[oid]).abilities[0].effects)
        try:
            while True:
                next(gen)
        except StopIteration:
            pass
        assert state.objects[oid].prepared
        assert castable(game) == [TUTOR]


class TestTiming:
    def test_a_sorcery_face_is_not_offered_at_instant_speed(self, builder):
        """Priced *and timed* off the spell face, the way an Adventure half is:
        Demonic Tutor is a sorcery whatever the creature printing it is."""
        game = board(builder)
        game.state.step = Step.DECLARE_ATTACKERS
        assert castable(game) == []


class TestTheLoaderChecksTheLink:
    def _card(self, **overrides):
        from automtg.cards.schema import CardModel

        body = {
            "id": "t_bad_prepared",
            "name": "Test Bad Prepared",
            "oracle_text": "This creature enters prepared.",
            "mana_cost": "{3}{B}",
            "types": ["Creature"],
            "power": 2,
            "toughness": 2,
            "prepared_face": "t_tutor",
        }
        body.update(overrides)
        return CardModel.model_validate(body)

    def test_an_unknown_face_is_refused(self, registry):
        from automtg.cards.loader import compile_card
        from automtg.cards.loader.linking import link_prepared_faces
        from automtg.engine.errors import DslError

        pool = {c.id: c for c in registry}
        card = compile_card(self._card(prepared_face="t_nothing"), source="test")
        pool[card.id] = card
        with pytest.raises(DslError, match="unknown card"):
            link_prepared_faces(pool)

    def test_a_permanent_face_is_refused(self, registry):
        """"a copy of its **spell**" -- a creature put on the stack this way
        would be a spell that never leaves it."""
        from automtg.cards.loader import compile_card
        from automtg.cards.loader.linking import link_prepared_faces
        from automtg.engine.errors import DslError

        pool = {c.id: c for c in registry}
        card = compile_card(self._card(prepared_face="t_bear"), source="test")
        pool[card.id] = card
        with pytest.raises(DslError, match="is a permanent"):
            link_prepared_faces(pool)

    def test_the_op_needs_objects(self):
        from automtg.cards.loader import compile_card
        from automtg.cards.schema import CardModel
        from automtg.engine.errors import DslError

        with pytest.raises(DslError, match="nothing to prepare"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_bad_prepare_op",
                        "name": "Test Bad Prepare Op",
                        "oracle_text": "It becomes prepared.",
                        "mana_cost": "{1}",
                        "types": ["Sorcery"],
                        "spell_effects": [{"op": "become_prepared"}],
                    }
                ),
                source="test",
            )
