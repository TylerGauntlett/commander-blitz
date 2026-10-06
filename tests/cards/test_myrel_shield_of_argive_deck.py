"""The Myrel, Shield of Argive deck's token engine, card by card, doing what it prints.

Every card here already cleared the six authoring gates, and that is exactly why
this file exists. Gate 5 -- the behaviour gate -- casts a card **once**, in one
fixed sandbox, and reads the board. Four of its documented limits land on the
fourteen cards below, and they are the cards the deck is actually built out of:

- **It never activates an ability.** Valiant Veteran's graveyard pump,
  Recruitment Officer's dig, Memorial to Glory's sacrifice and the whole of
  Decree of Justice's cycling half got no behavioural check at all. For Decree
  that is most of the card: the sandbox casts it, sees thirteen Angels, and
  never learns that cycling it makes **Soldiers**.
- **A trigger that never fires cannot be asserted.** Nothing in that position
  attacks, so Myrel's own token engine and Preeminent Captain's cheat-into-play
  are both unobserved; nothing reaches an opponent's end step, so both of Keeper
  of the Accord's triggers are; and nothing enters *after* the card under test,
  so Court Street Denizen's is. Ten of these fourteen expectations are
  `battlefield_count: 33` plus at most a hand or graveyard size -- "it entered,
  and nothing misfired".
- **A static that prices a later spell is invisible.** Daru Warchief and
  Ballyrush Banneret both discount a *different* card, and the sandbox casts one.
- **A static that reads the board is only ever read on the sandbox's board.**
  Captain of the Watch, Valiant Veteran and Daru Warchief all say "Soldier", and
  a sandbox where the card under test is the only Soldier cannot tell "other
  Soldiers you control" from "creatures".

So the authored expectations are floors, and these are the observations. Each
class is one card, and each pins the **near miss** as well -- the reading that
would be wrong if the card had been written the other way. This deck is unusually
full of them, because almost every card counts something: whether Myrel counts
Soldiers or attackers, whether Keeper compares against the player whose end step
it is or against the board, whether Ballyrush's two subtypes are an or or a sum,
whether Martial Coup's sweeper fires at four or at five.

**Why every position holds an `ANCHOR`.** With no play available to anybody the
engine's auto-pass runs whole turns inside a single `apply`. Two measurements
here die of it: an end-step trigger is overshot by six turns, so a Keeper test
reads a token some *later* opponent's end step made, and a triggered ability's
target decision is answered on the way past, so Court Street Denizen taps nothing
and looks broken. A castable instant in each seat's hand is a reason for priority
to stop, and it is load bearing rather than scenery.
"""

from __future__ import annotations

from automtg.engine import legality
from automtg.engine.characteristics import chars
from automtg.engine.costs import cost_reduction
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.player_statics import player_cant_activate, player_cant_cast_spells
from tests.conftest import (
    _default_answer,
    activations,
    find_action,
    keywords,
    oids_of,
    only_oid,
    pass_until,
    pt,
    settle_completely,
)

PLAINS = "plains"
ANCHOR = "t_plain_instant"  # {W}, gain 1 life -- a reason for priority to stop
BEAR = "t_bear"  # {1}{G} 2/2 vanilla, the opponent's body
# A real Soldier *card* from the deck, and a card rather than a token on purpose:
# a cost reduction is charged to something that gets cast, and no token ever is.
# Resolute Reinforcements is the cheapest one, which is what makes the {1}
# discount observable at a one-land boundary.
SOLDIER = "resolute_reinforcements"  # {1}{W} Human Soldier, flash
# The deck's own white non-Soldier, and the control for every "Soldier" clause
# below. White matters: it keeps the card a legal Court Street Denizen trigger
# while still failing every Soldier filter, so one card serves as the positive
# case for one static and the negative case for four others.
NOT_A_SOLDIER = "soul_warden"  # {W} Human Cleric 1/1
# Both subtypes on one card, which is the only way to ask whether Ballyrush
# Banneret's "Kithkin spells **and** Soldier spells" is an or or a sum.
KITHKIN_SOLDIER = "preeminent_captain"  # {2}{W} Kithkin Soldier
# A Soldier that is neither of the two lords, so it can be buffed and countered
# without its own text confusing the reading.
PLAIN_SOLDIER = "ballyrush_banneret"  # {1}{W} Kithkin Soldier 2/1
WHITE_TOKEN = "soldier_1_1_w"  # 1/1 white Soldier
COLORLESS_TOKEN = "soldier_1_1_c"  # 1/1 *colorless* Soldier artifact -- Myrel's
HUMAN_TOKEN = "human_soldier_1_1_w"  # 1/1 white Human Soldier -- Esgaroth's
ANGEL_TOKEN = "angel_4_4_w_flying"  # 4/4 white Angel with flying -- Decree's
BIG_CREATURE = "moonshaker_cavalry"  # {5}{W}{W}{W}, mana value 8
# The deck's own `Land -- Plains` that is not a basic Plains, which is the only
# shape that can tell a "basic Plains" search from a subtype-only one.
NONBASIC_PLAINS = "idyllic_grange"
MARKER = "secluded_steppe"  # a land that is nothing else, for spotting a reorder


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def answer(game, *, yes: bool = False, pick: bool = False, limit: int = 200) -> None:
    """Let the stack empty, optionally saying yes and choosing rather than declining.

    The passive default answers NO to every `MAY` and finishes every declaration,
    which is right for a board that only needs to settle and wrong for the five
    cards here whose printed second half lives behind a prompt.
    """
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return
        if yes and decision.kind is DecisionKind.MAY:
            game.apply(find_action(game, ActionKind.YES))
            continue
        if pick and decision.kind is DecisionKind.CHOOSE_OBJECTS:
            choice = next((a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE), None)
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


def cast_only(game, card_id: str, pid: int = 0) -> int:
    """Put ``card_id`` on the stack and stop, leaving its questions unanswered."""
    pass_until(
        game,
        lambda g: (
            g.pending() is not None
            and g.pending().player == pid
            and any(
                a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == card_id
                for a in g.legal_actions()
            )
        ),
    )
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    return action.source


def cast(game, card_id: str, pid: int = 0, *, yes: bool = False) -> int:
    """Cast ``card_id`` from ``pid``'s hand and let everything resolve."""
    oid = cast_only(game, card_id, pid)
    answer(game, yes=yes, pick=yes)
    return oid


