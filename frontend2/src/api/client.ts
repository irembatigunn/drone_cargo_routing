import axios from 'axios'
import type { Scenario, Solution, GAConfig, FitnessWeights, GraphData, VisibilityEdge } from '../types/domain'

const api = axios.create({ baseURL: '/api' })

export const scenarioApi = {
  listPresets: () => api.get<{ presets: string[] }>('/presets').then(r => r.data),
  getPreset: (id: string) => api.get<Scenario>(`/presets/${id}`).then(r => r.data),
  generate: (params: { n_packages: number; n_zones: number; fleet_size: number; seed: number; name?: string }) =>
    api.post<Scenario>('/scenarios/generate', params).then(r => r.data),
  save: (scenario: Scenario) => api.post('/scenarios/save', scenario).then(r => r.data),
  getGraphData: (id: string) => api.get<GraphData>(`/scenarios/${id}/graph_data`).then(r => r.data),
  getVisibilityEdges: (id: string) => api.get<{ edges: VisibilityEdge[] }>(`/scenarios/${id}/visibility_edges`).then(r => r.data),
}

export const optimizationApi = {
  runRandom: (scenarioId: string, seed: number, weights?: FitnessWeights) =>
    api.post<Solution>('/optimize/random', { scenario_id: scenarioId, seed, weights }).then(r => r.data),
  runNN: (scenarioId: string, weights?: FitnessWeights) =>
    api.post<Solution>('/optimize/nearest_neighbor', { scenario_id: scenarioId, weights }).then(r => r.data),
  startGA: (scenarioId: string, gaParams: GAConfig, weights: FitnessWeights, seed: number) =>
    api.post<{ run_id: string }>('/optimize/ga', {
      scenario_id: scenarioId,
      ga_params: gaParams,
      weights,
      seed,
    }).then(r => r.data),
  getRun: (runId: string) => api.get(`/runs/${runId}`).then(r => r.data),
}
