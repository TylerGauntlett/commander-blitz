""""Whenever an opponent activates an ability…, if it isn't a mana ability."

Harsh Mentor is the shipped witness, and it is the whole of the card: a 2/2 for
{1}{R} whose only printed line is this trigger. Rule 602.1 makes activating an
ability a distinct action from casting a spell, and rule 605 carves the mana
abilities out of it -- so the card needs both halves, and neither existed.

`EventType.ABILITY_ACTIVATED` was already defined and already emitted by both
activation paths in `game.py`. What it never had was a *listener*: both sites
called `state.emit`, whose docstring says it only records and leaves the trigger
bus to the caller, and no name in `TRIGGER_EVENTS` mapped to it -- so no card
could have subscribed even if something had fired. It was a log line. `fire`
rather than `emit` is the same one-word fix the cycling trigger next door
documents, and the same silent no-op it was fixed for.

The near misses are wrong rather than merely absent:

- `spell_cast` is the tempting one -- also "an opponent did a thing that used
  the stack", also supporting `controller: "opponent"` -- but it fires on a card
  going from hand to stack, which is a *disjoint* set of actions. A Harsh Mentor
  built on it would punish every instant and never punish an equip, a fetchland
  or a Signet.
- `becomes_target` fires on the object being pointed at, so it sees nothing when
  an ability has no targets (cracking a Signet, sacrificing a Panorama) and
  misfires on every targeted spell.

The second half is "if it isn't a mana ability", and it is not an intervening-if
the engine could already ask. Every `condition` key asks about the board or
about the trigger's own card; `TriggerSpec.filter` reads the *source permanent's*
printed face. Neither can reach *which ability was used* -- and the permanents
this clause exists for are exactly the ones carrying both kinds. Bant Panorama
taps for {C} and sacrifices itself to fetch; an Azorius Signet taps for {W}{U}.
Same card types, opposite answers. So the flag rides on the event, both
activation paths set it, and `TriggerSpec.mana_ability` compares against it.

Dropping the clause does not approximate the card, it replaces it: every land in
a real game taps many times a turn, and a Harsh Mentor without the exclusion is a
Manabarbs.

The authoring verifier never activates anything -- it casts a card and stops --
so this trigger cannot fire in the fixed sandbox and Harsh Mentor's expectation
is `{"zone": "battlefield"}`. This file is where the behaviour is proved.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError
from tests.conftest import event_types, only_oid, settle

MENTOR = "harsh_mentor"

#: A Land that taps for {C} *and* sacrifices itself to fetch: the "same object,
#: opposite answers" case the filter provably cannot decide.
PANORAMA = "bant_panorama"
#: `{1}, {T}: Add {W}{U}` -- a mana ability with a cost the payment solver cannot
#: use, so it is offered to the player and reaches `Game._activate_mana`. Every
#: plain `{T}: Add {G}` land is tapped by the solver instead and never reaches an
#: activation path at all.
SIGNET = "azorius_signet"
#: `{G}: This creature gets +1/+1` -- an activated ability with no targets and no
#: decisions, so the assertion is about the trigger rather than about a prompt.
MUTATOR = "t_mutator"
#: An Enchantment's activated ability: the type filter's negative.
SAC_OUTLET = "t_sac_outlet"
#: Cycling, which is an activated ability of a *Land card in a hand*. "on the
#: battlefield" is the clause that must refuse it.
CYCLING_LAND = "barren_moor"


#: Lands enough to pay for anything activated below.
LANDS = ["forest", "island", "island", "swamp"]


def position(builder, *, theirs=(), hand=(), players=2, them=1):
    """Harsh Mentor under player 0; ``them`` is the active player who acts.

    ``them`` is made the active player so the position opens on their priority.
    That only holds if they have something worth deciding: the engine auto-passes
    a player whose board offers nothing, and a board whose *only* offer is a mana
    ability is such a board -- which is why the mana tests put an anchor on it.
    """
    game = builder(players=players)
    board = [*theirs, *LANDS]
    if them == 0:
        game = game.battlefield(0, [MENTOR, *board])
    else:
        game = game.battlefield(0, [MENTOR])
        game = game.battlefield(them, board)
    if hand:
        game = game.hand(them, list(hand))
    return game.active(them).max_turns(4).build()


def activate(game, card_id, *, pid=None, ability_index=None):
    """Activate one ability of ``card_id`` and let everything resolve."""
    oid = only_oid(game, card_id, pid)
    offered = [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE
        and a.source == oid
        and (ability_index is None or a.ability_index == ability_index)
    ]
    assert offered, (
        f"no activation offered for {card_id}; "
        f"legal: {[a.label or a.kind.value for a in game.legal_actions()]}"
    )
    game.apply(offered[0])
    settle(game)
    return oid


def life(game, pid: int) -> int:
    return game.state.players[pid].life


class TestTheEventReachesTheBus:
    """`fire`, not `emit` -- the whole of the first half."""

    def test_an_opponents_activation_deals_2_to_them(self, builder):
        game = position(builder, theirs=[MUTATOR])
        activate(game, MUTATOR)
        assert life(game, 1) == 38

    def test_the_trigger_actually_queued(self, builder):
        """The event is the same one `emit` always wrote; the difference is that
        something heard it. `ability_triggered` is only emitted by
        `triggers._queue`, so its presence is the proof."""
        game = position(builder, theirs=[MUTATOR])
        mark = len(game.state.events)
        activate(game, MUTATOR)
        kinds = event_types(game.state.events[mark:])
        assert "ability_activated" in kinds
        assert "ability_triggered" in kinds

    def test_the_mentor_is_the_source_of_the_damage(self, builder):
        game = position(builder, theirs=[MUTATOR])
        mentor = only_oid(game, MENTOR)
        mark = len(game.state.events)
        activate(game, MUTATOR)
        damage = [e for e in game.state.events[mark:] if e.type == "damage_dealt"]
        assert damage and damage[0].source == mentor, (
            "'this creature deals 2 damage' -- the Mentor, not the ability"
        )

    def test_a_lands_activated_ability_counts(self, builder):
        """Cracking a fetchland is the printed example, and it is why
        `spell_cast` could never stand in: nothing is cast."""
        game = position(builder, theirs=[PANORAMA])
        activate(game, PANORAMA)
        assert life(game, 1) == 38


class TestManaAbilitiesAreExcluded:
    """"…if it isn't a mana ability." Without it this is Manabarbs."""

    def test_a_mana_ability_activated_by_hand_does_not_trigger(self, builder):
        game = position(builder, theirs=[SIGNET, MUTATOR])
        activate(game, SIGNET)
        assert life(game, 1) == 40

    def test_and_the_event_still_fired(self, builder):
        """The exclusion is the *spec's* doing, not the event's absence.

        If `_activate_mana` had gone on emitting instead of firing, this test
        would pass for the wrong reason and `mana_ability: false` would be a
        guard that never runs -- so the event has to be in the log with the
        trigger absent."""
        game = position(builder, theirs=[SIGNET, MUTATOR])
        mark = len(game.state.events)
        activate(game, SIGNET)
        kinds = event_types(game.state.events[mark:])
        assert "ability_activated" in kinds, "the mana path fires the event"
        assert "ability_triggered" not in kinds, "and the spec drops it"

    def test_the_types_filter_could_not_have_told_them_apart(self, builder):
        """An Artifact and a Land are both in "an artifact, creature, or land",
        and one of them is a Signet. The printed characteristics the filter can
        read are identical in kind; only the flag separates them."""
        game = position(builder, theirs=[SIGNET, PANORAMA])
        activate(game, SIGNET)
        assert life(game, 1) == 40, "the Signet's mana ability is exempt"
        activate(game, PANORAMA)
        assert life(game, 1) == 38, "the Panorama's sacrifice ability is not"


class TestWhoseActivationItWas:
    def test_your_own_activation_does_not_trigger_your_mentor(self, builder):
        """`controller: "opponent"` is read off the *activating player*, which
        for this event is not the subject's controller."""
        game = position(builder, theirs=[MUTATOR], them=0)
        activate(game, MUTATOR, pid=0)
        assert life(game, 0) == 40

    def test_the_damage_follows_the_activating_player_in_a_pod(self, builder):
        """"that player", via `{"binding": "event_player"}` -- not "each
        opponent", which in a four-player game is a different card."""
        game = position(builder, theirs=[MUTATOR], players=4, them=2)
        activate(game, MUTATOR, pid=2)
        assert life(game, 2) == 38
        assert [life(game, p) for p in (0, 1, 3)] == [40, 40, 40]


