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

from automtg.cards.authoring.verify import check_expectation, swap_in_tribal_body
from automtg.cards.registry import CardRegistry
from automtg.engine.actions import PendingDecision
from automtg.engine.carddef import CardDef
from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.events import EventType
from automtg.engine.game import Game
from automtg.engine.objects import PLUS_ONE
from automtg.engine.primitives import add_counters, lose_life
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
    # "As an additional cost to cast this spell, tap an untapped Vampire you
    # control" -- New Blood. `t_bear` is a Bear, so a printed cost naming any
    # tribe is unpayable and the card is never offered. The swap is shared with
    # `verify.build_sandbox` rather than copied, so the two sandboxes cannot
    # disagree about what such a cost can be paid with, and it happens **only**
    # for a card that names a tribe -- every other card sees the board it was
    # measured on.
    under_test = registry.get(card_id) if card_id in registry else None
    builder.battlefield(0, swap_in_tribal_body(registry, list(OWN_BOARD), under_test))
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


def add_dummy_spell(game: Game, seat: int = 1) -> None:
    """Put spells on ``seat``'s side of the stack for a spell target to find.

    The seat defaults to the opponent, which is whose spell every counterspell
    in the pool wants. Kitsa is the first card to want the other one -- "copy
    target instant or sorcery spell **you control**" -- and with only the
    opponent's dummies up she reported as unusable on a board that simply held
    nobody's spell she was allowed to point at.
    """
    for card_id in DUMMY_SPELLS:
        obj = new_object(game.state, card_id, owner=seat, zone=Zone.HAND)
        game.state.players[seat].hand.append(obj.oid)
        push_spell(game.state, obj.oid, seat)


def add_dummy_ability(game: Game, registry, seat: int = 0) -> None:
    """Put an **ability** on the stack for an `ability_on_stack` target to find.

    The sibling of `add_dummy_spell` above, and needed for the same reason at a
    different kind of object: the fodder helpers stock the *battlefield*, and an
    ability on the stack is not on it, so Peter Parker's Camera reported as
    unusable on a board that simply held no ability to copy.

    The seat defaults to **the controller's own**, which is the opposite of
    `add_dummy_spell`'s default and is the printed clause: every card in this
    family says "an ability **you control**" (the Camera, Lithoform Engine,
    Strionic Resonator), where every counterspell wants the opponent's.

    Any permanent with a non-mana activated ability will do, since
    `_ability_matches` reads only the controller -- so this picks the first one in
    the pool rather than trying to satisfy a selector it knows nothing about.
    """
    from automtg.engine.stack import push_activated_ability

    for card_id in sorted(registry.ids()):
        card = registry.get(card_id)
        ability = next(
            (a for a in card.abilities if a.is_activated and not a.is_mana_ability),
            None,
        )
        if ability is None or ability.targets:
            # No targets, so putting it on the stack needs no choices made.
            continue
        obj = new_object(game.state, card_id, owner=seat, zone=Zone.BATTLEFIELD)
        obj.controller = seat
        game.state.battlefield.append(obj.oid)
        push_activated_ability(game.state, obj.oid, ability.index, seat)
        return


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
            # otherwise, which three riders do: "Exile Teferi's Protection",
            # rebound's "exile it as it resolves", and Approach of the Second
            # Sun's "put it into its owner's library seventh from the top".
            # `authoring/verify.py` makes the same allowance and reads the same
            # three flags, because the two harnesses have to agree or a card
            # passes one gate and fails the other for the same behaviour.
            #
            # Approach is the card that proved that warning was not theoretical:
            # the `tucks_itself` rider shipped having widened only the other
            # harness, so the card was accepted by `--collect` and failed here.
            spell_zones = {Zone.GRAVEYARD}
            if played.exiles_itself or played.rebound:
                spell_zones.add(Zone.EXILE)
            if played.tucks_itself is not None:
                spell_zones.add(Zone.LIBRARY)
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
            _reach_the_level(game, oid, ability)
            _pay_the_counters(game, oid, ability)
            _afford_the_life(game, ability)
            _provide_the_sacrifice(game, registry, ability)
            _provide_the_tap_fodder(game, registry, ability)
            _provide_the_untap_fodder(game, registry, ability)
            _provide_the_counter_fodder(game, registry, ability)
            _satisfy_the_activation_condition(game, registry, ability, oid)
            _stock_the_hand(game, ability)
            _provide_the_target(game, registry, oid, ability)
            for other in game.state.battlefield:
                game.state.objects[other].entered_turn = 0
            game.state.bump_chars()
            game._advance()
            _provide_the_attacker(game, registry, ability)
            _satisfy_the_attack_count(game, registry, ability)

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


