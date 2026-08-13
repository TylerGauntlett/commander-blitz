"""The "every card actually works" gate.

For every card in ``data/cards`` this exercises the real code path: put it in a
hand with enough mana and a board rich enough to satisfy its targets, take the
legal action the engine offers, and drive every decision the resolution asks
for.  A card that cannot be cast, or that throws while resolving, fails here.

This is the test that makes "the decks are curated so every card works" a fact
rather than an intention.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from automtg.cards.authoring.verify import check_expectation
from automtg.cards.registry import CardRegistry
from automtg.engine.actions import PendingDecision
from automtg.engine.carddef import CardDef
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.game import Game
from automtg.engine.objects import PLUS_ONE
from automtg.engine.primitives import lose_life
from automtg.engine.stack import push_spell
from automtg.engine.state import new_object
from tests.conftest import GameBuilder

EXPECTATIONS_PATH = Path(__file__).resolve().parent / "expectations.json"

#: A mana base deep enough for anything in either deck.
MANA_BASE = ["plains"] * 6 + ["island"] * 6 + ["swamp"] * 6 + ["mountain"] * 6 + ["forest"] * 6

#: Things for targeted effects to point at.
OWN_BOARD = ["t_bear", "t_dork"]
OPPONENT_BOARD = ["t_bear", "t_flyer", "sol_ring", "t_anthem", "forest", "island"]
OWN_GRAVEYARD = ["t_bear", "t_dork", "t_flyer"]


@pytest.fixture(scope="session")
def expectations() -> dict:
    if not EXPECTATIONS_PATH.exists():
        return {}
    return json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))


def all_cards(registry: CardRegistry) -> list[CardDef]:
    """Every card a game can actually put into play from a deck.

    Tokens are excluded because nobody casts one. Back faces are excluded for
    the same reason and a stronger one: a back face has no mana cost and is
    never in a hand, a library or a deck -- it only ever exists as the face a
    permanent that is already on the battlefield turned over to. Casting one is
    not a thing that can happen, so "it cannot be cast" is not a defect.
    ``TestTransformingCards`` covers them where they do exist.
    """
    return [card for card in registry if not card.is_token and card.front_face is None]


def card_ids(registry: CardRegistry) -> list[str]:
    return sorted(card.id for card in all_cards(registry))


def pytest_generate_tests(metafunc):
    """Parametrize over every shipped card id."""
    if "card_id" not in metafunc.fixturenames:
        return
    registry = CardRegistry.from_dir()
    metafunc.parametrize("card_id", card_ids(registry))


def build_sandbox(registry: CardRegistry, card_id: str, *, in_hand: bool = True) -> Game:
    builder = GameBuilder(registry, players=2, seed=1)
    builder.battlefield(0, MANA_BASE)
    builder.battlefield(0, OWN_BOARD)
    builder.battlefield(1, OPPONENT_BOARD)
    builder.graveyard(0, OWN_GRAVEYARD)
    builder.library(0, ["forest", "island", "swamp", "mountain", "plains"] * 8)
    builder.library(1, ["forest", "island"] * 10)
    if in_hand:
        builder.hand(0, [card_id])
    return builder.build(advance=False)


def add_dummy_spell(game: Game) -> None:
    """Put a spell on the stack so counterspells have something to target."""
    obj = new_object(game.state, "t_bear", owner=1, zone=Zone.HAND)
    game.state.players[1].hand.append(obj.oid)
    push_spell(game.state, obj.oid, 1)


def drive(game: Game, limit: int = 60) -> None:
    """Answer every decision with the first legal action until the game settles."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None or game.over:
            return
        if decision.kind is DecisionKind.PRIORITY:
            return
        game.apply(_answer(game, decision))


