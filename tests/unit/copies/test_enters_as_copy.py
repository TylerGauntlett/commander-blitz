"""A permanent that enters as a copy of another one.

    "You may have this Equipment **enter as a copy** of any Equipment on the
    battlefield."                            -- Masterwork of Ingenuity

614.1b, and the fifth entry on the enters-the-battlefield replacement whitelist.
`ReplacementModel.event` was a closed list of four -- `self_enters`,
`self_enters_tapped`, `self_enters_with_counters`, `self_enters_prepared` -- and
`_enter_battlefield` honoured `tapped`, `counters` and `prepared` out of
`modify`; no branch could change the arriving object's *identity*.

**Neither existing copy is this one.** `copy_permanent` calls `create_token` with
the model's def id: it makes a new permanent and never touches the object it is
pointed at, where Masterwork has to enter as the real card -- it stays a card, it
can be equipped and returned, and its copy is set as it arrives. `become_copy` is
the right mechanism and the wrong timing: it applies in place, and the only way
to reach it here is a `self_enters` trigger, which puts the Equipment on the
battlefield as *itself* first. Everything watching an Equipment enter sees the
blank, and anything answering the trigger answers it before the copy exists.

**Asked a moment early, on purpose.** `move_object` is not a generator and cannot
stop for a decision -- making it one would put a suspend point inside every zone
change in the engine -- so `offer_enters_copy` asks just before the move, beside
`offer_enters_costs` and from the same two call sites, and leaves the answer on
`enters_copy_of`. That is not an approximation: 614 applies the replacements
during the zone change and nobody receives priority in between, so there is no
window in which the permanent exists with the question unanswered.

`enters_copy_of` is a field of its own rather than `copying` written early,
because `reset_permanent_state` clears `copying` -- a permanent that leaves the
battlefield stops being a copy -- and it runs during the very move this answer
has to survive.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.errors import DslError
from tests.conftest import pass_until

MASTERWORK = "t_eac_masterwork"  # {1} blank Equipment, may enter as a copy
BLADE = "t_eac_blade"  # +3/+3 and an equip, the thing worth copying
OTHER = "t_eac_other"  # +1/+1, so the choice is a choice
PLAIN = "t_eac_plain"  # the same blank Equipment with no copy clause


def position(builder, spell: str, board=()):
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 6)
        .battlefield(0, list(board))
        .hand(0, [spell])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def cast(game, card_id: str, *, say_yes: bool = True, copy_id: str | None = None):
    """Cast ``card_id``, answering the enters-as-a-copy questions.

    Both questions are asked *before* the permanent is on the battlefield, so
    they arrive as ordinary pending decisions during the resolution rather than
    as a trigger, which is the whole point of the clause.
    """
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    for _ in range(40):
        pending = game.pending()
        if pending is None or pending.kind is DecisionKind.PRIORITY:
            break
        if pending.kind is DecisionKind.MAY:
            want = ActionKind.YES if say_yes else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is want))
            continue
        choices = [a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]
        if not choices:
            break
        if copy_id is not None:
            pick = next(
                (
                    a
                    for a in choices
                    if a.targets
                    and game.state.objects[a.targets[0].id].def_id == copy_id
                ),
                choices[0],
            )
        else:
            pick = choices[0]
        game.apply(pick)
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def name_of(game, oid: int) -> str:
    """The name this permanent now answers to -- `card_of` is the one place a
    permanent's current face is decided, and where `copying` is read."""
    return game.state.card_of(game.state.objects[oid]).name


def arrived(game):
    """The Masterwork object, however it now reads."""
    return game.state.objects[
        next(
            oid
            for oid in game.state.battlefield
            if game.state.objects[oid].def_id == MASTERWORK
        )
    ]


