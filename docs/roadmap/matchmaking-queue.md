---
id: matchmaking-queue
title: A queue
area: matchmaking
effort: L
impact: medium
why: strangers only, and the site is mostly one player today
depends_on: [zero-downtime-deploys, cpu-takeover, brackets, outcome-log]
status: proposed
---

## Today

A pod is reached by a code read down a phone line, so a table is only ever
people who already know each other. There is no way to be paired with a
stranger, and nothing that would make such a pairing fair.

## The change

**Shape.** `POST /api/queue {deck_id, pod_size}` and a long poll on the ticket,
the way pods already work ([ADR 0007](../adr/0007-versioned-long-polling.md)).
The server forms a pod when it holds enough compatible tickets, returns the
pod code and a player token, and from there the existing lobby and deal run
unchanged: matchmaking creates pods, it does not replace them. Compatibility
is the deck's bracket within one step, widening as a ticket ages; a ticket
older than a threshold is dealt with CPU seats rather than left waiting. The
whole feature lives on the hosted site, since the desktop already goes there
for anyone who is not on the LAN.

**What it needs first, and why each is a dependency:**

- persisted sessions and CPU takeover, because a stranger who leaves is the
  common case and a queue that produces dropped games teaches players not to
  use it;
- the outcome log, so the bracket thresholds can be tuned from games rather
  than guessed;
- an identity that outlives a pod only if anything is ever rated. Nothing in
  forming a pod needs one. A client-generated id in local storage is enough
  for "do not re-pair me with the seat that just left", and real accounts are
  a separate decision with an ADR of its own, taken only when ratings or a
  history are wanted.

**Scale.** A parked thread per waiting client is the long-poll's cost, and a
queue adds waiters. That is fine at the scale the site is for, and the day it
is not is the day a second worker and a shared store are needed, which is the
real reason the persisted-session work comes first.

## Gate

Server tests in the shape of `test_pod_races.py`: N tickets from N threads
form the right number of pods with compatible brackets and no ticket seated
twice; an aged ticket is dealt with CPUs; and a formed pod is an ordinary
pod to every existing test. The pod e2e spec drives two browsers through
the queue into one table.
