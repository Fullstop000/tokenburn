import { useCallback, useState } from 'react'

import { dashboardApiClient } from '../api/dashboardApi'
import { formatTime } from '../lib/dashboardView'
import type {
  BootstrapStatusPayload,
  CycleSummary,
  DashboardSummaryPayload,
  DirectivePayload,
  TaskSummary,
} from '../types/dashboard'

interface UseDashboardDataArgs {
  friendlyLoadError: (scope: string, error: unknown) => string
}

export function useDashboardData({ friendlyLoadError }: UseDashboardDataArgs) {
  const [metaText, setMetaText] = useState('Loading...')
  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [cycles, setCycles] = useState<CycleSummary[]>([])
  const [directive, setDirective] = useState<DirectivePayload | null>(null)
  const [bootstrapStatus, setBootstrapStatus] = useState<BootstrapStatusPayload | null>(null)
  const [summary, setSummary] = useState<DashboardSummaryPayload | null>(null)
  const [helpRequests, setHelpRequests] = useState<TaskSummary[]>([])
  const [helpCount, setHelpCount] = useState(0)
  const [summaryError, setSummaryError] = useState('')
  const [helpError, setHelpError] = useState('')

  const refreshSummary = useCallback(async (): Promise<void> => {
    try {
      const [taskPayload, cyclePayload, statsPayload, directivePayload, bootstrapPayload, summaryPayload] = await Promise.all([
        dashboardApiClient.getTasks(),
        dashboardApiClient.getCycles(),
        dashboardApiClient.getStats(),
        dashboardApiClient.getDirective(),
        dashboardApiClient.getBootstrapStatus(),
        dashboardApiClient.getSummary(),
      ])
      setTasks(taskPayload.tasks ?? [])
      setCycles(cyclePayload.cycles ?? [])
      setHelpCount(Number(statsPayload.status_counts?.needs_human ?? 0))
      setDirective(directivePayload)
      setBootstrapStatus(bootstrapPayload)
      setSummary(summaryPayload)
      setMetaText(`updated ${formatTime(taskPayload.updated_at)} · auto-refresh 5s`)
      setSummaryError('')
    } catch (error) {
      const message = friendlyLoadError('Overview data', error)
      setSummaryError(message)
      setMetaText(message)
    }
  }, [friendlyLoadError])

  const refreshHelpCenter = useCallback(async (): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getHelpCenter()
      setHelpRequests(payload.requests ?? [])
      setHelpError('')
    } catch (error) {
      setHelpError(friendlyLoadError('Help center', error))
    }
  }, [friendlyLoadError])

  return {
    bootstrapStatus,
    cycles,
    directive,
    helpCount,
    helpError,
    helpRequests,
    metaText,
    refreshHelpCenter,
    refreshSummary,
    summary,
    summaryError,
    tasks,
  }
}
