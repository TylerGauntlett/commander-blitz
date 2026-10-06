"""The Atraxa, Praetors' Voice superfriends deck: its planeswalkers K to O, doing what they print.

Every card here already cleared the six authoring gates, and that is exactly why
this file exists. Gate 5 -- the behaviour gate -- casts a card once, in one fixed
sandbox, and reads the board. For a planeswalker that is almost nothing: the
harness **never activates an ability**, so the recorded expectation for each of
these twelve cards is "it entered with its printed loyalty". Every loyalty
ability below was unobserved until here, and so was everything that happens on
a later turn:

- **"Until your next turn" durations.** Liliana's -2/-1, Nissa's 5/5 land and
  Kiora's damage shield must survive the opponent's whole turn and end at *your*
  next untap -- an end-of-turn reading passes every same-turn check and is a
  different card.
- **Emblems.** An emblem's effect lives in the command zone and fires on a later
  event: an upkeep, an end step, a land entering, an opponent trying to cast.
- **Statics that bite a later event.** Narset's draw limit, Kasmina's targeting
  tax, Liliana's death-draw.
- **Kasmina, Enigma Sage's grant.** Each other planeswalker you control has her
  loyalty abilities: paid from *that* walker's loyalty, counted against *that*
  walker's one activation a turn, and her -8 reads the colours of the walker
  that activated it.

Each class is one card and asserts the effect *and* the loyalty change of every
ability, plus the near miss -- the reading that would be true of the card
mis-written. Every position holds an `ANCHOR` in each seat: with no play
available the engine's auto-pass runs whole turns inside one `apply`, and an
"until your next turn" check needs priority to stop on the opponent's turn.
"""

from __future__ import annotations

from automtg.engine import legality
from automtg.engine.characteristics import abilities_of, chars
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.primitives import create_token
from tests.conftest import (
    _default_answer,
    activations,
    find_action,
    hand_ids,
    only_oid,
    pass_until,
    pt,
)

ANCHOR = "t_plain_instant"  # {W}, gain 1 life -- a reason for priority to stop
PLAINS = "plains"
BEAR = "t_bear"  # a vanilla 2/2
COURSER = "centaur_courser"  # a vanilla 3/3
WISP = "fugitive_wizard"  # a vanilla 1/1
ANGEL = "serra_angel"  # 4/4 flying, vigilance -- power above Oko's 3
BOLT = "lightning_bolt"  # {R} red instant, 3 damage to any target
BLUE_SORCERY = "divination"  # {2}{U} "Draw two cards."
BLACK_INSTANT = "dark_ritual"  # {B} "Add {B}{B}{B}."
REMOVAL = "fateful_absence"  # {1}{W} instant, "Destroy target creature or planeswalker."


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def answer(game, *, yes: bool = False, pick=None, limit: int = 200) -> None:
    """Let the stack empty, optionally saying yes and choosing rather than declining.

    ``pick`` is a predicate over a CHOOSE action, or ``True`` for "the first one".
    """
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return
        if yes and decision.kind is DecisionKind.MAY:
            game.apply(find_action(game, ActionKind.YES))
            continue
        if pick and decision.kind is DecisionKind.CHOOSE_OBJECTS:
            choice = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and (pick is True or pick(game, a))
                ),
                None,
            )
            if choice is not None:
                game.apply(choice)
                continue
        if (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack did not empty")


def activate(game, oid: int, index: int, targets=None, **kw) -> None:
    """Activate ability ``index`` of ``oid`` (with exactly ``targets``) and settle."""
    lines = activations(game, oid, index)
    assert lines, f"ability {index} is not offered"
    if targets is not None:
        lines = [a for a in lines if [t.id for t in a.targets] == list(targets)]
        assert lines, f"ability {index} is not offered at {targets}"
    game.apply(lines[0])
    answer(game, **kw)


def activate_x(game, oid: int, index: int, x: int) -> None:
    """Activate a -X ability, announce ``x``, and settle."""
    game.apply(activations(game, oid, index)[0])
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_X
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == x)
    )
    answer(game)


def cast(game, card_id: str, pid: int = 0, target: int | None = None, **kw) -> int:
    """Cast ``card_id`` from ``pid``'s hand (at ``target``) and let it resolve."""
    pass_until(game, lambda g: castable(g, card_id, pid))
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card_id
        and (target is None or [t.id for t in a.targets] == [target])
    )
    game.apply(action)
    answer(game, **kw)
    return action.source


def castable(game, card_id: str, pid: int = 0) -> bool:
    return (
        game.pending() is not None
        and game.pending().player == pid
        and any(
            a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
            for a in game.legal_actions()
        )
    )


def offered_casts(game, pid: int) -> set[str]:
    """What ``pid`` could cast now, asked of legality without waiting for priority."""
    return {
        game.state.objects[a.source].def_id
        for a in legality._priority_actions(game.state, pid)
        if a.kind is ActionKind.CAST and a.source is not None
    }


def loyalty(game, oid: int) -> int:
    return game.state.objects[oid].counters.get("loyalty", 0)


def tokens(game, def_id: str, pid: int | None = None) -> list:
    return [o for o in game.state.battlefield_objects(pid) if o.def_id == def_id and o.is_token]


def library(game, pid: int = 0) -> int:
    return len(game.state.players[pid].library)


def to_step(game, step: Step, active: int) -> None:
    """Pass to ``step`` of ``active``'s *next* turn reaching it (turn > the start)."""
    start = game.state.turn
    pass_until(
        game,
        lambda g: g.state.step is step and g.state.active_player == active and g.state.turn > start,
    )


def to_opponents_main(game) -> None:
    to_step(game, Step.PRECOMBAT_MAIN, 1)


def to_my_next_upkeep(game) -> None:
    to_step(game, Step.UPKEEP, 0)


