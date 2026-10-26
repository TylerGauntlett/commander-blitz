"""The selector DSL -- how card JSON describes "which objects".

A selector is a dict.  Every key is optional and all present keys must match::

    {"zone": "battlefield", "controller": "you", "types": ["Creature"],
     "power": {"op": ">=", "value": {"const": 3}}, "count": 1, "chooser": "controller"}

Two shorthand forms bypass matching entirely:

    {"target": "t1"}     the refs chosen for target spec ``t1`` at cast time
    {"binding": "subject"}  the object a trigger bound (the land that was played, ...)
"""

from __future__ import annotations

from collections.abc import Generator, Mapping
from typing import TYPE_CHECKING, Any

from ..characteristics import _base_pt, chars, creature_types_of, resolve_chosen_subtypes
from ..enums import CardType, Supertype, Zone
from ..errors import DslError
from ..mana import printed_cost_is, validate_printed_cost_list
from ..player_statics import commander_subtypes
from .context import EffectContext, ask_objects

if TYPE_CHECKING:  # pragma: no cover
    from ..state import GameState

#: Card types a selector may name.  Derived from the enum rather than imported
#: from ``cards.loader``, which imports this module.
KNOWN_TYPES = frozenset(t.value for t in CardType)

#: Supertypes a selector may name, from the enum for the same reason.  There are
#: three of them, which is what makes a typo here so much worse than a typo in a
#: subtype: ``not_supertypes: ["basic"]`` forbids nothing at all, and a Field of
#: Ruin that will happily destroy a Mountain is a different card.
KNOWN_SUPERTYPES = frozenset(s.value for s in Supertype)

