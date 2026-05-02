from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from app.services.preset_loader import list_presets, load_preset
from app.services.data_generator import generate_scenario
from app.services.distance_matrix import build_distance_matrix
from app.models.scenario import Scenario

app = FastAPI(title="Drone Cargo Routing API")

class GenerateRequest(BaseModel):
    name: str = "custom"
    n_packages: int
    n_zones: int
    fleet_size: int
    seed: int

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/api/presets")
def get_presets():
    return {"presets": list_presets()}

@app.get("/api/presets/{preset_id}", response_model=Scenario)
def get_preset(preset_id: str):
    scenario = load_preset(preset_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Preset not found")
    return scenario

@app.post("/api/scenarios/generate", response_model=Scenario)
def generate_custom_scenario(req: GenerateRequest):
    scenario = generate_scenario(
        name=req.name,
        n_packages=req.n_packages,
        n_zones=req.n_zones,
        fleet_size=req.fleet_size,
        seed=req.seed
    )
    return scenario

@app.get("/api/presets/{preset_id}/distance-matrix")
def get_preset_distance_matrix(preset_id: str):
    scenario = load_preset(preset_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Preset not found")
    return build_distance_matrix(scenario)
