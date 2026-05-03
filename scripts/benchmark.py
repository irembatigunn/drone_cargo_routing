#!/usr/bin/env python3
"""
30-run GA benchmark across all 3 presets.
Run: python scripts/benchmark.py
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.core.data_generator import generate_preset
from app.core.visibility_graph import build_visibility_graph_and_matrix
from app.core.evaluation import run_ga_batch, compare_solutions
from app.core.baseline_algorithms import run_random_assignment, run_nearest_neighbor
from app.models.ga_config import GAConfig, FitnessWeights

def run_benchmark():
    weights = FitnessWeights()
    results = {}

    for preset in ["small", "medium", "large"]:
        print(f"\n{'='*50}")
        print(f"Preset: {preset.upper()}")
        print(f"{'='*50}")

        scenario = generate_preset(preset)
        print(f"  {len(scenario.delivery_points)} pkgs, {len(scenario.no_fly_zones)} zones, {scenario.drone_fleet.count} drones")

        gd = build_visibility_graph_and_matrix(scenario)
        dm = gd["distance_matrix"]

        rand_sol = run_random_assignment(scenario, dm, weights)
        nn_sol = run_nearest_neighbor(scenario, dm, weights)

        print(f"  Random: dist={rand_sol.total_distance:.1f}, unassigned={len(rand_sol.unassigned_packages)}")
        print(f"  NN:     dist={nn_sol.total_distance:.1f}, unassigned={len(nn_sol.unassigned_packages)}")

        print(f"  Running 30-run GA batch...")
        cfg = GAConfig(generations=200, population_size=50, seed=42)
        ga_stats = run_ga_batch(scenario, dm, cfg, weights, n_runs=30)

        print(f"  GA dist: {ga_stats['total_distance']['mean']:.1f} ± {ga_stats['total_distance']['std']:.1f}")
        print(f"  GA conv: gen {ga_stats['convergence_generation']['mean']:.0f} ± {ga_stats['convergence_generation']['std']:.0f}")
        print(f"  GA TW violations: {ga_stats['time_window_violations']['mean']:.2f} ± {ga_stats['time_window_violations']['std']:.2f}")

        improvement = (rand_sol.total_distance - ga_stats["total_distance"]["mean"]) / rand_sol.total_distance * 100
        print(f"  GA improvement over Random: {improvement:.1f}%")

        results[preset] = {
            "random": {"distance": rand_sol.total_distance, "unassigned": len(rand_sol.unassigned_packages)},
            "nn": {"distance": nn_sol.total_distance, "unassigned": len(nn_sol.unassigned_packages)},
            "ga": ga_stats,
        }

    out = Path(__file__).parent.parent / "docs" / "benchmark_results.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print(f"\n✓ Results saved to {out}")

if __name__ == "__main__":
    run_benchmark()
