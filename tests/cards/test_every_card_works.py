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
#:
#: The opponent's creature is **legendary**, and inert -- a 2/2 with no abilities,
#: exactly `t_bear` wearing a supertype. Commander Sofia Daguerre reads "destroy
#: up to one target legendary permanent", and with no legendary on the board she
#: was the only legal target for her own enters trigger: she destroyed herself
#: and gate 4 rejected a permanent that ended in the graveyard. The card was
#: never wrong.
#:
#: A swap rather than an addition, so both board sizes are unchanged and no
#: expectation moves. Inert for the reason `verify.py`'s twin of this prop is:
#: a legendary with an activated ability the opponent can afford suppresses the
#: auto-pass, hands them a real priority window with the card under test still
#: on the stack, and cards start failing gate 4 with "never left the stack".
#: `t_flyer` keeps a *nonlegendary* creature on that board.
OWN_BOARD = ["t_bear", "t_dork"]
OPPONENT_BOARD = ["t_legend", "t_flyer", "sol_ring", "t_anthem", "forest", "island"]
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
    # The second card is deliberately not a land -- see `verify.build_sandbox`.
    # Cultivator Colossus puts a land from hand onto the battlefield, draws, and
    # repeats; against forty basic lands and a spare land in hand it decked the
    # player. Second rather than first, so the cards that reveal the *top* and
    # branch on whether it is a land still see one.
    library = ["forest", "island", "swamp", "mountain", "plains"] * 8
    library[1] = "t_bolt"
    builder.library(0, library)
    builder.library(1, ["forest", "island"] * 10)
    if in_hand:
        # A spare land beside the card under test, mirroring
        # `verify.build_sandbox`. 601.2a moves a spell to the stack before its
        # costs are paid, so a card can never discard *itself* to pay its own
        # additional cost -- and a hand of one leaves every mandatory "as an
        # additional cost, discard a card" with no fodder and unplayable here.
        # Big Score, Laughing Mad, Thrill of Possibility, Tormenting Voice,
        # Wild Guess and Mardu Outrider are the six that found it.
        #
        # A land rather than a spell: a castable card in hand keeps the player
        # on priority while the card under test is on the stack, and every card
        # then fails with "never left the stack".
        builder.hand(0, [card_id, "forest"])
    return builder.build(advance=False)


#: One spell of each broad shape, because a `kind: "spell"` target spec filters
#: with the full selector language: a lone creature spell makes "counter target
#: **noncreature** spell" unplayable here and fails Negate at gate 4. All three
#: target nothing of their own, since the sandbox may let whichever survives
#: resolve.
#:
#: `t_x_spell` is the third for the same reason the second exists: Frontline
#: Medic counters "target spell **with {X} in its mana cost**", and neither a
#: Bear nor a plain instant has one. It is a creature spell whose cost is
#: `{X}{G}`, so the shape it adds is the cost rather than the card type.
DUMMY_SPELLS = ("t_bear", "t_plain_instant", "t_x_spell")


def add_dummy_spell(game: Game) -> None:
    """Put spells on the stack so counterspells have something to target."""
    for card_id in DUMMY_SPELLS:
        obj = new_object(game.state, card_id, owner=1, zone=Zone.HAND)
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
        # ...but never an X that ends the game, mirroring
        # `verify._answer`. Toxic Deluge's X is paid in **life** and 118.4 puts
        # the whole total on offer, so the maximum is suicide: the player hits 0,
        # loses to a state-based action, and the spell never resolves. Inert for
        # a mana X, whose ceiling is bounded by the board's 30 lands against 40
        # life.
        pid = decision.player
        life = game.state.players[pid].life if pid is not None else 0
        alive = [a for a in choices if (a.choice or 0) < life]
        if alive:
            return max(alive, key=lambda a: a.choice or 0)
        if choices:
            return max(choices, key=lambda a: a.choice or 0)

    # Otherwise make a real choice, so optional effects actually get exercised.
    for action in actions:
        if action.kind in (ActionKind.CHOOSE, ActionKind.YES):
            return action
    return actions[0]


