import { useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { scenarioApi } from '../../api/client'

interface SectionProps {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
}

function Section({ title, children, defaultOpen = false }: SectionProps) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div style={{ borderBottom: '1px solid rgba(255,255,255,0.06)', marginBottom: 2 }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '8px 12px', background: 'transparent', border: 'none',
          color: '#94a3b8', fontFamily: 'Space Mono, monospace', fontSize: 10,
          cursor: 'pointer', letterSpacing: '0.08em', textTransform: 'uppercase',
        }}
      >
        {title}
        <span style={{ color: open ? '#38bdf8' : '#475569', fontSize: 12 }}>{open ? '▾' : '▸'}</span>
      </button>
      {open && <div style={{ padding: '0 12px 12px' }}>{children}</div>}
    </div>
  )
}

function Slider({ label, value, min, max, step = 0.01, onChange }: {
  label: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void
}) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ color: '#64748b', fontSize: 10, fontFamily: 'Space Mono, monospace' }}>{label}</span>
        <span style={{ color: '#e2e8f0', fontSize: 10, fontFamily: 'Space Mono, monospace' }}>{value}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(Number(e.target.value))}
        style={{ width: '100%', accentColor: '#38bdf8' }}
      />
    </div>
  )
}

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
      <span style={{ color: '#64748b', fontSize: 10, fontFamily: 'Space Mono, monospace' }}>{label}</span>
      <button
        onClick={() => onChange(!value)}
        style={{
          width: 36, height: 20, borderRadius: 10, border: 'none', cursor: 'pointer',
          background: value ? '#38bdf8' : '#1e293b', position: 'relative', transition: 'background 0.2s',
        }}
      >
        <div style={{
          width: 14, height: 14, borderRadius: '50%', background: 'white',
          position: 'absolute', top: 3, left: value ? 19 : 3, transition: 'left 0.2s',
        }} />
      </button>
    </div>
  )
}

