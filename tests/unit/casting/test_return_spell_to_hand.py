"""Returning a spell to its owner's hand — which is *not* countering it.

"Return target spell to its owner's hand. Draw a card." Reprieve is the witness,
and every interesting property of the card comes from the one line rule 701.5a
draws: **countering is a specific action**, and moving a spell off the stack some
other way is not it. Three things follow, and an implementation built on top of
`counter` gets all three wrong:

- "This spell can't be countered" does not stop it. Reprieve answers an
  uncounterable spell perfectly well, and a version that refused would be a
  strictly worse card than the printed one.
- The card goes to its **owner's hand**, not to a graveyard and not to the
  hand of whoever is doing the returning.
- Nothing that watches for a countered spell sees anything happen, so no
  `SPELL_COUNTERED` event is emitted.

**The failure this test exists to catch is a silent one.** The obvious way to
write the card — `return_to_hand` aimed at `{"target": "t1"}` — passes every
authoring gate while doing *nothing*: a `kind: "spell"` target is a
`TargetRef.stack(sid)`, `resolve_pool` keeps only `kind == "object"` refs, so the
pool comes back empty, the op returns having moved nothing, and the targeted
creature spell resolves onto the battlefield untouched. So it is not enough here
to assert that Reprieve resolved. Every test below asserts on where the *other*
spell ended up.

The last case has no card of its own yet and is pinned anyway, because it is the
one the rules answer counter-intuitively: a **copy** of a spell (706.10) is not a
card. There is nothing to put in a hand, so 704.5e removes it and it simply
ceases to exist.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.registry import CardRegistry
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.ops_stack import put_copy_on_stack
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.sandbox import GameBuilder
from commanderblitz.engine.stack import pull_spell_off_stack, push_spell
from commanderblitz.engine.structs import TargetRef
from tests.conftest import count_on_battlefield, event_types, pass_until

#: Reprieve, in the DSL. Written here rather than added to the shared test pool
#: because the whole claim of this module is about what this exact wording does,
#: and the wording and the assertions about it belong side by side.
REPRIEVE = {
    "id": "t_reprieve",
    "name": "Test Reprieve",
    "oracle_text": "Return target spell to its owner's hand.\nDraw a card.",
    "mana_cost": "{1}{W}",
    "types": ["Instant"],
    "targets": [{"id": "t1", "kind": "spell", "selector": {}, "count": 1}],
    "spell_effects": [
        {"op": "return_spell_to_hand", "target": "t1"},
        {"op": "draw", "amount": {"const": 1}},
    ],
}

#: A creature spell that cannot be countered -- the case where "return" and
#: "counter" stop agreeing, and the reason this could not be `counter` with a
#: different destination key bolted on.
STUBBORN = {
    "id": "t_stubborn_bear",
    "name": "Test Stubborn Bear",
    "oracle_text": "This spell can't be countered.",
    "mana_cost": "{1}{G}",
    "types": ["Creature"],
    "subtypes": ["Bear"],
    "power": 2,
    "toughness": 2,
    "uncounterable": True,
}

BEAR = "t_bear"


@pytest.fixture
def builder(registry: CardRegistry):
    """The shared pool plus this module's two cards.

    Overrides the session fixture of the same name so every helper below reads
    the way it does everywhere else. `CardRegistry` takes a plain id -> CardDef
    mapping, so no file has to be touched to add a card to one game.
    """
    cards = {card.id: card for card in registry}
    for payload in (REPRIEVE, STUBBORN):
        card = compile_card(CardModel.model_validate(payload))
        cards[card.id] = card
    pool = CardRegistry(cards)

    def make(players: int = 2, seed: int = 0) -> GameBuilder:
        return GameBuilder(pool, players=players, seed=seed)

    return make


def position(builder, *, spell: str = BEAR, reprieves: int = 1):
    """P1 casts ``spell``; P0 holds priority with Test Reprieve in hand.

    Returns ``(game, sid)`` where ``sid`` names the spell on the stack -- the
    only handle a card has on it, since a spell is a stack item and not a
    permanent.

    P0 gets exactly two Plains per Reprieve, so ``reprieves=1`` cannot hold one
    back; P1 keeps two Forests spare, which is what stops the turn rolling over
    the moment the stack empties -- with the returned spell back in hand and the
    mana to recast it, P1 has a real decision and the game must stop and ask.
    Without that the position auto-advances into P0's next turn, and a
    "did P0 draw?" assertion would be counting the draw step.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * (2 * reprieves))
        .battlefield(1, ["forest"] * 4)
        .hand(0, ["t_reprieve"] * reprieves)
        .hand(1, [spell])
        .library(0, ["island"] * 10)
        .library(1, ["island"] * 10)
        .active(1)
        .build()
    )
    for action in game.legal_actions():
        if (
            action.kind is ActionKind.CAST
            and action.source is not None
            and game.state.objects[action.source].def_id == spell
        ):
            game.apply(action)
            break
    else:  # pragma: no cover - a broken position, not a broken op
        raise AssertionError(f"P1 could not cast {spell}")
    pass_until(game, lambda g: g.state.priority_player == 0 and bool(g.state.stack))
    assert game.state.stack, "the spell should still be waiting to resolve"
    return game, game.state.stack[-1].sid