def position(builder, mine, theirs=(), *, loyalty_at: dict | None = None, **zones):
    """Player 0 holds ``mine``; both seats get a Plains and an ANCHOR.

    ``loyalty_at`` maps a walker id on my side to the loyalty it starts with.
    ``zones`` takes ``hand``, ``library``, ``graveyard`` and ``their_hand`` lists.
    """
    loyalty_at = loyalty_at or {}
    b = builder(players=2)
    plain = [c for c in mine if c not in loyalty_at]
    b = b.battlefield(0, [*plain, PLAINS])
    for card, n in loyalty_at.items():
        b = b.battlefield(0, [card], counters={"loyalty": n})
    b = b.battlefield(1, [*theirs, PLAINS])
    b = b.hand(0, [ANCHOR, *zones.get("hand", [])])
    b = b.hand(1, [ANCHOR, *zones.get("their_hand", [])])
    if "library" in zones:
        b = b.library(0, zones["library"])
    if "graveyard" in zones:
        b = b.graveyard(0, zones["graveyard"])
    return b.build()


# ----------------------------------------------------------------------
# Kasmina, Enigma Sage
# ----------------------------------------------------------------------


class TestKasminaEnigmaSage:
    """"Each other planeswalker you control has the loyalty abilities of Kasmina."
    "+2: Scry 1." / "-X: Create a 0/0 green and blue Fractal creature token. Put X
    +1/+1 counters on it." / "-8: Search your library for an instant or sorcery
    card that shares a color with this planeswalker, exile that card, then
    shuffle. You may cast that card without paying its mana cost."

    Her printed abilities sit at 3, 4 and 5 (0-2 are the three grant statics);
    a walker she grants them to has them appended after its own, at the same
    3, 4, 5 for a three-ability walker.
    """

    KASMINA = "kasmina_enigma_sage"
    NISSA = "nissa_voice_of_zendikar"  # loyalty 3, three loyalty abilities

    def test_plus_two_scries_and_adds_two_loyalty(self, builder):
        game = position(builder, [self.KASMINA], library=["forest"] * 10)
        kasmina = only_oid(game, self.KASMINA)
        activate(game, kasmina, 3)

        assert loyalty(game, kasmina) == 4
        assert library(game) == 10, "a scry draws nothing"
        assert hand_ids(game) == [ANCHOR]

    def test_minus_x_makes_a_fractal_with_exactly_x_counters(self, builder):
        game = position(builder, [], loyalty_at={self.KASMINA: 4})
        kasmina = only_oid(game, self.KASMINA)
        activate_x(game, kasmina, 4, 3)

        [fractal] = tokens(game, "fractal_0_0_gu", 0)
        assert fractal.counters.get("+1/+1") == 3
        assert pt(game, fractal.oid) == (3, 3)
        assert {str(c) for c in chars(game.state, fractal.oid).colors} == {"G", "U"}
        assert loyalty(game, kasmina) == 1, "-X removes exactly X"

    def test_minus_eight_finds_only_a_card_sharing_her_colours_and_casts_it_free(self, builder):
        """Green-blue Kasmina finds Divination; the red Bolt is not offered."""
        game = position(
            builder,
            [],
            loyalty_at={self.KASMINA: 8},
            library=[BOLT, BLUE_SORCERY, *["forest"] * 6],
        )
        kasmina = only_oid(game, self.KASMINA)
        game.apply(activations(game, kasmina, 5)[0])
        pass_until(game, lambda g: g.pending().kind is DecisionKind.CHOOSE_OBJECTS)
        offered = {
            game.state.objects[a.targets[0].id].def_id
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE
        }
        assert offered == {BLUE_SORCERY}

        answer(game, yes=True, pick=True)
        assert library(game) == 8 - 1 - 2, "exiled Divination, then it drew two"
        assert hand_ids(game).count("forest") == 2
        assert BLUE_SORCERY in [
            game.state.objects[o].def_id for o in game.state.players[0].graveyard
        ], "cast, resolved, and went to the graveyard"
        assert game.state.objects[kasmina].zone is Zone.GRAVEYARD, "8 - 8 = 0 loyalty"

    def test_she_does_not_grant_her_abilities_to_herself(self, builder):
        """"Each **other** planeswalker" -- no doubled set on Kasmina."""
        game = position(builder, [self.KASMINA, self.NISSA])
        kasmina = only_oid(game, self.KASMINA)

        assert len(abilities_of(game.state, kasmina)) == 6, "3 statics + 3 loyalty"

    def test_another_walker_you_control_has_her_loyalty_abilities(self, builder):
        game = position(builder, [self.KASMINA, self.NISSA])
        nissa = only_oid(game, self.NISSA)
        texts = [a.text for a in abilities_of(game.state, nissa)]

        assert texts[3] == "+2: Scry 1."
        assert texts[4].endswith("Put X +1/+1 counters on it.")
        assert texts[5][1:].startswith("8: Search your library"), "the -8"
        assert {a.ability_index for a in activations(game, nissa)} == {0, 1, 3, 4}, (
            "the -8 (5) and Nissa's own -7 (2) are not payable at 3 loyalty"
        )

    def test_a_granted_ability_is_paid_from_the_walker_that_activates_it(self, builder):
        game = position(builder, [self.KASMINA, self.NISSA], library=["forest"] * 10)
        kasmina, nissa = only_oid(game, self.KASMINA), only_oid(game, self.NISSA)
        activate(game, nissa, 3)

        assert loyalty(game, nissa) == 5, "Nissa's 3 + 2"
        assert loyalty(game, kasmina) == 2, "Kasmina's loyalty is untouched"

    def test_a_granted_activation_spends_that_walker_s_one_a_turn_and_only_its(self, builder):
        """606.3 per permanent: Nissa is done for the turn, Kasmina is not."""
        game = position(builder, [self.KASMINA, self.NISSA], library=["forest"] * 10)
        kasmina, nissa = only_oid(game, self.KASMINA), only_oid(game, self.NISSA)
        activate(game, nissa, 3)

        assert activations(game, nissa) == [], "neither Nissa's own nor the granted ones"
        assert activations(game, kasmina), "Kasmina still has her own activation"

    def test_a_granted_minus_x_is_capped_by_that_walker_s_loyalty(self, builder):
        game = position(builder, [self.KASMINA, self.NISSA])
        kasmina, nissa = only_oid(game, self.KASMINA), only_oid(game, self.NISSA)
        game.apply(activations(game, nissa, 4)[0])
        assert game.pending().context["max_x"] == 3, "Nissa's 3, not Kasmina's 2"
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == 3)
        )
        answer(game)

        [fractal] = tokens(game, "fractal_0_0_gu", 0)
        assert pt(game, fractal.oid) == (3, 3)
        assert game.state.objects[nissa].zone is Zone.GRAVEYARD
        assert loyalty(game, kasmina) == 2

    def test_a_granted_minus_eight_reads_the_colours_of_the_walker_that_has_it(self, builder):
        """"…shares a color with **this planeswalker**" -- on mono-black Liliana that
        is black, so Dark Ritual is found and Kasmina's own blue is not."""
        game = position(
            builder,
            [self.KASMINA],
            loyalty_at={"liliana_the_last_hope": 8},
            library=[BLUE_SORCERY, BLACK_INSTANT, *["forest"] * 6],
        )
        liliana = only_oid(game, "liliana_the_last_hope")
        game.apply(activations(game, liliana, 5)[0])
        pass_until(game, lambda g: g.pending().kind is DecisionKind.CHOOSE_OBJECTS)
        offered = {
            game.state.objects[a.targets[0].id].def_id
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE
        }
        assert offered == {BLACK_INSTANT}

    def test_an_opponent_s_walker_does_not_get_them(self, builder):
        """"…planeswalker **you control**"."""
        game = position(builder, [self.KASMINA], theirs=[self.NISSA])
        nissa = only_oid(game, self.NISSA, 1)

        assert len(abilities_of(game.state, nissa)) == 3


