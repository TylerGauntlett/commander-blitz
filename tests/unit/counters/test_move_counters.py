"""Graft and modular: moving counters from one permanent to another.

The census pairs these as "enters with counters, then moves them", and the
enters-with half had shipped long ago. What was missing was the move, and the
reason it is an op rather than `remove_counters` beside `add_counters` is
modular: it moves **all** of them, and the number is not knowable when the card
is written. Two ops would have to thread the count between them through a
binding that nothing sets.

Two clamps, both of which would otherwise create counters out of nothing:

**The amount is clamped to what is there.** A graft creature down to its last
counter moves one, not the two the card asked for.

**A move to nowhere takes nothing off the source.** With no legal destination
the counters stay put, which is what "move a +1/+1 counter from this creature
onto it" says when "it" is gone. Modular with no artifact creature to target
does not simply delete its counters.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, find_action, only_oid, plus_one_counters

MODULAR = "t_modular"  # 0/0 artifact creature, modular 3
GRAFTER = "t_grafter"  # 0/0, graft 2
BEAR = "t_bear"


def settle(game, *, say_yes: bool = False, limit: int = 30) -> None:
    for _ in range(limit):
        if not game.state.pending_triggers and not game.state.stack:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        if say_yes and decision.kind is DecisionKind.MAY:
            game.apply(find_action(game, ActionKind.YES))
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("nothing resolved")


class TestModular:
    def position(self, builder, *, heir: bool = True, start: int = 3):
        """A modular creature, and optionally a second one to inherit.

        The heir is another modular: "target **artifact creature**" needs one,
        and it needs a counter of its own or it is a 0/0 that dies on arrival.
        """
        b = builder(players=2).battlefield(0, [MODULAR], counters={"+1/+1": start})
        if heir:
            b = b.battlefield(0, [MODULAR], counters={"+1/+1": 1})
        game = b.build()
        dying, *rest = sorted(
            o.oid for o in game.state.battlefield_objects(0) if o.def_id == MODULAR
        )
        return game, dying, (rest[0] if rest else None)

    def test_the_counters_move_on_death(self, builder):
        game, mod, heir = self.position(builder)
        move_object(game.state, mod, Zone.GRAVEYARD)
        settle(game)
        assert plus_one_counters(game, heir) == 4, "its own one, plus the three it inherited"

    def test_all_of_them_move_without_the_card_saying_how_many(self, builder):
        """Why this is one op: the number is not knowable when the card is
        written, so the card reads `{"counters_had": "+1/+1"}` rather than 3."""
        game, mod, heir = self.position(builder, start=7)
        move_object(game.state, mod, Zone.GRAVEYARD)
        settle(game)
        assert plus_one_counters(game, heir) == 8

    def test_the_source_is_read_from_the_snapshot(self, builder):
        """`reset_permanent_state` empties the counters on the way to the
        graveyard, so by the time the trigger resolves the dead creature has
        none -- the same trap persist fell into. The count comes from the dies
        event's snapshot, and there is nothing left on the source to remove."""
        game, mod, _ = self.position(builder)
        move_object(game.state, mod, Zone.GRAVEYARD)
        assert plus_one_counters(game, mod) == 0, "wiped before the trigger sees anything"
        settle(game)

    def test_with_no_legal_target_nothing_happens(self, builder):
        game, mod, _ = self.position(builder, heir=False)
        move_object(game.state, mod, Zone.GRAVEYARD)
        settle(game)
        assert game.state.objects[mod].zone is Zone.GRAVEYARD


class TestMovingFromALiveSource:
    """The graft half: a source still on the battlefield, so the counters are
    really taken off it rather than read from a snapshot.

    Driven through `execute` rather than through the graft card's trigger. The
    card is in the pool and loads, but its "you may" wrapper does not resolve in
    a sandbox position -- a token created by hand queues its trigger in a window
    where nobody is about to receive priority, and it is dropped rather than put
    on the stack. That is a property of building positions by hand, not of this
    op, and chasing it here would test the sandbox instead of the mechanic.
    """

    def position(self, builder, *, start: int = 2):
        game = (
            builder(players=2)
            .battlefield(0, [GRAFTER], counters={"+1/+1": start})
            .battlefield(0, [BEAR])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        return game, only_oid(game, GRAFTER, 0), only_oid(game, BEAR, 0)

    def move(self, game, grafter: int, bear: int, **extra) -> None:
        import contextlib

        from commanderblitz.engine.effects import execute
        from commanderblitz.engine.effects.context import EffectContext

        ctx = EffectContext(state=game.state, controller=0, source_oid=grafter)
        ctx.bindings["dest"] = bear
        spec = {
            "op": "move_counters",
            "counter": "+1/+1",
            "objects": {"binding": "dest"},
            **extra,
        }
        gen = execute(ctx, [spec])
        with contextlib.suppress(StopIteration):
            while True:
                next(gen)

    def test_one_counter_moves_across(self, builder):
        game, grafter, bear = self.position(builder)
        self.move(game, grafter, bear, amount={"const": 1})
        assert plus_one_counters(game, grafter) == 1
        assert plus_one_counters(game, bear) == 1

    def test_the_default_moves_all_of_them(self, builder):
        game, grafter, bear = self.position(builder, start=4)
        self.move(game, grafter, bear)
        assert plus_one_counters(game, grafter) == 0
        assert plus_one_counters(game, bear) == 4

    def test_the_amount_is_clamped_to_what_is_there(self, builder):
        """Moving counters that do not exist would create them."""
        game, grafter, bear = self.position(builder, start=1)
        self.move(game, grafter, bear, amount={"const": 3})
        assert plus_one_counters(game, grafter) == 0
        assert plus_one_counters(game, bear) == 1, "one, not the three the card asked for"

    def test_an_empty_source_moves_nothing(self, builder):
        game, grafter, bear = self.position(builder, start=0)
        self.move(game, grafter, bear, amount={"const": 1})
        assert plus_one_counters(game, bear) == 0

    def test_the_graft_card_compiles(self, registry):
        card = registry.get(GRAFTER)
        (ability,) = [a for a in card.abilities if a.is_triggered]
        assert ability.trigger is not None
        assert ability.trigger.event == "permanent_enters"
        assert (ability.trigger.filter or {}).get("exclude_self") is True


class TestTheLoaderGuardsIt:
    def base(self, effect: dict) -> dict:
        return {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "x",
            "mana_cost": "{G}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "triggered",
                    "text": "x",
                    "trigger": {"event": "dies", "source": "self"},
                    "effects": [effect],
                }
            ],
        }

    def test_no_destination_is_refused(self):
        with pytest.raises(DslError, match="needs 'objects'"):
            compile_card(CardModel.model_validate(self.base({"op": "move_counters"})))

    def test_a_malformed_amount_is_refused(self):
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    self.base(
                        {
                            "op": "move_counters",
                            "objects": {"self_only": True},
                            "amount": {"nonsense": 1},
                        }
                    )
                )
            )

    def test_the_modular_card_compiles(self, registry):
        card = registry.get(MODULAR)
        (ability,) = [a for a in card.abilities if a.is_triggered]
        assert [e["op"] for e in ability.effects] == ["move_counters"]
