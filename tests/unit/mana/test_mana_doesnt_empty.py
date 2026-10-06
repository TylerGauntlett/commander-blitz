"""Mana that survives step and phase boundaries until end of turn.

    "Whenever this creature or equipped creature attacks, add an amount of {G}
    equal to its power. **Until end of turn, you don't lose this mana as steps
    and phases end.**"                              -- Tanuki Transplanter

500.4 empties every mana pool as each step and phase ends, and `turn.advance`
did exactly that unconditionally. Mana added by an attack trigger therefore
lived until the end of the declare-attackers step and no longer -- one boundary
short of ever reaching the main phase the card is for.

**The pip carries it, not the player.** The printed sentence is about *this*
mana: a Tanuki attack promises nothing about the mana already floating from a
land tapped a moment earlier, and the two sit in the same pool. Recorded against
the player, the wrong mana would survive; recorded against the pip, the right
mana does. (Omnath and Upwelling *do* say it about all your mana -- and they say
it as a static, a different card and a different mechanism.)

**The turn, not a flag**, for `GameObject.drawn_turn`'s reason before it: a flag
would have to be cleared at the turn boundary, and mana that forgot to be
cleared is mana that never empties. A recorded turn compared against the current
one cannot go stale.

**Where "until end of turn" ends.** The cleanup step's `advance` is what ends
the turn, so `empty_all_mana_pools` spares persistent mana at every boundary but
that one. Sparing it there too would float the mana into the next turn's untap
step, which is the opponent's mana to have and not yours.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.mana import SYMBOL_INDEX, ManaPool

KEEP = "t_mde_keep"  # "Add {G}{G}." + the rider
PLAIN = "t_mde_plain"  # the same spell, no rider

GREEN = SYMBOL_INDEX["G"]


def position(builder, spell: str):
    """Player 0 in their precombat main phase, holding one {0} sorcery."""
    return (
        builder(players=2)
        .hand(0, [spell])
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def run_out_the_turn(game, card_id: str) -> None:
    """Cast the {0} sorcery and let the turn play itself out.

    Once the sorcery is cast nobody in this position holds a card or a
    permanent, so no player ever has an action but passing and a single `apply`
    carries the game from the cast into the next turn. That is exactly the span
    the rider is about -- every boundary 500.4 applies to is crossed inside this
    one call -- which is why the assertions below read the event trace rather
    than the live pool. `mana_emptied` *is* 500.4 happening, and it names the
    turn, the step and the amount; a pool read afterwards could only say that
    the mana had gone, never at which boundary.
    """
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)


def emptyings(game, pid: int = 0) -> list[tuple[int, str, int]]:
    """``(turn, step, amount)`` for every time ``pid``'s pool lost mana."""
    return [
        (e.turn, Step(e.step).name, e.data["amount"])
        for e in game.state.events
        if e.type == "mana_emptied" and e.player == pid
    ]


def boundaries_crossed(game) -> int:
    """How many steps ended during turn 1 -- how many times 500.4 applied."""
    return sum(1 for e in game.state.events if e.type == "step_ended" and e.turn == 1)


class TestThePoolKeepsTheRightPips:
    """`ManaPool.clear` in isolation, where the rule is easiest to read."""

    def test_a_persistent_pip_survives_its_own_turn(self):
        pool = ManaPool()
        pool.add("G", 2, persists_through_turn=7)
        assert pool.clear(keep_for_turn=7) == 0
        assert pool.amounts[GREEN] == 2

    def test_an_ordinary_pip_in_the_same_pool_does_not(self):
        """The reason the rider rides on the pip: one pool, two promises."""
        pool = ManaPool()
        pool.add("G", 2, persists_through_turn=7)
        pool.add("G", 3)
        assert pool.clear(keep_for_turn=7) == 3
        assert pool.amounts[GREEN] == 2

    def test_a_pip_from_a_previous_turn_does_not(self):
        """The wearing-off, with nothing to clear it: the comparison simply
        stops holding once the turn moves on."""
        pool = ManaPool()
        pool.add("G", 2, persists_through_turn=7)
        assert pool.clear(keep_for_turn=8) == 2
        assert pool.amounts[GREEN] == 0

    def test_an_unconditional_clear_takes_everything(self):
        """What the end of the turn does -- and what every other caller that
        wants a clean pool, a player losing the game say, still means."""
        pool = ManaPool()
        pool.add("G", 2, persists_through_turn=7)
        assert pool.clear() == 2
        assert pool.amounts[GREEN] == 0

    def test_the_tags_stay_in_step_with_the_amounts(self):
        """`spend` reads both, so a clear that emptied one and not the other
        would hand out mana whose pips no longer exist."""
        pool = ManaPool()
        pool.add("G", 2, persists_through_turn=7)
        pool.add("R", 1)
        pool.clear(keep_for_turn=7)
        assert [len(pips) for pips in pool.tags] == list(pool.amounts)