#: Every key a selector may contain.  The loader validates against this set, so a
#: misspelled key is a load-time error rather than a silently ignored filter.
SELECTOR_KEYS = frozenset(
    {
        "zone",
        "controller",
        #: "A commander **you own** on the battlefield or in the command zone"
        #: (Majestic Genesis).  Ownership rather than control, read off
        #: ``GameObject.owner`` -- written once when the object is made and left
        #: alone by ``change_control``, so it is the one relation on a permanent
        #: that a control-changing effect cannot move.
        #:
        #: `controller` is the near miss and is a genuinely different set in a
        #: game this engine can reach, because `gain_control` is implemented:
        #: 903.3 defines a commander by *ownership*, so `controller: "you"`
        #: misses your own commander while an opponent holds it and counts an
        #: opponent's commander you have stolen.  Either way the number a card
        #: reads off the pool comes out wrong, and silently.
        #:
        #: The same word, in the same sense, that `STATIC_FILTER_KEYS` and the
        #: cost-reduction filter have read since Visions of Glory -- which
        #: spells this exact printed clause in a `mana_reduction`.  One
        #: difference, and it is because the two languages default differently:
        #: a static's filter defaults `controller: "you"` and so `owner` has to
        #: *suppress* that default, while an effect-side selector defaults
        #: nothing, so `owner` simply filters and composes with a `controller`
        #: written beside it.
        "owner",
        #: Whose hand/graveyard/library/exile to walk, as a full player spec
        #: rather than the three words ``controller`` allows -- so
        #: ``{"target": "t1"}`` scopes a zone to the one player a trigger
        #: targeted.  Bojuka Bog: "exile **target player's** graveyard", which
        #: `controller: "any"` would turn into Relic of Progenitus.
        #:
        #: Battlefield selectors ignore it, and correctly: a permanent's
        #: controller is a property of the object, so `controller` is a filter
        #: there rather than a choice of which list to read.
        "player",
        #: "Equipped creature", "enchanted creature" -- the permanent this Aura
        #: or Equipment is attached to, read off the ability's source.  Already
        #: in ``STATIC_FILTER_KEYS``; this is the same word on the effect side.
        "attached",
        #: "Choose two cards in your hand **drawn this turn**" -- Sylvan Library.
        #: `GameState.cards_drawn_this_turn` says how many and no selector could
        #: ask which; this reads the mark `draw_cards` puts on each card as it is
        #: drawn. Effect-side only: nothing continuous asks the question.
        "drawn_this_turn",
        #: "**modified** creatures you control" (Silkguard, and the whole Kamigawa
        #: cycle) -- a permanent with a counter on it, equipped, or enchanted by
        #: an Aura you control. A definition rather than a characteristic, which
        #: is why it is one key and not three: a card that spelled it out would
        #: have to say "or" across three unrelated relationships, and the
        #: selector language is a conjunction.
        "modified",
        "types",
        #: "target artifact **or** enchantment".  ``types`` is a conjunction --
        #: ``["Artifact", "Enchantment"]`` means a permanent that is both -- and
        #: the any-of form already existed for ``subtypes`` and ``colors`` and
        #: simply had no type equivalent.  ``not_types`` cannot stand in: the
        #: complement is only equal for single-typed permanents, so it would
        #: refuse artifact creatures, which the printed line accepts.
        "any_types",
        #: **One pool built from several**, each with its own zone -- "you may
        #: exile a nonland card from their **hand** or the chosen creature"
        #: (Cloak and Dagger, Entwined), where the two halves are a hand and the
        #: battlefield. Every branch is resolved in its own right and the
        #: results are concatenated, so one `count`/`chooser` then asks across
        #: the lot.
        #:
        #: Not `any_of`, which is the near miss and is a *filter*: it narrows
        #: the pool the outer selector already gathered from one zone, and
        #: refuses a `zone` inside a branch for exactly that reason. A card
        #: choosing "from their hand or the battlefield" has no one zone to
        #: gather from, so there is nothing for `any_of` to narrow.
        "union",
        #: A union of whole sub-selectors: matches when *any* of them does.
        #: "…among it and any number of commanders" is not a filter that can
        #: be narrowed into -- `self_only` and `is_commander` are both true
        #: of neither object -- so it needs an or across two descriptions
        #: rather than an or inside one key.
        "any_of",
        "not_types",
        "subtypes",
        "not_subtypes",
        "supertypes",
        #: "Destroy target **nonbasic** land an opponent controls" -- Field of
        #: Ruin, Ghost Quarter, Tectonic Edge.  A supertype the permanent must
        #: *lack*, which `supertypes` cannot say: it is a positive subset test,
        #: so it can require Basic and never forbid it.
        #:
        #: `not_subtypes` over the five basic land types is not the same filter
        #: and the difference is the whole card: it would spare every nonbasic
        #: land that carries a basic land type -- Hallowed Fountain, Murmuring
        #: Bosk, Dryad Arbor -- which is exactly what these cards are printed to
        #: answer.  `mana_value` cannot separate them either; both are 0.
        "not_supertypes",
        "colors",
        "not_colors",
        #: "Two or more colors", which `colors` cannot say: that is a membership
        #: test, so `["U", "R"]` matches a mono-blue permanent.
        "min_colors",
        #: "Colorless creatures you control get +2/+2"; "whenever you cast a
        #: **colorless** spell" -- Forsaken Monument. 105.2c: an object with no
        #: colour is colorless, and colorless is not a colour, so `colors` has
        #: no letter for it (an empty list there is no test at all). `true`
        #: matches an object with zero colours and `false` one with at least
        #: one. `not_colors` over all five letters says the same thing here,
        #: but only here: the static and trigger filter languages carry this
        #: key and not that one.
        "colorless",
        "keywords",
        "not_keywords",
        "tapped",
        #: "…with counters on them" / "…with a counter on it": one or more
        #: counters of any kind. Also a static filter key (Innkeeper's Talent).
        "has_counters",
        "attacking",
        #: "Whenever an opponent attacks **you** with two or more creatures" --
        #: Trouble in Pairs. A creature attacking this player *itself*, and not
        #: one of their planeswalkers: 506.2/508.1b make the player and each
        #: planeswalker they control separate things to attack, so a creature
        #: sent at your planeswalker is not attacking you.
        #:
        #: `attacking` is the near miss and has no notion of whom. The
        #: `attackers` binding of `creatures_attack_player` with `defending:
        #: "you"` is the other one and is deliberately wider: `combat.attackers`
        #: records the defending *player* for a planeswalker attack too, which
        #: is exactly Mangara, the Diplomat's "attacking you and/or planeswalkers
        #: you control" and one creature too many for Trouble in Pairs. This key
        #: narrows that binding (or any pool) by also reading
        #: `combat.attacking_permanent`. `"you"`, `"opponent"` or `"any"`
        #: (some player, never a planeswalker), relative to the ability's
        #: controller.
        "attacking_player",
        #: "Untap all creatures that **attacked this turn**" -- Relentless
        #: Assault, Aggravated Assault, Seize the Day. Not `attacking`, which is
        #: live combat state and is false for everything by the time these
        #: sorceries resolve: they are cast in a main phase, after the combat
        #: they are talking about, and `end_combat` has set `state.combat` to
        #: `None`. Answered from `TurnLedger.creatures_attacked`, the same
        #: per-turn record the `attackers_this_turn` value counts.
        "attacked_this_turn",
        #: "For each token you control **that entered this turn**, create a
        #: token that's a copy of it" -- Ocelot Pride. Answered from
        #: ``TurnLedger.entered_this_turn``, the same record
        #: `permanents_entered_this_turn` counts -- but this gathers the objects
        #: rather than counting them, which is what `for_each` needs to bind
        #: `each` for the copy.
        #:
        #: The reading already existed in the other three filter languages --
        #: `characteristics._matches` for statics, `cost_reduction._object_matches`
        #: and `triggers.matches_card_filter` -- and only the effect-side selector
        #: could not say it. `created_with: "self"` is the near miss and answers a
        #: narrower question: only the tokens *this source* made, which misses
        #: every token another card made this turn.
        "entered_this_turn",
        "blocking",
        "is_commander",
        "is_token",
        "power",
        #: "…each with **base** power or toughness 1 or less" -- Angelic
        #: Aberration. 613.2 layer 7a/7b: the copiable size, before
        #: counters, anthems, Auras, Equipment and pump. `power` and
        #: `toughness` above read the *live* value, and on any board with a
        #: counter or an anthem the two name different creatures in both
        #: directions.
        "base_power",
        "base_toughness",
        "toughness",
        "mana_value",
        #: "Counter target spell **with {X} in its mana cost**" -- Frontline
        #: Medic, Ertai's Meddling, Sunder Shaman. A question about the mana
        #: *symbols* printed on the face being cast, not about any number:
        #: `ManaCost.x_count`, which the parser has always counted and nothing
        #: had ever read back.
        #:
        #: `mana_value` is the only other cost reader here and it cannot say it
        #: in either direction. `ManaCost.mana_value` scores X as 0 (202.3b
        #: "X is considered to be 0" off the stack), so Fireball `{X}{R}` and
        #: Shock `{R}` are both mana value 1 and one comparison catches both or
        #: neither. Nor would a 202.3b-correct mana value on the stack fix it:
        #: a Fireball announced for X=0 still *has* {X} in its mana cost, and is
        #: still a legal target, while its mana value is Shock's exactly.
        #: `mana_symbols` is a value rather than a selector key and its `of`
        #: is restricted to W/U/B/R/G, so it cannot filter a pool and has no
        #: spelling for X.
        "x_in_mana_cost",
        #: "Search your library for an artifact card **with mana cost {0} or
        #: {1}**" -- Urza's Saga. A list of printed costs, any of which matches,
        #: compared symbol for symbol (`mana.printed_cost_is`). `mana_value`
        #: cannot say it: an artifact land has no mana cost and mana value 0, and
        #: `{X}` scores 0 too, so `mana_value <= 1` finds both and the printed
        #: card finds neither.
        "mana_cost",
        "exclude_self",
        #: "each **other** attacking creature" -- exclude whichever object a
        #: trigger bound under this name.  `exclude_self` cannot do it: it
        #: compares against the *ability source*, which for Shared Animosity is
        #: the enchantment, so it removes nothing from a set of attackers and
        #: the count is over by exactly one.
        #:
        #: Excludes the whole **set** a binding holds, not just its first oid --
        #: `as` on `create_token` records a list, and Martial Coup's "destroy all
        #: other creatures" has to spare every Soldier it just made.
        "exclude_binding",
        #: "…that shares a creature type with it".  Matches when the candidate's
        #: subtypes intersect those of the object bound under this name, read
        #: from *derived* characteristics on both sides so changelings and
        #: granted types count.  Not expressible with `subtypes`, which takes a
        #: literal list fixed when the card is written.
        "shares_a_type_with",
        #: "Whenever you cast a spell that shares a **creature type** with this
        #: creature…" -- Folk Hero's grant. `"self"` (the object that has the
        #: ability -- for a granted trigger, the recipient) or a binding name.
        #: Creature types only (205.3m), where `shares_a_type_with` intersects
        #: every subtype: a Background, Aura or Arcane is a subtype and not a
        #: creature type. Honoured by trigger filters as well as here; a trigger
        #: filter may only say `"self"`, since nothing is bound when it is asked.
        "shares_a_creature_type_with",
        #: "…another permanent you control that **shares a permanent type**
        #: with it" -- Cloudstone Curio. The card-type twin of the clause
        #: above, reading `types` where that one reads `subtypes`. A separate
        #: key rather than a mode, because the two ask different questions and
        #: the wrong one is quietly narrower: on this card the subtype reading
        #: finds another Goblin when a Goblin enters and nothing at all when a
        #: land does. `types` takes a literal list fixed when the card is
        #: written, and which permanent type matters is decided at resolution.
        "shares_permanent_type_with",
        #: "…and all tokens that player controls **with the same name as that
        #: permanent**" -- Legions to Ashes. The dynamic twin of `name`, which
        #: takes a literal string fixed when the card is written; which name
        #: matters here is decided by whatever was targeted at cast time.
        #: Compared on `card.name`, since nothing in the characteristics layer
        #: renames an object, and tolerant of a target that has already left the
        #: battlefield -- the spell exiles the target and its copies together,
        #: so a reading that needed the target still in play would sweep nothing
        #: whenever the ops ran in the other order.
        "shares_a_name_with",
        #: "…a creature spell that shares a creature type with **your
        #: commander**." Path of Ancestry. Takes a *player* rather than a
        #: binding name, which is why it is not a spelling of the clause above:
        #: nothing binds the commander, the commander is not what the trigger is
        #: about, and it is usually in the command zone rather than on the
        #: battlefield, so `_bound_oid` has nothing to find and `is_commander`
        #: asks the wrong question -- it is a predicate on the object being
        #: tested, not a reference to compare a different object against.
        #: A literal `subtypes` list cannot stand in either: which type matters
        #: is a property of the deck the card is played in.
        "shares_a_type_with_commander",
        #: "When **that mana** is spent to cast a spell…" -- Path of Ancestry,
        #: Opal Palace. A trigger filter only, matched against the spell: the
        #: permanents whose mana abilities paid for it are recorded on the spell
        #: by `pay_mana`, which is the only instant they are knowable.
        #:
        #: Also takes a **selector** -- "…if mana from a Treasure was spent to
        #: cast it" (Smaug, Wicked Worm), a class of permanents rather than one
        #: named object. That half matches what each source *was*, snapshotted
        #: onto the pip, because the Treasure is sacrificed to make its mana and
        #: its oid resolves to nothing by the time the spell is on the stack.
        #: Its legal keys are `PAID_BY_SELECTOR_KEYS`, not these.
        "paid_by",
        #: "…and each other creature that shares a color with it" -- radiance.
        #: The colour twin of the clause above, and it needs its own key for the
        #: same reason: `colors` takes a literal list written into the card, and
        #: which colour matters is decided by whatever was targeted. Read from
        #: **derived** colours on both sides, so a creature made black by
        #: another spell is caught. A colorless object shares a colour with
        #: nothing, itself included.
        "shares_a_color_with",
        "self_only",
        #: "…with the least toughness among creatures you control" -- bolster.
        #: Narrows the pool to whatever is tied for the extreme *after* every
        #: other clause has filtered it, because an extremum is a fact about the
        #: pool and not about any one candidate.
        "extreme",
        "count",
        #: "You may reveal **a** Human or artifact card from among them and put
        #: it into your hand." -- Boromir, Gondor's Hope, and every "look at the
        #: top N, you may take one" card printed since. Alongside an integer
        #: `count` it means "exactly that many, or none": the pick is bounded at
        #: N and the chooser may decline it, which is `min_count = 0` with
        #: `max_count` left at N.
        #:
        #: None of the three `count` spellings says it. A value forces exactly
        #: N -- the number becomes both bounds, so "You may" is silently deleted
        #: -- and `"any"` is min 0 / max *pool*, which would take every Human and
        #: artifact among the six rather than one. Wrapping the op in `may` is a
        #: different card again: it gates the whole effect list, so declining
        #: also skips the mandatory look and the mandatory "put the rest on the
        #: bottom", and it asks before anything has been seen, which is the one
        #: thing this clause is printed to prevent.
        #:
        #: Named after `TargetModel.optional`, which is this exact shape on the
        #: declared-target side ("exactly N, or none"). These pools are not
        #: targeted -- `look_at_top` bounds its own from the top of a library --
        #: so the word had to be spelled a second time here rather than reused.
        "optional",
        "chooser",
        "random",
        "target",
        "binding",
        "object_kind",
        "name",
        #: "…search your library for up to five Dragon cards **not named
        #: Tiamat**" -- the negation twin of `name`, and the one the `not_*`
        #: family was missing. Takes a string, or a list when a card names more
        #: than one ("not named Griselbrand or Emrakul"), since two `not_name`
        #: keys cannot sit in one selector.
        #:
        #: `exclude_self` is the near miss and is a different question: it
        #: excludes *this object*, and the card being excluded here is a second
        #: copy of Tiamat sitting in the library, which `exclude_self` never
        #: sees. Leaving the clause off is not a safe approximation either --
        #: a deck running two Tiamats would tutor the other one.
        "not_name",
        "damaged",
        # "…until this permanent leaves the battlefield." Cards in exile that
        # *this* source put there, read back by its own leaves-trigger.
        "exiled_with",
        "phased_out_with",
        #: "…exile all other tokens **created with this creature**" -- Faerie
        #: Artisans. The tokens this object's own effects created, read off the
        #: source's `created_tokens`; `"self"` is the only spelling. Scoped to
        #: this *object*, so tokens a previous incarnation made (400.7) and
        #: tokens another permanent made are not in it. "Other" is
        #: `exclude_binding` over the `as` the creating op wrote.
        "created_with",
        # "…dealt damage by this creature this turn." A trigger filter rather
        # than an object filter: answered from the per-turn damage ledger,
        # because the creature it asks about has usually just died.
        "damaged_by",
        #: "…an unblocked attacking creature you control" -- ninjutsu. Asks
        #: whether anything is blocking *this attacker*, which is not the
        #: negation of `blocking`: that key is about a blocker, and these are
        #: two different creatures.
        "blocked",
        # "When the creature this card haunts dies…" -- a trigger filter only,
        # answered off the ability's source, which is the card sitting in exile
        # with the link on it. The haunted creature carries no record of it.
        "haunted_by",
        # "…the creature this card is encoded on" -- cipher, the same shape as
        # `haunted_by` and answered the same way, off the ability source.
        "encoded_by",
    }
)

#: The only keys a selector-valued `paid_by` may use -- everything
#: :class:`mana.ManaOrigin` actually snapshots, and nothing else.
#:
#: A closed list rather than the full `SELECTOR_KEYS`, because what is being
#: filtered is a *memory* of a permanent and not a permanent: "tapped",
#: "attacking", a P/T comparison or a zone have no answer about an object that
#: was sacrificed three cost-payments ago. Read through the general selector
#: machinery they would all be silently false, which is the failure mode this
#: capability exists to fix, so they are refused at load time instead.
PAID_BY_SELECTOR_KEYS = frozenset(
    {"name", "types", "any_types", "not_types", "subtypes", "supertypes", "controller"}
)


