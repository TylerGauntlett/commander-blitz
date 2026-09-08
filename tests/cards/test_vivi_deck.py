"""The Vivi Ornitier deck, card by card, doing what it prints.

Every card here already cleared the six authoring gates, and that is exactly why
this file exists. Gate 5 -- the behaviour gate -- casts a card once, in one fixed
sandbox, and reads the board. Two of its documented limits bite almost every card
in this deck:

- **It never activates an ability.** Riptide Laboratory's bounce, Vivi's `{0}`
  mana ability and Kitsa's copy ability are the whole point of those cards, and
  the harness stops before any of them.
- **A trigger that never fires cannot be asserted.** Nothing in that position
  casts a spell *after* the card under test, and this is a spellslinger deck: an
  honest expectation for Sprite Dragon or Electrostatic Infantry is "zero
  counters", which is a statement that the card did not *misfire*, not that it
  works.

So the authoring expectations are floors, and these are the observations. Each
class is one card and asserts the printed sentence the gate could not reach.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.conftest import (
    action_for_card,
    advance_to_step,
    count_on_battlefield,
    only_oid,
    pass_until,
)

# A targetless noncreature instant. Lightning Bolt was the obvious choice and is
# the wrong one: "any target" auto-targets, the harness takes the first legal
# option, and that is the very creature under test -- which a 3-damage bolt then
# kills before anything can be asserted about its counter.
RITUAL = "pyretic_ritual"  # {1}{R} Instant, "Add {R}{R}{R}" -- no targets at all
WIZARD = "fugitive_wizard"  # a plain 1/1 Wizard, for the cards that care about the type
# A castable instant in the OPPONENT's hand, and it is load bearing rather than
# scenery. With no play available to anybody, the engine's auto-pass runs from
# the spell resolving straight through cleanup and into the next turn -- which
# wipes every until-end-of-turn grant before it can be read, and reaches the end
# step that exiles Stormsplitter's token. A test measuring either after cleanup
# would pass whatever the card did.
ANCHOR = "t_plain_instant"  # {W}, gain 1 life -- a reason for priority to stop


def cast(game, card_id: str, pid: int = 0) -> int:
    """Cast ``card_id`` from ``pid``'s hand and let it resolve. Returns its oid."""
    pass_until(
        game,
        lambda g: g.pending() is not None
        and g.pending().player == pid
        and any(
            a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == card_id
            for a in g.legal_actions()
        ),
    )
    action = action_for_card(game, ActionKind.CAST, card_id)
    oid = action.source
    game.apply(action)
    # Not just `not g.state.stack`: a spell leaves the stack as it begins to
    # resolve, so a card whose resolution asks something -- Frantic Search's
    # discard -- would be abandoned mid-resolution with the decision pending.
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )
    return oid


class TestSpriteDragon:
    """"Whenever you cast a noncreature spell, put a +1/+1 counter on this creature."""

    def position(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["sprite_dragon", "mountain", "mountain"])
            .hand(0, [RITUAL])
            .build()
        )
        return game, only_oid(game, "sprite_dragon")

    def test_it_starts_as_a_printed_1_1_with_flying_and_haste(self, builder):
        game, dragon = self.position(builder)
        c = chars(game.state, dragon)
        assert (c.power, c.toughness) == (1, 1)
        assert {"flying", "haste"} <= {str(k) for k in c.keywords}

    def test_casting_a_noncreature_spell_grows_it(self, builder):
        """The gate could only assert zero counters; this is the card working."""
        game, dragon = self.position(builder)
        cast(game, RITUAL)

        assert game.state.objects[dragon].counters.get("+1/+1") == 1
        assert (chars(game.state, dragon).power, chars(game.state, dragon).toughness) == (2, 2)


class TestElectrostaticInfantry:
    """"Whenever you cast an instant or sorcery spell, put a +1/+1 counter on this creature."""

    def position(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["electrostatic_infantry", "mountain", "mountain"])
            .hand(0, [RITUAL])
            .build()
        )
        return game, only_oid(game, "electrostatic_infantry")

    def test_it_has_trample_and_starts_1_2(self, builder):
        game, infantry = self.position(builder)
        c = chars(game.state, infantry)
        assert (c.power, c.toughness) == (1, 2)
        assert "trample" in {str(k) for k in c.keywords}

    def test_an_instant_grows_it_permanently(self, builder):
        """A counter, not a pump -- it must survive the turn it was made in."""
        game, infantry = self.position(builder)
        cast(game, RITUAL)

        assert game.state.objects[infantry].counters.get("+1/+1") == 1
        assert chars(game.state, infantry).power == 2


