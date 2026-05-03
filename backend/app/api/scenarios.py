"""
Scenarios API — preset loading, custom generation, save.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.scenario import Scenario
from app.core.data_generator import generate_scenario, generate_preset, SCENARIO_CONFIGS
from app.core.visibility_graph import build_visibility_graph_and_matrix
from app.core.linear_algebra import compute_centrality

router = APIRouter(prefix="/api")

PRESETS_DIR = Path(__file__).parent.parent.parent / "presets"
SAVED_RUNS_DIR = Path(__file__).parent.parent.parent / "saved_runs"
SAVED_RUNS_DIR.mkdir(exist_ok=True)

# In-memory cache: scenario_id → computed graph data
_graph_cache: dict[str, dict] = {}

# In-memory cache: scenario_id → Scenario object (for custom/generated scenarios)
_scenario_cache: dict[str, "Scenario"] = {}


def _get_or_compute_graph(scenario: Scenario) -> dict:
    if scenario.id not in _graph_cache:
        graph_data = build_visibility_graph_and_matrix(scenario)
        centrality = compute_centrality(
            graph_data["interest_keys"],
            graph_data["distance_matrix"],
        )
        graph_data["centrality"] = centrality
        _graph_cache[scenario.id] = graph_data
    return _graph_cache[scenario.id]


@router.get("/presets")
def list_presets():
    return {"presets": list(SCENARIO_CONFIGS.keys())}


@router.get("/presets/{preset_id}")
def get_preset(preset_id: str) -> Scenario:
    # Try loading from JSON first
    path = PRESETS_DIR / f"{preset_id}.json"
    if path.exists():
        return Scenario.model_validate_json(path.read_text())

    if preset_id not in SCENARIO_CONFIGS:
        raise HTTPException(404, f"Preset '{preset_id}' not found")

    scenario = generate_preset(preset_id)
    # Cache graph
    _get_or_compute_graph(scenario)
    return scenario


class GenerateRequest(BaseModel):
    n_packages: int = 18
    n_zones: int = 4
    fleet_size: int = 4
    seed: int = 42
    name: Optional[str] = None


@router.post("/scenarios/generate")
def generate_custom(req: GenerateRequest) -> Scenario:
    sid = f"custom_{req.seed}_{req.n_packages}"
    scenario = generate_scenario(
        name=req.name or f"Custom ({req.n_packages} pkgs)",
        n_packages=req.n_packages,
        n_zones=req.n_zones,
        fleet_size=req.fleet_size,
        seed=req.seed,
        scenario_id=sid,
    )
    # Store in scenario cache so subsequent requests can find it
    _scenario_cache[sid] = scenario
    _get_or_compute_graph(scenario)
    return scenario


@router.post("/scenarios/save")
def save_scenario(scenario: Scenario):
    path = SAVED_RUNS_DIR / f"{scenario.id}.json"
    path.write_text(scenario.model_dump_json(indent=2))
    return {"saved": str(path)}


@router.get("/scenarios/{scenario_id}/graph_data")
def get_graph_data(scenario_id: str):
    """Return distance matrix and centrality scores."""
    # Find scenario
    scenario = _find_scenario(scenario_id)
    if not scenario:
        raise HTTPException(404, "Scenario not found")

    graph_data = _get_or_compute_graph(scenario)
    dm = graph_data["distance_matrix"]
    paths = graph_data["path_cache"]

    # Serialize paths (tuple keys → string)
    paths_serialized = {
        f"{k[0]}::{k[1]}": [{"x": p.x, "y": p.y} for p in v]
        for k, v in paths.items()
    }

    return {
        "distance_matrix": dm,
        "centrality": graph_data["centrality"],
        "paths": paths_serialized,
        "interest_keys": graph_data["interest_keys"],
    }


@router.get("/scenarios/{scenario_id}/visibility_edges")
def get_visibility_edges(scenario_id: str):
    """Return all edges of the visibility graph for rendering."""
    scenario = _find_scenario(scenario_id)
    if not scenario:
        raise HTTPException(404, "Scenario not found")

    graph_data = _get_or_compute_graph(scenario)
    G = graph_data["graph"]
    nodes = graph_data["nodes"]

    edges = []
    for u, v, data in G.edges(data=True):
        if u in nodes and v in nodes:
            edges.append({
                "from": {"x": nodes[u].x, "y": nodes[u].y},
                "to": {"x": nodes[v].x, "y": nodes[v].y},
                "weight": round(data.get("weight", 0), 2),
            })
    return {"edges": edges}


def _find_scenario(scenario_id: str) -> Scenario | None:
    # In-memory custom/generated scenarios (checked first — fastest)
    if scenario_id in _scenario_cache:
        return _scenario_cache[scenario_id]
    # Presets
    path = PRESETS_DIR / f"{scenario_id}.json"
    if path.exists():
        return Scenario.model_validate_json(path.read_text())
    if scenario_id in SCENARIO_CONFIGS:
        s = generate_preset(scenario_id)
        return s
    # Saved runs
    path2 = SAVED_RUNS_DIR / f"{scenario_id}.json"
    if path2.exists():
        return Scenario.model_validate_json(path2.read_text())
    return None


def get_graph_data_for_scenario(scenario: Scenario) -> dict:
    return _get_or_compute_graph(scenario)
