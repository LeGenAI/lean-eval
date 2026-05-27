"""Bootstrap CIs on dataset row indices.

Matches the EntropyMaG-1 reporting convention (PDF Table 8):
"Bootstrap intervals resample dataset row indices, not individual repeats."
"""

from __future__ import annotations

import random
from typing import List, Sequence, Tuple


def _resample_rows(per_row: Sequence[float], rng: random.Random) -> List[float]:
    n = len(per_row)
    return [per_row[rng.randrange(n)] for _ in range(n)]


def bootstrap_ci(
    per_row_accuracy: Sequence[float],
    *,
    iterations: int = 1000,
    alpha: float = 0.05,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """Return (mean, lo, hi) for a single arm.

    `per_row_accuracy[i]` is the row-level accuracy (0..1) for problem i,
    typically averaged over the three repeats.
    """
    if not per_row_accuracy:
        return (0.0, 0.0, 0.0)
    rng = random.Random(seed)
    means: List[float] = []
    for _ in range(iterations):
        sample = _resample_rows(per_row_accuracy, rng)
        means.append(sum(sample) / len(sample))
    means.sort()
    lo = means[int(iterations * (alpha / 2))]
    hi = means[int(iterations * (1 - alpha / 2)) - 1]
    mean = sum(per_row_accuracy) / len(per_row_accuracy)
    return (mean, lo, hi)


def bootstrap_drop_ci(
    control_acc: Sequence[float],
    treatment_acc: Sequence[float],
    *,
    iterations: int = 1000,
    alpha: float = 0.05,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """Return (drop_mean_pp, lo_pp, hi_pp) for control-minus-treatment.

    The control and treatment arms are resampled independently because they
    contain different row indices; this matches the per-cell bootstrap used in
    the EntropyMaG-1 paper.
    """
    if not control_acc or not treatment_acc:
        return (0.0, 0.0, 0.0)
    rng_c = random.Random(seed)
    rng_t = random.Random(seed + 1)
    drops: List[float] = []
    for _ in range(iterations):
        c = _resample_rows(control_acc, rng_c)
        t = _resample_rows(treatment_acc, rng_t)
        drops.append(100.0 * (sum(c) / len(c) - sum(t) / len(t)))
    drops.sort()
    lo = drops[int(iterations * (alpha / 2))]
    hi = drops[int(iterations * (1 - alpha / 2)) - 1]
    mean = 100.0 * (
        sum(control_acc) / len(control_acc) - sum(treatment_acc) / len(treatment_acc)
    )
    return (mean, lo, hi)
