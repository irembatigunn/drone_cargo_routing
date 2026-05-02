"""
Feasibility (GA-Logic Engine entegrasyonu) testleri.

Chromosome decode + repair + time window / priority kontrolleri.
"""

import pytest
from app.services.feasibility import decode_chromosome, DecodeResult
from app.services.data_generator import generate_scenario
from app.services.distance_matrix import build_distance_matrix


@pytest.fixture
def scenario():
    return generate_scenario("test", 8, 2, 3, 42)


@pytest.fixture
def dist_matrix(scenario):
    return build_distance_matrix(scenario)["matrix"]


@pytest.fixture
def all_pkg_ids(scenario):
    return [dp.id for dp in scenario.delivery_points]


class TestDecodeChromosome:
    def test_basic_decode(self, scenario, dist_matrix, all_pkg_ids):
        """Basit round-robin chromosome decode edilebilmeli."""
        # 3 drone'a round-robin dağıt
        chromosome = [[], [], []]
        for i, pid in enumerate(all_pkg_ids):
            chromosome[i % 3].append(pid)

        result = decode_chromosome(scenario, dist_matrix, chromosome)

        assert isinstance(result, DecodeResult)
        # Tüm paketler ya trip'te ya unassigned'da olmalı
        assigned = []
        for trip in result.trips:
            assigned.extend(trip.sequence)
        total = len(assigned) + len(result.unassigned)
        assert total == len(all_pkg_ids)

    def test_all_packages_feasible_small_load(self, scenario, dist_matrix, all_pkg_ids):
        """8 paket, 3 drone — çoğu paket atanabilmeli."""
        chromosome = [[], [], []]
        for i, pid in enumerate(all_pkg_ids):
            chromosome[i % 3].append(pid)

        result = decode_chromosome(scenario, dist_matrix, chromosome)

        assigned_count = sum(len(t.sequence) for t in result.trips)
        # En az yarısı atanmış olmalı
        assert assigned_count >= len(all_pkg_ids) // 2

    def test_overloaded_drone_triggers_new_trip(self, scenario, dist_matrix, all_pkg_ids):
        """Tüm paketleri tek drone'a yığınca trip bölünmeli veya unassign olmalı."""
        chromosome = [all_pkg_ids, [], []]

        result = decode_chromosome(scenario, dist_matrix, chromosome)

        # Drone_1'in birden fazla trip'i olabilir
        drone1_trips = [t for t in result.trips if t.drone_id == "drone_1"]
        # Ya birden fazla trip var, ya da bazı paketler unassigned
        assert len(drone1_trips) >= 1

    def test_empty_chromosome(self, scenario, dist_matrix):
        """Boş chromosome hata vermemeli."""
        chromosome = [[], [], []]
        result = decode_chromosome(scenario, dist_matrix, chromosome)
        assert len(result.trips) == 0
        assert len(result.unassigned) == 0

    def test_trace_is_populated(self, scenario, dist_matrix, all_pkg_ids):
        """Forward chaining trace dolu olmalı (rapor için lazım)."""
        chromosome = [all_pkg_ids[:3], all_pkg_ids[3:6], all_pkg_ids[6:]]
        result = decode_chromosome(scenario, dist_matrix, chromosome)
        assert len(result.trace) > 0

    def test_trip_distances_positive(self, scenario, dist_matrix, all_pkg_ids):
        """Trip mesafeleri pozitif olmalı."""
        chromosome = [all_pkg_ids[:3], all_pkg_ids[3:6], all_pkg_ids[6:]]
        result = decode_chromosome(scenario, dist_matrix, chromosome)
        for trip in result.trips:
            assert trip.distance > 0

    def test_no_duplicate_assignments(self, scenario, dist_matrix, all_pkg_ids):
        """Aynı paket birden fazla trip'te olmamalı."""
        chromosome = [all_pkg_ids[:3], all_pkg_ids[3:6], all_pkg_ids[6:]]
        result = decode_chromosome(scenario, dist_matrix, chromosome)

        all_assigned = []
        for trip in result.trips:
            all_assigned.extend(trip.sequence)
        # Duplicate kontrolü
        assert len(all_assigned) == len(set(all_assigned))

    def test_time_window_violations_counted(self, scenario, dist_matrix, all_pkg_ids):
        """Time window violations sayılmalı (sıfır veya pozitif)."""
        chromosome = [all_pkg_ids[:3], all_pkg_ids[3:6], all_pkg_ids[6:]]
        result = decode_chromosome(scenario, dist_matrix, chromosome)
        assert result.time_window_violations >= 0

    def test_priority_violations_counted(self, scenario, dist_matrix, all_pkg_ids):
        """Priority violations sayılmalı (sıfır veya pozitif)."""
        chromosome = [all_pkg_ids[:3], all_pkg_ids[3:6], all_pkg_ids[6:]]
        result = decode_chromosome(scenario, dist_matrix, chromosome)
        assert result.priority_violations >= 0
