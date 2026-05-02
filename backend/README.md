# Drone Cargo Routing Optimization System - Backend

## Setup
1. Open terminal and navigate to backend: `cd backend`
2. Create a virtual environment: `python -m venv venv`
3. Activate it: `venv\Scripts\activate` (Windows)
4. Install dependencies: `pip install -r requirements.txt`

## Run
Start the development server:
`uvicorn app.main:app --reload`

## Available Endpoints
- `GET /health` : Health check
- `GET /api/presets` : List preset scenario IDs
- `GET /api/presets/{preset_id}` : Get a specific preset scenario
- `POST /api/scenarios/generate` : Generate a custom scenario
- `GET /api/presets/{preset_id}/distance-matrix` : Get the distance matrix for a preset