def _answer(game: Game, decision: PendingDecision):
    actions = game.legal_actions()
    assert actions, f"no legal action for {decision.kind.value}"

    # Decline combat: this test is about the card, and letting the sandbox attack
    # would fold combat damage and creature deaths into every card's outcome.
    if decision.kind in (DecisionKind.DECLARE_ATTACKERS, DecisionKind.DECLARE_BLOCKERS):
        for action in actions:
            if action.kind is ActionKind.FINISH_DECLARATION:
                return action

    # X is the player's, and "the first choice" is X = 0 -- which would quietly
    # measure every X card doing nothing. Maximum preserves exactly what this
    # harness saw before `CHOOSE_X` existed, when legality pinned X to the most
    # the board could pay for.
    if decision.kind is DecisionKind.CHOOSE_X:
        choices = [a for a in actions if a.kind is ActionKind.CHOOSE]
        if choices:
            return max(choices, key=lambda a: a.choice or 0)

    # Otherwise make a real choice, so optional effects actually get exercised.
    for action in actions:
        if action.kind in (ActionKind.CHOOSE, ActionKind.YES):
            return action
    return actions[0]


def find_play(game: Game, card_id: str):
    for action in game.legal_actions():
        if action.kind not in (ActionKind.CAST, ActionKind.PLAY_LAND):
            continue
        obj = game.state.objects.get(action.source)
        if obj is not None and obj.def_id == card_id and obj.zone is Zone.HAND:
            return action
    return None


class TestEveryCardIsPlayable:
    def test_card_can_be_played_and_resolves(self, registry, card_id, expectations):
        card = registry.get(card_id)
        game = build_sandbox(registry, card_id)

        needs_spell_target = any(spec.kind == "spell" for spec in card.targets)
        if needs_spell_target:
            add_dummy_spell(game)
        game._advance()

        action = find_play(game, card_id)
        assert action is not None, (
            f"{card_id} ({card.name}) is not playable in the sandbox; "
            f"offered: {[a.label for a in game.legal_actions()][:10]}"
        )

        oid = action.source
        game.apply(action)
        drive(game)

        obj = game.state.objects.get(oid)
        assert obj is not None, f"{card_id} vanished entirely"
        assert obj.zone is not Zone.STACK, f"{card_id} never left the stack"

        if card.is_permanent:
            # An Aura in the graveyard is the card working, not failing: Dead
            # Weight's -2/-2 can kill what it enchanted, and state-based actions
            # then correctly bin the Aura. `authoring/verify.py` makes the same
            # allowance, and the two harnesses have to agree or a card passes one
            # gate and fails the other for the same behaviour.
            allowed = (
                {Zone.BATTLEFIELD, Zone.GRAVEYARD} if card.is_aura else {Zone.BATTLEFIELD}
            )
            assert obj.zone in allowed, (
                f"{card_id} is a permanent but ended in {obj.zone.value}"
            )
        else:
            assert obj.zone is Zone.GRAVEYARD, (
                f"{card_id} is a spell but ended in {obj.zone.value}"
            )

        expectation = expectations.get(card_id)
        if expectation:
            _check_expectation(game, card_id, oid, expectation)


class TestActivatedAbilities:
    def test_every_activated_ability_can_be_used(self, registry, card_id):
        """Put the card onto the battlefield and activate each non-mana ability."""
        card = registry.get(card_id)
        activated = [
            a for a in card.abilities if a.is_activated and not a.is_mana_ability
        ]
        if not activated:
            pytest.skip(f"{card_id} has no activated abilities")

        for ability in activated:
            game = build_sandbox(registry, card_id, in_hand=False)
            # Where the card has to *be* to activate this. Cycling is played
            # from hand, so putting every card on the battlefield reported all
            # 44 cycling lands as broken when they were only in the wrong place.
            # Embalm added a third zone -- the graveyard -- so this puts the card
            # wherever the ability says rather than assuming hand is the only
            # alternative to the battlefield.
            zone = _home_zone(ability)
            oid = new_object(game.state, card_id, owner=0, zone=zone).oid
            if zone is Zone.BATTLEFIELD:
                game.state.battlefield.append(oid)
            else:
                game.state.players[0].zone_list(zone).append(oid)
            _pay_the_counters(game, oid, ability)
            _provide_the_sacrifice(game, registry, ability)
            _provide_the_tap_fodder(game, registry, ability)
            _satisfy_the_activation_condition(game, registry, ability)
            _stock_the_hand(game, ability)
            _provide_the_target(game, registry, oid, ability)
            for other in game.state.battlefield:
                game.state.objects[other].entered_turn = 0
            game.state.bump_chars()
            game._advance()
            _provide_the_attacker(game, registry, ability)

            action = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.ACTIVATE
                    and a.ability_index == ability.index
                    and game.state.objects[a.source].def_id == card_id
                ),
                None,
            )
            assert action is not None, (
                f"{card_id} ability {ability.index} ({ability.text!r}) is not activatable; "
                f"offered: {[a.label for a in game.legal_actions()][:10]}"
            )
            game.apply(action)
            drive(game)


