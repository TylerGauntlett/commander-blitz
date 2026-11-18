# ADR 0030 — A static control effect is enforced where state-based actions are checked

**Status:** accepted

## Context

"You control enchanted creature" (Control Magic, Become the Pilot) and "The
monarch controls enchanted creature" (Fealty to the Realm) are static abilities
whose effect is a control change in layer 2 (613.1b). Like every static effect it
applies continuously, for as long as the static does, in timestamp order with
the other effects of its layer (613.7).

The engine's other layers are computed: `chars` derives types, abilities, colours
and power/toughness from the printed face and the statics on the battlefield
every time it is asked. Control is not. `GameObject.controller` is a field,
written by `primitives.change_control`, and every reader in the engine — legality,
combat, the selectors, the `controller` key of every static filter, `chars`
itself — reads the field. The one-shot `gain_control` op and its durations
already work that way: the steal writes the field and a `TempEffect(kind="control")`
records how to undo it.

A static control effect cannot be one write. It must end when the Aura leaves,
moves or loses its abilities, follow the monarch as the crown moves, and yield to
a later control effect and resume when that one ends.

## Decision

The static writes the field too, and `primitives.reconcile_static_control` keeps
it true: it runs inside `sba.check`, so in every state-based-action pass, before
any player receives priority and after anything resolves. It returns whether it
changed anything and changes nothing when run twice, so the SBA loop reaches its
fixpoint.

Each (static source, affected permanent) pair owns one
`TempEffect(kind="control", while_static=True)` on the permanent, stamped with
the effect's 613.7 timestamp (`characteristics.static_timestamp`), recording the
seat it took the permanent from and the seat it last gave it to. The newest pair
on a permanent is in force while the permanent sits with that pair's seat;
otherwise a later effect holds it and the pair waits. A pair that no longer holds
ends with the handback through `_hand_back_control`, or, when a later effect
holds the permanent, is spliced out so that effect's handback skips it. Every
move goes through `change_control`, so 302.6, 506.4 and the `control_changed`
event apply. Cleanup and untap steps leave the entry alone.

The loader admits only `affects: {"attached": true}` and no `condition`, because
a filter or condition that reads what a seat controls would change as the static
moved the permanent, and the pass would hand it back and take it again forever.

## Consequences

**Good.** Every reader of control keeps reading the one field, unchanged. The
static and the timed steals share one record and one handback, so their
interaction (an Act of Treason on a Control Magic'd creature) is the existing
newest-first, still-the-reason logic. The SBA pass is already where a control
change's consequences are caught — the legend rule, an enchant clause that reads
"you control" (ADR 0029) — so those follow in the next pass.

**Bad.** Between the event that changes the static's answer and the next SBA
pass, the field is stale: inside one resolution, an Aura destroyed by the first
half of a spell has not yet handed the creature back when the second half reads
its controller. 613.7's order is approximated by the order in which pairs are
first enforced, which matches the timestamp for an Aura attaching but not for one
that regains its abilities. A permanent steal made by the seat a static entry
names is indistinguishable from the static still being the reason.

**Cost of reversing.** Moving the pass out of `sba.check` leaves the Aura's
arrival taking nothing until whatever new caller runs, and dropping it leaves
every control static inert. `tests/unit/effects/test_static_control.py` pins the
arrival, the endings, the crown, the later-effect ordering and the idempotence.

## Alternatives considered

**Computing control in `chars`.** Rules-exact, but every reader of
`GameObject.controller` would have to move to a derived read, and control feeds
the `controller` key that the layer pipeline's own filters read, so layer 2 would
have to be computed before the rest of `chars` with its own cache.

**A `gain_control` duration ended by the Aura leaving.** Covers the Aura leaving
only: not moving, not losing its abilities, not the crown moving.

**Eager hooks at each event** (`zones.move_object`, `attach`, `become_monarch`,
the ability-loss ops). Exact in time, but one hook per way the answer can change,
and a missed one is a creature silently on the wrong side of the board.
