"""Rewriting a word inside another card's text -- layer 3 (613.1c).

"Change the text of that creature by replacing all instances of one creature
type with Vampire." New Blood.

The engine had no layer 3 at all: `_compute` went straight from copy effects to
the type-granting statics, and nothing anywhere rewrote a word inside another
object's rules text. So the thing to pin is not that *a* type changed -- it is
that **all instances** did, and that they changed everywhere the old word was
being read.

`add_subtype` is the near miss and the reason a half-built version of this would
look right. "It becomes a Vampire in addition to its other types" (Captivating
Vampire) adds the word and leaves the old one, so a Goblin under it still
answers to Goblin lords, still dies to Goblin removal, and its own rules text is
untouched. New Blood *replaces* the word. Written as an `add_subtype` the card
loads, resolves, puts "Vampire" on the type line and is a different and much
weaker card -- which is exactly why the authoring worker refused to approximate
it rather than shipping something that looked implemented.

Four readers have to agree, and each is its own class below, because each one
can be missed on its own and the failure is silent every time:

- **`chars()`** -- the derived type line, via `_compute`. The obvious one, and
  the only one a naive implementation gets.
- **`_matches_printed`** -- what a static filter belonging to *another card*
  sees. A Vampire lord's anthem takes this path and never comes through
  `_compute`. Miss it and New Blood converts a creature no lord can find, which
  is the whole reason to cast it in a Vampire deck.
- **`abilities_of`** -- the words inside the object's *own* abilities. This is
  the half that turns a stolen Goblin lord into a Vampire lord, and it has to
  survive `_derived_abilities` too: substituting only on the fast path would
  make a text-changed permanent revert the moment any `grant_ability` static
  appeared anywhere on the battlefield.
- **`stack.ability_of`** -- how an activated or triggered ability is looked up
  when it resolves. The statics on a text-changed permanent already come through
  `abilities_of`; without this seam the activated and triggered halves of the
  same card would keep their old tribe.

`added_subtypes` is layer 4 and still applies *on top*: the two are different
effects and a creature can be under both.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import abilities_of, chars
from automtg.engine.enums import Zone
from automtg.engine.serialize import card_view
from automtg.engine.text_change import displayed, printed_type_instances, substitute
from automtg.engine.zones import move_object


def board(builder, mine=(), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .hand(0, ["forest"])
        .hand(1, ["forest"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .build()
    )


def oid_of(game, card_id: str, pid: int = 0) -> int:
    return next(
        obj.oid for obj in game.state.battlefield_objects(pid) if obj.def_id == card_id
    )


def change_text(game, oid: int, old: str, new: str = "Vampire") -> None:
    """Apply the text change directly, as `op_change_text` writes it.

    Directly rather than by casting `t_new_blood`: the op's own contribution is
    the *prompt* -- which types it offers -- and that is asserted on its own in
    `TestWhichTypesAreOffered`. Everything below is about what the recorded
    change then does to the four readers.
    """
    game.state.objects[oid].text_changes = (*game.state.objects[oid].text_changes, (old, new))
    game.state.bump_chars()


class TestTheSubtypeLine:
    def test_the_old_type_is_gone_and_the_new_one_is_there(self, builder):
        game = board(builder, mine=["t_plain_goblin"])
        goblin = oid_of(game, "t_plain_goblin")
        change_text(game, goblin, "Goblin")

        c = chars(game.state, goblin)
        assert "Vampire" in c.subtypes
        assert "Goblin" not in c.subtypes, (
            "a text change replaces the word; add_subtype is the one that keeps both"
        )

    def test_a_type_the_card_does_not_have_changes_nothing(self, builder):
        game = board(builder, mine=["t_plain_goblin"])
        goblin = oid_of(game, "t_plain_goblin")
        change_text(game, goblin, "Zombie")
        assert chars(game.state, goblin).subtypes == {"Goblin"}

    def test_changes_apply_in_order(self, builder):
        """612.4: timestamp order, and the second one reads the first one's output."""
        game = board(builder, mine=["t_plain_goblin"])
        goblin = oid_of(game, "t_plain_goblin")
        change_text(game, goblin, "Goblin", "Vampire")
        change_text(game, goblin, "Vampire", "Zombie")

        c = chars(game.state, goblin)
        assert "Zombie" in c.subtypes
        assert "Vampire" not in c.subtypes and "Goblin" not in c.subtypes

    def test_it_wears_off_when_the_permanent_leaves(self, builder):
        """A permanent that leaves and comes back is a new object with its printed text."""
        game = board(builder, mine=["t_plain_goblin"])
        goblin = oid_of(game, "t_plain_goblin")
        change_text(game, goblin, "Goblin")
        move_object(game.state, goblin, Zone.GRAVEYARD)

        assert game.state.objects[goblin].text_changes == ()


