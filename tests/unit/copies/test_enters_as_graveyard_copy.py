"""An as-enters copy of a card in the graveyard, and an exception that adds a supertype.

    "Flash. You may have Ezri Dax enter as a copy of any creature card in your
    graveyard that was put there from the battlefield this turn, except her
    name is Ezri Dax, Newly Joined and she's a legendary Trill in addition to
    her other types."                          -- Ezri Dax, Newly Joined

Two halves, each with a near miss that is a different card:

**The pool is cards, not permanents.** `self_enters_as_copy`'s ``copying`` is
a standing selector, so ``{"zone": "graveyard", "controller": "you", "types":
["Creature"], "graveyard_arrival_this_turn": ["from_battlefield"]}`` offers
exactly the creature cards in her controller's graveyard that left the
battlefield this turn. The copy is of that card's copiable values (707.2), and
it applies as she enters (614.1c), so the copied creature's own enters trigger
sees her arrive as the copy. Written as a `self_enters` trigger running
`become_copy`, she would enter as a 1/3 Trill Advisor, the copied enters
trigger would never fire, and an opponent would have priority with her
uncopied. A discarded creature card, or one that died on an earlier turn, is
not in the pool: "put there from the battlefield **this turn**".

**"…she's a legendary Trill" is a copiable value (706.9b, 707.9b).**
``except_.add_supertypes`` puts Legendary on the copied face beside
``add_subtypes``' Trill and ``name``, so a copy of a nonlegendary Bear is a
legendary Bear Trill named Ezri, and the legend rule (704.5j) pairs her with
another Ezri. Without it the copy is a nonlegendary creature that two Ezris
could share a board as.

Declined, or with nothing in the pool, she is her printed 1/3.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.authoring.verify import claimed_lines
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import discard_cards
from commanderblitz.engine.zones import destroy, move_object
from tests.conftest import hand_ids, only_oid, pass_until, pt

EZRI = "t_eagc_ezri"  # legendary 1/3 Trill Advisor, the clause above
BEAR = "t_bear"  # 2/2 Bear, vanilla
SCOUT = "t_etb_draw"  # 1/1 Scout, "When this enters, draw a card."
RELIC = "t_flying_artifact"  # a noncreature artifact
LEGEND = "t_legend"  # legendary 2/2, the opponent's
EZRI_NAME = "Test Ezri, Newly Joined"


def position(builder, *, mine=(), theirs=(), hand=(), ezris=1):
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 8)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .hand(0, [EZRI] * ezris + list(hand))
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def died(game, card_id: str, pid: int = 0) -> int:
    """Destroy ``card_id``'s permanent: it goes to the graveyard from the battlefield."""
    oid = only_oid(game, card_id, pid)
    destroy(game.state, oid)
    assert game.state.objects[oid].zone is Zone.GRAVEYARD
    return oid


def cast_ezri(game, *, say_yes: bool = True, copy_id: str | None = None) -> set[str]:
    """Cast one Ezri and answer her questions; the def ids she was offered.

    Empty when the "you may" was never asked. A pool of one card is not put
    to a choice -- the yes picks it -- so that card is the whole offer.
    """
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == EZRI
    )
    ezri = action.source
    game.apply(action)
    asked = False
    offered: set[str] = set()
    for _ in range(40):
        pending = game.pending()
        if pending is None or pending.kind is DecisionKind.PRIORITY:
            break
        if pending.kind is DecisionKind.MAY:
            asked = True
            want = ActionKind.YES if say_yes else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is want))
            continue
        choices = [a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]
        if not choices:
            break
        ids = {game.state.objects[a.targets[0].id].def_id: a for a in choices if a.targets}
        if not offered:
            offered = set(ids)
        game.apply(ids.get(copy_id, choices[0]) if copy_id else choices[0])
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
    copied = game.state.objects[ezri].copying
    if asked and not offered and copied is not None:
        offered = {copied}
    return offered


