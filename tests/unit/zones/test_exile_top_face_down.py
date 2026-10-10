"""Exiling a card nobody can see, and still being able to name it later.

"Pay 1 life: Exile the top card of your library face down. Put that card into
your hand at the beginning of your next end step." Necropotence's third line,
and the whole of this capability in one ability.

Two halves, and the second is the one with teeth:

- **Face down** is *privacy*, not identity. `GameObject.face_down` is the 707
  morph/manifest state a permanent has on the battlefield; a card in exile has
  no characteristics to hide behind, so what the printed words buy is that
  nobody has been shown it -- not even its controller. (`hideaway` writes
  `revealed_to.add(pid)` because 702.75a says its controller may look;
  Necropotence says no such thing, and the two must not be spelled the same
  way.)

  An empty `revealed_to` cannot *be* that mark, which is the trap this file
  exists to hold shut. Exile is a **public** zone -- `player_view` sends it in
  full to the whole table -- and `revealed_to` is empty for every card in every
  zone by default, so a face-down exile written that way is indistinguishable
  from an ordinary one and the words are inert: the card would look implemented
  and leak the very information it is printed to hide. Hence
  `hidden_in_exile`, and hence the two tests that read `player_view` rather than
  the object: the flag is only worth anything if it reaches the wire.

- **"That card"** has to still mean something a turn later, and before `as` it
  could not. `_move_found` deliberately writes no `exiled_by` (see
  `_cast_from_window` for why doing so would break Florian), so a delayed return
  written over `exiled_with: "self"` matches nothing and silently hands back no
  card at all -- the worst possible failure for a card whose entire function is
  drawing. Even with the link written it would be **source-wide**: a second
  activation's return would sweep up the first one's card too, where the printed
  "that card" is per-activation. `as` is per-resolution, and `op_delay` copies
  `ctx.bindings` when it schedules, so the delayed half moves exactly the card
  this activation exiled.

The pairing with `your_turn` is not incidental. Without it the return fires at
the next end step of *anybody's* turn, which for an ability used at instant
speed on an opponent's turn is a full turn early.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.serialize import player_view
from tests.conftest import pass_until


def board(builder, card: str):
    return (
        builder(players=2)
        .battlefield(0, [card])
        .hand(0, ["forest"])
        .hand(1, ["forest"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .build()
    )


def activate(game, card_id: str) -> int:
    """Run the ability's effects directly, and return the card it exiled.

    Directly rather than through `legal_actions`: the sandbox never activates an
    activated ability, and what is under test is the ops, not the cost.
    """
    source = next(
        obj.oid for obj in game.state.battlefield_objects(0) if obj.def_id == card_id
    )
    ability = game.state.registry.get(card_id).abilities[0]
    top = game.state.players[0].library[0]
    ctx = EffectContext(state=game.state, controller=0, source_oid=source, targets={}, bindings={})
    list(execute(ctx, list(ability.effects)))
    return top


def run_to_main_of(game, pid: int) -> None:
    pass_until(
        game,
        lambda g: g.state.active_player == pid and g.state.step is Step.PRECOMBAT_MAIN,
    )


class TestTheCardIsExiled:
    def test_the_top_card_leaves_the_library_for_exile(self, builder):
        game = board(builder, "t_necro_impulse")
        before = len(game.state.players[0].library)
        card = activate(game, "t_necro_impulse")

        assert game.state.objects[card].zone is Zone.EXILE
        assert len(game.state.players[0].library) == before - 1

    def test_it_takes_the_top_card_and_asks_nothing(self, builder):
        """A pool of one is not a choice; a tutor at 1 life would be a different card."""
        game = board(builder, "t_necro_impulse")
        expected = game.state.players[0].library[0]
        card = activate(game, "t_necro_impulse")
        assert card == expected
        assert game.pending() is None or game.pending().kind.name == "PRIORITY"


class TestFaceDownIsPrivacy:
    def test_nobody_has_been_shown_it(self, builder):
        """Not even its controller -- `hideaway` is the card that says otherwise."""
        game = board(builder, "t_necro_impulse")
        card = activate(game, "t_necro_impulse")
        assert game.state.objects[card].hidden_in_exile is True
        assert game.state.objects[card].revealed_to == set()

    def test_face_down_is_not_the_battlefield_morph_flag(self, builder):
        """707's `face_down` describes a permanent's characteristics; exile has none."""
        game = board(builder, "t_necro_impulse")
        card = activate(game, "t_necro_impulse")
        assert game.state.objects[card].face_down is False

    def test_an_ordinary_exile_is_not_hidden(self, builder):
        """The control, and the reason the flag exists.

        `revealed_to` is empty here too -- it is empty for every card in every
        zone by default -- so "nobody has been shown it" cannot be what marks a
        face-down exile. Without `hidden_in_exile` the two cards are
        indistinguishable and the printed words are inert.
        """
        game = board(builder, "t_open_impulse")
        card = activate(game, "t_open_impulse")
        assert game.state.objects[card].zone is Zone.EXILE
        assert game.state.objects[card].revealed_to == set()
        assert game.state.objects[card].hidden_in_exile is False

    def test_it_is_not_sent_to_any_seat(self, builder):
        """The whole point: exile is public, so hiding has to reach `player_view`.

        Sending it and marking it hidden would be the leak the card exists to
        prevent -- an opponent reading the state would know the card.
        """
        game = board(builder, "t_necro_impulse")
        card = activate(game, "t_necro_impulse")

        for seat in (0, 1):
            view = player_view(game.state, seat)["players"][0]
            assert card not in [c["oid"] for c in view["exile"]], f"seat {seat} can see it"
            assert view["exile_hidden_count"] == 1, "but the pile is still public"

    def test_an_ordinary_exile_is_sent_to_everybody(self, builder):
        game = board(builder, "t_open_impulse")
        card = activate(game, "t_open_impulse")

        for seat in (0, 1):
            view = player_view(game.state, seat)["players"][0]
            assert card in [c["oid"] for c in view["exile"]]
            assert view["exile_hidden_count"] == 0

    def test_coming_back_to_hand_clears_the_mark(self, builder):
        """A card that changes zones is a new object -- `reset_permanent_state`."""
        game = board(builder, "t_necro_impulse")
        run_to_main_of(game, 0)
        card = activate(game, "t_necro_impulse")
        run_to_main_of(game, 1)

        assert game.state.objects[card].zone is Zone.HAND
        assert game.state.objects[card].hidden_in_exile is False


class TestThatCardComesBack:
    def test_the_binding_names_what_was_exiled(self, builder):
        game = board(builder, "t_necro_impulse")
        source = next(
            obj.oid for obj in game.state.battlefield_objects(0)
            if obj.def_id == "t_necro_impulse"
        )
        ability = game.state.registry.get("t_necro_impulse").abilities[0]
        top = game.state.players[0].library[0]
        ctx = EffectContext(
            state=game.state, controller=0, source_oid=source, targets={}, bindings={}
        )
        list(execute(ctx, list(ability.effects)))
        assert ctx.bindings["impulsed"] == [top]

    def test_the_delay_hands_back_exactly_that_card(self, builder):
        game = board(builder, "t_necro_impulse")
        run_to_main_of(game, 0)
        card = activate(game, "t_necro_impulse")
        assert game.state.objects[card].zone is Zone.EXILE

        run_to_main_of(game, 1)
        assert game.state.objects[card].zone is Zone.HAND
        assert card in game.state.players[0].hand

    def test_two_activations_each_get_their_own_card_back(self, builder):
        """Per-activation, which is what a source-wide `exiled_with` link would lose."""
        game = board(builder, "t_necro_impulse")
        run_to_main_of(game, 0)
        first = activate(game, "t_necro_impulse")
        second = activate(game, "t_necro_impulse")
        assert first != second

        run_to_main_of(game, 1)
        assert game.state.objects[first].zone is Zone.HAND
        assert game.state.objects[second].zone is Zone.HAND

    def test_it_waits_for_your_own_end_step(self, builder):
        """Activated on the opponent's turn, it does not come back on theirs."""
        game = board(builder, "t_necro_impulse")
        run_to_main_of(game, 1)
        card = activate(game, "t_necro_impulse")

        run_to_main_of(game, 0)
        assert game.state.objects[card].zone is Zone.EXILE, (
            "an opponent's end step is not 'your next end step'"
        )

        run_to_main_of(game, 1)
        assert game.state.objects[card].zone is Zone.HAND


