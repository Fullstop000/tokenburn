import { useEffect } from 'react'

export function usePollingEffect(refresh: () => Promise<void> | void, intervalMs: number | null) {
  useEffect(() => {
    if (intervalMs === null) return
    const kickoffId = window.setTimeout(() => void refresh(), 0)
    const timerId = window.setInterval(() => void refresh(), intervalMs)
    return () => {
      window.clearTimeout(kickoffId)
      window.clearInterval(timerId)
    }
  }, [intervalMs, refresh])
}
