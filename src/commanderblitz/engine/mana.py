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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, NamedTuple

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

    def as_any_color(self) -> ManaCost:
        """This cost as paid with mana spent "as though it were mana of any color".

        Elder Brain: "you may spend mana as though it were mana of any color to
        cast it." Every coloured symbol -- ``{W}`` through ``{G}``, and each hybrid
        or Phyrexian pip still owed as mana -- may be paid with any one mana, the
        colourless kind included (the Mycosynth Lattice ruling: colourless mana
        spent this way is spent as though it had a colour). So each becomes one
        generic, and a hybrid pip becomes **one** whatever its other half was,
        because its coloured half is now payable with a single mana of anything.

        ``{C}`` is not a colour and stays: mana spent as though it were any
        *colour* is still not colourless mana, which is the whole difference from
        :meth:`as_any_type` (Valigarmanda's "mana of any type"), where ``{C}``
        folds too. ``X`` and ``text`` are left alone for the reasons given there,
        and 609.4b is why this is a payment rule and never a new cost: mana value
        and colour are read off the printed cost, not this one.
        """
        colorless = SYMBOL_INDEX[COLORLESS]
        folded = sum(n for i, n in enumerate(self.colored) if i != colorless)
        colored = [0] * N_SYMBOLS
        colored[colorless] = self.colored[colorless]
        return ManaCost(
            generic=self.generic + folded + len(self.hybrid),
            colored=tuple(colored),
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

    def black_as_phyrexian(self) -> ManaCost:
        """This cost with every ``{B}`` in it payable with 2 life as well.

        K'rrik, Son of Yawgmoth: "For each {B} in a cost, you may pay 2 life
        rather than pay that mana." Read exactly as a Phyrexian pip is (107.4f),
        and the rulings say where the edges are: a plain ``{B}`` becomes a
        ``{B/P}``; a pip that *may* be paid with black -- ``{B/R}``, ``{2/B}`` --
        gains the life half too, because choosing to pay it with {B} is what
        lets K'rrik buy it; ``{B/P}`` already has it; generic mana never does,
        and nor does a pip with no black in it.

        What the cost *is* does not move -- :attr:`colored` loses the pips but
        :attr:`hybrid` gains them, so :meth:`mana_value`, :attr:`colors` and
        :meth:`symbols_of` read the same numbers, and ``text`` stays printed.
        The converted plain pips go first in :attr:`hybrid` because
        :meth:`paying_phyrexian` buys pips in that order and a single-symbol pip
        is the one no other mana could have paid.
        """
        black = SYMBOL_INDEX["B"]
        plain = self.colored[black]
        widened = tuple(
            HybridPip(symbols=pip.symbols, generic=pip.generic, life=PHYREXIAN_LIFE)
            if black in pip.symbols and pip.life is None
            else pip
            for pip in self.hybrid
        )
        if not plain and widened == self.hybrid:
            return self
        colored = list(self.colored)
        colored[black] = 0
        return ManaCost(
            generic=self.generic,
            colored=tuple(colored),
            x_count=self.x_count,
            text=self.text,
            hybrid=(
                *(HybridPip(symbols=frozenset({black}), life=PHYREXIAN_LIFE),) * plain,
                *widened,
            ),
        )

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

        Pips are taken single-symbol first, then in printed order. Every
        Phyrexian symbol costs the same 2 life, so which of two identical pips
        goes is not a choice. Under K'rrik (:meth:`black_as_phyrexian`) a
        ``{B}`` and a ``{B/R}`` can sit in one cost, and buying the ``{B}`` is
        never worse: anything that could pay it could pay the ``{B/R}``. Two
        *different* payable-with-life pips in one cost -- ``{2/B}`` beside
        ``{B/R}``, or a ``{W/P}`` beside a ``{B}`` under K'rrik, which no shipped
        card prints -- would want the caller to say which, and
        this would be the place to widen.
        """
        if count <= 0:
            return self, 0
        kept: list[HybridPip] = []
        owed = 0
        left = count
        bought: set[int] = set()
        order = sorted(
            range(len(self.hybrid)),
            key=lambda i: (
                not (len(self.hybrid[i].symbols) == 1 and self.hybrid[i].generic is None),
                i,
            ),
        )
        for i in order:
            if left > 0 and self.hybrid[i].phyrexian:
                owed += self.hybrid[i].life or 0
                left -= 1
                bought.add(i)
        for i, pip in enumerate(self.hybrid):
            if i not in bought:
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


def _printed_shape(cost: ManaCost) -> tuple:
    """What a printed cost *is*, with the spelling of it thrown away.

    Every symbol counted and nothing summed across kinds: ``{C}`` is a coloured
    slot and not generic, ``{2/W}`` and ``{W/P}`` are hybrid pips and not the
    generic or white they can be paid with, and ``{X}`` is its own count. So
    ``{1}`` equals only a cost of one generic symbol.
    """
    hybrid: dict[HybridPip, int] = {}
    for pip in cost.hybrid:
        hybrid[pip] = hybrid.get(pip, 0) + 1
    return (cost.generic, cost.colored, cost.x_count, frozenset(hybrid.items()))


def _wanted_shape(text: str) -> tuple:
    return _printed_shape(ManaCost.parse("".join(text.split())))


def printed_cost_is(cost: ManaCost, wanted: Iterable[str]) -> bool:
    """ "An artifact card with **mana cost {0} or {1}**" -- Urza's Saga.

    The printed cost, compared symbol for symbol against each of ``wanted``.
    Not `mana_value`, which is a number read off the cost and cannot say it:

    - a card with **no mana cost** (202.1b -- an artifact land, Lotus Bloom) has
      mana value 0 and does not have mana cost {0}, so it never matches here;
    - ``{X}`` scores 0 (202.3b) and ``{X}`` is not ``{0}``;
    - ``{W}``, ``{C}``, ``{W/P}`` and ``{2/W}`` are each mana value 1 or 2 and
      none of them is ``{1}``.
    """
    if not cost.text:
        return False
    shape = _printed_shape(cost)
    return any(_wanted_shape(w) == shape for w in wanted)


def validate_printed_cost_list(value: object, where: str) -> None:
    """Load-time check for a ``mana_cost`` filter clause: a list of costs.

    A bare string is refused rather than wrapped: iterated, ``"{1}"`` is three
    characters, and a list is what "{0} or {1}" is. An empty string would name
    "no mana cost", which this clause exists to never match -- written, it is a
    filter that silently matches nothing.
    """
    if isinstance(value, str) or not isinstance(value, (list, tuple)) or not value:
        raise DslError(
            f"{where}: 'mana_cost' is a non-empty list of printed costs, "
            f'e.g. ["{{0}}", "{{1}}"], got {value!r}'
        )
    for entry in value:
        if not isinstance(entry, str) or not "".join(entry.split()):
            raise DslError(
                f"{where}: 'mana_cost' entries are printed costs like \"{{1}}\"; "
                f"a card with no mana cost never matches, got {entry!r}"
            )
        _wanted_shape(entry)  # raises DslError on an unparsable cost


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

    def as_any_color(self) -> Requirement:
        """This requirement as paid by someone spending mana as any colour.

        :meth:`ManaCost.as_any_color` read one level down, for the same reason
        :meth:`with_generic` exists here rather than on the cost: a discount is
        applied to the requirement, and Chromatic Orrery's waiver has to be read
        **after** it. Loosening the cost first would let "costs {2} less" reach
        through the generic part into pips that are by then generic -- a
        ``{1}{G}`` ability discounted by two would come out free instead of
        owing the one mana the ``{G}`` still is.

        The fold is identical: every coloured pip and every hybrid one becomes a
        single generic, ``{C}`` stays because colourless is not a colour, and a
        requirement with nothing to loosen is returned unchanged so the caller
        can use identity as its cheap test.
        """
        colorless = SYMBOL_INDEX[COLORLESS]
        folded = sum(n for i, n in enumerate(self.colored) if i != colorless)
        if not folded and not self.hybrid:
            return self
        colored = [0] * N_SYMBOLS
        colored[colorless] = self.colored[colorless]
        return Requirement(
            colored=tuple(colored),
            generic=self.generic + folded + len(self.hybrid),
            hybrid=(),
        )


class ManaKeywordGrant(NamedTuple):
    """ "…it gains haste until end of turn" -- Arena of Glory's second rider.

    The *other* kind of thing a pip can carry. `Pip.uncounterable` is a fact the
    casting rules read once and throw away; this one has to outlive the spell it
    paid for, because the permanent the spell becomes is what gains the keyword.

    ``spell_types`` is the printed "**creature** spell" half. Empty means any
    spell, which no card prints today and which the shape gets for free -- the
    restriction is on the *grant*, not on what the mana may buy, and that is the
    whole difference from `ManaRestriction`: Arena of Glory's mana pays for
    anything, and only a creature spell is given anything back.

    The duration is fixed at until-end-of-turn rather than being a field,
    because that is the only duration printed on this shape. A grant with no
    duration is riot's, and riot is `granted_keywords` and a different slot.
    """

    keywords: tuple[str, ...] = ()
    spell_types: tuple[str, ...] = ()


class ManaOrigin(NamedTuple):
    """What the permanent that made a unit of mana **was**, at that instant.

    Named apart from :class:`ManaSource` below, which is the *solver's* view of
    a permanent that could make mana: that one is an offer with an oid and a
    live board behind it, this one is a memory of a permanent that may be gone.

    "…if mana from a **Treasure** was spent to cast it" -- Smaug, Wicked Worm.
    A whole class of permanents rather than one named object, which is why the
    oid in :attr:`Pip.source` cannot answer it: a Treasure is *sacrificed* to
    make its mana, and `sba._tokens_and_attachments` pops a token that has left
    the battlefield straight out of ``state.objects``. By the time the spell is
    on the stack the recorded oid resolves to nothing at all, so a subtype test
    against it matches nothing -- silently, which is the dangerous direction.

    So the characteristics travel with the mana instead of a pointer back to an
    object that may no longer exist. Snapshotted from *derived* characteristics
    (`characteristics.mana_source_traits`), because a Treasure that something
    else turned into an artifact creature is still a Treasure, and a land
    animated into a creature really is a creature while the mana it made is in
    the pool.

    Hashable, so a payment can collect a set of them; ``oid`` rides along so a
    reader that still wants the object has it, and so two identical Treasures
    do not collapse into one entry.
    """

    oid: int | None = None
    name: str = ""
    types: frozenset[str] = frozenset()
    subtypes: frozenset[str] = frozenset()
    supertypes: frozenset[str] = frozenset()
    #: Who controlled the source when it made the mana -- "mana from a Treasure
    #: **you control**". The controller at spend time is the wrong question for
    #: the same reason the oid is: the Treasure is gone.
    controller: int | None = None


class Pip(NamedTuple):
    """One unit of mana in the pool, and what is known about where it came from.

    The pool holds six integers; everything else about a unit of mana lives
    here, one entry per point of ``amounts``.

    ``source`` is the permanent whose mana ability made it, or ``None`` for mana
    an effect produced. ``uncounterable`` is Cavern of Souls' rider -- "…and
    that spell can't be countered" -- and it has to ride the **pip** rather than
    the permanent, because Cavern has two mana abilities and only the second one
    prints the clause. Recorded per permanent instead, tapping a Cavern for its
    plain ``{C}`` would make the spell uncounterable too, which is a strictly
    better card than the one printed.

    ``source_traits`` is what that permanent *was* -- see :class:`ManaOrigin`.
    It rides the pip beside the oid rather than replacing it because the two
    answer different questions: "that mana" (Path of Ancestry) is about one
    object and needs the oid, and "mana from a Treasure" (Smaug) is about a
    class and must survive the object's death.
    """

    source: int | None = None
    uncounterable: bool = False
    #: The turn through which this pip survives step and phase boundaries --
    #: "Until end of turn, you don't lose this mana as steps and phases end"
    #: (Tanuki Transplanter). ``-1``, the default, is ordinary mana.
    #:
    #: The turn rather than a flag, for `GameObject.drawn_turn`'s reason: a flag
    #: would need clearing at the turn boundary, and mana that forgot to be
    #: cleared is mana that never empties.
    persists_through_turn: int = -1
    #: Arena of Glory's "…it gains haste until end of turn". On the pip for
    #: `uncounterable`'s reason and one step further: Arena has two mana
    #: abilities and only the exerting one prints the clause, so recorded per
    #: permanent its plain ``{R}`` would hand out haste for free.
    grant: ManaKeywordGrant | None = None
    source_traits: ManaOrigin | None = None
    #: "Spend this mana only to cast spells" -- Klauth, Unrivaled Ancient.
    #: ``None``, the default, is ordinary mana.
    #:
    #: A *tapped* restricted source never needs this: `costs.mana_sources`
    #: withholds the source itself, so the restricted mana is never made. Mana an
    #: **effect** put in the pool has already been made, and the pool is the only
    #: place left that can remember what it may pay for.
    restriction: ManaRestriction | None = None

    def permits(self, purpose: SpendPurpose | None) -> bool:
        """May this pip pay for what ``purpose`` describes?

        The same question :meth:`ManaSource.permits` asks, asked of a unit of
        mana instead of an untapped ability -- and answered by the same routine,
        so a restriction cannot mean one thing when a land makes it and another
        when a trigger does.
        """
        return _permits(self.restriction, purpose)


@dataclass(frozen=True)
class SpentMana:
    """What one payment actually consumed.

    Every half exists only at the instant `spend` runs: once the pool is
    decremented one blue mana is indistinguishable from another, and the
    permanent that made it is indistinguishable from every other permanent.
    """

    #: Sunburst and converge -- which colours were spent, generic included.
    colors: frozenset[str] = frozenset()
    #: "When **that mana** is spent..." -- which permanents' mana abilities made
    #: the mana this payment consumed. Path of Ancestry, Opal Palace.
    sources: frozenset[int] = frozenset()
    #: What those permanents **were** -- Smaug, Wicked Worm's "if mana from a
    #: Treasure was spent to cast it". Not derivable from `sources`: the
    #: Treasure was sacrificed to make the mana, so the oid resolves to nothing
    #: by the time anything asks. See :class:`ManaOrigin`.
    source_traits: frozenset[ManaOrigin] = frozenset()
    #: Whether **any** pip this payment consumed carried Cavern of Souls' rider.
    #: Any, not all: the printed sentence makes the spell uncounterable if that
    #: mana was spent on it, and says nothing about the rest of its cost.
    uncounterable: bool = False
    #: Every keyword grant carried by a pip this payment consumed -- Arena of
    #: Glory. A tuple rather than a bool because, unlike `uncounterable`, the
    #: rider still has to say *what* it grants and *which* spells get it. In the
    #: order the pips were taken, deduplicated, so two Arenas paying for one
    #: creature grant haste once.
    grants: tuple[ManaKeywordGrant, ...] = ()


class ManaPool:
    """Floating mana.  Emptied at the end of every step and phase.

    ``amounts`` is the count per symbol and ``tags`` is the same thing pip by
    pip: ``tags[i]`` holds one :class:`Pip` for each of ``amounts[i]``, naming
    the permanent whose mana ability made it and any rider that permanent's
    ability attached to it. The two are kept the same length by every method
    here, which is why nothing outside this class may touch ``amounts``
    directly.

    Provenance is a list rather than a set because "that mana" is a *unit* of
    mana and not a colour: a pool holding one black from Path of Ancestry and
    one black from a Swamp has to be able to spend either. It is also why the
    rider lives here rather than on the permanent -- see :class:`Pip`.
    """

    __slots__ = ("amounts", "tags")

    def __init__(
        self,
        amounts: Sequence[int] | None = None,
        tags: Sequence[Sequence[Pip]] | None = None,
    ) -> None:
        self.amounts: list[int] = list(amounts) if amounts else _zeros()
        self.tags: list[list[Pip]] = (
            [list(t) for t in tags]
            if tags is not None
            else [[Pip()] * n for n in self.amounts]
        )

    def add(
        self,
        symbol: str,
        count: int = 1,
        source: int | None = None,
        *,
        uncounterable: bool = False,
        persists_through_turn: int = -1,
        grant: ManaKeywordGrant | None = None,
        source_traits: ManaOrigin | None = None,
        restriction: ManaRestriction | None = None,
    ) -> None:
        index = SYMBOL_INDEX[symbol]
        self.amounts[index] += count
        # Built by keyword: three separate lanes have added a field to `Pip`,
        # and a positional call here would silently pass the wrong one the next
        # time somebody inserts a fourth.
        pip = Pip(
            source=source,
            uncounterable=uncounterable,
            persists_through_turn=persists_through_turn,
            grant=grant,
            source_traits=source_traits,
            restriction=restriction,
        )
        self.tags[index].extend([pip] * count)

    def add_tuple(
        self,
        produced: Sequence[int],
        source: int | None = None,
        *,
        uncounterable: bool = False,
        persists_through_turn: int = -1,
        grant: ManaKeywordGrant | None = None,
        source_traits: ManaOrigin | None = None,
        restriction: ManaRestriction | None = None,
    ) -> None:
        pip = Pip(
            source=source,
            uncounterable=uncounterable,
            persists_through_turn=persists_through_turn,
            grant=grant,
            source_traits=source_traits,
            restriction=restriction,
        )
        for i, v in enumerate(produced):
            self.amounts[i] += v
            self.tags[i].extend([pip] * v)

    def spendable(self, purpose: SpendPurpose | None = None) -> tuple[int, ...]:
        """The pool as ``purpose`` may actually spend it, symbol by symbol.

        :func:`solve_payment` plans against six integers, and an unrestricted
        count would let it plan on mana the payment then cannot take -- a spell
        offered on Klauth's ritual mana and an *ability* offered on it too, which
        is the strictly better card the printed line refuses.

        ``None`` means "no particular spell in mind" and withholds every
        restricted pip, exactly as :meth:`ManaSource.permits` withholds every
        restricted source: an under-count, which is the safe direction for a
        number the AI reads.

        Returns ``amounts`` untouched when nothing in the pool is restricted,
        which is every pool in almost every game.
        """
        counts: list[int] | None = None
        for i, pips in enumerate(self.tags):
            for pip in pips:
                if pip.restriction is not None and not pip.permits(purpose):
                    if counts is None:
                        counts = list(self.amounts)
                    counts[i] -= 1
        return tuple(self.amounts) if counts is None else tuple(counts)

    def total(self) -> int:
        return sum(self.amounts)

    def clear(
        self,
        keep_for_turn: int | None = None,
        keep_symbols: frozenset[str] = frozenset(),
        colorless_instead: bool = False,
    ) -> int:
        """Empty the pool, returning how much mana was lost.

        ``keep_for_turn`` spares the pips that say they survive that turn's step
        and phase boundaries -- Tanuki Transplanter's "until end of turn, you
        don't lose this mana". ``None`` empties everything, which is what the
        end of the turn does and what every caller wanting a clean pool means.

        ``keep_symbols`` spares every pip of those symbols whatever its turn --
        Leyline Tyrant's "you don't lose unspent red mana as steps and phases
        end", a fact about the *player* read off `mana_retention` statics by
        `GameState.empty_all_mana_pools`. It survives the end of the turn too,
        because the end of a turn is only the last step ending (500.4). Empty,
        the default, is every caller that means "lose all unspent mana" (Mana
        Short), which no retention effect stops.

        ``colorless_instead`` is Kruphix's and Omnath, Locus of the Void's "if
        you would lose unspent mana, that mana becomes colorless instead", read
        off `mana_becomes_colorless` statics by the same caller. A replacement
        rather than an exception: every pip the two spares above would not have
        kept stays in the pool as {C}, its own `Pip` moved across unchanged so
        a restriction or rider it carried still applies -- `keep_symbols`
        keeps a pip whole, and so does this. The kept pips keep their colour;
        only what would have been lost changes, and nothing is lost.
        """
        if keep_for_turn is None and not keep_symbols and not colorless_instead:
            lost = sum(self.amounts)
            self.amounts = _zeros()
            self.tags = [[] for _ in range(N_SYMBOLS)]
            return lost
        lost = 0
        recoloured: list[Pip] = []
        for i, pips in enumerate(self.tags):
            if SYMBOLS[i] in keep_symbols:
                continue
            kept: list[Pip] = []
            for pip in pips:
                if (
                    keep_for_turn is not None
                    and pip.persists_through_turn == keep_for_turn
                ):
                    kept.append(pip)
                elif colorless_instead:
                    recoloured.append(pip)
                else:
                    lost += 1
            self.tags[i] = kept
            self.amounts[i] = len(kept)
        if recoloured:
            colorless = SYMBOL_INDEX["C"]
            self.tags[colorless].extend(recoloured)
            self.amounts[colorless] = len(self.tags[colorless])
        return lost

    def copy(self) -> ManaPool:
        return ManaPool(self.amounts, self.tags)

    def _take(
        self, index: int, count: int, purpose: SpendPurpose | None = None
    ) -> list[Pip]:
        """Deduct ``count`` pips of one symbol and report who made them.

        **Newest first.** Which same-coloured pip a payment consumes is the
        player's choice in the printed rules, and this is the one bias that
        matches how the payment actually runs: `pay_mana` taps whatever it needs
        immediately before spending, so the mana it just made is at the end of
        the list. A Path of Ancestry tapped *for* a spell therefore pays for that
        spell, which is the only case the card is ever played for. Recorded as a
        simplification in ``docs/rules-coverage.md``.

        Newest first *among the pips this purpose may spend*: a restricted pip
        this payment is not allowed to touch is skipped over rather than
        deducted, and :meth:`spendable` is what promised there would be enough
        left. The two must agree -- a take that reached past the permission
        would spend Klauth's mana on an ability while the offer said it could
        not be.
        """
        pips = self.tags[index]
        if all(pip.restriction is None for pip in pips):
            self.amounts[index] -= count
            cut = len(pips) - count
            taken = pips[cut:]
            del pips[cut:]
            return taken
        usable = [i for i, pip in enumerate(pips) if pip.permits(purpose)]
        if len(usable) < count:
            raise ValueError("pool cannot cover requirement with this purpose")
        chosen = usable[len(usable) - count :]
        taken = [pips[i] for i in chosen]
        for i in reversed(chosen):
            del pips[i]
        self.amounts[index] -= count
        return taken

    def to_dict(self) -> dict[str, int]:
        return {s: self.amounts[i] for i, s in enumerate(SYMBOLS) if self.amounts[i]}

    def spend(self, req: Requirement, purpose: SpendPurpose | None = None) -> SpentMana:
        """Deduct ``req`` from the pool.  Assumes the pool can cover it.

        ``purpose`` is what the mana is being spent on, and must be the same
        value :meth:`spendable` was asked with when the payment was planned:
        every count below is read off the *permitted* pips, so a restricted pip
        is invisible here exactly as it was to the solver.

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
        # "…if mana from a Treasure was spent to cast it." Collected beside the
        # oids and not instead of them: this is what each source *was*, which is
        # the only half that survives the source being sacrificed to pay.
        made_by_traits: set[ManaOrigin] = set()
        # "…and that spell can't be countered." Any pip carrying the rider makes
        # the whole payment carry it: the printed sentence is about the spell the
        # mana was spent on, and says nothing about the rest of its cost.
        rider = False
        # "…it gains haste until end of turn". A list, not a set: the grant has
        # to survive into `SpentMana` as data rather than a flag, and a stable
        # order keeps one payment's report the same from run to run.
        grants: list[ManaKeywordGrant] = []

        # The pool as this payment may spend it, kept in step with every take
        # below: a restricted pip is not in these counts and is not taken.
        avail = list(self.spendable(purpose))

        def record(taken: list[Pip]) -> None:
            nonlocal rider
            for pip in taken:
                if pip.source is not None:
                    made_by.add(pip.source)
                if pip.source_traits is not None:
                    made_by_traits.add(pip.source_traits)
                rider = rider or pip.uncounterable
                if pip.grant is not None and pip.grant not in grants:
                    grants.append(pip.grant)

        def take(index: int, count: int) -> None:
            avail[index] -= count
            record(self._take(index, count, purpose))

        remaining_generic = req.generic
        for i in range(N_SYMBOLS):
            need = req.colored[i]
            if need:
                if avail[i] < need:
                    raise ValueError("pool cannot cover colored requirement")
                take(i, need)
                if i < len(COLOR_ORDER):
                    spent.add(COLOR_ORDER[i].value)
        # Hybrid pips choose their half here, and must choose it the *same* way
        # `satisfies` decided they could -- so both run one routine. A second,
        # looser rule here could take a symbol the solver was relying on for a
        # coloured pip and strand the payment halfway through.
        if req.hybrid:
            chosen = assign_hybrid(list(avail), req.hybrid, remaining_generic)
            if chosen is None:
                raise ValueError("pool cannot cover hybrid requirement")
            for pip, symbol in zip(req.hybrid, chosen, strict=True):
                if symbol < 0:
                    remaining_generic += pip.generic or 0
                else:
                    take(symbol, 1)
                    if symbol < len(COLOR_ORDER):
                        spent.add(COLOR_ORDER[symbol].value)
        # Pay generic from the most plentiful symbols first so scarce colours are
        # preserved for later spells in the same step.  Deterministic by index.
        while remaining_generic > 0:
            best = max(range(N_SYMBOLS), key=lambda i: (avail[i], -i))
            if avail[best] <= 0:
                raise ValueError("pool cannot cover generic requirement")
            amount = min(avail[best], remaining_generic)
            take(best, amount)
            remaining_generic -= amount
            if best < len(COLOR_ORDER):
                spent.add(COLOR_ORDER[best].value)
        return SpentMana(
            colors=frozenset(spent),
            sources=frozenset(made_by),
            source_traits=frozenset(made_by_traits),
            uncounterable=rider,
            grants=tuple(grants),
        )

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

#: The word a card file uses for an **unrestricted half** of a mana restriction:
#: "Spend this mana only to activate abilities" (Cryptic Trilobite, Omen Hawker),
#: which names no type at all.
#:
#: It compiles to a single empty :class:`RestrictionGroup`, which
#: `satisfied_by` accepts for every purpose of that kind -- nothing is required,
#: so the subset test holds whatever the names are. The *restriction* is then
#: carried entirely by the other half being omitted: with no `cast` groups, this
#: mana can never pay for a spell, which is the whole of what the printed line
#: forbids.
#:
#: A word rather than an accepted empty list, which stays a load error. `[]` is
#: what a mistake looks like, and reading a blank as "everything" is how a
#: strictly better card ships quietly.
WILDCARD = "any"

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
    #: The mana value of the spell being cast (or of the source whose ability is
    #: being activated) -- "…only to cast creature spells **with mana value 4 or
    #: greater**", Helga, Skittish Seer. A number rather than a name, which is
    #: the whole reason it is here: `names` is a flat set and there is nowhere in
    #: it for a comparison to live.
    mana_value: int | None = None
    #: Does that card's **printed** cost carry an ``{X}``? -- "…or creature
    #: spells **with {X} in their mana costs**", the other half of the same line.
    #: Rule 107.3: a Fireball cast for X=0 still has ``{X}`` in its mana cost, so
    #: this is a question about the symbols and not about `mana_value`, which
    #: scores X as 0 and cannot tell Fireball from Shock.
    x_in_mana_cost: bool | None = None


#: The comparison operators a restriction predicate may use, spelled exactly as
#: `effects.selectors._compare` spells them so one printed phrase cannot mean two
#: things depending on whether a filter or a mana restriction asks it. ``>=`` is
#: the default, because "4 or greater" is what the cards print.
RESTRICTION_OPS: dict[str, Any] = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "=": lambda a, b: a == b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}