ZONE_NAMES = {z.value: z for z in Zone}


def resolve_pool(ctx: EffectContext, selector: Mapping[str, Any] | None) -> list[int]:
    """Every object matching ``selector``, before ``count``/``chooser`` narrowing."""
    if selector is None:
        return []
    # `target` and `binding` name a pool directly rather than searching a zone.
    # On their own they are the whole selector; combined with other keys they are
    # the *source* and the rest still filters, which is what lets a card ask "is
    # the card I just bound a land?" without a condition language of its own.
    if "target" in selector or "binding" in selector:
        # `zone` still filters when the card writes one, but its *default* is not
        # the same on the two branches, because they are asking different
        # questions.
        #
        # A target is re-checked as the spell resolves (608.2b), so "target
        # creature" that is no longer a creature on the battlefield is no longer
        # a legal target and the default `battlefield` is the check.
        #
        # A binding written by an earlier op in this same resolution is a
        # *record*: "the number of creature cards exiled **this way**" is a fact
        # about what was exiled, and those cards have by construction just
        # changed zones. Defaulting to `battlefield` there does not narrow the
        # set, it empties it -- silently, since nothing is malformed -- so
        # `{"binding": "exiled", "types": ["Creature"]}` would count 0 and the
        # card would enter with no counters. Devour and amplify never noticed
        # because they read the bare `{"binding": …}`, which never reaches
        # `matches` at all.
        if "target" in selector:
            seeded = ctx.target_oids(str(selector["target"]))
            default_zone: str | None = "battlefield"
        else:
            seeded = _bound_oids(ctx, str(selector["binding"]))
            default_zone = None
        if set(selector) <= {"target", "binding"}:
            return seeded
        return _narrow_to_extreme(
            ctx,
            [oid for oid in seeded if matches(ctx, oid, selector, default_zone=default_zone)],
            selector,
        )

    if (branches := selector.get("union")) is not None:
        # One pool assembled from several, each branch resolved in its own
        # right -- so each may name its own zone, which is the whole difference
        # from `any_of` beside it. Order is the written order and duplicates are
        # dropped, because a branch that overlaps another is one card offered
        # once, not twice.
        #
        # The outer selector carries nothing but the pool-shaping keys (the
        # loader refuses the rest), so there is no filtering to do here and no
        # default zone to apply: a filter written outside would have to mean
        # something for a card in a hand *and* for a permanent, and the two
        # answer to different layers.
        pooled: list[int] = []
        for branch in branches:
            for oid in resolve_pool(ctx, branch):
                if oid not in pooled:
                    pooled.append(oid)
        return pooled

    state = ctx.state
    zone_name = selector.get("zone", "battlefield")
    zone = ZONE_NAMES.get(zone_name)
    if zone is None:
        raise DslError(f"unknown zone {zone_name!r} in selector")

    candidates: list[int] = []
    if "phased_out_with" in selector:
        # A phased-out permanent is "treated as though it does not exist"
        # (702.26c) and is *out of* `state.battlefield`, so the ordinary
        # battlefield pool cannot reach it -- which is why Oubliette could not
        # be written before this. The link is what makes naming it safe: this
        # pool is every phased-out object, and the `phased_out_with` filter
        # below narrows it to the ones this permanent itself sent away.
        candidates = [oid for oid, obj in state.objects.items() if obj.phased_out]
    elif zone is Zone.BATTLEFIELD:
        candidates = list(state.battlefield)
    elif zone is Zone.STACK:
        candidates = [item.oid for item in state.stack if item.oid is not None]
    else:
        for pid in _zone_owners(ctx, selector):
            candidates.extend(state.players[pid].zone_list(zone))

    return _narrow_to_extreme(
        ctx, [oid for oid in candidates if matches(ctx, oid, selector)], selector
    )


#: What `extreme` may rank on. Derived characteristics only, and read through
#: `chars` -- "the creature with the least toughness" means the toughness it
#: actually has, counters and anthems included.
EXTREME_KEYS = frozenset({"power", "toughness", "mana_value"})


def _narrow_to_extreme(
    ctx: EffectContext, pool: list[int], selector: Mapping[str, Any]
) -> list[int]:
    """Keep only the objects tied for the highest or lowest of some quantity.

    "Choose a creature with the **least toughness** among creatures you
    control" -- bolster, and the shape every "greatest/least" line on a card
    wants. It cannot be a `_compare` clause: those test each candidate against a
    value known in advance, and an extremum is only knowable once the whole pool
    is in hand.

    Ties are all kept rather than broken here. Rule 701.36a has the *player*
    choose among equals, and `choose_objects` is already the thing that asks --
    so narrowing to one would silently take that choice away, and picking by oid
    would make it depend on the order permanents happened to arrive in.
    """
    spec = selector.get("extreme")
    if spec is None or not pool:
        return pool
    if not isinstance(spec, Mapping):
        raise DslError(f"bad extreme spec {spec!r}")
    of = str(spec.get("of", "power"))
    if of not in EXTREME_KEYS:
        raise DslError(f"cannot rank on {of!r}; extreme allows {sorted(EXTREME_KEYS)}")
    pick = str(spec.get("pick", "greatest"))
    if pick not in ("greatest", "least"):
        raise DslError(f"unknown extreme pick {pick!r}; use 'greatest' or 'least'")

    def rank(oid: int) -> int:
        if of == "mana_value":
            obj = ctx.state.objects.get(oid)
            return ctx.state.card_of(obj).mana_value if obj is not None else 0
        c = chars(ctx.state, oid)
        return c.power if of == "power" else c.toughness

    best = (max if pick == "greatest" else min)(rank(oid) for oid in pool)
    return [oid for oid in pool if rank(oid) == best]


def _bound_oid(ctx: EffectContext, name: str) -> int | None:
    """The oid a trigger bound under ``name``, if it bound an object at all.

    A binding is sometimes an oid and sometimes a snapshot dict (see the
    ``snapshot`` op), so both spellings are read here rather than at each of the
    three call sites that need them.
    """
    value = ctx.bindings.get(name)
    if isinstance(value, Mapping):
        value = value.get("oid")
    return int(value) if isinstance(value, int) else None


def _commander_subtypes(ctx: EffectContext, who: str) -> frozenset[str]:
    """Every creature type the named players' commanders currently have.

    A separate clause from `shares_a_type_with` rather than a reserved binding
    name, because it takes a **player** and not an object: nothing binds the
    commander, the commander is not what the effect is about, and it is usually
    in the command zone rather than on the battlefield, so `_bound_oid` has
    nothing to find.

    The set itself comes from `characteristics.commander_subtypes`, shared with
    `triggers.matches_card_filter` so the two halves of the filter language
    cannot disagree about what a commander's types are.
    """

    out: set[str] = set()
    for pid in select_players(ctx, who):
        out |= commander_subtypes(ctx.state, pid)
    return frozenset(out)


def _bound_oids(ctx: EffectContext, name: str) -> list[int]:
    """Every object bound under ``name`` -- one, or a whole set of them.

    A binding is one oid for the trigger bindings and snapshots that have always
    existed, and a **list** for an op that recorded what it chose (``as``).
    Amplify and devour both need the list form: "X is the number of cards
    revealed this way" and "for each creature devoured" are counts of a set that
    a player picked a moment ago, and no selector can name it afterwards -- the
    revealed cards are still in a hand full of others, and the devoured
    creatures are gone.
    """
    value = ctx.bindings.get(name)
    if isinstance(value, (list, tuple)):
        return [int(v) for v in value if isinstance(v, int)]
    bound = _bound_oid(ctx, name)
    return [bound] if bound is not None else []


def _zone_owners(ctx: EffectContext, selector: Mapping[str, Any]) -> list[int]:
    """Whose hand/graveyard/library/exile this selector walks.

    ``player`` is the full player spec and takes precedence, because it can say
    things ``controller`` cannot: "target player's graveyard" is Bojuka Bog, and
    the nearest `controller` value -- `"any"` with `count: "all"` -- exiles every
    graveyard at the table, which is Relic of Progenitus. `select_players`
    already understood `{"target": ...}`; it simply had no caller here.
    """
    if "player" in selector:
        return select_players(ctx, selector["player"])
    # `owner` stands in for `controller` when only it was written, because in a
    # zone somebody owns the two words name the same seat: 400.3 sends a card to
    # its **owner's** hand, library and graveyard, and exile is kept per owner
    # here for the same reason. Without this the default below would quietly
    # re-impose "you" on a selector that deliberately said `owner: "any"`, and a
    # card asking about every graveyard at the table would read only its own --
    # the silent narrowing `player` is validated to prevent, arriving through
    # the other door.
    if "controller" not in selector and (own := selector.get("owner")) is not None:
        controller = own
    else:
        controller = selector.get("controller", "you")
    if controller == "you":
        return [ctx.controller]
    if controller == "opponent":
        return ctx.opponents()
    # "…enchanted player's graveyard". Named here as well as in `matches`,
    # because a zone selector picks *whose list to walk* rather than filtering
    # objects, and a name this function did not know fell through to
    # `alive()` -- every seat at the table, which for a hand or a graveyard is
    # the widest possible reading of a sentence naming one player.
    if controller == "enchanted_player":
        return select_players(ctx, controller)
    return ctx.state.alive()


def _resolve_chosen_card_type(
    selector: Mapping[str, Any], source: Any
) -> Mapping[str, Any]:
    """Turn ``types: [{"chosen_card_type_of": "self"}]`` into the chosen type.

    The card-type twin of `characteristics.resolve_chosen_subtypes`, and it
    makes the same choice at the same boundary: a source that has chosen nothing
    yet matches **nothing**. "All cards of the chosen type" before a type is
    chosen should return nothing, not the whole graveyard -- and the sentinel is
    a name no card has for exactly that reason.
    """
    out: list[str] = []
    for entry in selector["types"]:
        if not isinstance(entry, Mapping):
            out.append(entry)
            continue
        if entry.get("chosen_card_type_of") == "self":
            chosen = getattr(source, "chosen_card_type", None)
            if chosen is None:
                return {**selector, "types": ["\0none"]}
            out.append(chosen)
    return {**selector, "types": out}


