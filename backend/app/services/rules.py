"""
R1-R6 First-Order Logic Kuralları — Drone Cargo Routing

Her kural bir Rule objesidir:
  - condition: KnowledgeBase'deki context verilerine bakarak koşulun
               sağlanıp sağlanmadığını kontrol eder
  - consequent_generator: Koşul sağlandığında yeni Predicate'ler üretir

Context'te beklenen veriler (her kural kullanılmadan önce set edilmeli):
  - "scenario": Scenario objesi (drone fleet spec, delivery points vs.)
  - "drone_id": str — hangi drone için kontrol yapılıyor
  - "trip_id": str — hangi trip için
  - "current_load_kg": float — trip'teki mevcut yük (kg)
  - "distance_traveled": float — trip'te şu ana kadar kat edilen mesafe
  - "current_position": str — drone'un şu anki konumu (node id)
  - "candidate_package_id": str — eklenmek istenen paket id
  - "distance_matrix": dict — node çiftleri arası mesafeler
  - "current_time_min": float — simülasyon saati (dakika)
  - "trip_packages": list[str] — trip'teki mevcut paket id'leri (R6 için)
"""

from __future__ import annotations
from app.services.logic_engine import Rule, Predicate, KnowledgeBase
from app.models.scenario import Scenario


# ═══════════════════════════════════════════════════════════════════════════
# R1 — CAPACITY RULE
# ═══════════════════════════════════════════════════════════════════════════
#
#   ∀d ∈ Drones, ∀p ∈ Packages:
#     CurrentLoad(d, trip) + Weight(p) ≤ MaxPayload(d) → CanCarry(d, p, trip)
#
#   Ne yapıyor: Drone'un bu trip'te taşıdığı toplam yük + yeni paketin
#   ağırlığı, maksimum kapasiteyi aşıyor mu kontrol eder.
#
#   Gerçek hayat karşılığı: Bir kamyonun kasası 5 ton alıyor, içinde
#   3 ton var, yeni paket 1 ton → 4 ton ≤ 5 ton → sığar.
# ═══════════════════════════════════════════════════════════════════════════

def _r1_condition(kb: KnowledgeBase) -> bool:
    scenario: Scenario = kb.get_context("scenario")
    current_load = kb.get_context("current_load_kg", 0.0)
    pkg_id = kb.get_context("candidate_package_id")

    if scenario is None or pkg_id is None:
        return False

    pkg = _find_package(scenario, pkg_id)
    if pkg is None:
        return False

    max_payload = scenario.drone_fleet.max_payload_kg
    return (current_load + pkg.weight_kg) <= max_payload


def _r1_consequent(kb: KnowledgeBase) -> list[Predicate]:
    drone_id = kb.get_context("drone_id")
    pkg_id = kb.get_context("candidate_package_id")
    trip_id = kb.get_context("trip_id")
    return [Predicate("CanCarry", (drone_id, pkg_id, trip_id))]


R1_CAPACITY = Rule(
    name="R1_Capacity",
    description="CurrentLoad + Weight ≤ MaxPayload → CanCarry",
    condition=_r1_condition,
    consequent_generator=_r1_consequent,
)


# ═══════════════════════════════════════════════════════════════════════════
# R2 — RANGE RULE
# ═══════════════════════════════════════════════════════════════════════════
#
#   ∀d ∈ Drones, ∀route:
#     DistanceTraveled(d, route) + DistToNext(d, p) + DistFromNextToDepot
#       ≤ MaxRange → RangeFeasible(d, p, route)
#
#   Ne yapıyor: Drone bu pakete gidip sonra depot'a dönebilecek kadar
#   menzili var mı kontrol eder. Sadece "oraya gidebilir miyim" değil,
#   "gidip DÖNÜŞÜ de kurtarabilir miyim" bakıyoruz.
#
#   Neden DistFromNextToDepot da ekleniyor? Drone paketi bıraktıktan sonra
#   depot'a dönmek ZORUNDA. Eğer sadece "oraya gidebilir miyim" kontrol
#   etsek, drone paketi bırakır ama geri dönemez → kaybolur.
# ═══════════════════════════════════════════════════════════════════════════

