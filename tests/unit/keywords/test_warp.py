"""Warp: a cheaper cast now, the permanent exiled tonight, and the card back later.

    Warp {1}{R} (You may cast a card from your hand for its warp cost. Exile
    that permanent at the beginning of the next end step, then you may cast it
    from exile on a later turn.)

Three claims, and each is its own way to get the mechanic wrong.

**It is an alternative cost, not a discount.** 601.2b replaces the printed
price; `spell_cost_reduction` is clamped by `cost_reduction.cost_reduction` to the
*generic* part of a cost, so no reduction ever reaches a coloured pip and a
"{2}{R} off" version would misprice every card it touched. The permanent that
arrives is an ordinary one -- warp buys the cheap cast, not a smaller creature.

**The permanent is exiled, not sacrificed and not bounced.** Evoke is the
nearest shipped alternative cost and it buys a sacrifice written on the card's
own trigger. Warp's exile is written nowhere: the printed card says only
"Warp {1}{R}", so an author has no sentence to hang a `delayed_trigger` ability
on and the residual gate would reject one written anyway. The engine owes it,
scoped to the object that entered, at the beginning of the **next** end step --
so a creature warped in a main phase spends the turn on the battlefield and
attacks, which foretell and suspend (which exile from hand *first*) never give
it.

**It comes back on a later turn, not this one.** `playable_duration:
"later_turns"` is plot's span and its start is the point: the turn the
permission was granted on is the one turn the card may not be cast. Rebound is
the only other rider that casts something again later and it is instants and
sorceries cast from hand, recast on your very next upkeep.

And the grant is a fourth claim of its own. "Artifact cards and red creature
cards in your hand have warp {2}{R}" (Tannuk, Steadfast Second) is a static on
*another permanent* handing a card-level price to cards nobody can point at yet,
and the scope is a **union of two printed shapes**. Written as one ANDed filter
it would mean "red artifact creature"; written as `any_types` it would let a
blue creature card through. `any_of` is the only spelling that says what is
printed, and the blue creature below is how that is measured.

Witness: Tannuk, Steadfast Second
(`tannuk_steadfast_second` in `data/cards/auto/`), whose second line is
the whole of the grant.
"""

from __future__ import annotations

import pytest

from automtg.cards.schema import AbilityModel, CardModel
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.errors import DslError
from tests.conftest import pass_until

MARSHAL = "t_warp_marshal"  # grants warp {2}{R} to artifact cards and red creature cards
BAUBLE = "t_scrap_bauble"  # {5} Artifact -- the first branch of the union
LANCER = "t_ember_lancer"  # {4}{R}{R} red Creature -- the second branch
SCRIBE = "t_tide_scribe"  # {4}{U}{U} blue Creature -- neither branch
HULK = "t_warped_hulk"  # {5}{R} Creature printing "Warp {1}{R}" itself


def board(builder, *, hand=(), lands=8, islands=0, marshal=True, marshal_seat=0, library=()):
    """Player 0 on eight Mountains, with the granter out unless told otherwise.

    The seat always holds something playable: a position whose active player has
    no play at all auto-advances out of the main phase before a test can look at
    it, so every caller passes a hand and `board` never leaves one empty.
    """
    b = (
        builder(players=2)
        .hand(0, list(hand))
        .battlefield(0, ["mountain"] * lands + ["island"] * islands)
        .hand(1, ["forest"])
        .library(0, list(library) + ["forest"] * 30)
        .library(1, ["forest"] * 30)
    )
    if marshal:
        b = b.battlefield(marshal_seat, [MARSHAL])
    return b.build()


def casts(game, card_id, pid=0):
    """Every cast line legality offers for ``pid``'s copy of ``card_id``."""
    oid = next(
        o
        for zone in (game.state.players[pid].hand, game.state.players[pid].exile)
        for o in zone
        if game.state.objects[o].def_id == card_id
    )
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


def warp_line(game, card_id):
    return next(a for a in casts(game, card_id) if a.warp is not None)


def printed_line(game, card_id):
    return next(a for a in casts(game, card_id) if a.warp is None)


def battlefield_ids(game, pid=0):
    return [obj.def_id for obj in game.state.battlefield_objects(pid)]


def zone_ids(game, zone, pid=0):
    return [game.state.objects[o].def_id for o in game.state.players[pid].zone_list(zone)]


def tapped_lands(game, pid=0):
    return sum(
        1
        for o in game.state.battlefield_objects(pid)
        if o.tapped and game.state.card_of(o).is_land
    )