def ezris_on_battlefield(game) -> list[int]:
    return [o for o in game.state.battlefield if game.state.objects[o].def_id == EZRI]


def face(game, oid: int):
    return game.state.card_of(game.state.objects[oid])


class TestThePool:
    def test_a_creature_that_died_this_turn_is_offered(self, builder):
        game = position(builder, mine=[BEAR])
        died(game, BEAR)
        assert cast_ezri(game, copy_id=BEAR) == {BEAR}

    def test_a_discarded_creature_card_is_not(self, builder):
        """In the graveyard this turn, but from the hand: nothing to ask."""
        game = position(builder, hand=[BEAR])
        bear = next(
            o for o in game.state.players[0].hand if game.state.objects[o].def_id == BEAR
        )
        discard_cards(game.state, 0, [bear])
        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert cast_ezri(game) == set()
        (oid,) = ezris_on_battlefield(game)
        assert face(game, oid).name == EZRI_NAME and pt(game, oid) == (1, 3)

    def test_a_creature_that_died_last_turn_is_not(self, builder):
        game = position(builder, mine=[BEAR])
        bear = died(game, BEAR)
        # The arrival is read against the turn it happened on (400.7), so a
        # card that reached the graveyard a turn ago answers for that turn.
        game.state.objects[bear].graveyard_turn = game.state.turn - 1
        assert cast_ezri(game) == set()

    def test_a_card_that_was_already_there_is_not(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 8)
            .graveyard(0, [BEAR])
            .hand(0, [EZRI])
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        game._advance()
        assert cast_ezri(game) == set()

    def test_only_your_graveyard_and_only_creature_cards(self, builder):
        """An opponent's creature that died this turn is in *their* graveyard,
        and an artifact that left the battlefield is no creature card."""
        game = position(builder, mine=[BEAR, SCOUT, RELIC], theirs=[LEGEND])
        died(game, BEAR)
        died(game, SCOUT)
        died(game, RELIC)
        died(game, LEGEND, pid=1)
        assert cast_ezri(game, copy_id=BEAR) == {BEAR, SCOUT}
        (oid,) = ezris_on_battlefield(game)
        assert game.state.objects[oid].copying == BEAR

    def test_the_card_stays_in_the_graveyard(self, builder):
        """A copy of a card takes its values and leaves the card where it is."""
        game = position(builder, mine=[BEAR])
        bear = died(game, BEAR)
        cast_ezri(game, copy_id=BEAR)
        assert game.state.objects[bear].zone is Zone.GRAVEYARD


class TestTheCopy:
    def test_she_is_the_copy_with_her_name_legendary_and_a_trill(self, builder):
        game = position(builder, mine=[BEAR])
        died(game, BEAR)
        cast_ezri(game, copy_id=BEAR)
        (oid,) = ezris_on_battlefield(game)
        c = chars(game.state, oid)
        assert face(game, oid).name == EZRI_NAME
        assert (c.power, c.toughness) == (2, 2)
        assert {str(s) for s in c.supertypes} == {"Legendary"}
        assert {"Bear", "Trill"} <= {str(s) for s in c.subtypes}
        assert "Advisor" not in {str(s) for s in c.subtypes}, "her own types are copied over"

    def test_the_copied_enters_trigger_sees_her_arrive_as_the_copy(self, builder):
        """614.1c: the copy is how she enters, so the Scout's "When this
        enters, draw a card" is hers and triggers."""
        game = position(builder, mine=[SCOUT])
        died(game, SCOUT)
        before = len(hand_ids(game))
        cast_ezri(game, copy_id=SCOUT)
        (oid,) = ezris_on_battlefield(game)
        assert pt(game, oid) == (1, 1)
        assert len(hand_ids(game)) == before, "Ezri left the hand and the Scout drew one"

    def test_the_legend_rule_sees_the_copy(self, builder):
        """A legendary copy named Ezri beside a plain Ezri: one of them goes."""
        game = position(builder, mine=[BEAR], ezris=2)
        cast_ezri(game, say_yes=False)
        died(game, BEAR)
        cast_ezri(game, copy_id=BEAR)
        assert len(ezris_on_battlefield(game)) == 1

    def test_the_exception_does_not_outlive_the_object(self, builder):
        game = position(builder, mine=[BEAR])
        died(game, BEAR)
        cast_ezri(game, copy_id=BEAR)
        (oid,) = ezris_on_battlefield(game)
        move_object(game.state, oid, Zone.HAND)
        obj = game.state.objects[oid]
        assert obj.copying is None and obj.copying_add_supertypes is None


