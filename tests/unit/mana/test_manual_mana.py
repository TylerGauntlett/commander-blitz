"""Activating mana abilities by hand.

Two different things live here, and only one of them is a preference.

The **bug**: `costs.mana_sources` collects only `Cost.is_tap_only()` abilities,
and `legality._activate_actions` used to skip *every* mana ability on the
grounds that the solver would handle it. Between them, a mana ability with any
other cost -- a Signet's `{1}`, a Vivid land's counter -- had no code path in
the engine that could activate it at all. Twenty-seven shipped cards were dead.
Those are offered unconditionally now, because nothing else can play them.

The **preference**: `manual_mana` additionally offers the tap-only abilities the
solver *does* handle, so a player can choose which land to tap and which colour
a dual makes. Off by default, which is what keeps the RL action space and the
golden tests where they were -- see `docs/rules-coverage.md`.

The **seat**: `offer_all_abilities` is narrower than the preference and is not
one. A permanent that offers something *besides* its tap-only mana ability shows
both, because a human is going to click it and one option means one click spends
it -- Mind Stone was being sacrificed by the gesture that meant "what can this
do?". Set for human seats only, since an AI picks from a list rather than
clicking and would just tap its rocks for nothing.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.game import _only_pass_or_mana
from commanderblitz.engine.mana import SYMBOL_INDEX

#: A land in hand, so the main-phase window has a reason to stop.
#:
#: `game._should_auto_pass` treats "Pass, or add some mana" as no decision at
#: all and skips the window -- correctly, since mana empties at end of step and
#: there would be nothing to spend it on. A board with *only* mana abilities on
#: it therefore never stops, and there is nothing to assert against. One land
#: drop is the smallest real action that keeps the window open, and it is also
#: the realistic case: you tap a rock because you are about to spend the mana.
FILLER_HAND = ["mountain"]

#: A five-colour commander, for the Commander's Sphere positions below.
#:
#: The Sphere is this file's fixture for "one permanent, five mana options", and
#: it used to offer five off an empty command zone -- because
#: `data/cards/core.cards.json` wrote "any color in your commander's color
#: identity" as five fixed `choose_mode` modes, which is a strictly better card
#: in any deck narrower than five colours. That is fixed, so the five options
#: now have to be *earned* by a commander that actually has five colours.
#:
#: The fixture is better for it: these tests assert that the option the player
#: picks is the mana that arrives, and they now do so on a card that is telling
#: the truth about which options exist.
WUBRG = ["the_ur_dragon"]


def position(
    builder,
    cards,
    *,
    manual: bool = False,
    offer_all: bool = False,
    hand=None,
    pid: int = 0,
    commander=(),
):
    """A main phase with `cards` on the battlefield and the flags set.

    `commander` fills the command zone, which every Commander's Sphere position
    below needs. Its mana ability is "any color **in your commander's color
    identity**", so with an empty command zone 903.4 narrows it to *no* colours
    and the ability offers nothing -- see `WUBRG` below.
    """
    game = (
        builder()
        .battlefield(pid, cards)
        .hand(pid, FILLER_HAND if hand is None else hand)
        .commander(pid, list(commander))
        .step(Step.PRECOMBAT_MAIN)
        .active(pid)
        # The flags decide which actions exist, so they have to be set before the
        # game advances into its first window, not after.
        .build(advance=False)
    )
    game.state.players[pid].manual_mana = manual
    game.state.players[pid].offer_all_abilities = offer_all
    game._advance()
    return game


def activations(game, card_id: str | None = None):
    out = []
    for action in game.legal_actions():
        if action.kind is not ActionKind.ACTIVATE or action.source is None:
            continue
        if card_id and game.state.objects[action.source].def_id != card_id:
            continue
        out.append(action)
    return out


def pool_of(game, pid: int = 0) -> dict[str, int]:
    amounts = game.state.players[pid].mana_pool.amounts
    return {sym: amounts[i] for sym, i in SYMBOL_INDEX.items() if amounts[i]}


class TestAbilitiesTheSolverCannotUse:
    """Offered whether or not the player asked for manual mana."""

    def test_a_signet_is_activatable(self, builder):
        # "{1}, {T}: Add {W}{U}" is not tap-only, so `mana_sources` never sees
        # it. Before this it was an unplayable card wearing a mana ability.
        game = position(builder, ["azorius_signet", "island"])
        assert activations(game, "azorius_signet"), "the Signet offers nothing"

    def test_it_is_offered_with_manual_mana_off(self, builder):
        game = position(builder, ["azorius_signet", "island"], manual=False)
        assert activations(game, "azorius_signet")

    def test_a_filter_land_is_activatable(self, builder):
        game = position(builder, ["skycloud_expanse", "plains"])
        assert activations(game, "skycloud_expanse")

    def test_it_needs_its_cost_paid(self, builder):
        # No land, so the `{1}` is unaffordable and the ability must not appear.
        game = position(builder, ["azorius_signet"])
        assert activations(game, "azorius_signet") == []

    def test_activating_one_adds_its_mana(self, builder):
        game = position(builder, ["azorius_signet", "island"])
        game.apply(activations(game, "azorius_signet")[0])
        # {1} paid by the Island, {W}{U} produced.
        assert pool_of(game) == {"W": 1, "U": 1}


class TestTheTapOnlyOnesAreAPreference:
    def test_a_forest_offers_nothing_by_default(self, builder):
        game = position(builder, ["forest"], manual=False)
        assert activations(game, "forest") == []

    def test_manual_mana_offers_it(self, builder):
        game = position(builder, ["forest"], manual=True)
        assert len(activations(game, "forest")) == 1

    def test_commanders_sphere_offers_one_action_per_colour(self, builder):
        # The roadmap's example. Its mana ability is a five-mode `choose_mode`
        # that the solver resolves by picking an option index; manual mana turns
        # that index into the player's choice.
        game = position(builder, ["commanders_sphere"], manual=True, commander=WUBRG)
        mana = [a for a in activations(game, "commanders_sphere") if a.mana_option is not None]
        assert len(mana) == 5
        assert sorted(a.mana_option for a in mana) == [0, 1, 2, 3, 4]

    def test_each_colour_names_itself(self, builder):
        game = position(builder, ["commanders_sphere"], manual=True, commander=WUBRG)
        labels = {a.option_label for a in activations(game, "commanders_sphere") if a.option_label}
        assert labels == {"{W}", "{U}", "{B}", "{R}", "{G}"}

    def test_the_sacrifice_ability_is_offered_either_way(self, builder):
        # The non-mana ability was always reachable; turning the flag on must
        # not displace it.
        for manual in (False, True):
            game = position(builder, ["commanders_sphere"], manual=manual, commander=WUBRG)
            texts = [a.base_label for a in activations(game, "commanders_sphere")]
            assert any("Sacrifice" in text for text in texts), manual


class TestAPermanentWithMoreThanOneOptionShowsBoth:
    """`offer_all_abilities`: what a click on Mind Stone has to reveal.

    The suppression above is right for a Forest and wrong for a Mind Stone. A
    Forest offers one thing and the solver does it; a Mind Stone offers two, and
    hiding one of them left the panel with a single row that a single click
    fires -- so "what can this artifact do?" sacrificed it.
    """

    def test_mind_stone_offers_both_of_its_abilities(self, builder):
        game = position(builder, ["mind_stone", "mountain"], offer_all=True)
        offered = activations(game, "mind_stone")
        assert len(offered) == 2
        assert sorted(a.ability_index for a in offered) == [0, 1]

    def test_the_mana_one_is_the_one_that_was_missing(self, builder):
        game = position(builder, ["mind_stone", "mountain"], offer_all=True)
        labels = {a.base_label for a in activations(game, "mind_stone")}
        assert any("Add {C}" in label for label in labels)
        assert any("Sacrifice" in label for label in labels)

    def test_without_the_flag_only_the_sacrifice_shows(self, builder):
        # The AI seat's view, and the bug as reported.
        game = position(builder, ["mind_stone", "mountain"], offer_all=False)
        offered = activations(game, "mind_stone")
        assert len(offered) == 1
        assert "Sacrifice" in offered[0].base_label

    def test_a_land_is_still_the_solvers_alone(self, builder):
        # The flag is on for every human seat, so this is the case that decides
        # whether the panel grows a row per land. It must not.
        game = position(builder, ["forest"], offer_all=True)
        assert activations(game, "forest") == []

    def test_nothing_to_choose_between_means_nothing_is_offered(self, builder):
        # No second mana source, so the sacrifice ability's `{1}` is unaffordable
        # and Mind Stone is back to being one thing the solver does.
        game = position(builder, ["mind_stone"], offer_all=True)
        assert activations(game, "mind_stone") == []

    def test_commanders_sphere_reads_as_five_colours_plus_a_sacrifice(self, builder):
        game = position(builder, ["commanders_sphere"], offer_all=True, commander=WUBRG)
        offered = activations(game, "commanders_sphere")
        assert sorted(a.option_label for a in offered if a.option_label) == sorted(
            ["{W}", "{U}", "{B}", "{R}", "{G}"]
        )
        assert any("Sacrifice" in a.base_label for a in offered)


class TestTheChosenYieldIsWhatArrives:
    @pytest.mark.parametrize(
        ("option", "symbol"), [(0, "W"), (1, "U"), (2, "B"), (3, "R"), (4, "G")]
    )
    def test_it_adds_the_colour_that_was_picked(self, builder, option, symbol):
        # The whole point: not "some mana", but the one the player chose.
        game = position(builder, ["commanders_sphere"], manual=True, commander=WUBRG)
        action = next(
            a for a in activations(game, "commanders_sphere") if a.mana_option == option
        )
        game.apply(action)
        assert pool_of(game) == {symbol: 1}

    def test_the_source_ends_up_tapped(self, builder):
        game = position(builder, ["commanders_sphere"], manual=True, commander=WUBRG)
        action = next(a for a in activations(game, "commanders_sphere") if a.mana_option == 0)
        game.apply(action)
        sphere = next(
            o for o in game.state.battlefield_objects(0) if o.def_id == "commanders_sphere"
        )
        assert sphere.tapped


class TestManaAbilitiesNeverUseTheStack:
    """Rule 605.3a. The whole reason `_activate_mana` is not `_activate`."""

    def test_nothing_goes_on_the_stack(self, builder):
        game = position(builder, ["commanders_sphere"], manual=True, commander=WUBRG)
        game.apply(next(a for a in activations(game, "commanders_sphere") if a.mana_option == 0))
        assert game.state.stack == []

    def test_the_player_keeps_priority(self, builder):
        # If this went on the stack the window would pass to the opponent, and
        # the mana would empty before its controller could spend it.
        game = position(builder, ["commanders_sphere"], manual=True, commander=WUBRG)
        game.apply(next(a for a in activations(game, "commanders_sphere") if a.mana_option == 0))
        assert game.state.priority_player == 0

    def test_the_mana_is_still_floating_afterwards(self, builder):
        # It went to the pool rather than vanishing, which is what makes it
        # spendable on the spell the player tapped for in the first place.
        game = position(builder, ["commanders_sphere"], manual=True, commander=WUBRG)
        game.apply(next(a for a in activations(game, "commanders_sphere") if a.mana_option == 0))
        assert pool_of(game) == {"W": 1}
        assert game.state.pending_decision is not None, "the window stayed open"


class TestAManaOnlyWindowIsNotADecision:
    """The other half of offering mana abilities: not stopping for them.

    Eleven of thirteen steps grant priority. Before this, a window whose only
    action was `Pass` was skipped; now a board with two Signets on it can offer
    `Pass` plus four activations in every one of those windows, and stopping at
    all of them would be the "~11 forced Pass clicks per turn" that
    `_should_auto_pass` exists to prevent. Adding mana on its own accomplishes
    nothing -- it empties at end of step, and by construction there is nothing
    else in the window to spend it on.
    """

    def test_pass_plus_mana_counts_as_nothing_to_do(self, builder):
        game = position(builder, ["azorius_signet", "island"])
        options = [a for a in game.legal_actions() if a.kind is not ActionKind.PLAY_LAND]
        # Exactly the shape the shortcut must skip: one Pass, some mana.
        assert any(a.kind is ActionKind.ACTIVATE for a in options)
        assert _only_pass_or_mana(game.state, options, game.state.players[0])

    def test_a_real_action_still_stops(self, builder):
        game = position(builder, ["azorius_signet", "island"])
        # The land drop is a play, so this window is a genuine decision.
        assert not _only_pass_or_mana(
            game.state, game.legal_actions(), game.state.players[0]
        )

    def test_manual_mana_keeps_those_windows(self, builder):
        # Floating mana on purpose is exactly what the flag was turned on for,
        # so the shortcut narrows back to its old "only Pass is legal" test.
        game = position(builder, ["forest"], manual=True)
        options = [a for a in game.legal_actions() if a.kind is not ActionKind.PLAY_LAND]
        assert any(a.kind is ActionKind.ACTIVATE for a in options)
        assert not _only_pass_or_mana(game.state, options, game.state.players[0])

    def test_offer_all_abilities_does_not_keep_them(self, builder):
        # The guard against wiring the new flag into `_only_pass_or_mana` the way
        # `manual_mana` is. It is on for every human seat, so doing that would
        # stop every human at all thirteen steps of every turn.
        game = position(builder, ["azorius_signet", "island"], offer_all=True)
        options = [a for a in game.legal_actions() if a.kind is not ActionKind.PLAY_LAND]
        assert any(a.kind is ActionKind.ACTIVATE for a in options)
        assert _only_pass_or_mana(game.state, options, game.state.players[0])


class TestTheAgentIsUnaffected:
    def test_seats_start_with_it_off(self, builder):
        # `PlayerState.manual_mana` defaulting False is what keeps
        # `ACTION_SPACE_SIZE` at 825 and every golden replay identical.
        game = builder().build()
        assert all(not p.manual_mana for p in game.state.players)

    def test_no_action_carries_a_mana_option_by_default(self, builder):
        game = position(builder, ["forest", "commanders_sphere"], manual=False)
        assert all(a.mana_option is None for a in activations(game))

    def test_offer_all_abilities_is_off_by_default_too(self, builder):
        # Set by `GameSession` for human seats and nowhere else, so a training
        # run and a golden replay see exactly the board they always saw.
        game = builder().build()
        assert all(not p.offer_all_abilities for p in game.state.players)
