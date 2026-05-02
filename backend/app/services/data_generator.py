import numpy as np
import uuid
import math
from app.models.scenario import Scenario, Position, DeliveryPoint, NoFlyZone, DroneFleetSpec

def generate_scenario(name: str, n_packages: int, n_zones: int, fleet_size: int, seed: int) -> Scenario:
    np.random.seed(seed)
    
    # Depot
    depot = Position(x=500.0, y=500.0)
    
    # Drone Fleet
    fleet = DroneFleetSpec(
        count=fleet_size,
        max_payload_kg=5.0,
        max_range_per_trip=800.0,
        speed_units_per_min=100.0,
        recharge_time_min=10
    )
    
    # Delivery points
    delivery_points = []
    if n_packages <= 10:
        k = 3
    elif n_packages <= 20:
        k = 4
    else:
        k = 5
        
    cluster_centers = []
    for _ in range(k):
        angle = np.random.uniform(0, 2 * math.pi)
        radius = np.random.uniform(150, 400)
        cx = 500 + radius * math.cos(angle)
        cy = 500 + radius * math.sin(angle)
        cluster_centers.append((cx, cy))
        
    packages_per_cluster = [n_packages // k] * k
    for i in range(n_packages % k):
        packages_per_cluster[i] += 1
        
    pkg_idx = 1
    for c_idx, (cx, cy) in enumerate(cluster_centers):
        for _ in range(packages_per_cluster[c_idx]):
            while True:
                px = np.random.normal(cx, 70)
                py = np.random.normal(cy, 70)
                px = np.clip(px, 20, 980)
                py = np.clip(py, 20, 980)
                
                dist = math.sqrt((px - 500)**2 + (py - 500)**2)
                if dist >= 30:
                    break
            
            weight = float(np.clip(np.random.normal(2.0, 1.0), 0.5, 5.0))
            priority_val = np.random.choice(["low", "med", "high"], p=[0.5, 0.3, 0.2])
            open_min = int(np.random.uniform(0, 180))
            
            is_express = np.random.rand() < 0.2
            if is_express:
                duration = int(np.random.uniform(20, 40))
            else:
                duration = int(np.random.uniform(60, 120))
                
            close_min = open_min + duration
            
            dp = DeliveryPoint(
                id=f"pkg_{pkg_idx:03d}",
                position=Position(x=float(px), y=float(py)),
                weight_kg=weight,
                priority=priority_val,
                time_window_open_min=open_min,
                time_window_close_min=close_min,
                service_time_min=2
            )
            delivery_points.append(dp)
            pkg_idx += 1
            
    # No fly zones
    no_fly_zones = []
    zone_idx = 1
    for _ in range(n_zones):
        while True:
            zx = np.random.uniform(100, 900)
            zy = np.random.uniform(100, 900)
            dist_depot = math.sqrt((zx - 500)**2 + (zy - 500)**2)
            if dist_depot >= 150:
                break
                
        n_vertices = 4
        avg_r = np.random.uniform(60, 120)
        
        polygon = []
        angles = np.linspace(0, 2 * math.pi, n_vertices, endpoint=False)
        for angle in angles:
            jitter = np.random.uniform(-0.2, 0.2)
            r = avg_r * np.random.uniform(0.75, 1.25)
            vx = zx + r * math.cos(angle + jitter)
            vy = zy + r * math.sin(angle + jitter)
            polygon.append(Position(x=float(vx), y=float(vy)))
            
        nfz = NoFlyZone(
            id=f"zone_{zone_idx:03d}",
            polygon=polygon
        )
        no_fly_zones.append(nfz)
        zone_idx += 1
        
    scenario_id = str(uuid.uuid4())
    scenario = Scenario(
        id=scenario_id,
        name=name,
        canvas_width=1000,
        canvas_height=1000,
        depot=depot,
        delivery_points=delivery_points,
        no_fly_zones=no_fly_zones,
        drone_fleet=fleet,
        seed=seed
    )
    return scenario