class TestRiptideLaboratory:
    """"{1}{U}, {T}: Return target Wizard you control to its owner's hand."""

    def position(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["riptide_laboratory", "island", "island", WIZARD])
            .build()
        )
        return game, only_oid(game, "riptide_laboratory")

    def test_the_bounce_is_offered_when_you_control_a_wizard(self, builder):
        """The gate never activates anything, so legality is untested until here.

        Only the bounce is offered, not the `{T}: Add {C}`: mana payment is
        automatic for an AI seat, so a tap-only mana ability is the solver's and
        never reaches the action list. See the "Automatic mana payment" row in
        docs/rules-coverage.md.
        """
        game, lab = self.position(builder)
        activations = [
            a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == lab
        ]
        assert len(activations) == 1
        assert [t.id for t in activations[0].targets] == [only_oid(game, WIZARD)]

    def test_it_returns_the_wizard_to_hand(self, builder):
        game, lab = self.position(builder)
        wizard = only_oid(game, WIZARD)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == lab and a.targets
        )
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack)

        assert game.state.objects[wizard].zone is Zone.HAND

    def test_no_wizard_means_no_bounce_to_offer(self, builder):
        """The boundary: the ability needs a legal target to be activatable at all."""
        game = builder(players=2).battlefield(0, ["riptide_laboratory", "island", "island"]).build()
        lab = only_oid(game, "riptide_laboratory")
        activations = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == lab and a.targets
        ]
        assert activations == []


class TestAbrade:
    """"Choose one -- Abrade deals 3 damage to target creature; or destroy target artifact."""

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["mountain", "mountain"])
            .battlefield(1, ["t_bear", "sol_ring"])
            .hand(0, ["abrade"])
            .build()
        )

    def cast_mode(self, game, choice: int):
        """Cast Abrade and take ``choice``.

        The mode is *not* on the cast action. A mode-owned target is declared
        inside the cast rather than enumerated with it, so casting raises a
        CHOOSE_MODE decision and the target is settled behind it -- the reverse
        of a card-level target. See "Card-level targets chosen before modes" in
        docs/rules-coverage.md.
        """
        game.apply(action_for_card(game, ActionKind.CAST, "abrade"))
        assert game.pending().kind is DecisionKind.CHOOSE_MODE
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == choice)
        )
        pass_until(game, lambda g: not g.state.stack)

    def test_both_modes_are_offered(self, builder):
        """Gate 5 only ever takes the first mode; the second is untested until here."""
        game = self.position(builder)
        game.apply(action_for_card(game, ActionKind.CAST, "abrade"))

        pending = game.pending()
        assert pending.kind is DecisionKind.CHOOSE_MODE
        assert [o.value for o in pending.options] == [0, 1]

    def test_the_burn_mode_kills_a_two_toughness_creature(self, builder):
        game = self.position(builder)
        bear, ring = only_oid(game, "t_bear", 1), only_oid(game, "sol_ring", 1)
        self.cast_mode(game, 0)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert game.state.objects[ring].zone is Zone.BATTLEFIELD

    def test_the_destroy_mode_reaches_an_artifact_the_burn_mode_cannot(self, builder):
        """The point of the second mode: 3 damage does nothing to a Sol Ring."""
        game = self.position(builder)
        bear, ring = only_oid(game, "t_bear", 1), only_oid(game, "sol_ring", 1)
        self.cast_mode(game, 1)

        assert game.state.objects[ring].zone is Zone.GRAVEYARD
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD


class TestArchaeomancer:
    """"When this creature enters, return target instant or sorcery card from your graveyard."""

    def position(self, builder, graveyard):
        return (
            builder(players=2)
            .battlefield(0, ["island"] * 4)
            .graveyard(0, graveyard)
            .hand(0, ["archaeomancer"])
            .build()
        )

    def test_it_returns_a_spell_the_authoring_sandbox_could_not_offer(self, builder):
        """Gate 5's graveyard holds only creatures, so its trigger had no legal target."""
        game = self.position(builder, [RITUAL])
        ritual = game.state.players[0].graveyard[0]

        cast(game, "archaeomancer")
        assert ritual in game.state.players[0].hand
        assert ritual not in game.state.players[0].graveyard

    def test_a_creature_in_the_graveyard_is_not_a_legal_target(self, builder):
        """The boundary -- "instant or sorcery card", not "card"."""
        game = self.position(builder, ["t_bear"])
        bear = game.state.players[0].graveyard[0]

        cast(game, "archaeomancer")
        assert bear in game.state.players[0].graveyard, "a creature card stays put"


class TestFranticSearch:
    """"Draw two cards, then discard two cards. Untap up to three lands."""

    def position(self, builder):
        """Three tapped Swamps to untap, four untapped Islands to pay {2}{U}.

        The two sets have to be different lands: pay with the Swamps and the
        untap has nothing left to observe.
        """
        return (
            builder(players=2)
            .battlefield(0, ["swamp", "swamp", "swamp"], tapped=True)
            .battlefield(0, ["island"] * 4)
            .library(0, ["forest"] * 10)
            .hand(0, ["frantic_search", "mountain", "mountain"])
            .build()
        )

    def test_it_untaps_three_tapped_lands(self, builder):
        """The untap is why this card is free, and no expectation key can see it."""
        game = self.position(builder)
        swamps = [o for o in game.state.battlefield if game.state.objects[o].def_id == "swamp"]
        assert all(game.state.objects[o].tapped for o in swamps)

        game.apply(action_for_card(game, ActionKind.CAST, "frantic_search"))
        # Discard is forced (min 2); the untap is "up to three", so choose the
        # tapped Swamps deliberately -- the default chooser would take the
        # already-untapped Islands and observe nothing.
        while (p := game.pending()) is not None and p.kind is DecisionKind.CHOOSE_OBJECTS:
            wanted = [
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE
                and (p.prompt != "Untap" or a.targets[0].id in swamps)
            ]
            if not wanted:
                game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
                continue
            game.apply(wanted[0])
        pass_until(game, lambda g: not g.state.stack)

        assert not any(game.state.objects[o].tapped for o in swamps)

    def test_it_draws_two_and_discards_two(self, builder):
        game = self.position(builder)
        cast(game, "frantic_search")

        assert len(game.state.players[0].library) == 8, "40 -> drew 2"
        assert len(game.state.players[0].hand) == 2, "3, cast one, +2 draw, -2 discard"
        assert len(game.state.players[0].graveyard) == 3, "2 discards + the instant itself"


class TestManaGeyser:
    """"Add {R} for each tapped land your opponents control."""

    def test_it_counts_only_tapped_opponent_lands(self, builder):
        """Read the event, not the pool: the pool is emptied as the step ends.

        `add_mana_per` reports its multiplier on one mana_added event, which is
        the only durable witness that the count was 3 and not 4.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["mountain"] * 6)
            .battlefield(1, ["mountain", "mountain", "mountain"], tapped=True)
            .battlefield(1, ["forest"])
            .hand(0, ["mana_geyser"])
            .build()
        )
        mark = len(game.state.events)
        cast(game, "mana_geyser")

        bulk = [
            e
            for e in game.state.events[mark:]
            if e.type == "mana_added" and "times" in e.data
        ]
        assert len(bulk) == 1
        assert bulk[0].data == {"mana": "{R}", "times": 3}, "the untapped Forest does not count"


class TestBalmorBattlemageCaptain:
    """"Whenever you cast an instant or sorcery spell, creatures you control get +1/+0 and gain trample."""

    def test_the_team_grows_and_gains_trample(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["balmor_battlemage_captain", "t_bear", "mountain", "mountain"])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .hand(0, [RITUAL])
            .build()
        )
        bear = only_oid(game, "t_bear")
        assert chars(game.state, bear).power == 2
        assert "trample" not in {str(k) for k in chars(game.state, bear).keywords}

        cast(game, RITUAL)

        assert chars(game.state, bear).power == 3, "+1/+0"
        assert chars(game.state, bear).toughness == 2, "toughness is untouched"
        assert "trample" in {str(k) for k in chars(game.state, bear).keywords}