class TestAnotherCardsAnthemSeesIt:
    """`_matches_printed` -- the path a lord takes, which never enters `_compute`."""

    def test_a_vampire_lord_now_pumps_the_converted_creature(self, builder):
        game = board(builder, mine=["t_vampire_lord", "t_plain_goblin"])
        goblin = oid_of(game, "t_plain_goblin")
        assert (chars(game.state, goblin).power, chars(game.state, goblin).toughness) == (1, 1)

        change_text(game, goblin, "Goblin")
        c = chars(game.state, goblin)
        assert (c.power, c.toughness) == (3, 3), "the Vampire lord's +2/+2 now finds it"

    def test_a_goblin_lord_stops_pumping_it(self, builder):
        """The other direction, and the half `add_subtype` would get wrong.

        Under an `add_subtype` the creature would be a Goblin *and* a Vampire and
        both lords would pump it. Replacing the word means the old lord loses it.
        """
        game = board(builder, mine=["t_goblin_lord", "t_plain_goblin"])
        goblin = oid_of(game, "t_plain_goblin")
        assert chars(game.state, goblin).power == 2, "the Goblin lord's +1/+1"

        change_text(game, goblin, "Goblin")
        assert chars(game.state, goblin).power == 1, "no longer a Goblin"

    def test_added_subtypes_still_layer_on_top(self, builder):
        """Layer 4 is unaffected -- a creature can be under both effects."""
        from automtg.engine.primitives import add_subtypes

        game = board(builder, mine=["t_goblin_lord", "t_plain_goblin"])
        goblin = oid_of(game, "t_plain_goblin")
        change_text(game, goblin, "Goblin")
        add_subtypes(game.state, goblin, ["Goblin"])

        c = chars(game.state, goblin)
        assert {"Vampire", "Goblin"} <= c.subtypes
        assert c.power == 2, "the Goblin lord finds it again through added_subtypes"


class TestTheStolenLordsOwnText:
    """`abilities_of` -- "other Goblins you control get +1/+1" becomes "other Vampires"."""

    def test_its_anthem_stops_finding_its_old_tribe(self, builder):
        game = board(builder, mine=["t_goblin_lord", "t_plain_goblin"])
        lord = oid_of(game, "t_goblin_lord")
        other = oid_of(game, "t_plain_goblin")
        assert chars(game.state, other).power == 2

        change_text(game, lord, "Goblin")
        assert chars(game.state, other).power == 1, (
            "the lord's own text now says Vampires, so the Goblin is not pumped"
        )

    def test_its_anthem_now_finds_vampires(self, builder):
        game = board(builder, mine=["t_goblin_lord", "t_vampire_lord"])
        lord = oid_of(game, "t_goblin_lord")
        vampire = oid_of(game, "t_vampire_lord")
        assert chars(game.state, vampire).power == 2, "not a Goblin, so unpumped"

        change_text(game, lord, "Goblin")
        assert chars(game.state, vampire).power == 3, "the stolen lord is a Vampire lord now"

    def test_the_substitution_survives_a_grant_ability_static(self, builder):
        """`_derived_abilities` reads the printed list too, and must read the same one.

        `t_granter` is on the board for one reason: an ability-granting static
        anywhere makes `_ability_statics` non-empty, which pushes `abilities_of`
        off its fast path and through `_derived_abilities`. That second reader
        used to fetch `card_of(obj).abilities` for itself, so substituting only
        on the fast path left a text-changed permanent reverting to its old tribe
        the moment any granter appeared -- a bug needing two cards on the table
        at once, which is why this test names the granter rather than relying on
        the board it happened to have.
        """
        game = board(builder, mine=["t_goblin_lord", "t_vampire_lord", "t_granter"])
        lord = oid_of(game, "t_goblin_lord")
        change_text(game, lord, "Goblin")

        printed = [a for a in abilities_of(game.state, lord) if a.static is not None]
        assert any(a.static.get("effect") == "grant_ability" for a in printed) is False
        assert printed[0].static["affects"]["subtypes"] == ["Vampire"]


