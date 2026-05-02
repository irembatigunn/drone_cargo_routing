"""
Feasibility Checker — Logic Engine ile GA Arasındaki Köprü

GA'nın chromosome decode aşamasında Logic Engine kurallarını
kullanarak fizibilite kontrolü yapar ve infeasible chromosome'ları
repair eder.

Kullanım:
    from app.services.feasibility import decode_chromosome

    result = decode_chromosome(scenario, dist_matrix, chromosome)
    # result.routes → DroneRoute listesi
    # result.unassigned → atanamamış paket id'leri
    # result.time_window_violations → TW ihlal sayısı
    # result.trace → Modus Ponens inference trace (rapor için)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from app.models.scenario import Scenario
from app.services.logic_engine import KnowledgeBase, InferenceEngine, Predicate
from app.services.rules import register_all_rules


# ---------------------------------------------------------------------------
# Decode sonucu — GA'nın kullanacağı veri yapısı
# ---------------------------------------------------------------------------

@dataclass
class TripResult:
    """Bir trip'in decode sonucu."""
    drone_id: str
    trip_idx: int
    sequence: list[str]            # teslimat sırası (paket id'leri)
    distance: float = 0.0          # toplam mesafe
    duration_min: float = 0.0      # toplam süre (dakika)


@dataclass
class DecodeResult:
    """Tüm chromosome'un decode sonucu."""
    trips: list[TripResult] = field(default_factory=list)
    unassigned: list[str] = field(default_factory=list)
    time_window_violations: int = 0
    priority_violations: int = 0
    trace: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Ana fonksiyon: chromosome → decode result
# ---------------------------------------------------------------------------

def decode_chromosome(
    scenario: Scenario,
    dist_matrix: dict,
    chromosome: list[list[str]],
) -> DecodeResult:
    """
    GA chromosome'unu decode eder, Logic Engine kurallarını uygular.

    Parametreler:
        scenario: Senaryo (drone fleet, delivery points vs.)
        dist_matrix: Node çiftleri arası mesafe dict'i
                     Örnek: dist_matrix["depot"]["pkg_001"] = 234.5
        chromosome: Her drone'a atanan paket id listesi
                    Örnek: [["pkg_03","pkg_01"], ["pkg_02","pkg_05"], ...]

    Dönüş:
        DecodeResult: trip'ler, atanamamış paketler, ihlaller, trace

    Decode süreci:
    1. Her drone için sırayla paketleri dene
    2. R1 (kapasite) + R2 (menzil) + R5 (geri dönüş) kontrol et
    3. Geçemezse → trip'i kapat, yeni trip aç
    4. Yeni trip'te de geçemezse → unassigned havuzuna at
    5. Sonra unassigned'ları best-insertion ile tekrar dene (repair)
    6. R3 (time window) ve R6 (priority) son kontrolü yap
    """
    result = DecodeResult()
    speed = scenario.drone_fleet.speed_units_per_min
    max_range = scenario.drone_fleet.max_range_per_trip
    recharge_time = scenario.drone_fleet.recharge_time_min

    # --- Adım 1-4: Her drone için paketleri decode et ---

    for drone_idx, pkg_ids in enumerate(chromosome):
        drone_id = f"drone_{drone_idx + 1}"
        _decode_drone_packages(
            scenario, dist_matrix, drone_id, pkg_ids,
            speed, max_range, recharge_time, result,
        )

    # --- Adım 5: Unassigned paketleri repair et (best insertion) ---

    if result.unassigned:
        _repair_unassigned(scenario, dist_matrix, speed, max_range, result)

    # --- Adım 6: Time window ve priority kontrolü ---

    _check_time_windows(scenario, dist_matrix, speed, result)
    _check_priority_ordering(scenario, result)

    return result


# ---------------------------------------------------------------------------
# Drone paketlerini decode et
# ---------------------------------------------------------------------------

