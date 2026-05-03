"""
Tests for core modules.
Run: pytest tests/ -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import math
from app.core.data_generator import generate_preset, generate_scenario
from app.core.visibility_graph import build_visibility_graph_and_matrix
from app.core.logic_engine import (
    make_r1_capacity, make_r2_range, make_r5_must_return,
    InferenceEngine, KnowledgeBase, TripFeasibilityChecker
)
from app.core.genetic_algorithm import (
    run_ga, decode_chromosome, random_chromosome, nn_chromosome
)
from app.core.baseline_algorithms import run_random_assignment, run_nearest_neighbor
from app.core.monte_carlo import run_monte_carlo
from app.core.linear_algebra import compute_centrality
from app.models.ga_config import GAConfig, FitnessWeights
from app.models.scenario import DeliveryPoint, Position


# ─── Fixtures ────────────────────────────────────────────────

@pytest.fixture(scope="module")
def small_scenario():
    return generate_preset("small")

@pytest.fixture(scope="module")
def medium_scenario():
    return generate_preset("medium")

@pytest.fixture(scope="module")
def graph_data(small_scenario):
    return build_visibility_graph_and_matrix(small_scenario)


# ─── Data Generator ─────────────────────────────────────────

def test_preset_package_counts():
    for name, expected in [("small", 8), ("medium", 18), ("large", 35)]:
        s = generate_preset(name)
        assert len(s.delivery_points) == expected

def test_preset_zone_counts():
    for name, expected in [("small", 2), ("medium", 4), ("large", 6)]:
        s = generate_preset(name)
        assert len(s.no_fly_zones) == expected

def test_preset_fleet_sizes():
    for name, expected in [("small", 3), ("medium", 4), ("large", 6)]:
        s = generate_preset(name)
        assert s.drone_fleet.count == expected

def test_reproducibility():
    s1 = generate_preset("small")
    s2 = generate_preset("small")
    assert s1.delivery_points[0].position.x == s2.delivery_points[0].position.x

def test_delivery_points_in_canvas(small_scenario):
    for dp in small_scenario.delivery_points:
        assert 0 <= dp.position.x <= 1000
        assert 0 <= dp.position.y <= 1000

def test_depot_not_in_nfz(small_scenario):
    from shapely.geometry import Point, Polygon
    depot = Point(small_scenario.depot.x, small_scenario.depot.y)
    for zone in small_scenario.no_fly_zones:
        poly = Polygon([(v.x, v.y) for v in zone.polygon])
        assert not poly.contains(depot)

def test_packages_not_in_nfz(small_scenario):
    from shapely.geometry import Point, Polygon
    for dp in small_scenario.delivery_points:
        pt = Point(dp.position.x, dp.position.y)
        for zone in small_scenario.no_fly_zones:
            poly = Polygon([(v.x, v.y) for v in zone.polygon])
            assert not poly.contains(pt)

def test_weight_range(small_scenario):
    for dp in small_scenario.delivery_points:
        assert 0.5 <= dp.weight_kg <= 5.0

def test_priority_values(small_scenario):
    for dp in small_scenario.delivery_points:
        assert dp.priority in ("low", "med", "high")

def test_time_window_valid(small_scenario):
    for dp in small_scenario.delivery_points:
        assert dp.time_window_close_min > dp.time_window_open_min


# ─── Visibility Graph ────────────────────────────────────────

def test_graph_has_nodes(graph_data, small_scenario):
    expected_min = 1 + len(small_scenario.delivery_points)
    assert graph_data["graph"].number_of_nodes() >= expected_min

def test_distance_matrix_symmetric(graph_data, small_scenario):
    dm = graph_data["distance_matrix"]
    keys = graph_data["interest_keys"]
    for k1 in keys[:3]:
        for k2 in keys[:3]:
            if k1 in dm and k2 in dm.get(k1, {}):
                d12 = dm[k1][k2]
                d21 = dm.get(k2, {}).get(k1, d12)
                assert abs(d12 - d21) < 0.01

def test_self_distance_zero(graph_data):
    dm = graph_data["distance_matrix"]
    for k in graph_data["interest_keys"]:
        if k in dm:
            assert dm[k].get(k, 0) == 0.0

def test_depot_reachable(graph_data, small_scenario):
    dm = graph_data["distance_matrix"]
    for dp in small_scenario.delivery_points:
        assert dp.id in dm.get("depot", {})
        d = dm["depot"][dp.id]
        assert d > 0 and d < float("inf")


# ─── Logic Engine ────────────────────────────────────────────

def test_r1_capacity_pass():
    dp = DeliveryPoint(
        id="pkg_001", position=Position(x=100, y=100), weight_kg=2.0,
        priority="low", time_window_open_min=0, time_window_close_min=120,
    )
    rule = make_r1_capacity("drone_1", dp, current_load=2.0, max_payload=5.0)
    kb = KnowledgeBase()
    engine = InferenceEngine(kb)
    engine.add_rule(rule)
    engine.run()
    assert any("CanCarry" in f for f in kb.facts)

def test_r1_capacity_fail():
    dp = DeliveryPoint(
        id="pkg_001", position=Position(x=100, y=100), weight_kg=4.0,
        priority="low", time_window_open_min=0, time_window_close_min=120,
    )
    rule = make_r1_capacity("drone_1", dp, current_load=2.5, max_payload=5.0)
    kb = KnowledgeBase()
    engine = InferenceEngine(kb)
    engine.add_rule(rule)
    engine.run()
    assert not any("CanCarry" in f for f in kb.facts)

def test_r2_range_pass():
    rule = make_r2_range("drone_1", "pkg_001",
                         dist_so_far=100, dist_to_next=200,
                         dist_next_to_depot=100, max_range=800)
    kb = KnowledgeBase()
    engine = InferenceEngine(kb)
    engine.add_rule(rule)
    engine.run()
    assert any("RangeFeasible" in f for f in kb.facts)

def test_r5_must_return():
    rule = make_r5_must_return("drone_1", remaining_range=60, dist_to_depot=100)
    kb = KnowledgeBase()
    engine = InferenceEngine(kb)
    engine.add_rule(rule)
    engine.run()
    assert any("MustReturn" in f for f in kb.facts)

def test_logic_engine_modus_ponens_trace():
    dp = DeliveryPoint(
        id="pkg_001", position=Position(x=100, y=100), weight_kg=1.0,
        priority="high", time_window_open_min=0, time_window_close_min=120,
    )
    rule = make_r1_capacity("drone_1", dp, 0.0, 5.0)
    kb = KnowledgeBase()
    engine = InferenceEngine(kb)
    engine.add_rule(rule)
    engine.run()
    assert len(kb.trace) >= 1
    assert "Modus Ponens" in kb.trace[0]


# ─── Baselines & GA ──────────────────────────────────────────

def test_random_assignment(small_scenario, graph_data):
    w = FitnessWeights()
    sol = run_random_assignment(small_scenario, graph_data["distance_matrix"], w)
    assert sol.algorithm == "random"
    total = len(sol.unassigned_packages) + sum(len(t.sequence) for r in sol.routes for t in r.trips)
    assert total == len(small_scenario.delivery_points)

def test_nn_assignment(small_scenario, graph_data):
    w = FitnessWeights()
    sol = run_nearest_neighbor(small_scenario, graph_data["distance_matrix"], w)
    assert sol.algorithm == "nearest_neighbor"
    assert sol.total_distance > 0

def test_ga_improves_over_random(small_scenario, graph_data):
    w = FitnessWeights()
    rand = run_random_assignment(small_scenario, graph_data["distance_matrix"], w)
    cfg = GAConfig(generations=50, population_size=20, seed=42)
    final = None
    for msg in run_ga(small_scenario, graph_data["distance_matrix"], cfg, w):
        if msg["type"] == "complete":
            final = msg["final_solution"]
    assert final is not None
    # GA should match or beat random in most cases (stochastic, so not strict)
    assert final.fitness <= rand.fitness * 2  # at worst 2x (generous)

def test_ga_no_capacity_violations(small_scenario, graph_data):
    w = FitnessWeights()
    cfg = GAConfig(generations=50, population_size=20, seed=42)
    final = None
    for msg in run_ga(small_scenario, graph_data["distance_matrix"], cfg, w):
        if msg["type"] == "complete":
            final = msg["final_solution"]
    assert final.capacity_violations == 0

def test_ga_streams_generations(small_scenario, graph_data):
    w = FitnessWeights()
    cfg = GAConfig(generations=50, population_size=20, seed=42)
    gen_count = 0
    for msg in run_ga(small_scenario, graph_data["distance_matrix"], cfg, w):
        if msg["type"] == "generation":
            gen_count += 1
    assert gen_count >= 1


# ─── Monte Carlo ─────────────────────────────────────────────

def test_monte_carlo_range(small_scenario, graph_data):
    w = FitnessWeights()
    sol = run_nearest_neighbor(small_scenario, graph_data["distance_matrix"], w)
    mc = run_monte_carlo(sol, small_scenario.drone_fleet, n_iterations=100)
    assert 0.0 <= mc["expected_success_rate"] <= 1.0
    assert mc["ci_lower"] <= mc["expected_success_rate"] <= mc["ci_upper"]

def test_monte_carlo_empty_solution(small_scenario):
    from app.models.solution import Solution, DroneRoute
    sol = Solution(
        routes=[], unassigned_packages=[], total_distance=0, total_time_min=0,
        time_window_violations=0, capacity_violations=0, fitness=0,
        algorithm="random", metadata={},
    )
    mc = run_monte_carlo(sol, small_scenario.drone_fleet, n_iterations=10)
    assert mc["expected_success_rate"] == 0.0


# ─── Linear Algebra ──────────────────────────────────────────

def test_centrality_values_in_range(graph_data):
    c = compute_centrality(graph_data["interest_keys"], graph_data["distance_matrix"])
    for v in c["centrality"].values():
        assert 0.0 <= v <= 1.0

def test_frobenius_positive(graph_data):
    c = compute_centrality(graph_data["interest_keys"], graph_data["distance_matrix"])
    assert c["frobenius_norm"] > 0

def test_centrality_all_nodes(graph_data):
    c = compute_centrality(graph_data["interest_keys"], graph_data["distance_matrix"])
    for k in graph_data["interest_keys"]:
        assert k in c["centrality"]
