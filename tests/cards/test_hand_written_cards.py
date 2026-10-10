"""Hold the hand-written pool to the bar the authored pool already meets.

`tests/cards/test_auto_cards.py` re-runs all six authoring gates over every card
in `data/cards/auto/` on every test run, because a card accepted months ago can
be quietly invalidated by an engine change and nothing about the card file would
look different.

`data/cards/` -- the four precons and the shared staples -- never cleared those
gates at all. Those cards predate the pipeline, and two of the six have never run
over them: residual (is every printed sentence implemented?) and behaviour (does
the card demonstrably do it?).

They could not run, for one reason. `oracle_text` on a hand-written card used to
be a human paraphrase, written *after* whatever was skipped, so the card's own
record already agreed with the shortcut -- Krosan Tusker's oracle text was "A
large boar.", and against that text a vanilla 6/5 is faithful. Once
`scripts/audit_cards.py --fix-oracle` made `oracle_text` the printed text, the
question stopped being begged and the gates became answerable.

So they run here. A card that does not pass is listed in `precon_deficits.json`
with the reason, and xfails; every other hand-written card must clear all six.
The list has been worked down to empty, one repair and one regenerated baseline
at a time. It cannot get longer without somebody choosing to.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

import pytest

from commanderblitz.cards.authoring import fidelity as F
from commanderblitz.cards.authoring import verify as V
from commanderblitz.cards.images import load_index
from commanderblitz.cards.registry import CardRegistry, data_dir

BASELINE = Path(__file__).parent / "precon_deficits.json"
EXPECTATIONS = Path(__file__).parent / "expectations.json"

#: The command that rewrites the baseline, named in every failure message that
#: wants it run. A test that says "this is stale" without saying what to do
#: about it costs the reader the same lookup every time.
REGENERATE = "python scripts/audit_cards.py --update-baseline"


def _payloads() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted((data_dir() / "cards").glob("*.cards.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        for card in raw.get("cards", []):
            out[card["id"]] = card
    return out


def _baseline() -> dict[str, str]:
    if not BASELINE.exists():
        return {}
    return json.loads(BASELINE.read_text(encoding="utf-8")).get("cards", {})


def _expectations() -> dict[str, dict]:
    if not EXPECTATIONS.exists():
        return {}
    raw = json.loads(EXPECTATIONS.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


PAYLOADS = _payloads()
POOL = CardRegistry.from_paths(sorted((data_dir() / "cards").glob("*.cards.json")))
# Tokens are excluded: a token is a game object the engine creates, it has no
# printing to be measured against and cannot be cast in the gate 4 sandbox.
CARD_IDS = sorted(card.id for card in POOL if not card.is_token)
DEFICITS = _baseline()


@pytest.fixture(scope="module")
def catalog():
    index = load_index()
    if index is None:
        pytest.skip("no card catalog; run scripts/build_card_index.py")
    return index


@functools.lru_cache(maxsize=1)
def _failing() -> frozenset[str]:
    """Which cards fail the gates right now, by running them.

    The same computation `scripts/audit_cards.py --update-baseline` records, so
    the two cannot disagree -- the baseline is checked against the gates
    themselves rather than against the audit's reading of the printed text.
    Cached because it builds a sandbox per card and three tests want it.
    """
    return frozenset(
        card_id
        for card_id in CARD_IDS
        if not V.verify(
            PAYLOADS[card_id], _expectations().get(card_id, {}), _pool_without(card_id)
        ).ok
    )


def _pool_without(card_id: str) -> CardRegistry:
    """The hand-written pool minus one card -- what that card is verified against.

    Gate 6 rejects a card whose id is already in the registry, so verifying
    against the pool the card is *in* would either fail every card or, with the
    gate stood down, let a card lean on the copy of itself already loaded. The
    authored tier gets the same treatment from `author_cards._hand_written()`.
    """
    return CardRegistry({c.id: c for c in POOL if c.id != card_id})


class TestEveryHandWrittenCardClearsTheGates:
    @pytest.mark.parametrize("card_id", CARD_IDS)
    def test_it_clears_every_gate(self, card_id):
        """All six gates, against the card's own `oracle_text`.

        Its own, not the catalog's, and that is safe only because of the test
        below: `oracle_text` is now required to *be* the printed text, and is
        checked separately. Passing the catalog's copy here instead would fail
        every card, since `--fix-oracle` writes the printing in the pool's house
        style -- "When this creature enters" where the catalog names the card --
        and the ability text fields are matched against the stored form.
        """
        if card_id in DEFICITS:
            pytest.xfail(DEFICITS[card_id])
        verdict = V.verify(
            PAYLOADS[card_id],
            _expectations().get(card_id, {}),
            _pool_without(card_id),
        )
        assert verdict.ok, str(verdict)

    @pytest.mark.parametrize("card_id", CARD_IDS)
    def test_its_oracle_text_is_what_it_prints(self, card_id, catalog):
        """The half of the residual gate that cannot be checked against the card.

        This is the assumption the whole audit rests on. While `oracle_text` was
        a paraphrase written after the implementation, gate 3 compared a card to
        a summary of itself and passed by construction -- Krosan Tusker recorded
        "A large boar." and a vanilla 6/5 satisfied it. Checking the record
        against the catalog is what stops that from silently coming back.
        """
        card = POOL.get(card_id)
        entry = F.printed_row(card, catalog)
        if entry is None or not entry.oracle_text:
            pytest.skip(f"{card.name} is not in the catalog")
        printed = F.canonical(entry.oracle_text, card.name)
        recorded = F.canonical(card.oracle_text, card.name)
        assert recorded == printed, (
            f"{card_id} records text that is not what it prints\n"
            f"  records: {card.oracle_text!r}\n"
            f"  prints:  {entry.oracle_text!r}\n"
            f"  run: python scripts/audit_cards.py --fix-oracle"
        )


class TestTheBaselineIsHonest:
    """The list can only shrink, and only by a card actually being repaired.

    Deliberately not `xfail(strict=True)` on the cards themselves.
    `/author-cards` runs `pytest tests/cards` before it commits and stops on
    failure, so a strict xfail would make every *successful* repair abort the run
    that produced it. These say the same thing at the right altitude: the
    baseline is stale, here is the command.
    """

    def test_it_lists_no_card_that_already_passes(self):
        fixed = sorted(card_id for card_id in DEFICITS if card_id not in _failing())
        assert not fixed, f"repaired but still listed: {fixed}\nrun: {REGENERATE}"

    def test_no_card_fails_without_being_listed(self):
        """A new deficit cannot arrive unannounced.

        Adding a card to `data/cards/` that does not implement what it prints is
        allowed -- sometimes the DSL cannot say it yet -- but it has to be written
        down, which is the whole difference between this pool and the one that
        produced the deficits in the first place.
        """
        unlisted = sorted(card_id for card_id in _failing() if card_id not in DEFICITS)
        assert not unlisted, f"fails the gates and is unlisted: {unlisted}\nrun: {REGENERATE}"

    def test_it_names_real_cards(self):
        gone = sorted(set(DEFICITS) - set(CARD_IDS))
        assert not gone, f"listed but no longer in the pool: {gone}\nrun: {REGENERATE}"


def test_no_orphan_expectations():
    """Every key in `expectations.json` names a hand-written card.

    The mirror of `test_auto_cards.py`'s check. Without it a card superseded
    into `auto/`, turned into a back face or deleted leaves its expectation
    behind, and `test_every_card_works.py` goes on asserting that weaker,
    stale expectation against whatever now carries the id -- twelve did.
    """
    orphans = sorted(set(_expectations()) - set(CARD_IDS))
    assert orphans == [], f"expectations for cards that are not hand-written: {orphans[:10]}"


def test_the_hand_written_pool_is_measured_at_all():
    """A guard on the guard.

    Every assertion above is parametrized or derived, so a bug that emptied the
    pool would turn this file green rather than red -- the same failure shape the
    audit exists to catch, one level up.
    """
    assert len(CARD_IDS) > 150, f"only {len(CARD_IDS)} hand-written cards found"