def _reach_the_level(game: Game, oid: int, ability) -> None:
    """Stand a Class on the rung this ability needs (716).

    Same family as `_pay_the_counters`, and the same argument: "not activatable"
    must only ever mean the ability is broken. A card put on the battlefield
    here is a level-1 Class, so every "{3}{W}: Level 3" (activatable only at
    level 2) and every activated ability printed under level 2 or 3 would report
    as unusable on a board that simply never bought the levels below it.

    Written onto the object rather than bought through the level lines, as
    `_pay_the_counters` writes loyalty: this arranges a position. The *lower*
    rung is still refused -- a level-2 line on a level-2 Class is not offered --
    so this cannot launder a ladder the engine gets wrong.
    """
    needed = max(ability.level or 1, (ability.becomes_level or 2) - 1)
    game.state.objects[oid].class_level = needed


def _afford_the_life(game: Game, ability) -> None:
    """Raise the life total to something the ability's life cost can be paid from.

    Same argument as the mana base and the counters above: "could not pay for
    it" must never be read as "does not work". Aetherflux Reservoir prints
    "Pay 50 life", 118.4 forbids paying life you do not have, and the sandbox
    seats start at 40 -- so the one ability the card is played for reported as
    unusable on a board where it was merely unaffordable.

    Deliberately additive rather than a flat large number: the cost is paid for
    real a moment later, and a seat left at exactly the cost would be dead on
    the spot from the resulting zero.
    """
    cost = ability.cost
    if cost is None:
        return
    needed = getattr(cost, "pay_life", None)
    if not needed:
        return
    # `pay_life` is a value expression as often as it is a number -- War Room's
    # is `{"commander_color_identity": "you"}`. Evaluating it would need a
    # context this harness has not built yet, and the answer is only ever used
    # as a floor, so an unevaluated one takes a headroom that no printed card
    # exceeds.
    floor = int(needed) + 10 if isinstance(needed, int) else 60
    game.state.players[0].life = max(game.state.players[0].life, floor)


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
    # An ultimate costs more than the printed number -- The Theorist's -6 on a
    # starting loyalty of 3 -- so stock whichever is larger, as a counter cost
    # is stocked below.
    card = game.state.registry.get(game.state.objects[oid].def_id)
    loyalty = card.loyalty
    if loyalty is not None:
        price = getattr(cost, "loyalty", None) if cost else None
        needed = -int(price) if price is not None and int(price) < 0 else 0
        game.state.objects[oid].counters["loyalty"] = max(loyalty, needed)
    # The same replacement, for every card that is not a planeswalker. A
    # printed **0/0** whose size comes from "this creature enters with X +1/+1
    # counters on it" (614.1c) is placed here with nothing on it, and the
    # state-based action bins it before the first priority window -- so its
    # abilities reported as unusable from a graveyard. Cryptic Trilobite found
    # this; loyalty was the same bug, noticed one card type earlier.
    #
    # Only enough counters to live, not the X a real cast would have announced.
    # This arranges a position, and a larger creature proves nothing more.
    # Written straight onto the object for the reason the loyalty line above is:
    # a counter arriving is an event other cards react to, and nothing here is
    # playing a turn.
    for replacement in card.replacements or ():
        if replacement.get("event") != "self_enters_with_counters":
            continue
        kind = str(replacement.get("counter") or PLUS_ONE)
        amount = replacement.get("amount")
        if isinstance(amount, dict) and "const" in amount:
            wanted = int(amount["const"])
        elif isinstance(amount, int):
            wanted = int(amount)
        else:
            # An X, or anything else decided as the spell resolves. One counter
            # is enough for a 0/0 to survive, which is all this is for.
            wanted = max(1, 1 - int(card.toughness or 0))
        counters = game.state.objects[oid].counters
        counters[kind] = max(counters.get(kind, 0), wanted)
    game.state.bump_chars()
    # A station striation (721): "12+ | {3}{W}, {T}: …" is an ability the
    # permanent does not *have* below twelve charge counters, so a Planet placed
    # with none reported its best line as missing. Stocked to exactly the
    # number, which is the boundary the gate is written against -- one fewer
    # and the ability is rightly absent.
    threshold = getattr(ability, "threshold", None)
    if threshold is not None:
        kind, at_least = threshold
        counters = game.state.objects[oid].counters
        counters[kind] = max(counters.get(kind, 0), at_least)
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
    # As many as the cost asks for, not one. Bolas's Citadel sacrifices **ten**
    # nonland permanents, and a board handed a single creature reported a
    # working card as unusable -- the same false negative this helper exists to
    # prevent, one order of magnitude up.
    count = spec.get("count", 1)
    wanted = max(1, int(count) if isinstance(count, int) else 1)
    match = _fodder_for(registry, spec, wanted)
    if match is None:
        return
    for _ in range(wanted):
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
    wanted = int(spec.get("count", 1) or 1)
    match = _fodder_for(registry, spec, wanted)
    if match is None:
        return
    for _ in range(wanted):
        fodder = new_object(game.state, match.id, owner=0, zone=Zone.BATTLEFIELD)
        game.state.battlefield.append(fodder.oid)
    # Crew's cost is a total power, not a count: Shorikai's Crew 8 needs eight
    # power of untapped creatures, and the generic board's two may not reach it.
    needed = int(spec.get("total_power", 0) or 0)
    if needed:
        strong = next(
            (
                c
                for c in sorted(registry, key=lambda c: c.id)
                if not c.is_token
                and "Creature" in c.types
                and isinstance(c.power, int)
                and c.power > 0
            ),
            None,
        )
        if strong is not None:
            for _ in range(-(-needed // strong.power)):
                fodder = new_object(game.state, strong.id, owner=0, zone=Zone.BATTLEFIELD)
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
    wanted = int(spec.get("count", 1) or 1)
    match = _fodder_for(registry, spec, wanted)
    if match is None:
        return
    for _ in range(wanted):
        fodder = new_object(game.state, match.id, owner=0, zone=Zone.BATTLEFIELD)
        fodder.tapped = True
        game.state.battlefield.append(fodder.oid)


def _provide_the_counter_fodder(game: Game, registry, ability) -> None:
    """Put out a permanent carrying enough counters for a
    `remove_counters_from_among` cost.

    Tekuthal removes "three counters from among other artifacts, creatures, and
    planeswalkers you control", and the generic board carries no counters at
    all. One permanent of the selector's first type with that many +1/+1
    counters pays it, which is all the sandbox needs -- the split is the
    payer's and `test_remove_counters_from_among.py` pins it.
    """
    cost = ability.cost
    spec = getattr(cost, "remove_counters_from_among", None) if cost else None
    if not spec:
        return
    wanted = int(spec.get("count", 1) or 1)
    types = spec.get("types") or (spec.get("any_types") or ["Creature"])[:1]
    match = _fodder_for(registry, {"types": list(types)})
    if match is None:
        return
    fodder = new_object(game.state, match.id, owner=0, zone=Zone.BATTLEFIELD)
    fodder.counters[PLUS_ONE] = wanted
    game.state.battlefield.append(fodder.oid)


def _satisfy_the_activation_condition(game: Game, registry, ability, oid: int) -> None:
    """Put out whatever an "activate only if..." clause is counting.

    Sixth of the same family, and added for the same reason as the other five:
    the sandbox's job is that "not activatable" only ever means the ability is
    broken. Bloodline Keeper says "activate only if you control five or more
    Vampires" and the generic board has none.

    Deliberately dumb, exactly as `_provide_the_target` is. It reads three shapes
    -- ``{"cmp": ">=", "left": {"count": <selector>}, "right": {"const": n}}``,
    which it satisfies by adding permanents; the same comparison over
    ``life_lost_this_turn``, which it satisfies by taking the life; a per-player
    ``max_count_of``, which it satisfies by stocking one opponent's board;
    ``power_of`` the source itself, which it satisfies with +1/+1 counters;
    ``spells_cast_this_turn``, which it satisfies by emitting the cast events the
    ledger folds; and delirium's ``distinct`` over a graveyard, which it
    satisfies by putting cards of that many different types into one. A helper clever enough to solve an arbitrary condition would be
    a second implementation of `evaluate` living in the tests, and the first thing
    it would hide is a bug in the first.
    """
    condition = getattr(ability, "activation_condition", None)
    if isinstance(condition, dict) and "exists" in condition:
        _satisfy_an_exists(game, registry, condition["exists"])
        return
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

    # "Activate only if Kitsa's power is 3 or greater." A 1/3 printed under a
    # condition about its own power reports as broken on a board that simply
    # never grew it. Counters rather than a pump, because a counter is a
    # pipeline input the characteristics layer reads the same way the real card
    # would have grown -- and `chars` is what the condition asks, so a card
    # naming the wrong characteristic still fails.
    # "Activate only if this enchantment has four or more quest counters on it"
    # -- Luminarch Ascension. Eleventh of the family, and the first activation
    # condition to count counters on its own source rather than permanents on
    # the board. `_pay_the_counters` stocks counters a *cost* removes; this is
    # the same stocking for a condition that only reads them, and the two are
    # separate because a card can have either without the other.
    #
    # Written onto the object rather than through `add_counters` deliberately:
    # a quest counter arriving is an event some other card could react to, and
    # this helper is arranging a position rather than playing a turn.
    if "counters_on" in left:
        spec = left["counters_on"] or {}
        objects = spec.get("objects") or {}
        if not objects.get("self_only"):
            return
        kind = str(spec.get("counter", PLUS_ONE))
        game.state.objects[oid].counters[kind] = int(right["const"])
        game.state.bump_chars()
        return

    if "power_of" in left:
        want = int(right["const"])
        for _ in range(max(0, want - (chars(game.state, oid).power or 0))):
            add_counters(game.state, oid, "+1/+1", 1)
        game.state.bump_chars()
        return

    # "…only if you've cast three or more instant and/or sorcery spells this
    # turn" -- Urabrask. Ninth of the family, and the third that satisfies a
    # clause by *doing* the thing rather than by arranging the board.
    #
    # `state.emit` rather than a write to `TurnLedger`: `_tally` folds the event
    # into the ledger and `emit` records without scanning the trigger bus, so
    # this writes the tally through exactly the code a real cast writes it
    # through -- a card naming the wrong tally still fails -- while not
    # cascading a sandbox full of cast triggers off a spell nobody cast.
    if "spells_cast_this_turn" in left:
        spec = left["spells_cast_this_turn"]
        filt = spec.get("filter") if isinstance(spec, dict) else None
        match = _fodder_for(registry, {"types": ["Instant"]} if filt else {})
        if match is None:
            return
        for _ in range(int(right["const"])):
            game.state.emit(EventType.SPELL_CAST, player=0, card=match.id)
        return

    # Delirium -- "activate only if there are four or more card types among cards
    # in your graveyard" (Shifting Woodland). Twelfth of the family, and the
    # first condition that counts *distinct values* rather than objects, so
    # stocking one graveyard four times over would satisfy nothing: the helper
    # has to find four cards of four different types.
    #
    # Real cards from the registry rather than a synthetic one, for the reason
    # every other member of the family uses `_fodder_for`: the condition reads
    # printed types through `state.card_of`, so a card naming the wrong thing
    # still fails.
    if "distinct" in left:
        spec = left["distinct"] or {}
        if str(spec.get("of", "")) != "card_type":
            return
        objects = spec.get("objects") or {}
        zone = Zone.GRAVEYARD if objects.get("zone") == "graveyard" else None
        if zone is None:
            return
        wanted = int(right["const"])
        seen: set[str] = set()
        for card_type in ("Creature", "Instant", "Sorcery", "Artifact", "Enchantment", "Land"):
            if len(seen) >= wanted:
                break
            match = _fodder_for(registry, {"types": [card_type]})
            if match is None or card_type in seen:
                continue
            seen.add(card_type)
            card = new_object(game.state, match.id, owner=0, zone=zone)
            game.state.players[0].zone_list(zone).append(card.oid)
        return

    if "count" not in left:
        return
    selector = left["count"]
    if selector.get("zone", "battlefield") != "battlefield":
        return
    wanted = int(right["const"])
    match = _fodder_for(registry, selector, wanted)
    if match is None:
        return
    for _ in range(wanted):
        fodder = new_object(game.state, match.id, owner=0, zone=Zone.BATTLEFIELD)
        game.state.battlefield.append(fodder.oid)


def _satisfy_an_exists(game: Game, registry, selector: dict) -> None:
    """"Activate only if you control a creature with power 4 or greater" --
    Bonders' Enclave.

    Thirteenth of the family, and the first activation condition written as a
    bare ``exists`` rather than a ``cmp`` over a count. Fanatic of Rhonas wears
    the same clause, but on a mana ability, which this test never activates.

    It puts out one real card from the pool whose *printed* power clears the
    floor, rather than pumping a sandbox creature: the condition reads `chars`,
    so a card that names the wrong characteristic still fails. Only "you control
    it on the battlefield" and a ``>=`` power floor over a constant are read; any
    other shape is left alone and the ability reports as unusable, which is the
    honest answer when the harness cannot build the position.
    """
    if selector.get("controller", "you") != "you":
        return
    if selector.get("zone", "battlefield") != "battlefield":
        return
    min_power = None
    power = selector.get("power")
    if power is not None:
        value = power.get("value") if isinstance(power, dict) else None
        if power.get("op") != ">=" or not isinstance(value, dict) or "const" not in value:
            return
        min_power = int(value["const"])
    match = _fodder_for(registry, selector, min_power=min_power)
    if match is None:
        return
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
    wanted = max(1, count)
    match = _fodder_for(registry, {"types": spec.get("types") or ["Creature"]}, wanted)
    if match is None:
        return
    create_token(game.state, match.id, 0, wanted)


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


def _fodder_for(registry, selector: dict, count: int = 1, min_power: int | None = None):
    """The first card in the pool matching a counting filter's types.

    Shared by every helper that satisfies a requirement by putting permanents
    out, so "what counts as one of those" cannot drift between them.

    **A legendary card is passed over when more than one copy is needed.** The
    pool is searched in id order, so the first Advisor is
    `bruvac_the_grandiloquent` -- and four copies of a legendary creature is
    *one* copy once the legend rule (704.5j) has been applied at the next
    state-based check. That reported Persistent Petitioners' "Tap four untapped
    Advisors you control" as unusable: a working card, failing on a board the
    sandbox had quietly emptied.

    A preference rather than a filter, with the legendary card still taken when
    it is the only match: a board one short is a more honest failure than a
    board with nothing on it at all, and it fails loudly either way.
    """
    subtypes = {str(s) for s in selector.get("subtypes") or []}
    types = {str(t) for t in selector.get("types") or ["Creature"]}
    matches = [
        c
        for c in sorted(registry, key=lambda c: c.id)
        if not c.is_token
        and c.front_face is None
        and types <= set(c.types)
        and (not subtypes or subtypes & set(c.subtypes))
        and (min_power is None or (c.power is not None and c.power >= min_power))
    ]
    if not matches:
        return None
    if count > 1:
        return next((c for c in matches if not c.is_legendary), matches[0])
    return matches[0]


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
        # One per seat the specs actually ask for, rather than both always: a
        # second stack item changes what else is legal, and every card in the
        # pool but this one wants the opponent's.
        for spec in ability.targets:
            if spec.kind != "spell":
                continue
            add_dummy_spell(game, 0 if spec.selector.get("controller") == "you" else 1)
        return
    if any(spec.kind == "ability_on_stack" for spec in ability.targets):
        # Peter Parker's Camera -- "Copy target activated or triggered ability you
        # control." The spell branch above, one kind of stack object over: the
        # fodder stocks the battlefield and an ability on the stack is not there,
        # so the Camera was unaimed rather than broken.
        for spec in ability.targets:
            if spec.kind != "ability_on_stack":
                continue
            add_dummy_ability(
                game, registry, 1 if spec.selector.get("controller") == "opponent" else 0
            )
        return
    for spec in ability.targets:
        if spec.kind == "card_in_graveyard":
            # Emry, Lurker of the Loch -- "{T}: Choose target artifact card in
            # your graveyard." The fodder below is stocked onto the
            # *battlefield*, where a card in a graveyard can never be pointed
            # at, so the ability reported as unusable when it was only unaimed.
            # Conditional on the spec asking for it, so no other card's board
            # changes: this is the fourth prop in this family and the first that
            # has to choose a zone.
            _stock_the_graveyard(game, registry, spec)
            continue
        match = _target_fodder(registry, spec)
        if match is None:
            continue
        obj = new_object(game.state, match.id, owner=_seat_for(game, spec), zone=Zone.BATTLEFIELD)
        obj.entered_turn = 0
        # Commander's Plate's "Equip commander {3}" (702.6f) targets only a
        # commander, and the sandbox has none. The flag is set only when the
        # spec asks for it, so every other target stays an ordinary creature.
        if spec.selector.get("is_commander"):
            obj.is_commander = True
        # Gideon Jura's "-2: Destroy target **tapped** creature." Every creature
        # the sandbox holds is untapped, so the ability read as unusable when it
        # was only unaimed. Tapped only when the spec asks, like the flag above.
        if spec.selector.get("tapped"):
            obj.tapped = True
        game.state.battlefield.append(obj.oid)
    game.state.bump_chars()


def _stock_the_graveyard(game: Game, registry, spec) -> None:
    """Put a card the spec accepts into the graveyard it names.

    Emry, Lurker of the Loch is the witness: "{T}: Choose target **artifact
    card in your graveyard**." The sandbox's graveyard holds two creature
    cards, so an artifact-typed spec has nothing to point at.

    Deliberately dumb like the rest of this family: the selector is read only
    far enough to pick a card and a seat -- `types`, and whose graveyard --
    never to decide whether the result is a legal target. That answer stays
    `enumerate_target_tuples`', so no second copy of `matches` moves into the
    tests.
    """
    selector = spec.selector
    types = {str(t) for t in selector.get("types") or []}
    match = next(
        (
            c
            for c in sorted(registry, key=lambda c: c.id)
            if not c.is_token and c.front_face is None and types <= set(c.types)
        ),
        None,
    )
    if match is None:
        return
    # "your graveyard" is the default; `player`/`controller` is the only other
    # thing a shipped spec says, and it is read the way `_seat_for` reads it.
    owner = 0
    if selector.get("player") == "opponent" or selector.get("controller") == "opponent":
        owner = next((p.pid for p in game.state.players if p.pid != 0), 0)
    obj = new_object(game.state, match.id, owner=owner, zone=Zone.GRAVEYARD)
    game.state.players[owner].graveyard.append(obj.oid)


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
    # "Target artifact **or** enchantment you control" -- Adagia, Windswept
    # Bastion's 12+ line -- is `any_types`, and read as nothing it defaulted to
    # a creature neither half accepts. The first listed type is one it does.
    either = [str(t) for t in selector.get("any_types") or []]
    types = {str(t) for t in selector.get("types") or either[:1] or ["Creature"]}
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

    if _walk_to_declare_attackers(game):
        _declare_them(game, [attacker.oid])


def _walk_to_declare_attackers(game: Game) -> bool:
    """Pass priority until the declare-attackers decision is on the table.

    `_answer` is deliberately not reused: it declines combat outright, which is
    the whole thing being undone here. Shared by the two helpers that need the
    game in combat -- one to point an ability at an attacker, one to satisfy a
    clause counting how many attacked.
    """
    for _ in range(40):
        decision = game.pending()
        if decision is None or game.over:
            return False
        if decision.kind is DecisionKind.DECLARE_ATTACKERS:
            return True
        if decision.kind is not DecisionKind.PRIORITY:
            return False
        passing = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.PASS), None
        )
        if passing is None:
            return False
        game.apply(passing)
    return False