class TestCalderaPyremaw:
    """"…put a +1/+1 counter on this creature. Then it deals damage equal to its power."""

    def test_the_counter_lands_before_the_damage(self, builder):
        """Printed order matters: a 3/3 that grew first deals 4, not 3."""
        game = (
            builder(players=2)
            .battlefield(0, ["caldera_pyremaw", "mountain", "mountain"])
            .hand(0, [RITUAL])
            .build()
        )
        dragon = only_oid(game, "caldera_pyremaw")
        assert chars(game.state, dragon).power == 3

        cast(game, RITUAL)

        assert game.state.objects[dragon].counters.get("+1/+1") == 1
        assert chars(game.state, dragon).power == 4
        assert game.state.players[1].life == 36, "4 damage, the post-counter power"


class TestExaltedFlamerOfTzeentch:
    """"Fire of Tzeentch — …this creature deals 1 damage to each opponent."""

    def test_it_pings_on_an_instant(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["exalted_flamer_of_tzeentch", "mountain", "mountain"])
            .hand(0, [RITUAL])
            .build()
        )
        cast(game, RITUAL)
        assert game.state.players[1].life == 39
        assert game.state.players[0].life == 40, "each OPPONENT, not each player"


class TestStormsplitter:
    """"…create a token that's a copy of this creature. Exile that token at the next end step."""

    def test_it_copies_itself_and_the_copy_is_temporary(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["stormsplitter", "mountain", "mountain"])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .hand(0, [RITUAL])
            .build()
        )
        assert count_on_battlefield(game, "stormsplitter") == 1

        cast(game, RITUAL)
        assert count_on_battlefield(game, "stormsplitter") == 2, "the token copy"
        tokens = [
            o for o in game.state.battlefield_objects(0) if o.def_id == "stormsplitter" and o.is_token
        ]
        assert len(tokens) == 1, "the copy is a token, and the original is not"

    def test_the_token_does_not_survive_the_turn(self, builder):
        """The delayed exile is why this is not strictly better than printed."""
        game = (
            builder(players=2)
            .battlefield(0, ["stormsplitter", "mountain", "mountain"])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .hand(0, [RITUAL])
            .build()
        )
        cast(game, RITUAL)
        assert count_on_battlefield(game, "stormsplitter") == 2

        advance_to_step(game, Step.END_STEP)
        pass_until(game, lambda g: not g.state.stack)
        assert count_on_battlefield(game, "stormsplitter") == 1, "the token is exiled"


class TestAetherfluxReservoir:
    """"Whenever you cast a spell, you gain 1 life for each spell you've cast this turn."""

    def test_the_life_scales_with_the_turn_s_spell_count(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["aetherflux_reservoir"] + ["mountain"] * 6)
            .hand(0, [RITUAL, RITUAL])
            .build()
        )
        assert game.state.players[0].life == 40

        cast(game, RITUAL)
        assert game.state.players[0].life == 41, "first spell this turn: gain 1"

        cast(game, RITUAL)
        assert game.state.players[0].life == 43, "second spell: gain 2, not 1"


