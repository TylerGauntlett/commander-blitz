""""Whenever **your commander** enters or attacks" -- `owner` in a trigger filter,
and the trigger-filter key list that stops a key loading and being ignored.

    Tome of Legends — "This artifact enters with a page counter on it.
    Whenever your commander enters or attacks, put a page counter on this
    artifact. {1}, {T}, Remove a page counter from this artifact: Draw a card."

Rule 903.3: "your commander" is the commander you **own**, wherever it is and
whoever controls it. `gain_control` is implemented, so that is a genuinely
different set from "a commander you control" -- Norn's Choirmaster's shape,
trigger filter `{is_commander: true, controller: "you"}`. That reading misses
your own commander attacking for the opponent who stole it, and fires on the
opponent's commander while you hold it.

`owner` was already a legal selector key -- `selectors.matches` and the static
filter both read it -- and a trigger filter is validated against the same
`SELECTOR_KEYS`. But `triggers.matches_card_filter` never read it, so
`{is_commander: true, owner: "you"}` loaded clean and fired on **every**
commander at the table: strictly wider than printed, and invisible to every
gate. The intervening-if workaround is a different card too: 603.4 re-checks it
on resolution, so moving the commander in response would cancel a counter the
printed card (which has no "if") still gives.

`owner` is the fourth key found that way (`zone`, `tapped`, `not_supertypes`
were the others). So the loader now validates a trigger filter against
`TRIGGER_FILTER_KEYS` -- exactly what `matches_card_filter` reads -- and the
last class below holds the two in step.

What is pinned below, and each is a way this could be silently wrong:

1. Your commander entering or attacking adds a counter -- the card.
2. Your commander under an opponent's control still counts, attacking and
   entering alike.
3. An opponent's commander you have stolen does not, nor does theirs entering,
   nor a creature of yours that is not a commander.
4. The `controller: "you"` near miss reads both stolen boards the other way.
5. `owner: "opponent"` is the complement and `"any"` filters nobody.
6. The loader refuses a selector key the trigger matcher does not read, and a
   player word it cannot answer -- in a trigger filter and a `cause_filter`.
7. `TRIGGER_FILTER_KEYS` and the matcher do not drift apart.
"""

from __future__ import annotations

import inspect
import re

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import triggers
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import change_control
from commanderblitz.engine.triggers import TRIGGER_FILTER_KEYS, matches_card_filter
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, only_oid, settle

KEEPER = "t_page_keeper"  # Tome of Legends' two triggers, by ownership
BY_CONTROL = "t_page_keeper_by_control"  # the near miss, by control
COMMANDER = "t_commander_five"
BEAR = "t_bear"


def pages(game, oid: int) -> int:
    return game.state.objects[oid].counters.get("page", 0)


def make_commander(game, oid: int, owner: int) -> None:
    game.state.objects[oid].is_commander = True
    game.state.players[owner].commanders.append(oid)


def attack_board(builder, *, mine: bool, attacker: int, keepers=(KEEPER,)):
    """A commander standing on the battlefield, about to attack for ``attacker``.

    Player 0 holds the keeper(s). ``mine`` says whose commander it is -- player
    0's or player 1's -- and if its owner is not ``attacker`` it has been
    stolen first, long enough ago that it can attack.
    """
    owner = 0 if mine else 1
    game = (
        builder(players=2)
        .battlefield(0, list(keepers))
        .battlefield(owner, [COMMANDER])
        .library(0, ["swamp"] * 20)
        .library(1, ["swamp"] * 20)
        .active(attacker)
        .step(Step.UNTAP)
        .max_turns(3)
        .build(advance=False)
    )
    commander = only_oid(game, COMMANDER)
    make_commander(game, commander, owner)
    if owner != attacker:
        change_control(game.state, commander, attacker)
        game.state.objects[commander].entered_turn = game.state.turn - 1
    game._advance()
    return game, commander


