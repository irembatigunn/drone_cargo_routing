import React, { useCallback, useState } from 'react'
import { Stage, Layer, Line, Circle, RegularPolygon, Star, Text, Arrow, Group, Rect } from 'react-konva'
import type { KonvaEventObject } from 'konva/lib/Node'
import { useAppStore } from '../../store/appStore'
import type { Position, Solution } from '../../types/domain'

const DRONE_COLORS = ['#38bdf8', '#a78bfa', '#34d399', '#fb923c', '#f472b6', '#facc15']
const PRIORITY_COLORS = { low: '#94a3b8', med: '#f59e0b', high: '#ef4444' }
const CANVAS_SIZE = 1000

interface Props {
  width: number
  height: number
}

function scalePos(p: Position, scaleX: number, scaleY: number): [number, number] {
  return [p.x * scaleX, p.y * scaleY]
}

export function CanvasStage({ width, height }: Props) {
  const {
    scenario,
    solutions,
    visualization,
    animation,
    graphData,
    visibilityEdges,
    setVisualization,
  } = useAppStore()

  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null)
  const [stageScale, setStageScale] = useState(1)
  const [stagePos, setStagePos] = useState({ x: 0, y: 0 })

  const scaleX = width / CANVAS_SIZE
  const scaleY = height / CANVAS_SIZE

  // Get the active solution to display
  const activeSolution: Solution | undefined =
    solutions[visualization.selectedAlgo] ||
    solutions.ga ||
    solutions.nn ||
    solutions.random

  // Pan & Zoom
  const handleWheel = useCallback((e: KonvaEventObject<WheelEvent>) => {
    e.evt.preventDefault()
    const stage = e.target.getStage()
    if (!stage) return
    const oldScale = stageScale
    const pointer = stage.getPointerPosition()
    if (!pointer) return
    const scaleBy = 1.1
    const newScale = e.evt.deltaY < 0 ? oldScale * scaleBy : oldScale / scaleBy
    const clampedScale = Math.max(0.3, Math.min(5, newScale))
    const mousePointTo = {
      x: (pointer.x - stagePos.x) / oldScale,
      y: (pointer.y - stagePos.y) / oldScale,
    }
    setStageScale(clampedScale)
    setStagePos({
      x: pointer.x - mousePointTo.x * clampedScale,
      y: pointer.y - mousePointTo.y * clampedScale,
    })
  }, [stageScale, stagePos])

  if (!scenario) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500" style={{ width, height }}>
        <div className="text-center">
          <div className="text-5xl mb-4">🚁</div>
          <div className="font-mono text-sm">Select a scenario to begin</div>
        </div>
      </div>
    )
  }

  const depotScreen = scalePos(scenario.depot, scaleX, scaleY)

  return (
    <div style={{ position: 'relative', width, height, background: '#0a0e1a', cursor: 'crosshair' }}>
      <Stage
        width={width}
        height={height}
        onWheel={handleWheel}
        draggable
        scaleX={stageScale}
        scaleY={stageScale}
        x={stagePos.x}
        y={stagePos.y}
        onDragEnd={(e) => setStagePos({ x: e.target.x(), y: e.target.y() })}
      >
        {/* Layer 1: Background grid */}
        <Layer>
          {Array.from({ length: 11 }, (_, i) => (
            <React.Fragment key={`grid-${i}`}>
              <Line
                points={[i * width / 10, 0, i * width / 10, height]}
                stroke="rgba(255,255,255,0.04)"
                strokeWidth={1}
              />
              <Line
                points={[0, i * height / 10, width, i * height / 10]}
                stroke="rgba(255,255,255,0.04)"
                strokeWidth={1}
              />
            </React.Fragment>
          ))}
          <Rect x={0} y={0} width={width} height={height}
            stroke="rgba(255,255,255,0.15)" strokeWidth={1} fill="transparent" />
        </Layer>

        {/* Layer 2: No-fly zones */}
        <Layer>
          {scenario.no_fly_zones.map((zone) => {
            const flatPoints = zone.polygon.flatMap(v => [v.x * scaleX, v.y * scaleY])
            return (
              <Line
                key={zone.id}
                points={flatPoints}
                closed
                fill="rgba(220, 38, 38, 0.18)"
                stroke="#dc2626"
                strokeWidth={1.5}
                dash={[5, 3]}
              />
            )
          })}
          {scenario.no_fly_zones.map((zone) => {
            const cx = zone.polygon.reduce((s, v) => s + v.x, 0) / zone.polygon.length
            const cy = zone.polygon.reduce((s, v) => s + v.y, 0) / zone.polygon.length
            return (
              <Text
                key={`${zone.id}-label`}
                x={cx * scaleX - 20}
                y={cy * scaleY - 8}
                text="NO-FLY"
                fontSize={9}
                fill="rgba(220,38,38,0.7)"
                fontFamily="Space Mono, monospace"
              />
            )
          })}
        </Layer>

        {/* Layer 3: Visibility graph (toggleable) */}
        {visualization.showVisibilityGraph && (
          <Layer>
            {visibilityEdges.slice(0, 500).map((edge, i) => (
              <Line
                key={i}
                points={[edge.from.x * scaleX, edge.from.y * scaleY, edge.to.x * scaleX, edge.to.y * scaleY]}
                stroke="rgba(100,200,255,0.1)"
                strokeWidth={0.5}
              />
            ))}
          </Layer>
        )}

        {/* Layer 4: Routes */}
        {activeSolution && (
          <Layer>
            {activeSolution.routes.map((route, di) => {
              const color = DRONE_COLORS[di % DRONE_COLORS.length]
              const isHighlighted = !visualization.highlightedDroneId || visualization.highlightedDroneId === route.drone_id

              // Helper: get NFZ-aware path points between two nodes
              const getSegPath = (from: string, to: string): [number, number][] => {
                if (graphData?.paths) {
                  const key = `${from}::${to}`
                  const revKey = `${to}::${from}`
                  const pts = graphData.paths[key] || graphData.paths[revKey]
                  if (pts && pts.length >= 2) {
                    return pts.map(p => scalePos(p, scaleX, scaleY) as [number, number])
                  }
                }
                // Fallback: straight line
                const fromPos = from === 'depot' ? scenario.depot
                  : scenario.delivery_points.find(d => d.id === from)?.position
                const toPos = to === 'depot' ? scenario.depot
                  : scenario.delivery_points.find(d => d.id === to)?.position
                if (fromPos && toPos) {
                  return [scalePos(fromPos, scaleX, scaleY) as [number, number], scalePos(toPos, scaleX, scaleY) as [number, number]]
                }
                return []
              }

              return route.trips.map((trip, ti) => {
                // Build full route polyline by concatenating path segments
                const flatPoints: number[] = []

                const stops = ['depot', ...trip.sequence, 'depot']
                for (let si = 0; si < stops.length - 1; si++) {
                  const seg = getSegPath(stops[si], stops[si + 1])
                  if (seg.length === 0) continue
                  if (flatPoints.length === 0) {
                    // First segment: add all points
                    seg.forEach(([x, y]) => flatPoints.push(x, y))
                  } else {
                    // Skip first point (shared with last point of previous segment)
                    seg.slice(1).forEach(([x, y]) => flatPoints.push(x, y))
                  }
                }

                if (flatPoints.length < 4) return null

                const dashPattern = ti === 0 ? [] : ti === 1 ? [8, 4] : [2, 4]

                return (
                  <React.Fragment key={`${route.drone_id}-trip-${ti}`}>
                    <Line
                      points={flatPoints}
                      stroke={isHighlighted ? color : `${color}33`}
                      strokeWidth={isHighlighted ? 2 : 1}
                      dash={dashPattern}
                      opacity={isHighlighted ? 0.85 : 0.3}
                    />
                    {/* Trip number label at first delivery point */}
                    {visualization.showTripNumbers && trip.sequence.length > 0 && (() => {
                      const firstDp = scenario.delivery_points.find(d => d.id === trip.sequence[0])
                      if (!firstDp) return null
                      const [lx, ly] = scalePos(firstDp.position, scaleX, scaleY)
                      return (
                        <Text
                          x={lx + 6}
                          y={ly - 12}
                          text={`D${di + 1}T${ti + 1}`}
                          fontSize={8}
                          fill={color}
                          fontFamily="Space Mono, monospace"
                        />
                      )
                    })()}
                  </React.Fragment>
                )
              })
            })}
          </Layer>
        )}

        {/* Layer 5: Delivery points */}
        <Layer>
          {scenario.delivery_points.map((dp) => {
            const [sx, sy] = scalePos(dp.position, scaleX, scaleY)
            const radius = 5 + dp.weight_kg * 1.2
            const borderColor = PRIORITY_COLORS[dp.priority]
            const isAssigned = activeSolution && !activeSolution.unassigned_packages.includes(dp.id)
            const centralityScore = graphData?.centrality?.centrality?.[dp.id] || 0

            let fillColor = 'rgba(15, 23, 42, 0.9)'
            if (visualization.showCentrality) {
              const r = Math.round(255 * centralityScore)
              const g = Math.round(255 * (1 - centralityScore))
              fillColor = `rgba(${r}, ${g}, 30, 0.8)`
            }

            return (
              <Group key={dp.id}>
                <Circle
                  x={sx}
                  y={sy}
                  radius={radius}
                  fill={fillColor}
                  stroke={isAssigned ? borderColor : '#6b7280'}
                  strokeWidth={isAssigned ? 2 : 1}
                  opacity={isAssigned ? 1 : 0.5}
                  onMouseEnter={(e) => {
                    const stage = e.target.getStage()
                    const pos = stage?.getPointerPosition()
                    if (pos) {
                      setTooltip({
                        x: pos.x / stageScale - stagePos.x / stageScale,
                        y: pos.y / stageScale - stagePos.y / stageScale,
                        text: `${dp.id}\n${dp.weight_kg}kg | ${dp.priority}\nTW: ${dp.time_window_open_min}-${dp.time_window_close_min}min`,
                      })
                    }
                    setVisualization({ highlightedPkgId: dp.id })
                  }}
                  onMouseLeave={() => {
                    setTooltip(null)
                    setVisualization({ highlightedPkgId: null })
                  }}
                  onClick={() => {
                    if (activeSolution) {
                      const drone = activeSolution.routes.find(r =>
                        r.trips.some(t => t.sequence.includes(dp.id))
                      )
                      setVisualization({ highlightedDroneId: drone?.drone_id || null })
                    }
                  }}
                />
                <Text
                  x={sx - 8}
                  y={sy + radius + 2}
                  text={dp.id.replace('pkg_', '')}
                  fontSize={7}
                  fill="rgba(255,255,255,0.5)"
                  fontFamily="Space Mono, monospace"
                />
              </Group>
            )
          })}
        </Layer>

        {/* Layer 6: Depot */}
        <Layer>
          <Star
            x={depotScreen[0]}
            y={depotScreen[1]}
            numPoints={5}
            innerRadius={8}
            outerRadius={18}
            fill="#f97316"
            stroke="#fed7aa"
            strokeWidth={1.5}
          />
          <Text
            x={depotScreen[0] - 18}
            y={depotScreen[1] + 22}
            text="DEPOT"
            fontSize={9}
            fill="#f97316"
            fontFamily="Space Mono, monospace"
          />
        </Layer>

        {/* Layer 7: Drone agents (animation) */}
        {animation.isPlaying && (
          <Layer>
            {Object.entries(animation.dronePositions).map(([droneId, pos], di) => {
              const color = DRONE_COLORS[di % DRONE_COLORS.length]
              const [sx, sy] = scalePos(pos, scaleX, scaleY)
              return (
                <Group key={droneId}>
                  <RegularPolygon
                    x={sx}
                    y={sy}
                    sides={3}
                    radius={10}
                    fill={color}
                    stroke="white"
                    strokeWidth={1}
                  />
                  <Text
                    x={sx - 10}
                    y={sy + 12}
                    text={`D${di + 1}`}
                    fontSize={7}
                    fill={color}
                    fontFamily="Space Mono"
                  />
                </Group>
              )
            })}
          </Layer>
        )}
      </Stage>

      {/* Tooltip overlay */}
      {tooltip && (
        <div
          style={{
            position: 'absolute',
            left: tooltip.x * stageScale + stagePos.x + 12,
            top: tooltip.y * stageScale + stagePos.y - 10,
            background: 'rgba(15,23,42,0.95)',
            border: '1px solid rgba(255,255,255,0.15)',
            borderRadius: 6,
            padding: '6px 10px',
            color: 'white',
            fontFamily: 'Space Mono, monospace',
            fontSize: 11,
            pointerEvents: 'none',
            whiteSpace: 'pre',
            zIndex: 100,
          }}
        >
          {tooltip.text}
        </div>
      )}

      {/* Legend */}
      <div style={{
        position: 'absolute',
        bottom: 12,
        right: 12,
        background: 'rgba(10,14,26,0.85)',
        border: '1px solid rgba(255,255,255,0.1)',
        borderRadius: 8,
        padding: '8px 12px',
        display: 'flex',
        gap: 16,
        fontSize: 10,
        fontFamily: 'Space Mono, monospace',
        color: '#94a3b8',
      }}>
        {[
          { color: '#ef4444', label: 'High' },
          { color: '#f59e0b', label: 'Med' },
          { color: '#94a3b8', label: 'Low' },
        ].map(({ color, label }) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: color }} />
            {label}
          </div>
        ))}
        <div style={{ borderLeft: '1px solid rgba(255,255,255,0.1)', paddingLeft: 16, display: 'flex', alignItems: 'center', gap: 5 }}>
          <div style={{ width: 12, height: 12, background: '#f97316', clipPath: 'polygon(50% 0%, 0% 100%, 100% 100%)' }} />
          Depot
        </div>
        <div style={{ borderLeft: '1px solid rgba(255,255,255,0.1)', paddingLeft: 16, display: 'flex', alignItems: 'center', gap: 5 }}>
          <div style={{ width: 16, height: 8, background: 'rgba(220,38,38,0.3)', border: '1px dashed #dc2626' }} />
          NFZ
        </div>
      </div>

      {/* Algo selector overlay */}
      {activeSolution && (
        <div style={{
          position: 'absolute',
          top: 12,
          right: 12,
          display: 'flex',
          gap: 6,
        }}>
          {(['random', 'nn', 'ga'] as const).map((algo) => {
            const sol = solutions[algo]
            if (!sol) return null
            return (
              <button
                key={algo}
                onClick={() => setVisualization({ selectedAlgo: algo })}
                style={{
                  padding: '4px 10px',
                  borderRadius: 6,
                  border: '1px solid',
                  borderColor: visualization.selectedAlgo === algo ? '#38bdf8' : 'rgba(255,255,255,0.2)',
                  background: visualization.selectedAlgo === algo ? 'rgba(56,189,248,0.15)' : 'rgba(10,14,26,0.8)',
                  color: visualization.selectedAlgo === algo ? '#38bdf8' : '#64748b',
                  fontFamily: 'Space Mono, monospace',
                  fontSize: 11,
                  cursor: 'pointer',
                }}
              >
                {algo.toUpperCase()}
              </button>
            )
          })}
          {visualization.highlightedDroneId && (
            <button
              onClick={() => setVisualization({ highlightedDroneId: null })}
              style={{
                padding: '4px 10px',
                borderRadius: 6,
                border: '1px solid rgba(255,100,100,0.4)',
                background: 'rgba(255,100,100,0.1)',
                color: '#fca5a5',
                fontFamily: 'Space Mono, monospace',
                fontSize: 11,
                cursor: 'pointer',
              }}
            >
              ✕ Clear
            </button>
          )}
        </div>
      )}
    </div>
  )
}