def _r2_condition(kb: KnowledgeBase) -> bool:
    scenario: Scenario = kb.get_context("scenario")
    distance_traveled = kb.get_context("distance_traveled", 0.0)
    current_pos = kb.get_context("current_position")
    pkg_id = kb.get_context("candidate_package_id")
    dist_matrix = kb.get_context("distance_matrix")

    if scenario is None or pkg_id is None or dist_matrix is None:
        return False

    max_range = scenario.drone_fleet.max_range_per_trip
    pkg = _find_package(scenario, pkg_id)
    if pkg is None:
        return False

    # Şu anki konumdan pakete mesafe
    dist_to_pkg = _get_distance(dist_matrix, current_pos, pkg_id)
    # Paketten depot'a dönüş mesafesi
    dist_pkg_to_depot = _get_distance(dist_matrix, pkg_id, "depot")

    total_needed = distance_traveled + dist_to_pkg + dist_pkg_to_depot
    return total_needed <= max_range


def _r2_consequent(kb: KnowledgeBase) -> list[Predicate]:
    drone_id = kb.get_context("drone_id")
    pkg_id = kb.get_context("candidate_package_id")
    trip_id = kb.get_context("trip_id")
    return [Predicate("RangeFeasible", (drone_id, pkg_id, trip_id))]


R2_RANGE = Rule(
    name="R2_Range",
    description="DistTraveled + DistToNext + DistToDepot ≤ MaxRange → RangeFeasible",
    condition=_r2_condition,
    consequent_generator=_r2_consequent,
)


# ═══════════════════════════════════════════════════════════════════════════
# R3 — TIME WINDOW RULE (Soft Constraint)
# ═══════════════════════════════════════════════════════════════════════════
#
#   ∀p ∈ Packages:
#     ArrivalTime(p) > CloseTime(p) → TimeWindowViolation(p)
#     ArrivalTime(p) < OpenTime(p)  → WaitRequired(p)
#
#   Ne yapıyor: Paketin teslim zamanı, müşterinin belirttiği zaman
#   aralığında mı kontrol eder.
#
#   "Soft constraint" ne demek? Bu kural ihlal edilince drone çökmez,
#   sadece fitness fonksiyonunda PENALTY alır. Yani GA bunu mümkün
#   olduğunca kaçınmaya çalışır ama bazen kabul eder.
#
#   İki durum var:
#   - Geç kaldık (violation) → müşteri mutsuz, penalty
#   - Erken geldik (wait) → drone bekler, zaman kaybı ama violation değil
# ═══════════════════════════════════════════════════════════════════════════

def _r3_condition(kb: KnowledgeBase) -> bool:
    # R3 her zaman koşulunu kontrol eder — "arrival time biliniyor mu?"
    scenario: Scenario = kb.get_context("scenario")
    pkg_id = kb.get_context("candidate_package_id")
    current_time = kb.get_context("current_time_min")

    if scenario is None or pkg_id is None or current_time is None:
        return False

    pkg = _find_package(scenario, pkg_id)
    return pkg is not None


def _r3_consequent(kb: KnowledgeBase) -> list[Predicate]:
    scenario: Scenario = kb.get_context("scenario")
    pkg_id = kb.get_context("candidate_package_id")
    current_time = kb.get_context("current_time_min")
    current_pos = kb.get_context("current_position")
    dist_matrix = kb.get_context("distance_matrix")
    speed = scenario.drone_fleet.speed_units_per_min

    pkg = _find_package(scenario, pkg_id)
    results: list[Predicate] = []

    # Varış zamanı = şu anki zaman + yolculuk süresi + servis süresi
    dist_to_pkg = _get_distance(dist_matrix, current_pos, pkg_id)
    travel_time = dist_to_pkg / speed if speed > 0 else float("inf")
    arrival_time = current_time + travel_time

    if arrival_time > pkg.time_window_close_min:
        results.append(Predicate("TimeWindowViolation", (pkg_id,)))
    elif arrival_time < pkg.time_window_open_min:
        results.append(Predicate("WaitRequired", (pkg_id,)))
    else:
        results.append(Predicate("TimeWindowOK", (pkg_id,)))

    return results


R3_TIME_WINDOW = Rule(
    name="R3_TimeWindow",
    description="ArrivalTime vs TimeWindow → Violation / WaitRequired / OK",
    condition=_r3_condition,
    consequent_generator=_r3_consequent,
)


