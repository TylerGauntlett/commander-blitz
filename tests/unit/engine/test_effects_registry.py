"""The effect-op registry is populated by import, so importing is what is tested.

``engine/effects/__init__.py`` builds ``OPS`` by importing every ``ops_*``
module at its bottom, from an explicit tuple. There is no directory scan: a new
op module that nobody adds to that tuple registers nothing, and every card that
names one of its ops fails to load with "unknown effect op". These tests make
that mistake fail here, by name, rather than in a card test three suites away.
"""

from __future__ import annotations

import pkgutil
import sys

import pytest

from commanderblitz.engine import effects
from commanderblitz.engine.effects import OPS, register
from commanderblitz.engine.errors import DslError


def op_modules() -> list[str]:
    """Every ``ops_*`` module that exists on disk under ``engine.effects``."""
    return sorted(
        info.name
        for info in pkgutil.iter_modules(effects.__path__)
        if info.name.startswith("ops_")
    )


def test_every_op_module_on_disk_was_imported() -> None:
    on_disk = op_modules()
    assert on_disk, "no ops_* modules found; the package layout moved"
    not_imported = [
        name for name in on_disk if f"{effects.__name__}.{name}" not in sys.modules
    ]
    assert not not_imported, (
        f"{not_imported} exist but are not in the import tuple at the bottom of "
        "engine/effects/__init__.py, so nothing they register exists"
    )


def test_every_op_module_registers_something() -> None:
    by_module: dict[str, int] = {}
    for fn in OPS.values():
        module = fn.__module__.rsplit(".", 1)[-1]
        by_module[module] = by_module.get(module, 0) + 1
    silent = [name for name in op_modules() if by_module.get(name, 0) == 0]
    assert not silent, f"op modules that register no op: {silent}"


def test_registering_a_name_twice_is_refused() -> None:
    taken = next(iter(OPS))
    with pytest.raises(DslError, match="duplicate effect op"):
        register(taken)(lambda ctx, spec: None)
    # And the refusal did not clobber the original.
    assert OPS[taken].__module__.startswith(effects.__name__)


def test_the_registry_is_the_public_surface() -> None:
    assert effects.known_ops() == frozenset(OPS)
    assert set(effects.__all__) >= {"OPS", "RECORDING_OPS", "known_ops", "register"}
    assert effects.known_ops() >= effects.RECORDING_OPS, (
        "RECORDING_OPS names an op that is not registered"
    )
