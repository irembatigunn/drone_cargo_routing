from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


class Trip(BaseModel):
    sequence: list[str]  # delivery point IDs; depot start/end implicit
    distance: float
    duration_min: float


class DroneRoute(BaseModel):
    drone_id: str
    trips: list[Trip]


class Solution(BaseModel):
    routes: list[DroneRoute]
    unassigned_packages: list[str]
    total_distance: float
    total_time_min: float
    time_window_violations: int
    capacity_violations: int
    fitness: float
    algorithm: Literal["random", "nearest_neighbor", "ga"]
    metadata: dict = {}