def _decode_drone_packages(
    scenario: Scenario,
    dist_matrix: dict,
    drone_id: str,
    pkg_ids: list[str],
    speed: float,
    max_range: float,
    recharge_time: float,
    result: DecodeResult,
) -> None:
    """
    Tek bir drone için atanan paketleri sırayla dener.
    R1, R2, R5 kurallarını forward chaining ile kontrol eder.
    """

    trip_idx = 1
    current_pos = "depot"
    current_load = 0.0
    distance_traveled = 0.0
    current_time = 0.0
    current_trip_packages: list[str] = []

    for pkg_id in pkg_ids:
        # KnowledgeBase'i bu kontrol için hazırla
        feasible, new_trip_needed, trace_entries = _check_feasibility(
            scenario, dist_matrix, drone_id, f"trip_{trip_idx}",
            current_load, distance_traveled, current_pos,
            pkg_id, current_time, current_trip_packages,
        )
        result.trace.extend(trace_entries)

        if feasible:
            # Paketi trip'e ekle
            current_trip_packages, current_pos, current_load, \
                distance_traveled, current_time = _add_package_to_trip(
                    scenario, dist_matrix, pkg_id, current_trip_packages,
                    current_pos, current_load, distance_traveled,
                    current_time, speed,
                )
        elif new_trip_needed:
            # Mevcut trip'i kapat, depot'a dön
            if current_trip_packages:
                dist_back = _get_dist(dist_matrix, current_pos, "depot")
                trip_distance = distance_traveled + dist_back
                trip_duration = current_time + (dist_back / speed) + recharge_time

                result.trips.append(TripResult(
                    drone_id=drone_id,
                    trip_idx=trip_idx,
                    sequence=list(current_trip_packages),
                    distance=trip_distance,
                    duration_min=trip_duration,
                ))

            # Yeni trip başlat
            trip_idx += 1
            current_pos = "depot"
            current_load = 0.0
            distance_traveled = 0.0
            current_time = current_time + (
                _get_dist(dist_matrix, current_pos, "depot") / speed
            ) + recharge_time if current_trip_packages else current_time
            current_trip_packages = []

            # Yeni trip'te tekrar dene
            feasible2, _, trace2 = _check_feasibility(
                scenario, dist_matrix, drone_id, f"trip_{trip_idx}",
                current_load, distance_traveled, current_pos,
                pkg_id, current_time, current_trip_packages,
            )
            result.trace.extend(trace2)

            if feasible2:
                current_trip_packages, current_pos, current_load, \
                    distance_traveled, current_time = _add_package_to_trip(
                        scenario, dist_matrix, pkg_id, current_trip_packages,
                        current_pos, current_load, distance_traveled,
                        current_time, speed,
                    )
            else:
                result.unassigned.append(pkg_id)
        else:
            # Ne mevcut trip'te ne yeni trip'te uygun değil
            result.unassigned.append(pkg_id)

    # Son trip'i kapat (içinde paket varsa)
    if current_trip_packages:
        dist_back = _get_dist(dist_matrix, current_pos, "depot")
        result.trips.append(TripResult(
            drone_id=drone_id,
            trip_idx=trip_idx,
            sequence=list(current_trip_packages),
            distance=distance_traveled + dist_back,
            duration_min=current_time + (dist_back / speed),
        ))


# ---------------------------------------------------------------------------
# Fizibilite kontrolü — Logic Engine forward chaining
# ---------------------------------------------------------------------------

def _check_feasibility(
    scenario: Scenario,
    dist_matrix: dict,
    drone_id: str,
    trip_id: str,
    current_load: float,
    distance_traveled: float,
    current_pos: str,
    pkg_id: str,
    current_time: float,
    trip_packages: list[str],
) -> tuple[bool, bool, list[dict]]:
    """
    Logic Engine ile fizibilite kontrolü yapar.

    Dönüş: (feasible, new_trip_needed, trace)
        feasible: True ise paket eklenebilir
        new_trip_needed: True ise mevcut trip doldu, yeni trip dene
        trace: Inference trace (rapor için)
    """
    kb = KnowledgeBase()
    register_all_rules(kb)

    # Context'i ayarla
    kb.set_context("scenario", scenario)
    kb.set_context("drone_id", drone_id)
    kb.set_context("trip_id", trip_id)
    kb.set_context("current_load_kg", current_load)
    kb.set_context("distance_traveled", distance_traveled)
    kb.set_context("current_position", current_pos)
    kb.set_context("candidate_package_id", pkg_id)
    kb.set_context("distance_matrix", dist_matrix)
    kb.set_context("current_time_min", current_time)
    kb.set_context("trip_packages", trip_packages)

    # Forward chaining çalıştır
    engine = InferenceEngine(kb)
    engine.run()

    # Sonuçları oku
    can_carry = kb.has_fact("CanCarry", (drone_id, pkg_id, trip_id))
    range_ok = kb.has_fact("RangeFeasible", (drone_id, pkg_id, trip_id))
    must_return = kb.has_fact("MustReturn", (drone_id,))

    feasible = can_carry and range_ok and not must_return
    # Kapasite doldu veya menzil yetersiz → yeni trip lazım
    new_trip_needed = (not can_carry or not range_ok or must_return)

    return feasible, new_trip_needed, engine.get_trace()