class TestActivatedAndTriggeredHalves:
    """`stack.ability_of` -- the seam the statics path does not cover."""

    def test_a_triggers_filter_is_rewritten(self, builder):
        game = board(builder, mine=["t_goblin_herald"])
        herald = oid_of(game, "t_goblin_herald")
        change_text(game, herald, "Goblin")

        trigger = abilities_of(game.state, herald)[0].trigger
        assert trigger.filter["subtypes"] == ["Vampire"]

    def test_an_activated_abilitys_target_selector_is_rewritten(self, builder):
        game = board(builder, mine=["t_goblin_herald"])
        herald = oid_of(game, "t_goblin_herald")
        change_text(game, herald, "Goblin")

        target = abilities_of(game.state, herald)[1].targets[0]
        assert target.selector["subtypes"] == ["Vampire"]

    def test_resolution_reads_the_rewritten_ability(self, builder):
        """`ability_of` is what resolution looks the ability up through."""
        from automtg.engine.stack import ability_of
        from automtg.engine.structs import StackItem

        game = board(builder, mine=["t_goblin_herald"])
        herald = oid_of(game, "t_goblin_herald")
        change_text(game, herald, "Goblin")

        item = StackItem(
            sid=1,
            kind="ability",
            controller=0,
            def_id="t_goblin_herald",
            oid=herald,
            source_oid=herald,
            ability_index=1,
        )
        ability = ability_of(game.state, item)
        assert ability is not None
        assert ability.targets[0].selector["subtypes"] == ["Vampire"]


class TestWhichTypesAreOffered:
    def test_the_candidates_are_the_types_with_instances(self, builder, registry):
        """Printed subtype line plus every type named in the printed abilities.

        The rules let a player name any creature type; this narrows to the ones
        with an instance, which is observationally identical -- naming a word the
        card never says replaces nothing -- and turns a 400-entry prompt into a
        real choice.
        """
        game = board(builder, mine=["t_goblin_herald"])
        card = registry.get("t_goblin_herald")
        found = printed_type_instances(game.state, card)

        assert "Human" in found, "its own printed subtype line"
        assert "Goblin" in found, "named inside its trigger and its activated ability"
        assert "Vampire" not in found, "a word this card never says"


class TestTheWalkIsNarrow:
    def test_only_subtypes_lists_are_rewritten(self):
        """A walk that rewrote any matching string would hit names and prompts."""
        spec = {
            "op": "create_token",
            "name": "Goblin",
            "prompt": "Choose a Goblin",
            "objects": {"subtypes": ["Goblin"]},
        }
        out = substitute(spec, [("Goblin", "Vampire")])
        assert out["objects"]["subtypes"] == ["Vampire"]
        assert out["name"] == "Goblin", "a token's name is not a subtypes list"
        assert out["prompt"] == "Choose a Goblin"

    def test_it_reaches_arbitrary_nesting(self):
        spec = {"a": [{"b": ({"objects": {"subtypes": ["Goblin", "Elf"]}},)}]}
        out = substitute(spec, [("Goblin", "Vampire")])
        assert out["a"][0]["b"][0]["objects"]["subtypes"] == ["Vampire", "Elf"]

    def test_a_chosen_type_entry_passes_through(self):
        """`{"chosen_type_of": "self"}` is a reference, not an instance of a word."""
        spec = {"objects": {"subtypes": [{"chosen_type_of": "self"}]}}
        out = substitute(spec, [("Goblin", "Vampire")])
        assert out["objects"]["subtypes"] == [{"chosen_type_of": "self"}]


