from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.scenarios import router as scenarios_router
from app.api.optimization import router as optimization_router
from app.api.monte_carlo import router as mc_router

app = FastAPI(
    title="Drone Cargo Routing Optimization API",
    version="1.0.0",
    description="Multi-drone, time-windowed, obstacle-aware cargo routing with GA + Logic Engine",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scenarios_router)
app.include_router(optimization_router)
app.include_router(mc_router)


@app.get("/")
def root():
    return {"status": "ok", "service": "drone-routing-api"}


@app.get("/health")
def health():
    return {"status": "healthy"}