# ---------------------------------------------------------------------------
# Paketi trip'e ekleme (state güncelleme)
# ---------------------------------------------------------------------------

def _add_package_to_trip(
    scenario: Scenario,
    dist_matrix: dict,
    pkg_id: str,
    trip_packages: list[str],
    current_pos: str,
    current_load: float,
    distance_traveled: float,
    current_time: float,
    speed: float,
) -> tuple[list[str], str, float, float, float]:
    """
    Paketi trip'e ekler ve drone state'ini günceller.

    Dönüş: (trip_packages, new_pos, new_load, new_distance, new_time)
    """
    pkg = _find_pkg(scenario, pkg_id)
    dist_to_pkg = _get_dist(dist_matrix, current_pos, pkg_id)
    travel_time = dist_to_pkg / speed if speed > 0 else 0

    trip_packages.append(pkg_id)
    new_pos = pkg_id
    new_load = current_load + pkg.weight_kg
    new_distance = distance_traveled + dist_to_pkg

    arrival_time = current_time + travel_time
    # Erken vardıysak, açılış zamanını bekle
    effective_arrival = max(arrival_time, pkg.time_window_open_min)
    new_time = effective_arrival + pkg.service_time_min

    return trip_packages, new_pos, new_load, new_distance, new_time


# ---------------------------------------------------------------------------
# Repair — unassigned paketleri best-insertion ile yerleştir
# ---------------------------------------------------------------------------

def _repair_unassigned(
    scenario: Scenario,
    dist_matrix: dict,
    speed: float,
    max_range: float,
    result: DecodeResult,
) -> None:
    """
    Unassigned paketleri mevcut trip'lere best-insertion ile yerleştirmeye
    çalışır. Yerleşemeyenler unassigned olarak kalır.

    Best insertion: Her unassigned paket için, her trip'in her pozisyonuna
    denenir, marginal mesafe artışı en az olan pozisyona eklenir.
    """
    still_unassigned: list[str] = []

    for pkg_id in result.unassigned:
        best_cost = float("inf")
        best_trip_idx = -1
        best_insert_pos = -1

        for t_idx, trip in enumerate(result.trips):
            # Trip'in drone'unun kapasitesini kontrol et
            trip_load = sum(
                _find_pkg(scenario, pid).weight_kg
                for pid in trip.sequence
            )
            pkg = _find_pkg(scenario, pkg_id)
            if pkg is None:
                continue
            if trip_load + pkg.weight_kg > scenario.drone_fleet.max_payload_kg:
                continue

            # Her pozisyona insertion maliyetini hesapla
            for pos in range(len(trip.sequence) + 1):
                cost = _insertion_cost(
                    dist_matrix, trip.sequence, pkg_id, pos,
                )
                # Menzil kontrolü: yeni toplam mesafe max_range'i aşmamalı
                new_total = trip.distance - _return_dist(dist_matrix, trip.sequence) + \
                    _route_distance_with_insert(dist_matrix, trip.sequence, pkg_id, pos)
                if new_total > max_range:
                    continue

                if cost < best_cost:
                    best_cost = cost
                    best_trip_idx = t_idx
                    best_insert_pos = pos

        if best_trip_idx >= 0:
            # Paketi en iyi pozisyona ekle
            trip = result.trips[best_trip_idx]
            trip.sequence.insert(best_insert_pos, pkg_id)
            # Mesafeyi güncelle
            trip.distance = _calculate_trip_distance(dist_matrix, trip.sequence)
            trip.duration_min = trip.distance / speed
        else:
            still_unassigned.append(pkg_id)

    result.unassigned = still_unassigned


# ---------------------------------------------------------------------------
# Time window kontrolü (R3) — decode sonrası
# ---------------------------------------------------------------------------

