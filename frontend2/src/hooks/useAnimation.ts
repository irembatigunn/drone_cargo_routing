import { useEffect, useRef, useCallback } from 'react'
import type { Solution, Scenario, Position } from '../types/domain'
import { useAppStore } from '../store/appStore'

interface DroneTimeline {
  droneId: string
  waypoints: Array<{
    position: Position
    arriveAt: number
    departAt: number
    isDepot: boolean
    isRecharge: boolean
    pkgId?: string
    pathSegment?: Position[]  // full path including NFZ waypoints
  }>
}

function buildTimelines(solution: Solution, scenario: Scenario, paths: Record<string, Position[]>): DroneTimeline[] {
  const fleet = scenario.drone_fleet
  const depotPos = scenario.depot
  const dpMap = new Map(scenario.delivery_points.map(dp => [dp.id, dp]))
  const DEPOT_KEY = 'depot'

  const getPath = (from: string, to: string): Position[] => {
    const key = `${from}::${to}`
    const revKey = `${to}::${from}`
    return paths[key] || paths[revKey] || []
  }

  return solution.routes.map(route => {
    const waypoints: DroneTimeline['waypoints'] = []
    let currentTime = 0

    waypoints.push({ position: depotPos, arriveAt: 0, departAt: 0, isDepot: true, isRecharge: false })

    for (let tripIdx = 0; tripIdx < route.trips.length; tripIdx++) {
      const trip = route.trips[tripIdx]

      if (tripIdx > 0) {
        // Recharge at depot
        const prevDepartAt = waypoints[waypoints.length - 1].departAt
        const rechargeStart = prevDepartAt
        const rechargeEnd = rechargeStart + fleet.recharge_time_min
        waypoints[waypoints.length - 1].departAt = rechargeEnd
        currentTime = rechargeEnd
      }

      let prevKey = DEPOT_KEY
      for (const pkgId of trip.sequence) {
        const dp = dpMap.get(pkgId)
        if (!dp) continue

        const segPath = getPath(prevKey, pkgId)
        const segDist = segPath.length > 1
          ? segPath.reduce((sum, p, i) => i === 0 ? 0 : sum + Math.hypot(p.x - segPath[i-1].x, p.y - segPath[i-1].y), 0)
          : 0
        const travelTime = segDist / fleet.speed_units_per_min || 1

        const arriveAt = currentTime + travelTime
        const departAt = arriveAt + dp.service_time_min
        currentTime = departAt

        waypoints.push({
          position: dp.position,
          arriveAt,
          departAt,
          isDepot: false,
          isRecharge: false,
          pkgId,
          pathSegment: segPath,
        })
        prevKey = pkgId
      }

      // Return to depot
      const returnPath = getPath(prevKey, DEPOT_KEY)
      const returnDist = returnPath.length > 1
        ? returnPath.reduce((sum, p, i) => i === 0 ? 0 : sum + Math.hypot(p.x - returnPath[i-1].x, p.y - returnPath[i-1].y), 0)
        : 0
      const returnTime = returnDist / fleet.speed_units_per_min || 1

      waypoints.push({
        position: depotPos,
        arriveAt: currentTime + returnTime,
        departAt: currentTime + returnTime,
        isDepot: true,
        isRecharge: tripIdx < route.trips.length - 1,
      })
      currentTime += returnTime
    }

    return { droneId: route.drone_id, waypoints }
  })
}

export function useAnimation(solution: Solution | null, scenario: Scenario | null, paths: Record<string, Position[]>) {
  const { animation, setAnimation } = useAppStore()
  const rafRef = useRef<number>(0)
  const lastTimestampRef = useRef<number>(0)
  const timelinesRef = useRef<DroneTimeline[]>([])

  useEffect(() => {
    if (solution && scenario) {
      timelinesRef.current = buildTimelines(solution, scenario, paths)
    }
  }, [solution, scenario, paths])

  const getPositionAtTime = useCallback((timeline: DroneTimeline, t: number): Position => {
    const wps = timeline.waypoints
    if (!wps.length) return scenario?.depot || { x: 500, y: 500 }

    // Find active segment
    for (let i = 0; i < wps.length - 1; i++) {
      const wp = wps[i]
      const next = wps[i + 1]

      // Dwell at current waypoint
      if (t >= wp.arriveAt && t <= wp.departAt) {
        return wp.position
      }

      // Traveling to next waypoint
      if (t > wp.departAt && t < next.arriveAt) {
        const totalTravel = next.arriveAt - wp.departAt
        const elapsed = t - wp.departAt
        const progress = totalTravel > 0 ? elapsed / totalTravel : 1

        // Interpolate along path segment
        const seg = next.pathSegment
        if (seg && seg.length >= 2) {
          const totalSegLen = seg.reduce((s, p, i) =>
            i === 0 ? 0 : s + Math.hypot(p.x - seg[i-1].x, p.y - seg[i-1].y), 0)
          const targetDist = progress * totalSegLen
          let traveled = 0
          for (let j = 1; j < seg.length; j++) {
            const d = Math.hypot(seg[j].x - seg[j-1].x, seg[j].y - seg[j-1].y)
            if (traveled + d >= targetDist) {
              const t2 = d > 0 ? (targetDist - traveled) / d : 0
              return {
                x: seg[j-1].x + t2 * (seg[j].x - seg[j-1].x),
                y: seg[j-1].y + t2 * (seg[j].y - seg[j-1].y),
              }
            }
            traveled += d
          }
          return seg[seg.length - 1]
        }

        // Linear interpolation fallback
        return {
          x: wp.position.x + progress * (next.position.x - wp.position.x),
          y: wp.position.y + progress * (next.position.y - wp.position.y),
        }
      }
    }

    // Past end — stay at last waypoint
    return wps[wps.length - 1].position
  }, [scenario])

  const tick = useCallback((timestamp: number) => {
    if (!animation.isPlaying) return

    const delta = lastTimestampRef.current ? (timestamp - lastTimestampRef.current) / 1000 : 0
    lastTimestampRef.current = timestamp

    // Real time: 1 sim_minute = 1/speed_factor seconds
    const simDelta = delta * animation.speed

    const newTime = animation.currentTime + simDelta

    // Update drone positions
    const positions: Record<string, Position> = {}
    for (const timeline of timelinesRef.current) {
      positions[timeline.droneId] = getPositionAtTime(timeline, newTime)
    }

    setAnimation({ currentTime: newTime, dronePositions: positions })
    rafRef.current = requestAnimationFrame(tick)
  }, [animation.isPlaying, animation.speed, animation.currentTime, getPositionAtTime, setAnimation])

  useEffect(() => {
    if (animation.isPlaying) {
      lastTimestampRef.current = 0
      rafRef.current = requestAnimationFrame(tick)
    } else {
      cancelAnimationFrame(rafRef.current)
    }
    return () => cancelAnimationFrame(rafRef.current)
  }, [animation.isPlaying, tick])

  const play = useCallback(() => setAnimation({ isPlaying: true }), [setAnimation])
  const pause = useCallback(() => setAnimation({ isPlaying: false }), [setAnimation])
  const reset = useCallback(() => setAnimation({ isPlaying: false, currentTime: 0, dronePositions: {} }), [setAnimation])

  return { play, pause, reset, timelines: timelinesRef.current }
}
