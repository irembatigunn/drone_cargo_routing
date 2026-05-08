import { useCallback, useRef } from 'react'
import type { WSMessage } from '../types/domain'

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const openedRef = useRef(false)

  const connect = useCallback((
    runId: string,
    onMessage: (msg: WSMessage) => void,
    onClose?: () => void,
    onError?: () => void,
  ) => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const host = window.location.host
    const url = `${protocol}://${host}/ws/optimize/ga/${runId}`

    openedRef.current = false
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      openedRef.current = true
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as WSMessage
        onMessage(msg)
      } catch (e) {
        console.error('WS parse error', e)
      }
    }

    ws.onclose = (event) => {
      // If never opened, treat as connection failure
      if (!openedRef.current) {
        onError?.()
      }
      onClose?.()
    }

    ws.onerror = () => {
      // onclose will fire after this — defer to onclose logic
    }

    return ws
  }, [])

  const cancel = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'cancel' }))
      wsRef.current.close()
    }
  }, [])

  const disconnect = useCallback(() => {
    wsRef.current?.close()
    wsRef.current = null
  }, [])

  return { connect, cancel, disconnect }
}