def _check_time_windows(
    scenario: Scenario,
    dist_matrix: dict,
    speed: float,
    result: DecodeResult,
) -> None:
    """Her trip'teki her paket için varış zamanını hesaplar, TW ihlallerini sayar."""
    violations = 0

    for trip in result.trips:
        current_time = 0.0
        # Trip başlangıcını bul (önceki trip'lerin süresini hesaba kat)
        # Basitleştirme: her trip bağımsız, t=0'dan başlıyor
        # (Gerçek implementasyonda önceki trip süresi + recharge eklenir)
        current_pos = "depot"

        for pkg_id in trip.sequence:
            pkg = _find_pkg(scenario, pkg_id)
            if pkg is None:
                continue

            dist = _get_dist(dist_matrix, current_pos, pkg_id)
            travel_time = dist / speed if speed > 0 else 0
            arrival_time = current_time + travel_time

            if arrival_time > pkg.time_window_close_min:
                violations += 1

            effective_arrival = max(arrival_time, pkg.time_window_open_min)
            current_time = effective_arrival + pkg.service_time_min
            current_pos = pkg_id

    result.time_window_violations = violations


# ---------------------------------------------------------------------------
# Priority ordering kontrolü (R6) — decode sonrası
# ---------------------------------------------------------------------------

def _check_priority_ordering(scenario: Scenario, result: DecodeResult) -> None:
    """Trip içinde yüksek priority'li paketin düşük priority'liden sonra
    geldiği durumları sayar."""
    priority_map = {"high": 3, "med": 2, "low": 1}
    violations = 0

    for trip in result.trips:
        for i, pid1 in enumerate(trip.sequence):
            for pid2 in trip.sequence[i + 1:]:
                pkg1 = _find_pkg(scenario, pid1)
                pkg2 = _find_pkg(scenario, pid2)
                if pkg1 is None or pkg2 is None:
                    continue
                # pid1 sırada önce geliyor. Eğer pid2 daha yüksek
                # priority'liyse → ihlal
                if priority_map.get(pkg2.priority, 0) > priority_map.get(pkg1.priority, 0):
                    violations += 1

    result.priority_violations = violations


# ---------------------------------------------------------------------------
# Mesafe yardımcı fonksiyonları
# ---------------------------------------------------------------------------

def _get_dist(dist_matrix: dict, from_id: str, to_id: str) -> float:
    row = dist_matrix.get(from_id)
    if row is None:
        return float("inf")
    return row.get(to_id, float("inf"))


def _find_pkg(scenario: Scenario, pkg_id: str):
    for dp in scenario.delivery_points:
        if dp.id == pkg_id:
            return dp
    return None


def _calculate_trip_distance(dist_matrix: dict, sequence: list[str]) -> float:
    """depot → p1 → p2 → ... → depot toplam mesafesi."""
    if not sequence:
        return 0.0
    total = _get_dist(dist_matrix, "depot", sequence[0])
    for i in range(len(sequence) - 1):
        total += _get_dist(dist_matrix, sequence[i], sequence[i + 1])
    total += _get_dist(dist_matrix, sequence[-1], "depot")
    return total


def _return_dist(dist_matrix: dict, sequence: list[str]) -> float:
    """Trip'in son noktasından depot'a dönüş mesafesi."""
    if not sequence:
        return 0.0
    return _get_dist(dist_matrix, sequence[-1], "depot")


def _insertion_cost(
    dist_matrix: dict,
    sequence: list[str],
    pkg_id: str,
    pos: int,
) -> float:
    """Bir paketi belirli pozisyona eklemenin marginal mesafe maliyeti."""
    if not sequence:
        # Boş route: depot → pkg → depot
        return (
            _get_dist(dist_matrix, "depot", pkg_id) +
            _get_dist(dist_matrix, pkg_id, "depot")
        )

    if pos == 0:
        prev_node = "depot"
        next_node = sequence[0]
    elif pos >= len(sequence):
        prev_node = sequence[-1]
        next_node = "depot"
    else:
        prev_node = sequence[pos - 1]
        next_node = sequence[pos]

    old_cost = _get_dist(dist_matrix, prev_node, next_node)
    new_cost = (
        _get_dist(dist_matrix, prev_node, pkg_id) +
        _get_dist(dist_matrix, pkg_id, next_node)
    )
    return new_cost - old_cost


def _route_distance_with_insert(
    dist_matrix: dict,
    sequence: list[str],
    pkg_id: str,
    pos: int,
) -> float:
    """Paketi pozisyona ekledikten sonraki toplam route mesafesi (depot dahil)."""
    new_seq = list(sequence)
    new_seq.insert(pos, pkg_id)
    return _calculate_trip_distance(dist_matrix, new_seq)