def offers(game, pid: int, kind: ActionKind) -> set[str]:
    """The def_ids ``pid`` is offered ``kind`` for, read from legality directly.

    `game.legal_actions()` answers for whoever holds the pending decision, and
    three claims below are about a seat that is *never* offered a decision --
    Myrel's lock leaves its opponents with nothing to do, so the engine's
    auto-pass walks straight past them. `legality._priority_actions` is the same
    list the game would hand them, asked without waiting for priority to arrive.
    """
    return {
        game.state.objects[a.source].def_id
        for a in legality._priority_actions(game.state, pid)
        if a.kind is kind and a.source is not None
    }


def attack_with(game, oids, defender: int = 1) -> None:
    """Swing ``oids`` at ``defender`` and close the declaration."""
    pass_until(
        game,
        lambda g: g.pending() is not None and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
    )
    for oid in oids:
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == oid
                and any(t.kind == "player" and t.id == defender for t in a.targets)
            )
        )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def tokens(game, def_id: str, pid: int = 0) -> list:
    return [o for o in game.state.battlefield_objects(pid) if o.def_id == def_id and o.is_token]


def zone_ids(game, pid: int, zone: str) -> list[str]:
    return [game.state.objects[o].def_id for o in getattr(game.state.players[pid], zone)]


# ----------------------------------------------------------------------
# the commander
# ----------------------------------------------------------------------