def _home_zone(ability) -> Zone:
    """The zone an activated ability is actually offered from.

    The battlefield for almost everything, and it stays the default: an ability
    that lists several zones is still exercised somewhere it works. Cycling is
    the reason this is a question at all -- it is activated from hand, and the
    engine only offers `Ability.active_zones`.
    """
    zones = ability.active_zones or (Zone.BATTLEFIELD,)
    return Zone.BATTLEFIELD if Zone.BATTLEFIELD in zones else zones[0]


def _pay_the_counters(game: Game, oid: int, ability) -> None:
    """Stock the counters an ability's cost wants to remove.

    The sandbox already hands every card a mana base deep enough that "could not
    pay for it" never means "does not work". A counter cost is the same kind of
    setup: Khalni Heart Expedition's ability costs three quest counters, and a
    card that arrives with none would report as unusable when it is only
    unstocked.
    """
    cost = ability.cost
    spec = getattr(cost, "remove_counters", None) if cost else None
    if not spec:
        return
    kind = str(spec.get("counter", PLUS_ONE))
    amount = int(spec.get("amount", 1))
    game.state.objects[oid].counters[kind] = amount


def _provide_the_sacrifice(game: Game, registry, ability) -> None:
    """Put something on the board that the ability's sacrifice cost accepts.

    Same reasoning as `_pay_the_counters`: the sandbox's job is to make "could
    not pay for it" impossible, so that "not activatable" only ever means the
    ability is broken. Koma's ability costs *another Serpent*, and the generic
    board has none -- which reported a working card as unusable.
    """
    cost = ability.cost
    spec = getattr(cost, "sacrifice", None) if cost else None
    if not spec:
        return
    subtypes = {str(s) for s in spec.get("subtypes") or []}
    types = {str(t) for t in spec.get("types") or ["Creature"]}
    match = next(
        (
            c
            for c in sorted(registry, key=lambda c: c.id)
            if not c.is_token
            and types <= set(c.types)
            and (not subtypes or subtypes & set(c.subtypes))
        ),
        None,
    )
    if match is None:
        return
    fodder = new_object(game.state, match.id, owner=0, zone=Zone.BATTLEFIELD)
    game.state.battlefield.append(fodder.oid)


def _provide_the_tap_fodder(game: Game, registry, ability) -> None:
    """Put out enough untapped permanents for a `tap_permanents` cost.

    Same family as `_provide_the_sacrifice`, and needed for the same reason:
    the sandbox's job is to make "could not pay for it" impossible, so that
    "not activatable" only ever means the ability is broken. Captivating
    Vampire's cost is *five untapped Vampires* and the generic board has none,
    which reported a working card as unusable.

    The source itself is eligible among them -- it is a Vampire, and the
    printed ruling says so -- but it arrives after this runs, so the count is
    filled without relying on that.
    """
    cost = ability.cost
    spec = getattr(cost, "tap_permanents", None) if cost else None
    if not spec:
        return
    subtypes = {str(s) for s in spec.get("subtypes") or []}
    types = {str(t) for t in spec.get("types") or ["Creature"]}
    match = next(
        (
            c
            for c in sorted(registry, key=lambda c: c.id)
            if not c.is_token
            and types <= set(c.types)
            and (not subtypes or subtypes & set(c.subtypes))
        ),
        None,
    )
    if match is None:
        return
    for _ in range(int(spec.get("count", 1) or 1)):
        fodder = new_object(game.state, match.id, owner=0, zone=Zone.BATTLEFIELD)
        game.state.battlefield.append(fodder.oid)


