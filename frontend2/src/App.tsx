import { useEffect, useRef, useState } from 'react'
import { TopBar } from './components/TopBar/TopBar'
import { ConfigPanel } from './components/ConfigPanel/ConfigPanel'
import { CanvasStage } from './components/Canvas/CanvasStage'
import { MetricsPanel } from './components/MetricsPanel/MetricsPanel'
import { useAppStore } from './store/appStore'
import { scenarioApi } from './api/client'

const LEFT_W = 220
const RIGHT_W = 240
const TOP_H = 48

export default function App() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [canvasSize, setCanvasSize] = useState({ w: 800, h: 600 })
  const { setScenario, setGraphData, setVisibilityEdges, setActivePreset } = useAppStore()
  const [initialized, setInitialized] = useState(false)

  // Load medium preset on startup
  useEffect(() => {
    if (initialized) return
    setInitialized(true)
    const load = async () => {
      try {
        const scenario = await scenarioApi.getPreset('medium')
        setScenario(scenario)
        setActivePreset('medium')
        const [gd, edges] = await Promise.all([
          scenarioApi.getGraphData(scenario.id),
          scenarioApi.getVisibilityEdges(scenario.id),
        ])
        setGraphData(gd)
        setVisibilityEdges(edges.edges)
      } catch (e) {
        console.warn('Could not load default preset — backend may be starting')
      }
    }
    load()
  }, [initialized])

  // Responsive canvas sizing
  useEffect(() => {
    const update = () => {
      const totalW = window.innerWidth
      const totalH = window.innerHeight
      setCanvasSize({
        w: totalW - LEFT_W - RIGHT_W,
        h: totalH - TOP_H,
      })
    }
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])

  return (
    <div style={{
      width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column',
      background: '#080d18', overflow: 'hidden',
    }}>
      <TopBar />
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <div style={{ width: LEFT_W, flexShrink: 0, overflow: 'hidden' }}>
          <ConfigPanel />
        </div>
        <div ref={containerRef} style={{ flex: 1, overflow: 'hidden' }}>
          <CanvasStage width={canvasSize.w} height={canvasSize.h} />
        </div>
        <div style={{ width: RIGHT_W, flexShrink: 0, overflow: 'hidden' }}>
          <MetricsPanel />
        </div>
      </div>
    </div>
  )
}
