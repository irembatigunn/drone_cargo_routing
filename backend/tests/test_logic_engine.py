"""
Logic Engine + R1-R6 Kuralları için Unit Testler

Her test, belirli bir kuralın doğru koşullarda tetiklenip
tetiklenmediğini doğrular.
"""

import pytest
from app.services.logic_engine import Predicate, KnowledgeBase, InferenceEngine
from app.services.rules import (
    R1_CAPACITY, R2_RANGE, R3_TIME_WINDOW, R4_NO_FLY_ZONE,
    R5_MUST_RETURN, R6_PRIORITY, register_all_rules, SAFETY_MARGIN,
)
from app.services.data_generator import generate_scenario
from app.services.distance_matrix import build_distance_matrix


# ---------------------------------------------------------------------------
# Fixtures — testlerin ortak kullandığı veriler
# ---------------------------------------------------------------------------

@pytest.fixture
def scenario():
    """8 paketli, 2 no-fly zone'lu, 3 drone'lu test senaryosu."""
    return generate_scenario("test", 8, 2, 3, 42)


@pytest.fixture
def dist_matrix(scenario):
    result = build_distance_matrix(scenario)
    return result["matrix"]


@pytest.fixture
def kb_with_rules():
    """Tüm kurallar yüklü boş KnowledgeBase."""
    kb = KnowledgeBase()
    register_all_rules(kb)
    return kb


def _setup_base_context(kb, scenario, dist_matrix, pkg_id="pkg_001"):
    """Test için standart context ayarlar."""
    kb.set_context("scenario", scenario)
    kb.set_context("drone_id", "drone_1")
    kb.set_context("trip_id", "trip_1")
    kb.set_context("current_load_kg", 0.0)
    kb.set_context("distance_traveled", 0.0)
    kb.set_context("current_position", "depot")
    kb.set_context("candidate_package_id", pkg_id)
    kb.set_context("distance_matrix", dist_matrix)
    kb.set_context("current_time_min", 0.0)
    kb.set_context("trip_packages", [])


# ---------------------------------------------------------------------------
# Predicate testleri
# ---------------------------------------------------------------------------

class TestPredicate:
    def test_equality(self):
        p1 = Predicate("CanCarry", ("drone_1", "pkg_001"))
        p2 = Predicate("CanCarry", ("drone_1", "pkg_001"))
        assert p1 == p2

    def test_inequality(self):
        p1 = Predicate("CanCarry", ("drone_1", "pkg_001"))
        p2 = Predicate("CanCarry", ("drone_1", "pkg_002"))
        assert p1 != p2

    def test_hashable(self):
        p1 = Predicate("CanCarry", ("drone_1", "pkg_001"))
        p2 = Predicate("CanCarry", ("drone_1", "pkg_001"))
        s = {p1, p2}
        assert len(s) == 1  # Aynı predicate, set'te bir kez

    def test_str(self):
        p = Predicate("CanCarry", ("drone_1", "pkg_001"))
        assert str(p) == "CanCarry(drone_1, pkg_001)"


# ---------------------------------------------------------------------------
# KnowledgeBase testleri
# ---------------------------------------------------------------------------

class TestKnowledgeBase:
    def test_add_fact_new(self):
        kb = KnowledgeBase()
        assert kb.add_fact(Predicate("Test", ("a",))) is True

    def test_add_fact_duplicate(self):
        kb = KnowledgeBase()
        p = Predicate("Test", ("a",))
        kb.add_fact(p)
        assert kb.add_fact(p) is False  # Zaten var

    def test_has_fact(self):
        kb = KnowledgeBase()
        kb.add_fact(Predicate("CanCarry", ("d1", "p1")))
        assert kb.has_fact("CanCarry", ("d1", "p1")) is True
        assert kb.has_fact("CanCarry", ("d1", "p2")) is False

    def test_get_facts_by_name(self):
        kb = KnowledgeBase()
        kb.add_fact(Predicate("CanCarry", ("d1", "p1")))
        kb.add_fact(Predicate("CanCarry", ("d1", "p2")))
        kb.add_fact(Predicate("MustReturn", ("d1",)))
        assert len(kb.get_facts_by_name("CanCarry")) == 2
        assert len(kb.get_facts_by_name("MustReturn")) == 1

    def test_clear_facts(self):
        kb = KnowledgeBase()
        kb.add_fact(Predicate("Test", ()))
        kb.set_context("key", "value")
        kb.clear_facts()
        assert len(kb.facts) == 0
        assert kb.get_context("key") == "value"  # Context kalmalı


