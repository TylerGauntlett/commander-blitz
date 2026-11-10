"""An as-enters copy of a card the arrival itself exiled -- 614.1c, 707.9.

    "As The Mimeoplasm enters, you may exile two creature cards from
    graveyards. If you do, it enters as a copy of one of those cards with a
    number of additional +1/+1 counters on it equal to the power of the other
    card."                                               -- The Mimeoplasm

A `self_enters_as_copy` replacement with ``as_enters`` effects: the effects run
as part of the arrival (614.1c), the ``copying`` pool is what they bound
(``{"binding": "exiled"}``, cards in exile rather than permanents), the
controller picks the model, and the exception's ``enters_with`` reads the power
of the other card through the ``copied`` binding. The cheaper spelling, a
`self_enters` trigger running `exile`, `become_copy` and `add_counters`, puts a
0/0 on the battlefield first, and state-based actions bin it (704.5f) before
the trigger resolves -- `TestTheArrival` is that argument.

The copy is of the **card's** copiable values (707.2): its printed face, and the
power read off it is the card's in exile, with its characteristic-defining
ability applied (604.3). The counters are not copiable values (707.2); they are
placed as it enters. "Two" is two or none: with fewer than two creature cards
in all graveyards nothing is asked, nothing is exiled, and the printed 0/0 dies.
`t_meac_mimic` is The Mimeoplasm's line on a printed {2} 0/0.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind, Keyword, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer, action_for_card, pass_until, plus_one_counters
from tests.unit.copies.test_enters_as_copy import name_of

MIMIC = "t_meac_mimic"
OGRE, IMP, STAR, ALTAR = "t_meac_ogre", "t_meac_imp", "t_meac_star", "t_meac_altar"
WATCHER = "t_ae_watcher"  # gains life equal to an entering creature's power
RAISE = "t_riot_raise"  # returns target creature card from your graveyard


def position(builder, *, hand=(MIMIC,), mine=(), theirs=(), their_board=()):
    """Eight Forests, a main phase, ``mine``/``theirs`` in the two graveyards."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 8)
        .battlefield(1, list(their_board))
        .hand(0, list(hand))
        .graveyard(0, list(mine))
        .graveyard(1, list(theirs))
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def card(game, card_id):
    return next(o for o in game.state.objects.values() if o.def_id == card_id)


def mimic(game):
    return card(game, MIMIC)


def _pick(game, decision, card_ids) -> None:
    """Answer a CHOOSE_OBJECTS with the options whose cards are ``card_ids``."""
    wanted = list(card_ids)
    for index, option in enumerate(decision.options):
        if option.ref is None:
            continue
        def_id = game.state.objects[option.ref.id].def_id
        if def_id in wanted:
            wanted.remove(def_id)
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == index
                )
            )
            if game.pending() is not decision:
                return
    if game.pending() is decision:
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
        )


def play(game, *, exile=(), model=None, say_yes=True, cast=None, asked=None):
    """Cast (``cast`` or the action for the Mimic) and answer the arrival.

    ``exile`` names the two cards to exile, ``model`` the one to copy;
    ``asked`` collects the purposes of the object choices put to the caster.
    """
    game.apply(cast or action_for_card(game, ActionKind.CAST, MIMIC))
    for _ in range(100):
        decision = game.pending()
        if decision is None or (
            decision.kind is DecisionKind.PRIORITY and not game.state.stack
        ):
            break
        if decision.kind is DecisionKind.MAY:
            want = ActionKind.YES if say_yes else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is want))
            continue
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            purpose = decision.context.get("purpose")
            if asked is not None and decision.context["source"] == mimic(game).oid:
                asked.append((purpose, decision.player, decision.min_count, decision.max_count))
            if game.state.objects[decision.context["source"]].def_id == RAISE:
                # The reanimation's own pick: the Mimic is what comes back.
                _pick(game, decision, [MIMIC])
                continue
            _pick(game, decision, [model] if purpose == "enters_as_copy" else exile)
            continue
        game.apply(_default_answer(game, decision))
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


class TestTheCopy:
    def test_it_enters_as_one_card_with_the_others_power_in_counters(self, builder):
        game = position(builder, theirs=(OGRE, IMP))
        play(game, exile=(OGRE, IMP), model=OGRE)
        obj = mimic(game)
        assert obj.zone is Zone.BATTLEFIELD
        assert name_of(game, obj.oid) == "Test Mimic Ogre"
        assert plus_one_counters(game, obj.oid) == 1
        c = chars(game.state, obj.oid)
        assert (c.power, c.toughness) == (5, 4)
        assert Keyword.FLYING.value in c.keywords

    def test_the_other_choice_is_the_other_card(self, builder):
        game = position(builder, theirs=(OGRE, IMP))
        play(game, exile=(OGRE, IMP), model=IMP)
        obj = mimic(game)
        assert name_of(game, obj.oid) == "Test Mimic Imp"
        assert plus_one_counters(game, obj.oid) == 4
        c = chars(game.state, obj.oid)
        assert (c.power, c.toughness) == (5, 5)

    def test_both_cards_are_exiled(self, builder):
        game = position(builder, theirs=(OGRE, IMP))
        play(game, exile=(OGRE, IMP), model=OGRE)
        assert card(game, OGRE).zone is Zone.EXILE
        assert card(game, IMP).zone is Zone.EXILE

    def test_graveyards_means_any_of_them(self, builder):
        """One card from each graveyard: "from graveyards", not "your"."""
        game = position(builder, mine=(IMP,), theirs=(OGRE,))
        play(game, exile=(OGRE, IMP), model=OGRE)
        assert name_of(game, mimic(game).oid) == "Test Mimic Ogre"
        assert plus_one_counters(game, mimic(game).oid) == 1

    def test_the_power_is_the_cards_in_exile_cda_included(self, builder):
        """604.3: a */3 counting its owner's Forests is a 3 in exile, not 0."""
        game = position(builder, theirs=(STAR, IMP), their_board=["forest"] * 3)
        play(game, exile=(STAR, IMP), model=IMP)
        assert plus_one_counters(game, mimic(game).oid) == 3

    def test_the_counters_are_not_copied_into_the_values(self, builder):
        """707.2: the copiable values are the card's; the counters sit on top."""
        game = position(builder, theirs=(OGRE, IMP))
        play(game, exile=(OGRE, IMP), model=OGRE)
        obj = mimic(game)
        printed = game.state.card_of(obj)
        assert (printed.power, printed.toughness) == (4, 3)


