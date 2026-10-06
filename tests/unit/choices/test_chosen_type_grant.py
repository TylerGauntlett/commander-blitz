""""This creature is **the chosen type** in addition to its other types."

Roaming Throne's third line, and Arcane Adaptation's and Xenograft's whole text.
`{"chosen_type_of": "self"}` already existed, and only as a **read**: every
shipped user of it — Vanquisher's Banner, Cavern of Souls, Urza's Incubator —
asks "is that other object of the chosen type". None of them makes something
*be* that type, which is the other half of the family and needs the entry on the
granting side of an `add_subtype` static.

Rule 205.1b and layer 4 (613.1d): the grant is continuous, not a one-shot
written onto the permanent, and three claims follow from that and are each
pinned below.

- **Nothing is granted before a type is chosen.** The alternative failure is the
  one an empty filter always has, one direction over: falling back to "every
  type" would make the Throne a changeling for the moment the choice was
  pending, and it would answer every tribal lord on the board.
- **The choice moves and the type moves with it.** A second `choose_type` or a
  `change_text` re-points the grant, because layer 4 re-reads the source on
  every recompute. A one-shot could not do this, which is why the op is not an
  alternative spelling of the static.
- **The substitution reads the static's own source**, not the permanent being
  computed. With a `{"self_only": true}` Throne the two are the same object and
  every wrong implementation looks right, so the Xenograft-shaped test card here
  — "each creature you control is the chosen type" — is the one that can tell
  them apart.

*The trap this closes.* The same spec inside a `self_enters` trigger compiled
clean before this change, and `op_add_subtype` did `[str(t) for t in …]`: the
permanent gained the literal subtype `"{'chosen_type_of': 'self'}"`, a card that
loads, resolves, passes a zone assertion and is of no creature type at all. The
op is **refused** at load time rather than taught the substitution — a one-shot
freezes the word it writes, so the same JSON in the two places would read
identically and play as two different cards.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.effects.ops_characteristics import op_add_subtype
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.errors import DslError

THRONE = "t_chosen_throne"  # "This creature is the chosen type…", self_only
XENOGRAFT = "t_chosen_xenograft"  # "…each creature you control is…"
BEAR = "t_bear"


def only(game, def_id: str) -> int:
    return next(o for o in game.state.battlefield if game.state.objects[o].def_id == def_id)


def board(builder, cards):
    """The named permanents on player 0's battlefield, with nothing chosen yet.

    Put there directly rather than cast, so that the enters trigger has not run
    and `chosen_type` is `None` — which is the state the first claim is about.
    """
    return builder(players=2).battlefield(0, list(cards)).build()


def choose(game, oid: int, type_name: str | None) -> None:
    """Set the type this permanent named, the way its own trigger would."""
    game.state.objects[oid].chosen_type = type_name
    game.state.bump_chars()


def a_card(*, effect: str = "add_subtype", subtypes=None, **static):
    """A one-static permanent, for the load-time claims."""
    return {
        "id": "x",
        "name": "X",
        "oracle_text": "This creature is the chosen type in addition to its other types.",
        "mana_cost": "{2}",
        "types": ["Creature"],
        "subtypes": ["Wall"],
        "power": 1,
        "toughness": 3,
        "abilities": [
            {
                "kind": "static",
                "text": "This creature is the chosen type in addition to its other types.",
                "effect": effect,
                "affects": {"self_only": True},
                "subtypes": [{"chosen_type_of": "self"}] if subtypes is None else subtypes,
                **static,
            }
        ],
    }


class TestWhatItGrants:
    def test_nothing_is_granted_before_a_type_is_chosen(self, builder):
        game = board(builder, [THRONE])
        throne = only(game, THRONE)

        assert game.state.objects[throne].chosen_type is None
        assert set(chars(game.state, throne).subtypes) == {"Wall"}, (
            "an unchosen grant adds nothing -- not every type, and not a placeholder"
        )

    def test_the_chosen_type_is_added_to_the_printed_line(self, builder):
        game = board(builder, [THRONE])
        throne = only(game, THRONE)
        choose(game, throne, "Dragon")

        subtypes = set(chars(game.state, throne).subtypes)
        assert "Dragon" in subtypes
        assert "Wall" in subtypes, "'in addition to its other types', not instead of them"

    def test_the_literal_spec_never_reaches_the_type_line(self, builder):
        """The whole shape of the bug this closes, asserted as a shape.

        `str()` on the entry produced the subtype "{'chosen_type_of': 'self'}",
        and a permanent carrying it reads as a creature of a type no card in the
        game shares. Every subtype here is a name.
        """
        game = board(builder, [THRONE])
        throne = only(game, THRONE)
        choose(game, throne, "Dragon")

        for subtype in chars(game.state, throne).subtypes:
            assert "chosen_type_of" not in subtype

    def test_choosing_again_moves_the_grant(self, builder):
        """Layer 4 re-reads the source, so the old type does not linger."""
        game = board(builder, [THRONE])
        throne = only(game, THRONE)

        choose(game, throne, "Dragon")
        assert "Dragon" in chars(game.state, throne).subtypes

        choose(game, throne, "Elf")
        subtypes = set(chars(game.state, throne).subtypes)
        assert subtypes == {"Wall", "Elf"}, "a continuous grant, not a word written down"

    def test_a_grant_that_is_taken_back_leaves_the_printed_line(self, builder):
        """A Throne that leaves and returns chooses again, and until it does…"""
        game = board(builder, [THRONE])
        throne = only(game, THRONE)

        choose(game, throne, "Dragon")
        choose(game, throne, None)
        assert set(chars(game.state, throne).subtypes) == {"Wall"}


class TestWhoseChoiceItReads:
    """The static's **source**, not the permanent the static is applied to."""

    def test_another_creature_gains_the_granter_s_type(self, builder):
        game = board(builder, [XENOGRAFT, BEAR])
        xenograft, bear = only(game, XENOGRAFT), only(game, BEAR)
        choose(game, xenograft, "Dragon")

        assert game.state.objects[bear].chosen_type is None, "the Bear chose nothing"
        assert set(chars(game.state, bear).subtypes) == {"Bear", "Dragon"}

    def test_a_recipient_that_chose_nothing_is_not_what_is_read(self, builder):
        """The failure this catches reads the *affected* object and grants nothing."""
        game = board(builder, [XENOGRAFT, BEAR])
        xenograft = only(game, XENOGRAFT)
        choose(game, xenograft, "Elf")

        assert "Elf" in chars(game.state, only(game, BEAR)).subtypes

    def test_two_sources_grant_their_own_types(self, builder):
        """Two Thrones choose independently; `self_only` keeps them apart."""
        game = board(builder, [THRONE, THRONE])
        first, second = (
            o for o in game.state.battlefield if game.state.objects[o].def_id == THRONE
        )
        choose(game, first, "Dragon")
        choose(game, second, "Elf")

        assert set(chars(game.state, first).subtypes) == {"Wall", "Dragon"}
        assert set(chars(game.state, second).subtypes) == {"Wall", "Elf"}


