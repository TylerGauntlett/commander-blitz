""""Choose one that hasn't been chosen —"

    Henrika Domnathi — "At the beginning of combat on your turn, choose one
    that hasn't been chosen — • Each player sacrifices a creature of their
    choice. • You draw a card and you lose 1 life. • Transform Henrika."

`op_choose_mode` rebuilt its label list unconditionally on every resolution and
handed the whole thing to `ask_mode`, and nothing anywhere recorded which modes a
permanent had used. A mode was `{label, effects}`; the only mode-related key was
entwine's `all_if`, which forces *every* mode — the opposite question.

Without the clause the card is materially stronger, not merely different: it
could transform every combat, or drain every combat, forever. That is why the
authoring worker refused to write it rather than shipping the unguarded version.

**Spent modes are struck off, not offered and ignored.** An ability that listed a
used mode and then did nothing would read on screen as a mode that fizzled, and
the point of the printed clause is that the card runs out of things to do.

**Recorded as ordinary `flags` on the source**, which gives the right lifetime
for free: `reset_permanent_state` clears them on a zone change, and 712.13a makes
a permanent that left and came back a new object that may choose again — the same
rule flip and transform already lean on. Keyed by printed label rather than
index, so reordering a card's modes cannot silently re-open a spent one.

**Refused on a spell.** A spell's top-level modes are chosen at cast time
(601.2b, `Game._ask_modes`), a path this filter never sees — so the spent modes
would still be offered and the flag written for nothing. It is meaningless there
anyway: a spell is a new object each cast and remembers nothing.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.errors import DslError
from tests.conftest import oids_of

HENRIKA = "t_henrika"  # two modes, "that hasn't been chosen"
GAIN = "Gain 1 life"
DRAW = "Draw and lose 1"


def board(builder):
    """Enough library and turns for three of the controller's combats.

    The walk below crosses whole turns, so a short library or a low turn cap
    ends the game before the second choice is ever offered -- and the test would
    then report "nothing offered" for a reason that has nothing to do with the
    modes.
    """
    return (
        builder(players=2)
        .battlefield(0, [HENRIKA])
        .library(0, ["swamp"] * 60)
        .library(1, ["swamp"] * 60)
        .active(0)
        .max_turns(40)
        .step(Step.UPKEEP)
        .build()
    )


def offered_modes(game, limit: int = 400) -> list[str]:
    """Walk to the next beginning-of-combat choice and report its labels.

    Answers *every* other decision on the way, not just priority: the walk
    crosses whole turns, so it meets cleanup discards and combat declarations
    too, and a walker that gave up on those would report "no modes offered" for
    a card that was about to offer two.
    """
    for _ in range(limit):
        decision = game.pending()
        if decision is None or game.over:
            return []
        if decision.kind is DecisionKind.CHOOSE_MODE:
            return [o.label for o in decision.options]
        actions = game.legal_actions()
        if not actions:
            return []
        preferred = (
            [a for a in actions if a.kind is ActionKind.PASS]
            or [a for a in actions if a.kind is ActionKind.FINISH_DECLARATION]
            or [a for a in actions if a.kind is ActionKind.NO]
            or actions
        )
        game.apply(preferred[0])
    return []


def take(game, label: str) -> None:
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.CHOOSE_MODE
    index = [o.label for o in decision.options].index(label)
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE and a.choice == index
        )
    )


def run_on(game, turns: int = 4) -> None:
    """Play forward a few of the controller's turns, answering passively."""
    stop = game.state.turn + turns
    for _ in range(600):
        if game.over or game.state.turn >= stop:
            return
        decision = game.pending()
        if decision is None:
            return
        actions = game.legal_actions()
        if not actions:
            return
        preferred = (
            [a for a in actions if a.kind is ActionKind.PASS]
            or [a for a in actions if a.kind is ActionKind.FINISH_DECLARATION]
            or [a for a in actions if a.kind is ActionKind.NO]
            or actions
        )
        game.apply(preferred[0])


class TestASpentModeIsNotOffered:
    def test_both_modes_are_offered_first(self, builder):
        game = board(builder)
        assert sorted(offered_modes(game)) == sorted([GAIN, DRAW])

    def test_the_chosen_one_is_struck_off(self, builder):
        game = board(builder)
        offered_modes(game)
        take(game, GAIN)

        henrika = oids_of(game, HENRIKA)[0]
        assert "mode_chosen:Gain 1 life" in game.state.objects[henrika].flags

    def test_the_other_mode_is_untouched(self, builder):
        game = board(builder)
        offered_modes(game)
        take(game, GAIN)

        henrika = oids_of(game, HENRIKA)[0]
        assert "mode_chosen:Draw and lose 1" not in game.state.objects[henrika].flags

    def test_the_remaining_mode_is_taken_next_combat(self, builder):
        """The claim the card actually makes, rather than the flag behind it.

        Asserted on the board rather than on a decision: with one mode left
        there is nothing to choose between, and `ask_mode` does not stop to ask
        a question with a single answer. So the second combat takes the survivor
        without prompting -- correct, and invisible to a test that waited for a
        prompt.
        """
        game = board(builder)
        offered_modes(game)
        take(game, GAIN)
        henrika = oids_of(game, HENRIKA)[0]

        run_on(game)

        assert "mode_chosen:Draw and lose 1" in game.state.objects[henrika].flags

    def test_an_exhausted_ability_does_nothing(self, builder):
        game = board(builder)
        offered_modes(game)
        take(game, GAIN)
        henrika = oids_of(game, HENRIKA)[0]
        run_on(game)
        assert len(game.state.objects[henrika].flags) == 2, "both modes spent"

        # From here every later combat has nothing left to choose. Life is the
        # clean witness: the surviving mode costs 1 life, and nothing else in
        # this position changes a life total. The library is not, because the
        # draw step moves it every turn whatever the ability does.
        life = game.state.players[0].life
        run_on(game)

        assert game.state.players[0].life == life
        assert len(game.state.objects[henrika].flags) == 2, "and nothing new was spent"


class TestTheFlagsHaveTheRightLifetime:
    def test_leaving_the_battlefield_clears_them(self, builder):
        """712.13a -- a permanent that comes back is a new object."""
        from automtg.engine.zones import destroy

        game = board(builder)
        henrika = oids_of(game, HENRIKA)[0]
        game.state.objects[henrika].flags.add("mode_chosen:Gain 1 life")

        destroy(game.state, henrika)

        assert game.state.objects[henrika].flags == set()


class TestTheLoaderRefusesItOnASpell:
    def _spell(self) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_bad_once_each",
                "name": "Bad Once Each",
                "mana_cost": "{1}",
                "types": ["Instant"],
                "oracle_text": "Choose one that hasn't been chosen —",
                "spell_effects": [
                    {
                        "op": "choose_mode",
                        "count": 1,
                        "once_each": True,
                        "modes": [
                            {"label": "A", "effects": [{"op": "draw", "player": "you"}]},
                            {"label": "B", "effects": [{"op": "draw", "player": "you"}]},
                        ],
                    }
                ],
            }
        )

    def test_a_spell_cannot_remember_its_modes(self):
        with pytest.raises(DslError, match="remembers nothing"):
            compile_card(self._spell())

    def test_a_permanents_ability_can(self, registry):
        """The same op inside an ability is exactly what the card wants."""
        ability = registry.get(HENRIKA).abilities[0]
        assert ability.effects[0]["once_each"] is True
