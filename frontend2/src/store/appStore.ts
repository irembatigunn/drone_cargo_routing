import { create } from 'zustand'
import type {
  Scenario, Solution, GAConfig, FitnessWeights,
  GraphData, Position, VisibilityEdge
} from '../types/domain'

export interface RunHistory {
  gen: number
  bestFitness: number
  meanFitness: number
}

interface CurrentRun {
  runId: string
  algorithm: 'random' | 'nn' | 'ga'
  status: 'idle' | 'running' | 'complete' | 'error'
  progress: number
  history: RunHistory[]
  currentGenSolution: Solution | null
}

interface AnimationState {
  isPlaying: boolean
  currentTime: number
  dronePositions: Record<string, Position>
  speed: number
}

interface AppState {
  // Scenario
  scenario: Scenario | null
  graphData: GraphData | null
  visibilityEdges: VisibilityEdge[]

  // Solutions
  solutions: {
    random?: Solution
    nn?: Solution
    ga?: Solution
  }

  // Current GA run
  currentRun: CurrentRun | null

  // Config
  gaConfig: GAConfig
  weights: FitnessWeights
  seed: number

  // Visualization toggles
  visualization: {
    showVisibilityGraph: boolean
    showCentrality: boolean
    showTripNumbers: boolean
    animationSpeed: number
    selectedAlgo: 'random' | 'nn' | 'ga'
    highlightedDroneId: string | null
    highlightedPkgId: string | null
  }

  // Animation
  animation: AnimationState

  // UI state
  isRunning: boolean
  activePreset: string

  // Actions
  setScenario: (s: Scenario) => void
  setGraphData: (g: GraphData) => void
  setVisibilityEdges: (e: VisibilityEdge[]) => void
  setSolution: (algo: 'random' | 'nn' | 'ga', s: Solution) => void
  setCurrentRun: (run: CurrentRun | null) => void
  updateRunProgress: (gen: number, bestF: number, meanF: number, sol: Solution) => void
  completeRun: (sol: Solution) => void
  setGAConfig: (c: Partial<GAConfig>) => void
  setWeights: (w: Partial<FitnessWeights>) => void
  setSeed: (s: number) => void
  setVisualization: (v: Partial<AppState['visualization']>) => void
  setAnimation: (a: Partial<AnimationState>) => void
  setIsRunning: (b: boolean) => void
  setActivePreset: (p: string) => void
  resetRun: () => void
}

export const useAppStore = create<AppState>((set, get) => ({
  scenario: null,
  graphData: null,
  visibilityEdges: [],
  solutions: {},
  currentRun: null,
  isRunning: false,
  activePreset: 'medium',

  gaConfig: {
    population_size: 50,
    generations: 200,
    mutation_rate: 0.15,
    crossover_rate: 0.8,
    tournament_size: 3,
    elitism: 2,
    convergence_patience: 50,
    nn_seed_ratio: 0.2,
    seed: 42,
  },

  weights: {
    w_distance: 1.0,
    w_time_violation: 50.0,
    w_unassigned: 500.0,
    penalty_per_violation: 100.0,
  },

  seed: 42,

  visualization: {
    showVisibilityGraph: false,
    showCentrality: false,
    showTripNumbers: false,
    animationSpeed: 5,
    selectedAlgo: 'ga',
    highlightedDroneId: null,
    highlightedPkgId: null,
  },

  animation: {
    isPlaying: false,
    currentTime: 0,
    dronePositions: {},
    speed: 5,
  },

  setScenario: (s) => set({ scenario: s }),
  setGraphData: (g) => set({ graphData: g }),
  setVisibilityEdges: (e) => set({ visibilityEdges: e }),
  setSolution: (algo, s) => set((state) => ({ solutions: { ...state.solutions, [algo]: s } })),

  setCurrentRun: (run) => set({ currentRun: run }),

  updateRunProgress: (gen, bestF, meanF, sol) => set((state) => {
    if (!state.currentRun) return {}
    const maxGen = state.gaConfig.generations
    return {
      currentRun: {
        ...state.currentRun,
        progress: Math.round((gen / maxGen) * 100),
        history: [...state.currentRun.history, { gen, bestFitness: bestF, meanFitness: meanF }],
        currentGenSolution: sol,
      }
    }
  }),

  completeRun: (sol) => set((state) => ({
    solutions: { ...state.solutions, ga: sol },
    currentRun: state.currentRun ? { ...state.currentRun, status: 'complete', progress: 100 } : null,
    isRunning: false,
  })),

  setGAConfig: (c) => set((state) => ({ gaConfig: { ...state.gaConfig, ...c } })),
  setWeights: (w) => set((state) => ({ weights: { ...state.weights, ...w } })),
  setSeed: (s) => set({ seed: s }),
  setVisualization: (v) => set((state) => ({ visualization: { ...state.visualization, ...v } })),
  setAnimation: (a) => set((state) => ({ animation: { ...state.animation, ...a } })),
  setIsRunning: (b) => set({ isRunning: b }),
  setActivePreset: (p) => set({ activePreset: p }),
  resetRun: () => set({
    currentRun: null,
    solutions: {},
    isRunning: false,
    animation: { isPlaying: false, currentTime: 0, dronePositions: {}, speed: 5 },
  }),
}))
