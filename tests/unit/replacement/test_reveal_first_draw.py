"""`reveal_first_draw` and `reveals_first_draw` -- a card revealed *as* it is drawn.

Witness: Inquisitor Eisenhorn, "You may reveal the first card you draw each turn
as you draw it. Whenever you reveal an instant or sorcery card this way, create
Cherubael." Primitive Etchings is the same pair without the "may".

The reveal is made at the moment of the draw, and only of the turn's first
card: the same fact miracle (702.94a) is built on, read at the same seam
(`replacements._draw_one`). Without it the nearest shape was a `draw` trigger
with `nth: 1` that revealed on resolution -- the card is no longer being drawn
by then, the reveal is no longer optional at the draw, and the trigger fires on
every first draw rather than on the reveal. "This way" is the other half: the
trigger hears only the reveal its own permanent's static let its controller
make, which is what `granted_by` on the event says.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import AbilityModel, CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.replacements import draw as draw_with_replacements
from tests.conftest import _default_answer, oids_of, settle_completely

INQUISITOR = "t_rfd_inquisitor"  # may reveal; instant or sorcery -> Cherubael
ETCHINGS = "t_rfd_etchings"      # must reveal; creature -> draw a card
CHERUBAEL = "cherubael_4_4_b_flying"
BOLT = "lightning_bolt"          # an instant
WRATH = "t_miracle"              # a sorcery with miracle {W}
BEAR = "grizzly_bears"           # a creature
PLAINS = "plains"


def run(game, pid: int, answers: list[bool]) -> list:
    """Draw one card for ``pid``, answering yes/no questions in order; return them."""
    gen = draw_with_replacements(game.state, pid, 1)
    asked = []
    send = None
    queue = list(answers)
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return asked
        asked.append(decision)
        send = [0] if (queue.pop(0) if queue else False) else [1]


def position(builder, *, top: str, granters=(INQUISITOR,), seat: int = 0,
             drawer: int = 0, drawn_already: int = 0, lands: int = 0):
    b = builder(players=2)
    if granters:
        b = b.battlefield(seat, list(granters))
    if lands:
        b = b.battlefield(drawer, [PLAINS] * lands)
    game = (
        b.library(drawer, [top] + [PLAINS] * 10)
        .library(1 - drawer, [top] + [PLAINS] * 10)
        .build(advance=False)
    )
    game.state.cards_drawn_this_turn[drawer] = drawn_already
    return game


def reveals(game) -> list:
    return [e for e in game.state.events if e.type == EventType.REVEALED_FIRST_DRAW]


def pending_sources(game) -> list[str]:
    return [game.state.objects[t.source_oid].def_id for t in game.state.pending_triggers]


class TestTheMayReveal:
    def test_the_first_draw_asks_and_a_yes_reveals_it(self, builder):
        game = position(builder, top=BOLT)
        asked = run(game, 0, [True])

        assert [d.kind for d in asked] == [DecisionKind.MAY]
        (event,) = reveals(game)
        assert event.player == 0 and event.data["card"] == BOLT
        assert game.state.objects[event.data["oid"]].def_id == BOLT
        assert event.data["granted_by"] == oids_of(game, INQUISITOR, 0)

    def test_a_no_reveals_nothing_and_triggers_nothing(self, builder):
        game = position(builder, top=BOLT)
        run(game, 0, [False])
        assert reveals(game) == []
        assert game.state.pending_triggers == []

    def test_the_card_is_drawn_either_way(self, builder):
        game = position(builder, top=BOLT)
        run(game, 0, [False])
        assert any(game.state.objects[o].def_id == BOLT for o in game.state.players[0].hand)


class TestTheScope:
    def test_a_second_draw_is_not_offered(self, builder):
        """"The **first** card you draw each turn"."""
        game = position(builder, top=BOLT, drawn_already=1)
        assert run(game, 0, [True]) == []
        assert reveals(game) == []

    def test_without_the_static_nothing_is_asked(self, builder):
        game = position(builder, top=BOLT, granters=())
        assert run(game, 0, [True]) == []

    def test_an_opponents_draw_is_not_offered(self, builder):
        """"…the first card **you** draw": the granter's controller only."""
        game = position(builder, top=BOLT, seat=0, drawer=1)
        assert run(game, 1, [True]) == []
        assert reveals(game) == []


class TestTheTriggerFiltersTheRevealedCard:
    @pytest.mark.parametrize("top", [BOLT, WRATH])
    def test_an_instant_or_sorcery_triggers(self, builder, top):
        game = position(builder, top=top)
        run(game, 0, [True])
        assert pending_sources(game) == [INQUISITOR]

    @pytest.mark.parametrize("top", [BEAR, PLAINS])
    def test_anything_else_is_revealed_and_triggers_nothing(self, builder, top):
        game = position(builder, top=top)
        run(game, 0, [True])
        assert len(reveals(game)) == 1
        assert game.state.pending_triggers == []


