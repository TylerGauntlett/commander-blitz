"""Putting "the same number and kind of counters" a placement just put.

    "Whenever you put one or more counters on another creature, if it's not a
    Kree, you may put **the same number and kind of counters** on Captain
    Marvel."                               -- Captain Marvel, Apex Avenger

The trigger was always writable -- `counter_placed` with ``put_by: "you"``,
``controller: "any"`` and a filter for another creature -- and the event has
always put the kind and the amount into the bindings. What was missing was an
`add_counters` that could *read* the kind: its ``counter`` was a fixed string,
so the line could only be written for one kind, and a Captain that copies only
+1/+1 counters is a different and weaker card. ``counter: {"binding":
"counter"}`` is that read; ``amount: {"binding": "amount"}`` already worked.

What each reading rests on, and each has a test class:

- **"The same number"** is the event's ``amount``, the number that really
  arrived after replacements (122.6, `primitives.add_counters` reports it after
  `replace_counters`), and the copy is a placement of its own, so a
  replacement on the Captain applies to it again.
- **"And kind"** is any kind: a keyword counter grants its keyword (122.1b) and
  a shield counter is spent as one (122.1c) on the Captain too.
- **"One or more"** triggers once per COUNTER_PLACED. The engine fires one per
  kind per permanent -- `add_counters` takes one kind, proliferate (701.27a)
  adds each kind through it, and an arrival with counters fires one per kind
  (`zones._fire_entered_with_counters`). So a placement of two kinds at once
  is two triggers, each copying its own kind: the Captain ends with exactly
  the counters the other creature got, and "you may" is answered per kind.
- **"You put"** is ``put_by`` (122.6a): an opponent's placement on my creature
  does not trigger it.
- **"Another creature, if it's not a Kree"** is the filter and an
  intervening-if (603.4) on the subject. The Captain's own copy lands on
  herself, which "another" refuses, so the ability never feeds itself.
- **"You may"** declined puts nothing.
- **The loader** allows the bound kind only on `add_counters` under a
  `counter_placed` trigger, the only event that binds one; anywhere else the op
  would put nothing, silently.

Captain Marvel, Apex Avenger is the witness; `t_cpc_captain` in
`tests/data/copy_placed_counters.cards.json` is its trigger on a {W} 1/1.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, add_subtypes
from commanderblitz.engine.zones import destroy
from tests.conftest import find_action, keywords, only_oid, pt

CAPTAIN = "t_cpc_captain"  # copies counters you put on another non-Kree creature
KREE = "t_cpc_kree"  # 2/2 Kree Soldier
BEAR = "t_bear"  # 2/2 Bear
SCALES = "t_rc_scales"  # +1/+1 counters on your creatures: that many plus one
BOLT = "t_bolt"  # {R} instant, so priority stops while a trigger is on the stack


def position(builder, *, mine=(BEAR,), theirs=(BEAR,), counters=None):
    """Player 0 with the Captain and ``mine``; player 1 with ``theirs``.

    Returns ``(game, captain)``, in player 0's precombat main.
    """
    b = builder(players=2).battlefield(0, ["mountain", CAPTAIN])
    b = b.battlefield(0, list(mine), counters=counters or {})
    game = b.battlefield(1, list(theirs)).hand(0, [BOLT]).step(Step.PRECOMBAT_MAIN).build()
    return game, only_oid(game, CAPTAIN, 0)


def resolve(game, *answers: bool) -> list:
    """Pass until everything has resolved, answering each "you may" in turn.

    Returns the may decisions asked, so a test can count the triggers.
    """
    replies = iter(answers)
    asked = []
    for _ in range(400):
        decision = game.pending()
        if decision is None or (
            not game.state.stack
            and not game.state.pending_triggers
            and decision.kind is DecisionKind.PRIORITY
        ):
            return asked
        if decision.kind is DecisionKind.MAY:
            asked.append(decision)
            want = ActionKind.YES if next(replies, True) else ActionKind.NO
            game.apply(find_action(game, want))
            continue
        game.apply(find_action(game, ActionKind.PASS))
    raise AssertionError("did not settle")


def counters_of(game, oid: int) -> dict:
    return {k: n for k, n in game.state.objects[oid].counters.items() if n}


def proliferate(game, controller: int = 0) -> None:
    """One proliferate choosing everything, outside the stack."""
    ctx = EffectContext(state=game.state, controller=controller)
    gen = execute(ctx, [{"op": "proliferate"}])
    try:
        decision = next(gen)
        while True:
            decision = gen.send(list(range(len(decision.options))))
    except StopIteration:
        pass


class TestTheSameNumber:
    def test_plus_one_counters_are_copied_in_number(self, builder):
        game, captain = position(builder)
        bear = only_oid(game, BEAR, 0)
        add_counters(game.state, bear, "+1/+1", 3, by=0)
        assert len(resolve(game, True)) == 1, "three at once are one trigger"
        assert counters_of(game, captain) == {"+1/+1": 3}
        assert pt(game, captain) == (4, 4)

    def test_the_number_is_what_arrived_and_the_copy_is_replaced_again(self, builder):
        """Hardened Scales turns two into three on the bear, and the event reports
        the three that arrived (122.6). The copy is a placement of its own, so the
        Scales makes it four on the Captain."""
        game, captain = position(builder, mine=(BEAR, SCALES))
        bear = only_oid(game, BEAR, 0)
        add_counters(game.state, bear, "+1/+1", 2, by=0)
        assert counters_of(game, bear) == {"+1/+1": 3}
        resolve(game, True)
        assert counters_of(game, captain) == {"+1/+1": 4}

    def test_a_placement_on_an_opponents_creature_counts(self, builder):
        """"Another creature", not "another creature you control": my counter
        on their bear still mirrors."""
        game, captain = position(builder, mine=())
        theirs = only_oid(game, BEAR, 1)
        add_counters(game.state, theirs, "+1/+1", 2, by=0)
        resolve(game, True)
        assert counters_of(game, captain) == {"+1/+1": 2}


class TestTheSameKind:
    @pytest.mark.parametrize("kind", ["flying", "lifelink", "stun", "charge"])
    def test_any_kind_is_copied_as_that_kind(self, builder, kind):
        game, captain = position(builder)
        bear = only_oid(game, BEAR, 0)
        add_counters(game.state, bear, kind, 1, by=0)
        resolve(game, True)
        assert counters_of(game, captain) == {kind: 1}

    def test_a_keyword_counter_grants_its_keyword(self, builder):
        """122.1b: the copy is a real flying counter, not a tally."""
        game, captain = position(builder)
        add_counters(game.state, only_oid(game, BEAR, 0), "flying", 1, by=0)
        resolve(game, True)
        assert "flying" in keywords(game, captain)

    def test_a_shield_counter_is_spent_as_one(self, builder):
        """122.1c: the copied shield replaces the Captain's destruction."""
        game, captain = position(builder)
        add_counters(game.state, only_oid(game, BEAR, 0), "shield", 1, by=0)
        resolve(game, True)
        assert counters_of(game, captain) == {"shield": 1}
        destroy(game.state, captain)
        assert game.state.objects[captain].on_battlefield
        assert counters_of(game, captain) == {}


