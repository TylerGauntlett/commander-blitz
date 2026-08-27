"""A player target the card *excludes* rather than names.

Lucy MacLean, Positively Armed: "Whenever a token enters, you may have **target
player other than its controller** create a token that's a copy of it..."

`targeting._player_allowed` was the whole of player-target legality and read one
key in three ways -- "you", "opponent", and a `return True` fallthrough for
everything else. The fallthrough was the bug, and it was silent in the worst
way: `validate_selector` has always accepted a Mapping there, so
`{"controller": {"controller_of": "subject"}}` compiled cleanly, was dropped on
the floor, and left a card printed "other than its controller" playing as
"target any player" -- strictly wider than the printing, with nothing anywhere
to say so.

Two things were missing and both are needed:

- the **mapping** forms `select_players` already parses (`controller_of`,
  `owner_of`, `binding`, `target`) have to be honoured here, which means this
  function needs a context and therefore needs the trigger's bindings threaded
  down to it;
- a **negated** form, because every existing spec names the players to *allow*
  and this line names the one player to forbid.

"opponent" is the near miss, and on a card that triggers on *anybody's* token it
is wrong in both directions at once: it forbids you when an opponent made the
token, and permits the very opponent who made it. At a four-player pod "other
than its controller" is three seats -- the other two opponents and you -- which
no single inclusive spec can name.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.carddef import TargetSpec
from automtg.engine.errors import DslError
from automtg.engine.primitives import create_token
from automtg.engine.structs import TargetRef
from automtg.engine.targeting import candidates, still_legal

BEAR = "t_bear"


def board(builder, players: int = 4):
    return (
        builder(players=players)
        .battlefield(0, ["plains", BEAR])
        .battlefield(1, ["plains"])
        .build()
    )


def other_than(binding: str) -> TargetSpec:
    return TargetSpec(
        id="t1",
        kind="player",
        selector={"controller": {"not": {"controller_of": binding}}},
    )


def seats(refs) -> set[int]:
    return {ref.id for ref in refs}


class TestExcludingTheBoundPlayer:
    def test_every_seat_but_the_tokens_controller_is_offered(self, builder):
        """A pod is the case the inclusive specs cannot say."""
        game = board(builder, players=4)
        token = create_token(game.state, "soldier_1_1_w", 2, 1)[0]

        refs = candidates(
            game.state, 0, other_than("subject"), None, bindings={"subject": token}
        )

        assert seats(refs) == {0, 1, 3}, "everyone except seat 2, who made it"

    def test_you_are_offered_when_an_opponent_made_the_token(self, builder):
        """The half "opponent" gets wrong by forbidding you."""
        game = board(builder, players=4)
        token = create_token(game.state, "soldier_1_1_w", 1, 1)[0]

        refs = candidates(
            game.state, 0, other_than("subject"), None, bindings={"subject": token}
        )

        assert 0 in seats(refs)

    def test_you_are_excluded_when_you_made_it(self, builder):
        """...and the half it gets wrong by permitting the maker."""
        game = board(builder, players=4)
        token = create_token(game.state, "soldier_1_1_w", 0, 1)[0]

        refs = candidates(
            game.state, 0, other_than("subject"), None, bindings={"subject": token}
        )

        assert seats(refs) == {1, 2, 3}

    def test_a_dead_seat_is_never_offered(self, builder):
        """The complement is taken over the living, not over every seat."""
        game = board(builder, players=4)
        game.state.players[3].has_lost = True
        token = create_token(game.state, "soldier_1_1_w", 2, 1)[0]

        refs = candidates(
            game.state, 0, other_than("subject"), None, bindings={"subject": token}
        )

        assert 3 not in seats(refs)


class TestTheReCheckOnResolution:
    def test_control_changing_in_between_is_noticed(self, builder):
        """608.2b, and the reason the bindings have to reach `still_legal` too.

        The target was legal when it was declared. If control of the bound token
        moves to that player before the ability resolves, they have become its
        controller and the target is no longer legal.
        """
        game = board(builder, players=4)
        token = create_token(game.state, "soldier_1_1_w", 2, 1)[0]
        spec = other_than("subject")
        ref = TargetRef.player(1)

        assert still_legal(game.state, 0, spec, ref, None, bindings={"subject": token})

        game.state.objects[token].controller = 1

        assert not still_legal(
            game.state, 0, spec, ref, None, bindings={"subject": token}
        )


class TestTheStringsStillMeanWhatTheyMeant:
    @pytest.mark.parametrize(
        ("clause", "expected"),
        [("you", {0}), ("opponent", {1, 2, 3}), ("any", {0, 1, 2, 3})],
    )
    def test_the_shipped_clauses_are_unchanged(self, builder, clause, expected):
        game = board(builder, players=4)
        spec = TargetSpec(id="t1", kind="player", selector={"controller": clause})

        assert seats(candidates(game.state, 0, spec, None)) == expected

    def test_an_absent_clause_is_still_every_seat(self, builder):
        game = board(builder, players=4)
        spec = TargetSpec(id="t1", kind="player", selector={})

        assert seats(candidates(game.state, 0, spec, None)) == {0, 1, 2, 3}


def probe(selector: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_player_probe",
            "name": "Player Probe",
            "oracle_text": "Target player draws a card.",
            "mana_cost": "{U}",
            "types": ["Instant"],
            "targets": [{"id": "t1", "kind": "player", "selector": selector}],
            "spell_effects": [
                {"op": "draw", "player": {"target": "t1"}, "amount": {"const": 1}}
            ],
        }
    )


class TestTheLoaderNoLongerWidensSilently:
    """The fallthrough is closed at load time as well as honoured at runtime.

    Honouring the clause fixes the cards that spell it correctly. Refusing an
    unknown one is what stops the *next* misspelling loading clean and playing
    wide -- which is how this shipped in the first place.
    """

    def test_a_misspelled_string_clause_is_refused(self):
        """`validate_selector` already caught this one; pinned so it stays caught."""
        with pytest.raises(DslError, match="unknown controller clause"):
            compile_card(probe({"controller": "each_opponent_but_one"}))

    def test_a_negated_spec_loads(self):
        card = compile_card(probe({"controller": {"not": {"controller_of": "subject"}}}))
        assert card.targets[0].selector["controller"] == {
            "not": {"controller_of": "subject"}
        }

    def test_a_negation_wrapping_nonsense_is_refused(self):
        with pytest.raises(DslError, match="unknown player spec"):
            compile_card(probe({"controller": {"not": "the_loser"}}))

    def test_not_may_not_be_combined_with_another_key(self):
        with pytest.raises(DslError, match="'not' is the whole spec"):
            compile_card(
                probe({"controller": {"not": {"controller_of": "subject"}, "you": True}})
            )

    def test_any_is_still_accepted(self):
        assert compile_card(probe({"controller": "any"})).targets[0].kind == "player"
