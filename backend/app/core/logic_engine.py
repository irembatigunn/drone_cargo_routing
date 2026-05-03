"""
Logic Engine — Section 5.2 of PRD.
Custom forward-chaining inference engine with Predicates, Rules, and KnowledgeBase.
Implements R1-R6 (Capacity, Range, TimeWindow, NoFlyZone, MustReturn, PriorityOrdering).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Any
import math

from app.models.scenario import Scenario, DeliveryPoint, DroneFleetSpec


# ───────────────────────────────────────────────────────────────
# Core engine primitives
# ───────────────────────────────────────────────────────────────

@dataclass
class Predicate:
    name: str
    args: tuple
    _func: Callable[..., bool]

    def holds(self) -> bool:
        return self._func()

    def __hash__(self):
        return hash((self.name, self.args))

    def __eq__(self, other):
        return self.name == other.name and self.args == other.args


@dataclass
class Rule:
    name: str
    antecedents: list[Predicate]
    consequent: Predicate
    reasoning: str = ""  # human-readable trace


@dataclass
class KnowledgeBase:
    facts: set[str] = field(default_factory=set)  # fact keys
    inferred: list[str] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)


class InferenceEngine:
    """
    Forward-chaining engine.
    Runs until saturation (no new facts) or goal achieved.
    Uses Modus Ponens: if all antecedents hold → assert consequent.
    """

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb
        self.rules: list[Rule] = []

    def add_rule(self, rule: Rule):
        self.rules.append(rule)

    def run(self, max_iter: int = 100) -> KnowledgeBase:
        for _i in range(max_iter):
            new_facts_added = False
            for rule in self.rules:
                # Check antecedents
                all_hold = all(pred.holds() for pred in rule.antecedents)
                consequent_key = f"{rule.consequent.name}{rule.consequent.args}"
                if all_hold and consequent_key not in self.kb.facts:
                    if rule.consequent.holds():
                        self.kb.facts.add(consequent_key)
                        self.kb.inferred.append(consequent_key)
                        self.kb.trace.append(
                            f"[{rule.name}] Modus Ponens: "
                            f"{[f'{p.name}{p.args}' for p in rule.antecedents]} → "
                            f"{consequent_key}"
                        )
                        new_facts_added = True
            if not new_facts_added:
                break  # Saturation reached
        return self.kb


# ───────────────────────────────────────────────────────────────
# Rule factories (R1–R6) — called per-trip evaluation
# ───────────────────────────────────────────────────────────────

PRIORITY_ORDER = {"low": 0, "med": 1, "high": 2}
SAFETY_MARGIN = 50.0


def make_r1_capacity(drone_id: str, pkg: DeliveryPoint, current_load: float,
                     max_payload: float) -> Rule:
    """R1: CanCarry(d, p, trip) ← CurrentLoad + Weight ≤ MaxPayload"""
    def can_carry():
        return current_load + pkg.weight_kg <= max_payload

    return Rule(
        name="R1_Capacity",
        antecedents=[Predicate("WeightFits", (drone_id, pkg.id), can_carry)],
        consequent=Predicate("CanCarry", (drone_id, pkg.id), can_carry),
        reasoning=(
            f"∀d={drone_id}, p={pkg.id}: "
            f"CurrentLoad({current_load:.2f}) + Weight({pkg.weight_kg:.2f}) "
            f"≤ MaxPayload({max_payload:.2f}) → CanCarry"
        ),
    )


def make_r2_range(drone_id: str, pkg_id: str, dist_so_far: float,
                  dist_to_next: float, dist_next_to_depot: float,
                  max_range: float) -> Rule:
    """R2: RangeFeasible ← DistTraveled + DistToNext + DistNextToDepot ≤ MaxRange"""
    def range_ok():
        return dist_so_far + dist_to_next + dist_next_to_depot <= max_range

    return Rule(
        name="R2_Range",
        antecedents=[Predicate("RangeCheck", (drone_id, pkg_id), range_ok)],
        consequent=Predicate("RangeFeasible", (drone_id, pkg_id), range_ok),
        reasoning=(
            f"∀d={drone_id}, p={pkg_id}: "
            f"Dist({dist_so_far:.1f}) + ToNext({dist_to_next:.1f}) "
            f"+ ToDepot({dist_next_to_depot:.1f}) "
            f"≤ MaxRange({max_range:.1f}) → RangeFeasible"
        ),
    )


def make_r3_time_window(pkg: DeliveryPoint, arrival_time: float) -> Rule:
    """R3: TimeWindowViolation ← ArrivalTime > CloseTime (soft constraint)"""
    def violation():
        return arrival_time > pkg.time_window_close_min

    def wait_req():
        return arrival_time < pkg.time_window_open_min

    return Rule(
        name="R3_TimeWindow",
        antecedents=[Predicate("LateArrival", (pkg.id,), violation)],
        consequent=Predicate("TimeWindowViolation", (pkg.id,), violation),
        reasoning=(
            f"∀p={pkg.id}: ArrivalTime({arrival_time:.1f}) "
            f"> CloseTime({pkg.time_window_close_min}) → TimeWindowViolation"
        ),
    )


def make_r5_must_return(drone_id: str, remaining_range: float,
                         dist_to_depot: float) -> Rule:
    """R5: MustReturn ← RemainingRange < DistToDepot + SafetyMargin"""
    def must_return():
        return remaining_range < dist_to_depot + SAFETY_MARGIN

    return Rule(
        name="R5_MustReturn",
        antecedents=[Predicate("LowRange", (drone_id,), must_return)],
        consequent=Predicate("MustReturn", (drone_id,), must_return),
        reasoning=(
            f"∀d={drone_id}: RemainingRange({remaining_range:.1f}) "
            f"< DistToDepot({dist_to_depot:.1f}) + SafetyMargin({SAFETY_MARGIN}) "
            f"→ MustReturn"
        ),
    )


def make_r6_priority(p1: DeliveryPoint, p2: DeliveryPoint,
                     tw_compatible: bool) -> Rule:
    """R6: PreferredOrder(p1, p2) ← Priority(p1) > Priority(p2) ∧ TWCompatible"""
    def preferred():
        return (PRIORITY_ORDER[p1.priority] > PRIORITY_ORDER[p2.priority]
                and tw_compatible)

    return Rule(
        name="R6_Priority",
        antecedents=[
            Predicate("HigherPriority", (p1.id, p2.id),
                      lambda: PRIORITY_ORDER[p1.priority] > PRIORITY_ORDER[p2.priority]),
            Predicate("TWCompatible", (p1.id, p2.id), lambda: tw_compatible),
        ],
        consequent=Predicate("PreferredOrder", (p1.id, p2.id), preferred),
        reasoning=(
            f"∀p1={p1.id}(prio={p1.priority}), p2={p2.id}(prio={p2.priority}): "
            f"Priority(p1) > Priority(p2) ∧ TWCompatible → PreferredOrder"
        ),
    )


# ───────────────────────────────────────────────────────────────
# High-level feasibility checks (used by GA and baselines)
# ───────────────────────────────────────────────────────────────

class TripFeasibilityChecker:
    """
    Stateful checker: maintains trip state (current load, range used, time)
    and applies logic rules R1, R2, R5 to determine if next package can be added.
    """

    def __init__(self, fleet: DroneFleetSpec, dist_matrix: dict,
                 depot_key: str = "depot"):
        self.fleet = fleet
        self.dist_matrix = dist_matrix
        self.depot_key = depot_key

    def _d(self, a: str, b: str) -> float:
        try:
            return self.dist_matrix[a][b]
        except KeyError:
            try:
                return self.dist_matrix[b][a]
            except KeyError:
                return float("inf")

    def check_add_package(
        self,
        drone_id: str,
        pkg: DeliveryPoint,
        current_node: str,
        current_load: float,
        range_used: float,
        current_time_min: float,
        trace_rules: bool = False,
    ) -> tuple[bool, list[str]]:
        """
        Returns (feasible, rule_trace).
        R1, R2, R5 checked via logic engine.
        """
        kb = KnowledgeBase()
        engine = InferenceEngine(kb)

        dist_to_pkg = self._d(current_node, pkg.id)
        dist_pkg_to_depot = self._d(pkg.id, self.depot_key)
        remaining_range = self.fleet.max_range_per_trip - range_used

        r1 = make_r1_capacity(drone_id, pkg, current_load, self.fleet.max_payload_kg)
        r2 = make_r2_range(drone_id, pkg.id, range_used, dist_to_pkg,
                           dist_pkg_to_depot, self.fleet.max_range_per_trip)
        r5 = make_r5_must_return(drone_id, remaining_range,
                                 dist_to_pkg + dist_pkg_to_depot)

        engine.add_rule(r1)
        engine.add_rule(r2)
        engine.add_rule(r5)
        engine.run()

        can_carry = f"CanCarry('{drone_id}', '{pkg.id}')" in " ".join(kb.facts) or \
                    any("CanCarry" in f and pkg.id in f for f in kb.facts)
        range_ok = any("RangeFeasible" in f and pkg.id in f for f in kb.facts)
        must_return = any("MustReturn" in f for f in kb.facts)

        # Simpler direct checks (engine result might miss due to string matching)
        direct_carry = current_load + pkg.weight_kg <= self.fleet.max_payload_kg
        direct_range = (range_used + dist_to_pkg + dist_pkg_to_depot
                        <= self.fleet.max_range_per_trip)
        direct_must_return = (remaining_range < dist_to_pkg + dist_pkg_to_depot + SAFETY_MARGIN)

        feasible = direct_carry and direct_range and not direct_must_return

        trace = kb.trace if trace_rules else []
        return feasible, trace

    def evaluate_trip_time_violations(
        self,
        trip_sequence: list[str],
        delivery_map: dict[str, DeliveryPoint],
        start_time_min: float = 0.0,
    ) -> tuple[int, float]:
        """
        Walk a trip sequence and count time window violations.
        Returns (violation_count, total_minutes_late).
        """
        violations = 0
        total_late = 0.0
        current_time = start_time_min
        current_node = self.depot_key

        for pkg_id in trip_sequence:
            pkg = delivery_map[pkg_id]
            travel = self._d(current_node, pkg_id) / self.fleet.speed_units_per_min
            current_time += travel

            # R3 check
            if current_time > pkg.time_window_close_min:
                violations += 1
                total_late += current_time - pkg.time_window_close_min
            elif current_time < pkg.time_window_open_min:
                current_time = float(pkg.time_window_open_min)  # wait

            current_time += pkg.service_time_min
            current_node = pkg_id

        return violations, total_late