class TestWhatThePlayerReads:
    """The screen has to agree with the rules, or the board is unreadable."""

    def test_the_type_line_and_oracle_text_are_rewritten(self, builder):
        game = board(builder, mine=["t_goblin_lord"])
        lord = oid_of(game, "t_goblin_lord")
        change_text(game, lord, "Goblin")

        view = card_view(game.state, lord)
        assert "Vampire" in view["type_line"] and "Goblin" not in view["type_line"]
        assert view["oracle_text"] == "Other Vampires you control get +1/+1."

    def test_it_agrees_with_the_subtypes_in_the_same_payload(self, builder):
        """Both come from the same change; disagreeing would be worse than neither."""
        game = board(builder, mine=["t_plain_goblin"])
        goblin = oid_of(game, "t_plain_goblin")
        change_text(game, goblin, "Goblin")

        view = card_view(game.state, goblin)
        assert "Vampire" in view["subtypes"]
        assert "Vampire" in view["type_line"]

    def test_an_untouched_card_reads_exactly_as_printed(self, builder, registry):
        game = board(builder, mine=["t_goblin_lord"])
        lord = oid_of(game, "t_goblin_lord")
        assert card_view(game.state, lord)["oracle_text"] == registry.get(
            "t_goblin_lord"
        ).oracle_text

    def test_the_plural_is_rewritten_as_a_plural(self):
        assert displayed("Other Goblins you control get +1/+1.", [("Goblin", "Vampire")]) == (
            "Other Vampires you control get +1/+1."
        )

    def test_a_longer_word_containing_the_type_is_left_alone(self):
        """Whole words only -- the boundary is the point."""
        assert displayed("Hobgoblin stays put", [("Goblin", "Vampire")]) == "Hobgoblin stays put"


class TestTheLoaderRefusesNonsense:
    def card(self, **effect):
        base = {"op": "change_text", "objects": {"target": "t1"}}
        base.update(effect)
        return CardModel.model_validate(
            {
                "id": "t_bad_change",
                "name": "Test Bad Change",
                "oracle_text": "Change the text of target creature.",
                "mana_cost": "{B}",
                "types": ["Sorcery"],
                "colors": ["B"],
                "color_identity": ["B"],
                "targets": [
                    {
                        "id": "t1",
                        "kind": "permanent",
                        "selector": {"zone": "battlefield", "types": ["Creature"]},
                    }
                ],
                "spell_effects": [base],
            }
        )

    def test_a_creature_type_is_fine(self):
        from automtg.cards.loader import compile_card

        compile_card(self.card(to="Vampire"))

    def test_a_missing_to_is_a_load_error(self):
        """Without it the op has nothing to write and would silently do nothing."""
        from automtg.cards.loader import compile_card

        with pytest.raises(DslError, match=r"'to'"):
            compile_card(self.card())

    def test_a_non_creature_subtype_is_a_load_error(self):
        from automtg.cards.loader import compile_card

        with pytest.raises(DslError, match="creature type"):
            compile_card(self.card(to="Equipment"))

    def test_another_word_class_is_refused_by_name(self):
        """Colour words and basic land types are their own surfaces, not built."""
        from automtg.cards.loader import compile_card

        with pytest.raises(DslError, match=r"color_word|not modelled"):
            compile_card(self.card(to="Vampire", word_class="color_word"))
