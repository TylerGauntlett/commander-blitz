"""The condition DSL -- boolean tests used by ``if`` effects, intervening-if
clauses on triggers, and static ability conditions.

    {"cmp": ">=", "left": {...}, "right": {...}}
    {"all": [...]}  {"any": [...]}  {"not": {...}}
    {"exists": {selector}}
    {"zone_is": "battlefield"}
    {"kicked": true}
    {"gift_promised": false}
    {"evoked": true}
    {"cast_during": "your_main"}
    {"was_cast": true}
    {"is_active_player": {"binding": "event_player"}}
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ..characteristics import chars
from ..enums import STEP_PHASE, Phase
from ..errors import DslError
from .context import EffectContext
from .selectors import PLAYER_SPEC_NAMES, resolve_pool, select_players, validate_selector
from .values import evaluate_value, validate_value

if TYPE_CHECKING:  # pragma: no cover
    from ..state import GameState

CONDITION_KEYS = frozenset(
    {
        "entered_from",
        #: Not a condition of its own: a sibling key on `cast_from_graveyard`
        #: naming the binding to ask about instead of the ability's own source.
        "of",
        "cmp",
        "left",
        "right",
        "all",
        "any",
        "not",
        "exists",
        #: "If two nonland cards that **share a color** were milled this way"
        #: (Sphinx's Tutelage). A relation *between* two members of a pool, and
        #: the only condition here that is not a property of one object: every
        #: other colour reader asks about a single card (`colors`/`not_colors`
        #: against a fixed colour, `min_colors` counting one card's own), and
        #: `shares_a_color_with` resolves its argument through `_bound_oid`,
        #: which reads one oid and returns None for the list binding a `mill`
        #: always writes.
        "two_share_a_color",
        "zone_is",
        "is_your_turn",
        "kicked",
        # Gift (702.164a): "**if the gift wasn't promised**, return that card to
        # the battlefield…". `kicked`'s shape for a choice that costs nothing:
        # the promise is made as the spell is cast and the spell branches on it.
        #
        # It is deliberately not spelled as a test on the recipient -- "did
        # anybody get a gift" and "who got it" are two questions, and only the
        # first one is what the printed sentence asks. The second is a player
        # spec (`"gift_recipient"`), which is the half that aims the reward.
        "gift_promised",
        "evoked",
        "cast_from_graveyard",
        #: Approach of the Second Sun's "if this spell was cast from your hand".
        #: The sibling of the key above and not its negation: a spell cast from
        #: exile, from a Citadel top or from the command zone was cast from
        #: neither, and a copy was never cast at all (707.10).
        "cast_from_hand",
        # Overload (702.96a): "change its text by replacing all instances of
        # 'target' with 'each'". There is no rewriting a printed sentence, and
        # the two halves really are two effects, so the card branches on this.
        "overloaded",
        # Which of `additional_cost_options` was paid, by index. **Tiered**
        # (Fire Magic, Ice Magic): each tier is a different effect, so the card
        # is one `choose_mode`-free branch per price. Bitter Triumph needed no
        # such key because both of its prices lead to the same effect.
        "cost_option",
        # **Spree** (702.166a): whether mode n was among the ones bought. The
        # set-membership sibling of `cost_option`, and a separate key rather
        # than a widening of it because the two ask different questions: "the
        # tier that was paid *is* n" against "n was *among* those paid". A
        # spree card asked the first would run at most one of the modes it
        # charged for.
        "spree_mode",
        "has_city_s_blessing",
        # "If you're the monarch…" (721). Takes a player spec, so a card can also
        # ask it of somebody else.
        "is_monarch",
        # "…if there is **no** monarch" -- Crown of Gondor. Deliberately its own
        # key and not `{"not": {"is_monarch": "you"}}`, which is a different
        # question: that negation is also true while an *opponent* holds the
        # crown, which is precisely the case the card must not fire in.
        "no_monarch",
        # "…if it isn't renowned". A one-way word written by `set_flag`.
        "has_flag",
        # "If this creature hasn't been **exerted this turn**" -- the same
        # question with the other lifetime, written by `set_turn_flag` and
        # cleared with the rest of the turn ledger. Its own key rather than a
        # duration on `has_flag`, because a card that reached for the wrong one
        # would be wrong only on the *second* turn, which no one-turn test sees.
        "has_turn_flag",
        # Prowl: "…if a player was dealt combat damage this turn by a Faerie or
        # a Rogue". A list of creature subtypes, true when *any* of them dealt
        # combat damage to a player this turn.
        "combat_damage_by",
        # Addendum: "if you cast this spell during your main phase". Reads the
        # step stamped on the object as it went on the stack, not the step the
        # game is in now -- see `_cast_during`.
        "cast_during",
        # "When this artifact enters, **if it was cast**…" (603.6e). About
        # *this* arrival on the battlefield, which is the one thing none of the
        # `cast_*` stamps can say: they are written once and never cleared, so
        # they still answer for a permanent that was cast, died and was
        # reanimated. See `entered_by_cast`.
        "was_cast",
        # "…**during their turn**". Whether the player a spec names is the
        # active player. Takes a full player spec the way `is_monarch` does, so
        # a trigger writes `{"binding": "event_player"}` and asks about the
        # player the *event* was about rather than about its own controller,
        # which is the only thing `is_your_turn` can ask.
        "is_active_player",
    }
)

#: What `cast_during` may name. A phase, plus `main` for "either main phase",
#: each optionally prefixed `your_` to *also* require that the caster was the
#: active player -- which is the difference between "during a main phase" and
#: addendum's "during **your** main phase".
#:
#: A generated vocabulary rather than a hand-kept list: the phases are the
#: engine's own, so a card cannot name one the turn structure does not have.
CAST_DURING_PHASES = frozenset({p.value for p in Phase} | {"main"})
CAST_DURING_NAMES = frozenset(
    set(CAST_DURING_PHASES) | {f"your_{name}" for name in CAST_DURING_PHASES}
)


def evaluate(ctx: EffectContext, cond: Any) -> bool:
    """Evaluate a condition in an existing effect context."""
    if cond is None:
        return True
    if isinstance(cond, bool):
        return cond
    if not isinstance(cond, Mapping):
        raise DslError(f"unparsable condition {cond!r}")

    if "all" in cond:
        return all(evaluate(ctx, c) for c in cond["all"])
    if "any" in cond:
        return any(evaluate(ctx, c) for c in cond["any"])
    if "not" in cond:
        return not evaluate(ctx, cond["not"])
    if "exists" in cond:
        return bool(resolve_pool(ctx, cond["exists"]))
    if "two_share_a_color" in cond:
        return _two_share_a_color(ctx, cond["two_share_a_color"])
    if "zone_is" in cond:
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        return obj is not None and obj.zone.value == cond["zone_is"]
    if "kicked" in cond:
        # Two sources, because the flag has two lifetimes. While the spell
        # resolves the StackItem is authoritative and nothing is on the
        # object yet; once it is a permanent the StackItem is gone and the
        # object is. An ETB trigger only ever sees the second, which is why
        # "if it was kicked" read False on every permanent before this.
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        was_kicked = ctx.kicked or (obj is not None and obj.cast_kicked)
        return was_kicked == bool(cond["kicked"])
    if "gift_promised" in cond:
        # Two sources for the same reason `kicked` has two: while the spell
        # resolves the StackItem is authoritative, and once the spell is gone --
        # a delayed trigger it scheduled, an enters trigger of the permanent it
        # became -- only the object is left. `stack.resolve` writes the object
        # *before* `spell_effects` run, so both readings agree at every moment.
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        promised = ctx.gift_to is not None or (obj is not None and obj.cast_gift_to is not None)
        return promised == bool(cond["gift_promised"])
    if "overloaded" in cond:
        # Written onto the object *before* `spell_effects` run, so this reads
        # the object in both lifetimes -- the same shape `kicked` has, and for
        # the same reason: an overloaded permanent's own enters trigger sees
        # only the object, the StackItem having gone.
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        was_overloaded = obj is not None and obj.cast_overloaded
        return was_overloaded == bool(cond["overloaded"])
    if "cost_option" in cond:
        # Read off the object rather than the StackItem, exactly as `overloaded`
        # and `kicked` are: a permanent spell's own enters trigger runs after the
        # item has gone.
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        chosen = obj.cast_cost_option if obj is not None else None
        return chosen == int(cond["cost_option"])
    if "spree_mode" in cond:
        # Spree (702.166a). Read off the object for `cost_option`'s reason, and
        # asked as **membership**: the modes bought are a subset, so "+ {2} —
        # Mill four cards" must fire whenever {2} was among the prices paid,
        # whatever else was paid beside it. An equality test here would make a
        # two-mode cast run one mode, which is the whole bug this key exists to
        # not have.
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        bought = obj.cast_spree_modes if obj is not None else ()
        return int(cond["spree_mode"]) in bought
    if "evoked" in cond:
        # Read in both lifetimes. On the battlefield it is "it's sacrificed
        # when it enters", an ETB trigger; on the stack it is "if the {1}{B}
        # cost was paid", an `if` inside an instant's `spell_effects`. Both
        # read the object, which `stack.resolve` writes *before* the effects
        # run and again as the permanent lands -- `overloaded`'s shape.
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        was_evoked = obj is not None and obj.cast_evoked
        return was_evoked == bool(cond["evoked"])
    if "cast_from_graveyard" in cond:
        # "If this spell was cast from a graveyard, create ten of those tokens
        # instead." Read while the spell is still resolving, so `ctx.source_oid`
        # is the spell itself.
        #
        # `zone_is` cannot answer this: it reports the source's *current* zone,
        # which for any resolving sorcery is the stack, identically whether it
        # was cast from hand or from the graveyard.
        # `of` names a **binding** to ask instead of the source -- Celes, Rune
        # Knight's "…or was cast from a graveyard", which is about the creature
        # that just entered and not about Celes. It is the other half of
        # `entered_from` and cannot be folded into it: a creature *cast* from a
        # graveyard enters from the **stack**, so the zone it entered from
        # answers "stack" and the card would miss exactly the case it names
        # second.
        who = cond.get("of")
        target = ctx.bindings.get(str(who)) if who is not None else ctx.source_oid
        if isinstance(target, list):
            target = target[0] if target else None
        obj = ctx.state.objects.get(target) if isinstance(target, int) else None
        from_graveyard = obj is not None and obj.cast_from_graveyard
        return from_graveyard == bool(cond["cast_from_graveyard"])
    if "cast_from_hand" in cond:
        # "**If this spell was cast from your hand** and you've cast another
        # spell named Approach of the Second Sun this game, you win the game."
        #
        # The sibling of `cast_from_graveyard` directly above, reading the stamp
        # `stack.push_spell` already writes beside it, and it exists because the
        # negation of that one is not this one: a spell cast from exile (foretell,
        # plot, adventure), from a Citadel top or from the command zone was cast
        # from neither a graveyard nor a hand. Approach cares about hand
        # specifically -- a copy of it, which was never cast from anywhere
        # (707.10), must not win the game.
        #
        # `zone_is` cannot answer it for the same reason it cannot answer the
        # graveyard half: it reports the source's *current* zone, which for any
        # resolving sorcery is the stack.
        who = cond.get("of")
        target = ctx.bindings.get(str(who)) if who is not None else ctx.source_oid
        if isinstance(target, list):
            target = target[0] if target else None
        obj = ctx.state.objects.get(target) if isinstance(target, int) else None
        from_hand = obj is not None and obj.cast_from_hand
        return from_hand == bool(cond["cast_from_hand"])
    if "cast_during" in cond:
        # Addendum. Asked of the ability's own source: while the spell resolves
        # that is the spell itself, and once it has become a permanent it is
        # still the same object, so an enters trigger can ask it too.
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        return _cast_during(obj, str(cond["cast_during"]))
    if "combat_damage_by" in cond:
        # Prowl. Answered from the turn ledger rather than from the board,
        # because by the time the spell is cast the creature that got through
        # may be dead, bounced or no longer a Faerie -- and none of those undo
        # the damage the condition is about.
        wanted = cond["combat_damage_by"]
        names = {str(wanted)} if isinstance(wanted, str) else {str(w) for w in wanted}
        return bool(names & ctx.state.turn_ledger.combat_damage_types)
    if "has_flag" in cond:
        # Renown's "if it isn't renowned", written as `{"not": {"has_flag":
        # "renowned"}}`. Asked of the ability's own source, which is the only
        # thing that can have become the word.
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        return obj is not None and str(cond["has_flag"]) in obj.flags
    if "has_turn_flag" in cond:
        # Combat Celebrant's "if this creature hasn't been exerted this turn",
        # written as `{"not": {"has_turn_flag": "exerted"}}`. Asked of the
        # ability's own source, the way `has_flag` above is.
        #
        # Read off the turn ledger and not off the object, so it answers `False`
        # again on the next turn without anything having to remember to erase
        # it -- and so a source that has left the battlefield still answers
        # truthfully about what it did while it was there.
        return ctx.source_oid is not None and ctx.state.turn_ledger.has_object_flag(
            ctx.source_oid, str(cond["has_turn_flag"])
        )
    if "has_city_s_blessing" in cond:
        pids = select_players(ctx, cond["has_city_s_blessing"])
        return any(ctx.state.players[p].has_city_s_blessing for p in pids)
    if "is_monarch" in cond:
        # `any`, matching `has_city_s_blessing` above -- and unlike the blessing
        # it can never be true of two of them, so "if an opponent is the monarch"
        # over `each_opponent` is exact rather than approximate.
        pids = select_players(ctx, cond["is_monarch"])
        return any(ctx.state.monarch == p for p in pids)
    if "no_monarch" in cond:
        return (ctx.state.monarch is None) == bool(cond["no_monarch"])
    if "is_active_player" in cond:
        # "…during **their** turn." A player spec rather than a fixed seat,
        # which is the whole of the difference from `is_your_turn`: that one
        # compares the active player to `ctx.controller`, and a trigger is
        # always evaluated with the ability's own controller there
        # (`triggers._matches`), so it can only ever ask about you.
        #
        # `any`, matching `is_monarch` -- and like the monarchy it can never be
        # true of two seats at once, so the quantifier is exact rather than an
        # approximation. An empty spec (a binding the event never carried) is
        # `False`, which is the safe direction: a "during their turn" clause
        # that cannot tell whose turn it is must not fire.
        pids = select_players(ctx, cond["is_active_player"])
        return any(ctx.state.active_player == p for p in pids)
    if "entered_from" in cond:
        # "…if one or more of them **entered from a graveyard**." Celes.
        # Read off the trigger's own binding rather than the object, because by
        # the time the condition is asked the permanent is on the battlefield
        # and nothing on it remembers where it came from -- `cause` names the
        # mechanism and the same mechanism reaches play from any zone.
        want = cond["entered_from"]
        zones = [want] if isinstance(want, str) else list(want)
        return ctx.bindings.get("from_zone") in zones
    if "was_cast" in cond:
        # 603.6e. Asked of the ability's own source, which for the enters
        # trigger this clause lives on is the permanent that just arrived.
        #
        # `cast_during` enumerated over every phase is the near miss and
        # reduces to `obj.cast_step is not None`: a stamp written once by
        # `stack.push_spell` and cleared by nothing, so a permanent that was
        # cast, died and was reanimated still answers `True` and hands out its
        # enters payload a second time. `not_cause` on the trigger is the other
        # one and names a single cause to refuse, which stops a token copy and
        # nothing else -- not a reanimation, not a blink, not Show and Tell.
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        was_cast = obj is not None and obj.entered_by_cast
        return was_cast == bool(cond["was_cast"])
    if "is_your_turn" in cond:
        return (ctx.state.active_player == ctx.controller) == bool(cond["is_your_turn"])
    if "cmp" in cond:
        op = cond["cmp"]
        left = evaluate_value(ctx, cond.get("left"))
        right = evaluate_value(ctx, cond.get("right"))
        if op == ">=":
            return left >= right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == "<":
            return left < right
        if op in ("=", "=="):
            return left == right
        if op == "!=":
            return left != right
        raise DslError(f"unknown comparison operator {op!r}")

    raise DslError(f"unknown condition {sorted(cond)}")


def _cast_during(obj: Any, spec: str) -> bool:
    """Whether ``obj`` was **cast** in the phase ``spec`` names.

    Read off the step `stack.push_spell` stamped on the object, never off
    `state.step`. Those are two different questions: Unbreakable Formation cast
    in your main phase and answered with a spell that gets countered, or simply
    responded to, still resolves in your main phase -- but the same card cast in
    your main phase in response to something that then moves the turn on must
    still get its addendum, and a card cast in your *end step* must not get one
    merely because nothing has happened since.

    ``False`` for anything never cast. A token, or a permanent an effect put
    onto the battlefield, has no cast at all, and "if you cast this spell" is
    not true of it.
    """
    if obj is None or obj.cast_step is None:
        return False
    if spec.startswith("your_"):
        # The other half of "**your** main phase": `is_your_turn` compares the
        # active player to the controller *now*, which is neither the right
        # moment nor, after a change of control, the right player.
        if not obj.cast_on_own_turn:
            return False
        spec = spec[len("your_") :]
    phase = STEP_PHASE[obj.cast_step]
    if spec == "main":
        return phase in (Phase.PRECOMBAT_MAIN, Phase.POSTCOMBAT_MAIN)
    return phase.value == spec


def evaluate_condition(
    state: GameState,
    cond: Any,
    *,
    controller: int,
    source: int | None = None,
    bindings: Any = None,
) -> bool:
    """Evaluate a condition without an effect already running.

    Used by trigger intervening-if clauses, which are checked both when the
    ability would trigger and again as it resolves.

    ``bindings`` are what the *event* carried -- the creature that entered, the
    land that was played, how many blockers there were. Without them a
    condition may only ask about the board and about its own source, which is
    enough for Threshold and not for evolve: "if that creature has greater
    power than this creature" is a comparison between the trigger's source and
    the object the event was about, and with no bindings the second half reads
    zero and the ability silently never fires.
    """
    ctx = EffectContext(
        state=state,
        controller=controller,
        source_oid=source,
        bindings=dict(bindings) if bindings else {},
    )
    return evaluate(ctx, cond)


def validate_condition(cond: Any, where: str) -> None:
    """Load-time validation of a condition tree."""
    if cond is None or isinstance(cond, bool):
        return
    if not isinstance(cond, Mapping):
        raise DslError(f"{where}: condition must be an object")
    unknown = set(cond) - CONDITION_KEYS
    if unknown:
        raise DslError(f"{where}: unknown condition keys {sorted(unknown)}")

    for key in ("all", "any"):
        if key in cond:
            if not isinstance(cond[key], list):
                raise DslError(f"{where}: {key} takes a list")
            for i, sub in enumerate(cond[key]):
                validate_condition(sub, f"{where}.{key}[{i}]")
    if "not" in cond:
        validate_condition(cond["not"], f"{where}.not")
    if "exists" in cond:
        validate_selector(cond["exists"], f"{where}.exists")
    if "two_share_a_color" in cond:
        # Validated as the pool it is. A bare `true` here would be a card that
        # loads, prints "if two nonland cards that share a color were milled
        # this way" and asks about nothing.
        validate_selector(cond["two_share_a_color"], f"{where}.two_share_a_color")
    if "cmp" in cond:
        validate_value(cond.get("left"), f"{where}.left")
        validate_value(cond.get("right"), f"{where}.right")
    # Not defaulted and not truthiness-tested: `{"no_monarch": "false"}` is a
    # non-empty string and would read as `true`, which would make Crown of
    # Gondor's trigger fire in exactly the case it must not.
    if "no_monarch" in cond and not isinstance(cond["no_monarch"], bool):
        raise DslError(f"{where}.no_monarch: must be true or false")
    if "is_monarch" in cond:
        who = cond["is_monarch"]
        if isinstance(who, str) and who not in PLAYER_SPEC_NAMES:
            raise DslError(
                f"{where}.is_monarch: must name one of {sorted(PLAYER_SPEC_NAMES)} "
                f"or a target/binding, got {who!r}"
            )
    if "is_active_player" in cond:
        who = cond["is_active_player"]
        # `true` is the tempting miss and the reason this is not defaulted:
        # `select_players` refuses a bool outright, so the card would raise at
        # the first trigger instead of at load. `"active_player"` is the other
        # one -- a legal spec that makes the leaf a tautology, and therefore a
        # card whose "during their turn" clause has no clause in it.
        if isinstance(who, bool) or who is None:
            raise DslError(
                f"{where}.is_active_player: needs a player spec -- "
                f"{{'binding': 'event_player'}} for 'during their turn' -- "
                f"got {who!r}"
            )
        if isinstance(who, str):
            if who == "active_player":
                raise DslError(
                    f"{where}.is_active_player: 'active_player' is always true here; "
                    f"name the player the clause is about instead"
                )
            if who not in PLAYER_SPEC_NAMES:
                raise DslError(
                    f"{where}.is_active_player: must name one of "
                    f"{sorted(PLAYER_SPEC_NAMES)} or a target/binding, got {who!r}"
                )
    # Not truthiness-tested, for `no_monarch`'s reason: `{"was_cast": "false"}`
    # is a non-empty string and would read as `true`, which on Wedding Ring is
    # the difference between one copy and one per reanimation.
    if "was_cast" in cond and not isinstance(cond["was_cast"], bool):
        raise DslError(f"{where}.was_cast: must be true or false")
    # A flag name that is not a name matches nothing, so the guard never bites
    # and the once-each-turn clause it was written for is simply absent from a
    # card that reads as though it has one. `true` is the tempting mistake --
    # it stringifies to `"True"`, which no `set_turn_flag` ever wrote.
    if "has_turn_flag" in cond and not (
        isinstance(cond["has_turn_flag"], str) and cond["has_turn_flag"]
    ):
        raise DslError(
            f"{where}.has_turn_flag: needs the name of a flag written by "
            f"set_turn_flag, got {cond['has_turn_flag']!r}"
        )
    # A phase name the turn structure does not have matches nothing, so the
    # addendum clause would simply never fire on a card that prints one --
    # exactly the silent failure the rest of these guards exist for. `"main
    # phase"`, `"precombat"` and `Phase.PRECOMBAT_MAIN` (which stringifies to
    # something no comparison here ever equals) are the tempting misses.
    if "cast_during" in cond and cond["cast_during"] not in CAST_DURING_NAMES:
        raise DslError(
            f"{where}.cast_during: must name one of {sorted(CAST_DURING_NAMES)}, "
            f"got {cond['cast_during']!r}"
        )
    if "combat_damage_by" in cond:
        wanted = cond["combat_damage_by"]
        names = [wanted] if isinstance(wanted, str) else wanted
        if not isinstance(names, (list, tuple)) or not names:
            raise DslError(f"{where}.combat_damage_by: needs a creature subtype, or a list of them")
        if not all(isinstance(n, str) and n for n in names):
            # An empty or non-string entry would match nothing, and prowl's whole
            # content is which types got through -- so the alternative cost would
            # simply never be offered, on a card that reads as though it is.
            raise DslError(
                f"{where}.combat_damage_by: every entry must be a subtype name, got {names!r}"
            )


def _two_share_a_color(ctx: EffectContext, selector: Mapping[str, Any]) -> bool:
    """Do any two cards in this pool have a colour in common?

    "If two nonland cards that share a color were milled this way, repeat this
    process" -- Sphinx's Tutelage. A **relation between two members** of a pool,
    which is what makes it a condition of its own rather than a selector clause:
    every other colour reader in the language asks a question about one card.
    `colors` and `not_colors` test against a colour fixed when the card is
    written; `min_colors` counts the colours on a single object; and
    `shares_a_color_with` resolves its argument through `_bound_oid`, which reads
    one oid and returns ``None`` for a list -- and a `mill`'s `as` binding is
    always a list, so that clause matches nothing at all when pointed here.

    `exists` with a count is the near miss and drops the colour clause entirely:
    "two nonland cards were milled" repeats on almost every mill, which is a far
    longer loop than the card prints.

    Colourless cards share no colour with anything, which falls out of the
    intersection being empty and is the printed ruling: two colourless cards do
    not continue the process. Pairwise, and short-circuiting on the first pair
    found -- the question is whether *any* two share, not how many do.

    Colours are read the way `selectors.matches` reads them, derived on the
    battlefield and printed anywhere else. The cards this is asked about are in a
    graveyard, so it is the printed face, which is what "cards ... milled this
    way" means.
    """

    seen: list[frozenset[str]] = []
    for oid in resolve_pool(ctx, selector):
        obj = ctx.state.objects.get(oid)
        if obj is None:
            continue
        if obj.on_battlefield:
            colors = frozenset(chars(ctx.state, oid).colors)
        else:
            colors = frozenset(ctx.state.card_of(obj).colors)
        if any(colors & other for other in seen):
            return True
        seen.append(colors)
    return False
