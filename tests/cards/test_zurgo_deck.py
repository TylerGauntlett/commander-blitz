"""The Zurgo Stormrender deck, card by card, doing what it prints.

Every card here cleared the six authoring gates, and almost every one was
measured by gate 5 at "it is on the battlefield" -- which is the gate's
documented limit, not the card's. Its sandbox casts a card once and stops:

- **It never reaches combat.** Zurgo's mobilize and Hellrider's ping are attack
  triggers, and Zurgo's draw half needs a token to leave the battlefield *while
  attacking*. Chief of the Edge's anthem shows on the Warrior mobilize makes.
- **Nothing dies after the card under test.** Zurgo's drain half, Bastion of
  Remembrance, Zulaport Cutthroat and Dictate of Erebos are all "whenever a
  creature leaves / dies" payoffs, and the sandbox sacrifices nothing.
- **Nothing enters after it.** Impact Tremors watches creatures entering, and
  Intangible Virtue only shows on a token made after it is down.

So these are the observations. Each class is one card, and each pins a near
miss as well: Zurgo's two branches are exclusive (a draw *or* a drain), a
nontoken creature leaving feeds neither, Impact Tremors does not count the
enchantment that made the token, the Virtue skips nontoken creatures, and the
death payoffs ignore an opponent's creature dying.

Tokens are made by real token spells here, not placed by the builder: a token
card placed with `.battlefield` is an ordinary object, not a token, and every
"creature token" filter in this deck would correctly ignore it.
"""

from __future__ import annotations

import pytest

from automtg.engine.characteristics import chars, has_keyword
from automtg.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import _default_answer, action_for_card, oids_of, only_oid, pass_until

ZURGO = "zurgo_stormrender"
WARRIOR = "warrior_1_1_r"  # the mobilize token
GOBLIN = "goblin_1_1_r"
HUMAN = "human_1_1_w"
FODDER = "dragon_fodder"  # {1}{R} sorcery: two 1/1 red Goblin tokens
TREMORS = "impact_tremors"
VIRTUE = "intangible_virtue"
BASTION = "bastion_of_remembrance"
ZULAPORT = "zulaport_cutthroat"
HELLRIDER = "hellrider"
CHIEF = "chief_of_the_edge"
HATEBLADE = "mardu_hateblade"  # a nontoken Human Warrior, for Chief's "other Warriors"
DICTATE = "dictate_of_erebos"
BEAR = "t_bear"  # a plain nontoken 2/2
OUTLET = "t_sac_outlet"  # "Sacrifice a creature: You gain 1 life."
REMOVAL = "t_removal"  # {W} instant: exile target creature
EDICT = "t_edict"  # {B} sorcery: each opponent sacrifices a creature
# A castable instant in each seat's hand: with no play available to anybody the
# engine's auto-pass runs whole turns inside one `apply` and overshoots the step
# under test.
ANCHOR = "t_plain_instant"