def _declare_them(game: Game, oids: list[int]) -> None:
    """Declare each oid as an attacker, then close the declaration.

    An oid the engine will not accept is skipped rather than asserted on: this
    is a helper arranging a position, and "could not build the board" has to
    stay distinguishable from "the ability is broken". The caller's own
    assertion is what reports the failure.
    """
    for oid in oids:
        add = next(
            (
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER and a.source == oid
            ),
            None,
        )
        if add is not None:
            game.apply(add)
    finish = next(
        (a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION),
        None,
    )
    if finish is not None:
        game.apply(finish)


def _satisfy_the_attack_count(game: Game, registry, ability) -> None:
    """"Activate only if you attacked with two or more creatures this turn."

    Tenth of the family, and the third that has to satisfy a clause by *doing*
    the thing rather than by arranging the board -- `TurnLedger` records
    creatures **declared as attackers**, so stocking the battlefield the way the
    `count` branch does satisfies nothing, exactly as it satisfies nothing for
    `permanents_entered_this_turn`.

    Minas Tirith is the witness and is the first card in the pool to print this
    clause as an *activation* condition. Windbrisk Heights had carried the same
    value expression for as long, but inside an `if` in the ability's effects --
    so the ability was always activatable and merely did nothing, and the shape
    that gates activation itself had never been exercised.

    Runs after `_provide_the_attacker` and reuses its walk, so a card wanting
    both an attacking target and an attack count gets one trip to combat rather
    than two. Creatures are made rather than borrowed from the board: the
    sandbox's own two are props whose printed text is not this test's business,
    and one of them being unable to attack would read as the ability failing.
    """
    condition = getattr(ability, "activation_condition", None)
    if not isinstance(condition, dict) or "cmp" not in condition:
        return
    left, right = condition.get("left") or {}, condition.get("right") or {}
    if "attackers_this_turn" not in left or "const" not in right:
        return
    if str(left["attackers_this_turn"]) != "you":
        return
    wanted = int(right["const"])
    if wanted <= 0:
        return

    match = next(
        (
            c
            for c in sorted(registry, key=lambda c: c.id)
            if not c.is_token and c.is_creature and not c.keywords
        ),
        None,
    )
    if match is None:
        return
    oids: list[int] = []
    for _ in range(wanted):
        attacker = new_object(game.state, match.id, owner=0, zone=Zone.BATTLEFIELD)
        attacker.entered_turn = 0
        game.state.battlefield.append(attacker.oid)
        oids.append(attacker.oid)
    game.state.bump_chars()
    if _walk_to_declare_attackers(game):
        _declare_them(game, oids)


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

