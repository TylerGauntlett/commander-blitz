""""Whenever you cast a noncreature **or** Dragon spell" -- `any_of` in a
trigger filter.

    Firespitter Whelp — "Flying. Whenever you cast a noncreature or Dragon
    spell, this creature deals 1 damage to each opponent."

Every key of a trigger filter is ANDed, so the two printed halves written as one
filter, `{not_types: [Creature], subtypes: [Dragon]}`, say "noncreature Dragon
spell" -- a Kindred Dragon instant and nothing else. `any_types` is an or over
card types and cannot reach a subtype. Two triggers, one per half, are a
different card: rule 603.2 fires a triggered ability once per occurrence of its
event, and one cast is one occurrence, so a noncreature Dragon spell triggers
the printed Whelp once and the two-trigger version twice.

`any_of` is the disjunction the effect-side selector and the static filters
already have (`selectors.matches`, `characteristics._matches_printed`), and
`triggers.matches_card_filter` recurses the same way: each branch is a trigger
filter asked about the same subject, and the keys beside `any_of` apply to all
of them.

What is pinned below, and each is a way this could be silently wrong:

1. A noncreature spell and a Dragon creature spell each fire it once.
2. A non-Dragon creature spell does not.
3. A spell that answers both branches fires it once, not twice. (The witness
   is a creature-or-Dragon watcher and a Dragon creature spell; a Kindred
   Dragon instant is the same both-branches case for the printed Whelp.)
4. Keys beside `any_of` still narrow every branch.
5. The loader holds each branch to `TRIGGER_FILTER_KEYS`, and refuses an
   `any_of` of fewer than two branches.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.triggers import matches_card_filter
from tests.conftest import only_oid
from tests.unit.triggers.test_magecraft import cast

WHELP = "t_any_of_whelp"
OX = "t_any_of_ox"  # a non-Dragon creature spell
DRAKE = "t_any_of_drake"  # a Dragon creature spell
SPARK = "t_any_of_spark"  # a plain noncreature spell
OVERLAP = "t_any_of_overlap"  # "a creature or Dragon spell": a Drake answers both


def position(builder, spell: str, watcher: str = WHELP):
    """``watcher`` on your battlefield, ``spell`` in hand, a Mountain to cast it."""
    game = (
        builder(players=2)
        .battlefield(0, [watcher, "mountain"])
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, [spell])
        .hand(1, ["t_plain_instant"])
        .build()
    )
    return game


def damage_dealt(builder, spell: str, watcher: str = WHELP) -> int:
    game = position(builder, spell, watcher)
    before = game.state.players[1].life
    cast(game, spell)
    return before - game.state.players[1].life


class TestTheWhelpFiresOncePerMatchingSpell:
    def test_a_noncreature_spell(self, builder):
        assert damage_dealt(builder, SPARK) == 1

    def test_a_dragon_creature_spell(self, builder):
        assert damage_dealt(builder, DRAKE) == 1

    def test_a_non_dragon_creature_spell_does_not(self, builder):
        assert damage_dealt(builder, OX) == 0

    def test_a_spell_answering_both_branches_fires_once(self, builder):
        """The two-trigger spelling would deal 2 here; one cast is one event."""
        assert damage_dealt(builder, DRAKE, OVERLAP) == 1


class TestTheMatcher:
    @pytest.fixture
    def board(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [WHELP, OX, DRAKE])
            .battlefield(1, [DRAKE])
            .library(0, ["forest"] * 5)
            .library(1, ["forest"] * 5)
            .build()
        )
        state = game.state
        whelp = state.objects[only_oid(game, WHELP)]
        mine = next(o.oid for o in state.objects.values() if o.def_id == DRAKE and o.controller == 0)
        theirs = next(o.oid for o in state.objects.values() if o.def_id == DRAKE and o.controller == 1)
        return state, whelp, only_oid(game, OX), mine, theirs

    def test_either_branch_answers(self, board):
        state, whelp, ox, mine, _ = board
        filt = {"any_of": [{"subtypes": ["Ox"]}, {"subtypes": ["Dragon"]}]}
        assert matches_card_filter(state, ox, filt, whelp)
        assert matches_card_filter(state, mine, filt, whelp)
        assert not matches_card_filter(state, whelp.oid, {"any_of": [{"subtypes": ["Ox"]}, {"not_types": ["Creature"]}]}, whelp)

    def test_a_key_beside_it_narrows_every_branch(self, board):
        state, whelp, _, mine, theirs = board
        filt = {"controller": "you", "any_of": [{"subtypes": ["Ox"]}, {"subtypes": ["Dragon"]}]}
        assert matches_card_filter(state, mine, filt, whelp)
        assert not matches_card_filter(state, theirs, filt, whelp)


def _trigger_card(filt) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_any_of_probe",
            "name": "Any Of Probe",
            "oracle_text": "Whenever you cast a spell, you gain 1 life.",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "triggered",
                    "trigger": {"event": "spell_cast", "controller": "you", "filter": filt},
                    "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }
    )


class TestTheLoader:
    def test_the_whelp_shape_loads(self):
        compile_card(_trigger_card({"any_of": [{"not_types": ["Creature"]}, {"subtypes": ["Dragon"]}]}))

    def test_a_branch_key_the_matcher_never_reads_is_refused(self):
        with pytest.raises(DslError, match="would load and be ignored"):
            compile_card(_trigger_card({"any_of": [{"not_types": ["Creature"]}, {"not_colors": ["W"]}]}))

    @pytest.mark.parametrize("branches", [[{"subtypes": ["Dragon"]}], []])
    def test_fewer_than_two_branches_is_refused(self, branches):
        with pytest.raises(DslError, match="any_of"):
            compile_card(_trigger_card({"any_of": branches}))