#: The keys a restriction group entry may carry instead of a type name. Closed,
#: and checked as a set: an unknown key inside the object would otherwise load,
#: be read by nobody, and leave the group permitting everything its names alone
#: permit -- which is the strictly-better card this whole grammar exists to
#: refuse.
RESTRICTION_PREDICATES = frozenset({"mana_value", "x_in_mana_cost"})


@dataclass(frozen=True)
class RestrictionGroup:
    """One all-of inside a restriction: names that must be there, and must not.

    ``required`` alone was the whole language until "spend this mana only to
    cast a **non**creature spell" (The Emperor of Palamecia). That line has no
    positive spelling: `"noncreature"` is not a type, so as a literal it matches
    nothing ever and freezes the mana permanently unspendable, while enumerating
    the noncreature types over-permits every artifact creature and enchantment
    creature spell -- `permits` would see "artifact" among the names and never
    learn that "creature" is there too.

    So the group asks both questions. It is the same one-word idea trigger
    filters have had all along as `not_types`, arriving in the one place that
    lacked it.

    The **predicates** are the third question, and they arrived with Helga,
    Skittish Seer: "spend this mana only to cast creature spells with mana value
    4 or greater or creature spells with {X} in their mana costs". Neither
    clause has a name -- `"mana-value-4"` is not a type, so as a literal it is
    the permanently-unspendable mana `_restriction_name` warns about, and
    dropping the clause to a bare ``["creature"]`` funds every creature spell
    ever printed. So a group carries a comparison and a symbol question beside
    its names, all of them required at once.
    """

    required: frozenset[str] = frozenset()
    forbidden: frozenset[str] = frozenset()
    #: ``(op, n)`` -- "with mana value 4 or greater" is ``(">=", 4)``. A
    #: normalised pair rather than the card's comparison mapping, so the group
    #: stays hashable: a `Pip` is a NamedTuple and carries one of these.
    mana_value: tuple[str, int] | None = None
    #: "…with {X} in their mana costs", true or false. ``None`` is a group that
    #: does not ask.
    x_in_mana_cost: bool | None = None

    def names(self) -> frozenset[str]:
        """Every name mentioned, either way round -- for `dynamic`'s scan."""
        return self.required | self.forbidden

    def satisfied_by(self, purpose: SpendPurpose) -> bool:
        """Does this one all-of hold for what is being paid for?

        The whole purpose rather than its `names`, because a predicate asks
        about something no set of names can hold. An unanswerable predicate --
        a purpose carrying no mana value at all -- fails rather than passes,
        which is `_permits`' direction throughout: under-permit rather than
        hand out a strictly better card.
        """
        if not (self.required <= purpose.names) or (self.forbidden & purpose.names):
            return False
        if self.mana_value is not None:
            op, wanted = self.mana_value
            if purpose.mana_value is None or not RESTRICTION_OPS[op](purpose.mana_value, wanted):
                return False
        return not (
            self.x_in_mana_cost is not None and purpose.x_in_mana_cost is not self.x_in_mana_cost
        )


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

    cast: tuple[RestrictionGroup, ...] = ()
    activate: tuple[RestrictionGroup, ...] = ()
    #: Does any group name :data:`CHOSEN_TYPE`?  Derived here rather than stored
    #: by the loader so it cannot drift from the groups it describes, and
    #: computed once at load so `costs.resolve_mana_restriction` can return an
    #: entirely static restriction untouched instead of rebuilding it per
    #: battlefield walk.
    dynamic: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        # A bare frozenset is accepted as a group and means what it always
        # meant: every name required, none forbidden. Kept because that *is*
        # the shorthand -- the negation is the new half, not the old one -- and
        # because coercing here is one line against rewriting every construction
        # of a restriction that predates it.
        for slot in ("cast", "activate"):
            groups = getattr(self, slot)
            if any(not isinstance(g, RestrictionGroup) for g in groups):
                object.__setattr__(
                    self,
                    slot,
                    tuple(
                        g if isinstance(g, RestrictionGroup) else RestrictionGroup(frozenset(g))
                        for g in groups
                    ),
                )
        object.__setattr__(
            self, "dynamic", any(CHOSEN_TYPE in g.names() for g in self.cast + self.activate)
        )

    def groups(self, kind: str) -> tuple[RestrictionGroup, ...]:
        return self.activate if kind == ACTIVATE else self.cast