class TestTheChoices:
    def test_the_caster_chooses_exactly_two_then_one_model(self, builder):
        asked = []
        game = position(builder, theirs=(OGRE, IMP, STAR))
        play(game, exile=(OGRE, IMP), model=OGRE, asked=asked)
        assert asked == [("destroy", 0, 2, 2), ("enters_as_copy", 0, 1, 1)]

    def test_a_noncreature_card_is_not_offered(self, builder):
        game = position(builder, theirs=(OGRE, IMP, ALTAR))
        play(game, exile=(OGRE, ALTAR, IMP), model=OGRE)
        assert card(game, ALTAR).zone is Zone.GRAVEYARD

    def test_declining_exiles_nothing_and_it_dies_a_0_0(self, builder):
        game = position(builder, theirs=(OGRE, IMP))
        play(game, say_yes=False)
        assert card(game, OGRE).zone is Zone.GRAVEYARD
        assert card(game, IMP).zone is Zone.GRAVEYARD
        assert mimic(game).zone is Zone.GRAVEYARD

    def test_one_creature_card_is_not_enough(self, builder):
        """Two or none: with one creature card nothing is asked or exiled."""
        asked = []
        game = position(builder, theirs=(OGRE, ALTAR))
        play(game, exile=(OGRE,), model=OGRE, asked=asked)
        assert asked == []
        assert card(game, OGRE).zone is Zone.GRAVEYARD
        assert mimic(game).zone is Zone.GRAVEYARD

    def test_the_passive_answers_finish_the_arrival(self, builder):
        """The authoring verifier's and a no-opinion seat's answers: no."""
        game = position(builder, theirs=(OGRE, IMP))
        game.apply(action_for_card(game, ActionKind.CAST, MIMIC))
        pass_until(game, lambda g: mimic(g).zone is not Zone.STACK)
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert mimic(game).zone is Zone.GRAVEYARD
        assert card(game, OGRE).zone is Zone.GRAVEYARD


class TestTheArrival:
    def test_an_enters_trigger_reads_the_copy_with_its_counters(self, builder):
        """The watcher gains 5, the copy's size: the 0/0 was never seen."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 8 + [WATCHER])
            .hand(0, [MIMIC])
            .graveyard(1, [OGRE, IMP])
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        game._advance()
        life = game.state.players[0].life
        play(game, exile=(OGRE, IMP), model=OGRE)
        assert game.state.players[0].life == life + 5

    def test_the_bindings_do_not_outlive_the_arrival(self, builder):
        game = position(builder, theirs=(OGRE, IMP))
        play(game, exile=(OGRE, IMP), model=OGRE)
        obj = mimic(game)
        assert obj.as_enters_bindings is None
        assert obj.enters_copy_of is None

    def test_a_reanimated_one_copies_too_and_not_itself(self, builder):
        """Any arrival asks; the card on its way in is not "in a graveyard"."""
        asked = []
        game = position(builder, hand=(RAISE,), mine=(MIMIC, IMP), theirs=(OGRE,))
        raise_it = action_for_card(game, ActionKind.CAST, RAISE)
        play(game, exile=(OGRE, IMP), model=IMP, cast=raise_it, asked=asked)
        obj = mimic(game)
        assert obj.zone is Zone.BATTLEFIELD
        assert name_of(game, obj.oid) == "Test Mimic Imp"
        assert plus_one_counters(game, obj.oid) == 4
        # Ogre and Imp are the only two other creature cards, so the exile is
        # forced once accepted -- the Mimic itself was never in the pool.
        assert asked == [("enters_as_copy", 0, 1, 1)]


def _card(replacement) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "x",
            "name": "X",
            "types": ["Creature"],
            "mana_cost": "{1}",
            "power": 0,
            "toughness": 0,
            "replacements": [replacement],
        }
    )


EXILE_TWO = {
    "op": "exile",
    "objects": {"zone": "graveyard", "controller": "any", "types": ["Creature"], "count": 2},
    "as": "exiled",
}


class TestLoadTimeRefusals:
    def test_the_written_shape_loads(self):
        compiled = compile_card(
            _card(
                {
                    "event": "self_enters_as_copy",
                    "as_enters": [EXILE_TWO],
                    "copying": {"binding": "exiled"},
                }
            )
        )
        assert compiled.replacements[0]["copying"] == {"binding": "exiled"}

    def test_a_pool_the_effects_did_not_bind_is_refused(self):
        """A battlefield pool beside ``as_enters`` would be a forced copy."""
        with pytest.raises(DslError, match="binding"):
            compile_card(
                _card(
                    {
                        "event": "self_enters_as_copy",
                        "as_enters": [EXILE_TWO],
                        "copying": {"zone": "battlefield", "types": ["Creature"]},
                    }
                )
            )
