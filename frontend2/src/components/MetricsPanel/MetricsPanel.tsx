import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { useAppStore } from '../../store/appStore'
import type { Solution } from '../../types/domain'

function KPIRow({ label, values }: { label: string; values: { random?: string; nn?: string; ga?: string } }) {
  const best = Object.entries(values)
    .filter(([, v]) => v !== undefined && v !== '—')
    .sort(([, a], [, b]) => parseFloat(a!) - parseFloat(b!))[0]?.[0]

  return (
    <tr>
      <td style={{ padding: '5px 8px', color: '#64748b', fontFamily: 'Space Mono, monospace', fontSize: 9 }}>{label}</td>
      {(['random', 'nn', 'ga'] as const).map(algo => (
        <td key={algo} style={{
          padding: '5px 8px', textAlign: 'right',
          fontFamily: 'Space Mono, monospace', fontSize: 10,
          color: best === algo ? '#34d399' : '#94a3b8',
          background: best === algo ? 'rgba(52,211,153,0.05)' : 'transparent',
        }}>
          {values[algo] || '—'}
        </td>
      ))}
    </tr>
  )
}

function formatSol(sol: Solution | undefined, key: keyof Solution) {
  if (!sol) return '—'
  const v = sol[key]
  if (typeof v === 'number') return v.toFixed(1)
  if (Array.isArray(v)) return String(v.length)
  return String(v)
}

