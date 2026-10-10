"""Replacing a token creation before the token exists.

    Academy Manufactor: "If you would create a Clue, Food, or Treasure token,
    instead create one of each."
    Divine Visitation: "If one or more creature tokens would be created under
    your control, that many 4/4 white Angel creature tokens with flying and
    vigilance are created instead."

Neither sentence was sayable. `ReplacementModel.event` is a closed whitelist of
three enters-the-battlefield forms, every one of which modifies a permanent that
is *already arriving*, and `primitives.create_token` took a fixed id and fired
TOKEN_CREATED only once the token was on the battlefield -- so there was no
moment at which the pending creation could be seen, let alone altered.

The near miss is a `token_created` trigger, and it is wrong in a way worth
naming because it looks right on a board: it adds tokens **alongside** rather
than instead, so the 1/1 Soldiers still exist and the Angels are extra, which is
a strictly stronger card than the printed one; it uses the stack, so the extra
tokens arrive later and can be responded to; and a Manufactor written that way
would re-trigger on the Treasure it just made and never stop.

So the mechanism is a static consulted inside `create_token`
(`primitives._token_creation_plan`), and the rules claims below are the whole of
what it must get right:

* **614.5 -- a replacement applies at most once to a given event.** This is not
  a nicety here, it is the difference between Divine Visitation and an infinite
  loop, because the Angels it creates are creature tokens too. It is also what
  fixes the number two Academy Manufactors produce: three of each, not an
  unbounded cascade.
* **The replacement is the *token's controller's*.** Both cards say "you". A
  Divine Visitation across the table must not touch your Soldiers.
* **The creating effect's own instructions survive.** "Create a tapped Treasure"
  into an Angel is a *tapped* Angel -- the printed ruling -- because only the
  token's identity was replaced.

The two printed sentences read as different shapes -- a substitution *set* keyed
on what was about to be made, and a substitution of identity that preserves a
count -- and they are one mechanism: each token that would have been created
becomes one of each id in `create_instead`. Manufactor lists three ids, so one
Treasure becomes three tokens; Divine Visitation lists one, so N Soldiers become
N Angels and the count is preserved without a count ever being written down.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.loader.linking import validate_token_references
from commanderblitz.cards.registry import CardRegistry, authored_card_paths
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import Keyword, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import create_token
from commanderblitz.engine.sandbox import GameBuilder
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, pass_until

MANUFACTOR = "academy_manufactor"
VISITATION = "divine_visitation"
CLUE = "clue_token"
FOOD = "food_token"
TREASURE = "treasure_token"
ANGEL = "angel_4_4_w_flying_vigilance"
SOLDIER = "human_soldier_1_1_w"


def manufactor(card_id: str = MANUFACTOR, **extra) -> dict:
    return {
        "id": card_id,
        "name": "Academy Manufactor",
        "mana_cost": "{3}",
        "types": ["Artifact", "Creature"],
        "subtypes": ["Construct"],
        "power": 1,
        "toughness": 3,
        "abilities": [
            {
                "kind": "static",
                "text": (
                    "If you would create a Clue, Food, or Treasure token, "
                    "instead create one of each."
                ),
                "effect": "replace_token_creation",
                "affects_token": {"subtypes": ["Clue", "Food", "Treasure"]},
                "create_instead": [CLUE, FOOD, TREASURE],
                **extra,
            }
        ],
    }


def visitation(card_id: str = VISITATION, **extra) -> dict:
    return {
        "id": card_id,
        "name": "Divine Visitation",
        "mana_cost": "{3}{W}{W}",
        "types": ["Enchantment"],
        "abilities": [
            {
                "kind": "static",
                "text": (
                    "If one or more creature tokens would be created under your "
                    "control, that many 4/4 white Angel creature tokens with "
                    "flying and vigilance are created instead."
                ),
                "effect": "replace_token_creation",
                "affects_token": {"types": ["Creature"]},
                "create_instead": [ANGEL],
                **extra,
            }
        ],
    }


@pytest.fixture(scope="module")
def pool() -> CardRegistry:
    """The shipped pool plus the two cards this capability exists for.

    Compiled here rather than added to `data/cards/`: the point of the test is
    that the *DSL* can express them, and a card file is the authoring pipeline's
    business. Both go through `compile_card`, so every loader guard below is the
    one a real card file would meet.
    """
    return with_cards(manufactor(), visitation())


def with_cards(*specs: dict) -> CardRegistry:
    cards = {card.id: card for card in CardRegistry.from_paths(authored_card_paths(Path("data/cards")))}
    for spec in specs:
        compiled = compile_card(CardModel.model_validate(spec))
        cards[compiled.id] = compiled
    validate_token_references(cards)
    return CardRegistry(cards)


def board(pool: CardRegistry, *permanents: str, pid: int = 0):
    """``permanents`` on ``pid``'s battlefield, with nobody having passed yet."""
    return GameBuilder(pool, players=2, seed=0).battlefield(pid, list(permanents)).build(
        advance=False
    )


