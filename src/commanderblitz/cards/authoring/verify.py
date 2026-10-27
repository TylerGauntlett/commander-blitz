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

from commanderblitz.engine.actions import PendingDecision
from commanderblitz.engine.carddef import CardDef, Cost
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import matches
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import CommanderBlitzError, DslError
from commanderblitz.engine.game import Game
from commanderblitz.engine.mana import ManaCost
from commanderblitz.engine.sandbox import GameBuilder
from commanderblitz.engine.stack import push_spell
from commanderblitz.engine.state import new_object

from ..loader import compile_card
from ..loader.linking import link_faces, validate_token_references
from ..proxy import CardFacts, lift_keywords
from ..proxy import _residual as proxy_residual
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
    #: Something for "counter target spell **with mana value 1**" to point at --
    #: Mental Misstep, and the rest of the cheap-interaction shelf behind it.
    #: The role `add_dummy_spell`'s docstring said the next unrepresented
    #: selector would need, added rather than the gate relaxed: the three
    #: incumbent dummies are mana value 5, 2 and 3, so a printed mana-value
    #: ceiling of 1 left the card with no legal target and gate 4 reported "not
    #: playable in the sandbox".
    #:
    #: ``x_count == 0`` as well as the mana value, because `mana_value` scores
    #: an announced X as 0 (202.3b) -- Secure the Wastes would otherwise qualify
    #: as a one-drop here and be a second, wrong answer to the `x_spell` role.
    "one_drop_spell": lambda c: (c.is_instant or c.is_sorcery)
    and not c.targets
    and c.mana_cost.x_count == 0
    and c.mana_value == 1,
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


def _props(
    registry: CardRegistry, roles: tuple[str, ...], *, exclude: str | None = None
) -> list[str]:
    """Concrete card ids for a list of roles, skipping any the pool cannot fill.

    Sorted before picking so the sandbox is identical run to run -- an unstable
    board makes a verdict unreproducible, which is the one thing a gate must
    never be.

    ``exclude`` is a card under test that would *act* as its own prop: one
    that sorts first for its role faces a copy of itself, and a non-mana
    ability payable off the opponent's Forest and Island stops the drive at
    their priority window -- the Bident of Thassa trap `legendary_creature`
    records, with the card as its own prop. Aether Spellbomb, ahead of
    `arcane_signet` for "artifact", was the measured case. A quiet card stays
    eligible, because moving the prop moves every verdict written against it:
    Arcane Signet is its own artifact prop, and its next neighbour is not quiet.
    """
    out: list[str] = []
    for role in roles:
        match = _ROLES[role]
        pick = next(
            (
                c.id
                for c in sorted(registry, key=lambda c: c.id)
                if match(c) and c.id != exclude
            ),
            None,
        )
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


def tribal_cost_subtype(card: CardDef | None) -> str | None:
    """The creature subtype this card's additional cost demands, if any.

    "As an additional cost to cast this spell, **tap an untapped Vampire you
    control**" -- New Blood. Read off the compiled cost rather than guessed at
    from the oracle text, so the question asked is the one the payment solver
    will ask.
    """
    if card is None or card.additional_cost is None:
        return None
    pool = card.additional_cost.tap_permanents or card.additional_cost.untap_permanents
    if not pool:
        return None
    wanted = pool.get("subtypes")
    if not wanted or len(wanted) != 1 or not isinstance(wanted[0], str):
        return None
    return wanted[0]


def _own_board(registry: CardRegistry, card: CardDef | None) -> list[str]:
    """Your two creatures -- with one swapped for the tribe a cost demands.

    Both slots are normally filled by the alphabetically first creature in the
    pool, which is an Ooze. So a printed "tap an untapped **Vampire** you
    control" is unpayable, legality never offers the cast, and gate 4 reports
    "not playable in the sandbox" -- the harness naming an unrepresented shape
    rather than a verdict about the card. Add the prop; do not relax the gate,
    the call `legendary_creature` and `small_creature` record above.

    **Swapped only for a card that needs it**, which is `add_dummy_spell`'s
    rule and for its reason: every card measured before this change must see
    the position it was measured in. Two measured facts made that non-optional
    here rather than a preference:

    - Filling a slot unconditionally with a *vanilla* creature moved eleven
      hand-written verdicts, because the hand-written pool has no vanilla
      Vampire at all -- `_props` skips a role the pool cannot fill, so the board
      silently became 31 and every `battlefield_count` in that pool read one
      low. A prop that is sometimes absent is worse than one that is never
      there.
    - The tribe is read off the card's own cost, so the test is exact rather
      than a guess about which cards are "the tribal ones".

    The replacement carries **no abilities at all** -- stricter than the "no
    activated or triggered ability" the roles above ask for, and deliberately
    so, because the ability that would hurt here is a *static* one: the tribes
    that print tap costs are the tribes that print lords, and the quietest
    Vampire in the pool by the roles' own standard is Legion Lieutenant, whose
    "other Vampires you control get +1/+1" would pump the other prop and land
    inside the measured P/T of every card verified afterwards.

    Among those, the **fewest keywords** wins, ties broken by id so the position
    is identical run to run. Keywords cannot be excluded outright -- the
    hand-written pool has 43 Vampires and not one of them is vanilla -- so the
    rule is to take the quietest body that exists rather than to insist on a
    perfect one and silently fall back to no prop at all. Lifelink on the
    resulting pick costs nothing: the sandbox declines combat, so it never
    deals damage.

    It takes the first slot rather than being appended, so the boards stay 32
    and 6; the second keeps the plain `creature` role, so a card wanting a
    creature that is *not* of the tribe still finds one.

    The second slot has a swap of its own, on the same terms: an artifact
    creature for a card whose toughness counts the artifacts you control
    (:func:`swap_in_artifact_body`).
    """
    props = _props(registry, OWN_BOARD_ROLES)
    return swap_in_artifact_body(registry, swap_in_tribal_body(registry, props, card), card)


