"""Looking at the top card of your library, privately, for as long as you can.

    Verge Rangers — "You may look at the top card of your library any time."

Rule 400.2: a library is a hidden zone, and rule 701.16a separates *looking* from
*revealing* — a card looked at is seen by the player looking and by nobody else,
while a card revealed is shown to every player. The engine had only the second
half. `reveal_library_top` is Vampire Nocturnus' "play with the top card of your
library revealed", and `serialize` deliberately writes its `library_top` into
**every** seat's view on the argument that an opponent who cannot see a revealed
card is playing against information they are entitled to.

**Without this static there is no honest way to author Verge Rangers.** Reusing
the public one would hand the opponent a card Verge Rangers never shows them —
a strictly different card, and one that gives away which lands are coming off the
top of a deck whose other ability plays lands from there. Reusing the `look_at_top`
op would be a one-shot look at resolution, spent the moment it happened, where the
printed line is a standing permission with no moment for a trigger to fire at.

So the two statics differ in exactly one thing, and this file is about that one
thing: **which seats the card reaches**. Every claim below is therefore asserted
from *both* seats, because a version that sent the card to everybody would pass
every controller-side assertion.

The third claim is the wearing-off: the permission is continuous, not latched, so
it ends the instant its source leaves the battlefield and the card goes back to
being hidden from its own controller too.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.errors import DslError
from automtg.engine.player_statics import player_looks_at_library_top, player_reveals_library_top
from automtg.engine.serialize import player_view
from tests.conftest import only_oid

#: "You may look at the top card of your library any time." — private.
PEEKER = "t_top_peeker"
#: "Play with the top card of your library revealed." — public.
NOCTURNUS = "t_nocturnus"

TOP = "t_deathtoucher"
BEAR = "t_bear"


def position(builder, *cards: str, players: int = 2):
    """``cards`` on seat 0's battlefield, with ``TOP`` on top of their library."""
    return (
        builder(players=players)
        .battlefield(0, list(cards))
        .library(0, [TOP, "island", "island"])
        .library(1, [BEAR, "forest"])
        .build()
    )


def top_seen_by(game, seat: int, of: int = 0):
    """The card ``seat`` is shown on top of ``of``'s library, or ``None``."""
    return player_view(game.state, seat)["players"][of]["library_top"]


def public_flag(game, seat: int, of: int = 0) -> bool:
    return player_view(game.state, seat)["players"][of]["library_top_public"]


class TestNothingLooksByDefault:
    def test_the_reader_says_no(self, builder):
        game = position(builder, BEAR)
        assert player_looks_at_library_top(game.state, 0) is False

    def test_the_library_stays_hidden_from_its_own_controller(self, builder):
        game = position(builder, BEAR)
        assert top_seen_by(game, 0) is None


class TestTheControllerSeesIt:
    def test_the_reader_says_yes(self, builder):
        game = position(builder, PEEKER)
        assert player_looks_at_library_top(game.state, 0) is True

    def test_their_own_seat_is_sent_the_card(self, builder):
        game = position(builder, PEEKER)
        top = top_seen_by(game, 0)
        assert top is not None
        assert top["card_id"] == TOP

    def test_it_is_the_top_card_and_not_the_next_one(self, builder):
        """A zone of one. The rest of the library is still a count."""
        game = position(builder, PEEKER)
        assert top_seen_by(game, 0)["card_id"] == TOP
        assert player_view(game.state, 0)["players"][0]["library_count"] == 3

    def test_it_follows_the_library(self, builder):
        """Continuous, not measured once -- drawing the card shows the next."""
        from automtg.engine.primitives import draw_cards

        game = position(builder, PEEKER)
        assert top_seen_by(game, 0)["card_id"] == TOP

        draw_cards(game.state, 0, 1)

        assert top_seen_by(game, 0)["card_id"] == "island"

    def test_an_empty_library_shows_nothing(self, builder):
        game = builder(players=2).battlefield(0, [PEEKER]).library(0, []).build()
        assert player_looks_at_library_top(game.state, 0) is True
        assert top_seen_by(game, 0) is None