def tokens(game) -> Counter:
    """How many of each token id are on the battlefield, across both seats."""
    return Counter(
        obj.def_id for obj in game.state.battlefield_objects() if obj.is_token
    )


class TestWhatIsCreatedInstead:
    """The original token is never created -- that is what "instead" means."""

    def test_a_manufactor_turns_one_treasure_into_one_of_each(self, pool):
        game = board(pool, MANUFACTOR)
        create_token(game.state, TREASURE, 0, 1)
        assert tokens(game) == {CLUE: 1, FOOD: 1, TREASURE: 1}

    def test_the_count_is_multiplied_per_token_not_per_event(self, pool):
        """"Create two Treasure tokens" is two creations, so two of each."""
        game = board(pool, MANUFACTOR)
        create_token(game.state, TREASURE, 0, 2)
        assert tokens(game) == {CLUE: 2, FOOD: 2, TREASURE: 2}

    def test_a_manufactor_ignores_a_token_its_filter_does_not_name(self, pool):
        game = board(pool, MANUFACTOR)
        create_token(game.state, SOLDIER, 0, 2)
        assert tokens(game) == {SOLDIER: 2}

    def test_a_visitation_preserves_the_count_and_replaces_the_identity(self, pool):
        game = board(pool, VISITATION)
        create_token(game.state, SOLDIER, 0, 3)
        assert tokens(game) == {ANGEL: 3}, "'that many' is the count, not one Angel"

    def test_the_angels_are_the_printed_angels(self, pool):
        """The substitute is a whole token definition, so its characteristics
        are its own -- the Soldier's 1/1 body is gone rather than resized."""
        game = board(pool, VISITATION)
        create_token(game.state, SOLDIER, 0, 1)
        angel = only_oid(game, ANGEL)
        c = chars(game.state, angel)
        assert (c.power, c.toughness) == (4, 4)
        assert c.colors == frozenset({"W"})
        assert {Keyword.FLYING.value, Keyword.VIGILANCE.value} <= set(c.keywords)

    def test_a_visitation_ignores_a_noncreature_token(self, pool):
        game = board(pool, VISITATION)
        create_token(game.state, TREASURE, 0, 1)
        assert tokens(game) == {TREASURE: 1}

    def test_the_event_names_the_token_that_was_actually_made(self, pool):
        """`token_created` is what "whenever you create a token" reads. It must
        say Angel: a trigger told a Soldier arrived would be counting a token
        that was never created."""
        game = board(pool, VISITATION)
        mark = len(game.state.events)
        create_token(game.state, SOLDIER, 0, 2)
        made = [e for e in game.state.events[mark:] if e.type == "token_created"]
        assert [e.data.get("card") for e in made] == [ANGEL, ANGEL]


