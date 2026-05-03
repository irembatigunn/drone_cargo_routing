export interface Position {
  x: number
  y: number
}

export interface DeliveryPoint {
  id: string
  position: Position
  weight_kg: number
  priority: 'low' | 'med' | 'high'
  time_window_open_min: number
  time_window_close_min: number
  service_time_min: number
}

export interface NoFlyZone {
  id: string
  polygon: Position[]
}

export interface DroneFleetSpec {
  count: number
  max_payload_kg: number
  max_range_per_trip: number
  speed_units_per_min: number
  recharge_time_min: number
}

export interface Scenario {
  id: string
  name: string
  canvas_width: number
  canvas_height: number
  depot: Position
  delivery_points: DeliveryPoint[]
  no_fly_zones: NoFlyZone[]
  drone_fleet: DroneFleetSpec
  simulation_horizon_min: number
  seed: number
}

export interface Trip {
  sequence: string[]
  distance: number
  duration_min: number
}

export interface DroneRoute {
  drone_id: string
  trips: Trip[]
}

export interface MonteCarloResult {
  expected_success_rate: number
  ci_lower: number
  ci_upper: number
  std: number
  n_iterations: number
}

export interface Solution {
  routes: DroneRoute[]
  unassigned_packages: string[]
  total_distance: number
  total_time_min: number
  time_window_violations: number
  capacity_violations: number
  fitness: number
  algorithm: 'random' | 'nearest_neighbor' | 'ga'
  metadata: Record<string, any>
}

export interface GAConfig {
  population_size: number
  generations: number
  mutation_rate: number
  crossover_rate: number
  tournament_size: number
  elitism: number
  convergence_patience: number
  nn_seed_ratio: number
  seed: number
}

export interface FitnessWeights {
  w_distance: number
  w_time_violation: number
  w_unassigned: number
  penalty_per_violation: number
}

export interface GenerationMessage {
  type: 'generation'
  generation: number
  best_fitness: number
  mean_fitness: number
  best_solution: Solution
}

export interface CompleteMessage {
  type: 'complete'
  final_solution: Solution
  compute_time_seconds: number
  convergence_generation: number
}

export type WSMessage = GenerationMessage | CompleteMessage | { type: 'error'; message: string }

export interface VisibilityEdge {
  from: Position
  to: Position
  weight: number
}

export interface GraphData {
  distance_matrix: Record<string, Record<string, number>>
  centrality: { centrality: Record<string, number>; frobenius_norm: number; eigenvalue: number }
  paths: Record<string, Position[]>
  interest_keys: string[]
}
