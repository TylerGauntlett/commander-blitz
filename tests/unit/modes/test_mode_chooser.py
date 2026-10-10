"""The Warring Triad — "Target player adds one mana of any color."

The player who *adds* the mana is the one who picks its colour. The engine
spells "one mana of any color" as a `choose_mode` over five `add_mana` modes
(Arcane Signet, Command Tower), and `op_choose_mode` asked `ctx.controller`
every time — so the mana landed in the targeted player's pool in a colour their
opponent had chosen for them. That is a strictly better card than the one
printed, and on a board where both players want the same colour it looks
completely normal.

`ask_mode` always took an arbitrary chooser, exactly as `ask_objects` did for
Fact or Fiction's pile-splitter, so "somebody else decides" cost nothing but the
wiring — no new `DecisionKind`.

The subtle half is *when* the question is asked. Rules 601.2b and 602.2b put
mode selection at the moment a spell or ability goes on the stack, and
`CardDef.cast_time_modes` pre-answers it there. That is right for an ordinary
modal card and wrong for this one twice over: the controller would be the one
answering, and the target may not even be fixed in a way the chooser can read
yet. So `carddef.asks_another_player` keeps a chooser-carrying mode out of
`cast_time_modes`, which pushes it to resolution — the same place a *nested*
`choose_mode` already lives, and for the same reason.

`t_selfish_rock` is the counterfactual: byte-for-byte the donor rock without the
`chooser`, so every difference asserted below is that one key.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.enums import ActionKind, DecisionKind
from tests.conftest import only_oid

DONOR = "t_donor_rock"
SELFISH = "t_selfish_rock"


def board(builder, card_id: str):
    game = (
        builder(players=2)
        .battlefield(0, [card_id])
        .hand(0, ["forest"])
        .build()
    )
    return game, only_oid(game, card_id)


def activate(game, oid: int, *, at: int):
    """Activate the rock aimed at player ``at``.

    Both targets are offered, and which one is chosen is the entire experiment:
    pointed at yourself the two cards are indistinguishable, because the
    controller and the chooser are the same seat.
    """
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE
        and a.source == oid
        and any(t.kind == "player" and t.id == at for t in a.targets)
    )
    game.apply(action)
    return game


def run_to_mode_choice(game, oid: int, *, at: int):
    """Activate at ``at``, then advance until somebody is asked to choose a mode."""
    activate(game, oid, at=at)
    for _ in range(200):
        decision = game.pending()
        if decision is None:
            return None
        if decision.kind is DecisionKind.CHOOSE_MODE:
            return decision
        if decision.kind is DecisionKind.PRIORITY:
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
            continue
        return decision
    return None


class TestWhoIsAsked:
    """The claim the whole capability exists for."""

    def test_the_targeted_player_chooses_the_colour(self, builder):
        game, oid = board(builder, DONOR)
        decision = run_to_mode_choice(game, oid, at=1)
        assert decision is not None, "nobody was asked to choose a colour"
        assert decision.kind is DecisionKind.CHOOSE_MODE
        assert decision.player == 1, "the player adding the mana picks its colour"

    def test_without_a_chooser_the_controller_picks(self, builder):
        """The counterfactual, and the behaviour every other modal card wants."""
        game, oid = board(builder, SELFISH)
        decision = run_to_mode_choice(game, oid, at=1)
        assert decision is not None
        assert decision.kind is DecisionKind.CHOOSE_MODE
        assert decision.player == 0

    def test_pointed_at_yourself_you_choose(self, builder):
        """The control: with controller and chooser the same seat, no difference."""
        game, oid = board(builder, DONOR)
        decision = run_to_mode_choice(game, oid, at=0)
        assert decision is not None
        assert decision.player == 0


class TestWhenItIsAsked:
    """601.2b pre-answers ordinary modal cards; this one has to wait."""

    def test_a_chooser_defers_the_mode_to_resolution(self, registry):
        ability = registry.get(DONOR).abilities[0]
        assert ability.cast_time_modes is None

    def test_without_one_the_mode_is_settled_on_activation(self, registry):
        ability = registry.get(SELFISH).abilities[0]
        assert ability.cast_time_modes is not None


class TestTheLoaderRefusesTheImpossibleCase:
    def test_a_mana_ability_may_not_hand_off_its_choice(self):
        """605.1a/605.3: no stack, no window in which to ask somebody else.

        The cards that look like they want this -- The Warring Triad included --
        target, and a mana ability cannot target, so they were never mana
        abilities to begin with.
        """
        from commanderblitz.cards.loader import compile_card
        from commanderblitz.cards.schema import CardModel
        from commanderblitz.engine.errors import DslError

        card = CardModel.model_validate(
            {
                "id": "t_bad_mana_ability",
                "name": "Test Bad Mana Ability",
                "oracle_text": "{T}: Add one mana of any color.",
                "mana_cost": "{2}",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "activated",
                        "text": "{T}: Add one mana of any color.",
                        "is_mana_ability": True,
                        "cost": {"tap": True},
                        "effects": [
                            {
                                "op": "choose_mode",
                                "chooser": "opponent",
                                "modes": [
                                    {"label": "W", "effects": [{"op": "add_mana", "mana": "{W}"}]},
                                    {"label": "U", "effects": [{"op": "add_mana", "mana": "{U}"}]},
                                ],
                            }
                        ],
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="another player"):
            compile_card(card, source="test")
