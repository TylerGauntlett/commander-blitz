"""A mana doubler on the other half of the board: "whenever you tap a **nonland**
permanent for mana, add one mana of any type that permanent produced".

    Kinnan, Bonder Prodigy -- the printed sentence Vorinclex, Voice of Hunger
    and Zendikar Resurgent already shipped as `double_land_mana`, with one word
    changed.

Rule 605.1b makes this a *mana ability* even though it is triggered: it triggers
off a mana ability and adds mana, and 605.4a resolves it immediately without
using the stack. So it cannot be a `triggered` ability here -- tapping for mana
happens inside cost payment, where nothing may be queued and nothing may stop to
ask -- and it is answered at the mana choke point beside `double_land_mana`.

What was wrong without this: `is_land` was computed inline at each of the three
places tapped mana is counted, and the static carried no permanent filter at
all, so "a land" was the only class the engine could say. There was no spelling
of Kinnan; written as `double_land_mana` he would have doubled every land and no
nonland permanent -- the exact complement of his printed line.

The three readers are `costs._sources_of` (the planner: what can I cast?),
`costs.activate_mana_ability` (the payment: what lands in the pool?) and
legality's chip label. The first two disagreeing is the failure that matters: a
spell offered on Kinnan mana and then paid for without it strands the cast
half-paid, so both are pinned here.

"One mana of any type that permanent produced" is `mana_produced`'s doubling and
is *not* a fixed colour: a rock that taps for {U} or {B} doubles whichever it
just made. The simplification recorded in docs/rules-coverage.md carries over --
a source with a choice doubles what it produced rather than offering a free
choice of type, because a mana ability cannot ask.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import activate_mana_ability, pay_mana
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import SYMBOL_INDEX, ManaCost
from tests.conftest import oids_of

KINNAN = "t_nonland_doubler"  # "whenever you tap a nonland permanent for mana"
TURN_KINNAN = "t_turn_kinnan"  # the same, gated on "as long as it's your turn"
VORINCLEX = "t_land_doubler"  # "whenever you tap a land for mana"
DORK = "t_dork"  # {T}: Add {G}.
ROCK = "t_bicolor_rock"  # {T}: Add {U} or {B}.
FOUR_DROP = "t_green_four_drop"

G = SYMBOL_INDEX["G"]
U = SYMBOL_INDEX["U"]
B = SYMBOL_INDEX["B"]


def position(builder, mine=(), theirs=(), *, hand=()):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .active(0)
        .build(advance=False)
    )


def tap(game, card_id: str, pid: int = 0, option: int = 0) -> list[int]:
    """Tap the first ``card_id`` ``pid`` controls for mana; return their pool."""
    oid = oids_of(game, card_id, pid)[0]
    activate_mana_ability(game.state, oid, 0, pid, option)
    return list(game.state.players[pid].mana_pool.amounts)


class TestTheNonlandHalf:
    def test_a_mana_creature_makes_two(self, builder):
        game = position(builder, [KINNAN, DORK])
        pool = tap(game, DORK)
        assert pool[G] == 2
        assert sum(pool) == 2

    def test_without_kinnan_it_makes_one(self, builder):
        game = position(builder, [DORK])
        assert tap(game, DORK)[G] == 1

    def test_an_artifact_counts_too(self, builder):
        """ "Nonland permanent", not "creature" -- a rock is one."""
        game = position(builder, [KINNAN, ROCK])
        assert tap(game, ROCK)[U] == 2


class TestALandIsNotDoubled:
    """The printed word is *nonland*, and the land doubler is a different card."""

    def test_a_forest_under_kinnan_makes_one(self, builder):
        game = position(builder, [KINNAN, "forest"])
        pool = tap(game, "forest")
        assert pool[G] == 1
        assert sum(pool) == 1

    def test_the_land_doubler_still_doubles_its_land(self, builder):
        """The shared static, unregressed: Vorinclex's own half is untouched."""
        game = position(builder, [VORINCLEX, "forest"])
        assert tap(game, "forest")[G] == 2

    def test_the_land_doubler_leaves_a_nonland_alone(self, builder):
        """And the complement: `double_land_mana` never reached a mana dork."""
        game = position(builder, [VORINCLEX, DORK])
        assert tap(game, DORK)[G] == 1

    def test_both_doublers_each_take_their_own_half(self, builder):
        game = position(builder, [KINNAN, VORINCLEX, DORK, "forest"])
        assert tap(game, DORK)[G] == 2
        assert tap(game, "forest")[G] == 4  # 2 from the dork + 2 from the Forest

    def test_neither_stacks_on_one_tap(self, builder):
        """A permanent is a land or it is not, so only one of the two applies."""
        game = position(builder, [KINNAN, VORINCLEX, "forest"])
        assert tap(game, "forest")[G] == 2