def resolve_stack(game):
    """Pass priority until nothing is waiting to resolve."""
    pass_until(game, lambda g: not g.state.stack)


def run_to_main_of(game, pid):
    pass_until(
        game,
        lambda g: g.state.active_player == pid and g.state.step is Step.PRECOMBAT_MAIN,
    )


def warp_in(game, card_id):
    """Cast ``card_id`` for its warp cost and let it resolve."""
    game.apply(warp_line(game, card_id))
    resolve_stack(game)


class TestItIsAnAlternativeCostAndNotADiscount:
    """601.2b: the warp price replaces the printed one, pips included."""

    def test_the_granted_line_charges_the_warp_price(self, builder):
        # {2}{R} out of eight Mountains, not {4}{R}{R}. A reduction clamped to
        # the generic part could never have reached the second {R}.
        game = board(builder, hand=[LANCER])
        warp_in(game, LANCER)
        assert LANCER in battlefield_ids(game)
        assert tapped_lands(game) == 3

    def test_a_printed_warp_cost_charges_itself(self, builder):
        # No granter on the board at all: "Warp {1}{R}" is a field on the card,
        # exactly as "Evoke {2}{U}" is.
        # The Forest is there only to keep a play in hand: a position whose
        # active player has nothing to do runs on past the end step by itself,
        # and the warp delay would have exiled the creature before the
        # assertion.
        game = board(builder, hand=[HULK, "forest"], marshal=False)
        warp_in(game, HULK)
        assert HULK in battlefield_ids(game)
        assert tapped_lands(game) == 2

    def test_the_printed_line_survives_beside_the_warp_one(self, builder):
        # "You may cast": a player who wants the permanent to stay must still
        # be able to pay for it. Replacing the line would take that away.
        game = board(builder, hand=[LANCER])
        assert sorted(a.warp is None for a in casts(game, LANCER)) == [False, True]

    def test_the_two_lines_are_different_actions(self, builder):
        # Same source, same targets, same X. The price is the only thing
        # separating them, so it has to be part of the action's identity or a
        # lookup answers with whichever came first -- and the two do very
        # different things to the permanent.
        game = board(builder, hand=[LANCER])
        assert warp_line(game, LANCER).key() != printed_line(game, LANCER).key()
        assert warp_line(game, LANCER).base_label != printed_line(game, LANCER).base_label

    def test_the_label_names_the_price(self, builder):
        # The price is not on the card under a grant, so the row is the only
        # place a player can read what this line costs.
        game = board(builder, hand=[BAUBLE])
        assert "(warp {2}{R})" in warp_line(game, BAUBLE).base_label

    def test_the_permanent_arrives_normally(self, builder):
        # Not a smaller creature, not a tapped one, not a token: warp buys the
        # cheap cast and nothing else about the arrival.
        game = board(builder, hand=[LANCER])
        warp_in(game, LANCER)
        lancer = next(o for o in game.state.battlefield_objects(0) if o.def_id == LANCER)
        assert not lancer.tapped
        from automtg.engine.characteristics import chars

        assert (chars(game.state, lancer.oid).power, chars(game.state, lancer.oid).toughness) == (
            4,
            4,
        )

    def test_the_printed_cast_is_untouched(self, builder):
        # The control for every exile assertion below: a normally-cast creature
        # under the same granter is nobody's business at the end step.
        game = board(builder, hand=[LANCER])
        game.apply(printed_line(game, LANCER))
        resolve_stack(game)
        assert not game.state.delayed_triggers
        run_to_main_of(game, 1)
        assert LANCER in battlefield_ids(game)