def cast_reprieve(game, sid: int) -> None:
    """P0 casts Test Reprieve at the spell ``sid``, and does not resolve it."""
    want = TargetRef.stack(sid)
    for action in game.legal_actions():
        if action.kind is ActionKind.CAST and action.source is not None:
            obj = game.state.objects[action.source]
            if obj.def_id == "t_reprieve" and want in action.targets:
                game.apply(action)
                return
    raise AssertionError(f"no cast of Test Reprieve at sid {sid}")


def run_op(state, controller: int, targets, source_oid: int | None = None) -> None:
    """Run the bare op, outside a card, and assert it asks nothing."""
    ctx = EffectContext(
        state=state, controller=controller, source_oid=source_oid, targets=targets
    )
    for _ in execute(ctx, [{"op": "return_spell_to_hand", "target": "t1"}]):
        raise AssertionError("return_spell_to_hand has no question to ask")


def card_oid(game, def_id: str) -> int:
    return next(oid for oid, obj in game.state.objects.items() if obj.def_id == def_id)


class TestTheSpellActuallyLeaves:
    """The claim the naive card passed all six gates without ever making."""

    def test_the_spell_is_off_the_stack_and_in_its_owners_hand(self, builder):
        game, sid = position(builder)
        bear = card_oid(game, BEAR)
        cast_reprieve(game, sid)
        pass_until(game, lambda g: not g.state.stack)

        assert count_on_battlefield(game, BEAR) == 0, (
            "the whole failure this pins: the targeted spell resolving anyway"
        )
        assert game.state.stack_item(sid) is None
        assert game.state.objects[bear].zone is Zone.HAND
        assert bear in game.state.players[1].hand
        assert game.state.objects[bear].stack_id is None

    def test_it_is_the_owners_hand_not_the_returners(self, builder):
        game, sid = position(builder)
        bear = card_oid(game, BEAR)
        before = list(game.state.players[0].hand)
        cast_reprieve(game, sid)
        pass_until(game, lambda g: not g.state.stack)

        assert bear not in game.state.players[0].hand
        # P0's hand is what it was, minus the Reprieve it cast, plus its draw.
        assert len(game.state.players[0].hand) == len(before) - 1 + 1

    def test_the_second_sentence_still_happens(self, builder):
        """"Draw a card." A returned spell is not a fizzle."""
        game, sid = position(builder)
        library = len(game.state.players[0].library)
        cast_reprieve(game, sid)
        pass_until(game, lambda g: not g.state.stack)

        assert len(game.state.players[0].library) == library - 1

    def test_a_spell_cast_by_someone_who_does_not_own_it_goes_home(self, builder):
        """Rule 400.7 / 108.3: "its owner's hand" is not "its controller's".

        A spell whose controller is not its owner is rare enough that no shipped
        card makes one here, so it is built directly: `push_spell` takes the
        controller as an argument precisely because the two can differ.
        """
        game = builder(players=2).hand(1, [BEAR]).build()
        bear = card_oid(game, BEAR)
        item = push_spell(game.state, bear, controller=0)

        run_op(game.state, 0, {"t1": (TargetRef.stack(item.sid),)})

        assert bear in game.state.players[1].hand, "owner's hand, not controller's"
        assert bear not in game.state.players[0].hand


class TestItIsNotACounter:
    """Rule 701.5a. Three observable differences, one per test."""

    def test_an_uncounterable_spell_is_still_returned(self, builder):
        game, sid = position(builder, spell="t_stubborn_bear")
        stubborn = card_oid(game, "t_stubborn_bear")
        cast_reprieve(game, sid)
        pass_until(game, lambda g: not g.state.stack)

        assert count_on_battlefield(game, "t_stubborn_bear") == 0
        assert stubborn in game.state.players[1].hand

    def test_nothing_is_told_that_a_spell_was_countered(self, builder):
        game, sid = position(builder)
        mark = len(game.state.events)
        cast_reprieve(game, sid)
        pass_until(game, lambda g: not g.state.stack)

        kinds = event_types(game.state.events[mark:])
        assert EventType.SPELL_COUNTERED not in kinds, (
            "'whenever a spell is countered' must not see a returned spell"
        )

    def test_the_card_does_not_pass_through_a_graveyard(self, builder):
        game, sid = position(builder)
        cast_reprieve(game, sid)
        pass_until(game, lambda g: not g.state.stack)

        assert BEAR not in [
            game.state.objects[oid].def_id for oid in game.state.players[1].graveyard
        ]


