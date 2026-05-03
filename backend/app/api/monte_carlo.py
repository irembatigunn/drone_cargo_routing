from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.models.solution import Solution
from app.core.monte_carlo import run_monte_carlo
from app.api.scenarios import _find_scenario

router = APIRouter(prefix="/api")


class MCRequest(BaseModel):
    solution: Solution
    n_iters: int = 1000
    alpha: float = 0.02


@router.post("/monte_carlo")
def monte_carlo_endpoint(req: MCRequest) -> dict:
    scenario_id = req.solution.metadata.get("scenario_id")
    scenario = _find_scenario(scenario_id) if scenario_id else None

    if not scenario:
        # Use default drone fleet spec
        from app.models.scenario import DroneFleetSpec
        fleet = DroneFleetSpec(count=4)
    else:
        fleet = scenario.drone_fleet

    return run_monte_carlo(req.solution, fleet, req.n_iters, req.alpha)