def find_play(game: Game, card_id: str):
    matches = []
    for action in game.legal_actions():
        if action.kind not in (ActionKind.CAST, ActionKind.PLAY_LAND):
            continue
        obj = game.state.objects.get(action.source)
        if obj is not None and obj.def_id == card_id and obj.zone is Zone.HAND:
            matches.append(action)
    if not matches:
        return None
    # The front face, whenever one is offered. A modal DFC is offered twice --
    # once as a cast and once as a land drop -- and `_land_actions` runs first,
    # so without this the land line wins on ordering alone.
    # `authoring/verify.py` prefers the same line, and the two harnesses have to
    # agree or a card passes one gate and fails the other for one behaviour.
    return next((a for a in matches if not a.second_face), matches[0])


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

        # The face that actually resolved, which is not always the one under
        # test: a modal DFC played as its land half is a permanent even though
        # the card is an Instant.
        played = game.state.card_of(obj)
        if played.is_permanent:
            # An Aura in the graveyard is the card working, not failing: Dead
            # Weight's -2/-2 can kill what it enchanted, and state-based actions
            # then correctly bin the Aura. `authoring/verify.py` makes the same
            # allowance, and the two harnesses have to agree or a card passes one
            # gate and fails the other for the same behaviour.
            allowed = (
                {Zone.BATTLEFIELD, Zone.GRAVEYARD} if played.is_aura else {Zone.BATTLEFIELD}
            )
            assert obj.zone in allowed, (
                f"{card_id} is a permanent but ended in {obj.zone.value}"
            )
        else:
            # A spell goes to its owner's graveyard -- unless the card says
            # otherwise, which two riders do: "Exile Teferi's Protection" and
            # rebound's "exile it as it resolves". `authoring/verify.py` makes
            # the same allowance and reads the same two flags, because the two
            # harnesses have to agree or a card passes one gate and fails the
            # other for the same behaviour.
            spell_zones = {Zone.GRAVEYARD}
            if played.exiles_itself or played.rebound:
                spell_zones.add(Zone.EXILE)
            assert obj.zone in spell_zones, (
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
            _provide_the_untap_fodder(game, registry, ability)
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
    # Loyalty, for the same reason and one step earlier: this harness puts the
    # card on the battlefield by hand rather than through `move_object`, so the
    # enters-with-counters replacement that carries a planeswalker's starting
    # loyalty never runs. Every minus ability would report as unusable on a
    # board that was never legal.
    loyalty = game.state.registry.get(game.state.objects[oid].def_id).loyalty
    if loyalty is not None:
        game.state.objects[oid].counters["loyalty"] = loyalty
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
    # As many as the cost asks for, not one. Bolas's Citadel sacrifices **ten**
    # nonland permanents, and a board handed a single creature reported a
    # working card as unusable -- the same false negative this helper exists to
    # prevent, one order of magnitude up.
    count = spec.get("count", 1)
    wanted = int(count) if isinstance(count, int) else 1
    for _ in range(max(1, wanted)):
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


def _provide_the_untap_fodder(game: Game, registry, ability) -> None:
    """Put out enough **tapped** permanents for an `untap_permanents` cost.

    The mirror of `_provide_the_tap_fodder`, and needed for the same reason:
    the sandbox's job is to make "could not pay for it" impossible, so that
    "not activatable" only ever means the ability is broken. Halo Fountain's
    third line unbends *fifteen tapped creatures* and the generic board has
    none — untapped ones would not do, because the pool forces `tapped: True`.

    The source is not counted on, exactly as its twin does not count on it: it
    arrives after this runs, and here it would be tapped by its own `{T}`
    anyway.
    """
    cost = ability.cost
    spec = getattr(cost, "untap_permanents", None) if cost else None
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
        fodder.tapped = True
        game.state.battlefield.append(fodder.oid)


def _satisfy_the_activation_condition(game: Game, registry, ability) -> None:
    """Put out whatever an "activate only if..." clause is counting.

    Sixth of the same family, and added for the same reason as the other five:
    the sandbox's job is that "not activatable" only ever means the ability is
    broken. Bloodline Keeper says "activate only if you control five or more
    Vampires" and the generic board has none.

    Deliberately dumb, exactly as `_provide_the_target` is. It reads three shapes
    -- ``{"cmp": ">=", "left": {"count": <selector>}, "right": {"const": n}}``,
    which it satisfies by adding permanents; the same comparison over
    ``life_lost_this_turn``, which it satisfies by taking the life; and a
    per-player ``max_count_of``, which it satisfies by stocking one opponent's
    board. A helper clever enough to solve an arbitrary condition would be a
    second implementation of `evaluate` living in the tests, and the first thing
    it would hide is a bug in the first.
    """
    condition = getattr(ability, "activation_condition", None)
    if not isinstance(condition, dict) or "cmp" not in condition:
        return
    if _satisfy_a_per_player_count(game, registry, condition):
        return
    left = condition.get("left") or {}
    right = condition.get("right") or {}
    if "const" not in right:
        return

    if "permanents_entered_this_turn" in left:
        _make_permanents_enter(game, registry, left, int(right["const"]))
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
    match = _fodder_for(registry, selector)
    if match is None:
        return
    for _ in range(int(right["const"])):
        fodder = new_object(game.state, match.id, owner=0, zone=Zone.BATTLEFIELD)
        game.state.battlefield.append(fodder.oid)


def _make_permanents_enter(game: Game, registry, left: dict, count: int) -> None:
    """"Activate only if two or more creatures entered the battlefield under your
    control this turn" -- Diamond City.

    Eighth of the family, and the second that has to satisfy a clause by *doing*
    the thing rather than by arranging the board. `TurnLedger.permanents_entered`
    records arrivals, not residents, so stocking the battlefield the way the
    `count` branch does satisfies nothing: a permanent placed with `new_object`
    never entered. The same distinction the card is about.

    It goes through `create_token`, which fires the real enters event that the
    ledger folds -- the argument `life_lost_this_turn` makes one branch up, and
    for the same reason. A card that names the wrong tally still fails here,
    because nothing writes the number the condition reads except the engine.

    The token has to match the filter's own `types`, since the clause counts what
    entered rather than everything that did. A filter this cannot match is left
    alone rather than approximated, and the ability reports as unusable -- which
    is the honest answer when the harness cannot build the position.
    """
    from automtg.engine.primitives import create_token

    spec = left.get("permanents_entered_this_turn") or {}
    if spec.get("controller", "you") != "you":
        return
    match = _fodder_for(registry, {"types": spec.get("types") or ["Creature"]})
    if match is None:
        return
    create_token(game.state, match.id, 0, max(1, count))


def _satisfy_a_per_player_count(game: Game, registry, condition: dict) -> bool:
    """"Activate only if an opponent controls more lands than you" -- Weathered Wayfarer.

    Seventh of the family, and the one board the generic sandbox gets *backwards*
    rather than merely leaving bare: it deals you thirty lands to the opponent's
    two, so this clause is false by a wide margin and the ability is correctly not
    offered. Every other helper here adds something missing; this one has to
    out-build a mana base.

    Stocked on **one** opponent's side, not spread across the table. A per-player
    leaf that could be satisfied by the pooled total is the exact bug it exists to
    prevent, so a harness that spread the lands around would make the gate agree
    with the implementation it is supposed to check.

    Returns whether it handled the condition, so the caller can stop.
    """
    left = condition.get("left") or {}
    if "max_count_of" not in left:
        return False
    from automtg.engine.effects.context import EffectContext
    from automtg.engine.effects.values import evaluate_value

    spec = left["max_count_of"]
    selector = spec.get("objects") or {}
    if selector.get("zone", "battlefield") != "battlefield":
        return True
    match = _fodder_for(registry, selector)
    if match is None:
        return True
    # The right-hand side through the engine's own evaluator rather than a
    # reimplementation of it: "more lands than you" is measured against a board
    # this harness has already dealt, and no `const` says how big that is.
    ctx = EffectContext(state=game.state, controller=0)
    opponent = next((p.pid for p in game.state.players if p.pid != 0), None)
    if opponent is None:
        return True
    for _ in range(evaluate_value(ctx, condition.get("right")) + 1):
        fodder = new_object(game.state, match.id, owner=opponent, zone=Zone.BATTLEFIELD)
        game.state.battlefield.append(fodder.oid)
    game.state.bump_chars()
    return True


def _fodder_for(registry, selector: dict):
    """The first card in the pool matching a counting filter's types.

    Shared by the two branches of `_satisfy_the_activation_condition` that satisfy
    a count by putting permanents out, so "what counts as one of those" cannot
    drift between them.
    """
    subtypes = {str(s) for s in selector.get("subtypes") or []}
    types = {str(t) for t in selector.get("types") or ["Creature"]}
    return next(
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

    Deliberately dumb, the same way `_provide_the_sacrifice` and
    `_provide_the_attacker` are: the selector is read only far enough to *choose*
    a card and a seat, never to decide whether the result is legal. That answer
    stays `enumerate_target_tuples`', so no second copy of `matches` moves into
    the tests.

    Three things it reads, each because a shipped card reported as unusable
    without it. `types` — Field of Ruin targets a **land**, and the biggest
    creature in the pool is not one. `controller` — the same card wants a land
    *an opponent controls*, so the fodder has to be stocked on the other seat.
    And `not_supertypes`, which is the one clause where the dumb pick is not
    merely unhelpful but actively wrong: "nonbasic land" excludes exactly the
    lands a naive first-by-id pick is most likely to land on.
    """
    from automtg.engine.targeting import enumerate_target_tuples

    if not ability.targets:
        return
    if enumerate_target_tuples(game.state, 0, ability.targets, oid):
        return
    if any(spec.kind == "spell" for spec in ability.targets):
        # An **ability** that counters a spell -- Frontline Medic's "Sacrifice
        # this creature: Counter target spell…". The fodder helpers below stock
        # the *battlefield*, and a spell is not on it; there is nothing to point
        # at until something is on the stack. Safe here in a way it is not in
        # `verify.py`'s cast sandbox, where a non-empty stack would make a
        # creature uncastable (117.1a): this test puts the card onto the
        # battlefield directly and only ever activates it, which is
        # instant-speed.
        add_dummy_spell(game)
        return
    for spec in ability.targets:
        match = _target_fodder(registry, spec)
        if match is None:
            continue
        obj = new_object(game.state, match.id, owner=_seat_for(game, spec), zone=Zone.BATTLEFIELD)
        obj.entered_turn = 0
        game.state.battlefield.append(obj.oid)
    game.state.bump_chars()


def _seat_for(game: Game, spec) -> int:
    """Whose board the fodder for this spec belongs on."""
    if spec.selector.get("controller") != "opponent":
        return 0
    return next((p.pid for p in game.state.players if p.pid != 0), 0)


def _target_fodder(registry, spec):
    """One card from the pool that a target spec plausibly accepts.

    A creature spec keeps the original answer -- the **biggest** creature --
    because Herd Heirloom wants power 4 or greater and the first card by id has
    none. Anything else takes the first match by id, the same tie-break
    `_provide_the_sacrifice` uses.
    """
    if spec.kind not in ("permanent", "any"):
        return None
    selector = spec.selector
    types = {str(t) for t in selector.get("types") or ["Creature"]}
    subtypes = {str(s) for s in selector.get("subtypes") or []}
    forbidden = {str(s) for s in selector.get("not_supertypes") or []}

    def eligible(card) -> bool:
        return (
            not card.is_token
            and types <= set(card.types)
            and (not subtypes or subtypes & set(card.subtypes))
            and not (forbidden & set(card.supertypes))
        )

    if types == {"Creature"}:
        return max(
            (c for c in registry if c.is_creature and eligible(c)),
            key=lambda c: (c.power or 0, c.id),
            default=None,
        )
    return next((c for c in sorted(registry, key=lambda c: c.id) if eligible(c)), None)


def _selector_branches(selector):
    """A selector, and each of its ``any_of`` branches merged onto it.

    "It deals 4 damage to target **attacking or blocking** creature" (Eiganjo,
    Seat of the Empire) is one `any_of` over two branches, and the only clause
    the helper below can act on -- `attacking` -- lives inside a branch rather
    than on the outer selector. Without this it read nothing, declared no
    attacker, and a card whose ability is exactly right reported as unusable.

    Still only ever read far enough to *choose* a candidate and a seat, which is
    the standing contract of this family of helpers: whether the result is a
    legal target stays `enumerate_target_tuples`' answer, so no second copy of
    `matches` moves into the tests. Narrowing the card to plain "attacking" so
    the old reader could see it would have been the other way round -- a
    strictly weaker card written to suit the harness.
    """
    yield selector
    for branch in selector.get("any_of") or ():
        if isinstance(branch, dict):
            yield {**selector, **branch}


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
    wants = next(
        (
            branch
            for spec in ability.targets
            for branch in _selector_branches(spec.selector)
            if branch.get("attacking")
        ),
        None,
    )
    if wants is None:
        return

    subtypes = {str(s) for s in wants.get("subtypes") or []}
    types = {str(t) for t in wants.get("types") or ["Creature"]}
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