# ═══════════════════════════════════════════════════════════════════════════
# R4 — NO-FLY ZONE RULE (Hard Constraint)
# ═══════════════════════════════════════════════════════════════════════════
#
#   ∀segment ∈ DronePath, ∀z ∈ NoFlyZones:
#     Intersects(segment, Interior(z)) → ForbiddenPath(segment)
#
#   Ne yapıyor: İki nokta arasındaki doğrusal yol, herhangi bir yasak
#   bölgenin İÇİNDEN geçiyor mu kontrol eder.
#
#   ÖNEMLİ NOT: PRD'ye göre bu kural distance matrix precompute
#   aşamasında zaten zorlanıyor — visibility graph, no-fly zone içinden
#   geçen edge'leri hiç eklemiyor. Yani R4, GA decode sırasında
#   tetiklenmemeli (çünkü sadece geçerli yollar var).
#   Ama yine de tanımlıyoruz: (1) FOL completeness için, (2) raporda
#   göstermek için, (3) doğrulama katmanı olarak.
# ═══════════════════════════════════════════════════════════════════════════

def _r4_condition(kb: KnowledgeBase) -> bool:
    scenario: Scenario = kb.get_context("scenario")
    current_pos = kb.get_context("current_position")
    pkg_id = kb.get_context("candidate_package_id")
    dist_matrix = kb.get_context("distance_matrix")

    if scenario is None or current_pos is None or pkg_id is None:
        return False

    if not scenario.no_fly_zones:
        return False

    # direct_path_blocked context'te set edilmişse kontrol et
    # (visibility graph modülü tarafından hesaplanır)
    blocked = kb.get_context("direct_path_blocked")
    return blocked is True


def _r4_consequent(kb: KnowledgeBase) -> list[Predicate]:
    current_pos = kb.get_context("current_position")
    pkg_id = kb.get_context("candidate_package_id")
    return [Predicate("ForbiddenPath", (current_pos, pkg_id))]


R4_NO_FLY_ZONE = Rule(
    name="R4_NoFlyZone",
    description="Intersects(segment, Interior(zone)) → ForbiddenPath",
    condition=_r4_condition,
    consequent_generator=_r4_consequent,
)


# ═══════════════════════════════════════════════════════════════════════════
# R5 — MUST RETURN RULE
# ═══════════════════════════════════════════════════════════════════════════
#
#   ∀d ∈ Drones:
#     RemainingRange(d) < DistToDepot(d) + SafetyMargin → MustReturn(d)
#
#   Ne yapıyor: Drone'un kalan menzili, depot'a dönmeye yetecek kadar mı?
#   Yetmiyorsa veya sınırdaysa → hemen geri dön sinyali verir.
#
#   SafetyMargin neden var? Gerçek hayatta rüzgar, yağmur, batarya
#   degradasyonu gibi faktörler mesafeyi artırabilir. 50 birimlik güvenlik
#   payı bu belirsizlikleri karşılar.
#
#   R2'den farkı: R2 "bu paketi ALIP dönebilir miyim?", R5 ise
#   "şu an dönebilir miyim?" — R5 daha acil, trip'i kapatma kararı.
# ═══════════════════════════════════════════════════════════════════════════

SAFETY_MARGIN = 50.0  # PRD Section 9: drone.safety_margin_units = 50

def _r5_condition(kb: KnowledgeBase) -> bool:
    scenario: Scenario = kb.get_context("scenario")
    distance_traveled = kb.get_context("distance_traveled", 0.0)
    current_pos = kb.get_context("current_position")
    dist_matrix = kb.get_context("distance_matrix")

    if scenario is None or current_pos is None or dist_matrix is None:
        return False

    max_range = scenario.drone_fleet.max_range_per_trip
    remaining_range = max_range - distance_traveled
    dist_to_depot = _get_distance(dist_matrix, current_pos, "depot")

    return remaining_range < (dist_to_depot + SAFETY_MARGIN)


def _r5_consequent(kb: KnowledgeBase) -> list[Predicate]:
    drone_id = kb.get_context("drone_id")
    return [Predicate("MustReturn", (drone_id,))]