class TestTheLoaderRefusesNonsense:
    def card(self, **effect):
        base = {
            "op": "look_at_top",
            "amount": {"const": 1},
            "destination": "exile",
            "objects": {"count": 1},
        }
        base.update(effect)
        return CardModel.model_validate(
            {
                "id": "t_bad_impulse",
                "name": "Test Bad Impulse",
                "oracle_text": "Exile the top card of your library face down.",
                "mana_cost": "{B}",
                "types": ["Sorcery"],
                "colors": ["B"],
                "color_identity": ["B"],
                "spell_effects": [base],
            }
        )

    def test_face_down_into_exile_is_fine(self):
        from commanderblitz.cards.loader import compile_card

        compile_card(self.card(face_down=True))

    def test_face_down_anywhere_else_is_a_load_error(self):
        """It would load clean, print the words and do nothing -- `_move_found`
        writes the privacy only on the way into exile."""
        from commanderblitz.cards.loader import compile_card

        with pytest.raises(DslError, match="face_down"):
            compile_card(self.card(face_down=True, destination="hand"))

    def test_face_down_with_cast_free_is_a_load_error(self):
        """`cast_free` replaces the branch that would honour it."""
        from commanderblitz.cards.loader import compile_card

        with pytest.raises(DslError):
            compile_card(self.card(face_down=True, cast_free=True))
