"""The Atraxa, Praetors' Voice deck: the Oaths, the lands and removal, the walker
finders and The Chain Veil.

Split from `test_atraxa_praetors_voice_deck.py`, which covers the counter engine
-- proliferate and counter doubling -- says why these files exist, and holds the
helpers this file shares. Each class is one card, and pins the near miss as well.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.cost_reduction import cost_reduction
from automtg.engine.enums import ActionKind, Step, Zone
from tests.cards.test_atraxa_praetors_voice_deck import (
    ANCHOR,
    ARTIFACT,
    BEAR,
    ENCHANTMENT,
    FOREST,
    ISLAND,
    KOR_ALLY,
    OTHER_WALKER,
    PLAINS,
    SWAMP,
    THIRD_WALKER,
    WALKER,
    WIZARD,
    activations,
    cast_at,
    cast_only,
    counters,
    loyalty,
    offers,
    plus_one,
    resolve,
    spell_targets,
    to_end_step,
    tokens,
)
from tests.conftest import (
    hand_ids,
    library_ids,
    oids_of,
    only_oid,
    pass_until,
)

# ----------------------------------------------------------------------
# the Oaths
# ----------------------------------------------------------------------


class TestOathOfGideon:
    """ "When Oath of Gideon enters, create two 1/1 white Kor Ally creature
    tokens." / "Each planeswalker you control enters with an additional loyalty
    counter on it."

    The static changes a *later* walker's arrival, and the near miss is the
    tempting implementation -- a counter replacement with an addend -- which
    would also add one to every +N loyalty cost. The printed card never does.
    """

    def oath_board(self, builder, *, active: int = 0):
        return (
            builder(players=2)
            .battlefield(0, ["oath_of_gideon", PLAINS, *[SWAMP] * 3])
            .battlefield(1, [PLAINS, *[SWAMP] * 3])
            .hand(0, [WALKER, ANCHOR])
            .hand(1, [WALKER, ANCHOR])
            .active(active)
            .step(Step.PRECOMBAT_MAIN)
            .max_turns(3)
            .build()
        )

    def test_it_makes_two_kor_allies(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [*[PLAINS] * 4])
            .battlefield(1, [PLAINS])
            .hand(0, ["oath_of_gideon", ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast_only(game, "oath_of_gideon")
        resolve(game)
        made = tokens(game, KOR_ALLY)

        assert len(made) == 2
        c = chars(game.state, made[0].oid)
        assert (c.power, c.toughness) == (1, 1)
        assert {"Kor", "Ally"} <= set(c.subtypes)

    def test_a_walker_you_cast_enters_with_one_more(self, builder):
        game = self.oath_board(builder)
        cast_only(game, WALKER)
        resolve(game)

        assert loyalty(game, only_oid(game, WALKER, 0)) == 5

    def test_but_its_plus_one_is_still_plus_one(self, builder):
        """5 -> 6, not 5 -> 7."""
        game = self.oath_board(builder)
        cast_only(game, WALKER)
        resolve(game)
        walker = only_oid(game, WALKER, 0)
        game.apply(plus_one(game, walker))
        resolve(game)

        assert loyalty(game, walker) == 6

    def test_an_opponents_walker_enters_with_its_printed_loyalty(self, builder):
        """ "Each planeswalker **you control**"."""
        game = self.oath_board(builder, active=1)
        cast_only(game, WALKER, pid=1)
        resolve(game)

        assert loyalty(game, only_oid(game, WALKER, 1)) == 4


class TestOathOfAjani:
    """ "When Oath of Ajani enters, put a +1/+1 counter on each creature you
    control." / "Planeswalker spells you cast cost {1} less to cast." """

    def test_it_counters_each_creature_you_control(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR, WIZARD, PLAINS, FOREST])
            .battlefield(1, [BEAR, PLAINS])
            .hand(0, ["oath_of_ajani", ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast_only(game, "oath_of_ajani")
        resolve(game)

        assert counters(game, only_oid(game, BEAR, 0)) == {"+1/+1": 1}
        assert counters(game, only_oid(game, WIZARD, 0)) == {"+1/+1": 1}, "each, not one"
        assert counters(game, only_oid(game, BEAR, 1)) == {}, "…you control"

    def discount_board(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["oath_of_ajani", PLAINS])
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )

    def discount(self, game, card_id: str, pid: int = 0) -> int:
        return cost_reduction(game.state, pid, game.state.registry.get(card_id))

    def test_a_planeswalker_spell_costs_one_less(self, builder):
        assert self.discount(self.discount_board(builder), WALKER) == 1

    def test_a_creature_spell_does_not(self, builder):
        """ "**Planeswalker** spells"."""
        assert self.discount(self.discount_board(builder), BEAR) == 0

    def test_an_opponents_walker_does_not(self, builder):
        """ "…you cast"."""
        assert self.discount(self.discount_board(builder), WALKER, pid=1) == 0

    def priced(self, builder, *, oath: bool):
        return (
            builder(players=2)
            .battlefield(0, [SWAMP, SWAMP] + (["oath_of_ajani"] if oath else []))
            .hand(0, [WALKER])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

    def test_the_discount_is_charged_at_the_boundary(self, builder):
        """{2}{B} less {1} is {1}{B}: two Swamps."""
        assert WALKER in offers(self.priced(builder, oath=True), 0, ActionKind.CAST)

    def test_and_without_it_two_swamps_are_a_land_short(self, builder):
        assert WALKER not in offers(self.priced(builder, oath=False), 0, ActionKind.CAST)


class TestOathOfNissa:
    """ "When Oath of Nissa enters, look at the top three cards of your library.
    You may reveal a creature, land, or planeswalker card from among them and put
    it into your hand. Put the rest on the bottom of your library in any order."
    / "You may spend mana as though it were mana of any color to cast
    planeswalker spells." """

    def dig(self, builder, library):
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS, FOREST])
            .battlefield(1, [PLAINS])
            .hand(0, ["oath_of_nissa", ANCHOR])
            .hand(1, [ANCHOR])
            .library(0, list(library))
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast_only(game, "oath_of_nissa")
        top = game.state.players[0].library[:3]
        resolve(game, targets=top)
        return game

    def test_it_takes_a_planeswalker(self, builder):
        game = self.dig(builder, [ANCHOR, WALKER, ANCHOR, *[PLAINS] * 6])

        assert WALKER in hand_ids(game)
        assert library_ids(game)[-2:] == [ANCHOR, ANCHOR], "the rest to the bottom"

    def test_it_takes_a_creature(self, builder):
        game = self.dig(builder, [BEAR, ANCHOR, ANCHOR, *[PLAINS] * 6])

        assert BEAR in hand_ids(game)

    def test_an_instant_is_not_offered(self, builder):
        """ "a creature, land, or planeswalker card"."""
        game = self.dig(builder, [ANCHOR, ANCHOR, ANCHOR, *[ISLAND] * 6])

        assert hand_ids(game).count(ANCHOR) == 1, "only the anchor it started with"
        assert library_ids(game)[-3:] == [ANCHOR] * 3

    def test_it_looks_at_three_and_no_further(self, builder):
        game = self.dig(builder, [ANCHOR, ANCHOR, ANCHOR, WALKER, *[PLAINS] * 5])

        assert WALKER not in hand_ids(game)
        assert library_ids(game)[0] == WALKER

    def priced(self, builder, *, oath: bool, card: str):
        return (
            builder(players=2)
            .battlefield(0, [FOREST] * 3 + (["oath_of_nissa"] if oath else []))
            .hand(0, [card])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

    def test_green_mana_casts_a_black_planeswalker(self, builder):
        assert WALKER in offers(self.priced(builder, oath=True, card=WALKER), 0, ActionKind.CAST)

    def test_and_without_it_it_cannot(self, builder):
        assert WALKER not in offers(self.priced(builder, oath=False, card=WALKER), 0, ActionKind.CAST)

    def test_the_any_color_mana_is_only_for_planeswalkers(self, builder):
        """ "…to cast **planeswalker** spells" -- a {W} instant still needs white."""
        assert ANCHOR not in offers(self.priced(builder, oath=True, card=ANCHOR), 0, ActionKind.CAST)


# ----------------------------------------------------------------------
# lands and removal
# ----------------------------------------------------------------------


class TestRuptureSpire:
    """ "This land enters tapped." / "When this land enters, sacrifice it unless
    you pay {1}." / "{T}: Add one mana of any color." """

    def play(self, builder, *, lands=(PLAINS,), pay: bool):
        game = (
            builder(players=2)
            .battlefield(0, list(lands))
            .battlefield(1, [PLAINS])
            .hand(0, ["rupture_spire", ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.PLAY_LAND
                and game.state.objects[a.source].def_id == "rupture_spire"
            )
        )
        resolve(game, yes=pay)
        return game

    def test_paying_keeps_it_and_it_entered_tapped(self, builder):
        game = self.play(builder, pay=True)
        spire = only_oid(game, "rupture_spire", 0)

        assert game.state.objects[spire].tapped
        assert game.state.objects[only_oid(game, PLAINS, 0)].tapped, "the {1} was paid"

    def test_declining_sacrifices_it(self, builder):
        game = self.play(builder, pay=False)

        assert oids_of(game, "rupture_spire", 0) == []
        assert "rupture_spire" in [
            game.state.objects[o].def_id for o in game.state.players[0].graveyard
        ]

    def test_with_nothing_to_pay_with_it_is_sacrificed(self, builder):
        game = self.play(builder, lands=(), pay=True)

        assert oids_of(game, "rupture_spire", 0) == []

    def priced(self, builder, card: str):
        return (
            builder(players=2)
            .battlefield(0, ["rupture_spire"])
            .hand(0, [card])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

    def test_it_taps_for_white(self, builder):
        assert ANCHOR in offers(self.priced(builder, ANCHOR), 0, ActionKind.CAST)

    def test_and_for_blue(self, builder):
        """A second colour, so "any color" is not one hard-coded colour."""
        game = (
            builder(players=2)
            .battlefield(0, ["rupture_spire", PLAINS])
            .hand(0, ["contentious_plan"])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

        assert "contentious_plan" in offers(game, 0, ActionKind.CAST)


class TestPutrefy:
    """ "Destroy target artifact or creature. It can't be regenerated." """

    def board(self, builder):
        return (
            builder(players=2)
            .battlefield(0, [PLAINS, SWAMP, FOREST, FOREST])
            .battlefield(1, [BEAR, ARTIFACT, ENCHANTMENT, WALKER, "t_regenerator", FOREST])
            .hand(0, ["putrefy", ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .max_turns(3)
            .build()
        )

    def test_it_targets_artifacts_and_creatures_only(self, builder):
        game = self.board(builder)
        legal = spell_targets(game, "putrefy")

        assert only_oid(game, BEAR, 1) in legal
        assert only_oid(game, ARTIFACT, 1) in legal
        assert only_oid(game, ENCHANTMENT, 1) not in legal
        assert only_oid(game, WALKER, 1) not in legal

    def test_it_destroys_an_artifact(self, builder):
        game = self.board(builder)
        ring = only_oid(game, ARTIFACT, 1)
        cast_at(game, "putrefy", ring)
        resolve(game)

        assert game.state.objects[ring].zone is Zone.GRAVEYARD

    def test_a_regeneration_shield_does_not_save_it(self, builder):
        """The opponent regenerates in response, and the troll dies anyway."""
        game = self.board(builder)
        troll = only_oid(game, "t_regenerator", 1)
        cast_at(game, "putrefy", troll)
        pass_until(game, lambda g: g.pending() is not None and g.pending().player == 1)
        regen = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == troll
        )
        game.apply(regen)
        pass_until(
            game,
            lambda g: g.state.objects[troll].regeneration_shields > 0
            or g.state.objects[troll].zone is not Zone.BATTLEFIELD,
        )
        assert game.state.objects[troll].regeneration_shields == 1, "the premise: a shield"
        resolve(game)

        assert game.state.objects[troll].zone is Zone.GRAVEYARD


class TestFracture:
    """ "Destroy target artifact, enchantment, or planeswalker." """

    def board(self, builder):
        return (
            builder(players=2)
            .battlefield(0, [PLAINS, PLAINS, SWAMP])
            .battlefield(1, [BEAR, ARTIFACT, ENCHANTMENT, WALKER, PLAINS])
            .hand(0, ["fracture", ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_it_targets_all_three_and_not_a_creature(self, builder):
        game = self.board(builder)
        legal = spell_targets(game, "fracture")

        assert {
            only_oid(game, ARTIFACT, 1),
            only_oid(game, ENCHANTMENT, 1),
            only_oid(game, WALKER, 1),
        } <= legal
        assert only_oid(game, BEAR, 1) not in legal

    def test_it_destroys_a_planeswalker(self, builder):
        game = self.board(builder)
        walker = only_oid(game, WALKER, 1)
        cast_at(game, "fracture", walker)
        resolve(game)

        assert game.state.objects[walker].zone is Zone.GRAVEYARD


# ----------------------------------------------------------------------
# finding planeswalkers
# ----------------------------------------------------------------------


class TestCallTheGatewatch:
    """ "Search your library for a planeswalker card, reveal it, put it into your
    hand, then shuffle." """

    def search(self, builder, library):
        game = (
            builder(players=2)
            .battlefield(0, [*[PLAINS] * 3])
            .battlefield(1, [PLAINS])
            .hand(0, ["call_the_gatewatch", ANCHOR])
            .hand(1, [ANCHOR])
            .library(0, list(library))
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast_only(game, "call_the_gatewatch")
        resolve(game, targets=list(game.state.players[0].library))
        return game

    def test_it_finds_a_planeswalker(self, builder):
        game = self.search(builder, [BEAR, ARTIFACT, WALKER, *[PLAINS] * 5])

        assert WALKER in hand_ids(game)
        assert WALKER not in library_ids(game)

    def test_it_finds_nothing_else(self, builder):
        """ "a **planeswalker** card"."""
        game = self.search(builder, [BEAR, ARTIFACT, *[PLAINS] * 5])

        assert BEAR not in hand_ids(game)
        assert ARTIFACT not in hand_ids(game)
        assert len(game.state.players[0].library) == 7


class TestDeployTheGatewatch:
    """ "Look at the top seven cards of your library. Put up to two planeswalker
    cards from among them onto the battlefield. Put the rest on the bottom of
    your library in a random order." """

    def deploy(self, builder, library):
        game = (
            builder(players=2)
            .battlefield(0, [*[PLAINS] * 6])
            .battlefield(1, [PLAINS])
            .hand(0, ["deploy_the_gatewatch", ANCHOR])
            .hand(1, [ANCHOR])
            .library(0, list(library))
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast_only(game, "deploy_the_gatewatch")
        top = game.state.players[0].library[:7]
        resolve(game, targets=top)
        return game

    def test_up_to_two_walkers_enter_with_their_loyalty(self, builder):
        game = self.deploy(
            builder,
            [WALKER, BEAR, OTHER_WALKER, THIRD_WALKER, PLAINS, PLAINS, PLAINS, ISLAND, ISLAND],
        )
        arrived = [
            o for o in game.state.battlefield_objects(0)
            if o.def_id in (WALKER, OTHER_WALKER, THIRD_WALKER)
        ]

        assert len(arrived) == 2, "up to **two**, with three on offer"
        assert all(o.counter("loyalty") > 0 for o in arrived)
        left = [d for d in library_ids(game) if d in (WALKER, OTHER_WALKER, THIRD_WALKER)]
        assert len(left) == 1, "the third went to the bottom"

    def test_the_rest_go_to_the_bottom(self, builder):
        game = self.deploy(
            builder,
            [WALKER, BEAR, PLAINS, PLAINS, PLAINS, PLAINS, PLAINS, ISLAND, ISLAND],
        )

        assert oids_of(game, WALKER, 0), "the walker came in"
        assert oids_of(game, BEAR, 0) == [], "a creature is not a planeswalker"
        assert library_ids(game)[:2] == [ISLAND, ISLAND], "the six seen are under the unseen two"

    def test_it_looks_at_seven_and_no_further(self, builder):
        game = self.deploy(builder, [*[PLAINS] * 7, WALKER, ISLAND])

        assert oids_of(game, WALKER, 0) == []
        assert library_ids(game)[0] == WALKER


# ----------------------------------------------------------------------
# The Chain Veil
# ----------------------------------------------------------------------


class TestTheChainVeil:
    """ "At the beginning of your end step, if you didn't activate a loyalty
    ability of a planeswalker this turn, you lose 2 life." / "{4}, {T}: For each
    planeswalker you control, you may activate one of its loyalty abilities once
    this turn as though none of its loyalty abilities have been activated this
    turn."

    An end-step trigger with an intervening if, and an activated ability that
    changes what is offered *afterwards*: both invisible to the gate.
    """

    def board(self, builder, *, ender: int = 0, step=Step.PRECOMBAT_MAIN):
        game = (
            builder(players=2)
            .battlefield(0, ["the_chain_veil", WALKER, PLAINS, *[SWAMP] * 4])
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(ender)
            .step(step)
            .max_turns(6)
            .build()
        )
        return game, only_oid(game, "the_chain_veil", 0), only_oid(game, WALKER, 0)

    def test_no_loyalty_activation_costs_two_life(self, builder):
        game, _veil, _walker = self.board(builder, step=Step.POSTCOMBAT_MAIN)
        life = game.state.players[0].life
        to_end_step(game, 0)
        resolve(game)

        assert game.state.players[0].life == life - 2

    def test_a_loyalty_activation_avoids_it(self, builder):
        """+1 gains 2, and the Veil takes nothing back."""
        game, _veil, walker = self.board(builder)
        life = game.state.players[0].life
        game.apply(plus_one(game, walker))
        resolve(game)
        to_end_step(game, 0)
        resolve(game)

        assert game.state.players[0].life == life + 2

    def test_nothing_at_an_opponents_end_step(self, builder):
        """ "your end step"."""
        game, _veil, _walker = self.board(builder, ender=1, step=Step.POSTCOMBAT_MAIN)
        life = game.state.players[0].life
        to_end_step(game, 1)
        resolve(game)

        assert game.state.players[0].life == life

    def test_a_second_activation_is_not_offered_without_it(self, builder):
        """606.3, the control for the next test."""
        game, _veil, walker = self.board(builder)
        game.apply(plus_one(game, walker))
        resolve(game)

        assert activations(game, walker) == []

    def test_the_veil_grants_one_more_loyalty_activation(self, builder):
        game, veil, walker = self.board(builder)
        game.apply(plus_one(game, walker))
        resolve(game)
        game.apply(activations(game, veil)[0])
        resolve(game)

        assert game.state.objects[veil].tapped
        game.apply(plus_one(game, walker))
        resolve(game)
        assert loyalty(game, walker) == 6

    def test_and_only_one(self, builder):
        """ "once this turn" -- the third is not offered."""
        game, veil, walker = self.board(builder)
        game.apply(plus_one(game, walker))
        resolve(game)
        game.apply(activations(game, veil)[0])
        resolve(game)
        game.apply(plus_one(game, walker))
        resolve(game)

        assert activations(game, walker) == []
