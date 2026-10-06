"""Losing all abilities because an effect said so, once.

    "…you may have The Irencrag become a legendary Equipment artifact named
    Everflame, Heroes' Legacy. If you do, it gains equip {3} and "Equipped
    creature gets +3/+3" **and loses all other abilities**."
                                                        -- The Irencrag

`lose_all_abilities` existed only as a **static**, and a static is the wrong
shape for this line twice over. It is gathered off the printed face, so written
on The Irencrag it would strip "{T}: Add {C}" from the moment the artifact
entered -- before any legendary creature arrived and whether or not the player
ever said yes, which is a different and strictly worse card. And no
`static_condition_keys` clause can gate it, because the transformation it waits
for was not a fact the engine had a flag for at all.

So the fact goes on the **object**, read by `_derived_abilities` beside the
static -- the one place that decides what abilities a permanent has. The two
mean the same thing about the printed list and differ only in who is saying it
and for how long.

Two readers had to learn it and both would have been silently wrong: the fast
path in `abilities_of`, which returns the printed list outright when no static
and no op grant is in sight, and `_loses_abilities`, which answers the same
question for everything asking from outside the walk.

**Other** abilities: a grant applied in the same breath survives, because
`_derived_abilities` drops the *printed* list and appends the granted ones
after. That is what "loses all other abilities and gains …" says, and it is the
half a flag checked in the wrong place would get backwards.
"""

from __future__ import annotations

from automtg.engine.characteristics import abilities_of
from automtg.engine.enums import ActionKind, Step
from automtg.engine.zones import destroy
from tests.conftest import only_oid, pass_until

CRAG = "t_lao_crag"  # strips itself as it enters
GAINER = "t_lao_gainer"  # grants, then strips
PLAIN = "t_lao_plain"  # neither, the control


def position(builder, spell: str):
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4)
        .hand(0, [spell])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == spell
    )
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
    return game


def texts(game, card_id: str) -> list[str]:
    return [a.text for a in abilities_of(game.state, only_oid(game, card_id))]


class TestThePrintedAbilitiesGo:
    def test_the_mana_ability_is_gone(self, builder):
        game = position(builder, CRAG)
        assert not any("Add {C}" in t for t in texts(game, CRAG))

    def test_and_so_is_the_trigger_that_said_so(self, builder):
        """"all **other**" is about the grants, not about the sentence itself:
        the trigger has already resolved, and it is a printed ability like any
        other."""
        game = position(builder, CRAG)
        assert texts(game, CRAG) == []

    def test_the_permanent_is_still_there(self, builder):
        game = position(builder, CRAG)
        assert only_oid(game, CRAG) in game.state.battlefield


class TestTheControl:
    def test_an_unstripped_permanent_keeps_its_ability(self, builder):
        game = position(builder, PLAIN)
        assert any("Add {C}" in t for t in texts(game, PLAIN))


class TestGrantsSurvive:
    def test_the_granted_ability_is_kept(self, builder):
        """"loses all other abilities **and gains** …". The grant is applied in
        the same resolution and must outlive the strip."""
        game = position(builder, GAINER)
        assert any("Draw a card" in t for t in texts(game, GAINER))

    def test_while_the_printed_one_still_goes(self, builder):
        game = position(builder, GAINER)
        assert not any("Add {C}" in t for t in texts(game, GAINER))


class TestItWearsOffOnLeaving:
    def test_a_stripped_permanent_that_dies_gets_its_abilities_back(self, builder):
        """400.7: the object that comes back is a new one, and
        `reset_permanent_state` is where every other such fact is cleared."""
        game = position(builder, CRAG)
        oid = only_oid(game, CRAG)
        destroy(game.state, oid)
        assert game.state.objects[oid].lost_all_abilities is False
