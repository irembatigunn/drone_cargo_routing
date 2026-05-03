"""
Genetic Algorithm — Section 5.3 of PRD.
Full GA with BCRC crossover, 3 mutation operators, repair, elitism.
Yields (generation_idx, best_fitness, mean_fitness, best_chromosome) per generation.
"""
from __future__ import annotations

import random
import math
import time
from copy import deepcopy
from typing import Generator

import numpy as np

from app.models.scenario import Scenario, DeliveryPoint, DroneFleetSpec
from app.models.ga_config import GAConfig, FitnessWeights
from app.models.solution import Solution, DroneRoute, Trip
from app.core.ga_operators import (
    tournament_select, bcrc_crossover, apply_mutation
)
from app.core.logic_engine import TripFeasibilityChecker, SAFETY_MARGIN

DEPOT = "depot"


# ───────────────────────────────────────────────────────────────
# Chromosome encode / decode
# ───────────────────────────────────────────────────────────────

def decode_chromosome(
    chromosome: list[list[str]],
    scenario: Scenario,
    dist_matrix: dict,
) -> Solution:
    """
    Decode a chromosome into a Solution.
    Splits per-drone package lists into multi-trips (capacity/range constraints).
    Applies repair: infeasible packages go to unassigned pool then best-insertion.
    """
    fleet = scenario.drone_fleet
    delivery_map = {dp.id: dp for dp in scenario.delivery_points}
    checker = TripFeasibilityChecker(fleet, dist_matrix, DEPOT)

    routes: list[DroneRoute] = []
    unassigned_pool: list[str] = []

    for drone_idx, pkg_sequence in enumerate(chromosome):
        drone_id = f"drone_{drone_idx + 1}"
        trips: list[Trip] = []

        current_trip: list[str] = []
        current_load = 0.0
        range_used = 0.0
        current_node = DEPOT
        current_time = 0.0

        for pkg_id in pkg_sequence:
            if pkg_id not in delivery_map:
                continue
            pkg = delivery_map[pkg_id]
            feasible, _ = checker.check_add_package(
                drone_id, pkg, current_node,
                current_load, range_used, current_time
            )

            if feasible:
                d = _dist(dist_matrix, current_node, pkg_id)
                range_used += d
                current_load += pkg.weight_kg
                current_time += d / fleet.speed_units_per_min + pkg.service_time_min
                current_trip.append(pkg_id)
                current_node = pkg_id
            else:
                # Close current trip if has packages
                if current_trip:
                    trip_dist, trip_dur = _finalize_trip(
                        current_trip, dist_matrix, fleet, DEPOT)
                    trips.append(Trip(
                        sequence=current_trip,
                        distance=trip_dist,
                        duration_min=trip_dur,
                    ))
                    current_trip = []
                    current_load = 0.0
                    range_used = 0.0
                    current_node = DEPOT
                    current_time = sum(t.duration_min for t in trips) + fleet.recharge_time_min * len(trips)

                    # Retry with fresh trip
                    feasible2, _ = checker.check_add_package(
                        drone_id, pkg, current_node,
                        current_load, range_used, current_time
                    )
                    if feasible2:
                        d = _dist(dist_matrix, current_node, pkg_id)
                        range_used += d
                        current_load += pkg.weight_kg
                        current_time += d / fleet.speed_units_per_min + pkg.service_time_min
                        current_trip.append(pkg_id)
                        current_node = pkg_id
                    else:
                        unassigned_pool.append(pkg_id)
                else:
                    unassigned_pool.append(pkg_id)

        if current_trip:
            trip_dist, trip_dur = _finalize_trip(current_trip, dist_matrix, fleet, DEPOT)
            trips.append(Trip(sequence=current_trip, distance=trip_dist, duration_min=trip_dur))

        routes.append(DroneRoute(drone_id=drone_id, trips=trips))

    # Repair: try to insert unassigned packages
    still_unassigned = _repair_unassigned(
        unassigned_pool, routes, scenario, dist_matrix, checker, delivery_map)

    return _build_solution(routes, still_unassigned, scenario, dist_matrix, "ga")