def quiet_tribal_body(registry: CardRegistry, subtype: str) -> str | None:
    """The quietest creature of ``subtype`` in this pool, or None if it has none.

    See :func:`_own_board` for what "quietest" means and why it is not simply
    the alphabetically first. Public because the two sandboxes need the same
    answer: `tests/cards/test_every_card_works.py` builds its position from
    fixed test fixtures rather than from roles, and a second copy of this rule
    would be a second place for the two boards to disagree about what a tribal
    cost can be paid with.
    """
    match = sorted(
        (
            c
            for c in registry
            if c.is_creature
            and not c.is_token
            and "Legendary" not in c.supertypes
            and subtype in c.subtypes
            and not c.abilities
        ),
        key=lambda c: (len(c.keywords), c.id),
    )
    return match[0].id if match else None


def swap_in_tribal_body(
    registry: CardRegistry, board: list[str], card: CardDef | None
) -> list[str]:
    """``board`` with its first creature swapped for the tribe ``card``'s cost needs.

    A swap rather than an addition, so the board size is unchanged and no
    expectation moves -- the call both sandboxes' legendary props already record.
    Returns the board untouched when the card demands no tribe, or when the pool
    has no quiet body of it: the card then fails gate 4 saying it is not
    playable, which is the honest report of an unrepresented shape rather than a
    verdict about the card.
    """
    subtype = tribal_cost_subtype(card)
    if subtype is None or not board:
        return board
    pick = quiet_tribal_body(registry, subtype)
    if pick is None:
        return board
    return [pick, *board[1:]]