def _permits(restriction: ManaRestriction | None, purpose: SpendPurpose | None) -> bool:
    """May mana carrying ``restriction`` pay for what ``purpose`` describes?

    The one answer, asked by both producers of restricted mana -- an untapped
    ability the solver may tap (:meth:`ManaSource.permits`) and a pip an effect
    already put in the pool (:meth:`Pip.permits`). Written once so the same
    printed sentence cannot mean two different things depending on which of them
    made the mana.

    Both halves of the purpose are asked: the restriction's groups **for that
    kind** (casting a spell, or activating an ability), and then whether any one
    group's names are all present.

    ``None`` means "no particular spell in mind", and withholds every restricted
    source -- an under-count rather than an over-count, which is the safe
    direction for a number the AI reads.
    """
    if restriction is None:
        return True
    if purpose is None:
        return False
    return any(group.satisfied_by(purpose) for group in restriction.groups(purpose.kind))


def compile_restriction(spec: Any, where: str) -> ManaRestriction:
    """ "Spend this mana only to cast …" compiled to a :class:`ManaRestriction`.

    Beside the class it builds rather than in the card loader, for
    :func:`parse_mana_production`'s reason: both producers of restricted mana
    need it, and only one of them is a loader. A mana **ability**'s restriction
    is compiled once at load; an `add_mana` effect's is compiled as it resolves,
    because an effect's spec stays JSON all the way to the stack.

    A bare string or list is the **cast** half alone, which is what every card
    printed before Secluded Courtyard says and why the old spelling still means
    exactly what it meant:

    - ``"creature"`` -- one name, Ancient Ziggurat.
    - ``["Vampire", "Cleric", "Demon"]`` -- the printed "and/or", which is an
      any-of: one matching name is enough (Master of Dark Rites).

    An **object** names the halves separately, because the printed sentence
    does: "…only to cast a creature spell of the chosen type **or activate an
    ability of** a creature source of the chosen type" gives them different
    subjects, and a card that says nothing about activating abilities must not
    permit it.

    ```jsonc
    "mana_restriction": {
      "cast":     [["creature", {"chosen_type_of": "self"}]],
      "activate": [["creature", {"chosen_type_of": "self"}]]
    }
    ```

    A nested list is an **all-of**, and this card needs it: "a creature spell
    **of** the chosen type" is a conjunction, and flattening it into the any-of
    above would offer the mana for every creature ever printed -- a strictly
    better card than the printed one.

    An entry may also be a **predicate** rather than a name, which is what
    Helga, Skittish Seer needs -- "…only to cast creature spells with mana value
    4 or greater **or** creature spells with {X} in their mana costs" is an
    any-of of two all-ofs, and neither all-of is expressible in names:

    ```jsonc
    "mana_restriction": {
      "cast": [
        ["creature", {"mana_value": {"op": ">=", "value": 4}}],
        ["creature", {"x_in_mana_cost": true}]
      ]
    }
    ```

    See :func:`_restriction_predicate`. Dropping either predicate leaves
    ``["creature"]``, which funds every creature spell ever printed.

    ``{"chosen_type_of": "self"}`` is the one entry that is not a literal name.
    It compiles to :data:`CHOSEN_TYPE` and is substituted per permanent by
    `costs.resolve_mana_restriction`, because the type does not exist until the
    permanent is on the battlefield. Spelled the same way `subtypes` filters
    already spell it (Vanquisher's Banner, Door of Destinies) rather than as a
    new key meaning the same thing.
    """
    if isinstance(spec, Mapping):
        unknown = sorted(set(spec) - {"cast", "activate"})
        if unknown:
            raise DslError(
                f"{where}: 'mana_restriction' names {unknown}; mana is only ever spent "
                f"to 'cast' a spell or 'activate' an ability"
            )
        restriction = ManaRestriction(
            cast=_restriction_groups(spec.get("cast"), f"{where}.cast"),
            activate=_restriction_groups(spec.get("activate"), f"{where}.activate"),
        )
        if not restriction.cast and not restriction.activate:
            raise DslError(
                f"{where}: 'mana_restriction' permits nothing at all; omit it for ordinary mana"
            )
        if spec.get("cast") == WILDCARD and spec.get("activate") == WILDCARD:
            # Both halves unrestricted is ordinary mana wearing a restriction,
            # and the one shape that would make `"any"` a way to say nothing.
            raise DslError(
                f"{where}: 'mana_restriction' of {WILDCARD!r} on both halves restricts "
                f"nothing; omit it for ordinary mana"
            )
        return restriction
    if spec == WILDCARD:
        # A bare restriction is the *cast* half, so a bare wildcard is mana that
        # pays for every spell ever printed and merely declines to activate an
        # ability. No card prints that, and the shape is one keystroke from the
        # line that is meant -- "spend this mana only to activate abilities" --
        # which it would silently invert into a strictly better card. The
        # wildcard is only ever one named half of the mapping.
        raise DslError(
            f"{where}: a bare {WILDCARD!r} 'mana_restriction' restricts nothing worth "
            f"saying; name the half it belongs to, as {{{WILDCARD!r}: ...}} under "
            f"'cast' or 'activate'"
        )
    return ManaRestriction(cast=_restriction_groups(spec, where))