def swing(game, commander: int) -> None:
    for _ in range(80):
        decision = game.pending()
        if decision is not None and decision.kind is DecisionKind.DECLARE_ATTACKERS:
            break
        assert decision is not None, "never reached declare attackers"
        game.apply(_default_answer(game, decision))
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_ATTACKER and a.source == commander
        )
    )
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
    settle(game)


def enter_board(builder, *, owner: int, card: str = COMMANDER, commander: bool = True):
    """Player 0 holds the keeper; ``card`` waits in its owner's command zone."""
    b = builder(players=2).battlefield(0, [KEEPER])
    b = b.commander(owner, [card]) if commander else b.hand(owner, [card])
    game = b.library(0, ["swamp"] * 20).library(1, ["swamp"] * 20).build()
    waiting = next(o.oid for o in game.state.objects.values() if o.def_id == card)
    return game, only_oid(game, KEEPER), waiting


class TestYourCommanderAddsAPage:
    def test_your_commander_entering_adds_one(self, builder):
        game, keeper, commander = enter_board(builder, owner=0)
        move_object(game.state, commander, Zone.BATTLEFIELD)
        settle(game)
        assert pages(game, keeper) == 1

    def test_your_commander_attacking_adds_one(self, builder):
        game, commander = attack_board(builder, mine=True, attacker=0)
        keeper = only_oid(game, KEEPER)
        swing(game, commander)
        assert pages(game, keeper) == 1


class TestOwnershipNotControl:
    def test_your_commander_attacking_for_an_opponent_still_adds_one(self, builder):
        """The card's near miss. Stolen, it is still yours (903.3), and it is
        attacking -- possibly at you -- so the Tome turns a page."""
        game, commander = attack_board(builder, mine=True, attacker=1)
        assert game.state.objects[commander].controller == 1
        keeper = only_oid(game, KEEPER)
        swing(game, commander)
        assert pages(game, keeper) == 1

    def test_your_commander_entering_under_an_opponent_still_adds_one(self, builder):
        game, keeper, commander = enter_board(builder, owner=0)
        # The way `return_from_graveyard` puts a card onto the battlefield
        # under somebody else's control: set the controller, then move it.
        game.state.objects[commander].controller = 1
        move_object(game.state, commander, Zone.BATTLEFIELD)
        assert game.state.objects[commander].controller == 1
        settle(game)
        assert pages(game, keeper) == 1

    def test_an_opponents_commander_you_stole_does_not(self, builder):
        """The mirror: you control it and it attacks for you, but it is not
        your commander."""
        game, commander = attack_board(builder, mine=False, attacker=0)
        assert game.state.objects[commander].controller == 0
        keeper = only_oid(game, KEEPER)
        swing(game, commander)
        assert pages(game, keeper) == 0

    def test_an_opponents_commander_entering_does_not(self, builder):
        game, keeper, commander = enter_board(builder, owner=1)
        move_object(game.state, commander, Zone.BATTLEFIELD)
        settle(game)
        assert pages(game, keeper) == 0

    def test_a_creature_of_yours_that_is_not_a_commander_does_not(self, builder):
        game, keeper, bear = enter_board(builder, owner=0, card=BEAR, commander=False)
        move_object(game.state, bear, Zone.BATTLEFIELD)
        settle(game)
        assert pages(game, keeper) == 0


class TestTheControlReadingIsADifferentCard:
    """Why the key exists: on the two stolen boards `controller: "you"` gives
    the opposite answer each time."""

    def test_control_misses_your_stolen_commander(self, builder):
        game, commander = attack_board(builder, mine=True, attacker=1, keepers=(BY_CONTROL,))
        keeper = only_oid(game, BY_CONTROL)
        swing(game, commander)
        assert pages(game, keeper) == 0

    def test_control_counts_the_commander_you_stole(self, builder):
        game, commander = attack_board(builder, mine=False, attacker=0, keepers=(BY_CONTROL,))
        keeper = only_oid(game, BY_CONTROL)
        swing(game, commander)
        assert pages(game, keeper) == 1


