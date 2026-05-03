"""
Baseline Algorithms — Section 5.4 of PRD.
Random Assignment and Nearest Neighbor heuristic.
"""
from __future__ import annotations

import random
import time
from copy import deepcopy

from app.models.scenario import Scenario
from app.models.solution import Solution, DroneRoute, Trip
from app.models.ga_config import FitnessWeights
from app.core.genetic_algorithm import (
    decode_chromosome, random_chromosome, nn_chromosome,
    compute_fitness, _dist, _build_solution, DEPOT
)


def run_random_assignment(
    scenario: Scenario,
    dist_matrix: dict,
    weights: FitnessWeights,
    seed: int = 42,
) -> Solution:
    random.seed(seed)
    pkg_ids = [dp.id for dp in scenario.delivery_points]
    n_drones = scenario.drone_fleet.count

    start = time.time()
    chromosome = random_chromosome(pkg_ids, n_drones)
    solution = decode_chromosome(chromosome, scenario, dist_matrix)
    solution.algorithm = "random"
    solution.fitness = compute_fitness(solution, weights)
    solution.metadata = {
        "compute_time_seconds": round(time.time() - start, 4),
        "seed": seed,
    }
    return solution


def run_nearest_neighbor(
    scenario: Scenario,
    dist_matrix: dict,
    weights: FitnessWeights,
) -> Solution:
    """
    Full NN heuristic as per PRD §5.4.2:
    For each drone: from depot, greedily pick nearest feasible unassigned package.
    """
    fleet = scenario.drone_fleet
    delivery_map = {dp.id: dp for dp in scenario.delivery_points}
    pkg_ids = set(delivery_map.keys())
    n_drones = fleet.count

    start = time.time()

    routes_data: list[list[list[str]]] = [[] for _ in range(n_drones)]  # drone → trips
    assigned: set[str] = set()

    # Each drone greedily fills trips
    for drone_idx in range(n_drones):
        current = DEPOT
        current_load = 0.0
        range_used = 0.0
        current_trip: list[str] = []

        while True:
            # Find nearest feasible unassigned
            candidates = [
                p for p in pkg_ids
                if p not in assigned
            ]
            if not candidates:
                break

            best_next = None
            best_dist = float("inf")
            for p in candidates:
                pkg = delivery_map[p]
                d_to = _dist(dist_matrix, current, p)
                d_home = _dist(dist_matrix, p, DEPOT)

                load_ok = current_load + pkg.weight_kg <= fleet.max_payload_kg
                range_ok = range_used + d_to + d_home <= fleet.max_range_per_trip

                if load_ok and range_ok and d_to < best_dist:
                    best_dist = d_to
                    best_next = p

            if best_next is None:
                # Can't extend trip — close it and start new if packages remain
                if current_trip:
                    routes_data[drone_idx].append(current_trip)
                current_trip = []
                current_load = 0.0
                range_used = 0.0
                current = DEPOT

                # Check if we can serve anything from depot
                can_serve_any = any(
                    _dist(dist_matrix, DEPOT, p) + _dist(dist_matrix, p, DEPOT)
                    <= fleet.max_range_per_trip
                    for p in pkg_ids if p not in assigned
                )
                if not can_serve_any:
                    break
                continue

            pkg = delivery_map[best_next]
            d_to = _dist(dist_matrix, current, best_next)
            range_used += d_to
            current_load += pkg.weight_kg
            current_trip.append(best_next)
            assigned.add(best_next)
            current = best_next

        if current_trip:
            routes_data[drone_idx].append(current_trip)

    # Build chromosome-like structure for decode
    chromosome = [
        [p for trip in trips for p in trip]
        for trips in routes_data
    ]
    solution = decode_chromosome(chromosome, scenario, dist_matrix)
    solution.algorithm = "nearest_neighbor"
    solution.fitness = compute_fitness(solution, weights)
    solution.metadata = {
        "compute_time_seconds": round(time.time() - start, 4),
    }
    return solution
