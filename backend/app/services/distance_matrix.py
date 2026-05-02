import math
from typing import Dict, Any
from app.models.scenario import Scenario, Position

def euclidean_distance(a: Position, b: Position) -> float:
    return math.sqrt((a.x - b.x)**2 + (a.y - b.y)**2)

def build_distance_matrix(scenario: Scenario) -> Dict[str, Any]:
    nodes = []
    nodes.append({"id": "depot", "pos": scenario.depot})
    for dp in scenario.delivery_points:
        nodes.append({"id": dp.id, "pos": dp.position})
        
    matrix = {}
    for n1 in nodes:
        matrix[n1["id"]] = {}
        for n2 in nodes:
            matrix[n1["id"]][n2["id"]] = euclidean_distance(n1["pos"], n2["pos"])
            
    return {
        "nodes": [n["id"] for n in nodes],
        "matrix": matrix
    }
