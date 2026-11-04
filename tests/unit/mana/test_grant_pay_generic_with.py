"""A static that hands spells convoke, improvise or delve: `grant_pay_generic_with`.

Inspiring Statuary: "Nonartifact spells you cast have improvise." The spell has
the keyword while it is being cast, so 702.126a applies to it as if it were
printed: each artifact its controller taps pays for {1} of its generic cost.
Without the static the Statuary is a vanilla artifact -- `pay_generic_with` was
read only off the spell's own card, so nothing on the battlefield could confer
it.

What would be wrong without each claim below:

- **The filter bites.** A nonartifact spell improvises and an artifact spell
  does not; written without the filter the Statuary is a stronger card.
- **"You cast."** An opponent's Statuary taps none of your artifacts for you.
- **While it is there.** The grant is read at every cast, so it wears off the
  moment the Statuary leaves.
- **Several keywords spend together.** A convoke or delve spell under the
  Statuary may tap creatures (or exile cards) *and* artifacts in one cast; the
  pick offers both, and each spent object pays once. Offering one keyword or
  the other would be a weaker card than the rules allow.
- **Two instances are one.** A printed-improvise spell under the Statuary is
  asked exactly what it was asked before.
- **The loader refuses** a grant with no filter, no currency, or the currency
  key on some other static.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.unit.mana.test_pay_generic_with import (
    cast_lines,
    oids_of,
    pick,
    settle,
    spends,
    tapped_count,
)

STATUARY = "t_statuary"  # {3} artifact: nonartifact spells you cast have improvise
STUDY = "t_study"  # {3}{U} sorcery, no keyword, draw two
RELIC = "t_relic"  # {4} artifact, no keyword
TRINKET = "t_trinket"  # a vanilla artifact
IMPROVISER = "t_improviser"  # {3}{U} sorcery with printed improvise
CONVOKER = "t_convoker"  # {3}{R} sorcery, convoke, 2 damage to a player
DELVER = "t_delver"  # {3}{U} sorcery, delve, draw two
BEAR = "t_bear"  # a green 2/2, not an artifact


def position(builder, spell, *, lands=("island", 2), trinkets=1, statuary=0, graveyard=0,
             bears=0, theirs=0):
    land, count = lands
    return (
        builder(players=2)
        .hand(0, [spell])
        .battlefield(0, [land] * count)
        .battlefield(0, [TRINKET] * trinkets)
        .battlefield(0, [STATUARY] * statuary)
        .battlefield(0, [BEAR] * bears)
        .battlefield(1, [STATUARY] * theirs)
        .graveyard(0, [BEAR] * graveyard)
        .build()
    )


class TestTheGrant:
    def test_a_nonartifact_spell_improvises(self, builder):
        """Two Islands cannot pay {3}{U}; two artifacts make up the difference,
        and the Statuary is one of the artifacts that may tap."""
        game = position(builder, STUDY, trinkets=2, statuary=1)
        assert spends(game) == {2}
        game.apply(cast_lines(game)[0])
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.context["purpose"] == "improvise"
        assert (decision.min_count, decision.max_count) == (2, 3)
        before = len(game.state.players[0].hand)
        pick(game, "improvise", oids_of(game, TRINKET)[:1] + oids_of(game, STATUARY))
        settle(game)
        assert tapped_count(game, TRINKET) == 1
        assert tapped_count(game, STATUARY) == 1
        assert len(game.state.players[0].hand) == before - 1 + 2, "cast one, drew two"

    def test_without_the_statuary_it_cannot(self, builder):
        game = position(builder, STUDY, trinkets=2)
        assert cast_lines(game) == []

    def test_an_artifact_spell_does_not(self, builder):
        """The filter: "nonartifact spells"."""
        game = position(builder, RELIC, lands=("island", 2), trinkets=1, statuary=1)
        assert cast_lines(game) == []

    def test_an_opponents_statuary_does_not(self, builder):
        game = position(builder, STUDY, trinkets=2, theirs=1)
        assert cast_lines(game) == []

    def test_it_wears_off_when_the_statuary_leaves(self, builder):
        game = position(builder, STUDY, trinkets=2, statuary=1)
        assert spends(game) == {2}
        move_object(game.state, oids_of(game, STATUARY)[0], Zone.GRAVEYARD)
        assert cast_lines(game) == []


class TestSeveralKeywordsSpendTogether:
    def test_convoke_and_improvise_in_one_pick(self, builder):
        """One Mountain pays {R}; the green Bear convokes {1} and the Trinket
        and the Statuary improvise the other two."""
        game = position(builder, CONVOKER, lands=("mountain", 1), trinkets=2, statuary=1, bears=1)
        assert spends(game) == {3}
        game.apply(cast_lines(game)[0])
        decision = game.pending()
        assert decision.context["purpose"] == "convoke+improvise"
        assert "convoke" in decision.prompt and "improvise" in decision.prompt
        assert (decision.min_count, decision.max_count) == (3, 4)
        pick(game, "convoke+improvise", oids_of(game, BEAR) + oids_of(game, TRINKET)[:1]
             + oids_of(game, STATUARY))
        settle(game)
        assert tapped_count(game, BEAR) == 1
        assert tapped_count(game, TRINKET) == 1
        assert tapped_count(game, STATUARY) == 1
        assert not game.state.stack

    def test_convoke_alone_cannot_reach_it(self, builder):
        game = position(builder, CONVOKER, lands=("mountain", 1), statuary=0, bears=1)
        assert cast_lines(game) == []

    def test_delve_and_improvise_in_one_pick(self, builder):
        game = position(builder, DELVER, lands=("island", 1), trinkets=2, statuary=1,
                        graveyard=1)
        assert spends(game) == {3}
        game.apply(cast_lines(game)[0])
        assert game.pending().context["purpose"] == "improvise+delve"
        bear = game.state.players[0].graveyard[0]
        pick(game, "improvise+delve", [*oids_of(game, TRINKET), bear])
        settle(game)
        assert tapped_count(game, TRINKET) == 2
        assert tapped_count(game, STATUARY) == 0
        assert game.state.objects[bear].zone is Zone.EXILE, "the Bear was exiled to delve"


class TestTwoInstancesAreOne:
    def test_printed_improvise_is_asked_as_before(self, builder):
        game = position(builder, IMPROVISER, lands=("island", 2), trinkets=2, statuary=1)
        assert spends(game) == {2}
        game.apply(cast_lines(game)[0])
        decision = game.pending()
        assert decision.context["purpose"] == "improvise"
        assert (decision.min_count, decision.max_count) == (2, 3)
        pick(game, "improvise", oids_of(game, TRINKET))
        settle(game)
        assert tapped_count(game, TRINKET) == 2
        assert not game.state.stack


def _statuary(**static) -> CardModel:
    ability = {
        "kind": "static",
        "effect": "grant_pay_generic_with",
        "pay_generic_with": "tap_artifacts",
        "affects_player": "you",
        "affects_spells": {"not_types": ["Artifact"]},
    }
    ability.update(static)
    ability = {k: v for k, v in ability.items() if v is not None}
    return CardModel.model_validate(
        {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "Nonartifact spells you cast have improvise.",
            "mana_cost": "{3}",
            "types": ["Artifact"],
            "abilities": [ability],
        }
    )


class TestTheLoader:
    def test_the_card_compiles(self, registry):
        static = registry.get(STATUARY).abilities[0].static
        assert static["pay_generic_with"] == "tap_artifacts"
        assert static["affects_spells"] == {"not_types": ["Artifact"]}

    def test_the_probe_compiles(self):
        compile_card(_statuary())

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            ({"affects_spells": None}, "affects_spells"),
            ({"affects_spells": {}}, "affects_spells"),
            ({"affects_spells": {"controller": "you"}}, "unsupported keys"),
            ({"pay_generic_with": None}, "pay_generic_with"),
            ({"affects_player": None}, "affects_player"),
        ],
    )
    def test_an_incomplete_grant_is_refused(self, change, message):
        with pytest.raises(DslError, match=message):
            compile_card(_statuary(**change))

    def test_the_currency_on_another_static_is_refused(self):
        with pytest.raises(DslError, match="pay_generic_with"):
            compile_card(
                _statuary(
                    effect="spend_mana_as_any_color",
                    affects_spells={"types": ["Planeswalker"]},
                )
            )