def _repair_unassigned(
    unassigned: list[str],
    routes: list[DroneRoute],
    scenario: Scenario,
    dist_matrix: dict,
    checker: TripFeasibilityChecker,
    delivery_map: dict,
) -> list[str]:
    """Best-insertion repair for unassigned packages."""
    fleet = scenario.drone_fleet
    still_unassigned = []

    for pkg_id in unassigned:
        pkg = delivery_map.get(pkg_id)
        if not pkg:
            still_unassigned.append(pkg_id)
            continue

        best_cost = float("inf")
        best_route_i = -1
        best_trip_i = -1
        best_pos = -1

        for ri, droute in enumerate(routes):
            for ti, trip in enumerate(droute.trips):
                seq = trip.sequence
                for pos in range(len(seq) + 1):
                    prev = DEPOT if pos == 0 else seq[pos - 1]
                    nxt = DEPOT if pos == len(seq) else seq[pos]
                    cost = (_dist(dist_matrix, prev, pkg_id) +
                            _dist(dist_matrix, pkg_id, nxt) -
                            _dist(dist_matrix, prev, nxt))
                    if cost < best_cost:
                        # Quick feasibility check
                        new_load = sum(
                            delivery_map[p].weight_kg
                            for p in seq if p in delivery_map
                        ) + pkg.weight_kg
                        if new_load <= fleet.max_payload_kg:
                            best_cost = cost
                            best_route_i = ri
                            best_trip_i = ti
                            best_pos = pos

        if best_route_i >= 0:
            trip = routes[best_route_i].trips[best_trip_i]
            trip.sequence.insert(best_pos, pkg_id)
            # Recalculate trip metrics
            dist_new, dur_new = _finalize_trip(trip.sequence, dist_matrix, fleet, DEPOT)
            trip.distance = dist_new
            trip.duration_min = dur_new
        else:
            still_unassigned.append(pkg_id)

    return still_unassigned


def _finalize_trip(sequence: list[str], dist_matrix: dict,
                   fleet: DroneFleetSpec, depot: str) -> tuple[float, float]:
    total_dist = 0.0
    current = depot
    for pkg_id in sequence:
        total_dist += _dist(dist_matrix, current, pkg_id)
        current = pkg_id
    total_dist += _dist(dist_matrix, current, depot)
    duration = total_dist / fleet.speed_units_per_min + len(sequence) * 2  # 2 min service time per delivery
    return total_dist, duration


def _dist(dist_matrix: dict, a: str, b: str) -> float:
    if a == b:
        return 0.0
    try:
        return dist_matrix[a][b]
    except KeyError:
        try:
            return dist_matrix[b][a]
        except KeyError:
            return 9999.0


def _build_solution(
    routes: list[DroneRoute],
    unassigned: list[str],
    scenario: Scenario,
    dist_matrix: dict,
    algorithm: str,
) -> Solution:
    fleet = scenario.drone_fleet
    delivery_map = {dp.id: dp for dp in scenario.delivery_points}

    total_dist = sum(trip.distance for dr in routes for trip in dr.trips)
    drone_times = []
    tw_violations = 0

    for dr in routes:
        drone_time = 0.0
        for ti, trip in enumerate(dr.trips):
            if ti > 0:
                drone_time += fleet.recharge_time_min
            current = DEPOT
            t = drone_time
            for pkg_id in trip.sequence:
                pkg = delivery_map.get(pkg_id)
                if not pkg:
                    continue
                travel = _dist(dist_matrix, current, pkg_id) / fleet.speed_units_per_min
                t += travel
                if t > pkg.time_window_close_min:
                    tw_violations += 1
                elif t < pkg.time_window_open_min:
                    t = float(pkg.time_window_open_min)
                t += pkg.service_time_min
                current = pkg_id
            drone_time += trip.duration_min
        drone_times.append(drone_time)

    total_time = max(drone_times) if drone_times else 0.0
    return Solution(
        routes=routes,
        unassigned_packages=unassigned,
        total_distance=round(total_dist, 2),
        total_time_min=round(total_time, 2),
        time_window_violations=tw_violations,
        capacity_violations=0,
        fitness=0.0,
        algorithm=algorithm,
        metadata={},
    )


# ───────────────────────────────────────────────────────────────
# Fitness function
# ───────────────────────────────────────────────────────────────

def compute_fitness(solution: Solution, weights: FitnessWeights) -> float:
    f = (weights.w_distance * solution.total_distance
         + weights.w_time_violation * solution.time_window_violations * weights.penalty_per_violation
         + weights.w_unassigned * len(solution.unassigned_packages) * weights.penalty_per_violation)
    return f


# ───────────────────────────────────────────────────────────────
# Initialization helpers
# ───────────────────────────────────────────────────────────────

def random_chromosome(pkg_ids: list[str], n_drones: int) -> list[list[str]]:
    shuffled = pkg_ids[:]
    random.shuffle(shuffled)
    routes = [[] for _ in range(n_drones)]
    for i, pkg in enumerate(shuffled):
        routes[i % n_drones].append(pkg)
    return routes


