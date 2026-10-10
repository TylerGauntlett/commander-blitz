"""The first shipped meld pair: Gisela, the Broken Blade + Bruna, the Fading Light.

    "At the beginning of your end step, if you both own and control Gisela and
    a creature named Bruna, the Fading Light, exile them, then meld them into
    Brisela, Voice of Nightmares." (701.37)

`tests/unit/faces/test_meld.py` proves the mechanism on test cards with the op called
directly. This file is the real cards, end to end, through the real turn: the
end-step trigger, its intervening-if checked as 603.4 requires, the melded
permanent's printed body and its last line, and Bruna's cast trigger.

The clause that is easy to get wrong is "both **own and control**". Control is
what every other "you control" reads; ownership is the half a stolen Bruna (or a
stolen Gisela) fails, and 701.37a is why it matters -- only cards you own can
meld. So each half is asked both questions, in `trigger.condition`, and a board
where either half is borrowed does not meld.

Brisela's lock is `cant_cast_spells` filtered by mana value (see
`test_cant_cast_mana_value.py` for the X half); here it is checked as the
melded permanent carries it: an opponent's three-drop is withheld, their
four-drop is not, and its controller's own three-drop is untouched.
"""

from __future__ import annotations

from commanderblitz.engine import legality
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind, Keyword, Step, Zone
from commanderblitz.engine.player_statics import player_cant_cast_spells
from commanderblitz.engine.primitives import change_control
from commanderblitz.engine.zones import destroy
from tests.conftest import action_for_card, only_oid, pass_until

GISELA = "gisela_the_broken_blade"
BRUNA = "bruna_the_fading_light"
BRISELA = "brisela_voice_of_nightmares"
MV3 = "t_mv3"  # {2}{G} vanilla
MV4 = "t_mv4"  # {3}{G} vanilla


def late_in_the_turn(builder, *, mine=(GISELA, BRUNA), theirs=(), hand1=(), active=0):
    """``active``'s postcombat main, frozen: nothing has happened yet.

    Run it with `play_out`, which lets the engine auto-pass through the end
    step -- trigger and all -- into the next turn, where the player who now
    has a land to play stops it.
    """
    return (
        builder(players=2)
        .battlefield(0, ["forest"] * 4 + list(mine))
        .battlefield(1, ["forest"] * 4 + list(theirs))
        .hand(1, list(hand1))
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .step(Step.POSTCOMBAT_MAIN)
        .active(active)
        .build(advance=False)
    )


def play_out(game):
    game._advance()
    return game


def melded(game) -> list[int]:
    return [
        o.oid
        for o in game.state.battlefield_objects()
        if game.state.card_of(o).id == BRISELA
    ]


class TestTheyMeld:
    def test_at_your_end_step_the_two_become_brisela(self, builder):
        game = late_in_the_turn(builder)
        gisela = only_oid(game, GISELA, 0)
        play_out(game)

        assert melded(game) == [gisela]
        assert game.state.card_of(game.state.objects[gisela]).id == BRISELA

    def test_one_permanent_with_bruna_under_it(self, builder):
        game = late_in_the_turn(builder)
        bruna = only_oid(game, BRUNA, 0)
        gisela = only_oid(game, GISELA, 0)
        play_out(game)

        assert bruna not in game.state.battlefield
        assert game.state.objects[bruna].merged_into == gisela

    def test_brisela_is_a_legendary_9_10_eldrazi_angel(self, builder):
        game = late_in_the_turn(builder)
        gisela = only_oid(game, GISELA, 0)
        play_out(game)

        c = chars(game.state, gisela)
        assert (c.power, c.toughness) == (9, 10)
        assert "Legendary" in c.supertypes
        assert {"Eldrazi", "Angel"} <= set(c.subtypes)

    def test_with_all_four_keywords(self, builder):
        game = late_in_the_turn(builder)
        gisela = only_oid(game, GISELA, 0)
        play_out(game)

        assert {
            Keyword.FLYING.value,
            Keyword.FIRST_STRIKE.value,
            Keyword.VIGILANCE.value,
            Keyword.LIFELINK.value,
        } <= chars(game.state, gisela).keywords

    def test_its_mana_value_is_eleven(self, builder):
        """Gisela's 4 and Bruna's 7: the Brisela ruling."""
        game = late_in_the_turn(builder)
        gisela = only_oid(game, GISELA, 0)
        play_out(game)

        assert game.state.card_of(game.state.objects[gisela]).mana_value == 11

    def test_apart_again_they_are_themselves(self, builder):
        game = late_in_the_turn(builder)
        gisela = only_oid(game, GISELA, 0)
        bruna = only_oid(game, BRUNA, 0)
        play_out(game)
        destroy(game.state, gisela)

        assert game.state.objects[gisela].zone is Zone.GRAVEYARD
        assert game.state.objects[bruna].zone is Zone.GRAVEYARD
        assert game.state.card_of(game.state.objects[gisela]).id == GISELA
        assert game.state.card_of(game.state.objects[bruna]).id == BRUNA


