"""Turning a permanent over, which is one boolean and one choke point.

    Bloodline Keeper — "{B}: Transform this creature. Activate only if you
    control five or more Vampires." The back face, Lord of Lineage, is a 5/5
    that gives other Vampires +2/+2.

`docs/rules-coverage.md` listed transforming cards under **Not implemented**,
and the reason it turned out to be small is `GameState.card_of`. Every reader of
a card's characteristics — the layers, legality, combat, the serializer — goes
through that one function, so a permanent showing its other face is a flag on
the object and a branch in one place. Nothing else changed.

Three things that would each be silently wrong:

- **Rule 712.13a.** A permanent that leaves the battlefield and comes back
  enters **front face up**. Reset with the rest of the battlefield state, or a
  blink hands somebody a 5/5 lord.
- **A back face is not a card.** It has no mana cost and is never in a hand, a
  library or a deck; it exists only as the face a permanent already in play
  turned over to. `validate_deck` refuses one, and the guards that do it all ask
  `front_face is not None` — which is why the link is *derived* rather than
  authored in one direction.
- **The two faces share a Scryfall id**, because the id names the card and not
  the face. `CardArt.back` is what stops Lord of Lineage downloading Bloodline
  Keeper's illustration.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader.linking import link_faces
from automtg.cards.registry import validate_deck
from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, Zone
from automtg.engine.errors import DslError
from automtg.engine.events import EventType
from automtg.engine.primitives import transform
from automtg.engine.zones import destroy, move_object
from tests.conftest import event_types, only_oid

KEEPER = "bloodline_keeper"
BACK = "lord_of_lineage"


def a_keeper(builder, *, vampires: int = 0):
    """Bloodline Keeper out, with some number of other Vampires beside it."""
    game = (
        builder(players=2)
        .battlefield(0, [KEEPER])
        .battlefield(0, ["legion_lieutenant"] * vampires)
        .battlefield(0, ["swamp"] * 4)
        .build()
    )
    return game, only_oid(game, KEEPER)


class TestWhichFaceItShows:
    def test_it_starts_on_the_front(self, real_registry, builder):
        game, keeper = a_keeper(builder)
        obj = game.state.objects[keeper]
        assert obj.transformed is False
        assert game.state.card_of(obj).id == KEEPER
        assert (chars(game.state, keeper).power, chars(game.state, keeper).toughness) == (3, 3)

    def test_transforming_shows_the_back(self, real_registry, builder):
        game, keeper = a_keeper(builder)
        assert transform(game.state, keeper) is True

        obj = game.state.objects[keeper]
        assert game.state.card_of(obj).id == BACK
        assert (chars(game.state, keeper).power, chars(game.state, keeper).toughness) == (5, 5)

    def test_the_back_face_s_abilities_are_live(self, real_registry, builder):
        """The point of the card, and the proof that `card_of` reaches the
        characteristics pipeline: the anthem is printed on the *back*."""
        game, keeper = a_keeper(builder, vampires=1)
        other = only_oid(game, "legion_lieutenant")
        before = chars(game.state, other).power

        transform(game.state, keeper)
        assert chars(game.state, other).power == before + 2

    def test_transforming_twice_turns_it_back(self, real_registry, builder):
        game, keeper = a_keeper(builder)
        transform(game.state, keeper)
        transform(game.state, keeper)
        assert game.state.objects[keeper].transformed is False

    def test_a_direction_can_be_forced(self, real_registry, builder):
        """"Turn it face up" rather than "turn it over"; a second one is a no-op."""
        game, keeper = a_keeper(builder)
        assert transform(game.state, keeper, to_back=True) is True
        assert transform(game.state, keeper, to_back=True) is False

    def test_a_single_faced_permanent_does_nothing(self, real_registry, builder):
        """Rule 701.28d, and it keeps a blanket "transform each creature" honest
        on a board of ordinary cards."""
        game = builder(players=2).battlefield(0, ["legion_lieutenant"]).build()
        assert transform(game.state, only_oid(game, "legion_lieutenant")) is False

    def test_it_is_announced(self, real_registry, builder):
        """No zone change happens, so nothing else in the log would say the card
        on the board is now a different card."""
        game, keeper = a_keeper(builder)
        before = len(game.state.events)
        transform(game.state, keeper)

        new = list(game.state.events)[before:]
        assert EventType.TRANSFORMED in event_types(new)
        event = next(e for e in new if e.type == EventType.TRANSFORMED)
        assert event.data["face"] == "back"
        assert event.data["card"] == BACK


class TestItEntersFrontFaceUp:
    def test_leaving_the_battlefield_turns_it_back(self, real_registry, builder):
        """Rule 712.13a. Without this a blink is a free upgrade to the 5/5."""
        game, keeper = a_keeper(builder)
        transform(game.state, keeper)
        destroy(game.state, keeper)
        assert game.state.objects[keeper].transformed is False

    def test_returning_to_the_battlefield_is_the_front_face(self, real_registry, builder):
        game, keeper = a_keeper(builder)
        transform(game.state, keeper)
        destroy(game.state, keeper)
        move_object(game.state, keeper, Zone.BATTLEFIELD)

        obj = game.state.objects[keeper]
        assert game.state.card_of(obj).id == KEEPER
        assert (chars(game.state, keeper).power, chars(game.state, keeper).toughness) == (3, 3)


class TestTheActivationCondition:
    def test_with_too_few_vampires_it_is_not_offered(self, real_registry, builder):
        """"Activate only if you control five or more Vampires." Not offered and
        then refused: an unofferable ability that appears is a button that lies."""
        game, _keeper = a_keeper(builder, vampires=1)
        assert not self._transform_actions(game)

    def test_with_five_vampires_it_is_offered(self, real_registry, builder):
        """Four others plus the Keeper itself is five."""
        game, _keeper = a_keeper(builder, vampires=4)
        assert self._transform_actions(game)

    def test_the_token_ability_is_offered_either_way(self, real_registry, builder):
        """The restriction is on one ability, not on the permanent."""
        game, _keeper = a_keeper(builder, vampires=0)
        assert [a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE]

    @staticmethod
    def _transform_actions(game):
        return [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE
            and game.state.objects[a.source].def_id == KEEPER
            and a.ability_index == 1
        ]


class TestABackFaceIsNotACard:
    def test_a_deck_may_not_list_one(self, real_registry):
        from automtg.cards.registry import DeckList

        deck = DeckList(
            id="t",
            name="T",
            commanders=("edgar_markov",),
            color_identity=frozenset("WBR"),
            cards=((BACK, 1),),
        )
        problems = validate_deck(deck, real_registry)
        assert any("back face" in p for p in problems)

    def test_the_link_is_derived_in_both_directions(self, real_registry):
        assert real_registry.get(KEEPER).back_face == BACK
        assert real_registry.get(BACK).front_face == KEEPER
        assert real_registry.get(KEEPER).front_face is None


class TestLoadTimeGuards:
    def _pair(self, front_back: str | None, back_back: str | None):
        from dataclasses import replace

        from automtg.engine.carddef import CardDef

        front = CardDef(id="f", name="F", back_face=front_back)
        back = CardDef(id="b", name="B", back_face=back_back)
        return {"f": front, "b": replace(back)}

    def test_an_unknown_back_face_is_refused(self):
        cards = self._pair("nope", None)
        with pytest.raises(DslError, match="unknown card"):
            link_faces(cards)

    def test_a_three_faced_card_is_refused(self):
        """Two faces, not a chain -- a cycle would make `card_of` a walk."""
        cards = self._pair("b", "f")
        with pytest.raises(DslError, match="may not have a back face"):
            link_faces(cards)

    def test_the_ordinary_pair_links(self):
        cards = self._pair("b", None)
        link_faces(cards)
        assert cards["b"].front_face == "f"


class TestTheArtIsTheOtherFace:
    def test_both_faces_share_a_printing_and_differ_by_face(self, real_registry):
        """The scryfall id names the card, not the face. Without `CardArt.back`
        Lord of Lineage downloads the illustration it just turned away from."""
        from automtg.cards.images import build_registry_images, load_index

        index = load_index()
        if index is None:
            pytest.skip("no card catalog")
        images = build_registry_images(real_registry, index)
        front, back = images[KEEPER], images[BACK]

        assert front.scryfall_id is not None
        assert front.scryfall_id == back.scryfall_id
        assert front.back is False
        assert back.back is True
        assert "/back/" in back.remote_url()
        assert "/front/" in front.remote_url()
