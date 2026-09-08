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
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from tests.conftest import action_for_card, only_oid, pass_until

# A targetless noncreature instant. Lightning Bolt was the obvious choice and is
# the wrong one: "any target" auto-targets, the harness takes the first legal
# option, and that is the very creature under test -- which a 3-damage bolt then
# kills before anything can be asserted about its counter.
RITUAL = "pyretic_ritual"  # {1}{R} Instant, "Add {R}{R}{R}" -- no targets at all
WIZARD = "fugitive_wizard"  # a plain 1/1 Wizard, for the cards that care about the type


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
