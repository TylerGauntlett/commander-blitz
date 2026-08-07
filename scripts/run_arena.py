"""Run headless duels and report the results.

    python scripts/run_arena.py --games 200 --pods 2,4
    python scripts/run_arena.py --agents heuristic,heuristic --pods 4 --out runs/
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automtg.ai.arena import run_arena
from automtg.ai.stats import render_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=100, help="games per pod size")
    parser.add_argument("--pods", default="2,4", help="comma-separated pod sizes")
    parser.add_argument("--agents", default="heuristic,random", help="agents, by seat")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None, help="write reports here")
    parser.add_argument(
        "--checkpoint",
        default=None,
        help="policy checkpoint for any 'policy' seat (default: it plays the heuristic)",
    )
    parser.add_argument(
        "--max-draw-rate",
        type=float,
        default=None,
        help="fail if the draw rate exceeds this (use as a gate)",
    )
    args = parser.parse_args()

    pod_sizes = [int(p) for p in args.pods.split(",") if p.strip()]
    agents = [a.strip() for a in args.agents.split(",") if a.strip()]

    start = time.time()
    summaries = run_arena(
        agent_names=agents,
        pod_sizes=pod_sizes,
        games=args.games,
        seed=args.seed,
        out_dir=args.out,
        checkpoint=args.checkpoint,
    )
    elapsed = time.time() - start

    print(render_markdown(summaries))
    total = sum(s.games for s in summaries.values())
    print(f"{total} games in {elapsed:.1f}s ({elapsed / max(1, total):.3f}s/game)")
    if args.out:
        print(f"reports written to {args.out}")

    if args.max_draw_rate is not None:
        for pod_size, summary in sorted(summaries.items()):
            if summary.draw_rate > args.max_draw_rate:
                print(
                    f"FAIL {pod_size}-player draw rate {summary.draw_rate:.1%} "
                    f"exceeds {args.max_draw_rate:.1%}"
                )
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