def _counts_own_artifacts(value: Any) -> bool:
    """Does this value expression count artifacts its controller controls?"""
    if isinstance(value, dict):
        counted = value.get("count")
        if (
            isinstance(counted, dict)
            and counted.get("controller") == "you"
            and "Artifact" in (counted.get("types") or ())
        ):
            return True
        return any(_counts_own_artifacts(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_counts_own_artifacts(v) for v in value)
    return False


def toughness_counts_own_artifacts(card: CardDef | None) -> bool:
    """Is this card's toughness the number of artifacts you control, and it none?

    "Broodstar's power and toughness are each equal to the number of artifacts
    you control" (604.3, a characteristic-defining ability). Read off the
    compiled static rather than the oracle text, so the question asked is the
    one the layer system will answer. A card that is itself an artifact counts
    itself -- Master of Etherium enters as a 1/1 on any board -- so only a
    *non*-artifact reading such a count can enter as a 0/0.
    """
    if card is None or "Artifact" in card.types:
        return False
    return any(
        a.static
        and a.static.get("effect") == "set_pt"
        and (a.static.get("affects") or {}).get("self_only")
        and _counts_own_artifacts(a.static.get("toughness"))
        for a in card.abilities
    )


def quiet_artifact_body(registry: CardRegistry) -> str | None:
    """The quietest artifact creature in this pool, or None if it has none.

    "Quiet" is :func:`quiet_tribal_body`'s standard and for its reason: **no
    abilities at all**, because the static that would hurt here is a lord's --
    Master of Etherium's "other artifact creatures you control get +1/+1"
    would land inside the measured P/T of the card under test. Then the fewest
    keywords, then a card before a token, then the id, so the position is
    identical run to run.

    Tokens are eligible because the hand-written pool, which `--collect`
    verifies against, has no artifact creature without abilities that is not a
    token. A card is still preferred: a token prop would be counted by a
    `tokens` assertion and would cease to exist on a bounce, two ways a prop
    could fold itself into another card's verdict.
    """
    match = sorted(
        (
            c
            for c in registry
            if c.is_creature
            and "Artifact" in c.types
            and "Legendary" not in c.supertypes
            and not c.abilities
            and (c.toughness or 0) > 0
        ),
        key=lambda c: (len(c.keywords), c.is_token, c.id),
    )
    return match[0].id if match else None


def swap_in_artifact_body(
    registry: CardRegistry, board: list[str], card: CardDef | None
) -> list[str]:
    """``board`` with its last creature swapped for an artifact one, if ``card`` needs it.

    Your board has no artifact, so a non-artifact creature whose toughness is
    the number of artifacts you control enters as a 0/0 and state-based
    actions bin it -- Broodstar failed gate 4 with "is a permanent but ended in
    graveyard". The harness was naming a shape the position could not
    represent, not a verdict about the card, so the prop is added and the gate
    left alone: the call `legendary_creature`, `small_creature` and
    :func:`swap_in_tribal_body` record.

    The same terms as the tribal swap, for the same reasons: **only** for a card
    :func:`toughness_counts_own_artifacts` says needs it, so every other card
    sees the position it was measured in; a swap rather than an addition, so the
    boards stay 32 and 6; and an artifact *creature*, so your board still holds
    two creatures. It takes the **last** slot, so it composes with the tribal
    swap, which takes the first. Returns the board untouched when the pool has
    no quiet artifact creature, and the card then fails gate 4 honestly.
    """
    if not toughness_counts_own_artifacts(card) or not board:
        return board
    pick = quiet_artifact_body(registry)
    if pick is None:
        return board
    return [*board[:-1], pick]


def build_sandbox(registry: CardRegistry, card_id: str, *, in_hand: bool = True) -> Game:
    """A fixed position with the card under test in hand."""
    builder = GameBuilder(registry, players=2, seed=1)
    under_test = registry.get(card_id) if card_id in registry else None
    builder.battlefield(0, MANA_BASE)
    builder.battlefield(0, _own_board(registry, under_test))
    acts = under_test is not None and any(
        (a.is_activated and not a.is_mana_ability) or a.is_triggered
        for a in under_test.abilities
    )
    builder.battlefield(
        1,
        [
            *_props(registry, OPPONENT_BOARD_ROLES, exclude=card_id if acts else None),
            "forest",
            "island",
        ],
    )
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


#: The spells every card with a `kind: "spell"` target finds on the stack.
DUMMY_ROLES = ("creature", "noncreature_spell", "x_spell")

#: Pushed on top of :data:`DUMMY_ROLES` only for a card none of them satisfies.
#: See :func:`add_dummy_spell` for why this list is conditional and that one is
#: not.
EXTRA_DUMMY_ROLES = ("one_drop_spell",)


def add_dummy_spell(
    game: Game, registry: CardRegistry, card: CardDef | None = None
) -> None:
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
    `one_drop_spell` is the second time, for Mental Misstep's "with mana value
    1" -- the three incumbents are mana value 5, 2 and 3.

    **The extras are pushed only when the card needs them**, which is the one
    thing that stops this list growing into a tax on every other counterspell.
    A dummy is a prop, and `legendary_creature` above spells out at length what
    an *acting* prop costs: no mana-value-1 spell in the pool is inert -- the
    three there are all cantrips -- so pushing one unconditionally would fold a
    card drawn by the opponent into the measured outcome of every card that
    counters, bounces or copies a spell. Reprieve is the worked example: its
    `hand_size` for the opponent moved from 2 to 3 when this was appended
    unconditionally, an assertion about Opt sitting inside Reprieve's verdict.

    So :data:`DUMMY_ROLES` is what every spell-targeting card gets, and
    :data:`EXTRA_DUMMY_ROLES` is added only for a card that none of them can
    satisfy -- asked with the very selector the target spec carries, so the test
    is exact rather than a guess about which cards are "the counterspells".
    Every card measured before this change sees the position it was measured in.
    """
    _push_dummies(game, registry, DUMMY_ROLES)
    if card is not None and _has_unmatched_spell_spec(game, card):
        _push_dummies(game, registry, EXTRA_DUMMY_ROLES)


def _push_dummies(game: Game, registry: CardRegistry, roles: tuple[str, ...]) -> None:
    for pick in _props(registry, roles):
        obj = new_object(game.state, pick, owner=1, zone=Zone.HAND)
        game.state.players[1].hand.append(obj.oid)
        push_spell(game.state, obj.oid, 1)


def _has_unmatched_spell_spec(game: Game, card: CardDef) -> bool:
    """Does this card want a spell nothing on the stack can be?

    The same question `targeting._spell_allowed` asks when it decides whether a
    stack item may be chosen, asked with the same `matches` and the same
    ``default_zone``, so "the harness thinks a dummy fits" and "legality offers
    it as a target" cannot come apart.
    """

    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    on_stack = [item.oid for item in game.state.stack if item.oid is not None]
    return any(
        not any(
            matches(ctx, oid, spec.selector, default_zone="stack") for oid in on_stack
        )
        for spec in card.targets
        if spec.kind == "spell"
    )


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
        raise CommanderBlitzError(f"no legal action for {decision.kind.value}")

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
        # The ordinal is X less any floor `ask_x` put under the question.
        floor = int(decision.context.get("min_x", 0))
        alive = [a for a in choices if (a.choice or 0) + floor < life]
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
    front = [a for a in matches if not a.second_face] or matches
    # **Spree** (702.166a): the line that buys the most modes. `multikicked`'s
    # argument, with the one difference that makes it unconditional: a spree
    # card has no free line to protect -- every line pays at least one price --
    # but legality offers the single-mode subsets first, so taking the first
    # would measure a third of Smuggler's Surprise and pass a card whose other
    # two modes do nothing at all. There is no way to tell that from the card
    # working, which is exactly the failure gate 5 exists to catch.
    #
    # `max` is stable, so every card without spree keeps legality's order and
    # the front-face preference above.
    return max(front, key=lambda a: len(a.spree_modes))


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
    partners: Sequence[dict] | None = None,
) -> Verdict:
    """Run every gate over one candidate.

    ``registry`` is the pool the card will join, minus the card itself; it
    supplies the sandbox's lands, dummy creatures and token definitions.

    ``supersedes`` says this card is a *replacement* for one already in the pool
    under the same id, so the duplicate-id gate should stand aside. Only
    ``--collect --supersede`` passes it, and only after the caller has committed
    to deleting the incumbent -- see ``scripts/author_cards.py``.

    ``partners`` is the other half of a **meld pair** (701.37) when that half is
    a machine-authored card of its own: Gisela names Bruna in ``melds_with``,
    and `link_meld_results` refuses a partner that is not in the pool. Unlike a
    companion, a partner is not this answer's to carry -- Bruna is cast, drawn
    and decked like any card and was verified through her own answer -- so it
    joins the pool here and is written nowhere. Only the id ``melds_with``
    names is accepted, so the slot cannot smuggle in anything else.
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
    except CommanderBlitzError as exc:
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
        for partner in partners or ():
            partner_card = compile_card(CardModel.model_validate(partner))
            if partner_card.id != card.melds_with or partner_card.id in existing:
                # Not this card's meld partner, or one the pool already has --
                # either way not something the slot exists for.
                verdict.failed_gate = "registry"
                verdict.reason = (
                    f"{partner_card.id!r} is not a meld partner this card needs "
                    f"brought into the pool (melds_with is {card.melds_with!r})"
                )
                return verdict
            pool[partner_card.id] = partner_card
        for extra in companions or ():
            extra_card = compile_card(CardModel.model_validate(extra))
            if extra_card.id in existing and not supersedes:
                # The same silent overwrite the front face is guarded against
                # above, one line further down and far quieter. A face id is a
                # slug of the *face's* printed name, so a card whose back half
                # is named after a card that already exists -- Emeritus of Woe
                # // Demonic Tutor is the one that found this -- lands its
                # companion on top of the incumbent. Nothing collides: the dict
                # merge replaces, `link_faces` then stamps `parent_face` on what
                # used to be a free-standing card, and a real Demonic Tutor
                # stops being something a deck may contain.
                #
                # Not `registry`, which the front's guard reads, because that
                # membership test has to ignore `card.id`; `existing` is the
                # pool with this answer's own front already taken out.
                verdict.failed_gate = "registry"
                verdict.reason = (
                    f"companion face {extra_card.id!r} is already in the pool as a "
                    f"card of its own -- give the face a distinct id"
                )
                return verdict
            pool[extra_card.id] = extra_card

        link_faces(pool)
        merged = CardRegistry(pool)
        validate_token_references({c.id: c for c in merged})
    except CommanderBlitzError as exc:
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
    if not played.is_permanent:
        # A spell goes to its owner's graveyard -- unless the card itself says
        # otherwise, which two riders do: "Exile Teferi's Protection" and
        # rebound's "exile it as it resolves". The gate asks whether the card
        # ended where a card of *its* kind ends, so it has to read the card
        # rather than the type. Widened only by a declared flag: a spell that
        # merely finds itself in exile still fails, which is what this catches.
        spell_zones = {Zone.GRAVEYARD}
        if played.exiles_itself or played.rebound:
            spell_zones.add(Zone.EXILE)
        if played.tucks_itself is not None:
            # "…put it into its owner's library seventh from the top" -- Approach
            # of the Second Sun. The third rider to widen this set, admitted on
            # exactly the same terms as the two above: a **declared** flag, so a
            # spell that merely finds itself in a library still fails the gate.
            spell_zones.add(Zone.LIBRARY)
        if obj.zone not in spell_zones:
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
        add_dummy_spell(game, registry, card)
    game._advance()

    action = find_play(
        game, card.id, kicked=kicked, multikicked=multikicked, gifted=gifted
    )
    if action is None:
        offered = [a.label for a in game.legal_actions()][:8]
        raise CommanderBlitzError(f"{card.id} is not playable in the sandbox; offered: {offered}")
    oid = action.source

    target_oid = next((ref.id for ref in action.targets if ref.kind == "object"), None)
    before: tuple[int, int] | None = None
    if target_oid is not None and target_oid in game.state.objects:
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

    facts = CardFacts(name=card.name, scryfall_id="", oracle_text=oracle_text)
    return proxy_residual(facts, claimed_lines(card, oracle_text))


def claimed_lines(card: CardDef, oracle_text: str) -> set[str]:
    """The printed lines something on this card accounts for.

    Split out from :func:`residual_text` so the fidelity audit can ask the
    complementary question -- *which* lines are unclaimed -- without keeping a
    second, drifting copy of the same bookkeeping.
    """

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


#: A station symbol at the head of a printed line: "12+ | …".
_STRIATION = re.compile(r"^(\d+)\+\s*\|")


#: The printed ordinals of a `cant_cast_first_turns` line, by how many turns
#: it names.
_FIRST_TURNS_WORDS = {
    1: "first turn",
    2: "first or second turns",
    3: "first, second, or third turns",
}


def fold_self_reference(text: str, name: str) -> str:
    """Collapse every way a card names itself to one token, for comparison only."""
    if name:
        # Longest first, so the possessive is replaced before the bare name.
        for form in sorted({f"{name}'s", name}, key=len, reverse=True):
            text = re.sub(re.escape(form), "~", text, flags=re.IGNORECASE)
    return _SELF_REFERENCE.sub("~", text)


#: The printed keyword each `pay_generic_with` currency is, for its claimant.
_PAY_GENERIC_KEYWORDS = {
    "tap_creatures": "convoke",
    "tap_artifacts": "improvise",
    "exile_from_graveyard": "delve",
}


#: The price on a strive line -- "costs {1}{W} more to cast for each target
#: beyond the first". Only the symbols are captured; the rest of the sentence
#: has to be there word for word, because a cost that grows with something other
#: than the target count is a different mechanic wearing the same word.
_STRIVE_LINE = re.compile(
    r"costs ((?:\{[^}]+\})+) more to cast for each target beyond the first$",
    re.IGNORECASE,
)


#: The two printed shapes of a card-level alternative cost (118.9), read off the
#: self-reference-folded, lower-cased line: "[If <condition>, ]you may <payment>
#: rather than pay this spell's mana cost" and "[If <condition>, ]you may cast
#: this spell without paying its mana cost". Anchored at both ends, so a
#: sentence that merely *mentions* a free cast -- "you may cast a card exiled
#: with ~ without paying its mana cost" -- is not read as the card's own price.
_ALTERNATIVE_COST_LINE = re.compile(
    r"^(?:if [^,]+, )?you may (?P<payment>.+?) rather than pay (?:~'s|its) mana cost$",
    re.IGNORECASE,
)
_FREE_CAST_LINE = re.compile(
    r"^(?:if [^,]+, )?you may cast ~ without paying (?:its|~'s) mana cost$",
    re.IGNORECASE,
)
#: "tap four untapped creatures you control with flying" -- `tap_permanents`.
_TAP_PAYMENT = re.compile(
    r"\btap (?P<count>\w+) untapped (?P<noun>.+?) you control"
    r"(?: with (?P<keywords>.+?))?(?= and |$)"
)
_PAY_LIFE = re.compile(r"\bpay (\d+) life\b")
_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}  # fmt: skip
#: The `alternative_cost` fields the claimant below reads off the printed line.
#: Any *other* field set on the node is a payment the claimant cannot see, so
#: it fails closed rather than wave it through.
_READ_ALTERNATIVE_FIELDS = frozenset(
    {
        "mana",
        "tap_permanents",
        "pay_life",
        "sacrifice",
        "return_to_hand",
        "exile_from_hand",
        "discard",
        "discard_selector",
    }
)
#: Selector keys a printed "tap N untapped <noun> you control with <keyword>"
#: can state. A selector narrowed any other way prints words this does not read.
_READ_TAP_KEYS = frozenset({"types", "subtypes", "any_types", "keywords", "controller", "count"})