def _restriction_groups(spec: Any, where: str) -> tuple[RestrictionGroup, ...]:
    """One half of a restriction: the groups, any of which may be satisfied.

    ``None`` is an omitted half and means "never", which is the whole of how a
    card that says only "to cast" refuses to fund an activation.

    ``"any"`` is the other end of the same axis: one empty group, which
    `RestrictionGroup.satisfied_by` satisfies for every purpose of that kind
    (``required <= names`` with nothing required). "Spend this mana only to
    **activate abilities**" (Cryptic Trilobite, Omen Hawker) names no type at
    all, and every group this language can otherwise hold is a set of literal
    type or subtype names -- there is no name every source has.

    The restriction is real because it lives in the *other* half: with `cast`
    omitted, this mana can never pay for a spell. That is why the wildcard is
    not "no restriction", and why both halves being ``"any"`` is refused above.

    Spelled as an explicit word rather than accepted as an empty list, which
    stays an error: ``[]`` is what a mistake looks like, and the difference
    between "I meant everything" and "I left this blank" is a strictly better
    card.
    """
    if spec is None:
        return ()
    if spec == WILDCARD:
        return (RestrictionGroup(),)
    groups = [spec] if isinstance(spec, str) else list(spec)
    if not groups:
        raise DslError(f"{where}: 'mana_restriction' is empty; omit it for ordinary mana")
    out: list[RestrictionGroup] = []
    for group in groups:
        entries = [group] if isinstance(group, (str, Mapping)) else list(group)
        if not entries:
            raise DslError(
                f"{where}: an empty group in 'mana_restriction' restricts nothing; "
                f"omit it for ordinary mana"
            )
        required: set[str] = set()
        forbidden: set[str] = set()
        predicates: dict[str, Any] = {}
        for entry in entries:
            if isinstance(entry, Mapping) and "not" in entry:
                if set(entry) != {"not"}:
                    raise DslError(
                        f"{where}: a negated mana restriction takes only 'not', "
                        f"not {dict(entry)!r}"
                    )
                forbidden.add(_restriction_name(entry["not"], where, negated=True))
            elif isinstance(entry, Mapping) and set(entry) & RESTRICTION_PREDICATES:
                key, value = _restriction_predicate(entry, where)
                if key in predicates:
                    # Two comparisons on one characteristic inside one all-of.
                    # Only one of them would be stored, so the other would load
                    # clean and be dropped -- and a dropped restriction is the
                    # better-than-printed card this grammar exists to refuse.
                    raise DslError(
                        f"{where}: {key!r} is given twice in one 'mana_restriction' "
                        f"group; a group asks each question once"
                    )
                predicates[key] = value
            else:
                required.add(_restriction_name(entry, where))
        if not required and not forbidden and not predicates:
            raise DslError(
                f"{where}: an empty group in 'mana_restriction' restricts nothing; "
                f"omit it for ordinary mana"
            )
        # A name on both sides is a group nothing can ever satisfy -- the same
        # permanently-unspendable mana a typo makes, and worth the same refusal.
        if overlap := required & forbidden:
            raise DslError(
                f"{where}: {sorted(overlap)!r} is both required and forbidden in one "
                f"'mana_restriction' group, which nothing can satisfy"
            )
        out.append(
            RestrictionGroup(
                frozenset(required),
                frozenset(forbidden),
                mana_value=predicates.get("mana_value"),
                x_in_mana_cost=predicates.get("x_in_mana_cost"),
            )
        )
    return tuple(out)