class TestViviOrnitier:
    """The commander, and the card gate 5 could say the least about.

    Both printed lines are unreachable in the authoring sandbox: the harness
    never activates an ability, and nothing casts a spell after the card under
    test. So the expectation for the deck's centrepiece was "it is on the
    battlefield", and everything below is new.
    """

    def position(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["vivi_ornitier", "mountain", "mountain"])
            .hand(0, [RITUAL, RITUAL])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        vivi = only_oid(game, "vivi_ornitier")
        # Vivi arrived this turn, and a creature that did is summoning sick.
        # The `{0}` ability prints no `{T}`, so 302.6 does not touch it -- but
        # the ability tests below are about the ability, not about sickness, and
        # the authoring harness clears exactly this before activating anything.
        game.state.objects[vivi].entered_turn = 0
        game.state.bump_chars()
        return game, vivi

    def test_casting_a_noncreature_spell_grows_it_and_burns(self, builder):
        """"…put a +1/+1 counter on Vivi and it deals 1 damage to each opponent."

        One sentence, two halves, and the gate could assert neither.
        """
        game, vivi = self.position(builder)
        before = game.state.players[1].life

        cast(game, RITUAL)

        assert game.state.objects[vivi].counters.get("+1/+1") == 1
        assert game.state.players[1].life == before - 1

    def test_the_damage_does_not_hit_you(self, builder):
        """"each **opponent**"."""
        game, _vivi = self.position(builder)
        before = game.state.players[0].life

        cast(game, RITUAL)

        assert game.state.players[0].life == before

    def zero_ability(self, game, vivi):
        return [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == vivi
        ]

    def test_it_is_not_offered_at_power_zero(self, builder):
        """Vivi is a printed **0/3**, and that is the whole engine of the card.

        "Add X mana …, where X is Vivi Ornitier's power" adds nothing at power
        zero, so legality declines to offer it -- a prompt that cannot change
        anything is the cost `copy_spell`'s `new_targets` was held back over.
        The ability turns on only once the trigger below has grown him, which is
        the loop the deck is built around.
        """
        game, vivi = self.position(builder)
        assert chars(game.state, vivi).power == 0, "the premise"

        assert not self.zero_ability(game, vivi)

    def test_once_grown_it_adds_mana_equal_to_its_power(self, builder):
        """The other half: two counters, two mana.

        Counters rather than a cast, because a ritual would put its own {R}{R}{R}
        in the pool and there would be no way to tell whose mana was whose.
        """
        from automtg.engine.primitives import add_counters

        game, vivi = self.position(builder)
        add_counters(game.state, vivi, "+1/+1", 2)
        game.state.bump_chars()
        assert chars(game.state, vivi).power == 2

        actions = self.zero_ability(game, vivi)
        assert actions, "a grown Vivi offers the ability"
        game.apply(actions[0])
        pass_until(game, lambda g: g.pending() is None or g.pending().kind is DecisionKind.PRIORITY)

        assert game.state.players[0].mana_pool.total() == 2

    def test_it_is_offered_only_once_each_turn(self, builder):
        """"Activate only … once each turn." The second look finds nothing."""
        from automtg.engine.primitives import add_counters

        game, vivi = self.position(builder)
        add_counters(game.state, vivi, "+1/+1", 2)
        game.state.bump_chars()
        game.apply(self.zero_ability(game, vivi)[0])
        pass_until(game, lambda g: g.pending() is None or g.pending().kind is DecisionKind.PRIORITY)

        assert not self.zero_ability(game, vivi)

    def test_it_is_not_offered_on_an_opponents_turn(self, builder):
        """"Activate only during your turn."""
        from automtg.engine.primitives import add_counters

        game, vivi = self.position(builder)
        add_counters(game.state, vivi, "+1/+1", 2)
        game.state.bump_chars()
        pass_until(
            game,
            lambda g: g.state.active_player == 1 and g.pending() is not None,
        )

        assert not self.zero_ability(game, vivi)


class TestArchmageOfRunes:
    """"Instant and sorcery spells you cast cost {1} less to cast."

    A static the gate cannot see: it changes the *price* of a later spell, and
    the sandbox casts only the card under test.
    """

    def position(self, builder, *, archmage: bool):
        board = ["mountain", "mountain"]
        if archmage:
            board = ["archmage_of_runes", *board]
        return (
            builder(players=2)
            .battlefield(0, board)
            .hand(0, [RITUAL])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def castable(self, game) -> bool:
        return any(
            a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == RITUAL
            for a in game.legal_actions()
        )

    def test_the_discount_makes_a_two_drop_castable_off_one_land(self, builder):
        """Pyretic Ritual is {1}{R}; two Mountains pay it either way, so the
        claim is measured at the boundary instead -- one Mountain short."""
        game = self.position(builder, archmage=True)
        # Tap one Mountain, leaving a single untapped land.
        land = next(o for o in game.state.battlefield_objects(0) if o.def_id == "mountain")
        land.tapped = True
        game.state.bump_chars()

        assert self.castable(game), "{1}{R} less {1} is {R}"

    def test_and_without_it_the_same_board_cannot(self, builder):
        """The control. Without it the test above is just "a land pays for a spell"."""
        game = self.position(builder, archmage=False)
        land = next(o for o in game.state.battlefield_objects(0) if o.def_id == "mountain")
        land.tapped = True
        game.state.bump_chars()

        assert not self.castable(game)

    def test_the_cast_trigger_draws(self, builder):
        """"Whenever you cast an instant or sorcery spell, draw a card."""
        game = self.position(builder, archmage=True)
        before = len(game.state.players[0].library)

        cast(game, RITUAL)

        assert len(game.state.players[0].library) == before - 1