# ---------------------------------------------------------------------------
# R1 — Capacity testleri
# ---------------------------------------------------------------------------

class TestR1Capacity:
    def test_can_carry_empty_drone(self, scenario, dist_matrix):
        """Boş drone herhangi bir paketi taşıyabilmeli (max 5kg, paketler 0.5-5kg)."""
        kb = KnowledgeBase()
        kb.add_rule(R1_CAPACITY)
        _setup_base_context(kb, scenario, dist_matrix)

        engine = InferenceEngine(kb)
        new_facts = engine.run()

        can_carry = [f for f in new_facts if f.name == "CanCarry"]
        assert len(can_carry) == 1

    def test_cannot_carry_overloaded(self, scenario, dist_matrix):
        """Neredeyse dolu drone ağır paketi taşıyamamalı."""
        kb = KnowledgeBase()
        kb.add_rule(R1_CAPACITY)
        _setup_base_context(kb, scenario, dist_matrix)
        kb.set_context("current_load_kg", 4.9)  # Neredeyse dolu

        # En ağır paketi bul (> 0.1 kg olmalı)
        heavy_pkg = max(scenario.delivery_points, key=lambda dp: dp.weight_kg)
        if heavy_pkg.weight_kg > 0.1:
            kb.set_context("candidate_package_id", heavy_pkg.id)

            engine = InferenceEngine(kb)
            new_facts = engine.run()

            can_carry = [f for f in new_facts if f.name == "CanCarry"]
            assert len(can_carry) == 0  # Taşıyamaz


# ---------------------------------------------------------------------------
# R2 — Range testleri
# ---------------------------------------------------------------------------

class TestR2Range:
    def test_range_feasible_from_depot(self, scenario, dist_matrix):
        """Depot'tan herhangi bir pakete gidip dönmek mümkün olmalı (800 menzil yeterli)."""
        kb = KnowledgeBase()
        kb.add_rule(R2_RANGE)
        _setup_base_context(kb, scenario, dist_matrix)

        engine = InferenceEngine(kb)
        new_facts = engine.run()

        feasible = [f for f in new_facts if f.name == "RangeFeasible"]
        assert len(feasible) == 1

    def test_range_infeasible_long_trip(self, scenario, dist_matrix):
        """Çok uzun yol kat etmiş drone artık gidemez."""
        kb = KnowledgeBase()
        kb.add_rule(R2_RANGE)
        _setup_base_context(kb, scenario, dist_matrix)
        kb.set_context("distance_traveled", 790.0)  # Menzil neredeyse bitmiş

        engine = InferenceEngine(kb)
        new_facts = engine.run()

        feasible = [f for f in new_facts if f.name == "RangeFeasible"]
        assert len(feasible) == 0


# ---------------------------------------------------------------------------
# R3 — TimeWindow testleri
# ---------------------------------------------------------------------------

class TestR3TimeWindow:
    def test_time_window_violation_late_arrival(self, scenario, dist_matrix):
        """Çok geç vardığında TimeWindowViolation üretmeli."""
        kb = KnowledgeBase()
        kb.add_rule(R3_TIME_WINDOW)
        _setup_base_context(kb, scenario, dist_matrix)
        kb.set_context("current_time_min", 999.0)  # Çok geç

        engine = InferenceEngine(kb)
        new_facts = engine.run()

        violations = [f for f in new_facts if f.name == "TimeWindowViolation"]
        assert len(violations) == 1

    def test_time_window_ok(self, scenario, dist_matrix):
        """Doğru zamanda varınca TimeWindowOK veya WaitRequired üretmeli."""
        kb = KnowledgeBase()
        kb.add_rule(R3_TIME_WINDOW)
        pkg = scenario.delivery_points[0]
        _setup_base_context(kb, scenario, dist_matrix, pkg.id)
        # Tam açılış zamanında depot'tan yola çık
        kb.set_context("current_time_min", float(pkg.time_window_open_min))

        engine = InferenceEngine(kb)
        new_facts = engine.run()

        # Ya TimeWindowOK ya da WaitRequired olmalı (violation olmamalı)
        violations = [f for f in new_facts if f.name == "TimeWindowViolation"]
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# R5 — MustReturn testleri
# ---------------------------------------------------------------------------

