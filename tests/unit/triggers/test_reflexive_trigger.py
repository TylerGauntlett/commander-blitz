"""Espers to Magicite — "…**When you do**, choose up to one target creature card
exiled this way."

    Exile each opponent's graveyard. When you do, choose up to one target
    creature card exiled this way. Create a token that's a copy of that card,
    except it's an artifact and it loses all other card types.

A reflexive triggered ability (603.11): the second sentence is a separate object
that goes on the stack after the first one has been carried out, and picks its
target *there*.

**A fifth `AbilityKind`, for the reason there is a fourth.** "When you do" names
no event. It means "when the instruction immediately above this one is carried
out", which is a fact about one resolution and not about anything the board can
be watched for — so the ability carries no `TriggerSpec` at all, and the effect
that carries out the instruction fires it by name. Both gates that keep it from
firing on its own hold independently: `_candidate_abilities` skips an ability
whose `trigger` is None, and `Ability.is_triggered` is False for this kind.

**Not more effects inline**, which is the shape it is easiest to mistake for.
Written that way the choice is made mid-resolution and is not a *target*:
nothing is announced, nobody may respond, and 608.2b never re-checks it. It also
moves *when* the choice happens — `t_inline` is the same two sentences as one
resolution, and its target is declared before the exile it is supposed to follow.

**Not `delayed_trigger`**, which watches an `EventType` and would need one that
does not exist.

The wiring is checked in both directions at load time because both directions
are silent: an ability nothing fires is a printed line that never happens, and
an op naming an id that is not there is a spell missing its second sentence.
Neither fails any other check — the ability compiles, the op is a known name.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import AbilityKind, ActionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import event_types

REFLEX = "t_reflex"
INLINE = "t_inline"
BEAR = "t_bear"


def board(builder, card: str = REFLEX):
    return (
        builder(players=2)
        .hand(0, [card, "forest"])
        .battlefield(0, ["swamp"] * 4)
        .battlefield(1, [BEAR])
        .graveyard(1, [BEAR, "forest"])
        .library(0, ["forest"] * 10)
        .build()
    )


def cast(game, card: str):
    state = game.state
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and state.card(a.source).id == card
    )
    game.apply(action)
    return game


def settle(game, limit: int = 30):
    for _ in range(limit):
        if not game.state.stack and game.pending() is None:
            return game
        actions = game.legal_actions()
        if not actions:
            return game
        game.apply(actions[0])
    return game


def log(game, since: int):
    """The event names emitted since a mark, which is where the ordering lives."""
    return event_types(game.state.events[since:])


def alive(game, pid: int = 1):
    state = game.state
    return [state.card_of(o).id for o in state.battlefield_objects(pid)]


class TestItIsItsOwnObjectOnTheStack:
    def test_the_target_is_declared_after_the_spell_has_resolved(self, builder):
        """The ordering *is* the rule. 603.11 puts the ability on the stack the
        next time a player would receive priority, and 603.3d chooses its
        targets as it is put there -- so the target is announced after the
        spell that fired it has finished and left."""
        game = board(builder)
        mark = len(game.state.events)
        cast(game, REFLEX)
        events = log(game, mark)
        assert events.index("became_target") > events.index("spell_resolved")

    def test_the_inline_version_declares_it_first(self, builder):
        """The counterfactual: written as more effects the choice is made at
        cast time, before the instruction it is supposed to follow."""
        game = board(builder, INLINE)
        mark = len(game.state.events)
        cast(game, INLINE)
        events = log(game, mark)
        assert events.index("became_target") < events.index("spell_resolved")

    def test_it_resolves_as_its_own_ability(self, builder):
        game = board(builder)
        mark = len(game.state.events)
        cast(game, REFLEX)
        assert "ability_resolved" in log(game, mark)

    def test_the_instruction_above_it_happened_first(self, builder):
        """"When you **do**" -- and the exile is what it reflects on."""
        game = board(builder)
        mark = len(game.state.events)
        cast(game, REFLEX)
        events = log(game, mark)
        assert events.index("leaves_graveyard") < events.index("ability_triggered")

    def test_it_eventually_resolves(self, builder):
        game = settle(cast(board(builder), REFLEX))
        assert alive(game) == []


class TestTheTargetIsChosenWhenItGoesOnTheStack:
    def test_the_cast_action_declares_no_target(self, builder):
        """The spell's own target line is empty: the target belongs to the
        reflexive ability, and 603.3d hands it over one moment later."""
        game = board(builder)
        state = game.state
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and state.card(a.source).id == REFLEX
        )
        assert action.targets == ()

    def test_the_inline_version_declares_it_at_cast_time(self, builder):
        """The counterfactual, and the observable difference between the two
        readings: `t_inline` names its creature before the exile it follows."""
        game = board(builder, INLINE)
        state = game.state
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and state.card(a.source).id == INLINE
        )
        assert action.targets != ()


class TestNothingElseCanFireIt:
    def test_it_carries_no_trigger_spec(self, registry):
        ability = registry.get(REFLEX).abilities[0]
        assert ability.kind is AbilityKind.REFLEXIVE
        assert ability.trigger is None

    def test_it_is_not_a_triggered_ability_for_matching_purposes(self, registry):
        """`_candidate_abilities` skips on either of these, and both are set:
        one gate failing quietly would let the card fire itself."""
        assert not registry.get(REFLEX).abilities[0].is_triggered

    def test_playing_a_whole_turn_without_it_never_fires_it(self, builder):
        """Nothing on the board is an event this ability answers to, so a game
        in which the spell is never cast never sees the second sentence."""
        game = (
            builder(players=2)
            .hand(0, [REFLEX, "forest"])
            .battlefield(0, ["swamp"] * 4)
            .battlefield(1, [BEAR])
            .graveyard(1, [BEAR])
            .library(0, ["forest"] * 10)
            .build()
        )
        mark = len(game.state.events)
        settle(game)
        assert "ability_triggered" not in log(game, mark)
        assert alive(game) == [BEAR]


def _card(**overrides):
    ability = {
        "kind": "reflexive",
        "id": "aftermath",
        "text": "When you do, draw a card.",
        "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
    }
    ability.update(overrides.pop("ability", {}))
    for key in [k for k, v in ability.items() if v is None]:
        ability.pop(key)
    body = {
        "id": "t_bad_reflex",
        "name": "Test Bad Reflex",
        "oracle_text": "Draw a card. When you do, draw a card.",
        "mana_cost": "{1}",
        "types": ["Sorcery"],
        "spell_effects": [
            {"op": "draw", "player": "you", "amount": {"const": 1}},
            {"op": "reflexive_trigger", "ability": "aftermath"},
        ],
        "abilities": [ability],
    }
    body.update(overrides)
    return CardModel.model_validate(body)


class TestTheLoaderChecksBothDirections:
    def test_it_loads_when_the_two_halves_agree(self):
        compile_card(_card(), source="test")

    def test_an_ability_nothing_fires_is_refused(self):
        """A printed line that never happens, and nothing else would say so."""
        with pytest.raises(DslError, match="is never fired"):
            compile_card(
                _card(
                    spell_effects=[{"op": "draw", "player": "you", "amount": {"const": 1}}]
                ),
                source="test",
            )

    def test_an_op_naming_nothing_is_refused(self):
        with pytest.raises(DslError, match="no reflexive ability"):
            compile_card(_card(ability={"id": "elsewhere"}), source="test")

    def test_the_op_needs_an_ability_key(self):
        with pytest.raises(DslError, match="'reflexive_trigger' needs an 'ability'"):
            compile_card(
                _card(
                    spell_effects=[{"op": "reflexive_trigger"}],
                    abilities=[],
                ),
                source="test",
            )

    def test_a_reflexive_ability_needs_an_id(self):
        with pytest.raises(DslError, match="needs an 'id'"):
            compile_card(_card(ability={"id": None}), source="test")

    def test_it_may_not_write_its_own_trigger(self):
        """The point of the kind: an event would let the board fire it."""
        with pytest.raises(DslError, match="does not write a trigger"):
            compile_card(
                _card(ability={"trigger": {"event": "self_enters", "source": "self"}}),
                source="test",
            )

    def test_an_id_on_another_kind_is_refused(self):
        """Nothing would ever read it, and its author believed otherwise."""
        with pytest.raises(DslError, match="'id' only means anything on a reflexive"):
            compile_card(
                _card(
                    spell_effects=[{"op": "draw", "player": "you", "amount": {"const": 1}}],
                    abilities=[
                        {
                            "kind": "triggered",
                            "id": "aftermath",
                            "trigger": {"event": "self_enters", "source": "self"},
                            "text": "When this enters, draw a card.",
                            "effects": [
                                {"op": "draw", "player": "you", "amount": {"const": 1}}
                            ],
                        }
                    ],
                ),
                source="test",
            )
