"""Granting a *static* ability with the one-shot op.

    "If you do, it gains equip {3} and **"Equipped creature gets +3/+3"** and
    loses all other abilities."                          -- The Irencrag

The `grant_ability` op could hand over an activated ability (Urza's Saga) or a
triggered one (Clavileño), and the loader refused it a **static** outright. The
refusal gave its reason: the op's grants "are pointers that the characteristics
pipeline never reads, so granting the static … with it would do nothing --
a continuous grant is the `grant_ability` **static**".

The premise was true and is no longer. `abilities_of` appends what
`_op_granted_abilities` returns, `_battlefield_statics` reads `abilities_of`, so
a static put on that list joins the characteristics pipeline with no new walk at
all -- the function simply had to stop filtering statics out.

And the continuous form is not a substitute here, which is why this had to be
the op: a `grant_ability` **static** on The Irencrag applies from the moment the
artifact enters, so it would hand out +3/+3 on turn one with no transformation
and no equip. The clause is a thing that happens *once*, when the player says
yes, and stays.

An op-granted **triggered** ability is still kept off the derived list -- and
that is a fact about `_op_granted_abilities`, not a refusal at load:
`triggers.collect` already yields one off the grant record itself, so listing it
here too would fire it twice.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, Step
from automtg.engine.zones import destroy
from tests.conftest import only_oid, pass_until

CRAG = "t_gso_crag"  # grants itself an anthem as it enters
PLAIN = "t_gso_plain"  # the same grantable, never granted
BEAR = "t_gso_bear"  # a 2/2 for the anthem to pump


def position(builder, artifact: str):
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4)
        .battlefield(0, [BEAR])
        .hand(0, [artifact])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == artifact
    )
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
    return game


def bear_pt(game) -> tuple[int, int]:
    c = chars(game.state, only_oid(game, BEAR))
    return c.power, c.toughness


class TestTheGrantedStaticApplies:
    def test_the_anthem_pumps(self, builder):
        """The whole capability. Loading was never the hard part -- this is the
        assertion the old refusal said could not be made."""
        game = position(builder, CRAG)
        assert bear_pt(game) == (5, 5)

    def test_without_the_grant_it_does_not(self, builder):
        """The control: the same grantable ability, never handed over."""
        game = position(builder, PLAIN)
        assert bear_pt(game) == (2, 2)


class TestItIsTheGrantAndNotThePrintedCard:
    def test_the_granter_keeps_no_printed_anthem(self, builder):
        """`grantable_abilities` are not abilities the card *has* -- so if the
        anthem were being read off the printed face rather than off the grant,
        the control above would pump too."""
        game = position(builder, PLAIN)
        assert bear_pt(game) == (2, 2)

    def test_the_grant_dies_with_the_granter(self, builder):
        """The record lives on the permanent that was granted -- here the
        artifact itself -- and `reset_permanent_state` clears it on the way out
        (400.7), so the anthem goes with it."""
        game = position(builder, CRAG)
        assert bear_pt(game) == (5, 5)
        destroy(game.state, only_oid(game, CRAG))
        game.state.bump_chars()
        assert bear_pt(game) == (2, 2)
