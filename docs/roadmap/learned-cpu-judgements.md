---
id: learned-cpu-judgements
title: Learned judgements behind the strategy hooks
area: cpus
effort: L
impact: high
why: every game the maintainer plays is against the CPU, and so is most of every stranger's first
depends_on: [outcome-log, replays, difficulty]
status: proposed
---

## Today

The CPU is reflexive: the heuristic scores every legal action from
the position in front of it and a per-deck `Strategy` adjusts the scores
([cpus/README.md](../cpus/README.md)). It cannot look ahead, because state is
never cloned, and it reads the table only as board power and life. The gaps a
playtester notices are the ones [TECH_DEBT.md](../../TECH_DEBT.md) lists under
"Strategy gaps" and the ones the CPU page admits: it attacks whoever is
softest rather than whoever is winning, points removal by printed size rather
than by what a permanent is doing, and never holds mana open on purpose.

The trainer exists ([ai-training.md](../ai-training.md)): masked PPO over a
structured action space, a per-card embedding, a snapshot pool of opponents,
and an arena that reports win rates with confidence intervals. What it has
not been given is enough experience, and a whole-policy replacement of the
heuristic is a long road for a reward that arrives once per game.

## The change

**Learn the judgements, keep the plan.** The strategy
hooks are already the seams where the CPU's judgement enters: `defender`,
`attack_value`, `block_value`, `priority_value`, `choose`, `junk_value`. Each
takes the agent's answer and returns the one to use. A learned model can sit
behind any of them, trained from the same environment, while the deck plan
goes on deciding what the deck is trying to do. Three models, in the order
they pay off:

1. **Threat.** Which seat is winning, and which permanent on the table is
   doing the most for its controller. Trained as a value head from self-play
   outcomes and from the outcome log the site will keep: the input is the
   observation the environment already encodes plus the card embeddings, the
   target is who went on to win. It feeds `defender` (attack the seat that is
   ahead, not the one that is low), the removal half of `priority_value`
   (point the Swords at the engine, not the biggest body), and the
   counterspell rule (hold it for the spell that matters).
2. **Tempo.** Whether to spend mana now or keep it up: a classifier over the
   same observation that predicts whether a held instant is used profitably
   before the CPU's next turn. This is the "hold mana open" gap, and it
   changes only the ordering `priority_value` returns.
3. **Combat.** `logic/fight.ts` and `board.could_block` model a fight one
   pair at a time; a learned block and attack valuation over the whole
   declaration is the piece the reflexive agent cannot do by rule.

Each model is a few hundred kilobytes and runs under the same mask, so the
CPU can never pick an illegal action and the structural guarantees of the
single seam are untouched. Each ships as a checkpoint the `policy` agent
already knows how to load, under the difficulty picker.

**Where lookahead fits.** [ADR 0005](../adr/0005-no-state-cloning.md) rules out
cloning in the engine; it does not rule out *replay* as a way to explore a
line offline. A search agent that forks the tape, replays, and scores the
result is affordable for generating training positions, where wall-clock
does not matter, and not for play, where it does. So the search exists to
teach the models, and the models play. This is the one place the no-cloning
decision is worth re-reading before work starts; it does not need amending.

Deliver it one model at a time, the threat model first, each as its own
pull request with its own arena result in the body.

## Gate

The arena with the deck held fixed and only the pilot swapped is the sharp
test: the threat model's first gate is that the strategy CPU with it beats
the strategy CPU without it on every precon at a confidence the arena
reports, and that the draw rate does not move. Each of the strategy gaps in
the debt page becomes a seeded position in `tests/ai/strategy/` that the new
pilot must get right. The baseline heuristic stays the opponent `verify.py`
gates on until a checkpoint has beaten it across the board for long enough
to be trusted.