def _is_modified(ctx: EffectContext, oid: int) -> bool:
    """"Modified" -- a counter on it, an Equipment attached, or your Aura.

    The keyword-action definition, and each of its three limbs is a different
    relationship read from a different direction:

    - **a counter of any kind**, not just +1/+1. A Role's, a loyalty counter, a
      stun counter -- the reminder text says "counters" and means it.
    - **equipped**, by anybody's Equipment. An Equipment stapled to your
      creature by an opponent still modifies it; the definition asks what is
      attached, not who owns it.
    - **enchanted by an Aura you control.** This limb *does* ask, and it is the
      one asymmetry in the definition: an opponent's Pacifism does not make your
      creature modified. "You" is the effect's controller, since that is who the
      sentence naming modified creatures belongs to.

    Answered by walking the battlefield for attachments rather than by reading a
    list on the creature, because attachment is stored one way -- on the Aura or
    Equipment, as `attached_to` -- and nothing walks back along it. That is the
    same fact `attached_to_host` is built on, one relationship read from the
    other end.
    """
    state = ctx.state
    obj = state.objects.get(oid)
    if obj is None:
        return False
    if any(n > 0 for n in obj.counters.values()):
        return True
    for other_oid in state.battlefield:
        other = state.objects.get(other_oid)
        if other is None or other.attached_to != oid:
            continue
        subtypes = chars(state, other_oid).subtypes
        if "Equipment" in subtypes:
            return True
        if "Aura" in subtypes and other.controller == ctx.controller:
            return True
    return False


