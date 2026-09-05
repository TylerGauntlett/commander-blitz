"""The compiled card pool, pinned.

A safety net for restructuring the loader and the engine's op modules without
changing what they produce. Every shipped card -- hand-written and
machine-authored -- is compiled through ``compile_card`` and serialised
deterministically; the hash of the whole pool, the sorted op registry and the
loader's vocabulary constants are compared against files checked in beside this
test. A move that drops a constant, forgets to import an op module, or changes
one compile path anywhere in 2,600 cards fails here, in seconds, naming what
moved.

To re-pin after a deliberate change::

    AUTOMTG_UPDATE_GOLDEN=1 python -m pytest tests/cards/test_golden_pool.py

and commit the two files with the change that made them move. The pin is the
pool as shipped, so a card added in the normal way moves it too -- that is the
point: this file is the one place that says "nothing changed", and adding a
card is a change.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from automtg.cards import loader
from automtg.cards.registry import CardRegistry, authored_card_paths
from automtg.engine.effects import known_ops

HERE = Path(__file__).resolve().parent
CARD_DIR = HERE.parents[1] / "data" / "cards"
POOL_HASH = HERE / "golden_pool.sha256"
VOCABULARY = HERE / "golden_vocabulary.json"

#: Every module-level constant in the loader whose *membership* is the DSL's
#: vocabulary. If one of these loses an entry, a card that used it fails to load;
#: if one gains an entry the DSL grew. Both are worth a diff in review.
VOCABULARY_CONSTANTS = sorted(
    name
    for name, value in vars(loader).items()
    if name.isupper() and isinstance(value, (frozenset, set, tuple, dict))
)


def canon(value: Any) -> Any:
    """A JSON-serialisable, order-independent view of a compiled object."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: canon(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(k): canon(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (set, frozenset)):
        return sorted((canon(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(value, (list, tuple)):
        return [canon(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def pool_digest(registry: CardRegistry) -> str:
    digest = hashlib.sha256()
    for card in sorted(registry, key=lambda c: c.id):
        digest.update(card.id.encode())
        digest.update(json.dumps(canon(card), sort_keys=True, separators=(",", ":")).encode())
    return digest.hexdigest()


def vocabulary_snapshot() -> dict[str, Any]:
    constants = {name: canon(getattr(loader, name)) for name in VOCABULARY_CONSTANTS}
    return {"ops": sorted(known_ops()), "loader": constants}


@pytest.fixture(scope="module")
def shipped() -> CardRegistry:
    return CardRegistry.from_paths(authored_card_paths(CARD_DIR))


def _updating() -> bool:
    return os.environ.get("AUTOMTG_UPDATE_GOLDEN") == "1"


def test_every_shipped_card_compiles_to_what_it_did(shipped: CardRegistry) -> None:
    digest = pool_digest(shipped)
    if _updating():
        POOL_HASH.write_text(digest + "\n", encoding="utf-8", newline="\n")
    assert POOL_HASH.exists(), "no golden hash yet: run with AUTOMTG_UPDATE_GOLDEN=1"
    pinned = POOL_HASH.read_text(encoding="utf-8").strip()
    assert digest == pinned, (
        f"the compiled pool changed ({len(shipped)} cards). If that was the intent, "
        "re-pin with AUTOMTG_UPDATE_GOLDEN=1 and commit golden_pool.sha256 with it."
    )


def test_the_ops_and_the_vocabulary_are_what_they_were() -> None:
    snapshot = vocabulary_snapshot()
    if _updating():
        VOCABULARY.write_text(
            json.dumps(snapshot, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    assert VOCABULARY.exists(), "no golden vocabulary yet: run with AUTOMTG_UPDATE_GOLDEN=1"
    pinned = json.loads(VOCABULARY.read_text(encoding="utf-8"))

    # Ops first and separately, because the likeliest way to lose one is a new
    # op module that nobody added to the import tuple in `effects/__init__.py`.
    missing = sorted(set(pinned["ops"]) - set(snapshot["ops"]))
    added = sorted(set(snapshot["ops"]) - set(pinned["ops"]))
    assert not missing, f"effect ops no longer registered: {missing}"
    assert not added, f"new effect ops, re-pin if intended: {added}"

    for name, value in pinned["loader"].items():
        assert name in snapshot["loader"], f"loader.{name} is gone"
        assert snapshot["loader"][name] == value, f"loader.{name} changed"
    extra = sorted(set(snapshot["loader"]) - set(pinned["loader"]))
    assert not extra, f"new loader vocabulary, re-pin if intended: {extra}"