class TestTheLayersLiteDivergence:
    """A granted type is in `chars`, and is **not** in another static's filter.

    `_matches` reads printed characteristics plus the object's own
    `added_subtypes`, on purpose: no static may depend on another's output. So a
    Xenograft naming Bear makes the board Bears everywhere `chars` is read, and
    a Bear lord beside it still pumps only the printed ones. Recorded in
    `docs/rules-coverage.md` and pinned here so it cannot drift silently.
    """

    def test_the_type_is_on_the_creature(self, builder):
        game = board(builder, [XENOGRAFT, "t_lord", "t_flyer"])
        choose(game, only(game, XENOGRAFT), "Bear")

        assert "Bear" in chars(game.state, only(game, "t_flyer")).subtypes

    def test_and_another_static_s_anthem_does_not_see_it(self, builder):
        """`t_lord` is "Other Bears you control get +1/+1"."""
        game = board(builder, [XENOGRAFT, "t_lord", "t_flyer"])
        choose(game, only(game, XENOGRAFT), "Bear")

        flyer = chars(game.state, only(game, "t_flyer"))
        assert (flyer.power, flyer.toughness) == (2, 2), "printed size, not 3/3"


class TestItReachesTheBoard:
    def test_the_trigger_and_the_grant_agree(self, builder):
        """End to end: cast the Throne, answer its trigger, read the type line."""
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 6)
            .hand(0, [THRONE])
            .library(0, ["forest"] * 10)
            .active(0)
            .max_turns(1)
            .build()
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST
                and game.state.objects[a.source].def_id == THRONE
            )
        )
        decision = game.pending()
        assert decision is not None and decision.kind is DecisionKind.CHOOSE_MODE
        index = [o.label for o in decision.options].index("Dragon")
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.choice == index
            )
        )

        throne = only(game, THRONE)
        assert game.state.objects[throne].chosen_type == "Dragon"
        assert set(chars(game.state, throne).subtypes) == {"Wall", "Dragon"}