# ----------------------------------------------------------------------
# Kasmina, Enigmatic Mentor
# ----------------------------------------------------------------------


class TestKasminaEnigmaticMentor:
    """"Spells your opponents cast that target a creature or planeswalker you
    control cost {2} more to cast." / "-2: Create a 2/2 blue Wizard creature
    token. Draw a card, then discard a card." """

    KASMINA = "kasmina_enigmatic_mentor"

    def test_minus_two_makes_a_wizard_and_loots(self, builder):
        game = position(builder, [self.KASMINA], library=["forest"] * 10)
        kasmina = only_oid(game, self.KASMINA)
        activate(game, kasmina, 1)

        [wizard] = tokens(game, "wizard_2_2_u", 0)
        assert pt(game, wizard.oid) == (2, 2)
        assert {str(c) for c in chars(game.state, wizard.oid).colors} == {"U"}
        assert library(game) == 9, "drew one"
        assert len(game.state.players[0].hand) == 1, "and discarded one"
        assert len(game.state.players[0].graveyard) == 1
        assert loyalty(game, kasmina) == 3

    def removal_targets(self, builder, extra_lands: int):
        """The opponent holds Fateful Absence ({1}{W}, "Destroy target creature or
        planeswalker") with exactly two Plains to spare, and a Wisp of their own as
        the untaxed control target."""
        game = (
            builder(players=2)
            .battlefield(0, [self.KASMINA, BEAR, PLAINS])
            .battlefield(1, [PLAINS, PLAINS, *[PLAINS] * extra_lands, WISP])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR, REMOVAL])
            .active(1)
            .build()
        )
        pass_until(game, lambda g: castable(g, REMOVAL, 1))
        targets = {
            t.id
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == REMOVAL
            for t in a.targets
        }
        return game, targets

    def test_an_opponent_s_two_mana_removal_cannot_reach_your_creature_or_her(self, builder):
        game, targets = self.removal_targets(builder, extra_lands=0)
        bear, kasmina = only_oid(game, BEAR, 0), only_oid(game, self.KASMINA, 0)

        assert bear not in targets and kasmina not in targets
        assert only_oid(game, WISP, 1) in targets, "their own creature is not taxed"

    def test_with_two_more_mana_it_can(self, builder):
        """The tax is {2} more, not a prohibition."""
        game, targets = self.removal_targets(builder, extra_lands=2)
        bear, kasmina = only_oid(game, BEAR, 0), only_oid(game, self.KASMINA, 0)

        assert bear in targets and kasmina in targets


# ----------------------------------------------------------------------
# Kaya the Inexorable
# ----------------------------------------------------------------------


