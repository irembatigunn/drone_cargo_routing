import { useRef, useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { optimizationApi, scenarioApi } from '../../api/client'
import { useWebSocket } from '../../hooks/useWebSocket'
import type { WSMessage } from '../../types/domain'
import { useAnimation } from '../../hooks/useAnimation'

export function TopBar() {
  const {
    scenario, gaConfig, weights, seed, isRunning, solutions, selectedAlgos,
    setIsRunning, setCurrentRun, updateRunProgress, completeRun, setSolution,
    animation, setAnimation, visualization,
  } = useAppStore()

  const { connect, cancel } = useWebSocket()
  const [status, setStatus] = useState<string>('')
  const isRunningRef = useRef(isRunning)
  isRunningRef.current = isRunning

  const graphData = useAppStore(s => s.graphData)
  const paths = graphData?.paths
    ? Object.fromEntries(
        Object.entries(graphData.paths).map(([k, v]) => [k, v])
      )
    : {}

  const { play, pause, reset } = useAnimation(
    solutions.ga || solutions.nn || solutions.random || null,
    scenario,
    paths,
  )

  const runOptimization = async () => {
    if (!scenario || isRunning) return

    const anySelected = selectedAlgos.random || selectedAlgos.nn || selectedAlgos.ga
    if (!anySelected) {
      setStatus('No algorithm selected')
      return
    }

    setIsRunning(true)
    setStatus('Starting...')

    try {
      // Run Random and NN in parallel (only if selected)
      const promises: Promise<void>[] = []

      if (selectedAlgos.random) {
        promises.push(
          optimizationApi.runRandom(scenario.id, seed, weights).then(sol => {
            setSolution('random', sol)
            setStatus(s => s.includes('GA') ? s : 'Random done')
          })
        )
      }
      if (selectedAlgos.nn) {
        promises.push(
          optimizationApi.runNN(scenario.id, weights).then(sol => {
            setSolution('nn', sol)
          })
        )
      }

      if (promises.length > 0) {
        setStatus('Running baselines...')
        await Promise.all(promises)
      }

      if (!selectedAlgos.ga) {
        setStatus('Done')
        setIsRunning(false)
        return
      }

      setStatus('Starting GA...')

      // Start GA
      const { run_id } = await optimizationApi.startGA(scenario.id, { ...gaConfig, seed }, weights, seed)

      setCurrentRun({
        runId: run_id,
        algorithm: 'ga',
        status: 'running',
        progress: 0,
        history: [],
        currentGenSolution: null,
      })

      connect(run_id, (msg: WSMessage) => {
        if (msg.type === 'generation') {
          setStatus(`GA gen ${msg.generation} | best: ${msg.best_fitness.toFixed(0)}`)
          updateRunProgress(msg.generation, msg.best_fitness, msg.mean_fitness, msg.best_solution)
        } else if (msg.type === 'complete') {
          completeRun(msg.final_solution)
          setStatus(`GA complete — ${msg.convergence_generation} gens, ${msg.compute_time_seconds.toFixed(1)}s`)
          setIsRunning(false)
        } else if (msg.type === 'error') {
          setStatus(`Error: ${msg.message}`)
          setIsRunning(false)
        }
      }, () => {
        if (isRunningRef.current) setIsRunning(false)
      }, () => {
        setStatus('WebSocket connection failed — check backend')
        setIsRunning(false)
      })
    } catch (e) {
      console.error(e)
      setStatus('Error — check backend')
      setIsRunning(false)
    }
  }

  const cancelRun = () => {
    cancel()
    setIsRunning(false)
    setStatus('Cancelled')
  }

  const hasSolution = !!(solutions.ga || solutions.nn || solutions.random)

  return (
    <div style={{
      height: 48, display: 'flex', alignItems: 'center', gap: 12,
      padding: '0 16px', background: '#080d18',
      borderBottom: '1px solid rgba(255,255,255,0.07)',
    }}>
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 160 }}>
        <span style={{ fontSize: 18 }}>🚁</span>
        <div>
          <div style={{ color: '#38bdf8', fontFamily: 'Space Mono, monospace', fontSize: 11, fontWeight: 700, letterSpacing: '0.08em' }}>
            DRONE ROUTING
          </div>
          <div style={{ color: '#334155', fontFamily: 'Space Mono, monospace', fontSize: 8 }}>
            OPTIMIZATION SYSTEM
          </div>
        </div>
      </div>

      <div style={{ flex: 1 }} />

      {/* Status */}
      {status && (
        <div style={{
          color: isRunning ? '#38bdf8' : '#64748b',
          fontFamily: 'Space Mono, monospace', fontSize: 10,
          maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {isRunning && (
            <span style={{
              display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
              background: '#38bdf8', marginRight: 6,
              animation: 'pulse 1s infinite',
            }} />
          )}
          {status}
        </div>
      )}

      <div style={{ flex: 1 }} />

      {/* Animation controls */}
      {hasSolution && (
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ color: '#334155', fontFamily: 'Space Mono', fontSize: 9 }}>SIM</span>
          <button
            onClick={reset}
            style={ctrlBtn}
            title="Reset"
          >⏮</button>
          <button
            onClick={animation.isPlaying ? pause : play}
            style={{ ...ctrlBtn, color: animation.isPlaying ? '#fbbf24' : '#34d399', borderColor: animation.isPlaying ? '#fbbf24' : '#34d399' }}
          >
            {animation.isPlaying ? '⏸' : '▶'}
          </button>
          <span style={{ color: '#475569', fontFamily: 'Space Mono', fontSize: 9 }}>
            {Math.floor(animation.currentTime)}m
          </span>
        </div>
      )}

      {/* Run / Cancel */}
      {!isRunning ? (
        <button
          onClick={runOptimization}
          disabled={!scenario}
          style={{
            padding: '7px 18px', borderRadius: 8,
            background: scenario ? 'rgba(56,189,248,0.15)' : 'rgba(255,255,255,0.05)',
            border: `1px solid ${scenario ? '#38bdf8' : 'rgba(255,255,255,0.1)'}`,
            color: scenario ? '#38bdf8' : '#334155',
            fontFamily: 'Space Mono, monospace', fontSize: 11,
            cursor: scenario ? 'pointer' : 'not-allowed',
            letterSpacing: '0.06em',
          }}
        >
          ▶ RUN OPTIMIZATION
        </button>
      ) : (
        <button
          onClick={cancelRun}
          style={{
            padding: '7px 18px', borderRadius: 8,
            background: 'rgba(239,68,68,0.1)',
            border: '1px solid rgba(239,68,68,0.4)',
            color: '#ef4444',
            fontFamily: 'Space Mono, monospace', fontSize: 11, cursor: 'pointer',
          }}
        >
          ■ CANCEL
        </button>
      )}
    </div>
  )
}

const ctrlBtn: React.CSSProperties = {
  width: 26, height: 26, borderRadius: 6,
  background: '#0f172a', border: '1px solid rgba(255,255,255,0.1)',
  color: '#94a3b8', cursor: 'pointer', fontSize: 11, display: 'flex',
  alignItems: 'center', justifyContent: 'center',
}
