"""
Data Generator — Section 3 of PRD.
Generates reproducible synthetic scenarios with clustered Gaussian delivery points,
convex no-fly zone polygons, and homojen drone fleet specs.
"""
from __future__ import annotations

import random
import math
import numpy as np
from scipy.spatial import ConvexHull
from shapely.geometry import Point, Polygon

from app.models.scenario import (
    Scenario, Position, DeliveryPoint, NoFlyZone, DroneFleetSpec
)


SCENARIO_CONFIGS = {
    "small":  {"n_packages": 8,  "n_drones": 3, "n_zones": 2, "n_clusters": 3, "seed": 42},
    "medium": {"n_packages": 18, "n_drones": 4, "n_zones": 4, "n_clusters": 4, "seed": 137},
    "large":  {"n_packages": 35, "n_drones": 6, "n_zones": 6, "n_clusters": 5, "seed": 2024},
}


def generate_scenario(
    name: str,
    n_packages: int,
    n_zones: int,
    fleet_size: int,
    seed: int,
    n_clusters: int | None = None,
    scenario_id: str | None = None,
) -> Scenario:
    np.random.seed(seed)
    random.seed(seed)

    depot = Position(x=500.0, y=500.0)

    if n_clusters is None:
        n_clusters = max(3, min(5, n_packages // 6))

    delivery_points = _generate_delivery_points(n_packages, n_clusters, depot, seed)
    no_fly_zones = _generate_no_fly_zones(n_zones, delivery_points, depot)
    drone_fleet = DroneFleetSpec(count=fleet_size)

    return Scenario(
        id=scenario_id or f"scenario_{seed}",
        name=name,
        depot=depot,
        delivery_points=delivery_points,
        no_fly_zones=no_fly_zones,
        drone_fleet=drone_fleet,
        seed=seed,
    )


def generate_preset(preset_name: str) -> Scenario:
    cfg = SCENARIO_CONFIGS[preset_name]
    return generate_scenario(
        name=preset_name,
        n_packages=cfg["n_packages"],
        n_zones=cfg["n_zones"],
        fleet_size=cfg["n_drones"],
        seed=cfg["seed"],
        n_clusters=cfg["n_clusters"],
        scenario_id=preset_name,
    )


# ───────────────────────────────────────────────────────────────
# Internal helpers
# ───────────────────────────────────────────────────────────────

def _generate_delivery_points(
    n: int, n_clusters: int, depot: Position, seed: int
) -> list[DeliveryPoint]:
    np.random.seed(seed)
    random.seed(seed)

    sigma = 70.0
    depot_arr = np.array([depot.x, depot.y])

    # Cluster centers — radial around depot
    angles = np.random.uniform(0, 2 * math.pi, n_clusters)
    radii = np.random.uniform(150, 400, n_clusters)
    centers = np.column_stack([
        depot_arr[0] + radii * np.cos(angles),
        depot_arr[1] + radii * np.sin(angles),
    ])

    # Distribute packages per cluster
    base = n // n_clusters
    counts = [base] * n_clusters
    remainder = n - sum(counts)
    for i in range(remainder):
        counts[i % n_clusters] += 1
    # small jitter ±2
    for i in range(n_clusters):
        delta = random.randint(-2, 2)
        counts[i] = max(1, counts[i] + delta)
    # fix total
    total = sum(counts)
    while total > n:
        idx = random.randrange(n_clusters)
        if counts[idx] > 1:
            counts[idx] -= 1
            total -= 1
    while total < n:
        idx = random.randrange(n_clusters)
        counts[idx] += 1
        total += 1

    points: list[DeliveryPoint] = []
    pkg_idx = 1
    for ci, (cx, cy) in enumerate(centers):
        for _ in range(counts[ci]):
            for _attempt in range(200):
                px, py = np.random.normal([cx, cy], sigma)
                px = float(np.clip(px, 20, 980))
                py = float(np.clip(py, 20, 980))
                dist = math.hypot(px - depot.x, py - depot.y)
                if dist >= 30:
                    break
            else:
                px, py = float(cx), float(cy)

            weight = float(np.clip(np.random.normal(2.0, 1.0), 0.5, 5.0))
            priority_r = random.random()
            if priority_r < 0.5:
                priority = "low"
            elif priority_r < 0.8:
                priority = "med"
            else:
                priority = "high"

            tw_open = int(np.random.uniform(0, 180))
            is_express = random.random() < 0.20
            if is_express:
                tw_dur = int(np.random.uniform(20, 40))
            else:
                tw_dur = int(np.random.uniform(60, 120))
            tw_close = tw_open + tw_dur

            points.append(DeliveryPoint(
                id=f"pkg_{pkg_idx:03d}",
                position=Position(x=round(px, 2), y=round(py, 2)),
                weight_kg=round(weight, 2),
                priority=priority,
                time_window_open_min=tw_open,
                time_window_close_min=tw_close,
                service_time_min=2,
            ))
            pkg_idx += 1

    return points


def _generate_no_fly_zones(
    n: int,
    delivery_points: list[DeliveryPoint],
    depot: Position,
) -> list[NoFlyZone]:
    dp_points = [(dp.position.x, dp.position.y) for dp in delivery_points]
    depot_pt = Point(depot.x, depot.y)
    zones: list[NoFlyZone] = []
    existing_polys: list[Polygon] = []
    max_attempts = 1000

    for zone_idx in range(n):
        for _attempt in range(max_attempts):
            # Random center at least 150 from depot
            angle = random.uniform(0, 2 * math.pi)
            radius = random.uniform(150, 450)
            cx = 500 + radius * math.cos(angle)
            cy = 500 + radius * math.sin(angle)
            cx = float(np.clip(cx, 80, 920))
            cy = float(np.clip(cy, 80, 920))

            n_verts = random.randint(4, 6)
            avg_r = random.uniform(60, 120)

            # Polar vertices with jitter
            base_angles = np.linspace(0, 2 * math.pi, n_verts, endpoint=False)
            jitter = np.random.uniform(-0.3, 0.3, n_verts)
            vert_angles = base_angles + jitter
            vert_radii = avg_r * np.random.uniform(0.75, 1.25, n_verts)
            vx = cx + vert_radii * np.cos(vert_angles)
            vy = cy + vert_radii * np.sin(vert_angles)
            raw_verts = np.column_stack([vx, vy])

            # Convex hull
            try:
                hull = ConvexHull(raw_verts)
                hull_verts = raw_verts[hull.vertices]
            except Exception:
                continue

            poly = Polygon(hull_verts)
            if not poly.is_valid:
                continue

            # Validation rules
            if poly.contains(depot_pt):
                continue
            if any(poly.contains(Point(px, py)) for px, py in dp_points):
                continue
            if any(poly.distance(Point(px, py)) < 10 for px, py in dp_points):
                continue
            if any(poly.intersects(ep) for ep in existing_polys):
                continue

            # CCW ordering
            coords = list(hull_verts)
            if _is_clockwise(coords):
                coords = coords[::-1]

            existing_polys.append(poly)
            zones.append(NoFlyZone(
                id=f"nfz_{zone_idx + 1:02d}",
                polygon=[Position(x=round(float(x), 2), y=round(float(y), 2))
                         for x, y in coords],
            ))
            break

    return zones


def _is_clockwise(pts: list) -> bool:
    """Shoelace formula sign."""
    s = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i][0], pts[i][1]
        x1, y1 = pts[(i + 1) % n][0], pts[(i + 1) % n][1]
        s += (x1 - x0) * (y1 + y0)
    return s > 0
