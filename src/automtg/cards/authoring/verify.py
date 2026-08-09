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

from dataclasses import dataclass, field
from typing import Any

from automtg.engine.actions import PendingDecision
from automtg.engine.carddef import CardDef
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.errors import AutoMtgError
from automtg.engine.game import Game
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
}

#: Which roles each zone gets.  The opponent's board carries one of each broad
#: type, so "destroy target artifact" and "return target creature" both find
#: something to point at.
OWN_BOARD_ROLES = ("creature", "creature")
OPPONENT_BOARD_ROLES = ("creature", "flier", "artifact", "enchantment")
OWN_GRAVEYARD_ROLES = ("creature", "flier")
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
    builder.library(0, list(BASIC_LANDS) * 8)
    builder.library(1, ["forest", "island"] * 10)
    if in_hand:
        builder.hand(0, [card_id])
    return builder.build(advance=False)


def add_dummy_spell(game: Game) -> None:
    """Put a spell on the stack so a counterspell has something to target."""
    obj = new_object(game.state, "t_bear", owner=1, zone=Zone.HAND)
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

    # Otherwise take a real choice, so an optional effect is actually exercised
    # rather than declined into a no-op that would pass any assertion.
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
)


def check_expectation(game: Game, card_id: str, oid: int, expectation: dict) -> list[str]:
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
) -> Verdict:
    """Run every gate over one candidate.

    ``registry`` is the pool the card will join, minus the card itself; it
    supplies the sandbox's lands, dummy creatures and token definitions.
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
    if card.id in registry:
        # A dict merge would have *replaced* the existing card, so a machine
        # could silently overwrite a hand-written one and every deck referencing
        # that id would quietly change. `CardRegistry.from_paths` raises on this
        # at load time; the gate has to raise on it at authoring time.
        verdict.failed_gate = "registry"
        verdict.reason = f"{card.id!r} is already in the pool"
        return verdict
    existing = {c.id: c for c in registry}
    try:
        merged = CardRegistry({**existing, card.id: card})
        from ..loader import validate_token_references

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
    """Cast it and assert only that it went where cards of its kind go."""
    game, oid = _cast(registry, card)
    obj = game.state.objects.get(oid)
    if obj is None:
        return [f"{card.id} vanished entirely"]
    if obj.zone is Zone.STACK:
        return [f"{card.id} never left the stack"]
    # An Aura in the graveyard is not a failure. Dead Weight gives -2/-2, kills
    # what it enchanted, and state-based actions correctly bin it a moment later
    # -- the card working exactly as printed. Rejecting that would throw away
    # every Aura whose own effect can finish its host.
    allowed = {Zone.BATTLEFIELD, Zone.GRAVEYARD} if card.is_aura else {Zone.BATTLEFIELD}
    if card.is_permanent and obj.zone not in allowed:
        return [f"{card.id} is a permanent but ended in {obj.zone.value}"]
    if not card.is_permanent and obj.zone is not Zone.GRAVEYARD:
        return [f"{card.id} is a spell but ended in {obj.zone.value}"]
    return []


def _play_and_check(registry: CardRegistry, card: CardDef, expectation: dict) -> list[str]:
    game, oid = _cast(registry, card)
    return check_expectation(game, card.id, oid, expectation)


def _cast(registry: CardRegistry, card: CardDef) -> tuple[Game, int]:
    game = build_sandbox(registry, card.id)
    if any(spec.kind == "spell" for spec in card.targets):
        add_dummy_spell(game)
    game._advance()

    action = find_play(game, card.id)
    if action is None:
        offered = [a.label for a in game.legal_actions()][:8]
        raise AutoMtgError(f"{card.id} is not playable in the sandbox; offered: {offered}")
    oid = action.source
    game.apply(action)
    drive(game)
    return game, oid


# ----------------------------------------------------------------------
# residual
# ----------------------------------------------------------------------


def residual_text(card: CardDef, oracle_text: str) -> str:
    """Printed sentences the card's abilities do not account for.

    Reuses ``proxy``'s reader so "what is left over" means the same thing whether
    a proxy, a template or an agent produced the card -- one definition of done.
    """
    from ..proxy import CardFacts, lift_keywords
    from ..proxy import _residual as proxy_residual

    consumed: set[str] = set()
    _, keyword_lines = lift_keywords(oracle_text, tuple(str(k) for k in card.keywords))
    consumed |= keyword_lines

    # An instant or sorcery has exactly one place for its text to go, so
    # `spell_effects` account for all of it and per-line attribution would be
    # inventing a distinction the card format does not have. Under-implementing
    # such a card is caught by gate 5 instead: three printed sentences and one op
    # will not satisfy an expectation asserting all three outcomes.
    if card.spell_effects:
        consumed |= set(oracle_text.split("\n"))

    consumed |= {line for line in oracle_text.split("\n") if _covered(card, line)}

    facts = CardFacts(name=card.name, scryfall_id="", oracle_text=oracle_text)
    return proxy_residual(facts, consumed)


def _covered(card: CardDef, line: str) -> bool:
    """Whether an ability on the card claims this printed line.

    Matched on the ability's ``text``, which is the author's own statement of
    which sentence they were implementing.  That makes the residual gate a check
    on *the author's* bookkeeping rather than on a parser's guess -- and an author
    who mislabels a line fails gate 5 anyway, where the board is the witness.
    """
    stripped = line.strip().rstrip(".")
    if not stripped:
        return True

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
    for ability in card.abilities:
        claimed = (ability.text or "").strip().rstrip(".")
        if claimed and (claimed == stripped or claimed in line or stripped in claimed):
            return True
    for replacement in card.replacements:
        if replacement.get("event") == "self_enters_tapped" and "tapped" in line.lower():
            return True
    return False
