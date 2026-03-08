import type { TaskSummary } from '../types/dashboard'

export type DashboardPage = 'overview' | 'work' | 'discovery' | 'memory' | 'control' | 'inbox'
export type WorkPanel = 'tasks' | 'detail' | 'cycles'
export type MemoryPanel = 'activity' | 'audit' | 'experience'
export type ControlPanel = 'models' | 'directive' | 'help' | 'inject'

export interface ActivityEvent {
  module?: string
  family?: string
  event_name?: string
  phase?: string
  action?: string
  detail?: string
  reasoning?: string
  message?: string
  event?: string
  task_id?: string
  timestamp?: string
  ts?: string
  success?: boolean
  data?: Record<string, unknown>
  task?: {
    id?: string
    title?: string
    status?: string
    branch_name?: string
    pr_url?: string
    execution_trace?: string
    execution_log?: string
    error_message?: string
    updated_at?: string
  }
  [key: string]: unknown
}

export interface TaskGroup {
  taskId: string
  title: string
  events: ActivityEvent[]
}

export interface DiscoverySnapshot {
  latestFunnel?: ActivityEvent
  strategy?: ActivityEvent
  candidates: ActivityEvent[]
  scored: ActivityEvent[]
  filteredOut: ActivityEvent[]
  queued: ActivityEvent[]
}

function normalizeModule(module?: string): string {
  return String(module ?? '').trim()
}

export function eventBadgeVariant(event: ActivityEvent): string {
  const module = normalizeModule(event.module).toLowerCase()
  return module || 'system'
}

export function eventBadgeLabel(event: ActivityEvent): string {
  return normalizeModule(event.module) || 'Unknown'
}

export function eventDisplayName(event: ActivityEvent): string {
  return String(event.event_name ?? '')
}

export function formatTime(iso?: string): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return iso.slice(11, 19) || iso
  }
}

export function formatDateTime(iso?: string): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    return d.toLocaleString('en-GB', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return iso
  }
}

export function groupActivityByTask(
  events: ActivityEvent[],
  taskList: TaskSummary[],
): { global: ActivityEvent[]; groups: TaskGroup[] } {
  const titleMap = new Map<string, string>()
  for (const t of taskList) titleMap.set(t.id, t.title)

  const global: ActivityEvent[] = []
  const byTask = new Map<string, ActivityEvent[]>()

  for (const ev of events) {
    const tid = String(ev.task_id ?? '')
    if (!tid) {
      global.push(ev)
      continue
    }
    const arr = byTask.get(tid)
    if (arr) arr.push(ev)
    else byTask.set(tid, [ev])
  }

  const groups = Array.from(byTask.entries()).map(([taskId, evts]) => ({
    taskId,
    title: titleMap.get(taskId) ?? `Task ${taskId.slice(0, 8)}`,
    events: evts,
  }))

  groups.sort((a, b) => {
    const aTs = String(a.events[a.events.length - 1]?.timestamp ?? a.events[a.events.length - 1]?.ts ?? '')
    const bTs = String(b.events[b.events.length - 1]?.timestamp ?? b.events[b.events.length - 1]?.ts ?? '')
    return bTs.localeCompare(aTs)
  })

  return { global, groups }
}

export function buildDiscoverySnapshot(events: ActivityEvent[]): DiscoverySnapshot {
  const discover = events.filter((ev) =>
    ev.module === 'Discovery'
    && ['strategy', 'candidate', 'queue', 'funnel'].includes(String(ev.family ?? '')),
  )
  const value = events.filter((ev) =>
    ev.module === 'Discovery' && ev.family === 'valuation',
  )
  return {
    latestFunnel: [...discover].reverse().find((ev) => ev.event_name === 'funnel_summarized'),
    strategy: [...discover].reverse().find((ev) => ev.event_name === 'strategy_selected'),
    candidates: discover.filter((ev) => ev.event_name === 'candidate_found').slice(-12).reverse(),
    scored: value.filter((ev) => ev.event_name === 'candidate_scored').slice(-12).reverse(),
    filteredOut: value.filter((ev) => ev.event_name === 'candidate_filtered_out').slice(-12).reverse(),
    queued: discover.filter((ev) => ev.event_name === 'candidate_queued').slice(-12).reverse(),
  }
}

export function formatActivityMessage(event: ActivityEvent): string {
  return String(event.message ?? event.detail ?? event.event ?? JSON.stringify(event))
}