class TestItIsExiledAtTheNextEndStep:
    """Not sacrificed (evoke), not bounced, and not this instant."""

    def test_it_survives_the_turn_it_arrived_on(self, builder):
        # The whole difference from foretell and suspend, which exile from hand
        # *first*: a warped creature is on the battlefield for this turn's
        # combat.
        game = board(builder, hand=[LANCER])
        warp_in(game, LANCER)
        pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
        assert LANCER in battlefield_ids(game)

    def test_it_is_gone_by_the_next_turn(self, builder):
        game = board(builder, hand=[LANCER])
        warp_in(game, LANCER)
        run_to_main_of(game, 1)
        assert LANCER not in battlefield_ids(game)

    def test_it_goes_to_exile_and_not_to_a_graveyard(self, builder):
        # Evoke's sacrifice is the near miss and it is the wrong zone: a card
        # in a graveyard is not one you may cast on a later turn.
        game = board(builder, hand=[LANCER])
        warp_in(game, LANCER)
        run_to_main_of(game, 1)
        assert zone_ids(game, Zone.EXILE) == [LANCER]
        assert zone_ids(game, Zone.GRAVEYARD) == []

    def test_it_goes_to_exile_and_not_back_to_hand(self, builder):
        game = board(builder, hand=[LANCER])
        warp_in(game, LANCER)
        run_to_main_of(game, 1)
        assert LANCER not in zone_ids(game, Zone.HAND)

    def test_the_delay_is_spent_once(self, builder):
        game = board(builder, hand=[LANCER])
        warp_in(game, LANCER)
        assert len(game.state.delayed_triggers) == 1
        run_to_main_of(game, 1)
        assert not game.state.delayed_triggers

    def test_the_delay_is_scoped_to_the_object_that_entered(self, builder):
        # "Exile **that** permanent". A second copy of the same card cast
        # normally is a different object and stays where it is -- a selector
        # written over the board rather than over the binding would take both.
        game = board(builder, hand=[LANCER, LANCER], lands=12)
        warp_in(game, LANCER)
        game.apply(printed_line(game, LANCER))
        resolve_stack(game)
        assert battlefield_ids(game).count(LANCER) == 2
        run_to_main_of(game, 1)
        assert battlefield_ids(game).count(LANCER) == 1

    def test_a_warped_permanent_that_already_died_is_not_chased(self, builder):
        # It is a card in a graveyard and a new object (400.7) by the time the
        # end step comes. Exiling it there would be the delay reaching past the
        # permanent it was made for -- and would hand the caster a free
        # recursion the card does not print.
        from automtg.engine.zones import destroy

        game = board(builder, hand=[LANCER])
        warp_in(game, LANCER)
        oid = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == LANCER)
        destroy(game.state, oid)
        run_to_main_of(game, 1)
        assert zone_ids(game, Zone.GRAVEYARD) == [LANCER]
        assert zone_ids(game, Zone.EXILE) == []


class TestItMayBeCastFromExileOnALaterTurn:
    """`later_turns`: the turn it was exiled on is the one turn it may not be cast."""

    def test_it_is_castable_on_the_following_turn(self, builder):
        game = board(builder, hand=[LANCER])
        warp_in(game, LANCER)
        run_to_main_of(game, 0)
        assert casts(game, LANCER), "the exiled card should offer a cast line"

    def test_casting_it_from_exile_costs_the_printed_price(self, builder):
        # "You may cast it from exile" -- a permission, not a second discount
        # and not a free cast. {4}{R}{R} out of the Mountains.
        game = board(builder, hand=[LANCER])
        warp_in(game, LANCER)
        run_to_main_of(game, 0)
        game.apply(printed_line(game, LANCER))
        resolve_stack(game)
        assert LANCER in battlefield_ids(game)
        assert tapped_lands(game) == 6

    def test_it_is_not_castable_from_exile_the_turn_it_was_exiled(self, builder):
        # "On a **later** turn". The exile happens in the end step, after the
        # last main phase, so the only way to see this is an opponent's turn --
        # where the card is exiled and the seat has priority at instant speed.
        game = board(builder, hand=[LANCER])
        warp_in(game, LANCER)
        pass_until(game, lambda g: g.state.turn > 1)
        exiled = next(o for o in game.state.players[0].exile)
        obj = game.state.objects[exiled]
        assert obj.playable_by == 0
        assert not obj.playable_live(game.state.turn - 1), (
            "the turn it was exiled on is the one turn it may not be cast"
        )
        assert obj.playable_live(game.state.turn)

    def test_the_second_cast_does_not_warp_itself_again(self, builder):
        # The loop guard: warp is offered from **hand** only. Without that the
        # card cast out of exile would warp again, be exiled again, and never
        # leave -- a one-card engine no printing has.
        game = board(builder, hand=[LANCER])
        warp_in(game, LANCER)
        run_to_main_of(game, 0)
        assert [a.warp for a in casts(game, LANCER)] == [None]

    def test_the_permission_is_not_free(self, builder):
        game = board(builder, hand=[LANCER])
        warp_in(game, LANCER)
        run_to_main_of(game, 0)
        exiled = next(o for o in game.state.players[0].exile)
        assert not game.state.objects[exiled].playable_free