class TestTheFilter:
    def test_an_enchantments_ability_is_not_one_of_the_three_types(self, builder):
        """`any_types`, not `types`: ["Artifact", "Creature", "Land"] read as a
        conjunction would be a permanent that is all three, which is nothing."""
        game = position(builder, theirs=[SAC_OUTLET, MUTATOR])
        mark = len(game.state.events)
        activate(game, SAC_OUTLET)
        assert "ability_triggered" not in event_types(game.state.events[mark:])
        assert life(game, 1) == 41, "its own 1 life, and no 2 damage on top"

    def test_cycling_a_land_from_hand_is_not_on_the_battlefield(self, builder):
        """The `zone` half. A cycled card is a Land card whose activated ability
        was used from a hand, so every characteristic the filter reads says yes
        and only the zone says no."""
        game = position(builder, hand=[CYCLING_LAND])
        offered = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE
            and game.state.objects[a.source].def_id == CYCLING_LAND
        ]
        assert offered, (
            "the fixture should be able to cycle; "
            f"legal: {[a.label or a.kind.value for a in game.legal_actions()]}"
        )
        mark = len(game.state.events)
        game.apply(offered[0])
        settle(game)
        assert "ability_activated" in event_types(game.state.events[mark:])
        assert life(game, 1) == 40


def probe(**trigger) -> dict:
    spec = {"event": "ability_activated", "controller": "opponent"}
    spec.update(trigger)
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "Whenever an opponent activates an ability, ...",
        "mana_cost": "{1}{R}",
        "types": ["Creature"],
        "power": 2,
        "toughness": 2,
        "abilities": [
            {
                "kind": "triggered",
                "text": "Whenever an opponent activates an ability, ...",
                "trigger": spec,
                "effects": [
                    {
                        "op": "damage",
                        "player": {"binding": "event_player"},
                        "amount": {"const": 2},
                    }
                ],
            }
        ],
    }


class TestTheLoader:
    def test_the_event_is_known(self):
        card = compile_card(CardModel.model_validate(probe(mana_ability=False)))
        assert card.abilities[0].trigger.mana_ability is False

    def test_omitting_the_flag_means_every_activation(self):
        card = compile_card(CardModel.model_validate(probe()))
        assert card.abilities[0].trigger.mana_ability is None

    def test_the_flag_is_refused_on_any_other_event(self):
        """Same reasoning as `counter` and `defending`: a restriction that can
        never apply looks like the printed clause and is not it."""
        payload = probe()
        payload["abilities"][0]["trigger"] = {
            "event": "spell_cast",
            "controller": "opponent",
            "mana_ability": False,
        }
        with pytest.raises(DslError, match="mana_ability"):
            compile_card(CardModel.model_validate(payload))
