"""An action's record is lossless, so a tape written to disk replays (ADR 0023)."""

from __future__ import annotations

from dataclasses import MISSING, fields

import pytest

from commanderblitz.engine.actions import Action
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.structs import TargetRef


def _non_default(spec):
    """A value for ``spec`` that is not its default, from the default's type."""
    default = spec.default
    if spec.name == "kind":
        return ActionKind.CAST
    if spec.name == "targets":
        return (TargetRef.obj(7), TargetRef.player(1), TargetRef.stack(2))
    if isinstance(default, bool):
        return not default
    if isinstance(default, tuple):
        return (2, 0)
    if isinstance(default, int):
        return default + 3
    if default is None:
        # `warp` is a mana string; every other optional field is an index.
        return "{2}{R}" if spec.name == "warp" else 4
    raise AssertionError(f"no test value for Action.{spec.name}")


IDENTITY = [spec for spec in fields(Action) if spec.compare]


@pytest.mark.parametrize("spec", IDENTITY, ids=lambda s: s.name)
def test_every_identity_field_survives_the_round_trip(spec):
    """A field added to Action is covered here the moment it exists."""
    assert spec.default is not MISSING or spec.name == "kind"
    values = {"kind": ActionKind.PASS, spec.name: _non_default(spec)}
    action = Action(**values)
    assert Action.from_record(action.to_record()) == action


def test_a_default_field_is_left_out_of_the_record():
    assert Action(ActionKind.PASS).to_record() == {"kind": "pass"}


def test_display_fields_are_not_recorded():
    action = Action(ActionKind.PASS, label="Pass", base_label="Pass", pays=(3,))
    assert set(action.to_record()) == {"kind"}


def test_an_unknown_field_is_refused_rather_than_ignored():
    with pytest.raises(ValueError):
        Action.from_record({"kind": "pass", "invented": True})
