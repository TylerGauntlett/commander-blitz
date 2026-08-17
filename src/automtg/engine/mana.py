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


@dataclass(frozen=True)
class HybridPip:
    """One ``{W/U}``-style pip: pay any of ``symbols``, or ``generic`` generic.

    Two shapes of hybrid, one representation.  ``{W/U}`` is a choice between two
    coloured symbols and has no generic alternative.  ``{2/W}`` is a choice
    between one coloured symbol and two generic, which is why the alternative is
    a *number* and not another symbol.
    """

    symbols: frozenset[int] = frozenset()
    generic: int | None = None

    @property
    def value(self) -> int:
        """What this pip contributes to mana value: ``{W/U}`` 1, ``{2/W}`` 2."""
        return self.generic if self.generic is not None else 1


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
                    "(phyrexian and snow mana are not implemented)"
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
    """``"W/U"`` or ``"2/W"`` -> a :class:`HybridPip`.

    Phyrexian (``{W/P}``) is deliberately still rejected: it is a *life* payment
    dressed as a mana symbol, and pretending it is a colour choice would make
    every phyrexian card cheaper than it is printed.
    """
    left, _, right = sym.partition("/")
    symbols: set[int] = set()
    generic: int | None = None
    for half in (left, right):
        if half.isdigit():
            generic = int(half)
        elif half in SYMBOL_INDEX:
            symbols.add(SYMBOL_INDEX[half])
        else:
            raise DslError(
                f"unsupported mana symbol {{{sym}}} in {text!r} "
                "(phyrexian and snow mana are not implemented)"
            )
    if not symbols:
        raise DslError(f"unparsable hybrid symbol {{{sym}}} in {text!r}")
    return HybridPip(symbols=frozenset(symbols), generic=generic)


@dataclass(frozen=True)
class Requirement:
    """A mana cost with ``X`` already chosen -- what the solver actually pays."""

    colored: tuple[int, ...] = (0,) * N_SYMBOLS
    generic: int = 0
    hybrid: tuple[HybridPip, ...] = ()

    @property
    def total(self) -> int:
        return sum(self.colored) + self.generic + sum(pip.value for pip in self.hybrid)


class ManaPool:
    """Floating mana.  Emptied at the end of every step and phase."""

    __slots__ = ("amounts",)

    def __init__(self, amounts: Sequence[int] | None = None) -> None:
        self.amounts: list[int] = list(amounts) if amounts else _zeros()

    def add(self, symbol: str, count: int = 1) -> None:
        self.amounts[SYMBOL_INDEX[symbol]] += count

    def add_tuple(self, produced: Sequence[int]) -> None:
        for i, v in enumerate(produced):
            self.amounts[i] += v

    def total(self) -> int:
        return sum(self.amounts)

    def clear(self) -> int:
        """Empty the pool, returning how much mana was lost."""
        lost = sum(self.amounts)
        self.amounts = _zeros()
        return lost

    def copy(self) -> ManaPool:
        return ManaPool(self.amounts)

    def to_dict(self) -> dict[str, int]:
        return {s: self.amounts[i] for i, s in enumerate(SYMBOLS) if self.amounts[i]}

    def spend(self, req: Requirement) -> frozenset[str]:
        """Deduct ``req`` from the pool.  Assumes the pool can cover it.

        Returns **which colours were actually spent** -- sunburst and converge,
        and the one fact about a payment that no card could previously read.
        The information exists only here: by the time the spell is on the stack
        the pool has been decremented and one blue mana is indistinguishable from
        another.

        It counts mana spent on the **generic** part too, which is what both
        keywords say: a Sunburst artifact cast for `{4}` off five different
        lands enters with five counters, and its printed cost has no coloured
        pips at all. Colorless is not a colour, so `{C}` contributes nothing.
        """
        spent: set[str] = set()
        remaining_generic = req.generic
        for i in range(N_SYMBOLS):
            need = req.colored[i]
            if need:
                if self.amounts[i] < need:
                    raise ValueError("pool cannot cover colored requirement")
                self.amounts[i] -= need
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
                    self.amounts[symbol] -= 1
                    if symbol < len(COLOR_ORDER):
                        spent.add(COLOR_ORDER[symbol].value)
        # Pay generic from the most plentiful symbols first so scarce colours are
        # preserved for later spells in the same step.  Deterministic by index.
        while remaining_generic > 0:
            best = max(range(N_SYMBOLS), key=lambda i: (self.amounts[i], -i))
            if self.amounts[best] <= 0:
                raise ValueError("pool cannot cover generic requirement")
            take = min(self.amounts[best], remaining_generic)
            self.amounts[best] -= take
            remaining_generic -= take
            if best < len(COLOR_ORDER):
                spent.add(COLOR_ORDER[best].value)
        return frozenset(spent)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"ManaPool({self.to_dict()})"


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
    restriction: frozenset[str] | None = None

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
            req = Requirement(
                colored=req.colored,
                generic=max(0, req.generic + extra_generic),
                hybrid=req.hybrid,
            )
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
