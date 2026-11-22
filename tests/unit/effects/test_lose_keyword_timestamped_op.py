"""The `lose_keyword_timestamped` op -- "nonland permanents your opponents
control **lose indestructible until end of turn**".

Exterminatus is the witness: "…lose indestructible until end of turn. Destroy
all nonland permanents." The first sentence is what makes the second one a
one-sided wrath, and three rules decide its shape.

**613.7, which grant wins.** A plain "loses X" is a layer-6 removal ordered by
timestamp among the effects that grant X. The printed keyword goes, and so does
every grant older than the removal; a grant made *after* it gives the keyword
back. The near miss is the `lose_keyword` op, Arcane Lighthouse's "lose X **and
can't have X**", which beats every grant whatever its timestamp: written with
it, an opponent's Heroic Intervention in response to nothing -- cast after the
loss, in the same turn -- would do nothing, which is a stronger card.
`TestANewerGrantGivesItBack` and `TestAnOlderGrantDoesNot` are the two halves.

**611.2c, which set it reaches.** A resolved effect that changes
characteristics reaches only the objects on the battlefield as it resolved, so a
permanent that arrives afterwards keeps its keyword. The `lose_keyword_timestamped`
static, read off its filter on every recompute, would get that wrong; this op
writes an entry onto each permanent it found.

**Until end of turn.** The entry rides `until_eot`: cleanup ends it, and a zone
change (400.7) drops it with the old object.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Keyword, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, clear_until_eot
from commanderblitz.engine.zones import move_object
from tests.conftest import keywords, only_oid

INDESTRUCTIBLE_GOLEM = "t_indestructible"  # 2/2 with indestructible printed
FLIER = "t_flier"  # 2/2 with flying printed
BEAR = "t_bear"  # 2/2 vanilla
FLY_ANTHEM = "t_flying_anthem"  # "Creatures you control have flying."
INDESTRUCTIBLE = Keyword.INDESTRUCTIBLE.value
FLYING = Keyword.FLYING.value

NONLAND = {"zone": "battlefield", "not_types": ["Land"], "count": "all"}

#: Exterminatus's first sentence, as the card writes it.
LOSS = {
    "op": "lose_keyword_timestamped",
    "keywords": [INDESTRUCTIBLE],
    "objects": {**NONLAND, "controller": "opponent"},
}
#: …and its second.
WRATH = {"op": "destroy", "objects": {**NONLAND, "controller": "any"}}


def position(builder, mine=(INDESTRUCTIBLE_GOLEM,), theirs=(INDESTRUCTIBLE_GOLEM, BEAR), hand=()):
    """Player 0 casts Exterminatus; player 1 is the opponent.

    Returns ``(game, oid)`` with ``oid`` player 1's first permanent in
    ``theirs`` -- by default the indestructible Golem.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["plains", *mine])
        .battlefield(1, ["plains", *theirs])
        .hand(1, list(hand))
        .build(advance=False)
    )
    return game, only_oid(game, theirs[0], 1)


def run(game, *specs: dict, controller: int = 0) -> None:
    ctx = EffectContext(state=game.state, controller=controller, source_oid=None)
    gen = execute(ctx, list(specs))
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def grant(oid: int, keyword: str = INDESTRUCTIBLE) -> dict:
    return {"op": "grant_keyword", "keywords": [keyword], "objects": {"oid": oid}}


def loses(oid: int, keyword: str = INDESTRUCTIBLE) -> dict:
    return {"op": "lose_keyword_timestamped", "keywords": [keyword], "objects": {"oid": oid}}


def on_battlefield(game, oid: int) -> bool:
    return game.state.objects[oid].zone == Zone.BATTLEFIELD


class TestItTakesTheKeyword:
    def test_the_opponents_permanents_lose_it(self, builder):
        game, golem = position(builder)
        run(game, LOSS)
        assert INDESTRUCTIBLE not in keywords(game, golem)

    def test_its_own_side_keeps_it(self, builder):
        game, _ = position(builder)
        run(game, LOSS)
        assert INDESTRUCTIBLE in keywords(game, only_oid(game, INDESTRUCTIBLE_GOLEM, 0))

    def test_it_takes_only_what_it_names(self, builder):
        game, _ = position(builder, theirs=(FLIER,))
        flier = only_oid(game, FLIER, 1)
        run(game, LOSS)
        assert FLYING in keywords(game, flier)

    def test_exterminatus_is_a_one_sided_wrath(self, builder):
        """What the card is for: the destroy reads the derived keyword."""
        game, golem = position(builder)
        mine = only_oid(game, INDESTRUCTIBLE_GOLEM, 0)
        bear = only_oid(game, BEAR, 1)
        run(game, LOSS, WRATH)

        assert not on_battlefield(game, golem)
        assert not on_battlefield(game, bear)
        assert on_battlefield(game, mine)
        assert on_battlefield(game, only_oid(game, "plains", 1)), "lands are spared"

    def test_without_the_loss_the_wrath_spares_it(self, builder):
        """Pins that the first sentence is what kills the Golem."""
        game, golem = position(builder)
        run(game, WRATH)
        assert on_battlefield(game, golem)