class TestDeclining:
    def test_declined_she_is_her_printed_self(self, builder):
        game = position(builder, mine=[BEAR])
        died(game, BEAR)
        assert cast_ezri(game, say_yes=False) == set()
        (oid,) = ezris_on_battlefield(game)
        assert game.state.objects[oid].copying is None
        assert face(game, oid).name == EZRI_NAME
        assert pt(game, oid) == (1, 3)
        assert {"Trill", "Advisor"} <= {str(s) for s in chars(game.state, oid).subtypes}


def _model(except_: dict, copying: dict | None = None, oracle: str = "") -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_eagc_probe",
            "name": "Probe",
            "oracle_text": oracle,
            "mana_cost": "{2}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 3,
            "replacements": [
                {
                    "event": "self_enters_as_copy",
                    "copying": copying or {"zone": "battlefield", "types": ["Creature"]},
                    "except_": except_,
                }
            ],
        }
    )


EZRI_POOL = {
    "zone": "graveyard",
    "controller": "you",
    "types": ["Creature"],
    "graveyard_arrival_this_turn": ["from_battlefield"],
}
EZRI_EXCEPT = {"name": "Probe", "add_supertypes": ["Legendary"], "add_subtypes": ["Trill"]}
EZRI_LINE = (
    "You may have Probe enter as a copy of any creature card in your graveyard that "
    "was put there from the battlefield this turn, except her name is Probe and "
    "she's a legendary Trill in addition to her other types."
)


class TestTheLoaderChecksIt:
    def test_the_ezri_shape_loads(self):
        compile_card(_model(EZRI_EXCEPT, EZRI_POOL))

    @pytest.mark.parametrize(
        ("except_", "message"),
        [
            ({"add_supertypes": []}, "non-empty list"),
            ({"add_supertypes": "Legendary"}, "non-empty list"),
            ({"add_supertypes": ["Legend"]}, "unknown supertype"),
            (
                {"add_supertypes": ["Legendary"], "remove_supertypes": ["Legendary"]},
                "both 'add_supertypes' and 'remove_supertypes'",
            ),
        ],
    )
    def test_a_malformed_key_is_refused(self, except_, message):
        with pytest.raises(DslError, match=message):
            compile_card(_model(except_))


class TestTheResidualGateClaimsTheLine:
    def test_the_whole_shape_claims_it(self):
        card = compile_card(_model(EZRI_EXCEPT, EZRI_POOL, EZRI_LINE))
        assert EZRI_LINE in claimed_lines(card, EZRI_LINE)

    @pytest.mark.parametrize(
        ("except_", "copying"),
        [
            ({"name": "Probe", "add_subtypes": ["Trill"]}, EZRI_POOL),
            ({"name": "Probe", "add_supertypes": ["Legendary"]}, None),
            (EZRI_EXCEPT, {"zone": "battlefield", "types": ["Creature"]}),
            (EZRI_EXCEPT, {k: v for k, v in EZRI_POOL.items() if k != "graveyard_arrival_this_turn"}),
        ],
        ids=["no-legendary", "battlefield-pool", "battlefield-pool-full-except", "any-arrival"],
    )
    def test_a_copy_missing_a_half_does_not(self, except_, copying):
        card = compile_card(_model(except_, copying, EZRI_LINE))
        assert EZRI_LINE not in claimed_lines(card, EZRI_LINE)
