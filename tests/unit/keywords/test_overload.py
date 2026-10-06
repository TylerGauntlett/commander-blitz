"""Overload — the one cast variant that changes what the spell points at.

    "Overload {3}{R} (You may cast this spell for its overload cost. If you do,
    change its text by replacing all instances of "target" with "each".)"

Kicker, evoke, emerge, flashback and prowl all change what a spell **costs**.
Overload changes what it *does*, and it does it by rewriting a printed sentence —
which is not something an engine can do to data it was handed.

So the card writes both halves and branches on `{"overloaded": true}`, the same
shape `kicked` has. That is not a workaround: "destroy target artifact" and
"destroy each artifact" really are two different effects, one targeted and one
not, and the residual gate still sees one printed line implemented by one `if`.

The half that is easy to get wrong is **targets**. An overloaded spell is cast
with none at all, so:

- legality gives the overload line the empty target tuple rather than the
  enumerated ones;
- every target the card declares must be `optional`, or the overload line is
  offered and then never castable — silently, because the printed line still is.

And the flag is written onto the object *before* `spell_effects` run. Written
after, every overloaded spell resolves as the targeted half — with no targets,
which is nothing at all.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError
from tests.conftest import pass_until

MOUNTAIN = "mountain"
SHOCK = "t_overloader"     # {R}, overload {3}{R}
GIANT = "t_big"            # 6/6 -- survives 2 damage, so the mark is readable


def position(builder, lands: int):
    return (
        builder(players=2)
        .battlefield(0, [MOUNTAIN] * lands)
        .battlefield(0, [GIANT])
        .battlefield(1, [GIANT, GIANT])
        .hand(0, [SHOCK])
        .library(0, [MOUNTAIN] * 20)
        .library(1, [MOUNTAIN] * 20)
        .build()
    )


def lines(game):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == SHOCK
    ]


def creatures(game):
    return [o for o in game.state.objects.values() if o.def_id == GIANT]


class TestTheTwoCastLines:
    def test_only_the_printed_line_is_offered_cheaply(self, builder):
        game = position(builder, lands=1)
        assert lines(game), "the {R} line"
        assert not any(a.overloaded for a in lines(game))

    def test_the_overload_line_appears_with_the_mana_for_it(self, builder):
        game = position(builder, lands=4)
        assert any(a.overloaded for a in lines(game))

    def test_the_overload_line_carries_no_targets(self, builder):
        """702.96a replaces every "target" with "each" — there is nothing to point at."""
        game = position(builder, lands=4)
        overloaded = next(a for a in lines(game) if a.overloaded)
        assert overloaded.targets == ()

    def test_the_printed_line_still_targets(self, builder):
        game = position(builder, lands=4)
        plain = [a for a in lines(game) if not a.overloaded and a.targets]
        assert plain, "the targeted half is unchanged"


class TestWhatEachResolvesTo:
    def test_the_printed_line_hits_one_creature(self, builder):
        game = position(builder, lands=1)
        action = next(a for a in lines(game) if not a.overloaded and a.targets)
        victim = action.targets[0].id
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack)

        assert game.state.objects[victim].damage == 2
        others = [o for o in creatures(game) if o.oid != victim]
        assert all(o.damage == 0 for o in others), "only the target"

    def test_the_overload_line_hits_every_creature(self, builder):
        game = position(builder, lands=4)
        action = next(a for a in lines(game) if a.overloaded)
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack)

        assert all(o.damage == 2 for o in creatures(game)), "each, including yours"

    def test_the_flag_is_readable_during_spell_effects(self, builder):
        """Written after them, the branch reads False and the spell does nothing."""
        game = position(builder, lands=4)
        action = next(a for a in lines(game) if a.overloaded)
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack)

        assert sum(o.damage for o in creatures(game)) == 6, "three creatures, 2 each"


class TestTheLoaderGuards:
    def _card(self, **extra) -> CardModel:
        base = {
            "id": "t_overload_probe",
            "name": "Overload Probe",
            "mana_cost": "{R}",
            "types": ["Instant"],
            "targets": [
                {
                    "id": "t1",
                    "kind": "permanent",
                    "count": 1,
                    "optional": True,
                    "selector": {"zone": "battlefield", "types": ["Creature"]},
                }
            ],
            "spell_effects": [
                {
                    "op": "if",
                    "condition": {"overloaded": True},
                    "then": [{"op": "draw", "player": "you"}],
                    "else": [{"op": "draw", "player": "you"}],
                }
            ],
        }
        base.update(extra)
        return CardModel.model_validate(base)

    def test_a_well_formed_overload_loads(self):
        compile_card(self._card(overload="{3}{R}"))

    def test_a_cost_nothing_reads_is_refused(self):
        """A more expensive cast that does exactly the same thing."""
        with pytest.raises(DslError, match="no effect reads"):
            compile_card(
                self._card(
                    overload="{3}{R}",
                    spell_effects=[{"op": "draw", "player": "you"}],
                )
            )

    def test_reading_it_without_a_cost_is_refused(self):
        with pytest.raises(DslError, match="has no 'overload' cost"):
            compile_card(self._card())

    def test_a_required_target_is_refused(self):
        """The overload line would be offered and never castable."""
        with pytest.raises(DslError, match="must all be 'optional'"):
            compile_card(
                self._card(
                    overload="{3}{R}",
                    targets=[
                        {
                            "id": "t1",
                            "kind": "permanent",
                            "count": 1,
                            "selector": {"zone": "battlefield", "types": ["Creature"]},
                        }
                    ],
                )
            )