def _satisfy_the_activation_condition(game: Game, registry, ability) -> None:
    """Put out whatever an "activate only if..." clause is counting.

    Sixth of the same family, and added for the same reason as the other five:
    the sandbox's job is that "not activatable" only ever means the ability is
    broken. Bloodline Keeper says "activate only if you control five or more
    Vampires" and the generic board has none.

    Deliberately dumb, exactly as `_provide_the_target` is. It reads two shapes --
    ``{"cmp": ">=", "left": {"count": <selector>}, "right": {"const": n}}``, which
    it satisfies by adding permanents, and the same comparison over
    ``life_lost_this_turn``, which it satisfies by taking the life. A helper clever
    enough to solve an arbitrary condition would be a second implementation of
    `evaluate` living in the tests, and the first thing it would hide is a bug in
    the first.
    """
    condition = getattr(ability, "activation_condition", None)
    if not isinstance(condition, dict) or "cmp" not in condition:
        return
    left = condition.get("left") or {}
    right = condition.get("right") or {}
    if "const" not in right:
        return

    # "Activate only if an opponent lost life this turn" -- Falkenrath Pit
    # Fighter. The tally is the real one the engine keeps, so this satisfies the
    # condition by actually taking the life rather than by writing the counter
    # the condition reads: a card that mis-names the tally still fails.
    if "life_lost_this_turn" in left:
        whose = str(left["life_lost_this_turn"])
        pids = [p.pid for p in game.state.players if p.pid != 0] if "opponent" in whose else [0]
        for pid in pids:
            lose_life(game.state, pid, int(right["const"]))
        return

    if "count" not in left:
        return
    selector = left["count"]
    if selector.get("zone", "battlefield") != "battlefield":
        return
    subtypes = {str(s) for s in selector.get("subtypes") or []}
    types = {str(t) for t in selector.get("types") or ["Creature"]}
    match = next(
        (
            c
            for c in sorted(registry, key=lambda c: c.id)
            if not c.is_token
            and c.front_face is None
            and types <= set(c.types)
            and (not subtypes or subtypes & set(c.subtypes))
        ),
        None,
    )
    if match is None:
        return
    for _ in range(int(right["const"])):
        fodder = new_object(game.state, match.id, owner=0, zone=Zone.BATTLEFIELD)
        game.state.battlefield.append(fodder.oid)


def _stock_the_hand(game: Game, ability) -> None:
    """Give the player the cards a discard cost wants to throw away.

    Third of the same family as `_pay_the_counters` and `_provide_the_sacrifice`:
    the sandbox's job is that "not activatable" only ever means the ability is
    broken. Nezahal's blink costs three cards and the board arrives with an
    empty hand.
    """
    cost = ability.cost
    needed = int(getattr(cost, "discard", 0) or 0) if cost else 0
    hand = game.state.players[0].hand
    while len(hand) < needed:
        card = new_object(game.state, "forest", owner=0, zone=Zone.HAND)
        hand.append(card.oid)


def _provide_the_target(game: Game, registry, oid: int, ability) -> None:
    """Put something on the board the ability can legally point at.

    Fourth of the same family as the three helpers above, and for the same
    reason: "not activatable" must only ever mean the ability is broken. Herd
    Heirloom targets a creature with power 4 or greater and the generic board
    carries neither -- so the ability reported as unusable when it was only
    unaimed.

    Deliberately dumb: it adds the biggest creature in the pool rather than
    solving the selector, because a helper clever enough to satisfy an arbitrary
    filter would be a second implementation of `matches` living in the tests.
    """
    from automtg.engine.targeting import enumerate_target_tuples

    if not ability.targets:
        return
    if enumerate_target_tuples(game.state, 0, ability.targets, oid):
        return
    biggest = max(
        (c for c in registry if c.is_creature and not c.is_token),
        key=lambda c: (c.power or 0, c.id),
        default=None,
    )
    if biggest is None:
        return
    obj = new_object(game.state, biggest.id, owner=0, zone=Zone.BATTLEFIELD)
    obj.entered_turn = 0
    game.state.battlefield.append(obj.oid)
    game.state.bump_chars()