class TestAnyTypeThatPermanentProduced:
    """Not a fixed colour: whatever the source just made is what doubles."""

    def test_the_blue_mode_doubles_blue(self, builder):
        game = position(builder, [KINNAN, ROCK])
        pool = tap(game, ROCK, option=0)
        assert (pool[U], pool[B]) == (2, 0)

    def test_the_black_mode_doubles_black(self, builder):
        game = position(builder, [KINNAN, ROCK])
        pool = tap(game, ROCK, option=1)
        assert (pool[B], pool[U]) == (2, 0)

    def test_a_green_dork_never_yields_the_rocks_colours(self, builder):
        game = position(builder, [KINNAN, ROCK, DORK])
        pool = tap(game, DORK)
        assert pool[G] == 2
        assert sum(pool) == 2


class TestWhoseTapsCount:
    def test_an_opponents_dork_gets_nothing(self, builder):
        """ "Whenever **you** tap" -- `affects_player: you`."""
        game = position(builder, [KINNAN], [DORK])
        assert tap(game, DORK, pid=1)[G] == 1


class TestPlannerAndPaymentAgree:
    @staticmethod
    def offered(builder, board) -> bool:
        game = builder(players=2).battlefield(0, list(board)).hand(0, [FOUR_DROP]).active(0).build()
        return any(
            a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == FOUR_DROP
            for a in game.legal_actions()
        )

    def test_the_solver_pays_four_green_from_two_dorks(self, builder):
        game = position(builder, [KINNAN, DORK, DORK])
        assert pay_mana(game.state, 0, ManaCost.parse("{G}{G}{G}{G}").with_x(0))

    def test_without_kinnan_it_cannot(self, builder):
        game = position(builder, [DORK, DORK])
        assert not pay_mana(game.state, 0, ManaCost.parse("{G}{G}{G}{G}").with_x(0))

    def test_legality_offers_the_spell_the_doubled_mana_affords(self, builder):
        assert self.offered(builder, [KINNAN, DORK, DORK])

    def test_and_does_not_offer_it_without(self, builder):
        assert not self.offered(builder, [DORK, DORK])


class TestItWearsOff:
    def test_gone_with_its_source(self, builder):
        game = position(builder, [KINNAN, DORK])
        game.state.battlefield.remove(oids_of(game, KINNAN, 0)[0])
        game.state.bump_chars()
        assert tap(game, DORK)[G] == 1

    def test_the_condition_is_asked(self, builder):
        """An "as long as" clause beside a player-wide static must bite here too."""
        on = builder(players=2).battlefield(0, [TURN_KINNAN, DORK]).active(0).build(advance=False)
        assert tap(on, DORK)[G] == 2
        off = builder(players=2).battlefield(0, [TURN_KINNAN, DORK]).active(1).build(advance=False)
        assert tap(off, DORK)[G] == 1


def _card(**static) -> dict:
    ability = {
        "kind": "static",
        "text": "Whenever you tap a nonland permanent for mana, add one mana of any "
        "type that permanent produced.",
        "effect": "double_nonland_mana",
        "affects_player": "you",
    }
    ability.update(static)
    ability = {k: v for k, v in ability.items() if v is not None}
    return {
        "id": "t_bad_kinnan",
        "name": "Bad Kinnan",
        "oracle_text": ability["text"],
        "mana_cost": "{2}{G}{U}",
        "types": ["Creature"],
        "power": 2,
        "toughness": 2,
        "abilities": [ability],
    }


class TestTheLoader:
    """`affects` is not in the refusal list on purpose: it is ignored on every
    player-wide static here, `double_land_mana` included, and narrowing that is
    a change to the shared family rather than to this sentence."""

    def test_the_shape_loads(self):
        compile_card(CardModel.model_validate(_card()))

    @pytest.mark.parametrize(
        "change",
        [
            {"affects_player": None},
            {"tapped_permanent": {"types": ["Creature"]}},
            {"add_mana": "{G}"},
        ],
        ids=["no-affects-player", "tapped-permanent", "add-mana"],
    )
    def test_refused(self, change):
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(_card(**change)))