export function ConfigPanel() {
  const {
    gaConfig, weights, seed, visualization, selectedAlgos,
    setGAConfig, setWeights, setSeed, setVisualization,
    setSelectedAlgos, setActivePreset, activePreset, setScenario, setGraphData,
    setVisibilityEdges, resetRun,
  } = useAppStore()

  const [customModal, setCustomModal] = useState(false)
  const [customParams, setCustomParams] = useState({ n_packages: 18, n_zones: 4, fleet_size: 4, seed: 99 })
  const [loadingPreset, setLoadingPreset] = useState(false)

  const loadPreset = async (name: string) => {
    setLoadingPreset(true)
    resetRun()
    try {
      const scenario = await scenarioApi.getPreset(name)
      setScenario(scenario)
      setActivePreset(name)
      const gd = await scenarioApi.getGraphData(scenario.id)
      setGraphData(gd)
      const edgesData = await scenarioApi.getVisibilityEdges(scenario.id)
      setVisibilityEdges(edgesData.edges)
    } catch (e) {
      console.error('Failed to load preset', e)
    } finally {
      setLoadingPreset(false)
    }
  }

  const generateCustom = async () => {
    setLoadingPreset(true)
    resetRun()
    setCustomModal(false)
    try {
      const scenario = await scenarioApi.generate(customParams)
      setScenario(scenario)
      setActivePreset('custom')
      const gd = await scenarioApi.getGraphData(scenario.id)
      setGraphData(gd)
      const edgesData = await scenarioApi.getVisibilityEdges(scenario.id)
      setVisibilityEdges(edgesData.edges)
    } catch (e) {
      console.error('Failed to generate', e)
    } finally {
      setLoadingPreset(false)
    }
  }

  return (
    <div style={{
      width: '100%', height: '100%', overflowY: 'auto',
      background: '#0d1321', borderRight: '1px solid rgba(255,255,255,0.07)',
    }}>
      <div style={{ padding: '14px 12px 8px', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
        <div style={{ color: '#38bdf8', fontFamily: 'Space Mono, monospace', fontSize: 11, letterSpacing: '0.1em' }}>
          CONFIG
        </div>
      </div>

      {/* Scenario Section */}
      <Section title="Scenario" defaultOpen>
        <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
          {['small', 'medium', 'large'].map(p => (
            <button
              key={p}
              onClick={() => loadPreset(p)}
              disabled={loadingPreset}
              style={{
                flex: 1, padding: '5px 0', borderRadius: 6, border: '1px solid',
                borderColor: activePreset === p ? '#38bdf8' : 'rgba(255,255,255,0.1)',
                background: activePreset === p ? 'rgba(56,189,248,0.12)' : '#0f172a',
                color: activePreset === p ? '#38bdf8' : '#475569',
                fontFamily: 'Space Mono, monospace', fontSize: 9, cursor: 'pointer',
              }}
            >
              {p.toUpperCase()}
            </button>
          ))}
        </div>
        <button
          onClick={() => setCustomModal(true)}
          style={{
            width: '100%', padding: '6px 0', borderRadius: 6,
            border: '1px solid rgba(255,255,255,0.1)', background: '#0f172a',
            color: '#64748b', fontFamily: 'Space Mono, monospace', fontSize: 9, cursor: 'pointer',
          }}
        >
          + CUSTOM SCENARIO
        </button>
        {loadingPreset && (
          <div style={{ color: '#38bdf8', fontSize: 9, fontFamily: 'Space Mono', marginTop: 6, textAlign: 'center' }}>
            Loading...
          </div>
        )}
      </Section>

      {/* Algorithm Selection */}
      <Section title="Algorithms" defaultOpen>
        {([
          { key: 'random' as const, label: 'Random Assignment' },
          { key: 'nn' as const, label: 'Nearest Neighbor' },
          { key: 'ga' as const, label: 'Genetic Algorithm' },
        ]).map(({ key, label }) => (
          <div key={key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <span style={{ color: selectedAlgos[key] ? '#e2e8f0' : '#475569', fontSize: 10, fontFamily: 'Space Mono, monospace' }}>{label}</span>
            <button
              onClick={() => setSelectedAlgos({ [key]: !selectedAlgos[key] })}
              style={{
                width: 36, height: 20, borderRadius: 10, border: 'none', cursor: 'pointer',
                background: selectedAlgos[key] ? '#38bdf8' : '#1e293b', position: 'relative', transition: 'background 0.2s',
              }}
            >
              <div style={{
                width: 14, height: 14, borderRadius: '50%', background: 'white',
                position: 'absolute', top: 3, left: selectedAlgos[key] ? 19 : 3, transition: 'left 0.2s',
              }} />
            </button>
          </div>
        ))}
      </Section>

      {/* GA Params */}
      <Section title="GA Parameters" defaultOpen>
        <Slider label="Population" value={gaConfig.population_size} min={20} max={200} step={5}
          onChange={v => setGAConfig({ population_size: v })} />
        <Slider label="Generations" value={gaConfig.generations} min={50} max={500} step={10}
          onChange={v => setGAConfig({ generations: v })} />
        <Slider label="Mutation Rate" value={gaConfig.mutation_rate} min={0.01} max={0.5} step={0.01}
          onChange={v => setGAConfig({ mutation_rate: Math.round(v * 100) / 100 })} />
        <Slider label="Crossover Rate" value={gaConfig.crossover_rate} min={0.5} max={1.0} step={0.05}
          onChange={v => setGAConfig({ crossover_rate: Math.round(v * 100) / 100 })} />
        <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
          <div style={{ flex: 1 }}>
            <div style={{ color: '#64748b', fontSize: 9, fontFamily: 'Space Mono', marginBottom: 4 }}>TOURNAMENT</div>
            <input type="number" min={2} max={10} value={gaConfig.tournament_size}
              onChange={e => setGAConfig({ tournament_size: Number(e.target.value) })}
              style={inputStyle} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ color: '#64748b', fontSize: 9, fontFamily: 'Space Mono', marginBottom: 4 }}>ELITISM</div>
            <input type="number" min={0} max={5} value={gaConfig.elitism}
              onChange={e => setGAConfig({ elitism: Number(e.target.value) })}
              style={inputStyle} />
          </div>
        </div>
      </Section>

      {/* Fitness Weights */}
      <Section title="Fitness Weights">
        <Slider label="w₁ Distance" value={weights.w_distance} min={0.1} max={10} step={0.1}
          onChange={v => setWeights({ w_distance: Math.round(v * 10) / 10 })} />
        <Slider label="w₂ TW Violation" value={weights.w_time_violation} min={0} max={500} step={5}
          onChange={v => setWeights({ w_time_violation: v })} />
        <Slider label="w₃ Unassigned" value={weights.w_unassigned} min={0} max={5000} step={50}
          onChange={v => setWeights({ w_unassigned: v })} />
      </Section>

      {/* Reproducibility */}
      <Section title="Reproducibility">
        <div style={{ color: '#64748b', fontSize: 9, fontFamily: 'Space Mono', marginBottom: 4 }}>SEED</div>
        <input type="number" value={seed}
          onChange={e => setSeed(Number(e.target.value))}
          style={{ ...inputStyle, width: '100%' }} />
      </Section>

      {/* Visualization Toggles */}
      <Section title="Visualization">
        <Toggle label="Visibility Graph" value={visualization.showVisibilityGraph}
          onChange={v => setVisualization({ showVisibilityGraph: v })} />
        <Toggle label="Centrality Heatmap" value={visualization.showCentrality}
          onChange={v => setVisualization({ showCentrality: v })} />
        <Toggle label="Trip Numbers" value={visualization.showTripNumbers}
          onChange={v => setVisualization({ showTripNumbers: v })} />
        <Slider label="Anim Speed" value={visualization.animationSpeed} min={1} max={30} step={1}
          onChange={v => setVisualization({ animationSpeed: v })} />
      </Section>

      {/* Custom Modal */}
      {customModal && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 1000,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <div style={{
            background: '#0d1321', border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 12, padding: 24, width: 280,
          }}>
            <div style={{ color: '#38bdf8', fontFamily: 'Space Mono', fontSize: 12, marginBottom: 16 }}>
              CUSTOM SCENARIO
            </div>
            {[
              { key: 'n_packages', label: 'Packages', min: 5, max: 50 },
              { key: 'n_zones', label: 'No-Fly Zones', min: 0, max: 8 },
              { key: 'fleet_size', label: 'Fleet Size', min: 2, max: 8 },
              { key: 'seed', label: 'Seed', min: 0, max: 99999 },
            ].map(({ key, label, min, max }) => (
              <div key={key} style={{ marginBottom: 12 }}>
                <div style={{ color: '#64748b', fontSize: 9, fontFamily: 'Space Mono', marginBottom: 4 }}>{label}</div>
                <input
                  type="number" min={min} max={max}
                  value={customParams[key as keyof typeof customParams]}
                  onChange={e => setCustomParams(prev => ({ ...prev, [key]: Number(e.target.value) }))}
                  style={{ ...inputStyle, width: '100%' }}
                />
              </div>
            ))}
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button onClick={() => setCustomModal(false)} style={{ ...btnStyle, flex: 1, color: '#64748b' }}>
                CANCEL
              </button>
              <button onClick={generateCustom} style={{ ...btnStyle, flex: 1, background: 'rgba(56,189,248,0.15)', color: '#38bdf8', borderColor: '#38bdf8' }}>
                GENERATE
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  background: '#0f172a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6,
  color: '#e2e8f0', fontFamily: 'Space Mono, monospace', fontSize: 11,
  padding: '5px 8px', outline: 'none',
}

const btnStyle: React.CSSProperties = {
  padding: '7px 0', borderRadius: 6, border: '1px solid rgba(255,255,255,0.1)',
  background: '#0f172a', color: '#94a3b8', fontFamily: 'Space Mono, monospace',
  fontSize: 10, cursor: 'pointer',
}