class TestThisWay:
    """"Whenever you reveal a card **this way**": only its own static's reveal."""

    def test_a_miracle_reveal_is_not_this_way(self, builder):
        """Declining Eisenhorn's reveal still lets miracle reveal the card, and
        that reveal is miracle's, not the Inquisitor's."""
        game = position(builder, top=WRATH, lands=1)
        asked = run(game, 0, [False, False])
        assert len(asked) == 2, "the reveal, then the miracle cast"
        assert reveals(game) == []
        assert game.state.pending_triggers == []

    def test_a_reveal_for_the_inquisitor_still_offers_miracle(self, builder):
        game = position(builder, top=WRATH, lands=1)
        asked = run(game, 0, [True, False])
        assert len(asked) == 2
        assert pending_sources(game) == [INQUISITOR]

    def test_two_granters_reveal_once_and_both_hear_it(self, builder):
        """A "must" beside a "may" leaves nothing to ask, and one revealed
        card is revealed for both."""
        game = position(builder, top=BOLT, granters=(INQUISITOR, ETCHINGS))
        assert run(game, 0, [True]) == []
        (event,) = reveals(game)
        assert sorted(event.data["granted_by"]) == sorted(
            oids_of(game, INQUISITOR, 0) + oids_of(game, ETCHINGS, 0)
        )
        assert pending_sources(game) == [INQUISITOR], "a Bolt is no creature"


class TestTheMandatoryReveal:
    def test_nothing_is_asked_and_the_card_is_revealed(self, builder):
        game = position(builder, top=BEAR, granters=(ETCHINGS,))
        assert run(game, 0, [False]) == []
        assert len(reveals(game)) == 1
        assert pending_sources(game) == [ETCHINGS]


class TestThroughTheDrawStep:
    def test_the_draw_step_offers_the_reveal_and_makes_cherubael(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [INQUISITOR])
            .library(0, [BOLT] + [PLAINS] * 20)
            .library(1, [PLAINS] * 20)
            .build()
        )
        for _ in range(400):
            decision = game.pending()
            assert decision is not None, "the reveal was never offered"
            yes = [a for a in game.legal_actions() if a.kind is ActionKind.YES]
            if yes and decision.player == 0:
                game.apply(yes[0])
                break
            game.apply(_default_answer(game, decision))
        settle_completely(game)
        assert len(oids_of(game, CHERUBAEL, 0)) == 1


class TestTheLoaderRefusesTheSilentFailures:
    """Each of these would load clean and play as a different card."""

    STATIC = dict(kind="static", text="x", effect="reveal_first_draw",
                  affects_player="you", reveal_optional=True)
    TRIGGER = dict(kind="triggered", text="y",
                   trigger={"event": "reveals_first_draw",
                            "filter": {"any_types": ["Instant", "Sorcery"]}},
                   effects=[{"op": "draw", "amount": {"const": 1}}])

    def _card(self, *abilities):
        return CardModel(
            id="t_bad", name="Bad", mana_cost="{3}", types=["Creature"],
            power=1, toughness=1, abilities=[AbilityModel(**a) for a in abilities],
        )

    def test_the_well_formed_pair_loads(self):
        card = compile_card(self._card(self.STATIC, self.TRIGGER))
        assert card.abilities[0].static["reveal_optional"] is True

    def test_a_trigger_without_the_static_is_refused(self):
        with pytest.raises(DslError, match="this way"):
            compile_card(self._card(self.TRIGGER))

    def test_a_trigger_scoped_to_self_is_refused(self):
        trigger = dict(self.TRIGGER, trigger={"event": "reveals_first_draw", "source": "self"})
        with pytest.raises(DslError, match="source"):
            compile_card(self._card(self.STATIC, trigger))

    def test_an_opponents_reveal_is_refused(self):
        trigger = dict(self.TRIGGER, trigger={"event": "reveals_first_draw",
                                              "controller": "opponent"})
        with pytest.raises(DslError, match="controller"):
            compile_card(self._card(self.STATIC, trigger))

    def test_a_reveal_granted_to_opponents_is_refused(self):
        with pytest.raises(DslError, match="affects_player"):
            compile_card(self._card(dict(self.STATIC, affects_player="opponent")))

    def test_a_filter_on_the_static_is_refused(self):
        with pytest.raises(DslError, match="trigger's filter"):
            compile_card(self._card(dict(self.STATIC, affects={"types": ["Instant"]})))

    def test_reveal_optional_elsewhere_is_refused(self):
        with pytest.raises(DslError, match="reveal_optional"):
            compile_card(self._card(dict(kind="static", text="z", effect="no_hand_limit",
                                         affects_player="you", reveal_optional=True)))