def _restriction_predicate(entry: Mapping[str, Any], where: str) -> tuple[str, Any]:
    """One non-name entry in a group: a comparison, or the ``{X}`` question.

    "Spend this mana only to cast creature spells **with mana value 4 or
    greater** or creature spells **with {X} in their mana costs**" -- Helga,
    Skittish Seer. Two clauses that name no type at all, sitting in a grammar
    whose every other entry is a type name.

    Spelled with the keys the selector language already uses for the same two
    questions (`mana_value`, `x_in_mana_cost`), and compiled to the same shapes,
    so "mana value 4 or greater" cannot mean one thing to a trigger filter and
    another to a mana restriction.

    One key per entry. Written as ``{"mana_value": …, "x_in_mana_cost": …}`` the
    two would be an all-of, which is exactly what a group *already* is -- and
    having two spellings for one meaning is how the second one ends up untested.
    """
    if len(entry) != 1:
        raise DslError(
            f"{where}: a mana restriction predicate asks one question; write "
            f"{sorted(entry)} as separate entries in the same group"
        )
    key, spec = next(iter(entry.items()))
    if key == "x_in_mana_cost":
        # `_compare`'s trap, in the one place `_compare` cannot catch it: a
        # `{"op": ">=", "value": 1}` here is a truthy mapping and would read as
        # `true`, quietly turning "with {X} in its cost" into "with any cost".
        # Refused for the reason `selectors` refuses the same spelling.
        if not isinstance(spec, bool):
            raise DslError(
                f"{where}.x_in_mana_cost: true or false -- whether the printed cost "
                f"has an {{X}} symbol at all; use 'mana_value' to compare numbers"
            )
        return key, spec
    op, wanted = ">=", spec
    if isinstance(spec, Mapping):
        unknown = sorted(set(spec) - {"op", "value"})
        if unknown:
            raise DslError(f"{where}.mana_value: unknown keys {unknown}; give 'op' and 'value'")
        op = str(spec.get("op", ">="))
        wanted = spec.get("value", 0)
    if op not in RESTRICTION_OPS:
        raise DslError(
            f"{where}.mana_value: unknown comparison operator {op!r} "
            f"(one of {sorted(RESTRICTION_OPS)})"
        )
    # `{"const": 4}` is how the authoring pipeline normalises a literal, and a
    # bare `4` is how a hand-written card says it. Both are accepted and both
    # collapse to the same integer; anything *else* is a value expression, and a
    # restriction is compiled once at load with no board to read -- so it would
    # have to be evaluated at spend time, where there is no `EffectContext`.
    # Refused here rather than silently read as 0, which would permit every
    # spell ever printed.
    if isinstance(wanted, Mapping) and set(wanted) == {"const"}:
        wanted = wanted["const"]
    if isinstance(wanted, bool) or not isinstance(wanted, int):
        raise DslError(
            f"{where}.mana_value: a literal number, got {wanted!r} -- a mana "
            f"restriction is compiled at load time and has no board to read"
        )
    return key, (op, int(wanted))


