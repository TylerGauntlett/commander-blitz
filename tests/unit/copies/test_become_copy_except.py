"""Kimahri, Valiant Guardian — a copy that keeps its own ability.

    Ronso Rage — At the beginning of combat on your turn, put a +1/+1 counter
    on Kimahri and tap target creature an opponent controls. Then you may have
    Kimahri become a copy of that creature, except its name is Kimahri, Valiant
    Guardian and it has vigilance and this ability.

Rule 707.9b: an exception to a copy effect is part of the copiable values. So
"and it has vigilance and this ability" is written onto the copied face itself
(`copying_keywords`, `copying_own_abilities`, read by `GameState.card_of`), not
granted on top of it. Without it, `become_copy` takes the copied creature's face
whole: Kimahri stops having vigilance and loses Ronso Rage, so the trigger fires
once and never again -- a far weaker card. A `grant_keyword` / `grant_ability`
after the copy would be a layer-6 grant instead, which a later
"loses all abilities" or a copy of Kimahri treats differently.

The kept ability is **appended** after the copied face's own abilities, so the
copied card's indices keep meaning what they printed.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import abilities_of
from commanderblitz.engine.effects import execute_one
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import clear_until_eot
from tests.conftest import keywords, only_oid, pass_until, pt

GUARDIAN = "t_guardian"
LIFEGIVER = "t_lifegiver"


def board(builder, *, advance: bool = False):
    game = (
        builder(players=2)
        .battlefield(0, [GUARDIAN])
        .battlefield(1, [LIFEGIVER])
        .build(advance=advance)
    )
    return game, only_oid(game, GUARDIAN), only_oid(game, LIFEGIVER)


def become_copy(game, oid: int, **overrides):
    spec = {
        "op": "become_copy",
        "duration": "permanent",
        "objects": {"zone": "battlefield", "self_only": True},
        "copying": {"zone": "battlefield", "controller": "opponent", "types": ["Creature"]},
        **overrides,
    }
    ctx = EffectContext(state=game.state, controller=0, source_oid=oid)
    gen = execute_one(ctx, spec)
    try:
        while True:
            next(gen)
    except StopIteration:
        pass
    return game


def face(game, oid: int):
    return game.state.card_of(game.state.objects[oid])


KIMAHRI_EXCEPT = {"add_keywords": ["vigilance"], "keep_abilities": [0]}


def ronso_rage(game, *, accept: bool = True) -> None:
    """Pass to player 0's next beginning of combat and answer Ronso Rage's
    "you may" -- the opponent's lone creature is its only legal target."""
    pass_until(game, lambda g: g.pending().kind is DecisionKind.MAY)
    want = ActionKind.YES if accept else ActionKind.NO
    game.apply(next(a for a in game.legal_actions() if a.kind is want))


class TestTheExceptionIsOnTheCopiedFace:
    def test_it_takes_the_body_and_keeps_its_name(self, builder):
        game, guardian, _giver = board(builder)
        become_copy(game, guardian, except_name="Test Guardian", except_=KIMAHRI_EXCEPT)
        assert face(game, guardian).name == "Test Guardian"
        assert pt(game, guardian) == (3, 3)

    def test_it_has_vigilance(self, builder):
        """"…and it has vigilance": Test Lifegiver prints none."""
        game, guardian, giver = board(builder)
        become_copy(game, guardian, except_=KIMAHRI_EXCEPT)
        assert "vigilance" in keywords(game, guardian)
        assert "vigilance" in face(game, guardian).keywords
        assert "vigilance" not in keywords(game, giver)

    def test_it_keeps_this_ability_after_the_copied_ones(self, builder):
        """The copied face's ability keeps seat 0; the kept one is appended."""
        game, guardian, _giver = board(builder)
        become_copy(game, guardian, except_=KIMAHRI_EXCEPT)
        abilities = abilities_of(game.state, guardian)
        assert [a.index for a in abilities] == [0, 1]
        assert abilities[0].is_activated
        assert abilities[1].trigger is not None
        assert abilities[1].text.startswith("At the beginning of combat")

    def test_without_the_exception_it_is_the_copied_creature_whole(self, builder):
        """The near miss: a plain `become_copy` loses vigilance and the trigger."""
        game, guardian, _giver = board(builder)
        become_copy(game, guardian, except_name="Test Guardian")
        assert "vigilance" not in keywords(game, guardian)
        assert len(abilities_of(game.state, guardian)) == 1

    def test_the_original_is_untouched(self, builder):
        game, guardian, giver = board(builder)
        become_copy(game, guardian, except_=KIMAHRI_EXCEPT)
        assert len(abilities_of(game.state, giver)) == 1
        assert face(game, giver).name == "Test Lifegiver"