class TestKayaTheInexorable:
    """"+1: Put a ghostform counter on up to one target nontoken creature. It gains
    'When this creature dies or is put into exile, return it to its owner's hand
    and create a 1/1 white Spirit creature token with flying.'" / "-3: Exile
    target nonland permanent." / "-7: You get an emblem with 'At the beginning of
    your upkeep, you may cast a legendary spell from your hand, from your
    graveyard, or from among cards you own in exile without paying its mana
    cost.'" """

    KAYA = "kaya_the_inexorable"

    def test_plus_one_ghostform_returns_the_creature_and_makes_a_spirit(self, builder):
        game = position(builder, [self.KAYA, BEAR, "mountain"], hand=[BOLT])
        kaya, bear = only_oid(game, self.KAYA), only_oid(game, BEAR)
        activate(game, kaya, 0, targets=[bear])
        assert game.state.objects[bear].counters.get("ghostform") == 1
        assert loyalty(game, kaya) == 6

        cast(game, BOLT, target=bear)

        assert game.state.objects[bear].zone is Zone.HAND
        [spirit] = tokens(game, "spirit_1_1_w_flying", 0)
        assert pt(game, spirit.oid) == (1, 1)
        assert "flying" in {str(k) for k in chars(game.state, spirit.oid).keywords}

    def test_plus_one_cannot_target_a_token(self, builder):
        """"…up to one target **nontoken** creature"."""
        game = position(builder, [self.KAYA])
        [zombie] = create_token(game.state, "zombie_2_2_b", 0)
        game.state.bump_chars()
        kaya = only_oid(game, self.KAYA)

        assert all(zombie not in [t.id for t in a.targets] for a in activations(game, kaya, 0))
        assert any(not a.targets for a in activations(game, kaya, 0)), "up to one: none is fine"

    def test_minus_three_exiles_a_nonland_permanent(self, builder):
        game = position(builder, [self.KAYA], theirs=["sol_ring"])
        kaya, ring = only_oid(game, self.KAYA), only_oid(game, "sol_ring", 1)
        their_plains = only_oid(game, PLAINS, 1)
        assert all(
            their_plains not in [t.id for t in a.targets] for a in activations(game, kaya, 1)
        ), "nonland"
        activate(game, kaya, 1, targets=[ring])

        assert game.state.objects[ring].zone is Zone.EXILE
        assert loyalty(game, kaya) == 2

    def test_minus_seven_emblem_casts_a_legendary_free_at_your_next_upkeep(self, builder):
        """A legendary from hand is offered; the nonlegendary Bear is not."""
        game = position(
            builder,
            [],
            loyalty_at={self.KAYA: 7},
            hand=["kasmina_enigmatic_mentor", BEAR],
        )
        kaya = only_oid(game, self.KAYA)
        activate(game, kaya, 2)
        assert len(game.state.players[0].command) == 1, "the emblem"
        assert game.state.objects[kaya].zone is Zone.GRAVEYARD, "7 - 7 = 0"

        to_my_next_upkeep(game)
        pass_until(game, lambda g: g.pending().kind is DecisionKind.CHOOSE_OBJECTS)
        offered = {
            game.state.objects[a.targets[0].id].def_id
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE
        }
        assert "kasmina_enigmatic_mentor" in offered
        assert BEAR not in offered, "a legendary spell only"
        assert self.KAYA in offered, "from your graveyard too"

        answer(
            game,
            pick=lambda g, a: g.state.objects[a.targets[0].id].def_id
            == "kasmina_enigmatic_mentor",
        )
        assert only_oid(game, "kasmina_enigmatic_mentor", 0)
        assert game.state.step is Step.UPKEEP, "cast in the upkeep, before any mana was made"


# ----------------------------------------------------------------------
# Kiora, Master of the Depths
# ----------------------------------------------------------------------


class TestKioraMasterOfTheDepths:
    """"+1: Untap up to one target creature and up to one target land." / "-2:
    Reveal the top four cards of your library. You may put a creature card
    and/or a land card from among them into your hand. Put the rest into your
    graveyard." / "-8: You get an emblem with 'Whenever a creature you control
    enters, you may have it fight target creature.' Then create three 8/8 blue
    Octopus creature tokens." """

    KIORA = "kiora_master_of_the_depths"

    def test_plus_one_untaps_a_creature_and_a_land(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [self.KIORA, PLAINS])
            .battlefield(0, [BEAR, "forest"], tapped=True)
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )
        kiora, bear, forest = (
            only_oid(game, self.KIORA),
            only_oid(game, BEAR),
            only_oid(game, "forest"),
        )
        activate(game, kiora, 0, targets=[bear, forest])

        assert not game.state.objects[bear].tapped
        assert not game.state.objects[forest].tapped
        assert loyalty(game, kiora) == 5

    def test_minus_two_takes_one_creature_and_one_land_and_mills_the_rest(self, builder):
        """"A creature card **and/or** a land card": one of each, not two creatures."""
        game = position(
            builder,
            [self.KIORA],
            library=[BEAR, COURSER, "forest", BOLT, "island", "island"],
        )
        kiora = only_oid(game, self.KIORA)
        activate(game, kiora, 1, pick=True)

        taken = sorted(set(hand_ids(game)) - {ANCHOR})
        assert len(hand_ids(game)) == 3
        assert "forest" in taken and len(set(taken) & {BEAR, COURSER}) == 1
        graveyard = sorted(game.state.objects[o].def_id for o in game.state.players[0].graveyard)
        assert len(graveyard) == 2 and BOLT in graveyard
        assert library(game) == 2, "only the top four were touched"
        assert loyalty(game, kiora) == 2

    def test_minus_eight_emblem_then_three_octopuses_that_fight(self, builder):
        """Printed order: the emblem first, so the Octopuses' own entry triggers it."""
        game = position(builder, [], theirs=[BEAR], loyalty_at={self.KIORA: 8})
        kiora, bear = only_oid(game, self.KIORA), only_oid(game, BEAR, 1)
        game.apply(activations(game, kiora, 2)[0])
        answer(game, yes=True, pick=lambda g, a: a.targets[0].id == bear)

        assert len(game.state.players[0].command) == 1
        assert len(tokens(game, "octopus_8_8_u", 0)) == 3
        assert all(pt(game, o.oid) == (8, 8) for o in tokens(game, "octopus_8_8_u", 0))
        assert game.state.objects[bear].zone is Zone.GRAVEYARD, "an Octopus fought it"
        assert game.state.objects[kiora].zone is Zone.GRAVEYARD

    def test_the_emblem_fights_on_a_later_creature_entering(self, builder):
        game = position(
            builder,
            ["forest", "forest"],
            theirs=[WISP],
            loyalty_at={self.KIORA: 8},
            hand=[BEAR],
        )
        kiora, wisp = only_oid(game, self.KIORA), only_oid(game, WISP, 1)
        # The Octopuses' triggers: decline every fight, so the Wisp survives them.
        game.apply(activations(game, kiora, 2)[0])
        answer(game)
        assert game.state.objects[wisp].zone is Zone.BATTLEFIELD

        bear = cast(game, BEAR, yes=True, pick=lambda g, a: a.targets[0].id == wisp)
        assert game.state.objects[wisp].zone is Zone.GRAVEYARD
        assert game.state.objects[bear].damage == 1, "a fight: the Wisp hit back"


# ----------------------------------------------------------------------
# Kiora, the Crashing Wave
# ----------------------------------------------------------------------