def _restriction_name(entry: Any, where: str, *, negated: bool = False) -> str:
    """One name inside a restriction group: a literal, or the chosen type.

    ``negated`` is the `{"not": …}` half, and it accepts literals only. No card
    prints "spend this only to cast a spell that is *not* the chosen type", and
    the sentinel would have to survive `costs._resolve_groups` for it to mean
    anything -- so it is refused here rather than accepted and half-honoured.
    """
    if negated and isinstance(entry, Mapping):
        raise DslError(
            f"{where}: a negated mana restriction takes a literal type or "
            f"subtype, not {dict(entry)!r}"
        )
    if isinstance(entry, Mapping):
        # Exactly the one dynamic leaf, and validated as such: a near-miss
        # spelling that fell through would freeze into a literal name no card
        # has, producing mana that can never be spent.
        if set(entry) != {"chosen_type_of"} or entry["chosen_type_of"] != "self":
            raise DslError(
                f"{where}: the only dynamic mana restriction is "
                f'{{"chosen_type_of": "self"}}, not {dict(entry)!r} '
                f"(the predicates are {sorted(RESTRICTION_PREDICATES)})"
            )
        return CHOSEN_TYPE
    # A predicate written as a *name* -- "mana value", "mana-value", "x in mana
    # cost". It is the natural typo now that both are real entries, and it is
    # the failure this whole function's shape check exists for: a word nothing
    # ever printed freezes the mana permanently unspendable, silently, which
    # reads at the table as a source that taps for nothing.
    if (
        isinstance(entry, str)
        and entry.replace("-", "_").replace(" ", "_").lower() in RESTRICTION_PREDICATES
    ):
        raise DslError(
            f"{where}: {entry!r} is a predicate, not a type -- write it as an "
            f"object in the group, e.g. {{\"mana_value\": {{\"op\": \">=\", "
            f'"value": 4}}}}'
        )
    # A card type, a supertype, or a subtype. Subtypes are open-ended in Magic
    # and there is no closed list to check one against, so the guard is the
    # weaker "looks like a word": a typo here produces mana that can never be
    # spent, which is a strictly worse card than the printed one -- the safe
    # direction, but a silent one, so it is worth the shape check.
    #
    # "legendary" was exactly that failure until `costs.spell_purpose` learned to
    # read supertypes: it passed this check, matched nothing on any card in the
    # game, and read on the board as a land that taps for nothing.
    if (
        not isinstance(entry, str)
        or not entry
        or not entry.replace("-", "").replace(" ", "").isalpha()
    ):
        raise DslError(
            f"{where}: unparsable mana restriction {entry!r} "
            f"(a card type, supertype or subtype, lowercased -- a comparison is "
            f"an object, one of {sorted(RESTRICTION_PREDICATES)})"
        )
    return entry.lower()