class TestTheGrantsScope:
    """A union of two printed shapes, and nothing else."""

    def test_an_artifact_card_has_warp(self, builder):
        game = board(builder, hand=[BAUBLE])
        assert [a.warp for a in casts(game, BAUBLE)] == [None, "{2}{R}"]

    def test_a_red_creature_card_has_warp(self, builder):
        game = board(builder, hand=[LANCER])
        assert sorted(a.warp or "" for a in casts(game, LANCER)) == ["", "{2}{R}"]

    def test_a_blue_creature_card_does_not(self, builder):
        # The measurement. `any_types: ["Artifact", "Creature"]` -- the tempting
        # near miss -- would hand warp to this card, and a colour clause ANDed
        # onto the whole filter would take it away from the Bauble.
        # Two Islands so the printed line is on offer: an empty list would
        # prove only that the seat could not pay {U}{U}.
        game = board(builder, hand=[SCRIBE], islands=2)
        assert [a.warp for a in casts(game, SCRIBE)] == [None]

    def test_without_the_granter_nobody_has_warp(self, builder):
        game = board(builder, hand=[BAUBLE, LANCER], marshal=False)
        assert [a.warp for a in casts(game, BAUBLE)] == [None]
        assert [a.warp for a in casts(game, LANCER)] == [None]

    def test_an_opponents_granter_grants_you_nothing(self, builder):
        # "…in **your** hand". `affects_player` is read against the granting
        # permanent's controller.
        game = board(builder, hand=[LANCER], marshal_seat=1)
        assert [a.warp for a in casts(game, LANCER)] == [None]

    def test_the_grant_is_standing_and_not_a_snapshot(self, builder):
        # A card drawn after the granter arrived has warp too: this is a static
        # re-read every time the cast lines are built, which is what
        # `grant_playable` could not be.
        from automtg.engine.primitives import draw_cards

        game = board(builder, hand=["forest"], library=[LANCER])
        draw_cards(game.state, 0, 1)
        assert [a.warp for a in casts(game, LANCER)] == [None, "{2}{R}"]

    def test_the_grant_wears_off_with_its_source(self, builder):
        from automtg.engine.zones import destroy

        game = board(builder, hand=[LANCER])
        marshal = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == MARSHAL)
        destroy(game.state, marshal)
        assert [a.warp for a in casts(game, LANCER)] == [None]

    def test_a_printed_warp_cost_does_not_need_the_granter(self, builder):
        game = board(builder, hand=[HULK], marshal=False)
        assert [a.warp for a in casts(game, HULK)] == [None, "{1}{R}"]


class TestTheLoaderRefusesTheSilentFailures:
    """Each of these would load clean and print a line the card does not perform."""

    def _card(self, **kwargs):
        base = dict(
            id="t_bad",
            name="Bad",
            mana_cost="{3}",
            types=["Creature"],
            power=1,
            toughness=1,
        )
        base.update(kwargs)
        return CardModel(**base)

    def _grant(self, **kwargs):
        base = dict(
            kind="static",
            text="x",
            effect="grant_warp",
            affects_player="you",
            warp_cost="{2}{R}",
            affects_spells={"types": ["Artifact"]},
        )
        base.update(kwargs)
        return AbilityModel(**base)

    def test_a_grant_with_no_filter_is_refused(self):
        from automtg.cards.loader import compile_card

        model = self._card(abilities=[self._grant(affects_spells=None)])
        with pytest.raises(DslError, match="affects_spells"):
            compile_card(model)

    def test_a_grant_with_no_price_is_refused(self):
        from automtg.cards.loader import compile_card

        model = self._card(abilities=[self._grant(warp_cost=None)])
        with pytest.raises(DslError, match="warp_cost"):
            compile_card(model)

    def test_a_filter_that_reads_board_state_is_refused(self):
        # A card in a hand has no board state, and `_matches_printed` would
        # walk past the word -- granting warp to everything the rest of the
        # filter admits.
        from automtg.cards.loader import compile_card

        model = self._card(abilities=[self._grant(affects_spells={"tapped": True})])
        with pytest.raises(DslError, match="tapped"):
            compile_card(model)

    def test_board_state_inside_an_any_of_branch_is_refused_too(self):
        from automtg.cards.loader import compile_card

        model = self._card(
            abilities=[
                self._grant(
                    affects_spells={"any_of": [{"types": ["Artifact"]}, {"tapped": True}]}
                )
            ]
        )
        with pytest.raises(DslError, match=r"any_of\[1\]"):
            compile_card(model)

    def test_a_warp_cost_equal_to_the_printed_one_is_refused(self):
        # One cast offered twice, and nobody would take the second -- evoke's
        # invariant, for evoke's reason.
        from automtg.cards.loader import compile_card

        model = self._card(mana_cost="{2}{R}", warp="{2}{R}")
        with pytest.raises(DslError, match="the same as the printed cost"):
            compile_card(model)

    def test_warp_on_a_nonpermanent_card_is_refused(self):
        # "Exile that permanent" has nothing to exile when the spell goes to a
        # graveyard, so the card would load, print its reminder text and simply
        # cost less.
        from automtg.cards.loader import compile_card

        model = self._card(types=["Instant"], power=None, toughness=None, warp="{R}")
        with pytest.raises(DslError, match="only on a permanent card"):
            compile_card(model)