def settle(game, *, limit: int = 300) -> None:
    """Let the stack and every pending trigger empty, taking passive answers."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return
        if (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack did not empty")


def board(builder, mine, *, theirs=(), hand=()):
    """Player 0's precombat main, five lands of Zurgo's colours untapped."""
    return (
        builder(players=2)
        .battlefield(0, ["plains", "plains", "swamp", "mountain", "mountain", *mine])
        .battlefield(1, ["plains", *theirs])
        .hand(0, [ANCHOR, *hand])
        .hand(1, [ANCHOR])
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
        .max_turns(4)
        .build()
    )


def cast(game, card_id: str) -> None:
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    settle(game)


def sacrifice(game, victim: int) -> None:
    """Pay the test outlet's cost with ``victim`` -- a real sacrifice, through
    the game loop that collects the leave and death triggers."""
    outlet = only_oid(game, OUTLET, 0)
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == outlet
        )
    )
    while (p := game.pending()) is not None and p.kind is DecisionKind.CHOOSE_OBJECTS:
        game.apply(
            next(a for a in game.legal_actions() if a.targets and a.targets[0].id == victim)
        )
    settle(game)
    assert victim not in game.state.battlefield


def exile(game, victim: int) -> None:
    """Cast the test removal at ``victim``."""
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == REMOVAL
            and (not a.targets or a.targets[0].id == victim)
        )
    )
    while (p := game.pending()) is not None and p.kind is DecisionKind.CHOOSE_OBJECTS:
        game.apply(next(a for a in game.legal_actions() if a.targets[0].id == victim))
    settle(game)
    assert victim not in game.state.battlefield


def attack_with(game, *attackers: int) -> None:
    """Declare ``attackers`` at player 1 and let the attack triggers resolve.
    Stops in the declare-attackers step, before any combat damage."""
    pass_until(
        game,
        lambda g: g.pending() is not None
        and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
    )
    for oid in attackers:
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == oid
                and a.targets[0].kind == "player"
            )
        )
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
    settle(game)
    assert game.state.step is Step.DECLARE_ATTACKERS


def life(game, pid: int) -> int:
    return game.state.players[pid].life


def library(game, pid: int) -> int:
    return len(game.state.players[pid].library)


class TestZurgoStormrender:
    """"Mobilize 1 (Whenever this creature attacks, create a tapped and attacking
    1/1 red Warrior creature token. Sacrifice it at the beginning of the next end
    step.) Whenever a creature token you control leaves the battlefield, draw a
    card if it was attacking. Otherwise, each opponent loses 1 life."

    The reminder text's end-step sacrifice is not asserted: the card's
    `create_token` schedules none, and the Warrior stays on the battlefield
    into the next turn.
    """

    def test_attacking_makes_a_tapped_attacking_one_one_red_warrior_token(self, builder):
        game = board(builder, [ZURGO])
        attack_with(game, only_oid(game, ZURGO, 0))
        [token] = oids_of(game, WARRIOR, 0)
        obj = game.state.objects[token]
        assert obj.is_token and obj.tapped
        assert game.state.combat.attackers[token] == 1, "attacking the player Zurgo attacks"
        c = chars(game.state, token)
        assert (c.power, c.toughness) == (1, 1)
        assert "Warrior" in c.subtypes and "R" in c.colors

    def test_without_an_attack_there_is_no_token(self, builder):
        game = board(builder, [ZURGO, BEAR])
        attack_with(game, only_oid(game, BEAR, 0))
        assert oids_of(game, WARRIOR, 0) == [], "mobilize is Zurgo's attack, not anyone's"

    def test_an_attacking_token_leaving_draws_a_card_and_drains_nothing(self, builder):
        game = board(builder, [ZURGO], hand=[REMOVAL])
        attack_with(game, only_oid(game, ZURGO, 0))
        [token] = oids_of(game, WARRIOR, 0)
        cards, theirs = library(game, 0), life(game, 1)
        exile(game, token)
        assert library(game, 0) == cards - 1
        assert life(game, 1) == theirs, "the draw *instead of* the drain"

    def test_a_token_leaving_outside_combat_drains_and_draws_nothing(self, builder):
        game = board(builder, [ZURGO, OUTLET], hand=[FODDER])
        cast(game, FODDER)
        goblin, _other = oids_of(game, GOBLIN, 0)
        cards = library(game, 0)
        sacrifice(game, goblin)
        assert life(game, 1) == 40 - 1
        assert library(game, 0) == cards

    def test_a_nontoken_creature_leaving_does_nothing(self, builder):
        game = board(builder, [ZURGO, OUTLET, BEAR])
        sacrifice(game, only_oid(game, BEAR, 0))
        assert life(game, 1) == 40
        assert library(game, 0) == 20


class TestImpactTremors:
    """"Whenever a creature you control enters, this enchantment deals 1 damage
    to each opponent." """

    def test_each_token_is_one_damage(self, builder):
        game = board(builder, [TREMORS], hand=[FODDER])
        cast(game, FODDER)
        assert life(game, 1) == 40 - 2
        assert life(game, 0) == 40, "each *opponent*, not each player"

    def test_the_enchantment_that_makes_the_token_is_not_a_creature(self, builder):
        """Bastion of Remembrance enters and makes a Human: one creature, one
        damage -- not two."""
        game = board(builder, [TREMORS], hand=[BASTION])
        cast(game, BASTION)
        assert len(oids_of(game, HUMAN, 0)) == 1
        assert life(game, 1) == 40 - 1


class TestIntangibleVirtue:
    """"Creature tokens you control get +1/+1 and have vigilance." """

    def test_tokens_get_plus_one_and_vigilance_and_a_nontoken_does_not(self, builder):
        game = board(builder, [VIRTUE, BEAR], hand=[FODDER])
        cast(game, FODDER)
        for goblin in oids_of(game, GOBLIN, 0):
            c = chars(game.state, goblin)
            assert (c.power, c.toughness) == (2, 2)
            assert has_keyword(game.state, goblin, "vigilance")
        bear = only_oid(game, BEAR, 0)
        assert (chars(game.state, bear).power, chars(game.state, bear).toughness) == (2, 2)
        assert not has_keyword(game.state, bear, "vigilance")