class TestTheLoader:
    def test_the_static_takes_it(self):
        card = compile_card(CardModel.model_validate(a_card()))
        assert card.abilities[0].static["subtypes"] == [{"chosen_type_of": "self"}]

    def test_a_near_miss_spelling_is_refused(self):
        """It would resolve to nothing and grant no type at all, for ever."""
        with pytest.raises(DslError, match="chosen_type_of"):
            compile_card(
                CardModel.model_validate(a_card(subtypes=[{"chosen_type_of": "source"}]))
            )

    def test_it_is_refused_on_a_static_that_does_not_read_subtypes(self):
        """`add_subtype` is the only reader, so elsewhere it is a line with none."""
        with pytest.raises(DslError, match="add_subtype"):
            compile_card(
                CardModel.model_validate(
                    a_card(effect="grant_keyword", keywords=["flying"])
                )
            )

    def test_the_op_is_refused(self):
        """The trap: this used to compile and stringify. See the module docstring."""
        spec = {
            "id": "x",
            "name": "X",
            "oracle_text": "When this creature enters, it becomes the chosen type.",
            "mana_cost": "{2}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "triggered",
                    "text": "When this creature enters, it becomes the chosen type.",
                    "trigger": {"event": "self_enters", "source": "self"},
                    "effects": [
                        {
                            "op": "add_subtype",
                            "subtypes": [{"chosen_type_of": "self"}],
                            "objects": {"self_only": True, "zone": "battlefield"},
                        }
                    ],
                }
            ],
        }
        with pytest.raises(DslError, match="literal"):
            compile_card(CardModel.model_validate(spec))

    def test_the_op_refuses_it_in_code_too(self):
        """Unreachable through `compile_card`, and loud rather than silent anyway."""
        with pytest.raises(TypeError, match="literal names"):
            next(
                op_add_subtype(
                    None,
                    {
                        "subtypes": [{"chosen_type_of": "self"}],
                        "objects": {"self_only": True, "zone": "battlefield"},
                    },
                )
            )

    def test_a_granted_static_may_not_carry_it(self):
        """A grant moves the source, and the recipient chose nothing.

        The same refusal a granted *filter* already had, on the grant side of
        the same static — `walk._refuse_granted_chosen_qualities`.
        """
        spec = {
            "id": "x",
            "name": "X",
            "oracle_text": "Creatures you control have \"This creature is the chosen type.\"",
            "mana_cost": "{2}",
            "types": ["Enchantment"],
            "grantable_abilities": [
                {
                    "kind": "static",
                    "text": "This creature is the chosen type.",
                    "effect": "add_subtype",
                    "affects": {"self_only": True},
                    "subtypes": [{"chosen_type_of": "self"}],
                }
            ],
            "abilities": [
                {
                    "kind": "static",
                    "text": "Creatures you control have \"This creature is the chosen type.\"",
                    "effect": "grant_ability",
                    "affects": {"controller": "you", "types": ["Creature"]},
                    "ability": 0,
                }
            ],
        }
        with pytest.raises(DslError, match="chosen_type_of"):
            compile_card(CardModel.model_validate(spec))