class TestAReplacementAppliesOnce:
    """614.5. Every claim here is a number that is otherwise unbounded."""

    def test_a_visitation_does_not_replace_its_own_angels(self, pool):
        """The Angels are creature tokens created under your control, so a
        replacement that re-read its own output would never terminate."""
        game = board(pool, VISITATION)
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game) == {ANGEL: 1}

    def test_a_manufactor_does_not_replace_its_own_treasure(self, pool):
        """The same loop from the other side: one of the three ids it creates
        matches the filter that created it."""
        game = board(pool, MANUFACTOR)
        create_token(game.state, CLUE, 0, 1)
        assert tokens(game) == {CLUE: 1, FOOD: 1, TREASURE: 1}

    def test_two_visitations_still_make_that_many_angels(self, pool):
        """A second copy applies to the *event*, and the event is already
        making Angels, so the board does not change. Two replacements, one
        each, and the second one is a no-op it may not repeat."""
        pool2 = with_cards(manufactor(), visitation(), visitation("divine_visitation_b"))
        game = board(pool2, VISITATION, "divine_visitation_b")
        create_token(game.state, SOLDIER, 0, 2)
        assert tokens(game) == {ANGEL: 2}

    def test_two_manufactors_make_three_of_each(self, pool):
        """The printed ruling. The first turns one Treasure into three tokens;
        the second applies once to *that* event, and each of the three becomes
        one of each -- three Clues, three Foods, three Treasures. Not nine of
        each, which is what re-reading its own output a second time would give,
        and not one of each, which is what refusing the second copy would."""
        pool2 = with_cards(manufactor(), visitation(), manufactor("academy_manufactor_b"))
        game = board(pool2, MANUFACTOR, "academy_manufactor_b")
        create_token(game.state, TREASURE, 0, 1)
        assert tokens(game) == {CLUE: 3, FOOD: 3, TREASURE: 3}


class TestWhoseReplacementItIs:
    """Both cards say "you", and the "you" is the token's controller."""

    def test_an_opponents_visitation_does_not_touch_your_tokens(self, pool):
        game = board(pool, VISITATION, pid=1)
        create_token(game.state, SOLDIER, 0, 2)
        assert tokens(game) == {SOLDIER: 2}

    def test_it_applies_to_its_own_controllers_tokens(self, pool):
        """The same board from the other side, so the test above cannot pass by
        the replacement being switched off altogether."""
        game = board(pool, VISITATION, pid=1)
        create_token(game.state, SOLDIER, 1, 2)
        assert tokens(game) == {ANGEL: 2}

    def test_the_source_of_the_creating_effect_is_not_the_question(self, pool):
        """A Manufactor's controller creating a Treasure for their *opponent*
        gets an ordinary Treasure: the replacement belongs to whoever the token
        arrives under, not to whoever caused it."""
        game = board(pool, MANUFACTOR)
        create_token(game.state, TREASURE, 1, 1)
        assert tokens(game) == {TREASURE: 1}


class TestTheManufactorVisitationInteraction:
    """Both on the battlefield is a real board, and it has a defined answer.

    They never feed each other, and the reason is in the token types rather than
    in any ordering rule: what a Manufactor makes is three noncreature artifacts,
    which a Visitation's "creature tokens" filter never names, and what a
    Visitation makes is an Angel, which is no kind of Clue, Food or Treasure. So
    616.1's "the affected player chooses which to apply first" -- which this
    engine does not ask -- cannot change the outcome of this pair.
    """

    def test_a_treasure_becomes_three_artifacts_and_no_angels(self, pool):
        game = board(pool, MANUFACTOR, VISITATION)
        create_token(game.state, TREASURE, 0, 1)
        assert tokens(game) == {CLUE: 1, FOOD: 1, TREASURE: 1}

    def test_a_creature_token_becomes_angels_and_no_artifacts(self, pool):
        game = board(pool, MANUFACTOR, VISITATION)
        create_token(game.state, SOLDIER, 0, 2)
        assert tokens(game) == {ANGEL: 2}

    def test_the_order_they_arrived_in_does_not_change_the_answer(self, pool):
        """The engine applies them in battlefield order rather than asking, so
        this is the pin on that divergence being invisible for this pair."""
        first = board(pool, MANUFACTOR, VISITATION)
        create_token(first.state, TREASURE, 0, 1)
        second = board(pool, VISITATION, MANUFACTOR)
        create_token(second.state, TREASURE, 0, 1)
        assert tokens(first) == tokens(second) == {CLUE: 1, FOOD: 1, TREASURE: 1}


