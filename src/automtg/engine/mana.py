"""Mana costs, mana pools, and the automatic payment solver.

Design note -- *mana is auto-paid*.  An ``Action`` never carries a payment.
Legality only offers a cast/activation if :func:`solve_payment` can find a set of
sources to tap; applying the action runs the same solver again and taps them.
This collapses an enormous branching factor for the RL agent and removes the
worst tedium from the UI, at the cost of not being able to deliberately tap the
"wrong" land.  See ``docs/adr/0003-auto-mana-payment.md``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from .enums import COLOR_ORDER, COLORLESS, Color
from .errors import DslError

#: Mana symbol order used by every 6-tuple in this module: W U B R G C.
SYMBOLS: tuple[str, ...] = (*(c.value for c in COLOR_ORDER), COLORLESS)
SYMBOL_INDEX: dict[str, int] = {s: i for i, s in enumerate(SYMBOLS)}
N_SYMBOLS = len(SYMBOLS)

_TOKEN_RE = re.compile(r"\{([^}]*)\}")

#: Guard on the payment solver's backtracking fallback.  Real board states settle
#: in a handful of nodes; this only exists so a pathological state cannot hang a
#: 10,000-game arena run.
MAX_SOLVER_NODES = 20_000


def _zeros() -> list[int]:
    return [0] * N_SYMBOLS


#: What one Phyrexian pip costs in life instead of mana (rule 107.4f).
PHYREXIAN_LIFE = 2


@dataclass(frozen=True)
class HybridPip:
    """One ``{W/U}``-style pip: pay any of ``symbols``, ``generic`` generic, or
    ``life`` life.

    Three shapes of "either/or" inside a cost, one representation.  ``{W/U}`` is
    a choice between two coloured symbols and has no other alternative.
    ``{2/W}`` is a choice between one coloured symbol and two generic, which is
    why *that* alternative is a number and not another symbol.  ``{W/P}`` --
    Phyrexian, rule 107.4f -- is a choice between one coloured symbol and two
    **life**, which is why ``life`` is a third field rather than a reuse of
    ``generic``: life is not mana, no source produces it, and the solver may not
    treat it as something a land could have made.

    Keeping all three here is what makes a Phyrexian pip count correctly
    everywhere a cost is *read* rather than paid.  ``{U/P}`` has mana value 1 and
    is blue, and stays both however it was actually paid, because :attr:`value`
    and :attr:`ManaCost.colors` never look at which half the payer chose.
    """

    symbols: frozenset[int] = frozenset()
    generic: int | None = None
    #: Life the payer may hand over instead of one of ``symbols``.  ``None`` for
    #: an ordinary hybrid; ``2`` for every printed Phyrexian symbol.
    life: int | None = None

    @property
    def value(self) -> int:
        """What this pip contributes to mana value: ``{W/U}`` 1, ``{2/W}`` 2.

        ``{W/P}`` is 1 -- the life half is not a *number of mana*, so rule
        202.3b counts the symbol as the one coloured pip it also is.  Mental
        Misstep is a mana-value-1 spell that can legally counter itself, and
        that only works if the life branch changes nothing here.
        """
        return self.generic if self.generic is not None else 1

    @property
    def phyrexian(self) -> bool:
        return self.life is not None


@dataclass(frozen=True)
class ManaCost:
    """A parsed mana cost.

    ``colored`` is a 6-tuple aligned with :data:`SYMBOLS`; the final slot is the
    ``{C}`` colorless requirement, which generic mana cannot satisfy but which can
    itself pay generic.  ``hybrid`` holds the pips that offer a choice; they are
    kept apart from ``colored`` precisely because they are not a fixed demand.
    """

    generic: int = 0
    colored: tuple[int, ...] = (0,) * N_SYMBOLS
    x_count: int = 0
    text: str = ""
    hybrid: tuple[HybridPip, ...] = ()

    @staticmethod
    def parse(text: str | None) -> ManaCost:
        """Parse ``"{4}{G}{U}"``.  ``None`` and ``""`` mean "no cost" (e.g. lands)."""
        if not text:
            return ManaCost(text="")
        generic = 0
        x_count = 0
        colored = _zeros()
        hybrid: list[HybridPip] = []
        pos = 0
        for match in _TOKEN_RE.finditer(text):
            if match.start() != pos:
                raise DslError(f"unparsable mana cost {text!r} near index {pos}")
            pos = match.end()
            sym = match.group(1).strip().upper()
            if sym.isdigit():
                generic += int(sym)
            elif sym == "X":
                x_count += 1
            elif sym in SYMBOL_INDEX:
                colored[SYMBOL_INDEX[sym]] += 1
            elif "/" in sym:
                hybrid.append(_parse_hybrid(sym, text))
            else:
                raise DslError(
                    f"unsupported mana symbol {{{sym}}} in {text!r} "
                    "(snow mana is not implemented)"
                )
        if pos != len(text):
            raise DslError(f"unparsable mana cost {text!r} (trailing {text[pos:]!r})")
        return ManaCost(
            generic=generic,
            colored=tuple(colored),
            x_count=x_count,
            text=text,
            hybrid=tuple(hybrid),
        )

    def mana_value(self, x: int = 0) -> int:
        """Converted mana cost.  ``X`` counts as 0 anywhere but on the stack."""
        return (
            self.generic
            + sum(self.colored)
            + sum(pip.value for pip in self.hybrid)
            + self.x_count * x
        )

    @property
    def colors(self) -> frozenset[Color]:
        """Every colour in the cost.

        A hybrid pip contributes **all** of its colours: ``{G/U}`` makes the card
        both green and blue, which is what decides its colour identity and so
        whether a Commander deck may run it at all.
        """
        indices = {i for i in range(len(COLOR_ORDER)) if self.colored[i] > 0}
        for pip in self.hybrid:
            indices.update(i for i in pip.symbols if i < len(COLOR_ORDER))
        return frozenset(COLOR_ORDER[i] for i in sorted(indices))

    def scaled(self, times: int) -> ManaCost:
        """This cost, charged ``times`` over -- cumulative upkeep.

        "Pay its upkeep cost **for each age counter on it**" is the only place a
        mana cost is not fixed when the card is written, and it multiplies every
        part of it: ``{1}{U}`` at three age counters is ``{3}{U}{U}{U}``, not
        ``{3}{U}``. Hybrid pips are repeated rather than summed, because each
        one is its own independent choice of which half to pay.

        ``X`` is deliberately not scaled and cannot appear: a cumulative upkeep
        with an X in it has no printing, and multiplying an X the caster already
        chose would charge for a number nobody picked.
        """
        n = max(0, int(times))
        if n == 1:
            return self
        return ManaCost(
            generic=self.generic * n,
            colored=tuple(c * n for c in self.colored),
            x_count=self.x_count,
            text=self.text,
            hybrid=self.hybrid * n,
        )

    def as_any_type(self) -> ManaCost:
        """This cost with every coloured demand relaxed -- "mana of any type can
        be spent to cast that spell".

        Summing the pips into ``generic`` *is* the rule rather than an
        approximation of it: a generic pip is the one demand any mana already
        satisfies, so a cost whose colour requirements have all been waived is
        exactly a generic cost of the same size. ``{C}`` goes with them, since
        "any type" names the colourless type too.

        ``X`` is left alone -- it is a number the caster chooses and not a
        colour -- and so is ``text``, which is the printed cost and still what
        the card says.

        Not a `spell_cost_reduction`: this changes nothing about how *much* is
        owed, only which mana may be handed over, and every reduction in the
        engine is clamped so that it can never reach into the coloured pips.
        """
        return ManaCost(
            generic=self.generic
            + sum(self.colored)
            + sum(pip.value for pip in self.hybrid),
            colored=(0,) * N_SYMBOLS,
            x_count=self.x_count,
            text=self.text,
            hybrid=(),
        )

    def symbols_of(self, color: str) -> int:
        """How many mana symbols of one colour appear in this cost — chroma.

        Not the same question as :attr:`colors`, which is a set: chroma reads
        Primalcrux off ``{G}{G}{G}{G}`` as four and ``colors`` says green once.
        Nothing else in the engine had ever looked *inside* a cost this way --
        every other reader wants its total or the set of colours in it.

        A hybrid pip counts for **each** of its colours (rule 107.4f): ``{G/U}``
        is a green mana symbol and a blue one, so a Kitchen Finks in play adds
        to both a green and a white chroma count. ``{2/W}`` likewise counts
        once for white, since the generic half is not a colour.
        """
        idx = SYMBOL_INDEX.get(color.upper())
        if idx is None:
            return 0
        return self.colored[idx] + sum(1 for pip in self.hybrid if idx in pip.symbols)

    def total_required(self, x: int = 0) -> int:
        return self.mana_value(x)

    def with_x(self, x: int) -> Requirement:
        """Flatten to a concrete requirement with ``X`` resolved."""
        return Requirement(
            colored=self.colored,
            generic=self.generic + self.x_count * x,
            hybrid=self.hybrid,
        )

    @property
    def phyrexian_count(self) -> int:
        """How many Phyrexian pips this cost has -- how many life lines it offers."""
        return sum(1 for pip in self.hybrid if pip.phyrexian)

    def paying_phyrexian(self, count: int) -> tuple[ManaCost, int]:
        """This cost with ``count`` of its Phyrexian pips bought with life.

        Returns the *remaining* cost and the life it owes, and that split is the
        whole implementation of rule 107.4f here. A ``{W/P}`` is one symbol with
        two ways to satisfy it; taking the life way is not a discount and not a
        replacement of the cost, it is one pip of the cost being paid in a
        different currency. So the pip leaves ``hybrid`` -- there is nothing left
        of it for the mana solver to pay -- and 2 life is added to what the
        payment charges.

        Removing the pip rather than teaching the solver about life is what keeps
        the rest of the engine honest. Nothing else has to learn a third kind of
        payment: ``satisfies``, ``assign_hybrid``, ``ManaPool.spend`` and every
        cost reduction go on seeing a cost made only of mana. And because it is
        the *pip* that goes and not the cost, a ``{2}{U/P}`` paid the life way is
        still a ``{2}`` that Trinisphere taxes and a cost reduction can shrink,
        which is exactly what an ``alternative_cost`` could never express.

        ``text`` is left as printed: it is what the card says, and it does not
        change because of how one casting of it was paid. Mana value likewise --
        a Gitaxian Probe cast for 2 life is still a mana-value-1 spell, so the
        remaining cost is never what :meth:`mana_value` is read from.

        Pips are taken in printed order. Every Phyrexian symbol costs the same 2
        life, so which of two identical pips goes is not a choice; a cost mixing
        colours (no card prints one) would want the caller to say which, and this
        would be the place to widen.
        """
        if count <= 0:
            return self, 0
        kept: list[HybridPip] = []
        owed = 0
        left = count
        for pip in self.hybrid:
            if left > 0 and pip.phyrexian:
                owed += pip.life or 0
                left -= 1
            else:
                kept.append(pip)
        if left:
            raise DslError(
                f"{self.text!r} has {self.phyrexian_count} phyrexian pips, "
                f"cannot pay {count} of them with life"
            )
        return (
            ManaCost(
                generic=self.generic,
                colored=self.colored,
                x_count=self.x_count,
                text=self.text,
                hybrid=tuple(kept),
            ),
            owed,
        )

    def is_free(self) -> bool:
        return (
            self.generic == 0
            and self.x_count == 0
            and not any(self.colored)
            and not self.hybrid
        )

    def plus(self, other: ManaCost | None) -> ManaCost:
        """This cost with an additional cost folded in -- kicker, for instance.

        The result is what gets *paid*; it is deliberately not what the card's
        mana value is computed from, which stays the printed cost.
        """
        if other is None:
            return self
        return ManaCost(
            generic=self.generic + other.generic,
            colored=tuple(a + b for a, b in zip(self.colored, other.colored, strict=True)),
            x_count=self.x_count + other.x_count,
            text=self.text + other.text,
            hybrid=self.hybrid + other.hybrid,
        )

    def __str__(self) -> str:
        return self.text or "{0}"


def _parse_hybrid(sym: str, text: str) -> HybridPip:
    """``"W/U"``, ``"2/W"`` or ``"W/P"`` -> a :class:`HybridPip`.

    Phyrexian (``{W/P}``) reads as a ``P`` half, and it is *not* folded into the
    colour set: pretending the P were a second colour would make every Phyrexian
    card castable off mana nobody has, and dropping it to a plain ``{W}`` --
    which is what the proxy generator used to do -- deletes the alternative
    payment the card is played for. It becomes :attr:`HybridPip.life` instead,
    and only :func:`assign_hybrid` may spend it.

    Split on every ``/`` rather than once, so a three-part symbol is read
    exactly rather than mangled: ``{W/U/P}`` is one pip payable with white, with
    blue, or with 2 life, and partitioning at the first slash left ``"U/P"`` as a
    half that matched nothing and raised.
    """
    symbols: set[int] = set()
    generic: int | None = None
    life: int | None = None
    for half in sym.split("/"):
        if half.isdigit():
            generic = int(half)
        elif half in SYMBOL_INDEX:
            symbols.add(SYMBOL_INDEX[half])
        elif half == "P":
            life = PHYREXIAN_LIFE
        else:
            raise DslError(
                f"unsupported mana symbol {{{sym}}} in {text!r} "
                "(snow mana is not implemented)"
            )
    if not symbols:
        raise DslError(f"unparsable hybrid symbol {{{sym}}} in {text!r}")
    return HybridPip(symbols=frozenset(symbols), generic=generic, life=life)


@dataclass(frozen=True)
class Requirement:
    """A mana cost with ``X`` already chosen -- what the solver actually pays.

    A Phyrexian pip that reaches here is one the payer chose to pay **with
    mana**: the life half is settled before the requirement is built, by
    :meth:`ManaCost.paying_phyrexian`, which takes the pip out of the cost
    entirely. So nothing in the solver has to know what life is.
    """

    colored: tuple[int, ...] = (0,) * N_SYMBOLS
    generic: int = 0
    hybrid: tuple[HybridPip, ...] = ()

    @property
    def total(self) -> int:
        return sum(self.colored) + self.generic + sum(pip.value for pip in self.hybrid)

    def with_generic(self, generic: int) -> Requirement:
        """This requirement repriced, keeping everything else. Commander tax,
        convoke, delve and every cost reduction land here, and all of them are
        clamped at zero: none may reach through the generic part into the pips."""
        if generic == self.generic:
            return self
        return Requirement(
            colored=self.colored,
            generic=max(0, generic),
            hybrid=self.hybrid,
        )


@dataclass(frozen=True)
class SpentMana:
    """What one payment actually consumed.

    Both halves exist only at the instant `spend` runs: once the pool is
    decremented one blue mana is indistinguishable from another, and the
    permanent that made it is indistinguishable from every other permanent.
    """

    #: Sunburst and converge -- which colours were spent, generic included.
    colors: frozenset[str] = frozenset()
    #: "When **that mana** is spent..." -- which permanents' mana abilities made
    #: the mana this payment consumed. Path of Ancestry, Opal Palace.
    sources: frozenset[int] = frozenset()


class ManaPool:
    """Floating mana.  Emptied at the end of every step and phase.

    ``amounts`` is the count per symbol and ``tags`` is the same thing pip by
    pip: ``tags[i]`` holds one entry for each of ``amounts[i]``, naming the
    permanent whose mana ability made it, or ``None`` for mana that came from an
    effect rather than from a permanent. The two are kept the same length by
    every method here, which is why nothing outside this class may touch
    ``amounts`` directly.

    Provenance is a list rather than a set because "that mana" is a *unit* of
    mana and not a colour: a pool holding one black from Path of Ancestry and
    one black from a Swamp has to be able to spend either.
    """

    __slots__ = ("amounts", "tags")

    def __init__(
        self,
        amounts: Sequence[int] | None = None,
        tags: Sequence[Sequence[int | None]] | None = None,
    ) -> None:
        self.amounts: list[int] = list(amounts) if amounts else _zeros()
        self.tags: list[list[int | None]] = (
            [list(t) for t in tags]
            if tags is not None
            else [[None] * n for n in self.amounts]
        )

    def add(self, symbol: str, count: int = 1, source: int | None = None) -> None:
        index = SYMBOL_INDEX[symbol]
        self.amounts[index] += count
        self.tags[index].extend([source] * count)

    def add_tuple(self, produced: Sequence[int], source: int | None = None) -> None:
        for i, v in enumerate(produced):
            self.amounts[i] += v
            self.tags[i].extend([source] * v)

    def total(self) -> int:
        return sum(self.amounts)

    def clear(self) -> int:
        """Empty the pool, returning how much mana was lost."""
        lost = sum(self.amounts)
        self.amounts = _zeros()
        self.tags = [[] for _ in range(N_SYMBOLS)]
        return lost

    def copy(self) -> ManaPool:
        return ManaPool(self.amounts, self.tags)

    def _take(self, index: int, count: int) -> list[int | None]:
        """Deduct ``count`` pips of one symbol and report who made them.

        **Newest first.** Which same-coloured pip a payment consumes is the
        player's choice in the printed rules, and this is the one bias that
        matches how the payment actually runs: `pay_mana` taps whatever it needs
        immediately before spending, so the mana it just made is at the end of
        the list. A Path of Ancestry tapped *for* a spell therefore pays for that
        spell, which is the only case the card is ever played for. Recorded as a
        simplification in ``docs/rules-coverage.md``.
        """
        self.amounts[index] -= count
        cut = len(self.tags[index]) - count
        taken = self.tags[index][cut:]
        del self.tags[index][cut:]
        return taken

    def to_dict(self) -> dict[str, int]:
        return {s: self.amounts[i] for i, s in enumerate(SYMBOLS) if self.amounts[i]}

    def spend(self, req: Requirement) -> SpentMana:
        """Deduct ``req`` from the pool.  Assumes the pool can cover it.

        Returns what the payment consumed: **which colours** -- sunburst and
        converge -- and **which permanents made it** -- Path of Ancestry's "when
        that mana is spent". Both facts exist only here: by the time the spell is
        on the stack the pool has been decremented and one blue mana is
        indistinguishable from another.

        Colours count mana spent on the **generic** part too, which is what both
        keywords say: a Sunburst artifact cast for `{4}` off five different lands
        enters with five counters, and its printed cost has no coloured pips at
        all. Colorless is not a colour, so `{C}` contributes nothing there -- but
        it is a source like any other, so it still names its permanent.
        """
        spent: set[str] = set()
        made_by: set[int] = set()
        remaining_generic = req.generic
        for i in range(N_SYMBOLS):
            need = req.colored[i]
            if need:
                if self.amounts[i] < need:
                    raise ValueError("pool cannot cover colored requirement")
                made_by.update(t for t in self._take(i, need) if t is not None)
                if i < len(COLOR_ORDER):
                    spent.add(COLOR_ORDER[i].value)
        # Hybrid pips choose their half here, and must choose it the *same* way
        # `satisfies` decided they could -- so both run one routine. A second,
        # looser rule here could take a symbol the solver was relying on for a
        # coloured pip and strand the payment halfway through.
        if req.hybrid:
            chosen = assign_hybrid(list(self.amounts), req.hybrid, remaining_generic)
            if chosen is None:
                raise ValueError("pool cannot cover hybrid requirement")
            for pip, symbol in zip(req.hybrid, chosen, strict=True):
                if symbol < 0:
                    remaining_generic += pip.generic or 0
                else:
                    made_by.update(t for t in self._take(symbol, 1) if t is not None)
                    if symbol < len(COLOR_ORDER):
                        spent.add(COLOR_ORDER[symbol].value)
        # Pay generic from the most plentiful symbols first so scarce colours are
        # preserved for later spells in the same step.  Deterministic by index.
        while remaining_generic > 0:
            best = max(range(N_SYMBOLS), key=lambda i: (self.amounts[i], -i))
            if self.amounts[best] <= 0:
                raise ValueError("pool cannot cover generic requirement")
            take = min(self.amounts[best], remaining_generic)
            made_by.update(t for t in self._take(best, take) if t is not None)
            remaining_generic -= take
            if best < len(COLOR_ORDER):
                spent.add(COLOR_ORDER[best].value)
        return SpentMana(colors=frozenset(spent), sources=frozenset(made_by))

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"ManaPool({self.to_dict()})"


#: The placeholder a restriction group carries for "the type this permanent
#: chose" -- Cavern of Souls, Unclaimed Territory, Secluded Courtyard.
#:
#: A restriction is otherwise a set of lowercased literal names fixed when the
#: card loads, and the chosen type does not exist until the permanent is on the
#: battlefield. So the load-time set carries this sentinel and
#: `costs.resolve_mana_restriction` substitutes the object's `chosen_type` at the
#: moment the mana is offered. A `\0` prefix cannot collide with a real card type
#: or subtype: the loader's shape check requires letters, and this is the same
#: trick `characteristics.resolve_chosen_subtypes` plays with `"\0none"`.
CHOSEN_TYPE = "\0chosen"

#: The two things mana is ever spent on, and the two halves a printed spend
#: restriction distinguishes: "Spend this mana only to **cast** a creature spell
#: of the chosen type or **activate an ability of** a creature source of the
#: chosen type."
CAST = "cast"
ACTIVATE = "activate"


@dataclass(frozen=True)
class SpendPurpose:
    """What a payment is *for*, as a restricted source needs to see it.

    Two parts, and both are load-bearing.  ``names`` is the flat set of
    lowercased types and subtypes -- of the spell being cast, or of the source
    whose ability is being activated.  ``kind`` is which of those two it was.

    The kind is not decoration.  Every restriction shipped before Secluded
    Courtyard reads "spend this mana only to **cast** …", and a purpose that
    carried names alone would have let Herd Heirloom, Ancient Ziggurat and
    Master of Dark Rites pay to *activate* an ability of any creature that
    matched -- a strictly better card than each of them prints, arriving without
    a line of their JSON changing.
    """

    kind: str
    names: frozenset[str]


@dataclass(frozen=True)
class ManaRestriction:
    """"Spend this mana only to cast X (or activate an ability of Y)."

    Two independent permissions, because the printed sentence gives them
    different subjects: Secluded Courtyard casts *a creature spell* of the
    chosen type and activates an ability of *a creature source* of the chosen
    type.  They coincide on that card and need not on the next one, so they are
    stored apart rather than as one list with a flag.

    Each is an **any-of of all-ofs**: a tuple of groups, every name in a group
    required at once.  Master of Dark Rites' "Vampire, Cleric, and/or Demon
    spells" is three one-name groups -- the printed "and/or" is an any-of.
    "A creature spell **of** the chosen type" is one two-name group, because
    either half alone is a different and better card: `creature` on its own casts
    every creature ever printed.

    An empty tuple is a real answer and means "never": a card that says nothing
    about activating abilities does not permit it.
    """

    cast: tuple[frozenset[str], ...] = ()
    activate: tuple[frozenset[str], ...] = ()
    #: Does any group name :data:`CHOSEN_TYPE`?  Derived here rather than stored
    #: by the loader so it cannot drift from the groups it describes, and
    #: computed once at load so `costs.resolve_mana_restriction` can return an
    #: entirely static restriction untouched instead of rebuilding it per
    #: battlefield walk.
    dynamic: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "dynamic", any(CHOSEN_TYPE in g for g in self.cast + self.activate)
        )

    def groups(self, kind: str) -> tuple[frozenset[str], ...]:
        return self.activate if kind == ACTIVATE else self.cast


@dataclass(frozen=True)
class ManaSource:
    """One untapped permanent's mana ability, flattened into its possible yields.

    ``options`` holds every 6-tuple the ability could produce (a dual land that
    reads "Add {G} or {U}" contributes two options; one that reads "Add {G}{U}"
    contributes a single option producing two mana).
    """

    oid: int
    ability_index: int
    options: tuple[tuple[int, ...], ...]
    is_land: bool = True
    sort_key: tuple = ()
    #: "Spend this mana only to cast a creature spell."  ``None`` is ordinary
    #: mana.  Enforced by *filtering sources* before the solver ever sees them
    #: rather than by tagging the pool: mana here is tapped at the moment it is
    #: spent, so a source that may not pay for this spell simply is not offered,
    #: and the solver's inner loop is untouched.
    #:
    #: Already resolved against *this permanent*: `costs.resolve_mana_restriction`
    #: has substituted any chosen type, so what arrives here is literal names.
    restriction: ManaRestriction | None = None

    def permits(self, purpose: SpendPurpose | None) -> bool:
        """May this source pay for what ``purpose`` describes?

        Both halves of the purpose are asked: the restriction's groups **for
        that kind** (casting a spell, or activating an ability), and then whether
        any one group's names are all present.

        ``None`` means "no particular spell in mind", and withholds every
        restricted source -- an under-count rather than an over-count, which is
        the safe direction for a number the AI reads.
        """
        if self.restriction is None:
            return True
        if purpose is None:
            return False
        return any(group <= purpose.names for group in self.restriction.groups(purpose.kind))

    def max_output(self) -> int:
        return max((sum(o) for o in self.options), default=0)

    def producible(self) -> frozenset[int]:
        return frozenset(i for o in self.options for i in range(N_SYMBOLS) if o[i] > 0)


@dataclass
class Payment:
    """The solver's answer: which abilities to activate, and the resulting spend.

    Each tap records ``(oid, ability_index, option_index)``.  The option index
    matters: a dual land's "Add {G} or {U}" is one ability with two options, and
    the caller must add exactly the mana the solver assumed, not re-decide.
    """

    taps: list[tuple[int, int, int]] = field(default_factory=list)
    produced: tuple[int, ...] = (0,) * N_SYMBOLS

    @property
    def is_empty(self) -> bool:
        return not self.taps


def parse_mana_production(text: str) -> tuple[int, ...]:
    """Parse a mana *production* string like ``"{G}{U}"`` into a 6-tuple."""
    out = _zeros()
    pos = 0
    for match in _TOKEN_RE.finditer(text or ""):
        if match.start() != pos:
            raise DslError(f"unparsable mana production {text!r}")
        pos = match.end()
        sym = match.group(1).strip().upper()
        if sym.isdigit():
            # "Add {2}" means two colorless/generic mana; model it as {C}.
            out[SYMBOL_INDEX[COLORLESS]] += int(sym)
        elif sym in SYMBOL_INDEX:
            out[SYMBOL_INDEX[sym]] += 1
        else:
            raise DslError(f"unsupported produced mana symbol {{{sym}}} in {text!r}")
    if pos != len(text or ""):
        raise DslError(f"unparsable mana production {text!r}")
    return tuple(out)


def satisfies(produced: Sequence[int], req: Requirement) -> bool:
    """Can ``produced`` pay ``req``?

    Colored (and ``{C}``) pips need their exact symbol; everything left over --
    of any symbol -- can pay generic.
    """
    surplus = 0
    for i in range(N_SYMBOLS):
        have = produced[i]
        need = req.colored[i]
        if have < need:
            return False
        surplus += have - need
    if not req.hybrid:
        # The overwhelming majority of costs. Kept as the untouched fast path,
        # because this runs inside the solver's inner loop on every priority
        # window and in every arena game.
        return surplus >= req.generic

    left = [produced[i] - req.colored[i] for i in range(N_SYMBOLS)]
    return assign_hybrid(left, req.hybrid, req.generic) is not None


def assign_hybrid(
    left: list[int], pips: Sequence[HybridPip], generic: int
) -> list[int] | None:
    """Pick a half for each hybrid pip, or ``None`` if the mana cannot cover them.

    Returns one entry per pip: the symbol index it takes, or ``-1`` for "paid
    with its generic alternative".  Both :func:`satisfies` and
    :meth:`ManaPool.spend` go through here, so the decision that a cost *can* be
    paid and the deduction that pays it can never disagree.

    A Phyrexian pip has no branch here and needs none.  By the time a cost
    reaches the solver, every pip the payer chose to buy with life has already
    been taken out of it by :meth:`ManaCost.paying_phyrexian`, so a ``{W/P}``
    still in ``pips`` is one being paid the white way -- which is why life,
    which no mana source produces and no pool holds, never enters the solver.

    Exhaustive rather than greedy, because the choices interact: with one white
    and one blue mana, ``{W/U}{W/U}`` is payable only if the two pips take
    different symbols, and any rule-of-thumb that picks "most plentiful first"
    gets that wrong.  Real costs carry at most three hybrid pips, so the search
    is tiny -- and it never runs at all for a cost without them.
    """
    if not pips:
        return [] if sum(left) >= generic else None

    pip, rest = pips[0], pips[1:]
    for i in sorted(pip.symbols):
        if left[i] > 0:
            left[i] -= 1
            tail = assign_hybrid(left, rest, generic)
            left[i] += 1
            if tail is not None:
                return [i, *tail]
    if pip.generic is not None:
        # "{2/W}" paid the expensive way: two mana of anything at all.
        tail = assign_hybrid(left, rest, generic + pip.generic)
        if tail is not None:
            return [-1, *tail]
    return None


def solve_payment(
    req: Requirement,
    pool: ManaPool | Sequence[int],
    sources: Sequence[ManaSource],
) -> Payment | None:
    """Find a set of mana abilities to activate that pays ``req``.

    Returns ``None`` when the cost cannot be paid.  A greedy pass handles every
    ordinary board; a bounded backtracking search catches the awkward cases
    (duals covering two different pips, filter lands, and so on).
    """
    base = tuple(pool.amounts) if isinstance(pool, ManaPool) else tuple(pool)
    if satisfies(base, req):
        return Payment(taps=[], produced=base)

    ordered = sorted(sources, key=lambda s: (s.sort_key, s.oid, s.ability_index))
    if not ordered:
        return None

    greedy = _greedy_solve(base, req, ordered)
    if greedy is not None:
        return greedy
    return _search_solve(base, req, ordered)


def max_affordable_x(
    cost: ManaCost,
    pool: ManaPool | Sequence[int],
    sources: Sequence[ManaSource],
    cap: int = 20,
    *,
    extra_generic: int = 0,
) -> int:
    """Largest ``X`` this player can pay for, or ``-1`` if even ``X=0`` is unaffordable.

    ``extra_generic`` is commander tax minus any cost reduction -- everything the
    caller will add to the generic part before it actually pays.  Without it a
    taxed ``{X}`` commander reports a maximum its own payment then cannot meet,
    and the card vanishes from the legal list even at ``X = 0``.  Negative values
    (a reduction) are clamped the same way :func:`costs.pay` clamps them.
    """

    def probe(x: int) -> bool:
        req = cost.with_x(x)
        if extra_generic:
            req = req.with_generic(req.generic + extra_generic)
        return solve_payment(req, pool, sources) is not None

    if cost.x_count <= 0:
        return 0 if probe(0) else -1
    best = -1
    for x in range(cap + 1):
        if not probe(x):
            break
        best = x
    return best


# --------------------------------------------------------------------------
# solver internals
# --------------------------------------------------------------------------


def _flexibility(source: ManaSource) -> int:
    return len(source.producible())


def _colour_abundance(sources: Iterable[ManaSource]) -> list[int]:
    """How many of these sources can produce each symbol."""
    counts = _zeros()
    for source in sources:
        for i in source.producible():
            counts[i] += 1
    return counts


def _greedy_solve(
    base: tuple[int, ...], req: Requirement, sources: Sequence[ManaSource]
) -> Payment | None:
    produced = list(base)
    used: set[int] = set()
    taps: list[tuple[int, int]] = []

    # Phase A -- cover the coloured (and {C}) pips, most-constrained colour first.
    while True:
        deficits = [max(0, req.colored[i] - produced[i]) for i in range(N_SYMBOLS)]
        if not any(deficits):
            break
        candidates: dict[int, list[ManaSource]] = {}
        for i in range(N_SYMBOLS):
            if deficits[i] == 0:
                continue
            candidates[i] = [
                s for k, s in enumerate(sources) if k not in used and i in s.producible()
            ]
            if not candidates[i]:
                return None
        colour = min(candidates, key=lambda i: (len(candidates[i]), i))
        pool_of = candidates[colour]
        pool_of.sort(key=lambda s: (_flexibility(s), 0 if s.is_land else 1, s.sort_key, s.oid))
        chosen = pool_of[0]
        idx = next(k for k, s in enumerate(sources) if s is chosen)
        viable = [(j, o) for j, o in enumerate(chosen.options) if o[colour] > 0]
        option_index, option = max(
            viable,
            key=lambda jo: (
                sum(min(jo[1][i], deficits[i]) for i in range(N_SYMBOLS)),
                sum(jo[1]),
                tuple(-v for v in jo[1]),
                -jo[0],
            ),
        )
        for i in range(N_SYMBOLS):
            produced[i] += option[i]
        used.add(idx)
        taps.append((chosen.oid, chosen.ability_index, option_index))

    # Phase B -- top up generic with whatever is left.
    #
    # Spend the most *abundant* colours first.  Tapping the only Forest to pay a
    # generic pip and then being unable to cast a green spell in the same turn is
    # the single most common way naive auto-payment plays badly, and the fix is
    # this one sort key.  Abundance is measured over the player's whole mana base
    # rather than the shrinking remainder, so a run of generic payments keeps
    # draining the same plentiful colour instead of alternating.
    abundance = _colour_abundance(sources)
    while not satisfies(produced, req):
        remaining = [
            (k, s) for k, s in enumerate(sources) if k not in used and s.max_output() > 0
        ]
        if not remaining:
            return None
        remaining.sort(
            key=lambda ks: (
                -ks[1].max_output(),
                -min((abundance[i] for i in ks[1].producible()), default=0),
                0 if ks[1].is_land else 1,
                ks[1].sort_key,
            )
        )
        idx, source = remaining[0]
        option_index, option = max(
            enumerate(source.options), key=lambda jo: (sum(jo[1]), tuple(-v for v in jo[1]), -jo[0])
        )
        for i in range(N_SYMBOLS):
            produced[i] += option[i]
        used.add(idx)
        taps.append((source.oid, source.ability_index, option_index))

    return Payment(taps=taps, produced=tuple(produced))


def _search_solve(
    base: tuple[int, ...], req: Requirement, sources: Sequence[ManaSource]
) -> Payment | None:
    """Bounded depth-first fallback over "skip this source / use option k"."""
    n = len(sources)
    suffix_max = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suffix_max[i] = suffix_max[i + 1] + sources[i].max_output()

    nodes = 0
    needed_total = req.total

    def recurse(idx: int, produced: tuple[int, ...], taps: list[tuple[int, int]]):
        nonlocal nodes
        nodes += 1
        if nodes > MAX_SOLVER_NODES:
            return None
        if satisfies(produced, req):
            return Payment(taps=list(taps), produced=produced)
        if idx >= n:
            return None
        if sum(produced) + suffix_max[idx] < needed_total:
            return None
        source = sources[idx]
        # Try using this source (each option, richest first) before skipping it.
        options = sorted(enumerate(source.options), key=lambda jo: (-sum(jo[1]), jo[1]))
        for option_index, option in options:
            nxt = tuple(produced[i] + option[i] for i in range(N_SYMBOLS))
            taps.append((source.oid, source.ability_index, option_index))
            found = recurse(idx + 1, nxt, taps)
            taps.pop()
            if found is not None:
                return found
        return recurse(idx + 1, produced, taps)

    return recurse(0, base, [])


def format_symbols(amounts: Iterable[int]) -> str:
    """Render a 6-tuple as ``{G}{G}{U}`` for logs and the UI."""
    parts: list[str] = []
    for i, v in enumerate(amounts):
        parts.extend("{" + SYMBOLS[i] + "}" for _ in range(v))
    return "".join(parts) or "{0}"
