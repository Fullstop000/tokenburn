import { useCallback, useState } from 'react'

import { dashboardApiClient } from '../api/dashboardApi'
import type { ActivityEvent } from '../lib/dashboardView'
import type { DiscoveryPayload, ExperienceEntry, LlmAuditEntry } from '../types/dashboard'

interface UseMemoryStateArgs {
  friendlyLoadError: (scope: string, error: unknown) => string
  showToast: (message: string, ok?: boolean) => void
  onActivityError: (message: string) => void
  onDiscoveryError: (message: string) => void
  onAuditError: (message: string) => void
  onExperiencesError: (message: string) => void
}

export function useMemoryState({
  friendlyLoadError,
  showToast,
  onActivityError,
  onDiscoveryError,
  onAuditError,
  onExperiencesError,
}: UseMemoryStateArgs) {
  const [activity, setActivity] = useState<ActivityEvent[]>([])
  const [discovery, setDiscovery] = useState<DiscoveryPayload | null>(null)
  const [activityPhase, setActivityPhase] = useState('')
  const [activityGroupBy, setActivityGroupBy] = useState<'time' | 'task'>('task')
  const [collapsedTasks, setCollapsedTasks] = useState<Set<string>>(new Set())
  const [audit, setAudit] = useState<LlmAuditEntry[]>([])
  const [auditDetail, setAuditDetail] = useState<LlmAuditEntry | null>(null)
  const [experiences, setExperiences] = useState<ExperienceEntry[]>([])

  const refreshActivity = useCallback(async (): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getActivity(300, activityPhase)
      setActivity((payload.events ?? []) as ActivityEvent[])
      onActivityError('')
    } catch (error) {
      onActivityError(friendlyLoadError('Activity history', error))
    }
  }, [activityPhase, friendlyLoadError, onActivityError])

  const refreshDiscovery = useCallback(async (): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getDiscovery(24)
      setDiscovery(payload)
      onDiscoveryError('')
    } catch (error) {
      onDiscoveryError(friendlyLoadError('Discovery history', error))
    }
  }, [friendlyLoadError, onDiscoveryError])

  const refreshAudit = useCallback(async (): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getLlmAudit(100)
      setAudit(payload.entries)
      onAuditError('')
    } catch (error) {
      onAuditError(friendlyLoadError('LLM audit', error))
    }
  }, [friendlyLoadError, onAuditError])

  const refreshExperiences = useCallback(async (): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getExperiences(200)
      setExperiences(payload.experiences ?? [])
      onExperiencesError('')
    } catch (error) {
      onExperiencesError(friendlyLoadError('Experience memory', error))
    }
  }, [friendlyLoadError, onExperiencesError])

  const openAuditDetail = useCallback(async (seq: number): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getLlmAuditDetail(seq)
      if (payload.error || !payload.entry) {
        showToast(payload.error ?? 'Audit entry not found', false)
        return
      }
      setAuditDetail(payload.entry as unknown as LlmAuditEntry)
    } catch (error) {
      showToast(`Failed to load audit detail: ${String(error)}`, false)
    }
  }, [showToast])

  const toggleCollapsedTask = useCallback((taskId: string): void => {
    setCollapsedTasks((current) => {
      const next = new Set(current)
      if (next.has(taskId)) next.delete(taskId)
      else next.add(taskId)
      return next
    })
  }, [])

  return {
    activity,
    activityGroupBy,
    activityPhase,
    audit,
    auditDetail,
    collapsedTasks,
    discovery,
    experiences,
    openAuditDetail,
    refreshActivity,
    refreshAudit,
    refreshDiscovery,
    refreshExperiences,
    setActivityGroupBy,
    setActivityPhase,
    setAuditDetail,
    toggleCollapsedTask,
  }
}
