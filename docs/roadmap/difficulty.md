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
`heuristic` with its strategies, and `policy`. A pod seats every CPU with
the same one, and a player cannot ask for an easier or harder table.

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