class TestACopyIsNotACard:
    """Rule 706.10: a copy of a spell is not a card, so no hand can hold it."""

    def test_the_copy_ceases_to_exist_instead(self, builder):
        game = builder(players=2).hand(1, [BEAR]).build()
        bear = card_oid(game, BEAR)
        original = push_spell(game.state, bear, controller=1)
        copy = put_copy_on_stack(game.state, 1, original)
        assert copy.oid is not None

        run_op(game.state, 0, {"t1": (TargetRef.stack(copy.sid),)})

        assert game.state.stack_item(copy.sid) is None
        assert copy.oid not in game.state.objects, "704.5e removes it outright"
        for player in game.state.players:
            assert copy.oid not in player.hand

    def test_the_original_is_untouched(self, builder):
        game = builder(players=2).hand(1, [BEAR]).build()
        bear = card_oid(game, BEAR)
        original = push_spell(game.state, bear, controller=1)
        copy = put_copy_on_stack(game.state, 1, original)

        run_op(game.state, 0, {"t1": (TargetRef.stack(copy.sid),)})

        assert game.state.stack_item(original.sid) is original
        assert game.state.objects[bear].zone is Zone.STACK


class TestWhenTheSpellHasAlreadyGone:
    """608.2b re-checks targets on resolution."""

    def test_the_second_reprieve_fizzles_and_does_not_draw(self, builder):
        """Two Reprieves at one spell. The second to resolve returns it; the
        first has nothing left to return, so it does not resolve at all -- and
        that takes its draw with it, because 608.2b counters the whole spell
        rather than skipping the sentence that lost its target."""
        game, sid = position(builder, reprieves=2)
        library = len(game.state.players[0].library)
        mark = len(game.state.events)
        cast_reprieve(game, sid)
        cast_reprieve(game, sid)
        pass_until(game, lambda g: not g.state.stack)

        kinds = event_types(game.state.events[mark:])
        assert EventType.SPELL_FIZZLED in kinds
        assert kinds.count("draw") == 1, (
            "only the Reprieve that found its target draws"
        )
        assert len(game.state.players[0].library) == library - 1

    def test_the_helper_says_so_rather_than_raising(self, builder):
        """An sid that is not on the stack is an answer, not an error."""
        game = builder(players=2).build()
        assert pull_spell_off_stack(game.state, 999, Zone.HAND) is None

    def test_an_ability_on_the_stack_is_not_a_spell(self, builder):
        """"Target spell" never names one, but the helper is asked directly by
        tests and by any future op, and an ability has no card to return."""
        from commanderblitz.engine.stack import push_activated_ability

        game = builder(players=2).battlefield(0, ["forest"]).build()
        forest = game.state.battlefield[0]
        item = push_activated_ability(game.state, forest, 0, 0)

        assert pull_spell_off_stack(game.state, item.sid, Zone.HAND) is None
        assert game.state.stack_item(item.sid) is item


class TestTheLoaderRefusesTheNearMisses:
    def _card(self, effect: dict, kind: str = "spell") -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_probe",
                "name": "Test Probe",
                "mana_cost": "{1}{W}",
                "types": ["Instant"],
                "oracle_text": "Return target spell to its owner's hand.",
                "targets": [{"id": "t1", "kind": kind, "selector": {}, "count": 1}],
                "spell_effects": [effect],
            }
        )

    def test_the_ordinary_form_loads(self):
        compile_card(self._card({"op": "return_spell_to_hand", "target": "t1"}))

    def test_a_permanent_target_is_refused_rather_than_ignored(self):
        with pytest.raises(DslError, match="kind 'spell'"):
            compile_card(
                self._card({"op": "return_spell_to_hand", "target": "t1"}, kind="permanent")
            )

    def test_an_undeclared_target_is_refused(self):
        with pytest.raises(DslError, match="does not declare"):
            compile_card(self._card({"op": "return_spell_to_hand", "target": "t9"}))

    def test_a_selector_is_refused_rather_than_dropped(self):
        """`objects` is what `return_to_hand` takes, so it is the copy-paste
        mistake -- and accepted here it would be silently ignored."""
        with pytest.raises(DslError, match="reads no 'objects'"):
            compile_card(
                self._card(
                    {
                        "op": "return_spell_to_hand",
                        "target": "t1",
                        "objects": {"zone": "stack"},
                    }
                )
            )
