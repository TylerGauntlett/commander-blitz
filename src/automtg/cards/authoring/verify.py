"""The six gates a candidate card must clear before it is written.

The point of this module is stated once, here, because everything else in the
package exists to feed it:

    ``compile_card`` validates **vocabulary**, not **meaning**.

A card whose ops all exist and whose selectors all parse can still say "draw a
card" and gain life instead. It loads, it plays, it never raises -- and nothing
on the board tells anybody it is wrong. ``docs/card-dsl.md`` is built around
refusing to ship "a card that looks implemented and does nothing"; a card that
looks implemented and does something *subtly different* is worse, because the
inert one at least fails visibly the first time somebody counts on it.

So a generator is never trusted. Every candidate has to stand up in a real
position and demonstrate what it does:

1. **schema**     -- the JSON is a ``CardModel``
2. **compile**    -- ops, selectors, triggers, keywords, static constraints
3. **residual**   -- the printed text is *fully* consumed, nothing left over
4. **playable**   -- it can be cast in a sandbox and resolves to the right zone
5. **behaviour**  -- a non-empty expectation that actually holds
6. **registry**   -- the whole pool still loads with it in

Gate 5 is the one that separates "the model believes this is Divination" from
"the engine demonstrably drew two cards", and it is why a card and its
expectation are authored together and rejected together.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from automtg.engine.actions import PendingDecision
from automtg.engine.carddef import CardDef
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.errors import AutoMtgError, DslError
from automtg.engine.game import Game
from automtg.engine.mana import ManaCost
from automtg.engine.sandbox import GameBuilder
from automtg.engine.stack import push_spell
from automtg.engine.state import new_object

from ..loader import compile_card
from ..registry import CardRegistry
from ..schema import CardModel

#: A mana base deep enough to cast anything, so "not playable" never means
#: "could not pay for it".  Mirrors ``tests/cards/test_every_card_works.py``.
MANA_BASE = ["plains"] * 6 + ["island"] * 6 + ["swamp"] * 6 + ["mountain"] * 6 + ["forest"] * 6

#: Things for targeted effects to point at, described by *role* rather than by
#: card id.  ``tests/cards/test_every_card_works.py`` names `t_bear` and friends
#: because it runs against the test registry; this has to work against whatever
#: pool the caller hands it, and a hardcoded id would tie the authoring pipeline
#: to test fixtures that are not shipped.
_ROLES: dict[str, Any] = {
    "creature": lambda c: c.is_creature and not c.is_token,
    "flier": lambda c: c.is_creature and not c.is_token and "flying" in c.keywords,
    "artifact": lambda c: "Artifact" in c.types and not c.is_token and not c.is_land,
    "enchantment": lambda c: "Enchantment" in c.types and not c.is_token,
    #: Something for "counter target **noncreature** spell" to point at. Targets
    #: none of its own, because the sandbox may let it resolve: a dummy that
    #: wants a target it was never given is an error inside the harness rather
    #: than a verdict about the card.
    "noncreature_spell": lambda c: (c.is_instant or c.is_sorcery) and not c.targets,
    #: Something for "counter target spell **with {X} in its mana cost**" to
    #: point at -- Frontline Medic. The role the `noncreature_spell` docstring
    #: below said the next unrepresented selector would need, added rather than
    #: the gate relaxed. Targetless for the same reason that one is.
    "x_spell": lambda c: (c.is_instant or c.is_sorcery)
    and not c.targets
    and c.mana_cost.x_count > 0,
    #: Something for "destroy target **legendary** permanent" to point at --
    #: Commander Sofia Daguerre. :func:`_play_once` carries the argument for
    #: why this is a prop and not a carve-out; the two clauses of the predicate
    #: are:
    #:
    #: - **legendary**, which is the shape the sandbox was missing;
    #: - **inert** -- nothing on it triggers and nothing on it can be activated
    #:   -- because a prop exists to be pointed at, and one that *acts* folds
    #:   its own behaviour into every card's verdict. Bident of Thassa is the
    #:   worked example: its `{1}{U}, {T}:` is payable off the Forest and Island
    #:   the opponent is dealt, and a payable non-mana activated ability stops
    #:   `_should_auto_pass`, so the opponent takes a real priority window while
    #:   the card under test is still on the stack, `drive` returns at
    #:   `PRIORITY`, and *every* card fails gate 4 with "never left the stack".
    #:   That is measured, not feared.
    #:
    #: A quiet prop is not a nicety either. The alphabetically first legendary
    #: creature is a 5/5 Leviathan, and swapping *that* one in moved three
    #: authored verdicts -- Whelming Wave exempts Leviathans, and two mass
    #: bounces are capped on power. Every prop is load-bearing for somebody, so
    #: the check on a change here is `tests/cards/test_auto_cards.py`, which
    #: re-runs all six gates over every authored card; the pick below leaves all
    #: of them passing.
    #:
    #: It fills the opponent's **creature** slot rather than being appended, so
    #: the boards stay 32 and 6 and every authored `battlefield_count` and
    #: `opponent_battlefield_count` still reads what it read when it was
    #: written. Nothing is lost by the swap: the prop is still a creature, and
    #: the flier keeps the board a *nonlegendary* creature for "destroy target
    #: nonlegendary creature" to find.
    #: Something for "return target creature card **with mana value 3 or less**"
    #: to point at -- Helping Hand, and every other cheap reanimation spell.
    #: The graveyard's two props were both mana value 5 (`acidic_slime` and
    #: `air_elemental`), so a printed cost ceiling of 3 left the spell with no
    #: legal target at all: gate 4 reported "not playable in the sandbox" and
    #: the only ways to pass were to drop the mana-value clause or to make the
    #: target `optional` when the card does not print "up to one" -- both of
    #: which describe a *different card*. The prop was missing, so the prop was
    #: added rather than the gate relaxed, the same call `legendary_creature`
    #: records above.
    #:
    #: Three clauses, each load-bearing:
    #:
    #: - **mana value 3 or less**, the shape that was absent;
    #: - **inert**, for the reason `legendary_creature` gives at length -- a
    #:   prop that acts folds its own behaviour into every card's verdict, and
    #:   the incumbent `acidic_slime` is not inert: reanimating it destroyed one
    #:   of the opponent's permanents, so any card that returned it had that
    #:   destruction baked into its expectation;
    #: - **nonlegendary**, because the worker brief promises the opponent's
    #:   creature is the position's one and only legendary permanent, and a
    #:   legend sitting in the graveyard breaks that promise the moment a
    #:   reanimation spell puts it onto the battlefield.
    "small_creature": lambda c: (
        c.is_creature
        and not c.is_token
        and "Legendary" not in c.supertypes
        and c.mana_value <= 3
        and not any(a.is_activated or a.is_triggered for a in c.abilities)
    ),
    "legendary_creature": lambda c: (
        c.is_creature
        and not c.is_token
        and "Legendary" in c.supertypes
        and not any(a.is_activated or a.is_triggered for a in c.abilities)
    ),
}

#: Which roles each zone gets.  The opponent's board carries one of each broad
#: type, so "destroy target artifact" and "return target creature" both find
#: something to point at -- and its creature is the board's one **legendary**
#: permanent, so "target legendary permanent" finds something that is not the
#: card under test.  Four roles, still, and a Forest and an Island: the counts
#: are 32 and 6 and every authored expectation was written against them.
OWN_BOARD_ROLES = ("creature", "creature")
OPPONENT_BOARD_ROLES = ("legendary_creature", "flier", "artifact", "enchantment")
OWN_GRAVEYARD_ROLES = ("small_creature", "flier")
BASIC_LANDS = ("forest", "island", "swamp", "mountain", "plains")


def _props(registry: CardRegistry, roles: tuple[str, ...]) -> list[str]:
    """Concrete card ids for a list of roles, skipping any the pool cannot fill.

    Sorted before picking so the sandbox is identical run to run -- an unstable
    board makes a verdict unreproducible, which is the one thing a gate must
    never be.
    """
    out: list[str] = []
    for role in roles:
        match = _ROLES[role]
        pick = next((c.id for c in sorted(registry, key=lambda c: c.id) if match(c)), None)
        if pick is not None:
            out.append(pick)
    return out

GATES = ("schema", "compile", "residual", "playable", "behaviour", "registry")


@dataclass
class Verdict:
    """Why a card was accepted or rejected, gate by gate."""

    card_id: str
    passed: list[str] = field(default_factory=list)
    failed_gate: str | None = None
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.failed_gate is None

    def __str__(self) -> str:
        if self.ok:
            return f"{self.card_id}: passed all {len(GATES)} gates"
        return f"{self.card_id}: FAILED at {self.failed_gate} -- {self.reason}"


# ----------------------------------------------------------------------
# the sandbox
# ----------------------------------------------------------------------


def build_sandbox(registry: CardRegistry, card_id: str, *, in_hand: bool = True) -> Game:
    """A fixed position with the card under test in hand."""
    builder = GameBuilder(registry, players=2, seed=1)
    builder.battlefield(0, MANA_BASE)
    builder.battlefield(0, _props(registry, OWN_BOARD_ROLES))
    builder.battlefield(1, [*_props(registry, OPPONENT_BOARD_ROLES), "forest", "island"])
    builder.graveyard(0, _props(registry, OWN_GRAVEYARD_ROLES))
    # Forty cards, and the **second** one is deliberately not a land. The pile
    # used to be forty basic lands, which made Cultivator Colossus -- "put a
    # land card from your hand onto the battlefield, draw a card, and repeat
    # this process" -- draw a land every iteration and deck the player, once the
    # hand gained a spare land for it to start on. One nonland stops that loop.
    #
    # Second rather than first, and the position is the whole point: Coiling
    # Oracle and Through the Forest Gate *reveal the top card* and branch on
    # whether it is a land, so a nonland on top would quietly retire the branch
    # those cards are about. Index 1 is deep enough that only a card drawing
    # twice ever sees it, and no expectation asserts what a drawn card *is*.
    library = list(BASIC_LANDS) * 8
    stopper = _props(registry, ("noncreature_spell",))
    if stopper:
        library[1] = stopper[0]
    builder.library(0, library)
    builder.library(1, ["forest", "island"] * 10)
    if in_hand:
        # A spare card beside the one under test, and it is load-bearing.
        # 601.2a moves a spell to the stack before its costs are paid, so a card
        # can never discard *itself* to pay its own additional cost -- and a
        # hand holding only the card under test therefore leaves every mandatory
        # "as an additional cost, discard a card" with no fodder and unplayable
        # at gate 4. Big Score and Laughing Mad are the witnesses.
        #
        # The prop is added rather than the gate relaxed, the same call
        # `legendary_creature` and `small_creature` record. It is a basic land
        # so that it does nothing on its own: nothing triggers off it, it is
        # never cast, and `find_play` looks for the card under test by id rather
        # than taking the first action.
        #
        # Every authored `hand_size` counts it, which is why they read one
        # higher than the printed spell would suggest.
        #
        # It has to be a **land**. A castable spare is not inert: with an
        # instant in hand the player keeps priority while the card under test is
        # on the stack, `drive` returns at PRIORITY, and 169 cards fail gate 4
        # with "never left the stack" -- the same trap `legendary_creature`
        # records about a payable activated ability, one zone over. A land is
        # played by a *special action*, so it offers something to do without
        # ever holding the stack open.
        #
        # Having a legal action at all is itself a fidelity gain: it stops the
        # position auto-passing to end of turn, and the brief promises
        # "measurement happens before cleanup, so until-end-of-turn effects are
        # still live". Before this, Call for Aid was measured *after* its
        # control effect had worn off.
        builder.hand(0, [card_id, "forest"])
    return builder.build(advance=False)


def add_dummy_spell(game: Game, registry: CardRegistry) -> None:
    """Put spells on the stack so a counterspell has something to target.

    Picked from the pool by role, like the board props: naming a test-only card
    here tied the authoring pipeline to fixtures that are not shipped, and every
    counterspell then failed with "unknown card id".

    **One of each broad shape**, for the same reason the opponent's board carries
    one of each type: a `kind: "spell"` target spec filters with the full
    selector language, so a lone creature spell makes "counter target
    **noncreature** spell" unplayable in the sandbox and fails Negate at gate 4.
    A card whose selector no dummy here satisfies -- "target spell with {X} in
    its mana cost", once something is authored with it -- will fail the same way,
    which is the harness reporting an unrepresented shape rather than the card
    being wrong. Add the role; do not relax the gate. `x_spell` is that role,
    added exactly as this paragraph asked: Frontline Medic put the selector into
    the pool, and the "Counter target spell with {X} in its mana cost" *instant*
    behind it in the queue is the first card that will reach this list with it.
    """
    for pick in _props(registry, ("creature", "noncreature_spell", "x_spell")):
        obj = new_object(game.state, pick, owner=1, zone=Zone.HAND)
        game.state.players[1].hand.append(obj.oid)
        push_spell(game.state, obj.oid, 1)


def drive(game: Game, limit: int = 60) -> None:
    """Answer every decision with a real choice until the card has finished.

    **Stops at the turn boundary.** Letting the sandbox roll into the next turn
    crosses the cleanup step, which wipes every until-end-of-turn effect -- so a
    pump spell or a keyword grant would be measured after the thing it did had
    already worn off, and gate 5 would quietly pass whatever the card actually
    did. That is the exact failure this harness exists to catch, hidden inside
    the harness itself.
    """
    turn = game.state.turn
    for _ in range(limit):
        if game.over or game.state.turn != turn:
            return
        decision = game.pending()
        if decision is None:
            return
        # Priority means the card has finished resolving. Combat means the turn
        # has moved on to something that is not this card -- and answering it is
        # what used to march the sandbox into the next turn.
        if decision.kind in _NOT_OUR_BUSINESS:
            return
        game.apply(_answer(game, decision))


#: Decisions that mean the card under test is done with. Answering these walks
#: the game forward through cleanup, which wipes until-end-of-turn effects.
_NOT_OUR_BUSINESS = frozenset(
    {
        DecisionKind.PRIORITY,
        DecisionKind.DECLARE_ATTACKERS,
        DecisionKind.DECLARE_BLOCKERS,
    }
)


def _answer(game: Game, decision: PendingDecision):
    actions = game.legal_actions()
    if not actions:
        raise AutoMtgError(f"no legal action for {decision.kind.value}")

    # Decline combat: this is about the card, and letting the sandbox attack
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
        # ...but not an X that ends the game. Toxic Deluge's X is paid in
        # **life**, and 118.4 puts the whole life total on offer, so the maximum
        # is suicide: the player hits 0, loses to a state-based action, and the
        # spell never resolves -- gate 4 reports "never left the stack" about a
        # card that is perfectly fine. A harness that kills the player observes
        # nothing.
        #
        # Provably inert for every X that is paid in mana: this sandbox has 30
        # lands against 40 life, so a mana ceiling never reaches the cap.
        pid = decision.player
        life = game.state.players[pid].life if pid is not None else 0
        alive = [a for a in choices if (a.choice or 0) < life]
        if alive:
            return max(alive, key=lambda a: a.choice or 0)
        if choices:
            return max(choices, key=lambda a: a.choice or 0)

    # Otherwise take a real choice, so an optional effect is actually exercised
    # rather than declined into a no-op that would pass any assertion.
    for action in actions:
        if action.kind in (ActionKind.CHOOSE, ActionKind.YES):
            return action
    return actions[0]


def find_play(
    game: Game,
    card_id: str,
    *,
    kicked: bool = False,
    multikicked: bool = False,
    gifted: bool = False,
):
    """The action that plays this card, optionally the kicked way.

    A kicker card is offered twice, and the two are different cards in every way
    that matters -- so which one is being asked for has to be said out loud
    rather than settled by whichever legality happens to list first.

    ``multikicked`` is the same request for the cost that is paid *any number of
    times*: legality offers one cast line per number, ascending from the free
    one, so taking the first match would always be the unkicked spell. It asks
    for the most the sandbox can pay -- the same "maximum, because zero measures
    nothing" that `_answer` applies to `CHOOSE_X`, and the same reason
    `_play_and_check` measures a kicker card kicked.

    ``gifted`` is that same request for the **gift** promise (702.164a), and it
    is the reason gift could not be smuggled in through the optional-additional
    -cost slot. `_additional_ceiling` offers times 0 and 1 at the same price for
    a cost of `{}`, and this function picks its line with `kicked`, which such a
    card does not set -- so the free line always won, the promised branch never
    ran once, and the card sailed through all six gates having done nothing.
    A flag legality can offer needs a flag the harness can ask for, or gate 5
    measures the half of the card that was already going to work.

    Unlike `kicked` it names a **seat** rather than a price, so the ask is "any
    promised line" and the first is taken: which opponent is promised is a
    choice between equals in a sandbox with one of them, and legality's order is
    stable.
    """
    matches = []
    for action in game.legal_actions():
        if action.kind not in (ActionKind.CAST, ActionKind.PLAY_LAND):
            continue
        if action.kind is ActionKind.CAST and action.kicked != kicked:
            continue
        if action.kind is ActionKind.CAST and (action.gift_to is not None) != gifted:
            continue
        obj = game.state.objects.get(action.source)
        if obj is not None and obj.def_id == card_id and obj.zone is Zone.HAND:
            matches.append(action)
    if not matches:
        return None
    if multikicked:
        # `max` over a stable list, so ties keep legality's order.
        return max(matches, key=lambda a: a.additional_times)
    # The **front** face, whenever one is offered. A modal DFC is offered twice
    # -- Malakir Rebirth as a cast and Malakir Mire as a land drop -- and the
    # payload under test describes the front: its `oracle_text`, its `mana_cost`
    # and its `spell_effects` are the front's. Exercising the back would judge
    # an Instant by where a Land ended up, which is a gate failure no expectation
    # could ever answer.
    #
    # `_land_actions` runs before `_cast_actions`, so without this the land line
    # simply wins on ordering -- the same kind of accident `kicked` already
    # disambiguates for a spell offered twice.
    return next((a for a in matches if not a.second_face), matches[0])


# ----------------------------------------------------------------------
# expectations
# ----------------------------------------------------------------------

#: What an expectation may assert.  Deliberately small and observable: every one
#: is a number a person can read off the board, so an authored expectation can be
#: checked by eye against the printed card.
EXPECTATION_KEYS = (
    "life",
    "hand_size",
    "library_size",
    "graveyard_size",
    "counters",
    "tokens",
    "battlefield_count",
    "opponent_battlefield_count",
    "zone",
    "granted",
    "target_pt_delta",
)


def check_expectation(
    game: Game,
    card_id: str,
    oid: int,
    expectation: dict,
    *,
    target_pt_before: tuple[int, int] | None = None,
    target_oid: int | None = None,
) -> list[str]:
    """Every way the position disagrees with what the card was supposed to do."""
    state = game.state
    problems: list[str] = []

    def compare(what: str, actual: Any, wanted: Any) -> None:
        if actual != wanted:
            problems.append(f"{what} is {actual}, expected {wanted}")

    for key, read in (
        ("life", lambda p: state.players[p].life),
        ("hand_size", lambda p: len(state.players[p].hand)),
        ("library_size", lambda p: len(state.players[p].library)),
        ("graveyard_size", lambda p: len(state.players[p].graveyard)),
    ):
        for pid, value in (expectation.get(key) or {}).items():
            compare(f"player {pid} {key}", read(int(pid)), value)

    if "counters" in expectation:
        kind = expectation["counters"]["kind"]
        compare(
            f"{kind} counters", state.objects[oid].counter(kind), expectation["counters"]["amount"]
        )

    if "tokens" in expectation:
        token_id = expectation["tokens"]["id"]
        made = [
            o for o in state.battlefield_objects(0) if state.objects[o.oid].def_id == token_id
        ]
        compare(f"{token_id} tokens", len(made), expectation["tokens"]["count"])

    if "battlefield_count" in expectation:
        compare(
            "your battlefield", len(state.battlefield_objects(0)), expectation["battlefield_count"]
        )
    if "opponent_battlefield_count" in expectation:
        compare(
            "opponent battlefield",
            len(state.battlefield_objects(1)),
            expectation["opponent_battlefield_count"],
        )
    if "zone" in expectation:
        # A list means "any of these", for a card whose destination is genuinely
        # conditional: Dead Weight kills what it enchants and is then binned by
        # state-based actions, so battlefield and graveyard are both correct
        # outcomes and pinning one would reject the card for working.
        wanted_zone = expectation["zone"]
        actual = state.objects[oid].zone.value
        if isinstance(wanted_zone, list):
            if actual not in wanted_zone:
                problems.append(f"the card's zone is {actual}, expected one of {wanted_zone}")
        else:
            compare("the card's zone", actual, wanted_zone)

    if "target_pt_delta" in expectation:
        # "+3/+3 until end of turn" is the single most common thing a card does
        # that no count on the board can see. Measured as a *delta* on the
        # spell's own target, because the sandbox's props come from whatever pool
        # the caller hands it and their printed P/T is not knowable here -- and
        # because the delta is exactly the number printed on the card.
        wanted = expectation["target_pt_delta"]
        if target_oid is None or target_pt_before is None:
            problems.append("target_pt_delta was asserted but the spell targeted nothing")
        else:
            from automtg.engine.characteristics import chars

            now = chars(state, target_oid)
            compare("target power delta", now.power - target_pt_before[0], wanted.get("power", 0))
            compare(
                "target toughness delta",
                now.toughness - target_pt_before[1],
                wanted.get("toughness", 0),
            )

    if "granted" in expectation:
        # "Permanents you control gain hexproof", "Equipped creature has haste".
        # Without this, a card whose whole job is granting a keyword had nothing
        # countable to assert and fell back to "it resolved" -- a gate that
        # passes whatever the card actually did.
        from automtg.engine.characteristics import chars

        wanted = set(expectation["granted"].get("keywords", []))
        how_many = expectation["granted"].get("count", 1)
        got = sum(
            1
            for obj in state.battlefield_objects(0)
            if wanted <= {str(k) for k in chars(state, obj.oid).keywords}
        )
        compare(f"permanents of yours with {sorted(wanted)}", got, how_many)

    return problems


# ----------------------------------------------------------------------
# the gates
# ----------------------------------------------------------------------


def verify(
    payload: dict,
    expectation: dict,
    registry: CardRegistry,
    *,
    oracle_text: str | None = None,
    supersedes: bool = False,
    companions: Sequence[dict] | None = None,
) -> Verdict:
    """Run every gate over one candidate.

    ``registry`` is the pool the card will join, minus the card itself; it
    supplies the sandbox's lands, dummy creatures and token definitions.

    ``supersedes`` says this card is a *replacement* for one already in the pool
    under the same id, so the duplicate-id gate should stand aside. Only
    ``--collect --supersede`` passes it, and only after the caller has committed
    to deleting the incumbent -- see ``scripts/author_cards.py``.
    """
    card_id = str(payload.get("id") or "<no id>")
    verdict = Verdict(card_id=card_id)

    # -- 1. schema ------------------------------------------------------
    try:
        model = CardModel.model_validate(payload)
    except Exception as exc:
        verdict.failed_gate = "schema"
        verdict.reason = str(exc).split("\n")[0]
        return verdict
    verdict.passed.append("schema")

    # -- 2. compile -----------------------------------------------------
    try:
        card = compile_card(model)
    except AutoMtgError as exc:
        verdict.failed_gate = "compile"
        verdict.reason = str(exc)
        return verdict
    verdict.passed.append("compile")

    # -- 3. residual ----------------------------------------------------
    leftover = residual_text(card, oracle_text if oracle_text is not None else model.oracle_text)
    if leftover:
        verdict.failed_gate = "residual"
        verdict.reason = f"printed text not represented: {leftover}"
        return verdict
    verdict.passed.append("residual")

    # -- 6 (early) registry ---------------------------------------------
    # Run before the sandbox because the sandbox needs a registry containing the
    # card, and a duplicate id or a dangling token reference would otherwise
    # surface as a confusing failure inside gate 4.
    if card.id in registry and not supersedes:
        # A dict merge would have *replaced* the existing card, so a machine
        # could silently overwrite a hand-written one and every deck referencing
        # that id would quietly change. `CardRegistry.from_paths` raises on this
        # at load time; the gate has to raise on it at authoring time.
        #
        # `supersedes` is the one way past this, and it is not a loophole: the
        # replacement still has to clear all six gates, and it is measured
        # against a pool with the incumbent *removed* below, so it cannot lean on
        # the card it is replacing.
        verdict.failed_gate = "registry"
        verdict.reason = f"{card.id!r} is already in the pool"
        return verdict
    existing = {c.id: c for c in registry if c.id != card.id}
    try:
        # A transforming card is **two** entries and one object: the front names
        # its `back_face` and `link_faces` derives the pointer back. The back
        # face has to be in the pool before the front can compile against it, so
        # it arrives here rather than in a second answer file -- one card, one
        # answer, however many faces it has.
        pool = {**existing, card.id: card}
        for extra in companions or ():
            extra_card = compile_card(CardModel.model_validate(extra))
            pool[extra_card.id] = extra_card
        from ..loader import link_faces, validate_token_references

        link_faces(pool)
        merged = CardRegistry(pool)
        validate_token_references({c.id: c for c in merged})
    except AutoMtgError as exc:
        verdict.failed_gate = "registry"
        verdict.reason = str(exc)
        return verdict

    # -- 4. playable ----------------------------------------------------
    try:
        problems = _play_once(merged, card)
    except Exception as exc:  # a raise here is exactly what this gate is for
        verdict.failed_gate = "playable"
        verdict.reason = f"{type(exc).__name__}: {exc}"
        return verdict
    if problems:
        verdict.failed_gate = "playable"
        verdict.reason = "; ".join(problems)
        return verdict
    verdict.passed.append("playable")

    # -- 5. behaviour ---------------------------------------------------
    if not expectation:
        verdict.failed_gate = "behaviour"
        verdict.reason = (
            "no expectation given; a card nobody asserted anything about has not been verified"
        )
        return verdict
    unknown = sorted(set(expectation) - set(EXPECTATION_KEYS))
    if unknown:
        verdict.failed_gate = "behaviour"
        verdict.reason = f"unknown expectation key(s) {unknown}; known: {list(EXPECTATION_KEYS)}"
        return verdict
    try:
        mismatches = _play_and_check(merged, card, expectation)
    except Exception as exc:
        verdict.failed_gate = "behaviour"
        verdict.reason = f"{type(exc).__name__}: {exc}"
        return verdict
    if mismatches:
        verdict.failed_gate = "behaviour"
        verdict.reason = "; ".join(mismatches)
        return verdict
    verdict.passed.append("behaviour")

    verdict.passed.append("registry")
    return verdict


def _play_once(registry: CardRegistry, card: CardDef) -> list[str]:
    """Cast it and assert only that it went where cards of its kind go.

    **Never weaken a gate to make a card pass.** This gate is the one that
    catches a creature which vanishes -- compiles, casts, resolves, and is not
    on the battlefield afterwards -- so the set of zones it allows a permanent
    is the whole of its value, and every widening of that set spends some of it.

    Commander Sofia Daguerre is the card that tested the rule. "When this
    enters, destroy up to one target legendary permanent" may lawfully name
    *her*: she is a Legendary Creature and a legal target for her own trigger.
    Every clause of her compiles, and she failed here with "is a permanent but
    ended in graveyard" -- because the sandbox carried no other legendary
    permanent, so the only legal target the harness could hand the trigger was
    the card under test, which then lawfully destroyed itself.

    Two things were **not** done about that, and saying why is the point of this
    paragraph:

    - The `allowed` set below was not widened to ``{BATTLEFIELD, GRAVEYARD}``
      for permanents whose own trigger can finish them. That reading covers
      almost every removal creature ever printed, so the gate would stop
      distinguishing "Sofia lawfully shot herself" from "this creature is
      simply gone", which is the only thing it is for. The `is_aura` carve-out
      is narrow on purpose -- Dead Weight's -2/-2 kills its own host and state-
      based actions bin the Aura, a *rules consequence with nowhere else to
      go* -- and it is precedent for an argued exception, not for a general one.
    - The card was not written with `exclude_self` on its target selector. That
      passes all six gates and prints a different card: "up to one target
      legendary permanent" includes Sofia, and shipping the exclusion would be
      the vocabulary quietly rewriting the rules text.

    What was actually missing was on the board, not in the gate. The sandbox
    had a creature, a flier, an artifact and an enchantment and **no legendary
    anything**, so "target legendary permanent" was a printed selector the
    position could not represent -- the same absence that made "counter target
    noncreature spell" unplayable here until `noncreature_spell` was added, and
    "target spell with {X} in its mana cost" until `x_spell` was. The house
    answer both times was *add the role, do not relax the gate*, and
    `legendary_creature` is the third time: the opponent's creature slot is
    filled by a legendary creature, so the boards stay 32 and 6 and a
    self-legal removal trigger is exercised against something that is not
    itself.

    A permanent that genuinely vanishes is still rejected here, unchanged.
    ``tests/cards/test_authoring.py`` asserts both halves together, because the
    second is what stops the first from being a weakened gate.
    """
    game, oid, _, _ = _cast(registry, card)
    obj = game.state.objects.get(oid)
    if obj is None:
        return [f"{card.id} vanished entirely"]
    if obj.zone is Zone.STACK:
        return [f"{card.id} never left the stack"]
    # An Aura in the graveyard is not a failure. Dead Weight gives -2/-2, kills
    # what it enchanted, and state-based actions correctly bin it a moment later
    # -- the card working exactly as printed. Rejecting that would throw away
    # every Aura whose own effect can finish its host.
    # The face that was actually played, which is not always the one under test:
    # a modal DFC played as its land half is a permanent even though the card
    # this gate was handed is an Instant. `find_play` prefers the front, so this
    # is the belt to that braces -- and it is the honest question either way,
    # since "did it end up where this kind of card ends up" is about the face
    # that resolved.
    played = game.state.card_of(obj)
    allowed = {Zone.BATTLEFIELD, Zone.GRAVEYARD} if played.is_aura else {Zone.BATTLEFIELD}
    if played.is_permanent and obj.zone not in allowed:
        return [f"{card.id} is a permanent but ended in {obj.zone.value}"]
    if not played.is_permanent and obj.zone is not Zone.GRAVEYARD:
        return [f"{card.id} is a spell but ended in {obj.zone.value}"]
    return []


def _play_and_check(registry: CardRegistry, card: CardDef, expectation: dict) -> list[str]:
    # A kicker card is measured *kicked*. Kicked is the strictly larger claim --
    # it does everything the unkicked spell does and more -- so asserting it
    # covers both halves of the printed text, whereas asserting the cheap mode
    # would let "if this spell was kicked, draw a card" ship doing nothing.
    # Gate 4 still casts it unkicked, so neither line goes unexercised.
    #
    # Multikicker is the same argument for the cost paid any number of times:
    # "return up to X target creature cards, where X is the number of times this
    # was kicked" does nothing at all for X = 0, so a gate that measured the free
    # line would let a card whose entire text is the kicks ship having returned
    # nothing -- and it would have no way to tell that from the card working.
    # Gate 4 casts it unkicked, which is where X = 0 gets exercised.
    #
    # A gift card is measured **promised**, and the argument is kicker's word for
    # word: the promised line is the strictly larger claim, because it does
    # everything the plain line does *plus* hand an opponent something. A gate
    # that took the unpromised line would let a card whose entire gift clause is
    # "they create a tapped 1/1 blue Fish" ship creating nothing, with no way to
    # tell that from the card working -- which is exactly what the measured
    # `additional_cost: {}` hack did before this existed. Gate 4 casts it
    # unpromised, so the "if the gift wasn't promised" half is exercised too.
    game, oid, target_oid, before = _cast(
        registry,
        card,
        kicked=card.kicker is not None,
        multikicked=card.multikicker is not None,
        gifted=card.gift is not None,
    )
    return check_expectation(
        game,
        card.id,
        oid,
        expectation,
        target_oid=target_oid,
        target_pt_before=before,
    )


def _cast(
    registry: CardRegistry,
    card: CardDef,
    *,
    kicked: bool = False,
    multikicked: bool = False,
    gifted: bool = False,
) -> tuple[Game, int, int | None, tuple[int, int] | None]:
    """Cast the card in the sandbox and let it finish.

    Returns the game, the card's own oid, and the first object it targeted along
    with that object's P/T *before* the spell -- the only moment the "before"
    half of a pump can be read.
    """
    game = build_sandbox(registry, card.id)
    # The **card's** targets, deliberately, and not its abilities'. Frontline
    # Medic is the first card whose spell target sits on an activated ability,
    # and widening this to reach it makes the sandbox strictly worse: the dummy
    # spells go on the stack, and a stack with anything on it is not a moment a
    # *creature* can be cast at all (117.1a), so the Medic stops being playable
    # in its own gate. A permanent's ability wants the dummies present later --
    # when it is activated -- which is not a thing this harness does.
    if any(spec.kind == "spell" for spec in card.targets):
        add_dummy_spell(game, registry)
    game._advance()

    action = find_play(
        game, card.id, kicked=kicked, multikicked=multikicked, gifted=gifted
    )
    if action is None:
        offered = [a.label for a in game.legal_actions()][:8]
        raise AutoMtgError(f"{card.id} is not playable in the sandbox; offered: {offered}")
    oid = action.source

    target_oid = next((ref.id for ref in action.targets if ref.kind == "object"), None)
    before: tuple[int, int] | None = None
    if target_oid is not None and target_oid in game.state.objects:
        from automtg.engine.characteristics import chars

        was = chars(game.state, target_oid)
        before = (was.power, was.toughness)

    game.apply(action)
    drive(game)
    return game, oid, target_oid, before


# ----------------------------------------------------------------------
# residual
# ----------------------------------------------------------------------


def residual_text(card: CardDef, oracle_text: str) -> str:
    """Printed sentences the card's abilities do not account for.

    Reuses ``proxy``'s reader so "what is left over" means the same thing whether
    a proxy, a template or an agent produced the card -- one definition of done.
    """
    from ..proxy import CardFacts
    from ..proxy import _residual as proxy_residual

    facts = CardFacts(name=card.name, scryfall_id="", oracle_text=oracle_text)
    return proxy_residual(facts, claimed_lines(card, oracle_text))


def claimed_lines(card: CardDef, oracle_text: str) -> set[str]:
    """The printed lines something on this card accounts for.

    Split out from :func:`residual_text` so the fidelity audit can ask the
    complementary question -- *which* lines are unclaimed -- without keeping a
    second, drifting copy of the same bookkeeping.
    """
    from ..proxy import lift_keywords

    consumed: set[str] = set()
    # ``strict``: the line counts as claimed only if this card really has those
    # keywords.  Without it a card printing "Shroud" and carrying `hexproof`
    # clears the residual gate, because the line names *a* known keyword.
    _, keyword_lines = lift_keywords(
        oracle_text, tuple(str(k) for k in card.keywords), strict=True
    )
    consumed |= keyword_lines

    # An instant or sorcery has exactly one place for its text to go, so
    # `spell_effects` account for all of it and per-line attribution would be
    # inventing a distinction the card format does not have. Under-implementing
    # such a card is caught by gate 5 instead: three printed sentences and one op
    # will not satisfy an expectation asserting all three outcomes.
    if card.spell_effects:
        consumed |= set(oracle_text.split("\n"))

    consumed |= {line for line in oracle_text.split("\n") if _covered(card, line)}
    return consumed


#: How a card refers to itself.  Scryfall's current templating writes "this
#: creature"/"this enchantment", the pool writes "this", and printings older than
#: the 2024 templating update write the card's own name.  All three are the same
#: word, and matching them literally makes a correct card look unimplemented:
#: an ability reading "When this enters, draw a card" would fail to claim the
#: printed line "When Elvish Visionary enters, draw a card".
_SELF_REFERENCE = re.compile(
    r"\bthis (?:creature|enchantment|artifact|permanent|land|spell|card)\b|\bthis\b",
    re.IGNORECASE,
)


def fold_self_reference(text: str, name: str) -> str:
    """Collapse every way a card names itself to one token, for comparison only."""
    if name:
        # Longest first, so the possessive is replaced before the bare name.
        for form in sorted({f"{name}'s", name}, key=len, reverse=True):
            text = re.sub(re.escape(form), "~", text, flags=re.IGNORECASE)
    return _SELF_REFERENCE.sub("~", text)


def _declares_printed_cost(printed: str, declared: ManaCost) -> bool:
    """Whether the mana symbols printed after a keyword are the ones charged.

    ``printed`` is the remainder of the line -- "{1}{W} (You may pay an
    additional {1}{W} any number of times…)" -- so the reminder text is cut at
    the parenthesis before parsing.  Compared on the parsed cost rather than the
    string, since ``ManaCost.text`` keeps the spelling and "{W}{1}" and "{1}{W}"
    are the same price.  Anything that will not parse is not a match.
    """
    symbols = printed.split("(")[0].strip().rstrip(".").strip()
    if not symbols:
        return False
    try:
        parsed = ManaCost.parse(symbols)
    except DslError:
        return False
    return (parsed.generic, parsed.colored, parsed.x_count, parsed.hybrid) == (
        declared.generic,
        declared.colored,
        declared.x_count,
        declared.hybrid,
    )


def _covered(card: CardDef, line: str) -> bool:
    """Whether an ability on the card claims this printed line.

    Matched on the ability's ``text``, which is the author's own statement of
    which sentence they were implementing.  That makes the residual gate a check
    on *the author's* bookkeeping rather than on a parser's guess -- and an author
    who mislabels a line fails gate 5 anyway, where the board is the witness.
    """
    stripped = line.strip().rstrip(".")
    lowered = line.lower()
    if not stripped:
        return True
    folded_line = fold_self_reference(stripped, card.name)

    # "Enchant creature" is not an ability -- it is the spell's targeting clause,
    # and it is implemented by the card's `targets` plus the engine attaching the
    # Aura on resolution. Asking for an ability to claim it would make every Aura
    # unauthorable.
    if stripped.lower().startswith("enchant ") and card.targets:
        return True

    # "This spell can't be countered" is the `uncounterable` flag, not an
    # ability: a spell is on the stack, where abilities do not reach it.
    if card.uncounterable and "can't be countered" in stripped.lower():
        return True

    # "Kicker {1}{U}" is the cost half of a mechanic whose other half is an
    # ordinary `if`, so no ability carries this line either.
    if card.kicker is not None and stripped.lower().startswith("kicker "):
        return True

    # "Gift a tapped Fish (You may promise an opponent a gift as you cast this
    # spell…)" is `kicker`'s shape again -- a card-level cast-time choice offered
    # by legality, with no ability that could honestly carry the line.
    #
    # Strict like `multikicker`'s claimant rather than permissive like
    # `kicker`'s, and for the same reason: what is promised is the whole of what
    # the line says, so the declared noun phrase has to *be* the printed one. A
    # card declaring `gift: "a card"` cannot claim a printed "Gift a tapped
    # Fish" -- that is a strictly better card wearing the right words. The
    # reminder text in parentheses is the rule and is dropped, exactly as
    # `_declares_printed_cost` drops it.
    if card.gift is not None and stripped.lower().startswith("gift "):
        promised = stripped[len("gift ") :].split("(")[0].strip().rstrip(".").strip()
        return promised.casefold() == card.gift.strip().casefold()

    # "Multikicker {1}{W} (You may pay an additional {1}{W} any number of times
    # as you cast this spell.)" is the same shape as `kicker` above: a
    # card-level cost, paid inside `game._cast`, with no ability that could
    # honestly carry the line -- an AbilityModel is activated, triggered or
    # static, and a cost is none of those.
    #
    # Deliberately *stricter* than the kicker line above, because this exemption
    # is being added after the fact and has to be unable to launder anything:
    #   * `card.multikicker` is only set by the loader once it has desugared the
    #     cost into working `additional_cost`/`additional_optional`/
    #     `additional_repeatable` machinery, so the word cannot be declared
    #     without the mechanic;
    #   * the loader also refuses a multikicker no effect reads via
    #     `additional_paid`, so the card must count the kicks;
    #   * and the symbols printed on the line have to be the symbols charged, so
    #     a card declaring `multikicker: "{1}"` cannot claim a printed
    #     "Multikicker {2}{R}".
    # An unparsable or mismatched cost fails closed -- the line stays residual.
    if card.multikicker is not None and stripped.lower().startswith("multikicker "):
        return _declares_printed_cost(stripped[len("multikicker ") :], card.multikicker)

    # "Ascend (If you control ten or more permanents…)" is a *state trigger*
    # checked in the state-based-action pass, not an ability: it uses no stack
    # and cannot be responded to, so there is nothing for an ability's `text` to
    # be attached to. Same shape as `kicker` above.
    if card.ascend and stripped.lower().startswith("ascend"):
        return True

    # "This spell costs {X} less to cast" is a property of the card read while
    # deciding what is castable -- there is no ability, because a spell on the
    # stack has already been paid for.
    if card.cost_reduction is not None and "costs" in lowered and "less to cast" in lowered:
        return True

    # "Emerge {5}{U}{U}" is a whole alternative way to cast the card, paid and
    # spent inside `game._cast`. Like `kicker` above there is no ability that
    # could honestly claim it -- an AbilityModel is activated, triggered or
    # static, and emerge is none of those. Elder Deep-Fiend is the first
    # permanent whose alternative-cost line has no sacrifice trigger to hang on,
    # which is why `evoke` had not hit this: Mulldrifter's line is claimed by
    # the "it's sacrificed when it enters" trigger it really does have.
    if card.emerge is not None and stripped.lower().startswith("emerge "):
        return True
    if card.evoke is not None and stripped.lower().startswith("evoke "):
        return True

    # "As an additional cost to cast this spell, sacrifice a creature" is the
    # same shape again: a card-level `Cost` charged by `_cast_variant`, with no
    # ability that could honestly claim it. This did not surface while the only
    # cards carrying one were instants and sorceries, because `claimed_lines`
    # treats `spell_effects` as accounting for every line of a spell. A creature
    # with an additional cost -- Demon of Catastrophes -- has no `spell_effects`
    # at all, and its printed cost went unclaimed.
    if card.additional_cost is not None and stripped.lower().startswith(
        "as an additional cost"
    ):
        return True

    # "Devoid (This card has no color.)" is self-implementing -- but only if the
    # card really is colourless, which is why this is a check and not a skip. A
    # card printing Devoid while carrying colours has not implemented it.
    if stripped.lower().startswith("devoid") and not card.colors:
        return True
    for ability in card.abilities:
        claimed = (ability.text or "").strip().rstrip(".")
        if not claimed:
            continue
        if claimed == stripped or claimed in line or stripped in claimed:
            return True
        folded = fold_self_reference(claimed, card.name)
        if folded == folded_line or folded in folded_line or folded_line in folded:
            return True
    # A replacement effect implements its own printed sentence: "enters tapped",
    # "enters with two charge counters on it". There is no ability to carry the
    # text, so the claim is matched on the replacement's event instead.
    for replacement in card.replacements:
        event = replacement.get("event")
        if event == "self_enters_tapped" and "tapped" in lowered:
            return True
        if event == "self_enters_with_counters" and "counter" in lowered and "enters" in lowered:
            return True
        if event == "self_enters_prepared" and "prepared" in lowered and "enters" in lowered:
            # "This creature enters prepared. (While it's prepared, you may cast
            # a copy of its spell. Doing so unprepares it.)" -- one printed line
            # holding the replacement *and* its reminder text, which is the
            # rules rather than anything the card implements. Claimed by the
            # replacement, the way "enters tapped" above is.
            return True
    return False