class TestThePrintedWarpLineIsClaimed:
    """Gate 3's bookkeeping, which is where a correct warp card used to die.

    `verify._covered` carries a claimant for every other card-level alternative
    cost -- kicker, multikicker, strive, emerge, evoke, bestow, mutate, gift,
    ascend -- and carried none for warp. Nothing had hit it because no shipped
    card used the field: the pool's only warp is the `grant_warp` static above,
    whose printed line that static's own `text` already claims.

    So a card printing "Warp {1}{R}" loaded, offered both cast lines, exiled and
    came back exactly as the classes above measure -- and was still rejected as
    half-implemented, with `residual_text` returning precisely that one line.
    Exalted Sunborn and Haliya, Guided by Light are the witnesses; both were
    filed as gap records against a mechanic the engine already had.

    "Warp" is not in `KNOWN_KEYWORDS` either, so `lift_keywords` cannot consume
    the line and there is no honest way to claim it from inside the card.
    """

    def _card(self, **extra) -> CardModel:
        base = {
            "id": "t_warp_residual",
            "name": "Warp Residual",
            "mana_cost": "{5}{R}",
            "oracle_text": "Warp {1}{R}\nFlying",
            "types": ["Creature"],
            "power": 3,
            "toughness": 3,
            "keywords": ["flying"],
            "warp": "{1}{R}",
        }
        base.update(extra)
        return CardModel.model_validate(base)

    def test_the_printed_warp_line_is_claimed(self):
        from automtg.cards.authoring.verify import residual_text
        from automtg.cards.loader import compile_card

        card = compile_card(self._card())
        assert residual_text(card, card.oracle_text) == ""

    def test_a_card_without_warp_leaves_the_line_residual(self):
        """The claimant is the field, not the word: no field, no claim.

        This is the half that stops the exemption becoming a way to print a
        mechanic you did not implement.
        """
        from automtg.cards.authoring.verify import residual_text
        from automtg.cards.loader import compile_card

        card = compile_card(self._card(id="t_warp_absent", warp=None))
        assert "Warp {1}{R}" in residual_text(card, card.oracle_text)

    def test_a_cheaper_declared_cost_cannot_claim_a_dearer_printed_one(self):
        """Strict like bestow's and mutate's claimants, for their reason.

        The whole line is the price, so a card charging {1}{R} while printing
        "Warp {3}{R}{R}" is a strictly cheaper card wearing the real one's
        words. The line stays residual rather than being waved through on the
        first word alone.
        """
        from automtg.cards.authoring.verify import residual_text
        from automtg.cards.loader import compile_card

        card = compile_card(
            self._card(
                id="t_warp_cheaper",
                oracle_text="Warp {3}{R}{R}\nFlying",
                warp="{1}{R}",
            )
        )
        assert "Warp {3}{R}{R}" in residual_text(card, card.oracle_text)

    def test_the_reminder_text_does_not_have_to_match(self):
        """`_declares_printed_cost` cuts at the parenthesis before parsing, so a
        real printing -- which always carries the reminder -- is claimed."""
        from automtg.cards.authoring.verify import residual_text
        from automtg.cards.loader import compile_card

        card = compile_card(
            self._card(
                id="t_warp_reminder",
                oracle_text=(
                    "Warp {1}{R} (You may cast this card from your hand for its warp "
                    "cost. Exile that permanent at the beginning of the next end step, "
                    "then you may cast it from exile on a later turn.)\nFlying"
                ),
            )
        )
        assert residual_text(card, card.oracle_text) == ""