class TestKioraTheCrashingWave:
    """"+1: Until your next turn, prevent all damage that would be dealt to and
    dealt by target permanent an opponent controls." / "-1: Draw a card. You may
    play an additional land this turn." / "-5: You get an emblem with 'At the
    beginning of your end step, create a 9/9 blue Kraken creature token.'" """

    KIORA = "kiora_the_crashing_wave"

    def shielded(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [self.KIORA, PLAINS, "mountain", "mountain"])
            .battlefield(1, [PLAINS, BEAR])
            .hand(0, [ANCHOR, BOLT, BOLT])
            .hand(1, [ANCHOR])
            .build()
        )
        kiora, bear = only_oid(game, self.KIORA), only_oid(game, BEAR, 1)
        activate(game, kiora, 0, targets=[bear])
        return game, kiora, bear

    def test_plus_one_only_targets_an_opponent_s_permanent(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [self.KIORA, BEAR, PLAINS])
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )
        kiora, mine = only_oid(game, self.KIORA), only_oid(game, BEAR, 0)
        targets = {t.id for a in activations(game, kiora, 0) for t in a.targets}

        assert mine not in targets and kiora not in targets
        assert only_oid(game, PLAINS, 1) in targets, "any permanent of theirs"

    def test_plus_one_prevents_damage_to_it_this_turn(self, builder):
        game, kiora, bear = self.shielded(builder)
        assert loyalty(game, kiora) == 3
        cast(game, BOLT, target=bear)

        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[bear].damage == 0

    def test_its_attack_deals_nothing_on_the_opponent_s_turn(self, builder):
        """"Dealt **by**", and still in force on their turn."""
        game, _kiora, bear = self.shielded(builder)
        life = game.state.players[0].life
        pass_until(
            game,
            lambda g: g.pending() is not None
            and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
            and g.pending().player == 1,
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == bear
                and any(t.kind == "player" and t.id == 0 for t in a.targets)
            )
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pass_until(game, lambda g: g.state.step is Step.END_STEP)

        assert game.state.players[0].life == life

    def test_the_shield_ends_at_your_next_turn(self, builder):
        """"Until your next turn", not "until end of turn" -- and not forever."""
        game, _kiora, bear = self.shielded(builder)
        to_my_next_upkeep(game)
        pass_until(game, lambda g: castable(g, BOLT))
        cast(game, BOLT, target=bear)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_minus_one_draws_and_grants_an_extra_land_drop(self, builder):
        game = position(builder, [], loyalty_at={self.KIORA: 3}, hand=["forest", "forest"])
        kiora = only_oid(game, self.KIORA)
        before = library(game)
        activate(game, kiora, 1)
        assert library(game) == before - 1
        assert loyalty(game, kiora) == 2

        game.apply(action_play_land(game))
        answer(game)
        assert any(a.kind is ActionKind.PLAY_LAND for a in game.legal_actions()), (
            "a second land is allowed"
        )

    def test_without_it_one_land_is_all(self, builder):
        """The control for the extra land drop."""
        game = position(builder, [self.KIORA], hand=["forest", "forest"])
        game.apply(action_play_land(game))
        answer(game)
        assert not any(a.kind is ActionKind.PLAY_LAND for a in game.legal_actions())

    def test_minus_five_emblem_makes_a_kraken_at_your_end_step_only(self, builder):
        game = position(builder, [], loyalty_at={self.KIORA: 5})
        kiora = only_oid(game, self.KIORA)
        activate(game, kiora, 2)
        assert len(game.state.players[0].command) == 1
        assert game.state.objects[kiora].zone is Zone.GRAVEYARD

        pass_until(game, lambda g: g.state.active_player == 1)
        [kraken] = tokens(game, "kraken_9_9_u", 0)
        assert pt(game, kraken.oid) == (9, 9)

        to_my_next_upkeep(game)
        assert len(tokens(game, "kraken_9_9_u", 0)) == 1, "the opponent's end step makes none"


def action_play_land(game):
    return next(a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND)


# ----------------------------------------------------------------------
# Liliana, Dreadhorde General
# ----------------------------------------------------------------------


class TestLilianaDreadhordeGeneral:
    """"Whenever a creature you control dies, draw a card." / "+1: Create a 2/2
    black Zombie creature token." / "-4: Each player sacrifices two creatures of
    their choice." / "-9: Each opponent chooses a permanent they control of each
    permanent type and sacrifices the rest." """

    LILIANA = "liliana_dreadhorde_general"

    def test_plus_one_makes_a_zombie(self, builder):
        game = position(builder, [self.LILIANA])
        liliana = only_oid(game, self.LILIANA)
        activate(game, liliana, 1)

        [zombie] = tokens(game, "zombie_2_2_b", 0)
        assert pt(game, zombie.oid) == (2, 2)
        assert loyalty(game, liliana) == 7

    def test_minus_four_each_player_sacrifices_two_and_your_deaths_draw(self, builder):
        game = position(builder, [self.LILIANA, BEAR, BEAR, BEAR], theirs=[BEAR, BEAR, BEAR])
        liliana = only_oid(game, self.LILIANA)
        before = [library(game, 0), library(game, 1)]
        activate(game, liliana, 2)

        mine = [o for o in game.state.battlefield_objects(0) if o.def_id == BEAR]
        theirs = [o for o in game.state.battlefield_objects(1) if o.def_id == BEAR]
        assert (len(mine), len(theirs)) == (1, 1), "two each, not two in all"
        assert library(game, 0) == before[0] - 2, "my two deaths drew two"
        assert library(game, 1) == before[1], "their creatures dying draws me nothing extra"
        assert loyalty(game, liliana) == 2

    def test_an_opponent_s_creature_dying_draws_nothing(self, builder):
        """"A creature **you control** dies"."""
        game = position(builder, [self.LILIANA, "mountain"], theirs=[BEAR], hand=[BOLT])
        bear = only_oid(game, BEAR, 1)
        before = library(game)
        cast(game, BOLT, target=bear)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert library(game) == before

    def test_minus_nine_opponents_keep_one_of_each_type(self, builder):
        game = position(
            builder,
            [BEAR, "forest"],
            theirs=[BEAR, "grizzly_bears", "sol_ring", "mind_stone", "island"],
            loyalty_at={self.LILIANA: 9},
        )
        liliana = only_oid(game, self.LILIANA)
        activate(game, liliana, 3)

        theirs = [o for o in game.state.battlefield_objects(1)]
        kinds = sorted(sorted(chars(game.state, o.oid).types)[0] for o in theirs)
        assert kinds == ["Artifact", "Creature", "Land"], "one of each, the rest sacrificed"
        mine = sorted(o.def_id for o in game.state.battlefield_objects(0))
        assert mine == sorted([BEAR, "forest", PLAINS]), "each OPPONENT; mine is untouched"