R5_MUST_RETURN = Rule(
    name="R5_MustReturn",
    description="RemainingRange < DistToDepot + SafetyMargin → MustReturn",
    condition=_r5_condition,
    consequent_generator=_r5_consequent,
)


# ═══════════════════════════════════════════════════════════════════════════
# R6 — PRIORITY ORDERING RULE
# ═══════════════════════════════════════════════════════════════════════════
#
#   ∀p1, p2 ∈ Packages (aynı drone, aynı trip):
#     Priority(p1) > Priority(p2) ∧ TimeWindowsCompatible
#     → PreferredOrder(p1, p2)
#
#   Ne yapıyor: Aynı trip'teki iki paket arasında, yüksek öncelikli
#   olanın önce teslim edilmesini ÖNERİR.
#
#   "Önerir" diyorum çünkü bu da soft constraint — kesin zorunluluk
#   değil. GA, bazen düşük öncelikli ama yakın olan paketi önce
#   teslim etmeyi tercih edebilir (toplam mesafe daha kısa olur).
#   Ama priority ordering ihlali fitness'ta penalize edilir.
# ═══════════════════════════════════════════════════════════════════════════

_PRIORITY_MAP = {"high": 3, "med": 2, "low": 1}


def _r6_condition(kb: KnowledgeBase) -> bool:
    scenario: Scenario = kb.get_context("scenario")
    trip_packages = kb.get_context("trip_packages", [])

    if scenario is None or len(trip_packages) < 2:
        return False

    # Trip'te en az iki farklı priority seviyesi var mı?
    priorities = set()
    for pid in trip_packages:
        pkg = _find_package(scenario, pid)
        if pkg:
            priorities.add(pkg.priority)

    return len(priorities) > 1


def _r6_consequent(kb: KnowledgeBase) -> list[Predicate]:
    scenario: Scenario = kb.get_context("scenario")
    trip_packages = kb.get_context("trip_packages", [])
    results: list[Predicate] = []

    # Her paket çifti için: yüksek priority olan önce gelmeli
    for i, pid1 in enumerate(trip_packages):
        for pid2 in trip_packages[i + 1:]:
            pkg1 = _find_package(scenario, pid1)
            pkg2 = _find_package(scenario, pid2)
            if pkg1 is None or pkg2 is None:
                continue

            p1_val = _PRIORITY_MAP.get(pkg1.priority, 0)
            p2_val = _PRIORITY_MAP.get(pkg2.priority, 0)

            if p1_val > p2_val:
                # pkg1 daha yüksek öncelikli → önce teslim edilmeli
                results.append(Predicate("PreferredOrder", (pid1, pid2)))
            elif p2_val > p1_val:
                results.append(Predicate("PreferredOrder", (pid2, pid1)))

    return results


R6_PRIORITY = Rule(
    name="R6_Priority",
    description="Priority(p1) > Priority(p2) → PreferredOrder(p1, p2)",
    condition=_r6_condition,
    consequent_generator=_r6_consequent,
)


# ═══════════════════════════════════════════════════════════════════════════
# Yardımcı fonksiyonlar
# ═══════════════════════════════════════════════════════════════════════════

def _find_package(scenario: Scenario, pkg_id: str):
    """Scenario'daki delivery point'i id ile bulur."""
    for dp in scenario.delivery_points:
        if dp.id == pkg_id:
            return dp
    return None


def _get_distance(dist_matrix: dict, from_id: str, to_id: str) -> float:
    """Distance matrix'ten iki node arası mesafeyi çeker."""
    if dist_matrix is None:
        return float("inf")
    row = dist_matrix.get(from_id)
    if row is None:
        return float("inf")
    return row.get(to_id, float("inf"))


# ═══════════════════════════════════════════════════════════════════════════
# Tüm kuralları KnowledgeBase'e kaydetme
# ═══════════════════════════════════════════════════════════════════════════

ALL_RULES = [R1_CAPACITY, R2_RANGE, R3_TIME_WINDOW, R4_NO_FLY_ZONE, R5_MUST_RETURN, R6_PRIORITY]


def register_all_rules(kb: KnowledgeBase) -> None:
    """Tüm R1-R6 kurallarını verilen KnowledgeBase'e kaydeder."""
    for rule in ALL_RULES:
        kb.add_rule(rule)
