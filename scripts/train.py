"""Train a self-play policy.

    python scripts/train.py --pod 2 --updates 100
    python scripts/train.py --pod 4 --updates 100 --out runs/

Checkpoints are written per pod size, because a duel and a four-player pod
reward different play and the spec asks for the two to be segmented.
Requires the ``train`` extra: pip install -e ".[train]"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from commanderblitz.ai.train import TrainConfig, train


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pod", type=int, default=2, choices=(2, 3, 4))
    parser.add_argument("--updates", type=int, default=100)
    parser.add_argument("--steps", type=int, default=512, help="env steps per update")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--out", type=Path, default=Path("runs"))
    args = parser.parse_args()

    try:
        import torch  # noqa: F401
    except ImportError:
        print('FAIL torch is not installed. Run: pip install -e ".[train]"')
        return 1

    config = TrainConfig(
        pod_size=args.pod,
        updates=args.updates,
        steps_per_update=args.steps,
        seed=args.seed,
        lr=args.lr,
        out_dir=args.out,
    )
    path = train(config)
    print(f"\nwrote {path}")
    print(f"evaluate it with: python scripts/run_arena.py --agents policy,heuristic --pods {args.pod}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