# ----------------------------------------------------------------------
# Liliana, the Last Hope
# ----------------------------------------------------------------------


class TestLilianaTheLastHope:
    """"+1: Up to one target creature gets -2/-1 until your next turn." / "-2:
    Mill two cards, then you may return a creature card from your graveyard to
    your hand." / "-7: You get an emblem with 'At the beginning of your end
    step, create X 2/2 black Zombie creature tokens, where X is two plus the
    number of Zombies you control.'" """

    LILIANA = "liliana_the_last_hope"

    def test_plus_one_kills_an_x_1(self, builder):
        game = position(builder, [self.LILIANA], theirs=[WISP])
        liliana, wisp = only_oid(game, self.LILIANA), only_oid(game, WISP, 1)
        activate(game, liliana, 0, targets=[wisp])

        assert game.state.objects[wisp].zone is Zone.GRAVEYARD
        assert loyalty(game, liliana) == 4

    def test_the_shrink_survives_the_opponent_s_turn(self, builder):
        game = position(builder, [self.LILIANA], theirs=[COURSER])
        liliana, courser = only_oid(game, self.LILIANA), only_oid(game, COURSER, 1)
        activate(game, liliana, 0, targets=[courser])
        assert pt(game, courser) == (1, 2)

        to_opponents_main(game)
        assert pt(game, courser) == (1, 2), "until YOUR next turn, not end of turn"

    def test_and_ends_at_your_next_turn(self, builder):
        game = position(builder, [self.LILIANA], theirs=[COURSER])
        liliana, courser = only_oid(game, self.LILIANA), only_oid(game, COURSER, 1)
        activate(game, liliana, 0, targets=[courser])

        to_my_next_upkeep(game)
        assert pt(game, courser) == (3, 3)

    def test_minus_two_mills_two_and_returns_a_creature(self, builder):
        game = position(
            builder, [self.LILIANA], library=["forest", BEAR, "island", "island"]
        )
        liliana = only_oid(game, self.LILIANA)
        activate(game, liliana, 1, pick=True)

        assert sorted(hand_ids(game)) == sorted([ANCHOR, BEAR])
        assert [game.state.objects[o].def_id for o in game.state.players[0].graveyard] == [
            "forest"
        ]
        assert library(game) == 2, "milled exactly two"
        assert loyalty(game, liliana) == 1

    def test_minus_seven_emblem_makes_two_plus_your_zombies_at_your_end_step(self, builder):
        game = position(builder, [], loyalty_at={self.LILIANA: 7})
        liliana = only_oid(game, self.LILIANA)
        [_zombie] = create_token(game.state, "zombie_2_2_b", 0)
        game.state.bump_chars()
        activate(game, liliana, 2)
        assert len(game.state.players[0].command) == 1

        pass_until(game, lambda g: g.state.active_player == 1)
        assert len(tokens(game, "zombie_2_2_b", 0)) == 1 + 3, "X = 2 + the one Zombie"

        to_my_next_upkeep(game)
        assert len(tokens(game, "zombie_2_2_b", 0)) == 4, "not on the opponent's end step"


# ----------------------------------------------------------------------
# Narset Transcendent
# ----------------------------------------------------------------------


class TestNarsetTranscendent:
    """"+1: Look at the top card of your library. If it's a noncreature, nonland
    card, you may reveal it and put it into your hand." / "-2: When you next cast
    an instant or sorcery spell from your hand this turn, it gains rebound." /
    "-9: You get an emblem with 'Your opponents can't cast noncreature spells.'" """

    NARSET = "narset_transcendent"

    def test_plus_one_takes_a_noncreature_nonland_top_card(self, builder):
        game = position(builder, [self.NARSET], library=[BOLT, "forest", "forest"])
        narset = only_oid(game, self.NARSET)
        activate(game, narset, 0, yes=True, pick=True)

        assert BOLT in hand_ids(game)
        assert library(game) == 2
        assert loyalty(game, narset) == 7

    def test_plus_one_leaves_a_creature_on_top(self, builder):
        game = position(builder, [self.NARSET], library=[BEAR, "forest", "forest"])
        narset = only_oid(game, self.NARSET)
        top = game.state.players[0].library[0]
        activate(game, narset, 0, yes=True, pick=True)

        assert hand_ids(game) == [ANCHOR]
        assert game.state.players[0].library[0] == top
        assert loyalty(game, narset) == 7

    def test_minus_two_gives_the_next_spell_rebound(self, builder):
        game = position(
            builder,
            [self.NARSET, "island", "island", "island"],
            hand=[BLUE_SORCERY],
            library=["forest"] * 10,
        )
        narset = only_oid(game, self.NARSET)
        activate(game, narset, 1)
        assert loyalty(game, narset) == 4

        divination = cast(game, BLUE_SORCERY)
        assert game.state.objects[divination].zone is Zone.EXILE, "rebound exiles it"
        assert library(game) == 8

        to_my_next_upkeep(game)
        answer(game, yes=True, pick=True)
        assert library(game) == 8 - 2, "cast again from exile: two more"
        assert game.state.objects[divination].zone is Zone.GRAVEYARD

    def test_minus_nine_emblem_stops_their_noncreature_spells_only(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [self.NARSET], counters={"loyalty": 9})
            .battlefield(0, [PLAINS])
            .battlefield(1, [PLAINS, "forest", "forest"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR, BEAR])
            .build()
        )
        narset = only_oid(game, self.NARSET)
        activate(game, narset, 2)
        assert len(game.state.players[0].command) == 1

        to_opponents_main(game)
        offered = offered_casts(game, 1)
        assert ANCHOR not in offered, "a noncreature spell is locked"
        assert BEAR in offered, "a creature spell is not"


