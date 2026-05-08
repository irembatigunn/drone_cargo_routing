"""
Optimization API — REST endpoints for Random/NN and WebSocket for GA streaming.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.models.scenario import Scenario
from app.models.solution import Solution
from app.models.ga_config import GAConfig, FitnessWeights
from app.core.baseline_algorithms import run_random_assignment, run_nearest_neighbor
from app.core.genetic_algorithm import run_ga, compute_fitness
from app.core.monte_carlo import run_monte_carlo
from app.api.scenarios import _find_scenario, get_graph_data_for_scenario

router = APIRouter(prefix="/api")

# In-memory run storage
_runs: dict[str, dict] = {}


class OptimizeRequest(BaseModel):
    scenario_id: str
    seed: int = 42
    weights: Optional[FitnessWeights] = None


class GAOptimizeRequest(BaseModel):
    scenario_id: str
    ga_params: Optional[GAConfig] = None
    weights: Optional[FitnessWeights] = None
    seed: int = 42


@router.post("/optimize/random")
def optimize_random(req: OptimizeRequest) -> Solution:
    scenario = _find_scenario(req.scenario_id)
    if not scenario:
        raise HTTPException(404, "Scenario not found")

    graph_data = get_graph_data_for_scenario(scenario)
    weights = req.weights or FitnessWeights()
    solution = run_random_assignment(scenario, graph_data["distance_matrix"], weights, req.seed)
    # Add MC
    mc = run_monte_carlo(solution, scenario.drone_fleet)
    solution.metadata["monte_carlo"] = mc
    return solution


@router.post("/optimize/nearest_neighbor")
def optimize_nn(req: OptimizeRequest) -> Solution:
    scenario = _find_scenario(req.scenario_id)
    if not scenario:
        raise HTTPException(404, "Scenario not found")

    graph_data = get_graph_data_for_scenario(scenario)
    weights = req.weights or FitnessWeights()
    solution = run_nearest_neighbor(scenario, graph_data["distance_matrix"], weights)
    mc = run_monte_carlo(solution, scenario.drone_fleet)
    solution.metadata["monte_carlo"] = mc
    return solution


@router.post("/optimize/ga")
def start_ga(req: GAOptimizeRequest) -> dict:
    """Start GA run, returns run_id for WebSocket connection."""
    scenario = _find_scenario(req.scenario_id)
    if not scenario:
        raise HTTPException(404, "Scenario not found")

    run_id = str(uuid.uuid4())
    config = req.ga_params or GAConfig(seed=req.seed)
    config.seed = req.seed
    weights = req.weights or FitnessWeights()

    _runs[run_id] = {
        "scenario_id": req.scenario_id,
        "scenario": scenario,
        "config": config,
        "weights": weights,
        "status": "pending",
        "history": [],
        "final_solution": None,
    }
    return {"run_id": run_id}


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    if run_id not in _runs:
        raise HTTPException(404, "Run not found")
    run = _runs[run_id]
    result = {
        "run_id": run_id,
        "status": run["status"],
        "history": run["history"],
    }
    if run["final_solution"]:
        result["final_solution"] = run["final_solution"].model_dump()
    return result


@router.websocket("/ws/optimize/ga/{run_id}")
async def websocket_ga(websocket: WebSocket, run_id: str):
    """
    WebSocket endpoint for real-time GA streaming.
    Server pushes generation updates; client can send {"type": "cancel"}.
    """
    await websocket.accept()

    if run_id not in _runs:
        await websocket.send_json({"type": "error", "message": "Run not found"})
        await websocket.close()
        return

    run = _runs[run_id]
    scenario: Scenario = run["scenario"]
    config: GAConfig = run["config"]
    weights: FitnessWeights = run["weights"]

    run["status"] = "running"

    graph_data = get_graph_data_for_scenario(scenario)
    dist_matrix = graph_data["distance_matrix"]

    cancelled = False

    # Start cancel listener as a background task
    async def listen_for_cancel():
        nonlocal cancelled
        try:
            while True:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=0.1)
                if data.get("type") == "cancel":
                    cancelled = True
                    return
        except (asyncio.TimeoutError, WebSocketDisconnect):
            pass

    cancel_task = asyncio.create_task(listen_for_cancel())

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    try:
        loop = asyncio.get_running_loop()

        all_messages = []

        def ga_worker():
            for msg in run_ga(scenario, dist_matrix, config, weights):
                if cancelled:
                    break
                all_messages.append(msg)

        future = loop.run_in_executor(executor, ga_worker)

        sent_count = 0
        while not future.done():
            await asyncio.sleep(0.05)
            while sent_count < len(all_messages):
                if cancelled:
                    break
                msg = all_messages[sent_count]
                sent_count += 1

                if msg["type"] == "generation":
                    sol = msg["best_solution"]
                    await websocket.send_json({
                        "type": "generation",
                        "generation": msg["generation"],
                        "best_fitness": msg["best_fitness"],
                        "mean_fitness": msg["mean_fitness"],
                        "best_solution": sol.model_dump(),
                    })
                    run["history"].append({
                        "gen": msg["generation"],
                        "bestFitness": msg["best_fitness"],
                        "meanFitness": msg["mean_fitness"],
                    })

            if cancelled:
                break

        # Drain remaining messages
        if not cancelled:
            await future
            while sent_count < len(all_messages):
                msg = all_messages[sent_count]
                sent_count += 1
                if msg["type"] == "complete":
                    final_solution = msg["final_solution"]
                    mc = run_monte_carlo(final_solution, scenario.drone_fleet)
                    final_solution.metadata["monte_carlo"] = mc
                    run["final_solution"] = final_solution
                    run["status"] = "complete"

                    await websocket.send_json({
                        "type": "complete",
                        "final_solution": final_solution.model_dump(),
                        "compute_time_seconds": msg.get("compute_time_seconds", 0),
                        "convergence_generation": msg.get("convergence_generation", 0),
                    })
                elif msg["type"] == "generation":
                    sol = msg["best_solution"]
                    await websocket.send_json({
                        "type": "generation",
                        "generation": msg["generation"],
                        "best_fitness": msg["best_fitness"],
                        "mean_fitness": msg["mean_fitness"],
                        "best_solution": sol.model_dump(),
                    })

    except WebSocketDisconnect:
        run["status"] = "disconnected"
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
        run["status"] = "error"
    finally:
        cancel_task.cancel()
        executor.shutdown(wait=False)
        try:
            await websocket.close()
        except Exception:
            pass


class BatchGARequest(BaseModel):
    scenario_id: str
    ga_params: Optional[GAConfig] = None
    weights: Optional[FitnessWeights] = None
    seed: int = 42
    n_runs: int = 30


@router.post("/optimize/batch_ga")
def batch_ga(req: BatchGARequest) -> dict:
    """
    Run GA n_runs times with different seeds (PRD §5.4.3 comparison protocol).
    Returns mean ± std for total_distance, total_time_min, time_window_violations, fitness.
    Single-threaded; n_runs=30 may take a few minutes for large scenarios.
    """
    from app.core.evaluation import run_ga_batch

    scenario = _find_scenario(req.scenario_id)
    if not scenario:
        raise HTTPException(404, "Scenario not found")

    graph_data = get_graph_data_for_scenario(scenario)
    dist_matrix = graph_data["distance_matrix"]

    config = req.ga_params or GAConfig(seed=req.seed)
    config.seed = req.seed
    weights = req.weights or FitnessWeights()

    stats = run_ga_batch(scenario, dist_matrix, config, weights, n_runs=req.n_runs)
    return stats