def nn_chromosome(pkg_ids: list[str], n_drones: int, dist_matrix: dict) -> list[list[str]]:
    """Nearest-neighbor heuristic to seed GA population."""
    routes = [[] for _ in range(n_drones)]
    unassigned = set(pkg_ids)
    for drone_idx in range(n_drones):
        current = DEPOT
        while unassigned:
            nearest = min(
                unassigned,
                key=lambda p: _dist(dist_matrix, current, p)
            )
            routes[drone_idx].append(nearest)
            unassigned.discard(nearest)
            current = nearest
            if len(routes[drone_idx]) >= max(1, len(pkg_ids) // n_drones + 1):
                break
    # Distribute remaining
    remaining = list(unassigned)
    for i, pkg in enumerate(remaining):
        routes[i % n_drones].append(pkg)
    return routes


# ───────────────────────────────────────────────────────────────
# Main GA generator
# ───────────────────────────────────────────────────────────────

def run_ga(
    scenario: Scenario,
    dist_matrix: dict,
    config: GAConfig,
    weights: FitnessWeights,
) -> Generator[dict, None, Solution]:
    """
    Generator that yields one dict per generation:
      {"type": "generation", "generation": int, "best_fitness": float,
       "mean_fitness": float, "best_solution": Solution}
    Final yield is {"type": "complete", "final_solution": Solution, ...}
    """
    random.seed(config.seed)
    np.random.seed(config.seed)

    start_time = time.time()
    pkg_ids = [dp.id for dp in scenario.delivery_points]
    n_drones = scenario.drone_fleet.count
    P = config.population_size

    # Initialize population
    nn_count = max(1, int(P * config.nn_seed_ratio))
    population = []
    for _ in range(nn_count):
        population.append(nn_chromosome(pkg_ids, n_drones, dist_matrix))
    for _ in range(P - nn_count):
        population.append(random_chromosome(pkg_ids, n_drones))

    def dist_func(a: str, b: str) -> float:
        return _dist(dist_matrix, a, b)

    # Evaluate initial population
    solutions = [decode_chromosome(c, scenario, dist_matrix) for c in population]
    fitnesses = [compute_fitness(s, weights) for s in solutions]
    for i, s in enumerate(solutions):
        s.fitness = fitnesses[i]

    best_gen_fitness = min(fitnesses)
    best_gen_idx = fitnesses.index(best_gen_fitness)
    no_improve_count = 0
    convergence_gen = config.generations

    for gen in range(config.generations):
        new_population = []
        new_fitnesses = []
        new_solutions = []

        # Elitism
        elite_indices = sorted(range(len(fitnesses)), key=lambda i: fitnesses[i])[:config.elitism]
        for idx in elite_indices:
            new_population.append(deepcopy(population[idx]))
            new_solutions.append(solutions[idx])
            new_fitnesses.append(fitnesses[idx])

        # Fill rest with crossover + mutation
        while len(new_population) < P:
            pa = tournament_select(population, fitnesses, config.tournament_size)
            pb = tournament_select(population, fitnesses, config.tournament_size)

            if random.random() < config.crossover_rate:
                ca, cb = bcrc_crossover(pa, pb, dist_func)
            else:
                ca, cb = deepcopy(pa), deepcopy(pb)

            ca = apply_mutation(ca, config.mutation_rate)
            cb = apply_mutation(cb, config.mutation_rate)

            for child in [ca, cb]:
                if len(new_population) >= P:
                    break
                new_population.append(child)
                sol = decode_chromosome(child, scenario, dist_matrix)
                f = compute_fitness(sol, weights)
                sol.fitness = f
                new_solutions.append(sol)
                new_fitnesses.append(f)

        population = new_population
        fitnesses = new_fitnesses
        solutions = new_solutions

        gen_best_f = min(fitnesses)
        gen_mean_f = sum(fitnesses) / len(fitnesses)
        gen_best_idx = fitnesses.index(gen_best_f)

        # Convergence check
        if gen_best_f < best_gen_fitness * (1 - 0.005):
            best_gen_fitness = gen_best_f
            no_improve_count = 0
        else:
            no_improve_count += 1

        if no_improve_count >= config.convergence_patience:
            convergence_gen = gen
            yield {
                "type": "generation",
                "generation": gen,
                "best_fitness": gen_best_f,
                "mean_fitness": gen_mean_f,
                "best_solution": solutions[gen_best_idx],
            }
            break

        yield {
            "type": "generation",
            "generation": gen,
            "best_fitness": gen_best_f,
            "mean_fitness": gen_mean_f,
            "best_solution": solutions[gen_best_idx],
        }

    compute_time = time.time() - start_time
    best_final_idx = fitnesses.index(min(fitnesses))
    final_solution = solutions[best_final_idx]
    final_solution.algorithm = "ga"
    final_solution.metadata = {
        "compute_time_seconds": round(compute_time, 3),
        "convergence_generation": convergence_gen,
        "total_generations": gen + 1,
    }

    yield {
        "type": "complete",
        "final_solution": final_solution,
        "compute_time_seconds": round(compute_time, 3),
        "convergence_generation": convergence_gen,
    }