# ----------------------------------------------------------------------
# Narset, Parter of Veils
# ----------------------------------------------------------------------


class TestNarsetParterOfVeils:
    """"Each opponent can't draw more than one card each turn." / "-2: Look at the
    top four cards of your library. You may reveal a noncreature, nonland card
    from among them and put it into your hand. Put the rest on the bottom of
    your library in a random order." """

    NARSET = "narset_parter_of_veils"

    def their_turn(self, builder, *, narset: bool):
        mine = [self.NARSET, PLAINS] if narset else [PLAINS]
        return (
            builder(players=2)
            .battlefield(0, mine)
            .battlefield(1, [PLAINS, "island", "island", "island"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR, BLUE_SORCERY])
            .active(1)
            .step(Step.UPKEEP)
            .build()
        )

    def test_an_opponent_draws_only_one_card_a_turn(self, builder):
        """The draw step's card is their one; Divination then draws nothing."""
        game = self.their_turn(builder, narset=True)
        before = library(game, 1)
        cast(game, BLUE_SORCERY, pid=1)

        assert library(game, 1) == before - 1

    def test_without_her_they_draw_three(self, builder):
        """The control."""
        game = self.their_turn(builder, narset=False)
        before = library(game, 1)
        cast(game, BLUE_SORCERY, pid=1)

        assert library(game, 1) == before - 3

    def test_you_are_not_limited(self, builder):
        """"Each **opponent**": her controller draws for the turn, then two more."""
        game = (
            builder(players=2)
            .battlefield(0, [self.NARSET, PLAINS, "island", "island", "island"])
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR, BLUE_SORCERY])
            .hand(1, [ANCHOR])
            .turn(3)  # not the starting player's first turn, which skips its draw
            .step(Step.UPKEEP)
            .build()
        )
        before = library(game)
        cast(game, BLUE_SORCERY)

        assert library(game) == before - 3

    def test_minus_two_takes_a_noncreature_nonland_and_bottoms_the_rest(self, builder):
        game = position(
            builder,
            [self.NARSET],
            library=[BEAR, "forest", BOLT, "island", "swamp", "swamp"],
        )
        narset = only_oid(game, self.NARSET)
        game.apply(activations(game, narset, 1)[0])
        pass_until(game, lambda g: g.pending().kind is DecisionKind.CHOOSE_OBJECTS)
        offered = {
            game.state.objects[a.targets[0].id].def_id
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE
        }
        assert offered == {BOLT}, "not the Bear, not a land"
        answer(game, pick=True)

        assert BOLT in hand_ids(game)
        lib = [game.state.objects[o].def_id for o in game.state.players[0].library]
        assert lib[:2] == ["swamp", "swamp"], "the rest went to the bottom"
        assert sorted(lib[2:]) == sorted([BEAR, "forest", "island"])
        assert loyalty(game, narset) == 3


# ----------------------------------------------------------------------
# Nissa, Vital Force
# ----------------------------------------------------------------------


class TestNissaVitalForce:
    """"+1: Untap target land you control. Until your next turn, it becomes a 5/5
    Elemental creature with haste. It's still a land." / "-3: Return target
    permanent card from your graveyard to your hand." / "-6: You get an emblem
    with 'Whenever a land you control enters, you may draw a card.'" """

    NISSA = "nissa_vital_force"

    def awaken(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [self.NISSA, PLAINS])
            .battlefield(0, ["forest"], tapped=True)
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )
        nissa, forest = only_oid(game, self.NISSA), only_oid(game, "forest")
        activate(game, nissa, 0, targets=[forest])
        return game, nissa, forest

    def test_plus_one_untaps_the_land_and_makes_it_a_5_5_haste_land_creature(self, builder):
        game, nissa, forest = self.awaken(builder)
        c = chars(game.state, forest)

        assert not game.state.objects[forest].tapped
        assert (c.power, c.toughness) == (5, 5)
        assert {"Creature", "Land"} <= set(c.types), "it's still a land"
        assert "Elemental" in c.subtypes
        assert "haste" in {str(k) for k in c.keywords}
        assert loyalty(game, nissa) == 6

    def test_it_only_targets_your_own_land(self, builder):
        game = position(builder, [self.NISSA])
        nissa = only_oid(game, self.NISSA)
        targets = {t.id for a in activations(game, nissa, 0) for t in a.targets}

        assert only_oid(game, PLAINS, 1) not in targets
        assert only_oid(game, PLAINS, 0) in targets

    def test_the_land_is_still_a_5_5_on_the_opponent_s_turn(self, builder):
        game, _nissa, forest = self.awaken(builder)
        to_opponents_main(game)

        assert pt(game, forest) == (5, 5)
        assert "Creature" in chars(game.state, forest).types

    def test_and_is_just_a_land_again_on_your_next_turn(self, builder):
        game, _nissa, forest = self.awaken(builder)
        to_my_next_upkeep(game)

        assert "Creature" not in chars(game.state, forest).types
        assert "Land" in chars(game.state, forest).types

    def test_minus_three_returns_a_permanent_card_only(self, builder):
        game = position(builder, [self.NISSA], graveyard=[BEAR, BOLT])
        nissa = only_oid(game, self.NISSA)
        bear, bolt = game.state.players[0].graveyard
        targets = {t.id for a in activations(game, nissa, 1) for t in a.targets}
        assert bear in targets and bolt not in targets, "an instant is not a permanent card"

        activate(game, nissa, 1, targets=[bear])
        assert game.state.objects[bear].zone is Zone.HAND
        assert loyalty(game, nissa) == 2

    def test_minus_six_emblem_draws_on_a_later_land_drop(self, builder):
        game = position(builder, [], loyalty_at={self.NISSA: 6}, hand=["forest"])
        nissa = only_oid(game, self.NISSA)
        activate(game, nissa, 2)
        assert len(game.state.players[0].command) == 1
        assert game.state.objects[nissa].zone is Zone.GRAVEYARD

        before = library(game)
        game.apply(action_play_land(game))
        answer(game, yes=True)
        assert library(game) == before - 1