export function MetricsPanel() {
  const { currentRun, solutions, scenario } = useAppStore()

  const history = currentRun?.history || []
  const lastHistory = history[history.length - 1]

  const mc = (sol?: Solution) => sol?.metadata?.monte_carlo?.expected_success_rate
    ? `${(sol.metadata.monte_carlo.expected_success_rate * 100).toFixed(1)}%`
    : '—'

  return (
    <div style={{
      width: '100%', height: '100%', overflowY: 'auto',
      background: '#0d1321', borderLeft: '1px solid rgba(255,255,255,0.07)',
      display: 'flex', flexDirection: 'column',
    }}>
      <div style={{ padding: '14px 12px 8px', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
        <div style={{ color: '#38bdf8', fontFamily: 'Space Mono, monospace', fontSize: 11, letterSpacing: '0.1em' }}>
          METRICS
        </div>
      </div>

      {/* GA Progress */}
      {currentRun && (
        <div style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ color: '#64748b', fontFamily: 'Space Mono', fontSize: 9 }}>GENERATION</span>
            <span style={{ color: '#e2e8f0', fontFamily: 'Space Mono', fontSize: 10 }}>
              {history.length} / —
            </span>
          </div>
          <div style={{ height: 4, background: '#1e293b', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{
              height: '100%', width: `${currentRun.progress}%`,
              background: 'linear-gradient(90deg, #38bdf8, #818cf8)',
              transition: 'width 0.3s', borderRadius: 2,
            }} />
          </div>

          {lastHistory && (
            <div style={{ display: 'flex', gap: 12, marginTop: 10 }}>
              <div>
                <div style={{ color: '#64748b', fontFamily: 'Space Mono', fontSize: 8 }}>BEST FITNESS</div>
                <div style={{ color: '#38bdf8', fontFamily: 'Space Mono', fontSize: 16, fontWeight: 700 }}>
                  {lastHistory.bestFitness.toFixed(0)}
                </div>
              </div>
              <div>
                <div style={{ color: '#64748b', fontFamily: 'Space Mono', fontSize: 8 }}>MEAN FITNESS</div>
                <div style={{ color: '#818cf8', fontFamily: 'Space Mono', fontSize: 16 }}>
                  {lastHistory.meanFitness.toFixed(0)}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Convergence Chart */}
      {history.length > 1 && (
        <div style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
          <div style={{ color: '#64748b', fontFamily: 'Space Mono', fontSize: 9, marginBottom: 8 }}>
            CONVERGENCE
          </div>
          <ResponsiveContainer width="100%" height={120}>
            <LineChart data={history} margin={{ top: 2, right: 4, left: -20, bottom: 0 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="3 3" />
              <XAxis dataKey="gen" tick={{ fill: '#475569', fontSize: 8, fontFamily: 'Space Mono' }} />
              <YAxis tick={{ fill: '#475569', fontSize: 8, fontFamily: 'Space Mono' }} />
              <Tooltip
                contentStyle={{ background: '#0d1321', border: '1px solid rgba(255,255,255,0.1)', fontFamily: 'Space Mono', fontSize: 10 }}
                labelStyle={{ color: '#64748b' }}
              />
              <Line type="monotone" dataKey="bestFitness" stroke="#38bdf8" dot={false} strokeWidth={1.5} name="Best" />
              <Line type="monotone" dataKey="meanFitness" stroke="#818cf8" dot={false} strokeWidth={1} strokeDasharray="4 2" name="Mean" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Scenario Info */}
      {scenario && (
        <div style={{ padding: '10px 12px', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
          <div style={{ color: '#64748b', fontFamily: 'Space Mono', fontSize: 9, marginBottom: 6 }}>SCENARIO</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
            {[
              { label: 'Packages', value: scenario.delivery_points.length },
              { label: 'Drones', value: scenario.drone_fleet.count },
              { label: 'NFZ', value: scenario.no_fly_zones.length },
              { label: 'Seed', value: scenario.seed },
            ].map(({ label, value }) => (
              <div key={label} style={{ background: '#0f172a', borderRadius: 6, padding: '5px 8px' }}>
                <div style={{ color: '#475569', fontFamily: 'Space Mono', fontSize: 8 }}>{label}</div>
                <div style={{ color: '#e2e8f0', fontFamily: 'Space Mono', fontSize: 13 }}>{value}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* KPI Comparison Table */}
      {(solutions.random || solutions.nn || solutions.ga) && (
        <div style={{ padding: '10px 12px' }}>
          <div style={{ color: '#64748b', fontFamily: 'Space Mono', fontSize: 9, marginBottom: 8 }}>COMPARISON</div>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ padding: '4px 8px', color: '#334155', fontFamily: 'Space Mono', fontSize: 8, textAlign: 'left' }}></th>
                {(['random', 'nn', 'ga'] as const).map(a => (
                  <th key={a} style={{ padding: '4px 8px', color: '#38bdf8', fontFamily: 'Space Mono', fontSize: 8, textAlign: 'right' }}>
                    {a.toUpperCase()}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <KPIRow label="Dist" values={{
                random: formatSol(solutions.random, 'total_distance'),
                nn: formatSol(solutions.nn, 'total_distance'),
                ga: formatSol(solutions.ga, 'total_distance'),
              }} />
              <KPIRow label="Time (min)" values={{
                random: formatSol(solutions.random, 'total_time_min'),
                nn: formatSol(solutions.nn, 'total_time_min'),
                ga: formatSol(solutions.ga, 'total_time_min'),
              }} />
              <KPIRow label="TW Viol." values={{
                random: formatSol(solutions.random, 'time_window_violations'),
                nn: formatSol(solutions.nn, 'time_window_violations'),
                ga: formatSol(solutions.ga, 'time_window_violations'),
              }} />
              <KPIRow label="Unassigned" values={{
                random: String(solutions.random?.unassigned_packages?.length ?? '—'),
                nn: String(solutions.nn?.unassigned_packages?.length ?? '—'),
                ga: String(solutions.ga?.unassigned_packages?.length ?? '—'),
              }} />
              <KPIRow label="MC Success" values={{
                random: mc(solutions.random),
                nn: mc(solutions.nn),
                ga: mc(solutions.ga),
              }} />
              <KPIRow label="Fitness" values={{
                random: solutions.random ? solutions.random.fitness.toFixed(0) : '—',
                nn: solutions.nn ? solutions.nn.fitness.toFixed(0) : '—',
                ga: solutions.ga ? solutions.ga.fitness.toFixed(0) : '—',
              }} />
              <KPIRow label="Compute (s)" values={{
                random: solutions.random?.metadata?.compute_time_seconds != null
                  ? Number(solutions.random.metadata.compute_time_seconds).toFixed(3) : '—',
                nn: solutions.nn?.metadata?.compute_time_seconds != null
                  ? Number(solutions.nn.metadata.compute_time_seconds).toFixed(3) : '—',
                ga: solutions.ga?.metadata?.compute_time_seconds != null
                  ? Number(solutions.ga.metadata.compute_time_seconds).toFixed(2) : '—',
              }} />
            </tbody>
          </table>
        </div>
      )}

      {/* Centrality info */}
      {useAppStore.getState().graphData && (
        <div style={{ padding: '10px 12px', borderTop: '1px solid rgba(255,255,255,0.07)' }}>
          <div style={{ color: '#64748b', fontFamily: 'Space Mono', fontSize: 9, marginBottom: 4 }}>
            LINEAR ALGEBRA
          </div>
          <div style={{ color: '#475569', fontSize: 9, fontFamily: 'Space Mono' }}>
            Frobenius: {useAppStore.getState().graphData?.centrality?.frobenius_norm?.toFixed(1)}
          </div>
          <div style={{ color: '#475569', fontSize: 9, fontFamily: 'Space Mono' }}>
            λ₁: {useAppStore.getState().graphData?.centrality?.eigenvalue?.toFixed(4)}
          </div>
        </div>
      )}
    </div>
  )
}
