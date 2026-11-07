"""`face_down` -- "a face-down creature you control enters", "if you control no
face-down permanents", "face-up nontoken creatures you control".

A selector and trigger-filter key reading whether a permanent is face down
(708.2: morph, megamorph, manifest, cloak). `true` is face down, `false` face
up. Without it, "a face-down creature you control enters" can only be written
as "a creature you control enters", which draws for every creature (They Came
from the Pipes, Trail of Mystery); "face-up nontoken creatures" grants
Whisperwood Elemental's dies-trigger to the manifests it is printed to skip; and
Glitch Interpreter's intervening-if has nothing to count.

Three things here are rules arguments rather than plumbing:

* **The arrival is face down.** A morph or a manifest is never on the
  battlefield face up, so the event that announces it must already see the
  shell. The engine used to mark it face down only *after* the move, so every
  enters trigger heard a face-up card: a filter asking `face_down: true` could
  never match, a manifested Forest set off landfall, and a morph cast for {3}
  fired its own "when this enters" -- an ability a face-down permanent does not
  have (708.2).
* **The shell's characteristics.** A face-down permanent is a 2/2 Creature
  with no name, colour, subtype or mana cost (708.2), whatever is underneath.
  A trigger filter reads a card face, because its subject is often gone; for a
  face-down permanent that face is the shell, so `types: ["Creature"]` matches
  a manifested land and `types: ["Land"]` does not.
* **Where the key may be written.** Not in a static's filters, which read a
  permanent's *printed* face -- the hidden card -- so `{"face_down": true,
  "types": ["Creature"]}` there would miss a manifested land, and an `affects`
  naming face-down permanents would never reach them, since `chars` returns the
  shell before any static applies. Not on a departure trigger either: the flag
  is cleared as the permanent leaves (708.9), before the filter is asked.
"""

from __future__ import annotations

import contextlib
import copy
import json
from pathlib import Path

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import only_oid, pt, settle_completely, static_probe

FOREST = "forest"
BEAR = "grizzly_bears"
PIPES = "t_fdf_pipes"  # "whenever a face-down creature you control enters, draw"
WATCH = "t_fdf_faceup_watch"  # "whenever a face-up creature you control enters, gain 1"
LANDFALL = "t_fdf_landfall"  # "whenever a land you control enters, gain 1"
GLITCH = "t_fdf_glitch"  # "when this enters, if you control no face-down permanents, draw"
WHISPER = "t_fdf_whisper"  # "face-up nontoken creatures you control get +1/+1"
ETB_MORPH = "t_fdf_etb_morph"  # morph {G}; "when this enters, draw a card"
BEAST = "t_morpher"  # morph {2}{G}, no abilities of its own

CARDS = Path(__file__).resolve().parents[2] / "data" / "face_down_filter.cards.json"


def board(builder, mine=(), *, hand=(), top=FOREST):
    """Player 0 with eight Forests, ``mine`` and ``hand``, and ``top`` on top of
    a library of Forests.

    A spare Bear stays in hand so that player 0 always has something to do
    and the engine stops at their priority rather than passing the turn --
    which would wear an "until end of turn" pump off before it is measured."""
    return (
        builder(players=2)
        .battlefield(0, [FOREST] * 8 + list(mine))
        .hand(0, [*hand, BEAR])
        .library(0, [top] + [FOREST] * 20)
        .library(1, [FOREST] * 20)
        .build()
    )


def run(game, spec: dict, controller: int = 0) -> None:
    """Resolve one effect for ``controller`` outside the stack, then let what
    it triggered resolve."""
    gen = execute(EffectContext(state=game.state, controller=controller), [spec])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)
    settle_completely(game)


def manifest(game, controller: int = 0) -> int:
    """Manifest the top card of ``controller``'s library; return the shell."""
    top = game.state.players[controller].library[0]
    run(game, {"op": "manifest", "player": "you", "amount": {"const": 1}}, controller)
    assert game.state.objects[top].face_down
    return top


def cast(game, card_id: str, *, face_down: bool) -> int:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and a.face_down is face_down
        and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    settle_completely(game)
    return action.source


def hand(game, pid: int = 0) -> int:
    return len(game.state.players[pid].hand)


def life(game, pid: int = 0) -> int:
    return game.state.players[pid].life


def card_model(card_id: str, **changes) -> CardModel:
    raw = next(c for c in json.loads(CARDS.read_text())["cards"] if c["id"] == card_id)
    raw = copy.deepcopy(raw)
    for path, value in changes.items():
        *head, last = path.split("__")
        node = raw
        for key in head:
            node = node[int(key)] if key.isdigit() else node[key]
        node[last] = value
    return CardModel.model_validate(raw)


class TestTheArrivalIsFaceDown:
    def test_a_manifest_is_face_down_as_it_enters(self, builder):
        """The Pipes hear the manifest as a face-down creature."""
        game = board(builder, [PIPES])
        before = hand(game)

        manifest(game)

        assert hand(game) == before + 1

    def test_a_morph_cast_face_down_is_face_down_as_it_enters(self, builder):
        game = board(builder, [PIPES], hand=[BEAST])
        before = hand(game)

        cast(game, BEAST, face_down=True)

        assert hand(game) == before  # the Beast left, the Pipes drew one

    def test_a_creature_cast_face_up_is_not(self, builder):
        game = board(builder, [PIPES], hand=[BEAST])
        before = hand(game)

        cast(game, BEAST, face_down=False)

        assert hand(game) == before - 1

    def test_an_opponents_manifest_is_not_yours(self, builder):
        game = board(builder, [PIPES])
        before = hand(game)

        manifest(game, controller=1)

        assert hand(game) == before