class TestTheOpponentDoesNot:
    """The reason the capability exists. Every assertion here would fail if
    `look_at_library_top` were authored as `reveal_library_top`."""

    def test_the_opponent_s_seat_is_not_sent_the_card(self, builder):
        game = position(builder, PEEKER)
        assert top_seen_by(game, 1) is None

    def test_no_seat_in_a_pod_but_the_controller_s_is(self, builder):
        """Four-player table: one seat sees it, three do not."""
        game = position(builder, PEEKER, players=4)
        assert top_seen_by(game, 0) is not None
        for seat in (1, 2, 3):
            assert top_seen_by(game, seat) is None, f"seat {seat} was shown a private card"

    def test_it_does_not_show_the_controller_anybody_else_s_library(self, builder):
        """"Your library" -- the permission is about one library, not all of them."""
        game = position(builder, PEEKER)
        assert top_seen_by(game, 0, of=1) is None

    def test_the_opponent_does_not_get_the_permission_itself(self, builder):
        """`affects_player: "you"` scopes it the same way the other eight are."""
        game = position(builder, PEEKER)
        assert player_looks_at_library_top(game.state, 1) is False


class TestLookingIsNotRevealing:
    """The two statics are told apart on the wire by `library_top_public`.

    The payload is otherwise identical, so a client with only `library_top`
    cannot word it correctly: calling a private look "revealed" tells its own
    player the opponent shares the knowledge, which is the leak made in the
    reader's head rather than on the wire.
    """

    def test_a_private_look_is_not_public(self, builder):
        game = position(builder, PEEKER)
        assert top_seen_by(game, 0) is not None
        assert public_flag(game, 0) is False

    def test_a_reveal_is_public_to_everyone(self, builder):
        game = position(builder, NOCTURNUS)
        assert public_flag(game, 0) is True
        assert public_flag(game, 1) is True
        assert top_seen_by(game, 1) is not None

    def test_the_two_are_independent_readers(self, builder):
        game = position(builder, PEEKER)
        assert player_looks_at_library_top(game.state, 0) is True
        assert player_reveals_library_top(game.state, 0) is False

    def test_both_at_once_is_public(self, builder):
        """A reveal alongside a look is still a reveal -- the card *is* shown,
        and the weaker permission cannot make it private again."""
        game = position(builder, PEEKER, NOCTURNUS)
        assert public_flag(game, 0) is True
        assert top_seen_by(game, 1) is not None
        assert public_flag(game, 1) is True

    def test_the_flag_is_false_when_no_card_is_sent(self, builder):
        """No card, no claim about it -- so the client never reads a stale
        `true` beside a `null` face."""
        game = position(builder, BEAR)
        assert top_seen_by(game, 0) is None
        assert public_flag(game, 0) is False
        assert public_flag(game, 1) is False


class TestItWearsOff:
    def test_it_stops_when_the_source_leaves(self, builder):
        """A standing permission, not a look that already happened."""
        from automtg.engine.zones import destroy

        game = position(builder, PEEKER)
        assert top_seen_by(game, 0) is not None

        destroy(game.state, only_oid(game, PEEKER))

        assert player_looks_at_library_top(game.state, 0) is False
        assert top_seen_by(game, 0) is None

    def test_a_condition_gates_it_like_the_others(self, builder):
        """It joins the eight player-wide statics `_active_player_statics` gates,
        so an "as long as…" clause on it is asked rather than ignored."""
        every = "t_all_player_statics"

        on = (
            builder(players=2)
            .battlefield(0, [every])
            .library(0, ["forest"] * 5)
            .active(0)
            .build(advance=False)
        )
        assert player_looks_at_library_top(on.state, 0) is True

        off = (
            builder(players=2)
            .battlefield(0, [every])
            .library(0, ["forest"] * 5)
            .active(1)
            .build(advance=False)
        )
        assert player_looks_at_library_top(off.state, 0) is False
        assert top_seen_by(off, 0) is None


class TestTheLoaderRefuses:
    def _card(self, ability: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_peeker_probe",
                "name": "Test Peeker Probe",
                "mana_cost": "{1}{G}",
                "types": ["Creature"],
                "subtypes": ["Scout"],
                "power": 1,
                "toughness": 1,
                "oracle_text": "You may look at the top card of your library any time.",
                "abilities": [
                    {
                        "kind": "static",
                        "text": "You may look at the top card of your library any time.",
                        **ability,
                    }
                ],
            }
        )

    def test_it_takes_the_ordinary_form(self):
        compile_card(self._card({"effect": "look_at_library_top", "affects_player": "you"}))

    def test_it_needs_affects_player(self):
        """A player-wide static with no player is a static about nobody, and
        `_reaches_player`'s "you" default would silently pick one."""
        with pytest.raises(DslError, match="affects_player"):
            compile_card(self._card({"effect": "look_at_library_top"}))

    def test_an_unknown_static_effect_is_still_refused(self):
        """The guard the new name had to be added to, asserted from the outside."""
        with pytest.raises(DslError):
            compile_card(self._card({"effect": "peek_library_top", "affects_player": "you"}))