def matches(
    ctx: EffectContext,
    oid: int,
    selector: Mapping[str, Any],
    *,
    default_zone: str | None = "battlefield",
) -> bool:
    """Does one object satisfy every clause of ``selector``?

    ``default_zone`` is what an absent ``zone`` clause means. It is the
    battlefield everywhere a selector *searches* a zone, and ``None`` -- no zone
    clause at all -- when the pool was named rather than searched by a
    ``binding``; see `resolve_pool`.
    """
    state = ctx.state
    obj = state.objects.get(oid)
    if obj is None:
        return False

    zone_name = selector.get("zone", default_zone)
    zone = ZONE_NAMES.get(zone_name) if zone_name is not None else None
    if zone is not None and obj.zone is not zone:
        return False

    # "…if it's a creature card **of the chosen type**." Herald's Horn asks this
    # about the top card of a library, where no trigger has bound an object and
    # no static is being computed -- so the substitution the characteristics
    # layer already does for `affects` and for trigger filters has to happen on
    # the effect side too. Resolved against the ability's own source, which is
    # the permanent that made the choice. `not_subtypes` too -- Kindred
    # Judgment's "destroy all creatures that **aren't** of the chosen type",
    # where the spell itself made the choice.
    if selector.get("subtypes") or selector.get("not_subtypes"):
        selector = resolve_chosen_subtypes(
            selector, state.objects.get(ctx.source_oid) if ctx.source_oid else None
        )
    # "Return all cards of **the chosen type** from your graveyard" -- Creeping
    # Renaissance. The card-type twin of the substitution above, and effect-side
    # only: no printed card reads a chosen permanent type from a static.
    if selector.get("types") and any(isinstance(e, Mapping) for e in selector["types"]):
        selector = _resolve_chosen_card_type(
            selector, state.objects.get(ctx.source_oid) if ctx.source_oid else None
        )

    card = state.card_of(obj)
    use_derived = obj.on_battlefield
    c = chars(state, oid) if use_derived else None
    types = c.types if c else card.types
    subtypes = c.subtypes if c else card.subtypes
    supertypes = c.supertypes if c else card.supertypes
    colors = c.colors if c else card.colors
    keywords = c.keywords if c else card.keywords

    if selector.get("exclude_self") and oid == ctx.source_oid:
        return False
    if selector.get("self_only") and oid != ctx.source_oid:
        return False
    # "…put a +1/+1 counter on **equipped creature**." Blade of the Bloodchief.
    # `attached` had existed only in `STATIC_FILTER_KEYS`, where
    # `characteristics` reads it while applying a continuous effect -- which is
    # why "Equipped creature gets +1/-1" always worked and no *op* could reach
    # the same creature. Read off the ability's source, and off its remembered
    # attachment too, so a trigger that fires as the creature leaves can still
    # find it.
    if selector.get("attached"):
        source = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        if source is None or oid not in (source.attached_to, source.last_attached_to):
            return False
    if selector.get("modified") and not _is_modified(ctx, oid):
        return False
    if selector.get("drawn_this_turn") and obj.drawn_turn != state.turn:
        # Compared against the turn rather than read as a flag, so nothing has
        # to clear it at a turn boundary -- a stale `true` would read as a card
        # drawn this turn that was not.
        return False
    if (name := selector.get("exclude_binding")) is not None and oid in _bound_oids(ctx, str(name)):
        # `_bound_oids`, not `_bound_oid`: a binding is one oid for a trigger or
        # a `snapshot`, and a **list** for an op that recorded what it produced.
        # Martial Coup writes X Soldiers with `as` and then says "destroy all
        # *other* creatures"; the singular reader returned `None` for that list,
        # so the exclusion matched nothing and the spell wrathed the tokens it
        # had just made. Reading one oid out of the list would be worse -- it
        # would spare exactly one Soldier and look almost right.
        return False
    if (name := selector.get("shares_a_type_with")) is not None:
        other = _bound_oid(ctx, str(name))
        if other is None:
            return False
        theirs = chars(state, other).subtypes if state.objects.get(other) else frozenset()
        if not (subtypes & theirs):
            return False
    if (name := selector.get("shares_permanent_type_with")) is not None:
        # "…another permanent you control that shares a **permanent type** with
        # it" -- Cloudstone Curio. The card-type twin of the clause above, and a
        # separate key rather than a mode of it because the two read different
        # halves of the type line: that one intersects *subtypes* and so says
        # "shares a creature type with it" (Goblin with Goblin), which on this
        # card would find another Goblin when a Goblin entered and nothing at
        # all when a land did -- quietly narrower than printed.
        #
        # `types` is a literal list fixed when the card is written and cannot
        # stand in, because which permanent type matters is decided at
        # resolution by whatever just entered.
        other = _bound_oid(ctx, str(name))
        if other is None:
            return False
        theirs = chars(state, other).types if state.objects.get(other) else frozenset()
        # An intersection, so an artifact creature entering finds both the
        # artifacts and the creatures -- 205.2a lets an object have several card
        # types, and the printed "a permanent type" is satisfied by any one of
        # them. Spell types (Instant, Sorcery) cannot appear on either side
        # here: both objects are on the battlefield, where every card type is a
        # permanent type (110.4a).
        if not (set(types) & set(theirs)):
            return False
    if (name := selector.get("shares_a_creature_type_with")) is not None:
        # The creature-types-only twin of `shares_a_type_with` (205.3m), which
        # also reads `"self"` -- the ability's own source -- the way
        # `shares_a_color_with` does. Shared with `triggers.matches_card_filter`
        # through `creature_types_of`, so the two halves cannot disagree.
        other = ctx.source_oid if str(name) == "self" else _bound_oid(ctx, str(name))
        if not (creature_types_of(state, oid) & creature_types_of(state, other)):
            return False
    if (who := selector.get("shares_a_type_with_commander")) is not None and not (
        subtypes & _commander_subtypes(ctx, str(who))
    ):
        return False
    if (name := selector.get("shares_a_color_with")) is not None:
        # Radiance. The colour twin of the clause above, and the boundary is the
        # same one intimidate has: a **colorless** object shares a colour with
        # nothing, itself included, so an intersection is the right test and
        # "is not a different colour" would be its opposite.
        # `"self"` is the ability's own source -- Kasmina, Enigma Sage's "an
        # instant or sorcery card that shares a color with **this
        # planeswalker**", which on a granted copy is the walker that has it.
        # Read off the object wherever it now is, so a walker that spent its
        # last loyalty on the -8 still answers with the colours it had.
        other = ctx.source_oid if str(name) == "self" else _bound_oid(ctx, str(name))
        if other is None:
            return False
        theirs = chars(state, other).colors if state.objects.get(other) else frozenset()
        if not (colors & theirs):
            return False

    controller = selector.get("controller")
    if controller == "you" and obj.controller != ctx.controller:
        return False
    if controller == "opponent" and obj.controller == ctx.controller:
        return False
    # A player spec rather than one of the three words -- "…among creatures
    # **they** control", scoped to the one opponent a `for_each_player` loop is
    # currently on. `"opponent"` cannot say it: it means every opponent at once,
    # so `extreme` would take one global maximum over the merged pool and, at a
    # pod, spare the opponent whose best creature is smaller.
    # "…for each artifact **they** control", where *they* is the player this
    # Aura enchants (Overencumbered). The one named spec allowed here beside the
    # three words, and it is allowed for the reason the mapping form is: no
    # combination of you/opponent/any names one seat. `"opponent"` is the near
    # miss and is exact only at two players -- at a pod it counts the whole
    # table's artifacts, so the enchanted player's toll goes up because somebody
    # else built a Signet.
    if (isinstance(controller, Mapping) or controller == "enchanted_player") and (
        obj.controller not in select_players(ctx, controller)
    ):
        return False

    # The ownership twin of the three clauses above, spelled the same way and
    # read off `obj.owner` instead. "A commander **you own** on the battlefield
    # or in the command zone" -- Majestic Genesis, and every other "you own"
    # clause with it.
    #
    # It is a filter and never a default: nothing is imposed when the key is
    # absent, so `owner` written beside `controller` is a conjunction ("a
    # permanent you own that an opponent controls" is sayable) and `owner`
    # written alone asks about ownership and nothing else. That is the whole
    # difference from the static side, where `characteristics._matches` has to
    # switch a defaulted `controller: "you"` off to say the same sentence.
    owner = selector.get("owner")
    if owner == "you" and obj.owner != ctx.controller:
        return False
    if owner == "opponent" and obj.owner == ctx.controller:
        return False
    if (isinstance(owner, Mapping) or owner == "enchanted_player") and (
        obj.owner not in select_players(ctx, owner)
    ):
        return False

    if (want := selector.get("types")) and not set(want).issubset(types):
        return False
    # any-of, matching `subtypes` and `colors` above rather than `types`.
    if (want := selector.get("any_types")) and not (set(want) & types):
        return False
    # Checked here, alongside the other keys, so it composes with them: the
    # union narrows nothing on its own and everything outside it still filters.
    #
    # A branch inherits the zone the *outer* selector settled on, not the
    # caller's default. `validate_selector` refuses a `zone` inside a branch --
    # "put 'zone' on the outer selector; a branch filters the pool it already
    # chose" -- so passing the caller's default down instead re-asked the
    # battlefield question about a pool that was never on the battlefield, and
    # every branch failed. Silently: "a Human **or** artifact card" from a
    # library look matched nothing at all and the op simply never asked, which
    # reads on screen exactly like a top six that happened to hold neither.
    if (branches := selector.get("any_of")) and not any(
        matches(ctx, oid, branch, default_zone=zone_name) for branch in branches
    ):
        return False
    if (want := selector.get("not_types")) and set(want) & types:
        return False
    if (want := selector.get("subtypes")) and not (set(want) & subtypes):
        return False
    if (want := selector.get("not_subtypes")) and set(want) & subtypes:
        return False
    if (want := selector.get("supertypes")) and not set(want).issubset(supertypes):
        return False
    # Read off `supertypes` above, which is *derived* on the battlefield -- so a
    # land that a Blood Moon-shaped effect had made basic would stop being a
    # legal target, and one that gained Snow would still be one.
    if (want := selector.get("not_supertypes")) and set(want) & supertypes:
        return False
    if (want := selector.get("colors")) and not (set(want) & colors):
        return False
    # "…a **multicolored** instant or sorcery spell" (202.2b). Read off the
    # derived `colors` here rather than the printed set, so a permanent something
    # has repainted is matched on what it *is* -- the same reason `not_colors`
    # one line down does.
    if (least := selector.get("min_colors")) is not None and len(colors) < int(least):
        return False
    if (want := selector.get("not_colors")) and set(want) & colors:
        return False
    if "colorless" in selector and (not colors) != bool(selector["colorless"]):
        return False
    if (want := selector.get("keywords")) and not set(want).issubset(keywords):
        return False
    if (want := selector.get("not_keywords")) and set(want) & keywords:
        return False
    if (want := selector.get("name")) is not None:
        if isinstance(want, Mapping):
            # "Put all cards **with the chosen name** from among them into your
            # hand" (Tamiyo, Collector of Tales): the name a `choose_card_name`
            # earlier in the same effect bound. Unbound, it matches nothing --
            # a name nobody chose names no card.
            want = ctx.bindings.get(str(want.get("binding")))
            if not isinstance(want, str) or not want:
                return False
        if card.name != want:
            return False
    # "…for up to five Dragon cards **not named Tiamat**". Read off `card.name`
    # exactly as the positive clause one line up does, for the same reason it
    # does: nothing in the characteristics layer renames an object, so the
    # card's name is the name.
    if (unwanted := selector.get("not_name")) and card.name in (
        {unwanted} if isinstance(unwanted, str) else set(unwanted)
    ):
        return False
    if (bound := selector.get("shares_a_name_with")) is not None:
        # Legions to Ashes: "…and all tokens that player controls **with the
        # same name as that permanent**." The dynamic twin of the literal
        # `name` clause directly above -- that one is a string the card author
        # writes at load time, this one is read off an object bound at cast
        # time, which is the only way to say "the same name as the thing I just
        # targeted".
        #
        # `card.name`, not a characteristics lookup: the characteristics layer
        # models types, colours, power and keywords, and nothing in it renames
        # an object, so the card's name is the name.
        other = _bound_oid(ctx, str(bound))
        if other is None:
            return False
        target = state.objects.get(other)
        # Deliberately tolerant of an object that has already left the
        # battlefield. Legions to Ashes exiles its target and the tokens in one
        # breath, and an implementation that read the name only while the
        # target was still in play would sweep nothing whenever the ops ran in
        # the other order -- a spell that silently did half its job.
        if target is None or state.card_of(target).name != card.name:
            return False

    if "tapped" in selector and bool(obj.tapped) != bool(selector["tapped"]):
        return False
    if "has_counters" in selector and any(n > 0 for n in obj.counters.values()) != bool(
        selector["has_counters"]
    ):
        return False
    if "is_commander" in selector and bool(obj.is_commander) != bool(selector["is_commander"]):
        return False
    if "is_token" in selector and bool(obj.is_token) != bool(selector["is_token"]):
        return False
    if "damaged" in selector and bool(obj.damage > 0) != bool(selector["damaged"]):
        return False
    if "damaged_by" in selector:
        # "…a creature dealt damage this way." Gallifrey Falls. Answered from
        # the per-turn ledger, the same one `triggers.matches_card_filter`
        # reads: `damaged` above is only "has damage marked on it", which is
        # true of a creature something else burned a moment earlier and false
        # of one this spell killed outright.
        who = selector["damaged_by"]
        want = ctx.source_oid if who == "self" else who
        if want not in ctx.state.damage_ledger.get(oid, ()):
            return False
    if "exiled_with" in selector:
        # "Return the exiled card" -- the cards *this* permanent exiled, and no
        # others. A plain `{"zone": "exile"}` filter matches every card in exile
        # from every source, so returning over it would hand back cards this
        # card never touched, which is a different card rather than an
        # approximation of this one.
        who = selector["exiled_with"]
        want = ctx.source_oid if who == "self" else who
        if obj.exiled_by is None or obj.exiled_by != want:
            return False
    if "created_with" in selector:
        # "…tokens created with this creature" -- the ones this object's
        # effects made, and no others. `is_token` plus `controller: "you"` is
        # the reachable approximation and it is a different card: it exiles
        # every Treasure, Clue and Soldier its controller has.
        creator = state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
        if creator is None or oid not in creator.created_tokens:
            return False
    if "phased_out_with" in selector:
        # "…until this enchantment leaves the battlefield" -- the permanents
        # *this* card phased out, and no others. The phasing twin of
        # `exiled_with`, and narrow for the same reason: a filter that matched
        # every phased-out permanent would hand back creatures this card never
        # touched, including ones phasing on their own keyword.
        who = selector["phased_out_with"]
        want = ctx.source_oid if who == "self" else who
        if obj.phased_out_by is None or obj.phased_out_by != want:
            return False

    # Deliberately *outside* the combat block below, because it is the one attack
    # question that is not about combat: it reads the turn ledger, so it still
    # answers in the postcombat main phase where `state.combat` is `None` -- which
    # is the only phase either card asking it is ever cast in. It also stays true
    # for a creature that has since left combat (506.4): being removed from combat
    # does not undo a declaration.
    if "attacked_this_turn" in selector and state.turn_ledger.has_attacked(oid) != bool(
        selector["attacked_this_turn"]
    ):
        return False

    # Beside its neighbour above and for the same reason: a turn-ledger question
    # rather than a board one, so it survives the permanent having since been
    # tapped, animated or moved within the battlefield. `entered_this_turn` is
    # the arrival record 400.7 makes meaningful -- a permanent that left and
    # came back is a new object with a new entry, which is the printed reading.
    if "entered_this_turn" in selector and state.turn_ledger.entered_this_turn(oid) != bool(
        selector["entered_this_turn"]
    ):
        return False

    combat = state.combat
    if "attacking" in selector and bool(combat and combat.attacking(oid)) != bool(
        selector["attacking"]
    ):
        return False
    if (who := selector.get("attacking_player")) is not None and not attacking_player_matches(
        combat, oid, str(who), ctx.controller
    ):
        return False
    if "blocked" in selector:
        # "…an **unblocked** attacking creature you control" -- ninjutsu. Not
        # the negation of `blocking`, which is about a *blocker*: this asks
        # whether anything is blocking **this attacker**, and the two are
        # different creatures. A creature that is not attacking at all is not
        # blocked either, which is why `blocked: false` is paired with
        # `attacking: true` on every printed line of this shape.
        is_blocked = bool(combat and any(v == oid for v in combat.blockers.values()))
        if is_blocked != bool(selector["blocked"]):
            return False
    if (blocking := selector.get("blocking")) is not None:
        if isinstance(blocking, Mapping) and "binding" in blocking:
            # "…blocked by a creature without flanking": *which* attacker it is
            # blocking, not merely that it is blocking something. The plain
            # boolean cannot say it -- on a board with two combats it matches
            # every blocker in both -- so this names a trigger binding, the way
            # `shares_a_type_with` and `exclude_binding` do.
            bound = ctx.bindings.get(str(blocking["binding"]))
            attacker = bound if isinstance(bound, int) else None
            if attacker is None or combat is None or combat.blockers.get(oid) != attacker:
                return False
        elif bool(combat and combat.blocking(oid)) != bool(blocking):
            return False

    if (spec := selector.get("power")) is not None:
        value = c.power if c else (card.power or 0)
        if not _compare(value, spec, ctx):
            return False
    if (spec := selector.get("toughness")) is not None:
        value = c.toughness if c else (card.toughness or 0)
        if not _compare(value, spec, ctx):
            return False
    # "…each with **base** power or toughness 1 or less" -- Angelic Aberration.
    # 613.2 layer 7a/7b: the copiable size, before counters, anthems, Auras,
    # Equipment and pump. `characteristics._base_pt` is the one function that
    # answers it -- the same one `_compute` starts from and static filters stop
    # at -- so this cannot drift from the pipeline's idea of where a creature's
    # size begins.
    #
    # Distinct from `power`/`toughness` above, which read the *live* value, and
    # on any board carrying a +1/+1 counter or an anthem the two name different
    # creatures in both directions: the live keys would spare the 1/1s this card
    # sacrifices and swallow a big creature whose printed line is small.
    #
    # Off the battlefield there is no object to layer anything onto, so the
    # printed value is already the base one and both spellings agree.
    for key, index in (("base_power", 0), ("base_toughness", 1)):
        if (spec := selector.get(key)) is None:
            continue
        if use_derived:
            value = _base_pt(state, obj)[index]
        else:
            value = (card.power if index == 0 else card.toughness) or 0
        if not _compare(value, spec, ctx):
            return False
    if (spec := selector.get("mana_value")) is not None and not _compare(
        card.mana_value, spec, ctx
    ):
        return False
    # "…with {X} in its mana cost". Read off the **printed** cost of the face
    # being cast -- `card` is already `card_of`, so a split half or an adventure
    # answers for the half on the stack -- and never off the announced value.
    # Rule 107.3: the {X} in a mana cost is a mana symbol, and choosing 0 for it
    # (601.2b) does not remove the symbol from the cost. A Fireball cast for X=0
    # is still "a spell with {X} in its mana cost"; `StackItem.x` is the number,
    # and the number is not the question.
    if (want := selector.get("x_in_mana_cost")) is not None and (
        card.mana_cost.x_count > 0
    ) is not bool(want):
        return False
    if (want := selector.get("mana_cost")) is not None and not has_printed_cost(ctx.state, oid, want):
        return False

    return True