def _declares_printed_tap(payment: str, declared: Any) -> bool:
    """Whether "tap N untapped <noun> you control[ with <keywords>]" is the pool.

    Both directions, because either mismatch is a different card: a declared
    pool the line does not print is a dearer card, and a printed narrowing the
    pool does not carry -- "with flying" over a bare `Creature` selector -- is a
    cheaper one.
    """
    match = _TAP_PAYMENT.search(payment)
    if match is None or declared is None:
        return match is None and declared is None
    spec = dict(declared)
    if set(spec) - _READ_TAP_KEYS or spec.get("controller", "you") != "you":
        return False
    if _NUMBER_WORDS.get(match.group("count"), -1) != int(spec.get("count", 1) or 1):
        return False
    wanted = {
        str(word).lower()
        for key in ("types", "subtypes", "any_types")
        for word in spec.get(key) or ()
    }
    filler = {"and/or", "and", "or", "other"}
    printed = {
        word[:-1] if word.endswith("s") else word
        for word in re.split(r"[\s,]+", match.group("noun"))
        if word and word not in filler
    }
    if printed != wanted:
        return False
    keywords = match.group("keywords")
    printed_keywords = (
        {word for word in re.split(r",\s*|\s+and\s+|\s+or\s+", keywords) if word}
        if keywords
        else set()
    )
    return printed_keywords == {str(k).lower() for k in spec.get("keywords") or ()}


