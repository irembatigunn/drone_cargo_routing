"""
Evaluation & Metrics — Section 5.7 of PRD.
Solution-level and algorithm-level metrics.
"""
from __future__ import annotations

import time
import numpy as np

from app.models.solution import Solution
from app.models.scenario import Scenario
from app.models.ga_config import GAConfig, FitnessWeights
from app.core.genetic_algorithm import run_ga, decode_chromosome, compute_fitness


def evaluate_solution(solution: Solution) -> dict:
    """Return solution-level metric dict."""
    return {
        "total_distance": solution.total_distance,
        "total_time_min": solution.total_time_min,
        "time_window_violations": solution.time_window_violations,
        "unassigned_packages": len(solution.unassigned_packages),
        "capacity_violations": solution.capacity_violations,
        "fitness": solution.fitness,
        "algorithm": solution.algorithm,
        "compute_time_seconds": solution.metadata.get("compute_time_seconds", 0),
    }


def compare_solutions(solutions: dict[str, Solution]) -> dict:
    """
    Build comparison dict for Random, NN, GA.
    """
    result = {}
    random_dist = None
    for algo, sol in solutions.items():
        result[algo] = evaluate_solution(sol)
        if algo == "random":
            random_dist = sol.total_distance

    # improvement_over_random
    if random_dist and random_dist > 0:
        for algo in result:
            dist = result[algo]["total_distance"]
            result[algo]["improvement_over_random_pct"] = round(
                (random_dist - dist) / random_dist * 100, 2
            )
    return result


def run_ga_batch(
    scenario: Scenario,
    dist_matrix: dict,
    config: GAConfig,
    weights: FitnessWeights,
    n_runs: int = 30,
) -> dict:
    """
    Run GA n_runs times with different seeds, return statistics.
    """
    distances = []
    times = []
    violations = []
    fitnesses = []
    conv_gens = []

    for run_i in range(n_runs):
        run_config = config.model_copy()
        run_config.seed = config.seed + run_i * 7  # different seeds

        final_solution = None
        for msg in run_ga(scenario, dist_matrix, run_config, weights):
            if msg["type"] == "complete":
                final_solution = msg["final_solution"]
                conv_gens.append(msg.get("convergence_generation", config.generations))
                break

        if final_solution:
            distances.append(final_solution.total_distance)
            times.append(final_solution.total_time_min)
            violations.append(final_solution.time_window_violations)
            fitnesses.append(final_solution.fitness)

    def stats(arr):
        a = np.array(arr)
        return {"mean": round(float(np.mean(a)), 2), "std": round(float(np.std(a)), 2)}

    return {
        "n_runs": n_runs,
        "total_distance": stats(distances),
        "total_time_min": stats(times),
        "time_window_violations": stats(violations),
        "fitness": stats(fitnesses),
        "convergence_generation": stats(conv_gens),
    }