class TestTheMatcherReadsTheWord:
    def _stolen(self, builder):
        game, commander = attack_board(builder, mine=True, attacker=1)
        return game, commander, game.state.objects[only_oid(game, KEEPER)]

    def test_you_opponent_and_any(self, builder):
        game, commander, source = self._stolen(builder)
        assert matches_card_filter(game.state, commander, {"owner": "you"}, source)
        assert not matches_card_filter(game.state, commander, {"owner": "opponent"}, source)
        assert matches_card_filter(game.state, commander, {"owner": "any"}, source)

    def test_relative_to_the_ability_controller_not_the_subject(self, builder):
        """Asked from the opponent's side of the table, the same commander is
        an opponent's."""
        game, commander, _ = self._stolen(builder)
        theirs = game.state.objects[commander]  # controlled by player 1
        assert not matches_card_filter(game.state, commander, {"owner": "you"}, theirs)
        assert matches_card_filter(game.state, commander, {"owner": "opponent"}, theirs)

    def test_it_composes_with_controller(self, builder):
        """"A commander you own that an opponent controls" -- a conjunction."""
        game, commander, source = self._stolen(builder)
        filt = {"owner": "you", "controller": "opponent"}
        assert matches_card_filter(game.state, commander, filt, source)
        assert not matches_card_filter(
            game.state, commander, {"owner": "you", "controller": "you"}, source
        )


def _trigger_card(filt: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_probe",
            "name": "Probe",
            "mana_cost": "{2}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "triggered",
                    "trigger": {"event": "attacks", "controller": "any", "filter": filt},
                    "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }
    )


def _cause_filter_card(filt: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_probe",
            "name": "Probe",
            "mana_cost": "{2}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "static",
                    "effect": "double_triggers",
                    "affects": {"controller": "you", "types": ["Creature"]},
                    "cause_events": ["permanent_enters"],
                    "cause_filter": filt,
                }
            ],
        }
    )


class TestTheLoaderRefusesAnIgnoredKey:
    def test_owner_loads(self):
        compile_card(_trigger_card({"is_commander": True, "owner": "you"}))

    @pytest.mark.parametrize(
        "filt",
        [
            {"attacking": True},
            {"name": "Grizzly Bears"},
            {"not_colors": ["W"]},
            {"not_subtypes": ["Human"]},
            {"blocking": True},
        ],
    )
    def test_a_selector_key_the_matcher_never_reads_is_refused(self, filt):
        """Each of these is a legal effect-side selector key and used to load
        here and be dropped -- a trigger strictly wider than printed."""
        with pytest.raises(DslError, match="would load and be ignored"):
            compile_card(_trigger_card(filt))

    @pytest.mark.parametrize("key", ["owner", "controller"])
    @pytest.mark.parametrize("word", ["enchanted_player", {"target": "t1"}])
    def test_a_player_word_the_matcher_cannot_answer_is_refused(self, key, word):
        with pytest.raises(DslError, match=key):
            compile_card(_trigger_card({key: word}))

    def test_a_cause_filter_is_held_to_the_same_list(self):
        """`double_triggers` matches its cause with the same function, so a
        static key that function does not read is refused there as well."""
        compile_card(_cause_filter_card({"types": ["Creature"], "owner": "you"}))
        with pytest.raises(DslError, match="would load and be ignored"):
            compile_card(_cause_filter_card({"types": ["Creature"], "attacking": True}))


class TestTheKeyListMatchesTheMatcher:
    def test_every_listed_key_is_read(self):
        """A key on the list the matcher does not read is the bug this list
        exists to prevent, so the list may only grow alongside the function."""
        source = inspect.getsource(triggers.matches_card_filter)
        read = (
            set(re.findall(r'filt\.get\("(\w+)"\)', source))
            | set(re.findall(r'"(\w+)" in filt', source))
            | set(re.findall(r'filt\["(\w+)"\]', source))
        )
        assert set(TRIGGER_FILTER_KEYS) == read
