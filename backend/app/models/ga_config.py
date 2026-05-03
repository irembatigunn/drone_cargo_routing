from pydantic import BaseModel, Field


class GAConfig(BaseModel):
    population_size: int = Field(default=50, ge=20, le=200)
    generations: int = Field(default=200, ge=50, le=500)
    mutation_rate: float = Field(default=0.15, ge=0.01, le=0.5)
    crossover_rate: float = Field(default=0.8, ge=0.5, le=1.0)
    tournament_size: int = Field(default=3, ge=2, le=10)
    elitism: int = Field(default=2, ge=0, le=5)
    convergence_patience: int = Field(default=50, ge=10, le=100)
    nn_seed_ratio: float = Field(default=0.20, ge=0.0, le=0.5)
    seed: int = 42


class FitnessWeights(BaseModel):
    w_distance: float = Field(default=1.0, ge=0.1, le=10.0)
    w_time_violation: float = Field(default=50.0, ge=0.0, le=500.0)
    w_unassigned: float = Field(default=500.0, ge=0.0, le=5000.0)
    penalty_per_violation: float = 100.0
