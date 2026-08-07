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
class ManaCost:
    """A parsed mana cost.

    ``colored`` is a 6-tuple aligned with :data:`SYMBOLS`; the final slot is the
    ``{C}`` colorless requirement, which generic mana cannot satisfy but which can
    itself pay generic.
    """

    generic: int = 0
    colored: tuple[int, ...] = (0,) * N_SYMBOLS
    x_count: int = 0
    text: str = ""

    @staticmethod
    def parse(text: str | None) -> ManaCost:
        """Parse ``"{4}{G}{U}"``.  ``None`` and ``""`` mean "no cost" (e.g. lands)."""
        if not text:
            return ManaCost(text="")
        generic = 0
        x_count = 0
        colored = _zeros()
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
            else:
                raise DslError(
                    f"unsupported mana symbol {{{sym}}} in {text!r} "
                    "(hybrid, phyrexian and snow mana are not implemented)"
                )
        if pos != len(text):
            raise DslError(f"unparsable mana cost {text!r} (trailing {text[pos:]!r})")
        return ManaCost(generic=generic, colored=tuple(colored), x_count=x_count, text=text)

    def mana_value(self, x: int = 0) -> int:
        """Converted mana cost.  ``X`` counts as 0 anywhere but on the stack."""
        return self.generic + sum(self.colored) + self.x_count * x

    @property
    def colors(self) -> frozenset[Color]:
        return frozenset(
            COLOR_ORDER[i] for i in range(len(COLOR_ORDER)) if self.colored[i] > 0
        )

    def total_required(self, x: int = 0) -> int:
        return self.mana_value(x)

    def with_x(self, x: int) -> Requirement:
        """Flatten to a concrete requirement with ``X`` resolved."""
        return Requirement(
            colored=self.colored, generic=self.generic + self.x_count * x
        )

    def is_free(self) -> bool:
        return self.generic == 0 and self.x_count == 0 and not any(self.colored)

    def __str__(self) -> str:
        return self.text or "{0}"


@dataclass(frozen=True)
class Requirement:
    """A mana cost with ``X`` already chosen -- what the solver actually pays."""

    colored: tuple[int, ...] = (0,) * N_SYMBOLS
    generic: int = 0

    @property
    def total(self) -> int:
        return sum(self.colored) + self.generic


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

    def spend(self, req: Requirement) -> None:
        """Deduct ``req`` from the pool.  Assumes the pool can cover it."""
        remaining_generic = req.generic
        for i in range(N_SYMBOLS):
            need = req.colored[i]
            if need:
                if self.amounts[i] < need:
                    raise ValueError("pool cannot cover colored requirement")
                self.amounts[i] -= need
        # Pay generic from the most plentiful symbols first so scarce colours are
        # preserved for later spells in the same step.  Deterministic by index.
        while remaining_generic > 0:
            best = max(range(N_SYMBOLS), key=lambda i: (self.amounts[i], -i))
            if self.amounts[best] <= 0:
                raise ValueError("pool cannot cover generic requirement")
            take = min(self.amounts[best], remaining_generic)
            self.amounts[best] -= take
            remaining_generic -= take

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
    return surplus >= req.generic


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
) -> int:
    """Largest ``X`` this player can pay for, or ``-1`` if even ``X=0`` is unaffordable."""
    if cost.x_count <= 0:
        return 0 if solve_payment(cost.with_x(0), pool, sources) else -1
    best = -1
    for x in range(cap + 1):
        if solve_payment(cost.with_x(x), pool, sources) is None:
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
