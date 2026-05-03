"""
GA Operators — Section 5.3 (operators sub-section) of PRD.
BCRC crossover, swap/relocate/2-opt mutation, tournament selection.
"""
from __future__ import annotations

import random
import math
from copy import deepcopy


Chromosome = list[list[str]]  # outer = drones, inner = package sequence


# ───────────────────────────────────────────────────────────────
# Selection
# ───────────────────────────────────────────────────────────────

def tournament_select(population: list[Chromosome], fitnesses: list[float],
                      k: int = 3) -> Chromosome:
    """Tournament selection — picks lowest fitness (minimization)."""
    indices = random.sample(range(len(population)), min(k, len(population)))
    best = min(indices, key=lambda i: fitnesses[i])
    return deepcopy(population[best])


# ───────────────────────────────────────────────────────────────
# Crossover: Best Cost Route Crossover (BCRC)
# ───────────────────────────────────────────────────────────────

def bcrc_crossover(
    parent_a: Chromosome,
    parent_b: Chromosome,
    dist_func,  # callable(a_id, b_id) -> float
) -> tuple[Chromosome, Chromosome]:
    """
    Best Cost Route Crossover (BCRC).
    1. Select a random route from each parent.
    2. Remove those packages from the other parent.
    3. Reinsert using best-insertion (minimum marginal cost).
    """
    if not parent_a or not parent_b:
        return deepcopy(parent_a), deepcopy(parent_b)

    child_a = _bcrc_one(parent_a, parent_b, dist_func)
    child_b = _bcrc_one(parent_b, parent_a, dist_func)
    return child_a, child_b


def _bcrc_one(receiver: Chromosome, donor: Chromosome, dist_func) -> Chromosome:
    """Remove donor route's packages from receiver, reinsert with best insertion."""
    if not donor or all(len(r) == 0 for r in donor):
        return deepcopy(receiver)

    # Pick a non-empty route from donor
    non_empty = [r for r in donor if r]
    if not non_empty:
        return deepcopy(receiver)
    donor_route = random.choice(non_empty)

    # Remove those packages from receiver
    child = deepcopy(receiver)
    removed = set(donor_route)
    for route in child:
        route[:] = [p for p in route if p not in removed]

    # Best insertion for each removed package
    for pkg in donor_route:
        best_cost = float("inf")
        best_route_i = 0
        best_pos = 0

        for ri, route in enumerate(child):
            for pos in range(len(route) + 1):
                cost = _insertion_cost(route, pos, pkg, dist_func)
                if cost < best_cost:
                    best_cost = cost
                    best_route_i = ri
                    best_pos = pos

        child[best_route_i].insert(best_pos, pkg)

    return child


def _insertion_cost(route: list[str], pos: int, pkg: str, dist_func) -> float:
    """Marginal distance cost of inserting pkg at position pos in route."""
    DEPOT = "depot"
    if not route:
        # Route: depot → pkg → depot
        return dist_func(DEPOT, pkg) + dist_func(pkg, DEPOT)

    prev = DEPOT if pos == 0 else route[pos - 1]
    nxt = DEPOT if pos == len(route) else route[pos]

    old_cost = dist_func(prev, nxt)
    new_cost = dist_func(prev, pkg) + dist_func(pkg, nxt)
    return new_cost - old_cost


# ───────────────────────────────────────────────────────────────
# Mutation operators
# ───────────────────────────────────────────────────────────────

def swap_mutation(chromosome: Chromosome) -> Chromosome:
    """Intra-route swap: two random packages within same route swap positions."""
    c = deepcopy(chromosome)
    eligible = [i for i, route in enumerate(c) if len(route) >= 2]
    if not eligible:
        return c
    ri = random.choice(eligible)
    i, j = random.sample(range(len(c[ri])), 2)
    c[ri][i], c[ri][j] = c[ri][j], c[ri][i]
    return c


def relocate_mutation(chromosome: Chromosome) -> Chromosome:
    """Inter-route relocate: move one package from one route to another."""
    c = deepcopy(chromosome)
    non_empty = [i for i, route in enumerate(c) if route]
    if len(non_empty) < 1:
        return c

    src_i = random.choice(non_empty)
    if not c[src_i]:
        return c

    pkg_pos = random.randrange(len(c[src_i]))
    pkg = c[src_i].pop(pkg_pos)

    # Destination route (can be different or same)
    dst_i = random.randrange(len(c))
    insert_pos = random.randint(0, len(c[dst_i]))
    c[dst_i].insert(insert_pos, pkg)
    return c


def two_opt_mutation(chromosome: Chromosome) -> Chromosome:
    """2-opt intra-route: reverse a segment within a random route."""
    c = deepcopy(chromosome)
    eligible = [i for i, route in enumerate(c) if len(route) >= 3]
    if not eligible:
        return c
    ri = random.choice(eligible)
    route = c[ri]
    n = len(route)
    i = random.randint(0, n - 2)
    j = random.randint(i + 1, n - 1)
    route[i:j + 1] = route[i:j + 1][::-1]
    return c


def apply_mutation(chromosome: Chromosome,
                   mutation_rate: float = 0.15,
                   swap_prob: float = 0.3,
                   relocate_prob: float = 0.4,
                   two_opt_prob: float = 0.3) -> Chromosome:
    """Apply mutation operators based on probabilities."""
    if random.random() > mutation_rate:
        return chromosome

    c = chromosome
    r = random.random()
    if r < swap_prob:
        c = swap_mutation(c)
    elif r < swap_prob + relocate_prob:
        c = relocate_mutation(c)
    else:
        c = two_opt_mutation(c)
    return c
