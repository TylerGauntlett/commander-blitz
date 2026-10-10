"""Cipher — haunt's link pointed a third way, and a copy of a card in exile.

    "Cipher (Then you may exile this spell card encoded on a creature you
    control. Whenever that creature deals combat damage to a player, its
    controller may cast a copy of this card without paying its mana cost.)"

The engine now has three exile links, and cipher is the one that made the third
direction obvious. All three are written on the exiled card and they name
different things, because the triggers that read them ask different questions:

| field | names | read by |
|---|---|---|
| `exiled_by` | the **exiler** | O-Ring's own leaves-trigger, and imprint's abilities |
| `haunting` | a creature whose **death** matters | a `creature_dies` trigger in exile |
| `encoded_on` | a creature whose **combat damage** matters | a `deals_combat_damage_to_player` trigger in exile |

The copy is `cast_copy`, and it is not `copy_spell`: that op copies something on
the **stack**, and an encoded card is in exile with nothing on the stack to
point at. It goes through the same `put_copy_on_stack`, so a cipher copy is a
token and announces its targets exactly as a storm copy does.

The original stays in exile — it is copied, not cast — which is the whole of why
cipher keeps paying.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.primitives import damage_player
from tests.conftest import _default_answer, only_oid, pass_until

SWAMP = "swamp"
WHISPER = "t_cipher"
BEAR = "t_bear"


def position(builder):
    return (
        builder(players=2)
        .battlefield(0, [SWAMP] * 3)
        .battlefield(0, [BEAR])
        .hand(0, [WHISPER])
        .library(0, [SWAMP] * 20)
        .library(1, [SWAMP] * 20)
        .build()
    )


def connect(game, attacker: int, amount: int = 2) -> int:
    """Deal combat damage by hand and run on. Returns how many copies were made.

    `damage_player` is a primitive: it *queues* the trigger and advances
    nothing, and the engine drains queued triggers in `_advance`, which returns
    early while a decision is already pending -- and one usually is.

    The **copies are counted off the log** rather than off the stack, because
    with nobody holding a response the whole thing happens inside one `apply`:
    the trigger drains, the copy is made, it resolves and it is gone. The stack
    is never non-empty from outside, so `spell_copied` is the only honest
    record that it happened.
    """
    before = len(game.state.events)
    damage_player(game.state, 1, amount, attacker, is_combat=True)
    for _ in range(120):
        decision = game.pending()
        if decision is None:
            break
        game.apply(_default_answer(game, decision))
        if any(e.type == "spell_copied" for e in game.state.events[before:]):
            break
    return sum(1 for e in game.state.events[before:] if e.type == "spell_copied")


def cast_and_encode(game):
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == WHISPER
    )
    whisper = action.source
    game.apply(action)
    pass_until(game, lambda g: g.pending() is None or not g.state.stack)
    return whisper


class TestTheEncoding:
    def test_the_card_is_exiled_encoded_on_the_creature(self, builder):
        game = position(builder)
        whisper = cast_and_encode(game)
        bear = only_oid(game, BEAR)

        assert game.state.objects[whisper].zone is Zone.EXILE
        assert game.state.objects[whisper].encoded_on == bear

    def test_the_spell_still_did_what_it_says(self, builder):
        game = position(builder)
        life = min(game.state.players[0].life, game.state.players[1].life)
        cast_and_encode(game)

        assert min(game.state.players[0].life, game.state.players[1].life) == life - 1

    def test_it_is_not_the_exiled_by_link(self, builder):
        """Three directions, three fields."""
        game = position(builder)
        whisper = cast_and_encode(game)

        assert game.state.objects[whisper].exiled_by is None
        assert game.state.objects[whisper].haunting is None


class TestTheTrigger:
    def test_combat_damage_casts_a_copy(self, builder):
        game = position(builder)
        cast_and_encode(game)
        bear = only_oid(game, BEAR)

        assert connect(game, bear) == 1

    def test_the_copy_is_of_this_card(self, builder):
        game = position(builder)
        cast_and_encode(game)
        bear = only_oid(game, BEAR)

        connect(game, bear)

        copied = next(e for e in game.state.events if e.type == "spell_copied")
        assert copied.data["card"] == WHISPER

    def test_no_second_card_ends_up_anywhere(self, builder):
        """A copy is a token: it resolves and is gone, leaving one card."""
        game = position(builder)
        cast_and_encode(game)
        bear = only_oid(game, BEAR)

        connect(game, bear)

        everywhere = [
            o for o in game.state.objects.values() if o.def_id == WHISPER
        ]
        assert len(everywhere) == 1, "the card, and no leftover copy"

    def test_the_original_stays_in_exile(self, builder):
        """It is copied, not cast -- which is why cipher keeps paying."""
        game = position(builder)
        whisper = cast_and_encode(game)
        bear = only_oid(game, BEAR)

        connect(game, bear)

        assert game.state.objects[whisper].zone is Zone.EXILE
        assert game.state.objects[whisper].encoded_on == bear

    def test_it_fires_again_next_time(self, builder):
        """The encoding is not spent, so a second connection copies again."""
        game = position(builder)
        cast_and_encode(game)
        bear = only_oid(game, BEAR)

        assert connect(game, bear, amount=1) == 1
        assert connect(game, bear, amount=1) == 1

    def test_the_copy_does_not_encode_itself(self, builder):
        """702.97b: a copy is not a card, so there is nothing to exile.

        Epic needed the same `not is_token` guard, and for the same reason --
        both keywords make copies that resolve through the very code that armed
        them.
        """
        game = position(builder)
        whisper = cast_and_encode(game)
        bear = only_oid(game, BEAR)
        connect(game, bear)

        encoded = [
            e for e in game.state.events if e.type == "encoded"
        ]
        assert len(encoded) == 1, "the card encoded once; the copy did not"
        assert game.state.objects[whisper].encoded_on == bear

    def test_another_creature_connecting_does_nothing(self, builder):
        """`encoded_by` names one creature, the way `haunted_by` does."""
        game = (
            builder(players=2)
            .battlefield(0, [SWAMP] * 3)
            .battlefield(0, [BEAR, BEAR])
            .hand(0, [WHISPER])
            .library(0, [SWAMP] * 20)
            .library(1, [SWAMP] * 20)
            .build()
        )
        whisper = cast_and_encode(game)
        encoded = game.state.objects[whisper].encoded_on
        other = next(
            o.oid
            for o in game.state.battlefield_objects(0)
            if o.def_id == BEAR and o.oid != encoded
        )

        assert connect(game, other) == 0