class TestTheyDoNot:
    def test_gisela_alone(self, builder):
        game = play_out(late_in_the_turn(builder, mine=(GISELA,)))

        assert melded(game) == []

    def test_a_bruna_you_control_but_do_not_own(self, builder):
        """701.37a: only cards you own meld. A stolen Bruna is controlled, not owned."""
        game = late_in_the_turn(builder, mine=(GISELA,), theirs=(BRUNA,))
        bruna = only_oid(game, BRUNA, 1)
        change_control(game.state, bruna, 0)
        assert game.state.objects[bruna].controller == 0
        play_out(game)

        assert melded(game) == []
        assert game.state.card_of(game.state.objects[bruna]).id == BRUNA

    def test_a_gisela_you_control_but_do_not_own(self, builder):
        game = late_in_the_turn(builder, mine=(BRUNA,), theirs=(GISELA,))
        change_control(game.state, only_oid(game, GISELA, 1), 0)
        play_out(game)

        assert melded(game) == []

    def test_a_bruna_you_own_but_do_not_control(self, builder):
        game = late_in_the_turn(builder)
        change_control(game.state, only_oid(game, BRUNA, 0), 1)
        play_out(game)

        assert melded(game) == []

    def test_not_at_an_opponents_end_step(self, builder):
        """"Your end step": the opponent's passes, and the game stops in your next
        turn's main phase -- before your own end step comes round."""
        game = play_out(late_in_the_turn(builder, active=1))

        assert game.state.active_idx == 0
        assert game.state.step is Step.PRECOMBAT_MAIN
        assert melded(game) == []


class TestBrunaReturnsAnAngel:
    """"When you cast this spell, you may return target Angel or Human creature card
    from your graveyard to the battlefield" -- and Gisela is an Angel."""

    def cast_bruna(self, builder, graveyard):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 7)
            .hand(0, [BRUNA])
            .graveyard(0, list(graveyard))
            .library(0, ["plains"] * 10)
            .library(1, ["forest"] * 10)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, BRUNA))
        return game

    def answer_the_target(self, game):
        """The trigger asks for its target as it goes on the stack; take the card."""
        decision = game.pending()
        assert decision is not None and decision.kind is not DecisionKind.PRIORITY, decision
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE))

    def on_battlefield(self, game, card_id) -> bool:
        return any(o.def_id == card_id for o in game.state.battlefield_objects(0))

    def test_gisela_comes_back(self, builder):
        game = self.cast_bruna(builder, [GISELA])
        self.answer_the_target(game)
        pass_until(game, lambda g: self.on_battlefield(g, BRUNA))

        assert self.on_battlefield(game, GISELA)

    def test_it_resolves_before_bruna_does(self, builder):
        """A cast trigger goes on the stack above its spell (603.3)."""
        game = self.cast_bruna(builder, [GISELA])
        self.answer_the_target(game)
        pass_until(game, lambda g: self.on_battlefield(g, GISELA))

        assert not self.on_battlefield(game, BRUNA)

    def test_a_card_that_is_neither_is_not_a_target(self, builder):
        game = self.cast_bruna(builder, [MV3])
        pass_until(game, lambda g: self.on_battlefield(g, BRUNA))

        assert [game.state.objects[o].def_id for o in game.state.players[0].graveyard] == [MV3]


class TestBriselasLock:
    """After the meld, on the opponent's turn: they have four Forests and both drops."""

    def after_the_meld(self, builder):
        game = play_out(late_in_the_turn(builder, hand1=(MV3, MV4)))
        assert melded(game)
        assert game.state.active_idx == 1
        return game

    def cast_ids(self, game, pid: int) -> set[str]:
        return {
            game.state.objects[a.source].def_id
            for a in legality._priority_actions(game.state, pid)
            if a.kind is ActionKind.CAST
        }

    def test_an_opponents_three_drop_is_withheld_and_four_is_not(self, builder):
        game = self.after_the_meld(builder)

        assert self.cast_ids(game, 1) == {MV4}

    def test_your_own_three_drop_is_untouched(self, builder):
        """"Your *opponents*" -- Brisela's controller is not named."""
        game = self.after_the_meld(builder)

        assert not player_cant_cast_spells(game.state, 0, game.state.registry.get(MV3))
        assert player_cant_cast_spells(game.state, 1, game.state.registry.get(MV3))

    def test_before_the_meld_nothing_is_locked(self, builder):
        game = late_in_the_turn(builder, mine=(GISELA,), hand1=(MV3, MV4))
        play_out(game)

        assert melded(game) == []
        assert self.cast_ids(game, 1) == {MV3, MV4}