#: What `attacking_player` may name, relative to the ability's controller.
ATTACKING_PLAYER_WORDS = ("you", "opponent", "any")


def attacking_player_matches(combat: Any, oid: int, who: str, controller: int) -> bool:
    """Is ``oid`` attacking a **player** -- the one ``who`` names -- rather than a
    planeswalker or battle that player controls?

    506.2 gives an attacking creature one of three things to attack: a player, a
    planeswalker, or a battle. `combat.attackers[oid]` is the defending *player*
    in all three cases (`add_attacker` refuses a permanent whose controller
    disagrees), which is right for "attacks you or a planeswalker you control"
    and one creature too many for "attacks you". `attacking_permanent` is
    the record that tells them apart, and it holds battles as well as walkers --
    so a creature swinging at a battle is not attacking anybody, which is what
    this asks and what 506.2 says.

    Shared by `matches` and `triggers.matches_card_filter`, so the effect and
    trigger halves of the filter language cannot disagree about it.
    """
    if combat is None or not combat.attacking(oid) or oid in combat.attacking_permanent:
        return False
    defender = combat.attackers[oid]
    if who == "you":
        return defender == controller
    if who == "opponent":
        return defender != controller
    return True


def has_printed_cost(state, oid: int, wanted) -> bool:
    """Does this object's printed mana cost equal one of ``wanted``?

    Read off `card_of`, so a split half or an Adventure answers for the face in
    play. An object a copy effect gave "no mana cost" (embalm, eternalize) has
    none, whatever the card it copies prints -- the same override `mana_value_of`
    honours.
    """

    obj = state.objects.get(oid)
    if obj is None:
        return False
    if obj.copy_overrides and obj.copy_overrides.get("no_mana_cost"):
        return False
    return printed_cost_is(state.card_of(obj).mana_cost, wanted)


def _compare(value: int, spec: Any, ctx: EffectContext) -> bool:
    # Local: `values` imports `selectors`, and each evaluates the other.
    from .values import evaluate_value

    if isinstance(spec, int):
        return value == spec
    if not isinstance(spec, Mapping):
        raise DslError(f"bad comparison spec {spec!r}")
    op = spec.get("op", ">=")
    other = evaluate_value(ctx, spec.get("value", 0))
    if op == ">=":
        return value >= other
    if op == "<=":
        return value <= other
    if op == ">":
        return value > other
    if op == "<":
        return value < other
    if op in ("=", "=="):
        return value == other
    if op == "!=":
        return value != other
    raise DslError(f"unknown comparison operator {op!r}")


def choose_objects(
    ctx: EffectContext,
    selector: Mapping[str, Any] | None,
    prompt: str = "Choose",
    purpose: str = "choose",
) -> Generator[Any, list[int], list[int]]:
    """Resolve a selector all the way to a concrete list of oids.

    Honours ``count`` (an integer, ``"all"`` or ``"any"``), ``optional``
    (an integer ``count`` the chooser may decline entirely), ``chooser``
    (``controller``, ``owner`` or ``none``) and ``random``.  When a choice is
    genuinely required this suspends and asks; otherwise it returns immediately.
    """
    pool = resolve_pool(ctx, selector)
    if not pool or selector is None:
        return []
    return (yield from pick_from_pool(ctx, pool, selector, prompt, purpose))


def pick_from_pool(
    ctx: EffectContext,
    pool: list[int],
    selector: Mapping[str, Any],
    prompt: str = "Choose",
    purpose: str = "choose",
    chooser: int | None = None,
) -> Generator[Any, list[int], list[int]]:
    """Apply a selector's ``count``/``optional``/``chooser``/``random`` to a built pool.

    Split out of ``choose_objects`` because not every pool comes from a zone.
    ``look_at_top`` bounds its own pool to the top N cards of a library and then
    wants exactly this narrowing, so the two share the ``count`` vocabulary
    rather than each inventing one -- which is what keeps ``"any"`` meaning the
    same thing wherever it is written.  ``chooser`` overrides the selector's own
    clause, for an op that already knows whose decision it is.
    """
    if not pool:
        return []

    count_spec = selector.get("count", "all")
    if count_spec == "all":
        return pool

    # "…put **any number of** creature cards from your hand onto the
    # battlefield."  A free subset: none of them, all of them, or anything
    # between, and the chooser decides.  Neither existing form says it --
    # `"all"` makes it mandatory, and a fixed number forces exactly that many --
    # so Last March of the Ents could not let you keep a creature in hand.
    # `ask_objects` always took distinct min/max bounds; only the spelling that
    # reaches them was missing, which is why this is a `count` form and not an op.
    if count_spec == "any":
        min_count, max_count = 0, len(pool)
    else:
        # Local: `values` imports `selectors`, and each evaluates the other.
        from .values import evaluate_value

        count = evaluate_value(ctx, count_spec)
        count = max(0, min(int(count), len(pool)))
        if count == 0:
            return []
        # "You may reveal **a** Human or artifact card from among them" -- the
        # size is still N, but nothing is forced. Only the *floor* moves, which
        # is what separates this from `"any"`: the ceiling stays at the printed
        # number, so an optional 1 takes one card or none and never two.
        #
        # It also has to survive the shortcut below. `count >= len(pool)` returns
        # the pool without asking, which is right for a mandatory pick -- there
        # is nothing to decide -- and wrong here, because declining is the
        # decision. A six-card look that turned up exactly one Human would
        # otherwise put it in hand without the player ever being asked.
        optional = bool(selector.get("optional"))
        if count >= len(pool) and not optional:
            return pool
        min_count, max_count = (0 if optional else count), count

    if selector.get("random"):
        return ctx.state.rng.shuffled(pool)[:max_count]

    chooser_spec = selector.get("chooser", "controller")
    if chooser_spec == "none":
        return pool[:max_count]
    if chooser is None:
        chooser = ctx.controller
        if chooser_spec == "owner" and pool:
            chooser = ctx.state.objects[pool[0]].owner
        elif chooser_spec not in ("controller", "owner"):
            # An arbitrary **player spec** -- Rejoin the Fight: "each opponent
            # chooses a creature card in **your** graveyard". Both existing
            # names resolve to the spell's controller for a pool in your own
            # yard, so the caster would pick the cards an opponent is supposed
            # to, which is the whole card.
            #
            # Resolved through `select_players`, so the ordinary vocabulary
            # works -- `{"binding": "each_player"}` inside a `for_each_player`
            # loop is the shape that card needs.
            seats = select_players(ctx, chooser_spec)
            if not seats:
                # Nobody to ask, so nothing is chosen -- rather than quietly
                # letting the controller decide.
                return []
            chooser = seats[0]

    picked = yield from ask_objects(ctx, prompt, pool, min_count, max_count, chooser, purpose)
    return picked


def _validate_player_spec_shape(who: Any, where: str) -> None:
    """A `chooser` that is not one of the three names must be a player spec.

    Shape only: a mapping is left to the loader's own `_validate_player_spec`,
    which is the one that can check a target id against the card's declarations.
    """
    if isinstance(who, Mapping):
        return
    if isinstance(who, str) and who in PLAYER_SPEC_NAMES:
        return
    raise DslError(f"{where}: unknown chooser {who!r}")


#: The **string** forms :func:`select_players` accepts, named so a load-time
#: validator can refuse a typo instead of leaving it to raise mid-resolution.
#: The mapping forms (``target``, ``controller_of_target``, ``binding``,
#: ``controller_of``, ``owner_of``, ``not``, ``attacked_by``,
#: ``dealt_combat_damage_by``) and a bare seat number are not
#: here: they name something the card declares elsewhere and are checked where
#: that is checked -- `loader.effects._validate_player_spec`.
PLAYER_SPEC_NAMES = frozenset(
    {
        "you",
        "controller",
        "each_opponent",
        "opponent",
        "each_player",
        "all",
        "active_player",
        # "**Enchanted opponent** creates a Clue token", "at the beginning of
        # combat on enchanted opponent's turn, **that player** may pay…" --
        # Overencumbered. The player the ability's own source is attached to
        # (303.4a). See `select_players`.
        "enchanted_player",
        # Gift (702.164a): the one opponent who was promised a gift as this
        # spell was cast. The only string here naming a seat the *caster* chose,
        # rather than one derived from the turn structure, from who is playing,
        # or from where a permanent is attached -- and the one `each_opponent`
        # gets wrong on this card: at a pod the promise goes to one player, so
        # "they create a token" handing one to every opponent is three times the
        # printed card. See `select_players`.
        "gift_recipient",
    }
)