class TestWhatTheCreatingEffectStillSays:
    """Only the token's identity is replaced. Everything else still applies."""

    def test_a_tapped_creation_makes_a_tapped_substitute(self, pool):
        """"Create a tapped 1/1" into a Visitation is a *tapped* Angel."""
        game = board(pool, VISITATION)
        create_token(game.state, SOLDIER, 0, 1, tapped=True)
        assert game.state.objects[only_oid(game, ANGEL)].tapped

    def test_an_untapped_creation_makes_an_untapped_substitute(self, pool):
        game = board(pool, VISITATION)
        create_token(game.state, SOLDIER, 0, 1)
        assert not game.state.objects[only_oid(game, ANGEL)].tapped

    def test_embalm_style_overrides_do_not_survive_onto_a_substitute(self, pool):
        """`overrides` describe the token that was replaced and never made --
        "except it's a white Zombie Angel" is a statement about *that* token. An
        Angel carrying somebody else's exception would be a card nobody printed.
        """
        game = board(pool, VISITATION)
        create_token(
            game.state, SOLDIER, 0, 1, overrides={"colors": ["B"], "subtypes": ["Zombie"]}
        )
        c = chars(game.state, only_oid(game, ANGEL))
        assert c.colors == frozenset({"W"})
        assert "Zombie" not in c.subtypes


class TestWhenItStopsApplying:
    """A static, so it is true exactly while its source is there and switched on."""

    def test_it_stops_when_the_source_leaves_the_battlefield(self, pool):
        game = board(pool, VISITATION)
        create_token(game.state, SOLDIER, 0, 1)
        move_object(game.state, only_oid(game, VISITATION), Zone.GRAVEYARD, to_player=0)
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game) == {ANGEL: 1, SOLDIER: 1}

    def test_an_as_long_as_clause_switches_it_off(self, pool):
        """The `condition` gate is honoured here, not dropped -- a static that
        printed its clause and applied unconditionally would be a strictly
        better card than the one written.

        Written as a "during your turn" Visitation because that is the one gate
        a test can move without touching the board the replacement reads.
        """
        pool2 = with_cards(manufactor(), visitation(condition={"is_your_turn": True}))
        game = (
            GameBuilder(pool2, players=2, seed=0)
            .battlefield(0, [VISITATION])
            .library(0, ["forest"] * 10)
            .library(1, ["forest"] * 10)
            .build()
        )
        assert game.state.active_player == 1
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game) == {SOLDIER: 1}, "not its controller's turn, so off"

        pass_until(game, lambda g: g.state.active_player == 0)
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game) == {SOLDIER: 1, ANGEL: 1}


class TestTheCardFileMustSayWhatItMeans:
    """Every guard refuses a card that would load clean and do nothing (or too
    much), which is the failure the whole validation pass exists to stop."""

    def test_the_two_real_cards_compile(self):
        with_cards(manufactor(), visitation())

    def test_affects_is_refused_because_there_is_no_permanent_yet(self):
        spec = visitation()
        del spec["abilities"][0]["affects_token"]
        spec["abilities"][0]["affects"] = {"types": ["Creature"]}
        with pytest.raises(DslError, match="'affects_token', not 'affects'"):
            compile_card(CardModel.model_validate(spec))

    def test_an_empty_create_instead_is_refused(self):
        spec = visitation()
        spec["abilities"][0]["create_instead"] = []
        with pytest.raises(DslError, match="needs 'create_instead'"):
            compile_card(CardModel.model_validate(spec))

    def test_a_board_state_filter_key_is_refused(self):
        """`tapped` is a fact about a permanent. The token has not been created,
        so a filter reading one would silently match nothing."""
        spec = visitation()
        spec["abilities"][0]["affects_token"] = {"tapped": True}
        with pytest.raises(DslError, match="unsupported keys"):
            compile_card(CardModel.model_validate(spec))

    def test_the_fields_mean_nothing_on_another_static(self):
        spec = visitation()
        spec["abilities"][0]["effect"] = "no_hand_limit"
        spec["abilities"][0]["affects_player"] = "you"
        with pytest.raises(DslError, match="only mean anything on a"):
            compile_card(CardModel.model_validate(spec))

    def test_an_unknown_token_id_is_refused_at_load_time(self):
        """Not when somebody plays a Treasure into it three turns from now."""
        with pytest.raises(DslError, match="create_instead references unknown card"):
            with_cards(visitation(create_instead=["seraph_of_nowhere"]))

    def test_a_real_card_is_not_a_token(self):
        with pytest.raises(DslError, match="not marked as a token"):
            with_cards(visitation(create_instead=["forest"]))
