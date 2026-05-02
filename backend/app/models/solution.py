from pydantic import BaseModel
from typing import List, Literal

class Trip(BaseModel):
    sequence: List[str]
    distance: float
    duration_min: float

class DroneRoute(BaseModel):
    drone_id: str
    trips: List[Trip]

class Solution(BaseModel):
    routes: List[DroneRoute]
    unassigned_packages: List[str]
    total_distance: float
    total_time_min: float
    time_window_violations: int
    capacity_violations: int
    fitness: float
    algorithm: Literal["random", "nearest_neighbor", "ga"]
    metadata: dict