def select_players(ctx: EffectContext, spec: Any) -> list[int]:
    """Resolve a player specification to a list of player ids."""
    state: GameState = ctx.state
    if spec is None:
        return [ctx.controller]
    if isinstance(spec, int):
        return [spec] if state.is_alive(spec) else []
    if isinstance(spec, str):
        if spec == "you" or spec == "controller":
            return [ctx.controller]
        if spec == "each_opponent" or spec == "opponent":
            return ctx.opponents()
        if spec == "each_player" or spec == "all":
            return state.alive()
        if spec == "active_player":
            return [state.active_player]
        if spec == "gift_recipient":
            # Gift (702.164a): "**they** create a tapped 1/1 blue Fish creature
            # token". The opponent the caster promised, and nobody at all when
            # the promise was not made -- which is what makes the reward
            # conditional without an `if` around it: `create_token` loops over
            # this spec, and an empty list creates nothing.
            #
            # The context first, then the object, for the reason
            # `{"gift_promised": …}` reads both: while the spell resolves the
            # StackItem is what knows, and afterwards -- in a delayed trigger it
            # scheduled, or on the permanent it became -- only the object is.
            promisee = ctx.gift_to
            if promisee is None and ctx.source_oid is not None:
                obj = state.objects.get(ctx.source_oid)
                promisee = obj.cast_gift_to if obj is not None else None
            return [promisee] if promisee is not None and state.is_alive(promisee) else []
        if spec == "enchanted_player":
            # "Enchanted opponent creates a Clue token." The seat this Aura is
            # attached to, read off the **ability's own source** -- the same
            # argument `attached`, `haunted_by` and cipher's `encoded_by` make:
            # the Aura knows what it is on, and nothing else in the game state
            # points back the other way.
            #
            # Every other spelling of "enchanted opponent" is a different card.
            # `{"target": …}` cannot say it: an ability's targets are scoped to
            # that ability (`loader.effects._validate_player_spec`), and a triggered
            # ability that declared none would resolve `ctx.target_players` to
            # `[]` -- which `op_may` reads as "nobody" and bills `ctx.controller`
            # instead, the documented Rhystic Study failure, so the Aura's own
            # controller would pay the enchanted player's toll. `each_opponent`
            # is the near miss and is wrong the moment there are two of them: it
            # taxes the whole table rather than the one seat the card names.
            #
            # `[]` when the source is gone or enchants a permanent instead, and
            # that is the safe direction: an effect aimed at nobody does
            # nothing, where a fallback to the controller would silently point
            # the card at its own caster.
            obj = state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
            pid = obj.attached_to_player if obj is not None else None
            return [pid] if pid is not None and state.is_alive(pid) else []
        raise DslError(f"unknown player spec {spec!r}")
    if isinstance(spec, Mapping):
        if "except" in spec:
            # "each **opponent** who did this" -- the recorded set minus a seat.
            # `not` is the complement over the whole table and cannot narrow an
            # inclusive spec, so an intersection had no spelling: the seats a
            # binding holds include you whenever you took the same option.
            rest = {k: v for k, v in spec.items() if k != "except"}
            excluded = set(select_players(ctx, spec["except"]))
            return [pid for pid in select_players(ctx, rest) if pid not in excluded]
        if "not" in spec:
            # "target player **other than** its controller."
            #
            # Every other form here names the players to *allow*; this one names
            # the player to forbid, and no composition of the inclusive forms
            # says it. `"opponent"` is the near miss and is wrong in both
            # directions at once on a card that triggers on anybody's token: it
            # forbids **you** when an opponent made the token, and permits the
            # very opponent who made it. At a four-player pod "other than its
            # controller" is *three* seats -- the other two opponents and you --
            # which is a set no single inclusive spec can name.
            #
            # The complement is taken over `alive()` rather than over every
            # seat, so a player who has already lost the game is not offered as
            # a legal target. Nested, so `{"not": {"controller_of": "subject"}}`
            # reuses the mapping form it wraps rather than duplicating it.
            excluded = set(select_players(ctx, spec["not"]))
            return [pid for pid in state.alive() if pid not in excluded]
        if "attacked_by" in spec:
            # "…each player **this creature attacked this turn** loses the
            # game" -- Angel of Destiny. Read off the turn ledger, because by the
            # end step `state.combat` is gone and was the only thing that knew.
            # Seat order, the living only, and nobody at all when the creature
            # did not attack -- the safe direction for a card that ends games.
            # "self" is the only subject (the loader refuses anything else).
            seats = state.turn_ledger.players_attacked_by.get(ctx.source_oid, set())
            return [pid for pid in state.alive() if pid in seats]
        if "dealt_combat_damage_by" in spec:
            # "…whose controller was dealt combat damage by this creature this
            # turn" -- Steel Hellkite. Off the turn ledger for the reason
            # `attacked_by` is, and keyed by the ability's source, so the
            # record of an object that has since left still answers for an
            # ability it already put on the stack (last-known information).
            # Seat order, the living only; nobody when it dealt none.
            seats = state.turn_ledger.players_dealt_combat_damage_by.get(ctx.source_oid, set())
            return [pid for pid in state.alive() if pid in seats]
        if "target" in spec:
            # Only refs that *are* players. A `kind: "spell"` or `kind:
            # "permanent"` target never produces one, and this quietly returning
            # `[]` for them is why `controller_of_target` below exists rather
            # than this key being widened -- see `loader.effects._validate_player_spec`,
            # which refuses the combination at load time.
            return ctx.target_players(str(spec["target"]))
        if "controller_of_target" in spec:
            # "Counter target spell **unless its controller** pays {3}."
            #
            # The one player spec that reads the *target list* rather than
            # `ctx.bindings`, and the reason it had to exist: bindings are
            # written by `triggers.event_bindings` and by `snapshot`, so
            # `controller_of` can only name a player some **trigger** already
            # found. An activated ability's `StackItem` carries its targets and
            # its bindings as separate things and binds nothing for what it was
            # activated at -- which is why ward's payer (a `becomes_target`
            # event binding) could be written and Frontline Medic's could not.
            #
            # Read at resolution and not at activation, which is 608.2 and not a
            # shortcut: control of a spell can change while the ability is on
            # the stack, and the seat that gets the bill is the one that
            # controls it when the payment is demanded.
            tid = str(spec["controller_of_target"])
            billed: list[int] = []
            for ref in ctx.target_refs(tid):
                if ref.kind == "stack":
                    item = state.stack_item(ref.id)
                    pid = item.controller if item is not None else None
                elif ref.kind == "object":
                    pid = obj.controller if (obj := state.objects.get(ref.id)) else None
                else:  # a player ref has no controller; the loader refuses it
                    pid = None
                # De-duplicated and in target order: "counter each of them
                # unless their controllers pay" is one bill per seat, and a
                # player who has already lost is not asked for anything.
                if pid is not None and pid not in billed and state.is_alive(pid):
                    billed.append(pid)
            return billed
        if "controller_of" in spec:
            binding = ctx.bindings.get(str(spec["controller_of"]))
            if isinstance(binding, Mapping):
                pid = binding.get("controller")
                return [int(pid)] if pid is not None else []
            obj = state.objects.get(int(binding)) if binding is not None else None
            return [obj.controller] if obj else []
        if "owner_of" in spec:
            binding = ctx.bindings.get(str(spec["owner_of"]))
            if isinstance(binding, Mapping):
                pid = binding.get("owner")
                return [int(pid)] if pid is not None else []
            obj = state.objects.get(int(binding)) if binding is not None else None
            return [obj.owner] if obj else []
        if "binding" in spec:
            value = ctx.bindings.get(str(spec["binding"]))
            if isinstance(value, int):
                return [value] if state.is_alive(value) else []
            if isinstance(value, list):
                # A **set of seats**, which `may`'s `as` writes: "each opponent
                # who discarded their hand this way". Deduped and returned in
                # seat order rather than acceptance order, so the damage lands
                # in a stable sequence, and filtered to the living for the
                # reason `not` takes its complement over `alive()`.
                seats = {int(v) for v in value if isinstance(v, int)}
                return [pid for pid in state.alive() if pid in seats]
            return []
    raise DslError(f"unparsable player spec {spec!r}")


