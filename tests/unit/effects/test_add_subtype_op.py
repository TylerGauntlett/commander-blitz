"""Making one permanent a Vampire, as a one-shot rather than a static.

(The tests below say Bear rather than Vampire: `t_lord` is the test pool's
"Other Bears you control get +1/+1", which is Captivating Vampire's first line
with one word changed.)

"Gain control of target creature. **It becomes a Vampire in addition to its
other types.**" Captivating Vampire's second sentence, and the reason the first
one is worth having: the stolen creature joins the swarm the card is already
buffing.

Two things about this are easy to get wrong, and both would load clean:

- **It is not the `add_subtype` static.** They read identically in English. A
  static applies continuously to whatever currently matches its filter and stops
  the instant its source leaves the battlefield; this is written onto one object
  and stays there. Captivating Vampire wants the second: the creature stays a
  Vampire after the Vampire that converted it dies.
- **A static's filter has to see it.** `_matches` reads the *printed* face on
  purpose, so that no static can depend on another static's output. A subtype
  recorded on the object is a pipeline input rather than an output, which is
  what makes it safe to let through — and without letting it through, the card's
  own anthem would ignore the creature it had just converted, which is most of
  the card.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_subtypes, change_control
from commanderblitz.engine.zones import destroy


def a_bird_and_a_lord(builder):
    """Player 0 has a lord for one subtype; player 1 has a creature without it.

    `t_lord` is "Other Bears you control get +1/+1" in the test pool -- the same
    shape as Captivating Vampire's first line, with Bear standing in for
    Vampire. `t_flyer` is a Bird, so it starts outside the anthem.
    """
    game = (
        builder(players=2).battlefield(0, ["t_lord"]).battlefield(1, ["t_flyer"]).build()
    )
    lord = next(
        oid for oid in game.state.battlefield if game.state.objects[oid].def_id == "t_lord"
    )
    bird = next(
        oid for oid in game.state.battlefield if game.state.objects[oid].def_id == "t_flyer"
    )
    return game, lord, bird


class TestWhatItAdds:
    def test_the_subtype_is_added_not_substituted(self, builder):
        game, _lord, bird = a_bird_and_a_lord(builder)
        add_subtypes(game.state, bird, ["Bear"])

        c = chars(game.state, bird)
        assert "Bear" in c.subtypes
        assert "Bird" in c.subtypes, "'in addition to its other types' is the whole clause"
        assert "Creature" in c.types, "a subtype change is not a type change"

    def test_adding_the_same_subtype_twice_is_idempotent(self, builder):
        game, _lord, bird = a_bird_and_a_lord(builder)
        add_subtypes(game.state, bird, ["Bear"])
        assert add_subtypes(game.state, bird, ["Bear"]) == ()
        assert game.state.objects[bird].added_subtypes == ("Bear",)

    def test_a_card_off_the_battlefield_is_not_changed(self, builder):
        game = builder(players=2).hand(1, ["t_bear"]).build()
        card = game.state.players[1].hand[0]
        assert add_subtypes(game.state, card, ["Vampire"]) == ()


class TestWhatSeesIt:
    def test_a_lord_you_control_now_buffs_it(self, builder):
        """The point of the card: converted, stolen, and then pumped."""
        game, _lord, bird = a_bird_and_a_lord(builder)
        printed = chars(game.state, bird).power

        change_control(game.state, bird, 0)
        assert chars(game.state, bird).power == printed, "not a Bear yet"

        add_subtypes(game.state, bird, ["Bear"])
        assert chars(game.state, bird).power == printed + 1

    def test_it_keeps_the_subtype_after_the_converter_dies(self, builder):
        """A static would end with its source. This does not, which is the
        difference between the op and the static of the same name."""
        game, lord, bird = a_bird_and_a_lord(builder)
        add_subtypes(game.state, bird, ["Bear"])
        destroy(game.state, lord)

        assert "Bear" in chars(game.state, bird).subtypes

    def test_leaving_the_battlefield_takes_it_back(self, builder):
        """A permanent that leaves and returns is a new object, printed face and
        all -- the same contract counters and `chosen_type` have."""
        game, _lord, bird = a_bird_and_a_lord(builder)
        add_subtypes(game.state, bird, ["Bear"])
        destroy(game.state, bird)

        assert game.state.objects[bird].added_subtypes == ()


class TestTheLoaderRefuses:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_converter",
                "name": "Test Converter",
                "mana_cost": "{1}{B}",
                "types": ["Sorcery"],
                "oracle_text": "Target creature becomes a Vampire in addition to its other types.",
                "targets": [
                    {"id": "t1", "kind": "permanent", "selector": {"types": ["Creature"]}}
                ],
                "spell_effects": [effect],
            }
        )

    def test_it_takes_the_ordinary_form(self):
        compile_card(
            self._card(
                {"op": "add_subtype", "subtypes": ["Vampire"], "objects": {"target": "t1"}}
            )
        )

    def test_naming_no_subtype_is_refused(self):
        with pytest.raises(DslError, match="needs 'subtypes'"):
            compile_card(self._card({"op": "add_subtype", "objects": {"target": "t1"}}))

    def test_naming_nothing_to_change_is_refused(self):
        with pytest.raises(DslError, match="nothing to change"):
            compile_card(self._card({"op": "add_subtype", "subtypes": ["Vampire"]}))

    def test_a_card_type_is_refused_rather_than_dropped(self):
        with pytest.raises(DslError, match="subtypes only"):
            compile_card(
                self._card(
                    {
                        "op": "add_subtype",
                        "subtypes": ["Vampire"],
                        "types": ["Artifact"],
                        "objects": {"target": "t1"},
                    }
                )
            )
