"""What a hand-written card *claims* to do, against what it actually prints.

`data/cards/auto/` is only in the pool because it cleared six gates. `data/cards/`
never cleared any of them -- those cards predate the pipeline, and two of the
gates have simply never run over them:

* **gate 3 (residual)** asks whether every printed sentence is accounted for.
* **gate 5 (behaviour)** asks whether the card demonstrably does what it says.

Neither could run, for one reason: on a hand-written card ``oracle_text`` is a
human paraphrase, written *after* whatever was skipped, so the card's own record
of its text already agrees with the shortcut. Krosan Tusker's oracle text is "A
large boar." -- and against that text, a vanilla 6/5 is a faithful implementation.
There is nothing for a gate to catch, because the question was begged.

So the authority here is never the card file. It is the catalog row in
``data/catalog/cards.sqlite``, which is Scryfall's printed text and knows nothing
about what the engine can express. The difference between the two is the deficit.

This module only *measures*. It writes nothing and repairs nothing: the repair is
``/author-cards``, which routes each deficit back through the same six gates the
authored tier goes through, and files a gap record for anything the DSL cannot
say rather than approximating it a second time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..images import CardIndex, IndexEntry
from ..loader import KNOWN_KEYWORDS
from ..proxy import _strip_reminders
from .verify import EXPECTATION_KEYS, claimed_lines, fold_self_reference

if TYPE_CHECKING:
    from automtg.engine.carddef import CardDef

    from ..registry import CardRegistry

#: Ways a hand-written card can fall short of its printing, worst first.
#:
#: ``residual``           a printed line nothing on the card implements
#: ``spell_text_lost``    an instant or sorcery printing a mechanic it does not
#:                        have -- see :func:`unimplemented_mechanics`
#: ``text_drift``         a printed line an ability plainly implements under a
#:                        terser name -- bookkeeping, not missing rules
#: ``paraphrased_oracle`` the card's own ``oracle_text`` is not what it prints
#: ``unasserted``         no behaviour expectation, so gate 5 cannot run
#: ``no_catalog_row``     nothing to check the card against
KINDS = (
    "residual",
    "spell_text_lost",
    "text_drift",
    "paraphrased_oracle",
    "unasserted",
    "no_catalog_row",
)

@dataclass(frozen=True)
class Deficit:
    """One thing wrong with one hand-written card."""

    card_id: str
    name: str
    kind: str
    detail: str

    def __str__(self) -> str:
        return f"{self.card_id}: {self.kind} -- {self.detail}"


# ----------------------------------------------------------------------
# normalization
# ----------------------------------------------------------------------

_WHITESPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^a-z0-9{} ]+")


def canonical(text: str, name: str = "") -> str:
    """Text reduced to what a comparison should actually care about.

    Reminder text goes (it is parenthetical by definition and carries no rules
    the card does not state elsewhere), self-reference folds, case and
    punctuation go.  Mana symbols survive, because "{2}{G}" is the difference
    between cycling and no cycling.
    """
    text = _strip_reminders(text)
    text = fold_self_reference(text, name)
    text = _PUNCTUATION.sub(" ", text.lower())
    return _WHITESPACE.sub(" ", text).strip()


# ----------------------------------------------------------------------
# the audit
# ----------------------------------------------------------------------


def printed_text(catalog: IndexEntry, name: str) -> str:
    """The catalog's oracle text, self-reference folded to the pool's house style.

    Written back onto the card by ``audit_cards.py --fix-oracle``, so it has to
    read like the rest of ``data/cards/`` rather than like a Scryfall dump.
    """
    text = catalog.oracle_text or ""
    if name:
        for form in sorted({f"{name}'s", name}, key=len, reverse=True):
            replacement = "this card's" if form.endswith("'s") else "this card"
            text = re.sub(re.escape(form), replacement, text)
    return text


def _overlap(line: str, claim: str, name: str) -> float:
    """How much of a printed line an ability's text accounts for, 0..1.

    Token containment rather than similarity, because the two are not the same
    length by nature: an ability's ``text`` is one clause of a sentence that also
    carries flavour and templating.  What matters is whether the claim covers the
    line's content, not whether they read alike.
    """
    wanted = set(canonical(fold_self_reference(line, name)).split())
    if not wanted:
        return 1.0
    got = set(canonical(fold_self_reference(claim, name)).split())
    return len(wanted & got) / len(wanted)


#: Below this, no ability on the card is plausibly about the line at all -- it is
#: simply not implemented.  Above it, some ability is clearly reaching for the
#: line and merely describes it in the pool's terser house style ("When this
#: enters, search for a basic land tapped." for a line printed "When Farhaven Elf
#: enters, you may search your library for a basic land card, put it onto the
#: battlefield tapped, then shuffle.").
DRIFT_FLOOR = 0.35

#: Where a match stops being a judgement call and becomes mechanical, which is
#: the only place ``--fix-text`` is allowed to rewrite anything.
REWRITE_FLOOR = 0.70


def unclaimed_lines(card: CardDef, printed: str) -> list[str]:
    """Printed lines nothing on the card accounts for, raw and in order.

    The complement of :func:`verify.claimed_lines`, so keyword lines, replacement
    effects and an instant's ``spell_effects`` are already accounted for and
    never show up here.  Matching against *all* printed lines instead was
    actively harmful: Stromkirk Captain's "Other Vampires you control have first
    strike." scores a perfect 1.00 against the bare printed line "First strike",
    which the keyword lift had already consumed -- so the ability would have been
    re-pointed at a line it does not implement, and the line it *does* implement
    would have lost its only claimant.
    """
    claimed = claimed_lines(card, printed)
    return [line for line in printed.split("\n") if line.strip() and line not in claimed]


def unaccounted_abilities(card: CardDef, printed: str) -> list[int]:
    """Indices of abilities whose ``text`` claims no printed line."""
    claimed = claimed_lines(card, printed)
    out: list[int] = []
    for index, ability in enumerate(card.abilities):
        text = (ability.text or "").strip()
        if not text:
            continue
        if not any(_covered_by(text, line, card.name) for line in claimed):
            out.append(index)
    return out


def _covered_by(text: str, line: str, name: str) -> bool:
    stripped = line.strip().rstrip(".")
    claim = text.rstrip(".")
    if claim == stripped or claim in line or stripped in claim:
        return True
    folded, folded_line = fold_self_reference(claim, name), fold_self_reference(stripped, name)
    return folded == folded_line or folded in folded_line or folded_line in folded


def forced_matches(card: CardDef, printed: str) -> dict[int, str]:
    """The assignments arithmetic makes for us.

    One ability with nothing to claim and one printed line with nothing claiming
    it can only be each other. No score is consulted, because none is needed --
    and no score would be trustworthy here anyway: Wood Elves records "When this
    enters, search for a Forest and put it onto the battlefield." against a line
    printed "When this creature enters, search your library for a Forest card,
    put that card onto the battlefield, then shuffle.", which is plainly the same
    ability and shares under half its words.

    Generalised to n abilities and n lines, which is the same deduction rather
    than a weaker one: the assignment is taken only when every spare ability
    prefers a *different* line, so there is exactly one way to pair them up.
    Avenger of Zendikar needs this -- an ETB and a landfall trigger, two printed
    lines, and each ability unambiguously about one of them.

    **What this cannot see, and it matters.** Pairing an ability with a line says
    they are about the same thing, not that the ability does all of it. Kalastria
    Highborn's trigger drains for 2 and the printed line drains for 2 *after an
    optional {B}*; the two pair correctly, the residual goes quiet, and the
    missing cost is still missing. Re-pointing does not make that card right --
    it makes the card file finally *say* what the card should do, which is the
    prerequisite for noticing. Catching the rest is gate 5's job, and a card
    carrying only a zone assertion is reported ``unasserted`` for exactly this
    reason.
    """
    lines = unclaimed_lines(card, printed)
    spare = unaccounted_abilities(card, printed)
    if not lines or len(lines) != len(spare):
        return {}

    best: dict[int, str] = {}
    for index in spare:
        claim = (card.abilities[index].text or "").strip()
        score, line = max((_overlap(line, claim, card.name), line) for line in lines)
        # Arity says these two are left over together; it does not say they are
        # about each other. An ability sharing almost nothing with the only line
        # going spare is a card where something else is wrong, and pairing them
        # would bury that under a residual that has stopped complaining.
        if score < DRIFT_FLOOR:
            return {}
        best[index] = line
    # A perfect matching or nothing: if two spare abilities want the same line,
    # the card splits a sentence across abilities or one of them is wrong, and
    # either way this is not the place to decide.
    return best if len(set(best.values())) == len(best) else {}


def match_abilities(card: CardDef, printed: str, *, floor: float) -> dict[int, str]:
    """``{ability index: the unclaimed printed line it is about}``.

    The pool's ability ``text`` fields are paraphrases -- "When this enters, draw
    a card" for a line printed "When Elvish Visionary enters, draw a card". The
    residual gate reads ``text`` as *the author's claim about which sentence they
    implemented*, so a paraphrase is a bookkeeping error rather than a missing
    ability.

    Only unambiguous assignments are returned; anything else stays in the report,
    where a person decides.
    """
    lines = unclaimed_lines(card, printed)
    if not lines:
        return {}
    out: dict[int, str] = {}
    for index, ability in enumerate(card.abilities):
        claim = (ability.text or "").strip()
        if not claim:
            continue
        best, line = max((_overlap(line, claim, card.name), line) for line in lines)
        if best >= floor:
            out[index] = line

    # One printed line cannot be implemented by two abilities. If two claim it,
    # neither is confident -- Stromkirk Captain really does split "get +1/+1 and
    # have first strike" across two statics, and neither ``text`` is the line.
    #
    # This is the *only* ambiguity check. An earlier version also required the
    # winning line to beat the same ability's second-best line by a margin, which
    # looked prudent and was not: Solemn Simulacrum prints "When this creature
    # enters..." and "When this creature dies...", so its two abilities each
    # score respectably against both lines, and every card whose triggers share a
    # templating prefix was reported as unimplemented.
    taken: dict[str, list[int]] = {}
    for index, line in out.items():
        taken.setdefault(line, []).append(index)
    return {i: line for i, line in out.items() if len(taken[line]) == 1}


#: A printed line that *declares a mechanic* rather than describing an effect:
#: a capitalised term, then a cost, an em-dash, or nothing. "Flashback—{1}{U},
#: Pay 3 life.", "Cycling {2}{G}", "Embalm {5}{W}", "Spell mastery — If two or
#: more instant...", "Evolve".
#:
#: Deliberately narrow. "Draw two cards.", "Create X 1/1 white Warrior creature
#: tokens." and "Search your library for up to two basic land cards, ..." all
#: begin with a capitalised verb and none of them match, because a mechanic
#: declaration is followed by its cost or its separator and a sentence is not.
#: The dashes are the characters actually printed on cards -- Scryfall uses an
#: em-dash, older data an en-dash -- so matching them is the entire job and
#: RUF001's "did you mean a hyphen" does not apply.  Same call as ``proxy.py``.
_MECHANIC_LINE = re.compile(r"^([A-Z][a-z]+(?: [a-z]+)?)\s*(?:\{|—|–|- |$)")  # noqa: RUF001


def unimplemented_mechanics(card: CardDef, printed: str) -> list[str]:
    """Printed lines naming a mechanic the card does not have, for a spell.

    The residual gate is *structurally blind* to instants and sorceries.
    ``verify.claimed_lines`` consumes every printed line the moment a card has
    ``spell_effects``, reasoning that a spell has one place for its text to go,
    that per-line attribution would invent a distinction the format does not
    have, and that under-implementation is caught by gate 5 instead.

    That last part holds only where gate 5 runs, and in the hand-written pool it
    mostly does not -- 148 of 192 cards have no expectation at all. So a Deep
    Analysis could ship with its flashback line doing nothing and no gate would
    object. (It no longer does: flashback shipped, and `declared` below has to
    list every card-level alternative cast or this reports the implemented ones
    as missing -- which is exactly what it did to Deep Analysis and Increasing
    Devotion between flashback landing and this line being added.)

    This does not try to re-derive per-line attribution. It asks the one question
    that can be answered from the text alone: does a printed line *announce a
    mechanic*, and does the card have that mechanic? Everything else about a
    spell -- Anticipate implemented as Preordain, Secure the Wastes making
    Soldiers where the card says Warriors -- is a semantic error that only the
    board can witness, and belongs to gate 5 and an expectation.
    """
    if not card.spell_effects:
        return []
    declared = set()
    if card.kicker is not None:
        declared.add("kicker")
    if card.retrace:
        declared.add("retrace")
    if card.suspend is not None:
        declared.add("suspend")
    if card.cost_reduction is not None:
        declared.add("affinity")
    if card.flashback is not None:
        declared.add("flashback")

    out: list[str] = []
    for line in printed.split("\n"):
        bare = _strip_reminders(line).strip()
        match = _MECHANIC_LINE.match(bare)
        if not match:
            continue
        term = match.group(1).casefold().replace(" ", "_")
        if term in KNOWN_KEYWORDS or term in declared:
            continue
        out.append(" ".join(line.split()))
    return out


def audit_card(
    card: CardDef,
    catalog: IndexEntry | None,
    expectation: dict | None,
) -> list[Deficit]:
    """Every way this card falls short of what it prints."""
    if card.is_token:
        # A token has no printing to be measured against -- it is a game object
        # the engine creates, and its "oracle text" is whatever the card that
        # makes it said.  Auditing it compares a card to nothing.
        return []

    if catalog is None:
        return [
            Deficit(
                card.id,
                card.name,
                "no_catalog_row",
                "not in data/catalog/cards.sqlite; nothing to check it against",
            )
        ]

    out: list[Deficit] = []
    printed = catalog.oracle_text or ""

    # 1. Does the card even record what it prints?  This is the one that makes
    #    the others possible: while `oracle_text` is a paraphrase, the residual
    #    gate is checking the implementation against a summary of itself.
    if canonical(printed, card.name) != canonical(card.oracle_text, card.name):
        out.append(
            Deficit(
                card.id,
                card.name,
                "paraphrased_oracle",
                f"records {_clip(card.oracle_text)!r}, prints {_clip(printed)!r}",
            )
        )

    # 2. The real gate 3, run against the printing rather than the paraphrase --
    #    split by whether anything on the card is even *reaching* for the line.
    #    The two need different work and must not share a bucket: a line no
    #    ability is about is missing rules, and a line some ability plainly
    #    implements under a terser name is a mislabelled `text` field.
    drift = set(match_abilities(card, printed, floor=DRIFT_FLOOR).values())
    for line in unclaimed_lines(card, printed):
        kind = "text_drift" if line in drift else "residual"
        out.append(Deficit(card.id, card.name, kind, " ".join(line.split())))

    for line in unimplemented_mechanics(card, printed):
        out.append(Deficit(card.id, card.name, "spell_text_lost", line))

    # 3. The real gate 5's precondition.  `verify` rejects an empty expectation
    #    outright ("a card nobody asserted anything about has not been
    #    verified"); the same standard applies here.
    #
    #    A zone-only expectation counts as unasserted, not as asserted. "It ended
    #    up on the battlefield" is what 447 of the authored cards assert and it is
    #    a real check -- it is how gate 4 and gate 5 differ at all -- but it says
    #    nothing about what the card *did*, so a card carrying only that has not
    #    had its effect verified by anybody. Counting it as covered would let
    #    `--fix-expectations` close this number by writing 179 assertions that
    #    assert nothing, which is worse than the gap it papers over.
    if not expectation:
        out.append(Deficit(card.id, card.name, "unasserted", "no behaviour expectation"))
    elif set(expectation) <= {"zone"}:
        out.append(
            Deficit(card.id, card.name, "unasserted", "only asserts where the card ended up")
        )
    else:
        unknown = sorted(set(expectation) - set(EXPECTATION_KEYS))
        if unknown:
            out.append(
                Deficit(card.id, card.name, "unasserted", f"unknown expectation key(s) {unknown}")
            )

    return out



def printed_row(card, index):
    """The catalog row for a card, including one *face* of a double-faced card.

    The index reduces every card to one row, and a transforming card's row is
    stored under the joined name -- "Bloodline Keeper // Lord of Lineage" -- so
    neither face finds it by its own name. The **front** face is what that row's
    ``oracle_text`` actually holds, so only the front is looked up this way; a
    back face has no printed text in the catalog at all and is honestly reported
    as having nothing to check against.
    """
    if card.back_face is not None:
        return index.lookup(card.name, joined=True)
    if card.front_face is not None:
        return None
    return index.lookup(card.name, token=False)

def audit(
    registry: CardRegistry,
    index: CardIndex,
    expectations: dict[str, dict],
) -> list[Deficit]:
    """Every deficit in a pool, worst first.

    ``registry`` is the hand-written layer alone.  Auditing ``auto/`` would be
    redundant -- ``tests/cards/test_auto_cards.py`` already re-runs all six gates
    over every card in it on every test run.
    """
    out: list[Deficit] = []
    for card in sorted(registry, key=lambda c: c.id):
        catalog = printed_row(card, index)
        out.extend(audit_card(card, catalog, expectations.get(card.id)))
    return sorted(out, key=lambda d: (KINDS.index(d.kind), d.card_id))


#: The one deficit that means the card does not do what it prints, and so the
#: only one that re-opens a queue entry for ``/author-cards``.
#:
#: The others are deliberately excluded. ``paraphrased_oracle`` is repaired by
#: ``--fix-oracle`` and needs no worker; ``text_drift`` is a mislabelled field on
#: an ability that already works; ``unasserted`` is a missing *test*, and handing
#: a worker a card that is correct but untested would get it rewritten rather
#: than asserted. Sending any of those to a worker would spend a card's worth of
#: effort re-authoring something that already plays correctly.
BLOCKING_KINDS = frozenset({"residual", "spell_text_lost"})


def blocking(deficits: list[Deficit]) -> dict[str, str]:
    """``{card_id: why}`` for cards whose implementation is incomplete."""
    out: dict[str, list[str]] = {}
    for deficit in deficits:
        if deficit.kind in BLOCKING_KINDS:
            out.setdefault(deficit.card_id, []).append(deficit.detail)
    return {card_id: " / ".join(lines) for card_id, lines in out.items()}


def _clip(text: str, limit: int = 60) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