class TestR5MustReturn:
    def test_must_return_low_range(self, scenario, dist_matrix):
        """Menzil azaldığında MustReturn tetiklenmeli."""
        kb = KnowledgeBase()
        kb.add_rule(R5_MUST_RETURN)
        _setup_base_context(kb, scenario, dist_matrix)
        # Menzil neredeyse bitmiş — depot'a ancak yetecek
        kb.set_context("distance_traveled", 780.0)

        engine = InferenceEngine(kb)
        new_facts = engine.run()

        must_return = [f for f in new_facts if f.name == "MustReturn"]
        assert len(must_return) == 1

    def test_no_must_return_plenty_of_range(self, scenario, dist_matrix):
        """Yeterli menzil varken MustReturn tetiklenmemeli."""
        kb = KnowledgeBase()
        kb.add_rule(R5_MUST_RETURN)
        _setup_base_context(kb, scenario, dist_matrix)
        kb.set_context("distance_traveled", 0.0)

        engine = InferenceEngine(kb)
        new_facts = engine.run()

        must_return = [f for f in new_facts if f.name == "MustReturn"]
        assert len(must_return) == 0


# ---------------------------------------------------------------------------
# R6 — Priority testleri
# ---------------------------------------------------------------------------

class TestR6Priority:
    def test_priority_ordering(self, scenario, dist_matrix):
        """Farklı priority'li paketler arasında PreferredOrder üretmeli."""
        kb = KnowledgeBase()
        kb.add_rule(R6_PRIORITY)
        _setup_base_context(kb, scenario, dist_matrix)

        # Farklı priority'li iki paket bul
        high_pkg = None
        low_pkg = None
        for dp in scenario.delivery_points:
            if dp.priority == "high" and high_pkg is None:
                high_pkg = dp
            elif dp.priority == "low" and low_pkg is None:
                low_pkg = dp

        if high_pkg and low_pkg:
            kb.set_context("trip_packages", [high_pkg.id, low_pkg.id])

            engine = InferenceEngine(kb)
            new_facts = engine.run()

            preferred = [f for f in new_facts if f.name == "PreferredOrder"]
            assert len(preferred) == 1
            # High priority olanın önce gelmesi lazım
            assert preferred[0].args[0] == high_pkg.id

    def test_no_ordering_same_priority(self, scenario, dist_matrix):
        """Aynı priority'li paketler arasında PreferredOrder olmamalı."""
        kb = KnowledgeBase()
        kb.add_rule(R6_PRIORITY)
        _setup_base_context(kb, scenario, dist_matrix)

        # Aynı priority'li iki paket bul
        same_prio_pkgs = [dp for dp in scenario.delivery_points if dp.priority == "low"]
        if len(same_prio_pkgs) >= 2:
            kb.set_context("trip_packages", [same_prio_pkgs[0].id, same_prio_pkgs[1].id])

            engine = InferenceEngine(kb)
            new_facts = engine.run()

            preferred = [f for f in new_facts if f.name == "PreferredOrder"]
            assert len(preferred) == 0


# ---------------------------------------------------------------------------
# Integration — Tüm kurallar birlikte
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_forward_chaining(self, scenario, dist_matrix, kb_with_rules):
        """Tüm kurallar yüklüyken forward chaining düzgün çalışmalı."""
        _setup_base_context(kb_with_rules, scenario, dist_matrix)

        engine = InferenceEngine(kb_with_rules)
        new_facts = engine.run()

        # En az R1 ve R2 tetiklenmeli (boş drone, depot'tan)
        fact_names = {f.name for f in new_facts}
        assert "CanCarry" in fact_names
        assert "RangeFeasible" in fact_names

        # Trace boş olmamalı
        assert len(engine.get_trace()) > 0

    def test_saturation(self, scenario, dist_matrix, kb_with_rules):
        """Forward chaining sonlu adımda durmalı (sonsuz döngü yok)."""
        _setup_base_context(kb_with_rules, scenario, dist_matrix)

        engine = InferenceEngine(kb_with_rules)
        engine.run()

        # max_iterations'a ulaşmadan durmuş olmalı
        trace = engine.get_trace()
        if trace:
            max_iter = max(t["iteration"] for t in trace)
            assert max_iter < 50  # default max_iterations
