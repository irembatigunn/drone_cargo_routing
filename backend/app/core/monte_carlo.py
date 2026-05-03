"""
Monte Carlo Simulation — Section 5.5 of PRD.
Computes expected delivery success rate for a given solution.
"""
from __future__ import annotations

import math
import numpy as np

from app.models.solution import Solution
from app.models.scenario import DroneFleetSpec


def run_monte_carlo(
    solution: Solution,
    fleet: DroneFleetSpec,
    n_iterations: int = 1000,
    alpha: float = 0.02,
    seed: int = 42,
) -> dict:
    """
    For each segment, P(failure) = alpha * (segment_length / max_range).
    Trip succeeds iff all its segments succeed.
    Solution success = successful_deliveries / total_packages.

    Returns:
        {
          "expected_success_rate": float,
          "ci_lower": float,
          "ci_upper": float,
          "std": float,
          "n_iterations": int,
        }
    """
    rng = np.random.default_rng(seed)
    max_range = fleet.max_range_per_trip

    # Collect all segments across all routes
    all_segments: list[tuple[str, str, float]] = []  # (from_id, to_id, length)
    total_deliveries = sum(
        len(trip.sequence)
        for dr in solution.routes
        for trip in dr.trips
    )

    if total_deliveries == 0:
        return {
            "expected_success_rate": 0.0,
            "ci_lower": 0.0,
            "ci_upper": 0.0,
            "std": 0.0,
            "n_iterations": n_iterations,
        }

    # Build trip segment lists for simulation
    trip_records: list[dict] = []  # {pkg_count, segment_failure_probs}
    for dr in solution.routes:
        for trip in dr.trips:
            seg_probs = []
            # trip.distance is total; approximate per-segment using uniform split
            n_segs = len(trip.sequence) + 1  # depot→p1→...→depot
            seg_len = trip.distance / max(n_segs, 1)
            p_fail_per_seg = alpha * (seg_len / max_range)
            seg_probs = [min(p_fail_per_seg, 1.0)] * n_segs
            trip_records.append({
                "pkg_count": len(trip.sequence),
                "seg_probs": seg_probs,
            })

    success_rates = []
    for _ in range(n_iterations):
        delivered = 0
        for record in trip_records:
            probs = record["seg_probs"]
            # All segments must succeed for trip to succeed
            samples = rng.random(len(probs))
            trip_ok = all(s > p for s, p in zip(samples, probs))
            if trip_ok:
                delivered += record["pkg_count"]
        success_rates.append(delivered / total_deliveries)

    arr = np.array(success_rates)
    mean = float(np.mean(arr))
    std = float(np.std(arr))
    # 95% CI (normal approximation)
    margin = 1.96 * std / math.sqrt(n_iterations)

    return {
        "expected_success_rate": round(mean, 4),
        "ci_lower": round(max(0.0, mean - margin), 4),
        "ci_upper": round(min(1.0, mean + margin), 4),
        "std": round(std, 4),
        "n_iterations": n_iterations,
    }