class TestFaceUp:
    def test_false_hears_a_face_up_arrival(self, builder):
        game = board(builder, [WATCH], hand=[BEAST])
        before = life(game)

        cast(game, BEAST, face_down=False)

        assert life(game) == before + 1

    def test_false_does_not_hear_a_face_down_one(self, builder):
        game = board(builder, [WATCH], hand=[BEAST])
        before = life(game)

        cast(game, BEAST, face_down=True)
        manifest(game)

        assert life(game) == before


class TestTheShell:
    def test_a_manifested_land_is_a_face_down_creature(self, builder):
        """708.2: the shell is a Creature whatever is underneath it -- here the
        top card is a Forest."""
        game = board(builder, [PIPES], top=FOREST)
        before = hand(game)

        manifest(game)

        assert hand(game) == before + 1

    def test_a_manifested_land_is_not_a_land_entering(self, builder):
        game = board(builder, [LANDFALL], top=FOREST)
        before = life(game)

        manifest(game)

        assert life(game) == before

    def test_a_morph_cast_face_down_has_no_enters_ability(self, builder):
        """The hidden card's "when this enters" is not on the shell (708.2)."""
        game = board(builder, hand=[ETB_MORPH])
        before = hand(game)

        cast(game, ETB_MORPH, face_down=True)

        assert hand(game) == before - 1

    def test_cast_face_up_it_does(self, builder):
        game = board(builder, hand=[ETB_MORPH])
        before = hand(game)

        cast(game, ETB_MORPH, face_down=False)

        assert hand(game) == before


class TestTheSelector:
    def test_no_face_down_permanents_is_the_intervening_if(self, builder):
        """Glitch Interpreter: with nothing face down, the condition holds."""
        game = board(builder, hand=[GLITCH])
        before = hand(game)

        cast(game, GLITCH, face_down=False)

        assert hand(game) == before

    def test_one_face_down_permanent_fails_it(self, builder):
        game = board(builder, hand=[GLITCH])
        manifest(game)
        before = hand(game)

        cast(game, GLITCH, face_down=False)

        assert hand(game) == before - 1

    def test_an_opponents_face_down_permanent_does_not(self, builder):
        """`controller: "you"` -- theirs is not one you control."""
        game = board(builder, hand=[GLITCH])
        manifest(game, controller=1)
        before = hand(game)

        cast(game, GLITCH, face_down=False)

        assert hand(game) == before

    def test_face_up_creatures_are_pumped_and_face_down_ones_are_not(self, builder):
        """Whisperwood Elemental's "face-up nontoken creatures you control"."""
        game = board(builder, [BEAR], hand=[WHISPER])
        shell = manifest(game)
        bear = only_oid(game, BEAR)

        cast(game, WHISPER, face_down=False)

        assert pt(game, bear) == (3, 3)
        assert pt(game, shell) == (2, 2)

    def test_turned_face_up_it_is_face_up(self, builder):
        """The status is read live: the same permanent, turned up, matches
        `false` and no longer `true`."""
        game = board(builder, [BEAR], hand=[WHISPER, BEAST])
        beast = cast(game, BEAST, face_down=True)
        game.state.objects[beast].face_down = False
        game.state.bump_chars()

        cast(game, WHISPER, face_down=False)

        assert pt(game, beast) == (6, 6)


class TestWhereItMayBeWritten:
    def test_the_test_cards_load(self):
        for card_id in (PIPES, WATCH, GLITCH, WHISPER):
            compile_card(card_model(card_id))

    def test_it_is_a_boolean(self):
        with pytest.raises(DslError, match="'face_down' is true"):
            compile_card(card_model(PIPES, abilities__0__trigger__filter={"face_down": "you"}))

    def test_it_asks_about_a_permanent(self):
        with pytest.raises(DslError, match="asks about a permanent"):
            compile_card(
                card_model(
                    WHISPER,
                    spell_effects__0__objects={"zone": "graveyard", "face_down": False},
                )
            )

    def test_it_is_refused_on_a_departure(self):
        """Read after the permanent has left, it would be false for everything."""
        with pytest.raises(DslError, match="cannot be read on 'creature_dies'"):
            compile_card(
                card_model(
                    PIPES,
                    abilities__0__trigger={
                        "event": "creature_dies",
                        "controller": "you",
                        "filter": {"face_down": True},
                    },
                )
            )

    def test_it_is_refused_in_a_static_filter(self):
        """A static's filter reads the printed face, which is the hidden card."""
        raw = static_probe(
            {
                "effect": "buff",
                "power": 1,
                "toughness": 1,
                "affects": {"types": ["Creature"], "face_down": False},
            }
        )
        with pytest.raises(DslError, match="face_down"):
            compile_card(CardModel.model_validate(raw))

    def test_it_is_refused_in_a_static_count(self):
        """"As long as you control a face-down permanent" on a static is a
        counting filter, matched against the printed face like `affects` --
        refused for the same reason."""
        raw = static_probe(
            {
                "effect": "buff",
                "power": 1,
                "toughness": 1,
                "affects": {"self_only": True},
                "condition": {
                    "exists": {"zone": "battlefield", "controller": "you", "face_down": True}
                },
            }
        )
        with pytest.raises(DslError, match="face_down"):
            compile_card(CardModel.model_validate(raw))