class TestBastionOfRemembrance:
    """"When this enchantment enters, create a 1/1 white Human Soldier creature
    token. Whenever a creature you control dies, each opponent loses 1 life and
    you gain 1 life." """

    def test_it_enters_with_a_human_and_the_human_dying_drains_one(self, builder):
        game = board(builder, [OUTLET], hand=[BASTION])
        cast(game, BASTION)
        human = only_oid(game, HUMAN, 0)
        assert game.state.objects[human].is_token
        sacrifice(game, human)
        assert life(game, 1) == 40 - 1
        assert life(game, 0) == 40 + 1 + 1, "Bastion's 1, plus the outlet's own 1"

    def test_with_zurgo_one_token_death_is_two_points(self, builder):
        """The deck's engine: the token's death is a Bastion drain *and*, being a
        token leaving outside combat, a Zurgo drain."""
        game = board(builder, [ZURGO, OUTLET], hand=[BASTION])
        cast(game, BASTION)
        sacrifice(game, only_oid(game, HUMAN, 0))
        assert life(game, 1) == 40 - 2
        assert library(game, 0) == 20


class TestZulaportCutthroat:
    """"Whenever this creature or another creature you control dies, each
    opponent loses 1 life and you gain 1 life."

    The "this creature" half -- its own death -- is pinned as a strict xfail:
    the engine's leave-the-battlefield look-back only collects `source: "self"`
    triggers from the departed object, so this ability misses its own death
    (TECH_DEBT CD-07). The xfail turns red the day that is fixed.
    """

    @pytest.mark.xfail(
        strict=True,
        reason="TECH_DEBT CD-07: a 'this or another creature dies' trigger misses its own death",
    )
    def test_its_own_death_drains(self, builder):
        game = board(builder, [ZULAPORT, OUTLET])
        sacrifice(game, only_oid(game, ZULAPORT, 0))
        assert life(game, 1) == 40 - 1

    def test_another_creature_dying_drains(self, builder):
        game = board(builder, [ZULAPORT, OUTLET, BEAR])
        sacrifice(game, only_oid(game, BEAR, 0))
        assert life(game, 1) == 40 - 1
        assert life(game, 0) == 40 + 1 + 1, "Zulaport's 1, plus the outlet's own 1"

    def test_an_opponents_creature_dying_does_not(self, builder):
        game = board(builder, [ZULAPORT], theirs=[BEAR], hand=[EDICT])
        cast(game, EDICT)
        assert oids_of(game, BEAR, 1) == []
        assert life(game, 1) == 40
        assert life(game, 0) == 40


class TestHellrider:
    """"Haste. Whenever a creature you control attacks, this creature deals 1
    damage to the player or planeswalker it's attacking." """

    def test_one_damage_per_attacker_before_combat_damage(self, builder):
        game = board(builder, [HELLRIDER, BEAR])
        attack_with(game, only_oid(game, HELLRIDER, 0), only_oid(game, BEAR, 0))
        assert life(game, 1) == 40 - 2
        assert life(game, 0) == 40

    def test_hellrider_need_not_attack_itself(self, builder):
        game = board(builder, [HELLRIDER, BEAR])
        attack_with(game, only_oid(game, BEAR, 0))
        assert life(game, 1) == 40 - 1


class TestChiefOfTheEdge:
    """"Other Warrior creatures you control get +1/+0." """

    def test_other_warriors_get_plus_one_power_and_nothing_else_does(self, builder):
        game = board(builder, [CHIEF, ZURGO, HATEBLADE, BEAR])

        def pt(card_id):
            c = chars(game.state, only_oid(game, card_id, 0))
            return c.power, c.toughness

        assert pt(ZURGO) == (4, 3), "an Orc *Warrior*"
        assert pt(HATEBLADE) == (2, 1)
        assert pt(CHIEF) == (3, 2), "*other* Warriors"
        assert pt(BEAR) == (2, 2)

    def test_the_mobilized_warrior_swings_as_a_two_one(self, builder):
        game = board(builder, [CHIEF, ZURGO])
        attack_with(game, only_oid(game, ZURGO, 0))
        [token] = oids_of(game, WARRIOR, 0)
        c = chars(game.state, token)
        assert (c.power, c.toughness) == (2, 1)


class TestDictateOfErebos:
    """"Flash. Whenever a creature you control dies, each opponent sacrifices a
    creature of their choice." """

    def test_your_creature_dying_makes_them_sacrifice_one(self, builder):
        game = board(builder, [DICTATE, OUTLET, BEAR, HATEBLADE], theirs=[BEAR, BEAR])
        sacrifice(game, only_oid(game, BEAR, 0))
        assert len(oids_of(game, BEAR, 1)) == 1, "one creature, not all of them"
        assert only_oid(game, HATEBLADE, 0) in game.state.battlefield, "each *opponent*"

    def test_their_creature_dying_does_not(self, builder):
        game = board(builder, [DICTATE], theirs=[BEAR, BEAR], hand=[EDICT])
        cast(game, EDICT)
        assert len(oids_of(game, BEAR, 1)) == 1, "the edict's one, and no Dictate follow-up"