class TestItEntersAsTheCopy:
    def test_it_takes_the_copied_name(self, builder):
        game = position(builder, MASTERWORK, board=[BLADE])
        cast(game, MASTERWORK)
        assert name_of(game, arrived(game).oid) == "Test Copyable Blade"

    def test_it_is_still_its_own_object(self, builder):
        """The difference between this and `copy_permanent`: no token is made,
        and the card on the battlefield is the Masterwork."""
        game = position(builder, MASTERWORK, board=[BLADE])
        cast(game, MASTERWORK)
        assert arrived(game).def_id == MASTERWORK
        assert len(game.state.battlefield) == 8, "six lands, the Blade, the Masterwork"

    def test_it_has_the_copied_abilities(self, builder):
        """The whole value of the card: a blank Equipment arrives with a +3/+3
        and an equip it never printed."""
        from automtg.engine.characteristics import abilities_of

        game = position(builder, MASTERWORK, board=[BLADE])
        cast(game, MASTERWORK)
        texts = [a.text for a in abilities_of(game.state, arrived(game).oid)]
        assert any("+3/+3" in t for t in texts)
        assert any("Equip" in t for t in texts)

    def test_the_copy_is_permanent(self, builder):
        """706.2 gives a copy applied as a permanent enters no duration, so it
        must not be swept by `clear_until_eot`."""
        game = position(builder, MASTERWORK, board=[BLADE])
        cast(game, MASTERWORK)
        assert arrived(game).copying_until_eot is False
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn, limit=800)
        assert name_of(game, arrived(game).oid) == "Test Copyable Blade"


class TestTheChoice:
    def test_declining_leaves_it_as_itself(self, builder):
        """"**You may**". Every printed card in this family offers it."""
        game = position(builder, MASTERWORK, board=[BLADE])
        cast(game, MASTERWORK, say_yes=False)
        assert name_of(game, arrived(game).oid) == "Test Masterwork"

    def test_the_named_permanent_is_the_one_copied(self, builder):
        game = position(builder, MASTERWORK, board=[BLADE, OTHER])
        cast(game, MASTERWORK, copy_id=OTHER)
        assert name_of(game, arrived(game).oid) == "Test Other Blade"

    def test_with_nothing_to_copy_it_simply_enters(self, builder):
        """An empty pool asks nothing, which is the printed answer with no
        other Equipment on the table -- and the Masterwork is not on the
        battlefield yet when the pool is gathered, so it cannot copy itself."""
        game = position(builder, MASTERWORK)
        cast(game, MASTERWORK)
        assert name_of(game, arrived(game).oid) == "Test Masterwork"


class TestWithoutTheClause:
    """The control: an identical Equipment with no replacement enters blank and
    is asked nothing."""

    def test_it_enters_as_itself(self, builder):
        game = position(builder, PLAIN, board=[BLADE])
        cast(game, PLAIN)
        oid = next(
            o
            for o in game.state.battlefield
            if game.state.objects[o].def_id == PLAIN
        )
        assert name_of(game, oid) == "Test Plain Equipment"


class TestTheLoaderPlacesIt:
    def _card(self, replacement):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "You may have this enter as a copy of any Equipment.",
                "mana_cost": "{1}",
                "types": ["Artifact"],
                "subtypes": ["Equipment"],
                "replacements": [replacement],
            }
        )

    def test_a_well_formed_clause_loads(self):
        compile_card(
            self._card(
                {
                    "event": "self_enters_as_copy",
                    "copying": {"zone": "battlefield", "subtypes": ["Equipment"]},
                }
            )
        )

    def test_without_a_pool_it_is_refused(self):
        """A copy replacement with no pool asks about nothing and the permanent
        enters as itself -- a line of text it never performs."""
        with pytest.raises(DslError, match="needs 'copying'"):
            compile_card(self._card({"event": "self_enters_as_copy"}))

    def test_an_unknown_selector_key_is_refused(self):
        """Checked at load, because the pool is only gathered when a permanent
        actually enters -- otherwise a typo is a mid-game crash."""
        with pytest.raises(DslError):
            compile_card(
                self._card(
                    {
                        "event": "self_enters_as_copy",
                        "copying": {"zone": "battlefield", "nonsense": True},
                    }
                )
            )

    def test_the_pool_is_refused_on_another_event(self):
        """Ignored elsewhere, the card would print a copy it never makes."""
        with pytest.raises(DslError, match="read only by 'self_enters_as_copy'"):
            compile_card(
                self._card(
                    {
                        "event": "self_enters_tapped",
                        "copying": {"zone": "battlefield", "subtypes": ["Equipment"]},
                    }
                )
            )