class TestANewerGrantGivesItBack:
    """613.7: a grant made after the removal survives it -- the claim that
    separates this op from the `lose_keyword` prohibition."""

    def test_a_later_grant_keyword(self, builder):
        game, golem = position(builder)
        run(game, LOSS)
        run(game, grant(golem), controller=1)
        assert INDESTRUCTIBLE in keywords(game, golem)

    def test_a_later_keyword_counter(self, builder):
        game, golem = position(builder)
        run(game, LOSS)
        add_counters(game.state, golem, INDESTRUCTIBLE, 1)
        assert INDESTRUCTIBLE in keywords(game, golem)

    def test_an_anthem_that_arrives_later(self, builder):
        game, _ = position(builder, theirs=(BEAR,), hand=(FLY_ANTHEM,))
        bear = only_oid(game, BEAR, 1)
        run(game, loses(bear, FLYING))
        anthem = next(
            o for o in game.state.players[1].hand if game.state.objects[o].def_id == FLY_ANTHEM
        )
        move_object(game.state, anthem, Zone.BATTLEFIELD)
        assert FLYING in keywords(game, bear)


class TestAnOlderGrantDoesNot:
    """The other half: a removal that only took the printed keyword would be
    the weaker card."""

    def test_an_earlier_grant_keyword_is_taken(self, builder):
        game, _ = position(builder, theirs=(BEAR,))
        bear = only_oid(game, BEAR, 1)
        run(game, grant(bear), controller=1)
        run(game, LOSS)
        assert INDESTRUCTIBLE not in keywords(game, bear)

    def test_an_anthem_already_there_is_overridden(self, builder):
        game, _ = position(builder, theirs=(BEAR, FLY_ANTHEM))
        bear = only_oid(game, BEAR, 1)
        assert FLYING in keywords(game, bear)
        run(game, loses(bear, FLYING))
        assert FLYING not in keywords(game, bear)

    def test_an_earlier_keyword_counter_is_taken(self, builder):
        game, _ = position(builder, theirs=(BEAR,))
        bear = only_oid(game, BEAR, 1)
        add_counters(game.state, bear, INDESTRUCTIBLE, 1)
        run(game, LOSS)
        assert INDESTRUCTIBLE not in keywords(game, bear)

    def test_a_second_loss_after_a_regrant_takes_it_again(self, builder):
        """The newest removal is the one compared."""
        game, golem = position(builder)
        run(game, LOSS)
        run(game, grant(golem), controller=1)
        run(game, LOSS)
        assert INDESTRUCTIBLE not in keywords(game, golem)


class TestTheSetIsFixedAsItResolves:
    """611.2c: only the objects on the battlefield as it resolved."""

    def test_a_permanent_that_arrives_later_keeps_it(self, builder):
        game, _ = position(builder, hand=(INDESTRUCTIBLE_GOLEM,))
        run(game, LOSS)
        late = next(
            o
            for o in game.state.players[1].hand
            if game.state.objects[o].def_id == INDESTRUCTIBLE_GOLEM
        )
        moved = move_object(game.state, late, Zone.BATTLEFIELD)
        assert INDESTRUCTIBLE in keywords(game, moved.oid)

    def test_a_blinked_permanent_is_a_new_object_with_it(self, builder):
        """400.7: the entry goes with the old object."""
        game, golem = position(builder)
        run(game, LOSS)
        move_object(game.state, golem, Zone.EXILE)
        back = move_object(game.state, golem, Zone.BATTLEFIELD)
        assert INDESTRUCTIBLE in keywords(game, back.oid)


class TestWearingOff:
    def test_it_ends_at_cleanup(self, builder):
        game, golem = position(builder)
        run(game, LOSS)
        clear_until_eot(game.state)
        assert INDESTRUCTIBLE in keywords(game, golem)

    def test_an_earlier_grant_is_back_with_it(self, builder):
        """The grant was read past, not deleted -- `chars` derives, it does not
        edit, so whatever outlasts the removal is there when it ends."""
        game, _ = position(builder, theirs=(BEAR,))
        bear = only_oid(game, BEAR, 1)
        game.state.objects[bear].granted_keywords.add(INDESTRUCTIBLE)
        game.state.bump_chars()
        run(game, LOSS)
        assert INDESTRUCTIBLE not in keywords(game, bear)
        clear_until_eot(game.state)
        assert INDESTRUCTIBLE in keywords(game, bear)


def _exterminatus(**overrides) -> CardModel:
    effect = {**LOSS, **overrides}
    effect = {k: v for k, v in effect.items() if v is not None}
    return CardModel.model_validate(
        {
            "id": "t_probe_exterminatus",
            "name": "Probe Exterminatus",
            "mana_cost": "{4}{B}{B}",
            "types": ["Sorcery"],
            "spell_effects": [effect, WRATH],
        }
    )


class TestTheLoaderRefuses:
    def test_the_printed_effect_loads(self):
        compile_card(_exterminatus())

    def test_cant_have(self):
        """"…and can't have X" is the prohibition, the `lose_keyword` op."""
        with pytest.raises(DslError, match="lose_keyword op"):
            compile_card(_exterminatus(cant_have=True))

    def test_no_keywords(self):
        with pytest.raises(DslError, match="keywords"):
            compile_card(_exterminatus(keywords=[]))

    def test_an_unknown_keyword(self):
        with pytest.raises(DslError, match="unknown keyword"):
            compile_card(_exterminatus(keywords=["indestructable"]))

    def test_a_numbered_keyword(self):
        with pytest.raises(DslError, match="numbered"):
            compile_card(_exterminatus(keywords=[Keyword.ANNIHILATOR.value]))

    def test_no_objects(self):
        with pytest.raises(DslError, match="objects"):
            compile_card(_exterminatus(objects=None))

    def test_a_longer_duration(self):
        with pytest.raises(DslError, match="duration"):
            compile_card(_exterminatus(duration="until_your_next_turn"))
