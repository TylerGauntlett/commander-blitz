# ADR 0007 — Versioned long-polling for multiplayer

**Status:** accepted

## Context

Until now the client only ever refreshed after its own mutation: `useGame` refetched
in the mutation's success handler and nowhere else. That was correct for a
single-player app, because nothing could change that this client did not cause.

Multiplayer breaks that assumption twice over. In the lobby, another player picks a
deck or locks in and every other screen must notice. At the table, another human
takes their turn and the seat waiting on them must notice. Neither is caused by the
client that needs to see it.

[ADR 0004] and `architecture.md` both record "no WebSockets" as a decision, on the
grounds that a local single-user app polling on mutation removes a whole class of
reconnection state. Multiplayer is the case that was supposed to force a revisit.

## Decision

**Every pod and every game session carries a monotonic `version`. Clients pass the
version they last saw as `?since=` (pods) or `?since_version=` (games), and the
server blocks on a `threading.Condition` until the number moves or ~25 seconds
elapse.**

Three rules make it work:

- `Condition.wait_for` **releases the lock while it blocks**. Rendering happens under
  the lock after the wait returns, in the same `with` block, so a caller can never
  observe a torn pod.
- **A timeout is not an error.** The server returns the current view with a 200 and
  the client immediately re-polls. A long poll is indistinguishable from a slow one,
  and a dropped connection costs at most one round trip.
- `since=0` **returns immediately.** That is the first fetch, and it means the same
  endpoint serves "give me the state" and "tell me when it changes".

## Consequences

**Good.** No new dependency, no reconnection state machine, no separate message
protocol to keep in sync with the REST shapes. Every handler stays a plain sync
`def`, which means `TestClient` drives the whole thing — `test_pod_races.py` fires
four simultaneous joins at one pod from a thread pool and asserts on the outcome
*set*, which would be far harder against an async socket layer. A client that
crashes needs no cleanup: its poll simply never comes back.

**The cost is a parked thread per waiting client.** Starlette runs sync handlers in a
40-thread pool, so four players in a pod plus four at a table is eight threads of the
forty. That is fine at pod scale and would not be at hundreds of concurrent players —
which this app is explicitly not for (`Reach: one uvicorn process, many clients on the
same machine or LAN`).

**Version numbers are per-object and process-local.** They are not durable, not
comparable across restarts, and not a vector clock. A client that reconnects after a
server restart sees a lower version than it held and simply re-fetches from zero,
which is the correct outcome anyway.

**A game client holds two cursors and must carry both.** The version says *when* to
wake; the event cursor (`event_cursor`, fed back as `?since=`) says *what* is new. A
response is self-describing — its events end at its `event_cursor` — so a client that
receives one overlapping something it already holds can trim it rather than render a
move twice, which is what makes it safe for a pump reply and a poll reply to land in
either order. The first game client carried only the version and asked for events from
zero, and every poll that landed replayed the whole game (`docs/bugs.md`).

## Alternatives considered

**WebSockets.** The obvious answer, and genuinely better above a few dozen concurrent
clients. Rejected because it brings a reconnection state machine, a second message
vocabulary parallel to the REST shapes, and async handlers throughout — three real
costs to buy something the LAN-scale target does not need. The cost is bounded and
this decision is reversible: the versioning is the hard part, and a socket transport
would push the same versioned views down the same shapes.

**Short polling on an interval.** Simplest of all, and what the mockups assumed.
Rejected because the interval is a choice between latency and load with no good
answer: 500 ms makes locking in feel instant and generates 8 requests a second across
a pod doing nothing; 3 s makes the lobby feel broken.

**Server-Sent Events.** A real middle ground — one-directional, no protocol upgrade,
auto-reconnecting. Rejected mainly because it needs an async generator per handler
and would have split the route layer into two styles, for a latency improvement over
long-polling that is essentially zero at this scale.

[ADR 0004]: 0004-incremental-combat.md