def _declares_printed_alternative_cost(line: str, card: CardDef) -> bool:
    """Whether this printed line is the card's own ``alternative_cost``, exactly.

    ``line`` is self-reference-folded, with its trailing period stripped. The mana symbols printed
    in the payment must be the declared ``mana`` (none printed means none
    charged), the "tap N untapped …" clause must be the declared
    ``tap_permanents``, and "pay N life" the declared ``pay_life``. The other
    payments it can name -- sacrifice, return, exile from hand, discard -- must
    appear on the line exactly when they are declared. A field this does not
    read fails closed.
    """
    cost = card.alternative_cost
    if cost is None:
        return False
    default = Cost()
    for name in Cost.__dataclass_fields__:
        if name not in _READ_ALTERNATIVE_FIELDS and getattr(cost, name) != getattr(
            default, name
        ):
            return False
    if _FREE_CAST_LINE.match(line):
        # "…cast this spell without paying its mana cost": nothing is paid.
        return cost.mana.is_free() and cost.charges_nothing()
    match = _ALTERNATIVE_COST_LINE.match(line)
    if match is None:
        return False
    symbols = re.findall(r"\{[^}]+\}", match.group("payment"))
    payment = match.group("payment").lower()
    if symbols:
        if not _declares_printed_cost("".join(symbols), cost.mana):
            return False
    elif not cost.mana.is_free():
        return False
    if not _declares_printed_tap(payment, cost.tap_permanents):
        return False
    life = _PAY_LIFE.search(payment)
    if not isinstance(cost.pay_life, int):
        return False
    if (int(life.group(1)) if life else 0) != cost.pay_life:
        return False
    verbs = (
        (r"\bsacrifice\b", cost.sacrifice is not None),
        (r"\breturn\b", cost.return_to_hand is not None),
        (r"\bexile\b.*\bfrom your hand\b", cost.exile_from_hand is not None),
        (r"\bdiscard\b", bool(cost.discard)),
    )
    return all((re.search(verb, payment) is not None) == declared for verb, declared in verbs)


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

    # "You can't cast Serra Avenger during your first, second, or third turns
    # of the game" is `cant_cast_first_turns`. Strict: the printed ordinals
    # must be exactly the turns the field names, or the card waits a
    # different number of turns than it prints.
    if card.cant_cast_first_turns is not None:
        turns = _FIRST_TURNS_WORDS.get(card.cant_cast_first_turns)
        if turns is not None and re.fullmatch(
            rf"you can't cast (?:~ |this spell )?during your {turns} of the game",
            folded_line.lower(),
        ):
            return True

    # "Teferi, Temporal Archmage can be your commander." is the other
    # deck-construction sentence (903.3), read by `validate_deck` through
    # `CardDef.can_be_commander` -- strict the same way the "any number" line
    # below is: claimed only when the sentence names this card.
    if card.can_be_commander and stripped.lower().endswith("can be your commander"):
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

    # "Strive — This spell costs {1}{W} more to cast for each target beyond the
    # first." Multikicker's shape: a card-level price charged inside
    # `game._cast`, so no ability can honestly carry the line -- and strict for
    # multikicker's reason. The loader sets `card.strive` only beside the one
    # "any number of target" spec it prices, and the symbols on the line have
    # to be the ones charged, so declaring `strive: "{1}"` cannot claim a printed
    # "{2}{R} more". An unparsable or mismatched line stays residual.
    if card.strive is not None and stripped.lower().startswith("strive"):
        match = _STRIVE_LINE.search(stripped)
        return match is not None and _declares_printed_cost(match.group(1), card.strive)

    # "Ascend (If you control ten or more permanents…)" is a *state trigger*
    # checked in the state-based-action pass, not an ability: it uses no stack
    # and cannot be responded to, so there is nothing for an ability's `text` to
    # be attached to. Same shape as `kicker` above.
    if card.ascend and stripped.lower().startswith("ascend"):
        return True

    # "Improvise (Your artifacts can help cast this spell…)", and convoke and
    # delve beside it: `pay_generic_with`, a card-level way to pay the generic
    # cost read by `casting` and `game._cast`, with no ability that could
    # honestly carry the line. Spells never reached this -- `spell_effects`
    # claims their every line -- and Kappa Cannoneer is the first permanent.
    #
    # Strict on the word: the printed keyword must be the declared currency's,
    # so a card tapping creatures cannot claim a printed "Improvise", and the
    # line must be the bare keyword plus its reminder text.
    if card.pay_generic_with is not None:
        keyword = _PAY_GENERIC_KEYWORDS.get(card.pay_generic_with)
        bare = re.sub(r"\([^()]*\)", "", stripped).strip().rstrip(".").strip().lower()
        if keyword is not None and bare == keyword:
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

    # "Bestow {1}{G}" is that same card-level alternative cost once more, and
    # the one this list had simply never reached -- Springheart Nantuko is the
    # first bestow card the pipeline tried to author, and it failed gate 3 with
    # every other line implemented. No ability can honestly claim the line: an
    # AbilityModel is activated, triggered or static, and bestow is none of the
    # three. `lift_keywords` cannot consume it either, because "bestow" is not
    # in `KNOWN_KEYWORDS` and the loader rejects a card that declares it as one.
    #
    # Declaring the field is not a way to *look* implemented. The loader parses
    # it, refuses it on a non-creature and on a card that is already an Aura,
    # and `legality`/`stack` then offer the bestow cast line with the
    # rules-supplied `BESTOW_TARGET` attached -- so the word cannot be written
    # without the mechanic behind it.
    #
    # Strict like `multikicker`'s claimant rather than permissive like `evoke`'s
    # directly above, and for multikicker's stated reason: bestow's whole line
    # is its price, so a card declaring `bestow: "{1}{G}"` must not be able to
    # claim a printed "Bestow {5}{W}" -- that is a strictly cheaper card wearing
    # the right words. An unparsable or mismatched cost fails closed and the
    # line stays residual.
    if card.bestow is not None and stripped.lower().startswith("bestow "):
        return _declares_printed_cost(stripped[len("bestow ") :], card.bestow)

    # "Mutate {1}{G}{G} (If you cast this spell for its mutate cost…)" is bestow's
    # shape exactly: a card-level alternative way to cast the spell, offered by
    # `legality` and paid inside `game._cast`, with no AbilityModel that could
    # honestly carry it -- one is activated, triggered or static, and mutate is
    # none of the three. Gemrazer is the first mutate card the pipeline tried to
    # author and it failed gate 3 with its other two lines implemented, which is
    # where Springheart Nantuko put bestow on this list.
    #
    # Declaring the field is not a way to *look* implemented: the loader parses
    # the cost, refuses it on a non-creature (702.140a) and refuses it beside
    # bestow, and `legality`/`stack` then offer the mutating cast line with the
    # rules-supplied `MUTATE_TARGET` and the over-or-under question at
    # resolution. So the word cannot be written without the mechanic behind it.
    #
    # Strict like bestow's claimant and for its reason: the whole line is the
    # price, so a card declaring `mutate: "{1}{G}"` must not be able to claim a
    # printed "Mutate {3}{G}{G}". An unparsable or mismatched cost fails closed
    # and the line stays residual.
    if card.mutate is not None and stripped.lower().startswith("mutate "):
        return _declares_printed_cost(stripped[len("mutate ") :], card.mutate)

    # "Warp {1}{W} (You may cast this card from your hand for its warp cost…)"
    # is the same shape a third time, and it is the one that had no claimant.
    # The mechanic is entirely built -- the loader parses the cost and refuses
    # it on a nonpermanent, `casting.warp_cost` offers the second cast line, and
    # `stack` supplies the rules-given exile at the next end step and the cast
    # from exile on a later turn -- but `warp` is not in `KNOWN_KEYWORDS`, so
    # `lift_keywords` cannot consume the line either, and a correctly
    # implemented warp card failed gate 3 with `residual_text` returning exactly
    # "Warp {1}{W}". No shipped card used the field, so nothing had hit it: the
    # only warp in the pool was the `grant_warp` static on another permanent,
    # whose printed line that static's own `text` already claims.
    #
    # Strict like bestow's and mutate's claimants and for their reason: the whole
    # line is the price, so a card declaring `warp: "{1}{W}"` must not be able to
    # claim a printed "Warp {3}{W}". An unparsable or mismatched cost fails
    # closed and the line stays residual.
    if card.warp is not None and stripped.lower().startswith("warp "):
        return _declares_printed_cost(stripped[len("warp ") :], card.warp)

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
    # "As an additional cost to cast this spell, behold a Kithkin **or** pay
    # {2}" -- the same card-level cost written as `additional_cost_options`,
    # and unclaimed for the same reason on a creature, which has no
    # `spell_effects` to claim it wholesale. Stricter than the line above,
    # because it is added after the fact: a printed "behold" needs a behold
    # branch and a declared one needs the word, and printed mana symbols must be
    # some branch's mana, so a card declaring "or pay {1}" cannot claim a
    # printed "or pay {2}". A mismatch leaves the line residual.
    if card.additional_cost_options and stripped.lower().startswith("as an additional cost"):
        printed = stripped.split("(")[0]
        options = card.additional_cost_options
        beholds = any(option.behold is not None for option in options)
        symbols = "".join(re.findall(r"\{[^}]+\}", printed))
        if ("behold" in printed.lower()) == beholds and (
            not symbols or any(_declares_printed_cost(symbols, o.mana) for o in options)
        ):
            return True

    # "You may pay {W} and tap four untapped creatures you control with flying
    # rather than pay this spell's mana cost." -- Sephara, Sky's Blade. The
    # card-level `alternative_cost` (118.9), offered by `casting` beside the
    # printed cost and charged by `game._cast`, and the claimant this list had
    # never needed: every card shipped with one was an instant, whose lines
    # `spell_effects` claims wholesale. A permanent has no `spell_effects`, and
    # no AbilityModel can honestly carry a cost -- one is activated, triggered
    # or static, and this is none of the three.
    #
    # Strict like bestow's and multikicker's claimants, and for their reason:
    # the line *is* the price. The printed mana must be the declared `mana`,
    # the printed "tap N untapped <noun> with <keyword>" the declared
    # `tap_permanents`, and the printed life the declared `pay_life`, so a card
    # declaring `{U}` cannot claim a printed `{W}` and one tapping three cannot
    # claim "tap four". Not an early `return False` on a mismatch: a sentence
    # that is not this card's price falls through to the ability claimants
    # below like any other line.
    if card.alternative_cost is not None and _declares_printed_alternative_cost(
        folded_line, card
    ):
        return True

    # "Devoid (This card has no color.)" is self-implementing -- but only if the
    # card really is colourless, which is why this is a check and not a skip. A
    # card printing Devoid while carrying colours has not implemented it.
    if stripped.lower().startswith("devoid") and not card.colors:
        return True

    # "A deck can have any number of cards named Persistent Petitioners." is a
    # *deck-construction* rule (903.5b), not a game rule: it is read by
    # `validate_deck` while a deck is being built, and by the time the card is
    # an object in a game it has nothing left to do. So no ability can honestly
    # claim it -- an AbilityModel is activated, triggered or static, and this is
    # none of the three -- and Persistent Petitioners failed gate 3 with both of
    # its real lines implemented and verified.
    #
    # Strict like `bestow`'s and `devoid`'s claimants rather than a bare prefix
    # skip: `CardDef.any_number_in_deck` returns True only when the name inside
    # the printed sentence is the card's *own* name, so the words cannot be
    # claimed without the rule standing behind them. A card that merely quotes
    # another card's sentence still fails the gate.
    if card.any_number_in_deck and stripped.lower().startswith(
        "a deck can have any number of cards named"
    ):
        return True
    # The same line with a ceiling on it -- Nazgul's "up to nine", Seven
    # Dwarves' "up to seven". It is the same deck-construction rule and so has
    # the same claimant, gated on `deck_copy_limit` having actually read a
    # number off *this* card: a limit it could not parse falls back to 1 and is
    # left residual rather than waved through on the strength of the words.
    if card.deck_copy_limit not in (None, 1) and stripped.lower().startswith(
        "a deck can have up to "
    ):
        return True
    # "12+ | {U}, {T}: Add {U} for each artifact you control." A station
    # striation (721) is claimed only by an ability gated at that very number,
    # and only by its whole text. The loose substring match below would let an
    # ungated "{U}, {T}: Add {U} …" claim the line -- a Planet that makes the
    # mana from turn one, wearing the printed words.
    striation = _STRIATION.match(stripped)
    if striation is not None:
        wanted = int(striation.group(1))
        return any(
            ability.threshold is not None
            and ability.threshold[1] == wanted
            and fold_self_reference((ability.text or "").strip().rstrip("."), card.name)
            == folded_line
            for ability in card.abilities
        )
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
        if event == "self_enters_as_copy" and "copy" in lowered and "enter" in lowered:
            # "You may have this Equipment enter as a copy of any Equipment on
            # the battlefield." The fourth of this family, claimed the same way
            # and for the same reason: 614.1b applies as the permanent arrives,
            # so there is no ability whose `text` could carry the line.
            #
            # The words are matched rather than skipped, and the loader will not
            # let the event be written without a `copying` pool, so the sentence
            # cannot be claimed by a card that copies nothing.
            #
            # Nor by a copy that drops a printed half: "…until end of turn"
            # needs the timed `duration` and "…except it has haste" needs an
            # `except_`, or the card claims a sentence it only half performs.
            if "until end of turn" in lowered and replacement.get("duration") != "end_of_turn":
                continue
            if "except it has" in lowered and not replacement.get("except_"):
                continue
            return True
        if event == "self_enters_replaced" and "would enter" in lowered:
            # "If this artifact would enter, you may discard a land card
            # instead. If you do, put this artifact onto the battlefield. If you
            # don't, put it into its owner's graveyard." -- Mox Diamond. One
            # printed line holding the whole replacement, claimed the way the
            # four above are: it replaces the arrival itself, so there is no
            # ability whose `text` could carry it.
            #
            # "would enter" rather than the looser "enter", so the sentence
            # cannot be claimed by "when this enters" -- that is a trigger, and
            # writing it as one is exactly the approximation this event exists
            # to replace.
            return True
    return False
