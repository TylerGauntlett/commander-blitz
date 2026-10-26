---
id: difficulty
title: Difficulty
area: play
effort: S
impact: medium
why: visible in every pod, and the place the CPU work lands where a player can see it
depends_on: []
status: proposed
---

## Today

Three agents already exist with a clear ordering: `heuristic_classic`,
`heuristic` with its strategies, and `policy`, all built by `agent_by_name`.
The wire already carries a per-seat agent: `SeatConfig.agent` and
`SeatAdminRequest.agent` accept `random`, `heuristic` or `policy`, and the
lobby's `set_agent` seat action stores it. Nothing in the client sends it:
`PodRoute` calls `adminSeat` only for the actions without an agent, so every
CPU a player seats plays `heuristic`. `heuristic_classic` is not a value the
server accepts, and `GameSession` builds every agent without a checkpoint, so
`policy` is `PolicyAgent` falling back to the heuristic. No checkpoint ships,
and [ai-training.md](../ai-training.md) trains one per pod size.

## The change

A per-seat choice in the pod (easy, normal, hard) as a field on `SeatConfig`
and a segment on the CPU chair, mapped to the three agents, with hard meaning
the best checkpoint shipped and falling back to the strategy CPU when none
is. It gives the learned-judgement work a place to land that a player can
see, and it ships before any model does.

## Gate

The lobby's predicates in `logic/lobby.ts` cover the new field; the pod
server tests assert the agent each seat is dealt; and the lobby story and
e2e spec reach the segment with a pad under the floors.

## Open questions

- **A new field, or the existing `agent`?** The change names a field on
  `SeatConfig`, but `agent` and `set_agent` are already that seam end to end.
  Recommended: keep `agent` as the one field and map easy, normal and hard
  onto it in the client, adding `heuristic_classic` to the accepted values;
  a second field that only translates to the first is two sources for one
  fact.
- **What is easy?** Recommended: `heuristic_classic`, the agent from before
  strategies, not `random`, which makes no game of it; `random` stays a value
  the API takes and the segment does not offer.
- **Where does the hard checkpoint live, and how is it found?** None ships
  today, and one is trained per pod size. Recommended: build the seam only,
  a server setting naming a checkpoint per pod size that `GameSession` hands
  to a `policy` seat, unset by default so hard plays the strategy CPU; which
  checkpoint ships, and whether it is committed or deployed beside the site,
  is a later item with its own ADR.
- **Does hard say it is falling back?** With no checkpoint, hard and normal
  play the same game. Recommended: keep all three segments and let the seat
  report the agent it actually got, so the lobby can mark hard as "strategy
  CPU" until a model lands, rather than hiding the segment.
- **Who may set it?** Recommended: the host, through `set_agent`, the same
  rule as the seat's deck; a joined player's own seat is human and has no
  difficulty.
- **Does a rematch keep it?** `GameRoute`'s rematch rebuilds the seats
  through `useNewGame` and omits `agent`, because the table view does not say
  which agent a seat runs, so every rematch plays `heuristic`. Recommended:
  the player view carries each CPU seat's agent and the rematch sends it back,
  so a hard table stays hard, in the same pull request.