class TestAcrossAWholeTurn:
    def test_the_mana_is_lost_exactly_once(self, builder):
        """Not at the end of the main phase, not at the end of combat: once."""
        game = position(builder, KEEP)
        run_out_the_turn(game, KEEP)
        assert len(emptyings(game)) == 1

    def test_and_that_once_is_the_end_of_the_turn(self, builder):
        game = position(builder, KEEP)
        run_out_the_turn(game, KEEP)
        assert emptyings(game) == [(1, "CLEANUP", 2)]

    def test_all_of_it_was_still_there(self, builder):
        """The amount is the proof the mana survived rather than leaked: two
        green went in, two green were lost at the end."""
        game = position(builder, KEEP)
        run_out_the_turn(game, KEEP)
        assert emptyings(game)[0][2] == 2

    def test_it_crossed_several_boundaries_to_get_there(self, builder):
        """"as steps and phases end", plural. Without this the assertions above
        would also pass on a turn that happened to have one boundary."""
        game = position(builder, KEEP)
        run_out_the_turn(game, KEEP)
        assert boundaries_crossed(game) > 3


class TestWithoutTheRider:
    """The control. 500.4 still empties an ordinary pool at the first boundary,
    so the assertions above measure the rider and not the plumbing."""

    def test_the_mana_goes_at_the_first_boundary(self, builder):
        game = position(builder, PLAIN)
        run_out_the_turn(game, PLAIN)
        assert emptyings(game) == [(1, "PRECOMBAT_MAIN", 2)]


class TestTheLoaderPlacesIt:
    def _card(self, **extra):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Add {G}.",
                "mana_cost": "{G}",
                "types": ["Sorcery"],
                **extra,
            }
        )

    def test_a_well_formed_rider_loads(self):
        compile_card(
            self._card(
                spell_effects=[
                    {"op": "add_mana", "mana": "{G}", "persists_until_end_of_turn": True}
                ]
            )
        )

    def test_add_mana_per_takes_it_too(self):
        compile_card(
            self._card(
                spell_effects=[
                    {
                        "op": "add_mana_per",
                        "mana": "{G}",
                        "per": {"types": ["Creature"], "controller": "you"},
                        "persists_until_end_of_turn": True,
                    }
                ]
            )
        )

    def test_it_is_refused_on_any_other_op(self):
        """Ignored elsewhere, the card would print a promise nobody reads."""
        with pytest.raises(DslError, match="read only by add_mana"):
            compile_card(
                self._card(
                    spell_effects=[
                        {
                            "op": "draw",
                            "amount": {"const": 1},
                            "persists_until_end_of_turn": True,
                        }
                    ]
                )
            )

    def test_false_is_refused(self):
        """Ordinary mana is the default and says nothing, so a written `false`
        is somebody meaning something by it -- and there is nothing to mean."""
        with pytest.raises(DslError, match="the only value is true"):
            compile_card(
                self._card(
                    spell_effects=[
                        {"op": "add_mana", "mana": "{G}", "persists_until_end_of_turn": False}
                    ]
                )
            )

    def test_it_is_refused_inside_a_mana_ability(self):
        """A mana ability never runs its effects -- `activate_mana_ability` adds
        the parsed symbols itself, which is what keeps activation inside cost
        payment decision-free. The rider would be read by nobody, so the card is
        refused rather than quietly shipped a boundary short."""
        with pytest.raises(DslError, match="not read inside a mana ability"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "x",
                        "name": "X",
                        "oracle_text": "{T}: Add {G}.",
                        "types": ["Land"],
                        "abilities": [
                            {
                                "kind": "activated",
                                "text": "{T}: Add {G}.",
                                "is_mana_ability": True,
                                "cost": {"tap": True},
                                "effects": [
                                    {
                                        "op": "add_mana",
                                        "mana": "{G}",
                                        "persists_until_end_of_turn": True,
                                    }
                                ],
                            }
                        ],
                    }
                )
            )
