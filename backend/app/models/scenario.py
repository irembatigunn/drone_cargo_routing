from pydantic import BaseModel
from typing import List, Literal

class Position(BaseModel):
    x: float
    y: float

class DeliveryPoint(BaseModel):
    id: str
    position: Position
    weight_kg: float
    priority: Literal["low", "med", "high"]
    time_window_open_min: int
    time_window_close_min: int
    service_time_min: int = 2

class NoFlyZone(BaseModel):
    id: str
    polygon: List[Position]

class DroneFleetSpec(BaseModel):
    count: int
    max_payload_kg: float = 5.0
    max_range_per_trip: float = 800.0
    speed_units_per_min: float = 100.0
    recharge_time_min: int = 10

class Scenario(BaseModel):
    id: str
    name: str
    canvas_width: int = 1000
    canvas_height: int = 1000
    depot: Position
    delivery_points: List[DeliveryPoint]
    no_fly_zones: List[NoFlyZone]
    drone_fleet: DroneFleetSpec
    seed: int
