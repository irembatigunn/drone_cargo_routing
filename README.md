# Drone Cargo Routing Optimization System

Multi-drone, time-windowed, obstacle-aware 2D cargo routing with:
- **Logic Engine** (Forward-chaining, R1-R6 rules, Modus Ponens)
- **Visibility Graph + Dijkstra** (obstacle-aware distance matrix)
- **Genetic Algorithm** (BCRC crossover, 3 mutation ops, repair)
- **Monte Carlo** (expected delivery success rate)
- **Eigenvector Centrality** (power iteration, Frobenius norm)
- **React/Konva.js** real-time visualization with WebSocket GA streaming

---

## Quick Start

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
python ../scripts/generate_presets.py   # generate preset JSONs
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend2
npm install
npm run dev       # runs on http://localhost:5173
```

### 3. Tests

```bash
cd backend
pytest tests/test_all.py -v
```

---

## Project Structure

```
drone-routing-system/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app
│   │   ├── config.py                  # Default params
│   │   ├── api/
│   │   │   ├── scenarios.py           # REST: presets, generate, save
│   │   │   ├── optimization.py        # REST + WebSocket: algorithms
│   │   │   └── monte_carlo.py
│   │   ├── core/
│   │   │   ├── data_generator.py      # Clustered Gaussian scenario generation
│   │   │   ├── visibility_graph.py    # Shapely + NetworkX visibility graph
│   │   │   ├── logic_engine.py        # Forward-chaining engine + R1-R6
│   │   │   ├── genetic_algorithm.py   # GA with BCRC crossover, repair
│   │   │   ├── ga_operators.py        # Crossover, mutation, selection ops
│   │   │   ├── baseline_algorithms.py # Random + Nearest Neighbor
│   │   │   ├── monte_carlo.py         # 1000-iter MC simulation
│   │   │   ├── linear_algebra.py      # Power iteration eigenvector centrality
│   │   │   └── evaluation.py          # Metrics + 30-run batch stats
│   │   └── models/
│   │       ├── scenario.py            # Pydantic v2 domain models
│   │       ├── solution.py
│   │       └── ga_config.py
│   ├── presets/
│   │   ├── small.json                 # 8 pkgs, 3 drones, seed=42
│   │   ├── medium.json                # 18 pkgs, 4 drones, seed=137
│   │   └── large.json                 # 35 pkgs, 6 drones, seed=2024
│   ├── tests/
│   │   └── test_all.py                # 29 unit tests (all pass)
│   └── requirements.txt
│
├── frontend2/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── components/
│   │   │   ├── Canvas/CanvasStage.tsx  # Konva.js multi-layer canvas
│   │   │   ├── ConfigPanel/           # GA params, weights, toggles
│   │   │   ├── MetricsPanel/          # Recharts convergence, KPI table
│   │   │   └── TopBar/                # Run/cancel, animation controls
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts        # Native WS for GA streaming
│   │   │   └── useAnimation.ts        # Timeline interpolation engine
│   │   ├── store/appStore.ts          # Zustand global state
│   │   ├── api/client.ts              # Axios API calls
│   │   └── types/domain.ts            # TypeScript domain types
│   └── package.json
│
├── scripts/
│   ├── generate_presets.py
│   └── benchmark.py
└── README.md
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/presets` | List preset names |
| GET | `/api/presets/{id}` | Full Scenario object |
| POST | `/api/scenarios/generate` | Custom scenario |
| GET | `/api/scenarios/{id}/graph_data` | Distance matrix + centrality |
| GET | `/api/scenarios/{id}/visibility_edges` | Visibility graph edges |
| POST | `/api/optimize/random` | Random assignment |
| POST | `/api/optimize/nearest_neighbor` | NN heuristic |
| POST | `/api/optimize/ga` | Start GA → returns run_id |
| WS | `/ws/optimize/ga/{run_id}` | Real-time GA streaming |
| GET | `/api/runs/{run_id}` | Run history + final solution |

---

## Algorithm Performance (medium preset)

| Algorithm | Dist | Unassigned | Fitness |
|-----------|------|------------|---------|
| Random | ~8300 | 0 | ~8300 |
| Nearest Neighbor | ~6950 | 0 | ~6950 |
| GA (50 gen) | ~6570 | 0 | ~6570 |