@dataclass(frozen=True)
class ManaSource:
    """One mana ability of one untapped permanent, flattened into its yields.

    ``options`` holds every 6-tuple the ability could produce (a dual land that
    reads "Add {G} or {U}" contributes two options; one that reads "Add {G}{U}"
    contributes a single option producing two mana).

    One *ability*, not one permanent.  A Talisman or a painland prints two tap
    abilities ("{T}: Add {C}" and "{T}: Add {B} or {R}") and so contributes two
    sources sharing an ``oid``.  The permanent can only be tapped once, so the
    solver treats every source with the same ``oid`` as mutually exclusive --
    the alternative was a Talisman that paid ``{1}{B}`` on its own.
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
        """May this source pay for what ``purpose`` describes?  See :func:`_permits`."""
        return _permits(self.restriction, purpose)

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


def max_affordable_times(
    cost: ManaCost,
    pool: ManaPool | Sequence[int],
    sources: Sequence[ManaSource],
    cap: int = 100,
) -> int:
    """Largest ``N`` for which ``cost`` charged ``N`` times over is payable.

    "You may pay **any amount of {R}**" (Leyline Tyrant) is a player-chosen
    count of one fixed symbol, which `max_affordable_x` cannot price: ``with_x``
    adds X as *generic*, so a red-only demand would be met by any mana. This
    probes `ManaCost.scaled` instead, so {R} at three is ``{R}{R}{R}`` and only
    red pays it. 0 when not even one is affordable.

    ``cap`` is the engine's guard against a pathological board, not a rule any
    card makes; the walk stops at the first unaffordable ``N``, so on an
    ordinary board it costs one solve per point actually payable.
    """
    best = 0
    for n in range(1, cap + 1):
        if solve_payment(cost.scaled(n).with_x(0), pool, sources) is None:
            break
        best = n
    return best


# --------------------------------------------------------------------------
# solver internals
# --------------------------------------------------------------------------


def _flexibility(source: ManaSource) -> int:
    return len(source.producible())


def _colour_abundance(sources: Iterable[ManaSource]) -> list[int]:
    """How many *permanents* among these sources can produce each symbol.

    Counted per permanent rather than per source, so a Talisman's two abilities
    do not make its colours look twice as plentiful as they are.
    """
    by_permanent: dict[int, set[int]] = {}
    for source in sources:
        by_permanent.setdefault(source.oid, set()).update(source.producible())
    counts = _zeros()
    for symbols in by_permanent.values():
        for i in symbols:
            counts[i] += 1
    return counts


def _greedy_solve(
    base: tuple[int, ...], req: Requirement, sources: Sequence[ManaSource]
) -> Payment | None:
    produced = list(base)
    # Permanents already tapped in this plan.  Keyed by oid, not by position in
    # ``sources``: a permanent with two tap abilities appears twice, and using
    # both would tap it twice.
    used: set[int] = set()
    taps: list[tuple[int, int, int]] = []

    # Phase A -- cover the coloured (and {C}) pips, most-constrained colour first.
    while True:
        deficits = [max(0, req.colored[i] - produced[i]) for i in range(N_SYMBOLS)]
        if not any(deficits):
            break
        candidates: dict[int, list[ManaSource]] = {}
        for i in range(N_SYMBOLS):
            if deficits[i] == 0:
                continue
            candidates[i] = [s for s in sources if s.oid not in used and i in s.producible()]
            if not candidates[i]:
                return None
        colour = min(candidates, key=lambda i: (len(candidates[i]), i))
        pool_of = candidates[colour]
        pool_of.sort(key=lambda s: (_flexibility(s), 0 if s.is_land else 1, s.sort_key, s.oid))
        chosen = pool_of[0]
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
        used.add(chosen.oid)
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
        remaining = [s for s in sources if s.oid not in used and s.max_output() > 0]
        if not remaining:
            return None
        remaining.sort(
            key=lambda s: (
                -s.max_output(),
                -min((abundance[i] for i in s.producible()), default=0),
                0 if s.is_land else 1,
                s.sort_key,
            )
        )
        source = remaining[0]
        option_index, option = max(
            enumerate(source.options), key=lambda jo: (sum(jo[1]), tuple(-v for v in jo[1]), -jo[0])
        )
        for i in range(N_SYMBOLS):
            produced[i] += option[i]
        used.add(source.oid)
        taps.append((source.oid, source.ability_index, option_index))

    return Payment(taps=taps, produced=tuple(produced))


def _search_solve(
    base: tuple[int, ...], req: Requirement, sources: Sequence[ManaSource]
) -> Payment | None:
    """Bounded depth-first fallback over "skip this source / use option k"."""
    n = len(sources)
    # Upper bound on what sources[i:] can still add.  Each *permanent* is
    # counted once, for its best ability from here on: two abilities of one
    # Talisman cannot both be tapped, and summing them would let the search
    # chase a payment that no board can make.  Admissible whichever of a
    # permanent's abilities an earlier branch took, because it only ever
    # over-estimates.
    suffix_max = [0] * (n + 1)
    best_after: dict[int, int] = {}
    for i in range(n - 1, -1, -1):
        out = sources[i].max_output()
        prev = best_after.get(sources[i].oid, 0)
        suffix_max[i] = suffix_max[i + 1] + max(0, out - prev)
        best_after[sources[i].oid] = max(prev, out)

    nodes = 0
    needed_total = req.total

    def recurse(
        idx: int,
        produced: tuple[int, ...],
        taps: list[tuple[int, int, int]],
        tapped: set[int],
    ):
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
        # Try using this source (each option, richest first) before skipping it
        # -- unless its permanent is already tapped by an earlier choice.
        if source.oid not in tapped:
            options = sorted(enumerate(source.options), key=lambda jo: (-sum(jo[1]), jo[1]))
            tapped.add(source.oid)
            for option_index, option in options:
                nxt = tuple(produced[i] + option[i] for i in range(N_SYMBOLS))
                taps.append((source.oid, source.ability_index, option_index))
                found = recurse(idx + 1, nxt, taps, tapped)
                taps.pop()
                if found is not None:
                    return found
            tapped.discard(source.oid)
        return recurse(idx + 1, produced, taps, tapped)

    return recurse(0, base, [], set())


def format_symbols(amounts: Iterable[int]) -> str:
    """Render a 6-tuple as ``{G}{G}{U}`` for logs and the UI."""
    parts: list[str] = []
    for i, v in enumerate(amounts):
        parts.extend("{" + SYMBOLS[i] + "}" for _ in range(v))
    return "".join(parts) or "{0}"