class TestTheDuration:
    def test_a_permanent_copy_keeps_its_exception_through_cleanup(self, builder):
        game, guardian, _giver = board(builder)
        become_copy(game, guardian, except_=KIMAHRI_EXCEPT)
        clear_until_eot(game.state)
        assert "vigilance" in keywords(game, guardian)
        assert len(abilities_of(game.state, guardian)) == 2

    def test_a_timed_copy_takes_its_exception_with_it(self, builder):
        game, guardian, _giver = board(builder)
        become_copy(game, guardian, duration="end_of_turn", except_=KIMAHRI_EXCEPT)
        clear_until_eot(game.state)
        obj = game.state.objects[guardian]
        assert obj.copying is None and obj.copying_own_abilities is None
        assert obj.copying_keywords is None
        assert face(game, guardian).name == "Test Guardian"

    def test_a_new_copy_replaces_the_old_exception(self, builder):
        """A later copy effect without the exception is the copied card whole."""
        game, guardian, _giver = board(builder)
        become_copy(game, guardian, except_=KIMAHRI_EXCEPT)
        become_copy(game, guardian)
        assert len(abilities_of(game.state, guardian)) == 1
        assert "vigilance" not in keywords(game, guardian)


class TestRonsoRageFiresAgain:
    def test_declining_leaves_it_itself(self, builder):
        game, guardian, giver = board(builder, advance=True)
        ronso_rage(game, accept=False)
        assert face(game, guardian).name == "Test Guardian"
        assert pt(game, guardian) == (2, 2)
        assert game.state.objects[giver].tapped

    def test_the_kept_trigger_fires_from_the_copied_face(self, builder):
        """The witness: Ronso Rage survives the copy and fires next turn."""
        game, guardian, _giver = board(builder, advance=True)
        ronso_rage(game)
        assert face(game, guardian).name == "Test Guardian"
        # The copied 3/3 body plus the counter Ronso Rage put first.
        assert pt(game, guardian) == (4, 4)
        assert "vigilance" in keywords(game, guardian)

        pass_until(game, lambda g: g.state.active_player == 1)
        ronso_rage(game)
        assert game.state.active_player == 0
        assert pt(game, guardian) == (5, 5)
        assert face(game, guardian).name == "Test Guardian"


class TestTheLoaderRefuses:
    def card(self, exception):
        ability = {
            "kind": "triggered",
            "text": "x",
            "trigger": {"event": "begin_combat", "controller": "you"},
            "effects": [
                {"op": "become_copy", "duration": "permanent", "except_": exception,
                 "objects": {"zone": "battlefield", "self_only": True},
                 "copying": {"zone": "battlefield", "controller": "opponent",
                             "types": ["Creature"], "count": 1}}
            ],
        }
        return {"id": "t_bad", "name": "Bad", "types": ["Creature"], "power": 1,
                "toughness": 1, "abilities": [ability]}

    @pytest.mark.parametrize(
        "exception",
        [
            {"name": "X"},
            {},
            {"add_keywords": ["not_a_keyword"]},
            {"keep_abilities": [1]},
            {"keep_abilities": "0"},
        ],
    )
    def test_a_malformed_exception(self, exception):
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(self.card(exception)))

    def test_a_well_formed_exception_loads(self):
        compile_card(CardModel.model_validate(self.card(KIMAHRI_EXCEPT)))