class TestMyrelShieldOfArgive:
    """The commander, and the card gate 5 could say the least about.

    "During your turn, your opponents can't cast spells or activate abilities of
    artifacts, creatures, or enchantments." / "Whenever Myrel attacks, create X
    1/1 colorless Soldier artifact creature tokens, where X is the number of
    Soldiers you control."

    Neither line is reachable in the authoring sandbox. The first is a
    prohibition on a *seat*, observable only from the action list of a player the
    sandbox never asks; the second needs a combat. So the recorded expectation
    for the deck's centrepiece was `battlefield_count: 33`, and everything below
    is new.
    """

    # -- the lock ----------------------------------------------------------

    def locked(self, builder, *, active: int):
        """Player 0 holds Myrel; player 1 has a spell, a creature and a land to use.

        Recruitment Officer is the opponent's creature rather than a Bear, because
        the claim is about *activating* and a vanilla creature has nothing to
        activate -- a position built out of Bears passes whether the lock reads
        the type line or not. Rogue's Passage is the land beside it, and it is the
        carve-out: the printed line names artifacts, creatures and enchantments
        and stops there.
        """
        return (
            builder(players=2)
            .battlefield(0, ["myrel_shield_of_argive", PLAINS])
            .battlefield(1, [*[PLAINS] * 5, "recruitment_officer", "rogue_s_passage"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .active(active)
            .build(advance=False)
        )

    def test_your_opponents_cannot_cast_during_your_turn(self, builder):
        game = self.locked(builder, active=0)

        assert player_cant_cast_spells(game.state, 1)
        assert ANCHOR not in offers(game, 1, ActionKind.CAST)

    def test_on_their_own_turn_they_can(self, builder):
        """ "**During your turn**" is a condition, and the control for the above."""
        game = self.locked(builder, active=1)

        assert not player_cant_cast_spells(game.state, 1)
        assert ANCHOR in offers(game, 1, ActionKind.CAST)

    def test_it_does_not_lock_you_out_of_your_own_turn(self, builder):
        """ "Your **opponents**" -- the near miss is a symmetric Grand Abolisher."""
        game = self.locked(builder, active=0)

        assert not player_cant_cast_spells(game.state, 0)
        assert ANCHOR in offers(game, 0, ActionKind.CAST)

    def test_a_creatures_ability_is_locked_too(self, builder):
        """The second half of the sentence, and a separate static from the first."""
        game = self.locked(builder, active=0)
        officer = only_oid(game, "recruitment_officer", 1)

        assert player_cant_activate(game.state, 1, officer)
        assert "recruitment_officer" not in offers(game, 1, ActionKind.ACTIVATE)

    def test_and_on_their_turn_it_is_not(self, builder):
        game = self.locked(builder, active=1)
        officer = only_oid(game, "recruitment_officer", 1)

        assert not player_cant_activate(game.state, 1, officer)
        assert "recruitment_officer" in offers(game, 1, ActionKind.ACTIVATE)

    def test_a_land_is_not_locked(self, builder):
        """ "…abilities of **artifacts, creatures, or enchantments**."

        The near miss is the tempting one -- a blanket "can't activate abilities"
        -- and it is a strictly better card: it turns off their mana too.
        """
        game = self.locked(builder, active=0)
        passage = only_oid(game, "rogue_s_passage", 1)

        assert not player_cant_activate(game.state, 1, passage)
        assert "rogue_s_passage" in offers(game, 1, ActionKind.ACTIVATE)

    # -- the attack trigger ------------------------------------------------

    def swing(self, builder, mine=()):
        """Myrel attacks alone; ``mine`` stays home and is only counted."""
        game = (
            builder(players=2)
            .battlefield(0, ["myrel_shield_of_argive", *mine, PLAINS])
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(0)
            .step(Step.UPKEEP)
            .max_turns(2)
            .build()
        )
        myrel = only_oid(game, "myrel_shield_of_argive")
        attack_with(game, [myrel])
        settle_completely(game)
        return game, myrel

    def test_it_counts_itself(self, builder):
        """Myrel is a Human **Soldier**, and X has no "other" in it: X = 1 alone."""
        game, _myrel = self.swing(builder)

        assert len(tokens(game, COLORLESS_TOKEN)) == 1

    def test_it_counts_a_soldier_that_stayed_home(self, builder):
        """ "…the number of **Soldiers you control**", not of attacking Soldiers.

        The near miss reads the combat instead of the board, and on this deck's
        real turns -- a wide board, one or two creatures actually swinging -- it
        makes a different card.
        """
        game, _myrel = self.swing(builder, mine=[PLAIN_SOLDIER])

        assert len(tokens(game, COLORLESS_TOKEN)) == 2

    def test_a_creature_that_is_not_a_soldier_is_not_counted(self, builder):
        """ "**Soldiers** you control", not creatures. Soul Warden adds nothing."""
        game, _myrel = self.swing(builder, mine=[NOT_A_SOLDIER])

        assert len(tokens(game, COLORLESS_TOKEN)) == 1

    def test_the_tokens_are_colorless_artifact_soldiers(self, builder):
        """Not decoration in a mono-white deck.

        The colour is why Court Street Denizen stays silent for every token this
        card makes -- see `TestCourtStreetDenizen` -- and the artifact type is
        what Mondrak and Skullclamp read. A white Soldier token here would pass
        every gate and quietly change two other cards.
        """
        game, _myrel = self.swing(builder)
        (token,) = tokens(game, COLORLESS_TOKEN)
        c = chars(game.state, token.oid)

        assert c.colors == frozenset()
        assert "Artifact" in c.types and "Creature" in c.types
        assert "Soldier" in c.subtypes
        assert (c.power, c.toughness) == (1, 1)

    def test_the_tokens_do_not_join_the_attack(self, builder):
        """They are created, not created attacking -- and `create_token` can do both.

        Printed Myrel makes tokens after attackers are declared, so they are not
        attacking (508.4). The near miss is one word in the card file and four
        extra damage a turn.
        """
        game, myrel = self.swing(builder)
        combat = game.state.combat

        assert combat is not None and combat.attacking(myrel)
        assert all(not combat.attacking(t.oid) for t in tokens(game, COLORLESS_TOKEN))


# ----------------------------------------------------------------------
# the Soldier payoffs
# ----------------------------------------------------------------------


class TestCaptainOfTheWatch:
    """ "Other Soldier creatures you control get +1/+1 and have vigilance."

    The gate saw the three tokens and could say nothing about the anthem: the
    Captain was the only Soldier on that board, so "other Soldier creatures you
    control" and "creatures" were indistinguishable.
    """

    def table(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["captain_of_the_watch", NOT_A_SOLDIER, PLAINS])
            .battlefield(1, [SOLDIER, PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )

    def test_the_tokens_it_makes_are_buffed_by_it(self, builder):
        """A 1/1 white Soldier token, read after the Captain's own static: 2/2."""
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS] * 6)
            .battlefield(1, [PLAINS])
            .hand(0, ["captain_of_the_watch", ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )
        cast(game, "captain_of_the_watch")
        made = tokens(game, WHITE_TOKEN)

        assert len(made) == 3
        assert all(pt(game, t.oid) == (2, 2) for t in made)
        assert all("vigilance" in keywords(game, t.oid) for t in made)

    def test_it_does_not_buff_itself(self, builder):
        """ "**Other** Soldier creatures." The Captain is a Human Soldier itself."""
        game = self.table(builder)

        assert pt(game, only_oid(game, "captain_of_the_watch")) == (3, 3)

    def test_a_creature_that_is_not_a_soldier_gets_nothing(self, builder):
        """ "Other **Soldier** creatures", not other creatures."""
        game = self.table(builder)
        warden = only_oid(game, NOT_A_SOLDIER)

        assert pt(game, warden) == (1, 1)
        assert "vigilance" not in keywords(game, warden)

    def test_an_opponents_soldier_gets_nothing(self, builder):
        """ "…you control"."""
        game = self.table(builder)
        theirs = only_oid(game, SOLDIER, 1)

        assert pt(game, theirs) == (1, 1)
        assert "vigilance" not in keywords(game, theirs)


class TestResoluteReinforcements:
    """ "Flash (You may cast this spell any time you could cast an instant.)"

    The gate casts in a main phase on its own turn, where flash is invisible: a
    card without it is castable there too. The token half is already pinned by
    the recorded expectation and is not re-asserted here.
    """

    def their_turn(self, builder):
        """Player 0's hand holds the flash Soldier and a Soldier without flash.

        Both in one hand rather than two positions, because the claim is a
        *difference* between them and one board rules out every other
        explanation -- same mana, same colour, same subtype, same mana value.
        """
        return (
            builder(players=2)
            .battlefield(0, [PLAINS, PLAINS])
            .battlefield(1, [PLAINS])
            .hand(0, [SOLDIER, "valiant_veteran"])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .active(1)
            .build(advance=False)
        )

    def test_it_is_castable_on_an_opponents_turn(self, builder):
        game = self.their_turn(builder)

        assert SOLDIER in offers(game, 0, ActionKind.CAST)

    def test_a_soldier_without_flash_is_not(self, builder):
        """The control. Valiant Veteran is the same cost, colour and subtype."""
        game = self.their_turn(builder)

        assert "valiant_veteran" not in offers(game, 0, ActionKind.CAST)


class TestDecreeOfJustice:
    """ "Create X 4/4 white Angel creature tokens with flying." / "Cycling {2}{W}" /
    "When you cycle this card, you may pay {X}. If you do, create X 1/1 white
    Soldier creature tokens."

    The gate cast it for thirteen Angels and stopped, which is one of three
    printed lines. Cycling is an activated ability *from hand* -- a zone the gate
    never activates from, for a card it would have to not cast -- and the trigger
    behind it is the reason this card is in a Soldier deck at all.
    """

    def in_hand(self, builder, lands: int):
        return (
            builder(players=2)
            .battlefield(0, [PLAINS] * lands)
            .battlefield(1, [PLAINS])
            .hand(0, ["decree_of_justice"])
            .hand(1, [ANCHOR])
            .library(0, [PLAINS] * 20)
            .build()
        )

    def cycle(self, game) -> None:
        decree = game.state.players[0].hand[0]
        game.apply(next(iter(activations(game, decree))))

    def test_the_doubled_x_halves_what_eight_mana_buys(self, builder):
        """ "{X}{X}{2}{W}{W}" -- eight lands is X = 2, and two Angels.

        The near miss is a single X in the cost, which loads clean, passes every
        gate, and makes a card that is four Angels off at every mana value.
        """
        game = self.in_hand(builder, 8)
        cast_only(game, "decree_of_justice")
        decision = game.pending()

        assert decision.kind is DecisionKind.CHOOSE_X
        assert [o.value for o in decision.options] == [0, 1, 2]

        answer(game)
        assert len(tokens(game, ANGEL_TOKEN)) == 2

    def test_cycling_is_offered_from_hand_and_draws(self, builder):
        """ "{2}{W}, Discard this card: Draw a card." The card ends in the graveyard."""
        game = self.in_hand(builder, 6)
        library = len(game.state.players[0].library)
        self.cycle(game)
        answer(game)

        assert zone_ids(game, 0, "graveyard") == ["decree_of_justice"]
        assert len(game.state.players[0].library) == library - 1
        assert len(game.state.players[0].hand) == 1, "the drawn card"

    def test_the_x_behind_the_cycling_is_what_is_left_after_paying_for_it(self, builder):
        """Six lands, {2}{W} spent cycling: X runs 0..3, not 0..6.

        No printed ceiling anywhere on the card, so 118.3 -- what the player can
        actually pay -- is the only bound there is.
        """
        game = self.in_hand(builder, 6)
        self.cycle(game)
        pass_until(
            game,
            lambda g: g.pending() is not None and g.pending().kind is DecisionKind.MAY,
        )
        game.apply(find_action(game, ActionKind.YES))
        decision = game.pending()

        assert decision.kind is DecisionKind.CHOOSE_X
        assert [o.value for o in decision.options] == [0, 1, 2, 3]

    def test_cycling_makes_soldiers_and_not_angels(self, builder):
        """The whole reason the card is in this deck, and the gate's blind spot.

        Both halves make X tokens off the same X, so a card file that reached for
        the Angel token here would be wrong in exactly the way nothing checks:
        three 4/4 fliers instead of three 1/1 Soldiers.
        """
        game = self.in_hand(builder, 6)
        self.cycle(game)
        answer(game, yes=True)

        assert len(tokens(game, WHITE_TOKEN)) == 3
        assert tokens(game, ANGEL_TOKEN) == []

    def test_declining_the_payment_makes_nothing(self, builder):
        """ "you **may** pay {X}" -- and the draw happens either way."""
        game = self.in_hand(builder, 6)
        self.cycle(game)
        answer(game)

        assert tokens(game, WHITE_TOKEN) == []
        assert len(game.state.players[0].hand) == 1, "cycling still drew"


class TestMartialCoup:
    """ "Create X 1/1 white Soldier creature tokens. If X is 5 or more, destroy all
    other creatures."

    The gate cast it at X = 20, where both halves fire, and recorded twenty
    tokens and an emptied opponent. What it cannot see is the threshold -- the
    whole decision the card asks its caster -- or the word "other", which at
    X = 20 is indistinguishable from a sweeper that spares nothing, because
    twenty 1/1s were the only creatures on the board it swept.
    """

    def table(self, builder, lands: int):
        """Exactly enough lands to fix X: {X}{W}W} off N lands is X = N - 2.

        The alternative is to pick X out of the decision, and this is better:
        the offered ceiling is then itself part of the measurement, and a
        mis-written cost fails here rather than being papered over by a test
        that asks for the X it wants.
        """
        return (
            builder(players=2)
            .battlefield(0, [*[PLAINS] * lands, NOT_A_SOLDIER])
            .battlefield(1, [BEAR, PLAINS])
            .hand(0, ["martial_coup"])
            .hand(1, [ANCHOR])
            .library(0, [PLAINS] * 20)
            .build()
        )

    def test_four_soldiers_leave_every_creature_standing(self, builder):
        """X = 4 is the near miss: "5 or more" written as `>` or as 4 sweeps here."""
        game = self.table(builder, 6)
        cast_only(game, "martial_coup")

        assert [o.value for o in game.pending().options] == [0, 1, 2, 3, 4]
        answer(game)

        assert len(tokens(game, WHITE_TOKEN)) == 4
        assert oids_of(game, NOT_A_SOLDIER, 0), "your own creature lives"
        assert oids_of(game, BEAR, 1), "and so does theirs"

    def test_five_soldiers_sweep_everything_else(self, builder):
        """X = 5, and "all other creatures" reaches your side of the table too."""
        game = self.table(builder, 7)
        cast_only(game, "martial_coup")

        assert [o.value for o in game.pending().options] == [0, 1, 2, 3, 4, 5]
        answer(game)

        assert oids_of(game, NOT_A_SOLDIER, 0) == [], "'all', not 'all theirs'"
        assert oids_of(game, BEAR, 1) == []

    def test_the_tokens_it_just_made_survive_their_own_sweeper(self, builder):
        """ "all **other** creatures" -- and the tokens are created first.

        Without the word, the card destroys the five Soldiers it just made and is
        a five-mana Wrath of God that leaves nothing behind.
        """
        game = self.table(builder, 7)
        cast(game, "martial_coup")

        assert len(tokens(game, WHITE_TOKEN)) == 5


class TestValiantVeteran:
    """ "Other Soldiers you control get +1/+1." / "{3}{W}{W}, Exile this card from
    your graveyard: Put a +1/+1 counter on each Soldier you control."

    Two lines the gate could not reach for two different reasons: the anthem
    because the Veteran was the only Soldier in the sandbox, and the ability
    because it is activated, and activated from the **graveyard** -- a zone the
    harness never activates from even when it activates.
    """

    def board(self, builder, *, veteran_in="battlefield"):
        """The Veteran on the battlefield or in the graveyard, same board otherwise.

        Ballyrush Banneret is the Soldier being measured rather than a token,
        because a token has to be made by something and the thing that makes one
        here would be the card under test.
        """
        b = (
            builder(players=2)
            .battlefield(0, [*[PLAINS] * 5, PLAIN_SOLDIER, NOT_A_SOLDIER])
            .battlefield(1, [SOLDIER, PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
        )
        if veteran_in == "battlefield":
            b = b.battlefield(0, ["valiant_veteran"])
        else:
            b = b.graveyard(0, ["valiant_veteran"])
        return b.build()

    def test_other_soldiers_get_plus_one_plus_one(self, builder):
        game = self.board(builder)

        assert pt(game, only_oid(game, PLAIN_SOLDIER)) == (3, 2), "a 2/1 Banneret"

    def test_it_does_not_buff_itself(self, builder):
        """ "**Other** Soldiers." The Veteran is a Kor Soldier."""
        game = self.board(builder)

        assert pt(game, only_oid(game, "valiant_veteran")) == (2, 2)

    def test_a_non_soldier_and_an_opponents_soldier_get_nothing(self, builder):
        game = self.board(builder)

        assert pt(game, only_oid(game, NOT_A_SOLDIER)) == (1, 1)
        assert pt(game, only_oid(game, SOLDIER, 1)) == (1, 1)

    def pump(self, game) -> int:
        veteran = game.state.players[0].graveyard[0]
        actions = activations(game, veteran)
        assert actions, "the graveyard ability was not offered"
        game.apply(actions[0])
        settle_completely(game)
        return veteran

    def test_the_graveyard_ability_counters_every_soldier_you_control(self, builder):
        game = self.board(builder, veteran_in="graveyard")
        self.pump(game)

        assert game.state.objects[only_oid(game, PLAIN_SOLDIER)].counters == {"+1/+1": 1}

    def test_it_counters_neither_a_non_soldier_nor_an_opponents_soldier(self, builder):
        """ "each **Soldier you control**" -- two words, two near misses."""
        game = self.board(builder, veteran_in="graveyard")
        self.pump(game)

        assert game.state.objects[only_oid(game, NOT_A_SOLDIER)].counters == {}
        assert game.state.objects[only_oid(game, SOLDIER, 1)].counters == {}

    def test_it_exiles_itself_so_it_cannot_be_done_twice(self, builder):
        """ "**Exile** this card from your graveyard" is the cost, not a rider.

        Written as a graveyard activation without it, five mana a turn buys a
        counter on the whole team for the rest of the game.
        """
        game = self.board(builder, veteran_in="graveyard")
        veteran = self.pump(game)

        assert game.state.objects[veteran].zone is Zone.EXILE
        assert activations(game, veteran) == []

    def test_it_is_not_offered_from_the_battlefield(self, builder):
        """The zone is half the ability: "from your **graveyard**"."""
        game = self.board(builder)

        assert activations(game, only_oid(game, "valiant_veteran")) == []


class TestPreeminentCaptain:
    """ "Whenever this creature attacks, you may put a Soldier creature card from
    your hand onto the battlefield tapped and attacking."

    Nothing attacks in the authoring sandbox, so the recorded expectation was
    `battlefield_count: 33` and the entire card is untested until here. Three
    words in it are each a different card if they are read wrong: **hand**, not
    library; **Soldier**, not creature; and **attacks**, not enters.
    """

    def swing(self, builder, *, hand=(), library=(), attacker="preeminent_captain", mine=()):
        game = (
            builder(players=2)
            .battlefield(0, ["preeminent_captain", *mine, PLAINS])
            .battlefield(1, [PLAINS])
            .hand(0, list(hand))
            .hand(1, [ANCHOR])
            .library(0, list(library) or [PLAINS] * 10)
            .active(0)
            .step(Step.UPKEEP)
            .max_turns(2)
            .build()
        )
        attack_with(game, [only_oid(game, attacker)])
        answer(game, yes=True)
        return game

    def test_it_puts_a_soldier_from_hand_onto_the_battlefield(self, builder):
        game = self.swing(builder, hand=["valiant_veteran"])

        assert oids_of(game, "valiant_veteran", 0), "the Soldier arrived"
        assert game.state.players[0].hand == [], "out of the hand"

    def test_the_soldier_arrives_tapped_and_attacking(self, builder):
        """Both riders, and both are the whole point: an untapped arrival is a
        free blocker as well as a free attacker."""
        game = self.swing(builder, hand=["valiant_veteran"])
        arrival = only_oid(game, "valiant_veteran", 0)

        assert game.state.objects[arrival].tapped
        assert game.state.combat is not None
        assert game.state.combat.attacking(arrival)

    def test_it_reaches_your_hand_and_not_your_library(self, builder):
        """An empty hand and a library full of Soldiers puts nothing down.

        The near miss is the shape of every other tutor on the card pool, and it
        would make this a three-mana Sneak Attack for the deck's whole curve.
        """
        game = self.swing(builder, hand=[], library=["valiant_veteran"] * 6)

        assert oids_of(game, "valiant_veteran", 0) == []
        assert len(game.state.players[0].library) == 6, "nothing left the library"

    def test_a_creature_that_is_not_a_soldier_stays_in_hand(self, builder):
        """ "a **Soldier** creature card."

        Asserted on the board rather than on the prompt: the engine offers the
        `may` before it knows whether anything in hand can answer it, so the
        absence of the question is not the claim -- the absence of the creature is.
        """
        game = self.swing(builder, hand=[NOT_A_SOLDIER])

        assert oids_of(game, NOT_A_SOLDIER, 0) == []
        assert game.state.players[0].hand, "still in hand"

    def test_another_creature_attacking_does_not_trigger_it(self, builder):
        """ "Whenever **this creature** attacks." The Captain stays home."""
        game = self.swing(
            builder,
            hand=["valiant_veteran"],
            mine=[NOT_A_SOLDIER],
            attacker=NOT_A_SOLDIER,
        )

        assert oids_of(game, "valiant_veteran", 0) == []
        assert game.state.players[0].hand, "the Soldier was never offered a way in"


class TestDaruWarchief:
    """ "Soldier spells you cast cost {1} less to cast." / "Soldier creatures you
    control get +1/+2."

    Both statics, and the gate saw neither: a discount is charged to a card the
    sandbox never casts, and an anthem needs a second Soldier on the board to be
    distinguishable from "creatures".
    """

    def board(self, builder, *, lord: bool = True, lands: int = 6):
        return (
            builder(players=2)
            .battlefield(0, [*[PLAINS] * lands] + (["daru_warchief"] if lord else []))
            .battlefield(1, [SOLDIER, PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )

    def priced(self, builder, *, lord: bool, lands: int):
        """The spell in hand, the board frozen exactly as written.

        `advance=False` because the claim is about a board one land short: with
        the discount the seat has a play and the game stops there, and without it
        the seat has none and the engine's auto-pass walks on into a turn with
        its lands untapped again -- which is a different board than the one the
        test describes.
        """
        return (
            builder(players=2)
            .battlefield(0, [*[PLAINS] * lands] + (["daru_warchief"] if lord else []))
            .hand(0, [SOLDIER])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

    def discount(self, game, spell: str, pid: int = 0) -> int:
        return cost_reduction(game.state, pid, game.state.registry.get(spell))

    def test_a_soldier_spell_costs_one_less(self, builder):
        game = self.board(builder)

        assert self.discount(game, SOLDIER) == 1

    def test_a_creature_that_is_not_a_soldier_pays_full_price(self, builder):
        """ "**Soldier** spells", not creature spells."""
        game = self.board(builder)

        assert self.discount(game, NOT_A_SOLDIER) == 0

    def test_it_does_not_discount_an_opponents_soldier(self, builder):
        """ "Soldier spells **you cast**"."""
        game = self.board(builder)

        assert self.discount(game, SOLDIER, pid=1) == 0

    def test_without_it_nothing_is_discounted(self, builder):
        """The control. Without it the first test is "a spell costs what it costs"."""
        game = self.board(builder, lord=False)

        assert self.discount(game, SOLDIER) == 0

    def test_the_discount_is_charged_and_not_merely_computed(self, builder):
        """One Plains, and {1}{W} less {1} is {W}.

        Legality and payment read one function, so the offer is the charge -- and
        a one-land board is the only boundary at which a {1} discount is
        observable from the action list at all.
        """
        game = self.priced(builder, lord=True, lands=1)

        assert SOLDIER in offers(game, 0, ActionKind.CAST)

    def test_and_on_the_same_board_without_it_the_spell_is_a_land_short(self, builder):
        game = self.priced(builder, lord=False, lands=1)

        assert SOLDIER not in offers(game, 0, ActionKind.CAST)

    def test_soldier_creatures_get_plus_one_plus_two(self, builder):
        """ "+1/+**2**", and the line has no "other": the Warchief buffs itself.

        A printed 1/1 reading 2/3 is the whole assertion, and it fails two ways
        -- 2/2 for a copied +1/+1, 1/1 for an "other" that is not printed.
        """
        game = self.board(builder)

        assert pt(game, only_oid(game, "daru_warchief")) == (2, 3)

    def test_a_non_soldier_and_an_opponents_soldier_are_untouched(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["daru_warchief", NOT_A_SOLDIER, PLAINS])
            .battlefield(1, [SOLDIER, PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )

        assert pt(game, only_oid(game, NOT_A_SOLDIER)) == (1, 1)
        assert pt(game, only_oid(game, SOLDIER, 1)) == (1, 1)


class TestBallyrushBanneret:
    """ "Kithkin spells and Soldier spells you cast cost {1} less to cast."

    One static with two subtypes in it, and the gate cast the Banneret onto an
    empty board and read `battlefield_count: 33`. The sentence has a genuine
    ambiguity in it that the card file has to resolve: "Kithkin spells **and**
    Soldier spells" is two sets unioned, not one set intersected, and it is one
    discount rather than two on a card that is both.
    """

    def board(self, builder, *, lord: bool = True, lands: int = 6):
        return (
            builder(players=2)
            .battlefield(0, [*[PLAINS] * lands] + (["ballyrush_banneret"] if lord else []))
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )

    def priced(self, builder, *, lord: bool, lands: int):
        """As `TestDaruWarchief.priced`, and frozen for the same reason."""
        return (
            builder(players=2)
            .battlefield(0, [*[PLAINS] * lands] + (["ballyrush_banneret"] if lord else []))
            .hand(0, [KITHKIN_SOLDIER])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

    def discount(self, game, spell: str, pid: int = 0) -> int:
        return cost_reduction(game.state, pid, game.state.registry.get(spell))

    def test_a_soldier_that_is_not_a_kithkin_is_still_discounted(self, builder):
        """The union. Read as an intersection, a Human Soldier gets nothing."""
        game = self.board(builder)

        assert self.discount(game, SOLDIER) == 1

    def test_a_card_that_is_both_is_still_only_one_less(self, builder):
        """Preeminent Captain is a **Kithkin Soldier**, and the discount is {1}.

        The near miss is two statics, one per subtype, which is the obvious way
        to write the sentence and gives every Kithkin Soldier in the deck {2}.
        """
        game = self.board(builder)

        assert self.discount(game, KITHKIN_SOLDIER) == 1

    def test_neither_subtype_pays_full_price(self, builder):
        game = self.board(builder)

        assert self.discount(game, NOT_A_SOLDIER) == 0

    def test_it_does_not_discount_an_opponents_spell(self, builder):
        game = self.board(builder)

        assert self.discount(game, SOLDIER, pid=1) == 0

    def test_the_discount_is_charged_at_the_boundary(self, builder):
        """{2}{W} less {1} is {1}{W}, which two Plains pay and three are not needed."""
        game = self.priced(builder, lord=True, lands=2)

        assert KITHKIN_SOLDIER in offers(game, 0, ActionKind.CAST)

    def test_and_without_it_the_same_two_lands_cannot(self, builder):
        game = self.priced(builder, lord=False, lands=2)

        assert KITHKIN_SOLDIER not in offers(game, 0, ActionKind.CAST)


class TestRecruitmentOfficer:
    """ "{3}{W}: Look at the top four cards of your library. You may reveal a
    creature card with mana value 3 or less from among them and put it into your
    hand. Put the rest on the bottom of your library in a random order."

    An activated ability and nothing else, so the gate checked that a 2/1 entered
    the battlefield. Two numbers in the sentence are each an off-by-one waiting to
    happen -- **four** cards and mana value **3 or less** -- and the third clause
    decides whether a whiff costs you the top of your library or nothing.
    """

    def dig(self, builder, library, *, take: bool = True):
        game = (
            builder(players=2)
            .battlefield(0, [*[PLAINS] * 4, "recruitment_officer"])
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .library(0, list(library))
            .build()
        )
        officer = only_oid(game, "recruitment_officer")
        game.apply(next(iter(activations(game, officer))))
        answer(game, pick=take)
        return game

    def test_it_finds_a_cheap_creature_and_puts_it_in_hand(self, builder):
        game = self.dig(builder, [NOT_A_SOLDIER, *[PLAINS] * 10])

        assert NOT_A_SOLDIER in zone_ids(game, 0, "hand")
        assert len(game.state.players[0].library) == 10

    def test_the_three_it_did_not_take_go_to_the_bottom(self, builder):
        """ "Put the rest on the bottom", which is the cost of the dig.

        The creature and three Plains are the top four, and a marker sits fifth:
        once the creature is taken the three Plains have to be *under* the
        marker, so the marker is on top. Written as "the rest stay where they
        are" -- the obvious near miss, and a strictly better card -- the marker
        would still be fifth.
        """
        game = self.dig(builder, [NOT_A_SOLDIER, PLAINS, PLAINS, PLAINS, MARKER, *[PLAINS] * 6])
        library = game.state.players[0].library

        assert len(library) == 10, "four seen, one taken, three returned"
        assert game.state.objects[library[0]].def_id == MARKER
        assert game.state.objects[library[-1]].def_id == PLAINS, "the three are underneath"

    def test_a_creature_too_expensive_is_not_offered(self, builder):
        """ "mana value **3 or less**". Moonshaker Cavalry is {5}{W}{W}{W}."""
        game = self.dig(builder, [BIG_CREATURE, *[PLAINS] * 10])
        library = game.state.players[0].library

        assert BIG_CREATURE not in zone_ids(game, 0, "hand")
        assert len(library) == 11, "nothing was taken"
        assert BIG_CREATURE in [game.state.objects[o].def_id for o in library[-4:]], (
            "it was looked at and buried, not skipped over"
        )

    def test_it_looks_at_four_cards_and_no_further(self, builder):
        """The fifth card is out of reach -- and is on top afterwards, because the
        four it *did* look at went to the bottom. A five-card look finds it."""
        game = self.dig(builder, [*[PLAINS] * 4, NOT_A_SOLDIER, *[PLAINS] * 6])
        library = game.state.players[0].library

        assert NOT_A_SOLDIER not in zone_ids(game, 0, "hand")
        assert game.state.objects[library[0]].def_id == NOT_A_SOLDIER

    def test_the_reveal_is_optional_and_declining_still_buries_the_four(self, builder):
        """ "You **may** reveal" -- the whiff and the decline cost the same four cards."""
        game = self.dig(builder, [NOT_A_SOLDIER, *[PLAINS] * 10], take=False)
        library = game.state.players[0].library

        assert NOT_A_SOLDIER not in zone_ids(game, 0, "hand")
        assert len(library) == 11, "nothing was drawn"
        assert NOT_A_SOLDIER in [game.state.objects[o].def_id for o in library[-4:]], (
            "it went to the bottom with the rest, not back on top"
        )


class TestEsgarothGarrison:
    """ "Esgaroth Garrison's power is equal to the number of creatures you control."
    / "When this creature enters, recruit. (Draw a card, then discard a card. If
    you discarded a nonland card, create a 1/1 white Human Soldier creature token.)"

    The gate recorded a library one smaller and a graveyard one bigger, which
    says the draw and the discard happened and nothing about the conditional
    behind them -- and it recorded no token, so whatever it discarded, the branch
    it took is the one that makes nothing. The power-setting static is invisible
    to it for the same reason every anthem here is: one creature on the board.
    """

    def board(self, builder, mine=()):
        return (
            builder(players=2)
            .battlefield(0, ["esgaroth_garrison", *mine, PLAINS])
            .battlefield(1, [BEAR, BEAR, PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )

    def test_its_power_counts_itself(self, builder):
        """A printed 0/5 alone on your side is a 1/5, not a 0/5."""
        game = self.board(builder)

        assert pt(game, only_oid(game, "esgaroth_garrison")) == (1, 5)

    def test_another_creature_you_control_raises_it(self, builder):
        """And the opponent's two Bears do not: "creatures **you** control"."""
        game = self.board(builder, mine=[NOT_A_SOLDIER])

        assert pt(game, only_oid(game, "esgaroth_garrison")) == (2, 5)

    def recruit(self, builder, top: str):
        """Cast the Garrison with exactly one card to draw and then discard.

        The hand holds the Garrison and nothing else, so the discard has exactly
        one legal answer and the branch under test is chosen by the *library*
        rather than by whatever a chooser happens to prefer.
        """
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS] * 5)
            .battlefield(1, [PLAINS])
            .hand(0, ["esgaroth_garrison"])
            .hand(1, [ANCHOR])
            .library(0, [top, *[PLAINS] * 10])
            .build()
        )
        cast(game, "esgaroth_garrison", yes=True)
        return game

    def test_a_nonland_discard_makes_a_soldier(self, builder):
        game = self.recruit(builder, NOT_A_SOLDIER)

        assert len(tokens(game, HUMAN_TOKEN)) == 1
        assert zone_ids(game, 0, "graveyard") == [NOT_A_SOLDIER], "drawn, then discarded"

    def test_a_land_discard_makes_nothing(self, builder):
        """ "If you discarded a **nonland** card" -- the near miss is no condition
        at all, and it is a strictly better card on every draw."""
        game = self.recruit(builder, PLAINS)

        assert tokens(game, HUMAN_TOKEN) == []
        assert zone_ids(game, 0, "graveyard") == [PLAINS], "the draw and discard still ran"


class TestCourtStreetDenizen:
    """ "Whenever another white creature you control enters, tap target creature an
    opponent controls."

    The gate cast the Denizen onto a board that then had nothing else enter, so
    its expectation records the opponent's six permanents untouched -- a
    statement that the card did not misfire. Every word in the trigger is a
    filter, and in a mono-white Soldier deck exactly one of them does real work:
    Myrel's tokens are **colorless**, so the deck's own widest turn must leave
    this card silent.

    The sentence above is the card's *current* oracle text and it is worth saying
    so, because the printed 2013 line was "you may tap target creature" -- neither
    mandatory nor restricted to an opponent's side. `data/catalog/cards.sqlite`
    carries the errata, the card file matches it, and a reader who remembers the
    old wording would read the tests below as two bugs.
    """

    def table(self, builder, *, entering: str, caster: int = 0):
        return (
            builder(players=2)
            .battlefield(0, ["court_street_denizen", *[PLAINS] * 5])
            .battlefield(1, [BEAR, *[PLAINS] * 5])
            .hand(0, [ANCHOR] if caster else [entering, ANCHOR])
            .hand(1, [entering, ANCHOR] if caster else [ANCHOR])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .max_turns(2)
            .build()
        )

    def test_a_white_creature_arriving_taps_a_creature_an_opponent_controls(self, builder):
        game = self.table(builder, entering=SOLDIER)
        bear = only_oid(game, BEAR, 1)
        assert not game.state.objects[bear].tapped

        cast(game, SOLDIER)

        assert game.state.objects[bear].tapped

    def test_a_colorless_soldier_token_does_not(self, builder):
        """Myrel attacks, two colorless Soldiers arrive, and nothing taps.

        This is the near miss that matters for this deck rather than a contrived
        one: a filter written on the *type* instead of the colour would fire
        twice here -- and again on every token Myrel, Decree of Justice and
        Memorial to Glory make for the rest of the game.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["court_street_denizen", "myrel_shield_of_argive", PLAINS])
            .battlefield(1, [BEAR, PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(0)
            .step(Step.UPKEEP)
            .max_turns(2)
            .build()
        )
        bear = only_oid(game, BEAR, 1)
        attack_with(game, [only_oid(game, "myrel_shield_of_argive")])
        settle_completely(game)

        assert len(tokens(game, COLORLESS_TOKEN)) == 2, "the premise: two arrived"
        assert not game.state.objects[bear].tapped

    def test_its_own_arrival_does_not_trigger_it(self, builder):
        """ "**another** white creature." The Denizen is itself a white creature."""
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS] * 5)
            .battlefield(1, [BEAR, PLAINS])
            .hand(0, ["court_street_denizen", ANCHOR])
            .hand(1, [ANCHOR])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .max_turns(2)
            .build()
        )
        bear = only_oid(game, BEAR, 1)
        cast(game, "court_street_denizen")

        assert oids_of(game, "court_street_denizen", 0), "the premise: it did arrive"
        assert not game.state.objects[bear].tapped

    def test_an_opponents_white_creature_does_not(self, builder):
        """ "…**you control**", and the near miss is a Denizen that taps a creature
        every time the player it is pointed at develops their own board."""
        game = self.table(builder, entering=SOLDIER, caster=1)
        bear = only_oid(game, BEAR, 1)

        cast(game, SOLDIER, pid=1)

        assert oids_of(game, SOLDIER, 1), "the premise: it arrived on their side"
        assert not game.state.objects[bear].tapped


class TestMemorialToGlory:
    """ "This land enters tapped." / "{T}: Add {W}." / "{3}{W}, {T}, Sacrifice this
    land: Create two 1/1 white Soldier creature tokens."

    A land, so the gate put it on the battlefield and counted permanents; it
    never activated either ability, and no expectation key records whether a land
    arrived tapped. The three lines interlock: the sacrifice needs the land
    untapped, and the land arrives tapped, so the turn it is played it is a
    Plains and nothing else.
    """

    def test_it_enters_tapped(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS])
            .battlefield(1, [PLAINS])
            .hand(0, ["memorial_to_glory"])
            .hand(1, [ANCHOR])
            .build()
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.PLAY_LAND
                and game.state.objects[a.source].def_id == "memorial_to_glory"
            )
        )
        settle_completely(game)
        memorial = only_oid(game, "memorial_to_glory")

        assert game.state.objects[memorial].tapped

    def test_and_so_the_sacrifice_is_out_of_reach_the_turn_it_arrives(self, builder):
        """ "{T}" is in the cost, and a land that entered tapped cannot pay it."""
        game = (
            builder(players=2)
            .battlefield(0, ["memorial_to_glory"], tapped=True)
            .battlefield(0, [PLAINS] * 4)
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )

        assert activations(game, only_oid(game, "memorial_to_glory")) == []

    def test_the_sacrifice_makes_two_soldiers_and_takes_the_land(self, builder):
        """Two, not one and not X -- and the land goes, which is what the price is."""
        game = (
            builder(players=2)
            .battlefield(0, ["memorial_to_glory", *[PLAINS] * 4])
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )
        memorial = only_oid(game, "memorial_to_glory")
        actions = activations(game, memorial)
        assert len(actions) == 1, "the mana ability is the solver's, not the action list's"
        game.apply(actions[0])
        settle_completely(game)

        assert len(tokens(game, WHITE_TOKEN)) == 2
        assert game.state.objects[memorial].zone is Zone.GRAVEYARD

    def test_the_mana_ability_pays_for_a_white_spell(self, builder):
        """ "{T}: Add {W}." Never in the action list -- mana payment is automatic
        for an AI seat, so a tap-only mana ability is the solver's. The only way
        to see it is to ask whether it bought something."""
        game = (
            builder(players=2)
            .battlefield(0, ["memorial_to_glory"])
            .hand(0, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

        assert ANCHOR in offers(game, 0, ActionKind.CAST)

    def test_and_tapped_it_does_not(self, builder):
        """The control, and the other half of "enters tapped" mattering."""
        game = (
            builder(players=2)
            .battlefield(0, ["memorial_to_glory"], tapped=True)
            .hand(0, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

        assert ANCHOR not in offers(game, 0, ActionKind.CAST)


class TestKeeperOfTheAccord:
    """ "At the beginning of each opponent's end step, if that player controls more
    creatures than you, create a 1/1 white Soldier creature token." / "…if that
    player controls more lands than you, you may search your library for a basic
    Plains card, put it onto the battlefield tapped, then shuffle."

    Two triggers on a step the authoring sandbox never reaches, so the recorded
    expectation was `battlefield_count: 33`. Both carry the same two questions,
    and each has a wrong answer that looks right on an ordinary board: **more
    than**, not as many as, and **that player** -- the one whose end step it is --
    not the table, and not whoever is furthest ahead.
    """

    def table(
        self,
        builder,
        *,
        mine=(),
        theirs=(),
        my_lands: int = 3,
        their_lands: int = 3,
        players: int = 2,
        ender: int = 1,
        third=(),
    ):
        """``ender``'s postcombat main, stepping forward into their end step.

        `max_turns` and a hand for every seat, because the trigger is read at a
        *step boundary*: with no play available anywhere the engine's auto-pass
        runs six turns inside one `apply`, and a test that then looked for a
        token would find one three opponents' end steps later and call it a pass.
        """
        b = (
            builder(players=players)
            .battlefield(0, ["keeper_of_the_accord", *mine, *[PLAINS] * my_lands])
            .battlefield(1, [*theirs, *[PLAINS] * their_lands])
            .library(0, [NONBASIC_PLAINS, PLAINS, PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(ender)
            .step(Step.POSTCOMBAT_MAIN)
            .max_turns(6)
        )
        if players > 2:
            b = b.battlefield(2, [*third, PLAINS]).hand(2, [ANCHOR])
        game = b.build()
        pass_until(
            game,
            lambda g: g.state.step is Step.END_STEP and g.state.active_player == ender,
        )
        answer(game, yes=True, pick=True)
        return game

    # -- the creature half -------------------------------------------------

    def test_more_creatures_makes_you_a_soldier(self, builder):
        """Two Bears against one Keeper."""
        game = self.table(builder, theirs=[BEAR, BEAR])

        assert len(tokens(game, WHITE_TOKEN)) == 1

    def test_an_equal_count_makes_nothing(self, builder):
        """ "**more** creatures than you". Two each: the off-by-one that would make
        this card draw a Soldier out of a mirror."""
        game = self.table(builder, mine=[NOT_A_SOLDIER], theirs=[BEAR])

        assert tokens(game, WHITE_TOKEN) == []

    def test_it_reads_the_player_whose_end_step_it_is(self, builder):
        """Three seats: the one ending their turn is level with you, and the third
        is five creatures ahead.

        The near miss counts the board rather than `event_player` -- "an opponent
        controls more creatures than you" -- and in a four-player game that is a
        token at the end of every single turn.
        """
        game = self.table(
            builder,
            players=3,
            mine=[NOT_A_SOLDIER],
            theirs=[BEAR],
            third=[BEAR] * 5,
        )

        assert tokens(game, WHITE_TOKEN) == []

    def test_nothing_happens_at_your_own_end_step(self, builder):
        """ "each **opponent's** end step", with both conditions met to prove it."""
        game = self.table(builder, theirs=[BEAR, BEAR], my_lands=1, their_lands=4, ender=0)

        assert tokens(game, WHITE_TOKEN) == []
        assert len(oids_of(game, PLAINS, 0)) == 1, "and no land was fetched either"

    # -- the land half -----------------------------------------------------

    def test_more_lands_fetches_a_basic_plains_tapped(self, builder):
        """One land against four. Tapped is the whole restraint on the card."""
        game = self.table(builder, my_lands=1, their_lands=4)
        mine = [game.state.objects[o] for o in oids_of(game, PLAINS, 0)]

        assert len(mine) == 2, "the one it started with, plus the fetch"
        assert [o.tapped for o in mine].count(True) == 1

    def test_the_search_leaves_a_nonbasic_plains_where_it_is(self, builder):
        """ "a **basic** Plains card."

        Idyllic Grange is the live near miss and it is in this very deck: a
        `Land — Plains` with no `Basic` on it. A subtype-only filter fetches it,
        which is an untapped-condition land arriving tapped for free, and a
        supertype-only filter fetches a Mountain out of a deck that had one.
        """
        game = self.table(builder, my_lands=1, their_lands=4)

        assert zone_ids(game, 0, "library").count(NONBASIC_PLAINS) == 1
        assert len(game.state.players[0].library) == 2, "one basic left the library"

    def test_an_equal_land_count_fetches_nothing(self, builder):
        """ "**more** lands than you". Four each."""
        game = self.table(builder, my_lands=4, their_lands=4)

        assert len(oids_of(game, PLAINS, 0)) == 4
        assert len(game.state.players[0].library) == 3