class TestOneOrMore:
    def test_two_kinds_at_once_are_one_trigger_each(self, builder):
        """Proliferate on a creature with two kinds puts each kind through its
        own placement, so the Captain copies each, and ends with exactly what
        the bear gained."""
        game, captain = position(builder, theirs=(), counters={"+1/+1": 1, "flying": 1})
        bear = only_oid(game, BEAR, 0)
        proliferate(game)
        # Only the bear carried counters, so proliferate offered only it.
        assert counters_of(game, bear) == {"+1/+1": 2, "flying": 2}
        assert len(resolve(game, True, True)) == 2
        assert counters_of(game, captain) == {"+1/+1": 1, "flying": 1}

    def test_each_kind_is_its_own_choice(self, builder):
        game, captain = position(builder, theirs=(), counters={"+1/+1": 1, "flying": 1})
        proliferate(game)
        resolve(game, True, False)
        assert sum(counters_of(game, captain).values()) == 1

    def test_two_creatures_are_two_triggers(self, builder):
        game, captain = position(builder, mine=(BEAR, KREE), theirs=(BEAR,))
        mine, theirs = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)
        add_counters(game.state, mine, "+1/+1", 1, by=0)
        add_counters(game.state, theirs, "+1/+1", 2, by=0)
        assert len(resolve(game, True, True)) == 2
        assert counters_of(game, captain) == {"+1/+1": 3}


class TestYouPut:
    def test_an_opponents_placement_does_not_trigger(self, builder):
        """On my own bear, but they put it: `controller: "any"` alone passes this."""
        game, captain = position(builder)
        add_counters(game.state, only_oid(game, BEAR, 0), "+1/+1", 1, by=1)
        assert not game.state.pending_triggers
        assert resolve(game) == []
        assert counters_of(game, captain) == {}

    def test_the_putter_is_the_sources_controller(self, builder):
        game, _ = position(builder)
        theirs = only_oid(game, BEAR, 1)
        add_counters(game.state, theirs, "+1/+1", 1, source=theirs)
        assert not game.state.pending_triggers