def validate_selector(selector: Any, where: str) -> None:
    """Load-time check that a selector uses only known keys."""
    if selector is None:
        return
    if not isinstance(selector, Mapping):
        raise DslError(f"{where}: selector must be an object, got {type(selector).__name__}")
    unknown = set(selector) - SELECTOR_KEYS
    if unknown:
        raise DslError(f"{where}: unknown selector keys {sorted(unknown)}")
    zone = selector.get("zone")
    if zone is not None and zone not in ZONE_NAMES:
        raise DslError(f"{where}: unknown zone {zone!r}")
    # `paid_by` takes either "self"/an oid ("when **that mana** is spent") or a
    # selector over what the mana's source *was* ("if mana from a **Treasure**
    # was spent to cast it"). The selector half is validated against its own
    # closed key list rather than `SELECTOR_KEYS`, because what it filters is a
    # snapshot and not a permanent: `tapped`, `power`, `zone` and the rest have
    # no answer about a Treasure that was sacrificed to make the mana, and every
    # one of them would load and then be silently false.
    paid_by = selector.get("paid_by")
    if isinstance(paid_by, Mapping):
        unknown_paid_by = set(paid_by) - PAID_BY_SELECTOR_KEYS
        if unknown_paid_by:
            raise DslError(
                f"{where}.paid_by: {sorted(unknown_paid_by)} cannot be asked of a "
                f"remembered mana source -- it may have left the battlefield to "
                f"make the mana. Use only {sorted(PAID_BY_SELECTOR_KEYS)}"
            )
        controller = paid_by.get("controller")
        if controller is not None and controller not in ("you", "opponent", "any"):
            raise DslError(
                f"{where}.paid_by: unknown controller clause {controller!r}; the "
                f"snapshot records one player, so only 'you', 'opponent' and 'any' "
                f"can be asked of it"
            )
    if "created_with" in selector and selector["created_with"] != "self":
        # A card can only name itself as the creator; any other value would
        # load and then silently match no token at all.
        raise DslError(f"{where}: created_with must be 'self', got {selector['created_with']!r}")
    chooser = selector.get("chooser")
    if chooser is not None and chooser not in ("controller", "owner", "none"):
        # Anything else is an ordinary player spec -- "each opponent chooses a
        # creature card in your graveyard". Validated as one so a typo is
        # refused at load time rather than resolving to nobody mid-game.
        _validate_player_spec_shape(chooser, f"{where}.chooser")
    controller = selector.get("controller")
    if (
        controller is not None
        and not isinstance(controller, Mapping)
        and controller not in ("you", "opponent", "any", "enchanted_player")
    ):
        raise DslError(f"{where}: unknown controller clause {controller!r}")
    owner = selector.get("owner")
    if (
        owner is not None
        and not isinstance(owner, Mapping)
        and owner not in ("you", "opponent", "any", "enchanted_player")
    ):
        # Refused for the reason `controller` is, and the stakes are higher: an
        # unrecognised word here matches *everything*, so a selector meaning "a
        # commander you own" would quietly mean "a commander", and the number a
        # card reads off that pool would be an opponent's.
        raise DslError(f"{where}: unknown owner clause {owner!r}")
    if "player" in selector:
        # Only zones that *belong* to a player have an owner to choose. On the
        # battlefield and the stack the list is shared, so `player` would be
        # silently ignored -- and a card that says "target player's" and quietly
        # means "everyone's" is the failure this validation exists to prevent.
        zone_name = selector.get("zone", "battlefield")
        if zone_name in ("battlefield", "stack"):
            raise DslError(
                f"{where}: 'player' scopes a zone somebody owns; the {zone_name} "
                f"is shared -- use 'controller' to filter it"
            )
    # A predicate, not a comparison -- and it sits next to `mana_value`, which
    # *is* one, so the wrong spelling is the natural one to reach for. Every
    # non-bool would be read through `bool()` and pass silently:
    # `{"op": ">=", "value": 1}` is a truthy dict and would mean `true` by
    # accident, and `0`/`""` would quietly become `false`. A card that asks for
    # "two or more X symbols" is not a printing, so there is nothing to widen
    # this into; there is only a spelling to refuse.
    # The same refusal for the same reason: `"C"` or `["C"]` would read as
    # `true` by accident, and `0` as `false`.
    if "colorless" in selector and not isinstance(selector["colorless"], bool):
        raise DslError(
            f"{where}: 'colorless' is true (no colours, 105.2c) or false (one or "
            f"more); use 'colors' to name a colour"
        )
    if "x_in_mana_cost" in selector and not isinstance(selector["x_in_mana_cost"], bool):
        raise DslError(
            f"{where}: 'x_in_mana_cost' is true or false -- whether the printed "
            f"cost has an {{X}} symbol at all; use 'mana_value' to compare numbers"
        )
    # A bare `true` is the tempting spelling -- it is how `attacking` is written
    # -- and it would name nobody: the key is *which* player, and a boolean read
    # as a word matches no branch, so every creature would silently fail it.
    who = selector.get("attacking_player")
    if who is not None and (not isinstance(who, str) or who not in ATTACKING_PLAYER_WORDS):
        raise DslError(
            f"{where}: 'attacking_player' names whom the creature attacks -- one of "
            f"{list(ATTACKING_PLAYER_WORDS)}; use 'attacking' for true/false"
        )
    if "mana_cost" in selector:
        validate_printed_cost_list(selector["mana_cost"], where)
    count = selector.get("count")
    if isinstance(count, str) and count not in ("all", "any"):
        raise DslError(f"{where}: unknown count {count!r}; use 'all', 'any' or a value")
    # "Any number" is a choice by definition, and both of these take the choice
    # away -- they would silently resolve the whole pool, which is `count: "all"`
    # wearing the wrong name.  A card that means "all" should say so.
    if count == "any":
        if selector.get("random"):
            raise DslError(f"{where}: count 'any' is a free choice; it cannot be random")
        if selector.get("chooser") == "none":
            raise DslError(f"{where}: count 'any' needs a chooser; use 'all' for no choice")
    if selector.get("optional"):
        # "Exactly N, or none" is only a sentence when there is an N. `"all"`
        # is mandatory by definition and `"any"` already reaches down to zero,
        # so `optional` on either is either a contradiction or a no-op -- and a
        # no-op key on a card that means "you may" is exactly the kind of
        # silently-ignored clause the whole key set is validated to prevent.
        if count is None or isinstance(count, str):
            raise DslError(
                f"{where}: 'optional' means 'exactly N of them, or none' and needs a "
                f"numeric count; 'all' is mandatory and 'any' already includes none"
            )
        # Same argument as `"any"` above, and the same two ways round it. Both
        # of these resolve the pool without asking anybody, which deletes the
        # "you may" the key was written to say.
        if selector.get("random"):
            raise DslError(f"{where}: 'optional' is a declinable choice; it cannot be random")
        if selector.get("chooser") == "none":
            raise DslError(
                f"{where}: 'optional' needs a chooser; with none there is nobody to decline"
            )
    # A misspelled type in an any-of clause matches nothing and narrows the
    # selector silently -- "target artifact or enchantmnet" would quietly become
    # "target artifact".  Checked here rather than in the loader's per-op guards
    # because every selector, on every op and every target spec, comes through.
    for key in ("types", "any_types", "not_types"):
        for name in selector.get(key) or ():
            # "…cards of **the chosen type**" (Creeping Renaissance). The one
            # entry here that is not a literal name, substituted per resolution
            # by `_resolve_chosen_card_type` rather than at load time, because
            # the choice does not exist until the spell resolves. Validated as
            # exactly that spelling: a near miss that fell through would freeze
            # into a name no card has and match nothing for ever.
            if isinstance(name, Mapping):
                if key != "types":
                    raise DslError(
                        f"{where}: the chosen card type may only appear in 'types', "
                        f"not {key!r}"
                    )
                if set(name) != {"chosen_card_type_of"} or name["chosen_card_type_of"] != "self":
                    raise DslError(
                        f'{where}: the only dynamic card type is '
                        f'{{"chosen_card_type_of": "self"}}, not {dict(name)!r}'
                    )
                continue
            if name not in KNOWN_TYPES:
                raise DslError(f"{where}: unknown card type {name!r} in {key!r}")
    # A literal name, or the name a `choose_card_name` bound. Anything else
    # would be compared against a card name, match nothing and look fine.
    wanted = selector.get("name")
    if wanted is not None and not isinstance(wanted, str) and not (
        isinstance(wanted, Mapping)
        and set(wanted) == {"binding"}
        and isinstance(wanted["binding"], str)
    ):
        raise DslError(
            f"{where}: 'name' takes a card name or {{'binding': ...}} naming a "
            f"choose_card_name's choice, got {wanted!r}"
        )
    # Same argument, and sharper for the negated key: a misspelled *positive*
    # supertype selects nothing and is visible on the first board, where a
    # misspelled `not_supertypes` excludes nothing and looks like it worked.
    for key in ("supertypes", "not_supertypes"):
        for name in selector.get(key) or ():
            if name not in KNOWN_SUPERTYPES:
                raise DslError(
                    f"{where}: unknown supertype {name!r} in {key!r} "
                    f"(known: {sorted(KNOWN_SUPERTYPES)})"
                )
    # The same argument once more, and the negated key is again the sharp one:
    # a positive `name` that is not a string selects nothing and is visible on
    # the first board, while a `not_name` written as anything but a name -- a
    # nested selector, say, on the assumption it is a generic `not` wrapper --
    # excludes nothing and looks like it worked.
    unwanted = selector.get("not_name")
    if unwanted is not None:
        names = [unwanted] if isinstance(unwanted, str) else unwanted
        if not isinstance(names, (list, tuple)) or not names:
            raise DslError(
                f"{where}: 'not_name' takes a card name or a list of them, got {unwanted!r}"
            )
        for name in names:
            if not isinstance(name, str):
                raise DslError(f"{where}: 'not_name' holds card names; {name!r} is not one")

    union = selector.get("union")
    if union is not None:
        if not isinstance(union, (list, tuple)) or len(union) < 2:
            raise DslError(f"{where}: union takes a list of at least two selectors")
        extra = set(selector) - {"union", "count", "chooser", "optional", "random"}
        if extra:
            # A branch brings its own zone, so a characteristic clause written
            # outside would have to mean one thing for a card in a hand and
            # another for a permanent on the battlefield -- and `matches` reads
            # derived characteristics for one and printed ones for the other.
            # Whatever it was meant to narrow, it belongs in the branches.
            raise DslError(
                f"{where}: union assembles whole selectors, so {sorted(extra)} "
                f"belong inside a branch -- only 'count', 'chooser', 'optional' "
                f"and 'random' may sit beside it"
            )
        for i, branch in enumerate(union):
            if not isinstance(branch, Mapping):
                raise DslError(f"{where}.union[{i}]: each branch is a selector")
            validate_selector(branch, f"{where}.union[{i}]")

    branches = selector.get("any_of")
    if branches is not None:
        if not isinstance(branches, (list, tuple)) or len(branches) < 2:
            raise DslError(f"{where}: any_of takes a list of at least two selectors")
        for i, branch in enumerate(branches):
            # A branch naming a zone would be read as a filter on the pool the
            # outer selector already chose, which is not what it looks like.
            if isinstance(branch, Mapping) and "zone" in branch:
                raise DslError(
                    f"{where}.any_of[{i}]: put 'zone' on the outer selector; a "
                    f"branch filters the pool it already chose"
                )
            validate_selector(branch, f"{where}.any_of[{i}]")
    if "any_types" in selector and len(selector.get("any_types") or ()) < 2:
        raise DslError(f"{where}: any_types needs at least two types; use 'types' for one")
