# ADR 0026 — The roadmap autopilot builds only decided items and merges on green

**Status:** accepted

[ADR 0010](0010-release-every-main-build.md) made every shipping merge a deploy
and a Deck release, on the reasoning that the gate is the judge of a tree. Until
now a person still started every roadmap run and pressed every merge: someone
typed `/extend-roadmap` in a new session, answered its questions, and merged the
green pull request. This ADR is what happens when nobody does.

## Context

The backlog under `docs/roadmap/` is already data: `scripts/roadmap.py --next`
ranks it, and `/extend-roadmap` can take the top item from plan to a green pull
request without help. Three things kept it a manual loop. The skill stops to ask
the architecture questions an item leaves open, and a run with nobody to answer
stops there. The skill never merges. And nothing starts the next run once a
pull request lands.

The questions are the part that matters. A feature built on a guessed answer is
a pull request that gets rewritten, and an autopilot that guesses would ship
those guesses straight to the site. The answers are cheap for the owner to give
and expensive to get wrong, so they belong in the plan, ahead of the run.

## Decision

**A scheduled task starts a fresh session every four hours with
`/extend-roadmap --auto`. That session builds only a *decided* item, opens its
pull request with auto-merge on, and lets branch protection decide the merge.
The merge starts the next run.**

- **Decided is a property of the item.** An item carries a **Decisions** section
  (each open question with the owner's answer) and no **Open questions**
  section. `scripts/roadmap.py` validates both, marks an undecided item on the
  page, and `--next --auto` prints the autopilot's queue: ready, decided and not
  continuous. Continuous items are batches a person starts. Only the owner
  writes an answer; `/plan-feature` writes the questions and a recommendation,
  and `/plan-feature answer <id>` records the answers.
- **It never guesses.** A question the item does not answer, or a **Today** that
  no longer holds, becomes an **Open question** in a `docs(roadmap):` pull
  request, and the item waits. When nothing is decided, a run drafts the open
  questions for the top undecided item instead, so the owner always has the
  next item's questions in front of them.
- **One autopilot pull request at a time.** Every pull request it opens carries
  the `autopilot` label, and a run that finds one open stops, or flags a stuck
  one with a single comment. The label is the lock because `--start` happens on
  a branch, where `main` cannot see it.
- **GitHub merges, not the agent.** The run turns on auto-merge with a squash.
  Branch protection on `main` requires `verify gate`, `pull request title` and
  `secrets`, so the merge happens only when the same gate a person would wait on
  is green. The run stays subscribed and fixes red checks and review asks until
  then, as `/extend-roadmap` §9 already requires.
- **The chain.** On the merge event the run fires the scheduled task named
  `roadmap autopilot` again, so the next run starts on the `main` the merge
  made. The four-hourly schedule is the safety net for a run that died, hit a
  usage limit or missed an event; a firing that finds the lock held costs one
  preflight.

## Consequences

- A `feat:` item the autopilot delivers deploys the site and cuts a Deck
  release with no person reading the diff first. What a person controls is the
  plan: the queue order, and the answers in **Decisions**. An item the owner
  wants to read before it ships keeps an **Open question** until they have.
- Every item on the backlog when this landed has no **Decisions**, so the
  autopilot builds nothing until the owner answers; until then each run
  prepares one item's questions.
- Branch protection on `main` and "Allow auto-merge" are load-bearing settings,
  set by a maintainer ([ci-cd.md](../ci-cd.md#roadmap-autopilot)). Without the
  protection, auto-merge merges at once.
- How fast the loop goes is set by the plan's usage limits. A run cut off by one
  leaves its pull request labelled and open, and the next firing goes on.

## Rejected

- **Answering the questions with the agent's own recommendation.** It removes
  the owner from the one decision only they can make, and turns a reversible
  plan into a deployed guess.
- **A GitHub Actions workflow running the agent on each merge.** It bills an API
  key separately from the plan the sessions already run on, and duplicates the
  harness's own PR subscription and scheduling.
- **A schedule alone, without the chain.** It works, but leaves up to four hours
  idle after every merge.
- **Merging from the session.** The skill's rule that it never merges stands;
  auto-merge keeps the decision with branch protection, where it can be audited
  and turned off in one setting.