class TestAnotherNonKree:
    def test_placing_on_a_kree_does_not_trigger(self, builder):
        game, captain = position(builder, mine=(KREE,))
        add_counters(game.state, only_oid(game, KREE, 0), "+1/+1", 2, by=0)
        assert not game.state.pending_triggers
        assert counters_of(game, captain) == {}

    def test_becoming_a_kree_in_response_fails_the_recheck(self, builder):
        """603.4: the "if" is asked again on resolution."""
        game, captain = position(builder)
        bear = only_oid(game, BEAR, 0)
        add_counters(game.state, bear, "+1/+1", 1, by=0)
        assert len(game.state.pending_triggers) == 1
        add_subtypes(game.state, bear, ["Kree"])
        assert resolve(game, True) == []
        assert counters_of(game, captain) == {}

    def test_placing_on_herself_does_not_loop(self, builder):
        """Her own copy lands on her, which "another" refuses: one trigger, one
        copy, and the stack empties."""
        game, captain = position(builder)
        add_counters(game.state, only_oid(game, BEAR, 0), "+1/+1", 1, by=0)
        assert len(resolve(game, True)) == 1
        assert counters_of(game, captain) == {"+1/+1": 1}
        assert not game.state.stack and not game.state.pending_triggers

    def test_a_placement_straight_on_her_does_not_trigger(self, builder):
        game, captain = position(builder)
        add_counters(game.state, captain, "+1/+1", 2, by=0)
        assert not game.state.pending_triggers
        assert counters_of(game, captain) == {"+1/+1": 2}


class TestYouMay:
    def test_declined_puts_nothing(self, builder):
        game, captain = position(builder)
        add_counters(game.state, only_oid(game, BEAR, 0), "+1/+1", 2, by=0)
        assert len(resolve(game, False)) == 1
        assert counters_of(game, captain) == {}


class TestTheLoader:
    def _card(self, ability=None, spell_effects=None):
        body = {
            "id": "x",
            "name": "X",
            "types": ["Creature"] if ability else ["Sorcery"],
            "power": 1 if ability else None,
            "toughness": 1 if ability else None,
        }
        if ability:
            body["abilities"] = [ability]
        if spell_effects:
            body["spell_effects"] = spell_effects
        return compile_card(CardModel.model_validate(body))

    COPY = {
        "op": "add_counters",
        "counter": {"binding": "counter"},
        "amount": {"binding": "amount"},
        "objects": {"self_only": True},
    }

    def test_on_a_counter_placed_trigger_it_loads(self):
        self._card(
            {
                "kind": "triggered",
                "trigger": {"event": "counter_placed", "controller": "any", "put_by": "you"},
                "effects": [self.COPY],
            }
        )

    def test_on_another_trigger_it_is_refused(self):
        with pytest.raises(DslError, match="counter_placed trigger"):
            self._card(
                {"kind": "triggered", "trigger": {"event": "self_enters"}, "effects": [self.COPY]}
            )

    def test_nested_under_may_on_another_trigger_is_refused(self):
        with pytest.raises(DslError, match="counter_placed trigger"):
            self._card(
                {
                    "kind": "triggered",
                    "trigger": {"event": "self_enters"},
                    "effects": [{"op": "may", "effects": [self.COPY]}],
                }
            )

    def test_on_a_spell_it_is_refused(self):
        with pytest.raises(DslError, match="a spell has no trigger"):
            self._card(spell_effects=[{**self.COPY, "objects": {"zone": "battlefield"}}])

    def test_another_binding_name_is_refused(self):
        with pytest.raises(DslError, match="a counter kind is a string"):
            self._card(
                {
                    "kind": "triggered",
                    "trigger": {"event": "counter_placed"},
                    "effects": [{**self.COPY, "counter": {"binding": "amount"}}],
                }
            )

    def test_on_another_op_it_is_refused(self):
        with pytest.raises(DslError, match="a counter kind is a string"):
            self._card(
                {
                    "kind": "triggered",
                    "trigger": {"event": "counter_placed"},
                    "effects": [
                        {
                            "op": "remove_counters",
                            "counter": {"binding": "counter"},
                            "amount": {"const": 1},
                            "objects": {"self_only": True},
                        }
                    ],
                }
            )