# ----------------------------------------------------------------------
# Nissa, Voice of Zendikar
# ----------------------------------------------------------------------


class TestNissaVoiceOfZendikar:
    """"+1: Create a 0/1 green Plant creature token." / "-2: Put a +1/+1 counter on
    each creature you control." / "-7: You gain X life and draw X cards, where X
    is the number of lands you control." """

    NISSA = "nissa_voice_of_zendikar"

    def test_plus_one_makes_a_plant(self, builder):
        game = position(builder, [self.NISSA])
        nissa = only_oid(game, self.NISSA)
        activate(game, nissa, 0)

        [plant] = tokens(game, "plant_0_1_g", 0)
        assert pt(game, plant.oid) == (0, 1)
        assert loyalty(game, nissa) == 4

    def test_minus_two_counters_your_creatures_only(self, builder):
        game = position(builder, [self.NISSA, BEAR, WISP], theirs=[BEAR])
        nissa = only_oid(game, self.NISSA)
        mine = [only_oid(game, BEAR, 0), only_oid(game, WISP, 0)]
        theirs = only_oid(game, BEAR, 1)
        activate(game, nissa, 1)

        assert all(game.state.objects[o].counters.get("+1/+1") == 1 for o in mine)
        assert not game.state.objects[theirs].counters.get("+1/+1")
        assert loyalty(game, nissa) == 1

    def test_minus_seven_gains_and_draws_per_land(self, builder):
        game = position(builder, ["forest", "forest", "forest"], loyalty_at={self.NISSA: 7})
        nissa = only_oid(game, self.NISSA)
        life, lib = game.state.players[0].life, library(game)
        activate(game, nissa, 2)

        assert game.state.players[0].life == life + 4, "three Forests and the Plains"
        assert library(game) == lib - 4


# ----------------------------------------------------------------------
# Oko, Thief of Crowns
# ----------------------------------------------------------------------


class TestOkoThiefOfCrowns:
    """"+2: Create a Food token." / "+1: Target artifact or creature loses all
    abilities and becomes a green Elk creature with base power and toughness
    3/3." / "-5: Exchange control of target artifact or creature you control and
    target creature an opponent controls with power 3 or less." """

    OKO = "oko_thief_of_crowns"

    def test_plus_two_makes_a_food(self, builder):
        game = position(builder, [self.OKO])
        oko = only_oid(game, self.OKO)
        activate(game, oko, 0)

        [food] = tokens(game, "food_token", 0)
        assert "Artifact" in chars(game.state, food.oid).types
        assert loyalty(game, oko) == 6

    def test_plus_one_elks_a_creature_and_strips_its_abilities(self, builder):
        game = position(builder, [self.OKO], theirs=[ANGEL])
        oko, angel = only_oid(game, self.OKO), only_oid(game, ANGEL, 1)
        activate(game, oko, 1, targets=[angel])
        c = chars(game.state, angel)

        assert (c.power, c.toughness) == (3, 3)
        assert set(c.subtypes) == {"Elk"}, "an Elk, no longer an Angel"
        assert {str(x) for x in c.colors} == {"G"}
        assert not {str(k) for k in c.keywords}, "flying and vigilance are gone"
        assert loyalty(game, oko) == 5

    def test_the_elk_is_permanent(self, builder):
        """No duration: still an Elk on the opponent's turn and on your next."""
        game = position(builder, [self.OKO], theirs=[ANGEL])
        oko, angel = only_oid(game, self.OKO), only_oid(game, ANGEL, 1)
        activate(game, oko, 1, targets=[angel])

        to_my_next_upkeep(game)
        assert pt(game, angel) == (3, 3)
        assert "flying" not in {str(k) for k in chars(game.state, angel).keywords}

    def test_plus_one_turns_an_artifact_into_a_3_3_elk(self, builder):
        game = position(builder, [self.OKO], theirs=["sol_ring"])
        oko, ring = only_oid(game, self.OKO), only_oid(game, "sol_ring", 1)
        activate(game, oko, 1, targets=[ring])
        c = chars(game.state, ring)

        assert set(c.types) == {"Creature"}, "it stops being an artifact (Oko's ruling)"
        assert (c.power, c.toughness) == (3, 3)
        assert not abilities_of(game.state, ring), "Sol Ring's mana ability is gone"

    def test_minus_five_exchanges_your_food_for_their_small_creature(self, builder):
        game = position(builder, [], theirs=[BEAR], loyalty_at={self.OKO: 5})
        oko, bear = only_oid(game, self.OKO), only_oid(game, BEAR, 1)
        [food] = create_token(game.state, "food_token", 0)
        game.state.bump_chars()
        activate(game, oko, 2, targets=[food, bear])

        assert game.state.objects[bear].controller == 0
        assert game.state.objects[food].controller == 1
        assert game.state.objects[oko].zone is Zone.GRAVEYARD

    def test_minus_five_cannot_take_a_creature_with_power_above_three(self, builder):
        game = position(builder, [BEAR], theirs=[ANGEL, WISP], loyalty_at={self.OKO: 5})
        oko = only_oid(game, self.OKO)
        angel, wisp = only_oid(game, ANGEL, 1), only_oid(game, WISP, 1)
        theirs = {a.targets[1].id for a in activations(game, oko, 2)}

        assert wisp in theirs
        assert angel not in theirs, "power 4 is above 3"