def _provide_the_attacker(game: Game, registry, ability) -> None:
    """Declare an attacker when the ability can only point at one.

    Fifth of the same family as the four helpers above, and the only one that
    has to move the *game* rather than stock the board: `attacking` is not a
    field on an object, it is `combat.attacking(oid)`, so the sole way to
    satisfy "target attacking Vampire" is to reach declare-attackers and
    declare something. Duskborne Skymarcher is the witness -- its ability is
    exactly right and was reported unusable here purely because the generic
    board is never in combat.

    The selector is read only to *choose* a candidate from the pool, the same
    way `_provide_the_sacrifice` reads a sacrifice cost's `types` and
    `subtypes`. Whether the result is a legal target stays
    `enumerate_target_tuples`' answer, so no second copy of `matches` moves into
    the tests.
    """
    wants = next((s for s in ability.targets if s.selector.get("attacking")), None)
    if wants is None:
        return

    subtypes = {str(s) for s in wants.selector.get("subtypes") or []}
    types = {str(t) for t in wants.selector.get("types") or ["Creature"]}
    match = next(
        (
            c
            for c in sorted(registry, key=lambda c: c.id)
            if not c.is_token
            and c.is_creature
            and types <= set(c.types)
            and (not subtypes or subtypes & set(c.subtypes))
        ),
        None,
    )
    if match is None:
        return
    attacker = new_object(game.state, match.id, owner=0, zone=Zone.BATTLEFIELD)
    attacker.entered_turn = 0
    game.state.battlefield.append(attacker.oid)
    game.state.bump_chars()

    # Walk to declare-attackers by passing priority. `_answer` is deliberately
    # not reused: it declines combat outright, which is the whole thing being
    # undone here.
    for _ in range(40):
        decision = game.pending()
        if decision is None or game.over:
            return
        if decision.kind is DecisionKind.DECLARE_ATTACKERS:
            break
        if decision.kind is not DecisionKind.PRIORITY:
            return
        passing = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.PASS), None
        )
        if passing is None:
            return
        game.apply(passing)
    else:
        return

    add = next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_ATTACKER and a.source == attacker.oid
        ),
        None,
    )
    if add is None:
        return
    game.apply(add)
    finish = next(
        (a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION),
        None,
    )
    if finish is not None:
        game.apply(finish)


class TestManaAbilities:
    def test_mana_abilities_produce_mana(self, registry, card_id):
        card = registry.get(card_id)
        mana_abilities = card.mana_abilities()
        if not mana_abilities:
            pytest.skip(f"{card_id} produces no mana")
        for ability in mana_abilities:
            assert ability.mana_options, f"{card_id} ability {ability.index} yields nothing"
            for option in ability.mana_options:
                assert sum(option) > 0


def _check_expectation(game: Game, card_id: str, oid: int, expectation: dict) -> None:
    """Assert a per-card expectation from ``expectations.json``.

    Delegates to the authoring gate's own checker rather than keeping a second
    copy. The two had already diverged: this file understood five of the eleven
    keys in ``verify.EXPECTATION_KEYS``, so an expectation asserting `granted`,
    `target_pt_delta`, `library_size`, `graveyard_size`, `zone` or
    `opponent_battlefield_count` was read here as asserting *nothing* and passed
    whatever the card did. The sandboxes were always meant to mirror each other
    -- ``verify.MANA_BASE`` says so in a comment -- and sharing the checker is
    how that stops being a comment.
    """
    problems = check_expectation(game, card_id, oid, expectation)
    assert not problems, f"{card_id}: " + "; ".join(problems)

