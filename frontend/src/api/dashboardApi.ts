import type {
  CycleSummary,
  DashboardStats,
  DirectivePayload,
  LlmAuditEntry,
  TaskDetail,
  TaskEvent,
  TaskSummary,
} from '../types/dashboard'

/** HTTP client dedicated to dashboard backend APIs. */
export class DashboardApiClient {
  private readonly baseUrl: string

  /** Create client with optional base URL prefix. */
  constructor(baseUrl = '') {
    this.baseUrl = baseUrl
  }

  /** Execute one JSON request and throw contextual errors when it fails. */
  private async requestJson<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, init)
    if (!response.ok) {
      throw new Error(`Request failed (${response.status}) for ${path}`)
    }
    return (await response.json()) as T
  }

  /** Fetch task summary list. */
  getTasks(): Promise<{ updated_at: string; tasks: TaskSummary[] }> {
    return this.requestJson('/api/tasks')
  }

  /** Fetch one task detail and its event timeline. */
  getTaskDetail(taskId: string): Promise<{ task?: TaskDetail; events?: TaskEvent[]; error?: string }> {
    return this.requestJson(`/api/tasks/${encodeURIComponent(taskId)}`)
  }

  /** Fetch latest cycle summary rows. */
  getCycles(): Promise<{ cycles: CycleSummary[] }> {
    return this.requestJson('/api/cycles')
  }

  /** Fetch aggregate dashboard counters. */
  getStats(): Promise<DashboardStats> {
    return this.requestJson('/api/stats')
  }

  /** Fetch current runtime directive. */
  getDirective(): Promise<DirectivePayload> {
    return this.requestJson('/api/directive')
  }

  /** Pause the agent immediately. */
  pause(): Promise<{ status: string; paused: boolean }> {
    return this.requestJson('/api/pause', { method: 'POST' })
  }

  /** Resume the agent immediately. */
  resume(): Promise<{ status: string; paused: boolean }> {
    return this.requestJson('/api/resume', { method: 'POST' })
  }

  /** Persist directive updates from control panel form. */
  saveDirective(payload: DirectivePayload): Promise<{ status: string; directive: DirectivePayload }> {
    return this.requestJson('/api/directive', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  }

  /** Create a manual task from dashboard inject form. */
  injectTask(payload: {
    title: string
    description: string
    priority: number
  }): Promise<{ status?: string; task_id?: string; error?: string }> {
    return this.requestJson('/api/tasks/inject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  }

  /** Fetch recent activity stream events. */
  getActivity(limit = 250, phase = ''): Promise<{ events: Record<string, unknown>[]; total_returned: number }> {
    const query = phase ? `?limit=${limit}&phase=${encodeURIComponent(phase)}` : `?limit=${limit}`
    return this.requestJson(`/api/activity${query}`)
  }

  /** Fetch recent audit list for LLM calls. */
  getLlmAudit(limit = 100): Promise<{ entries: LlmAuditEntry[]; total_returned: number }> {
    return this.requestJson(`/api/llm-audit?limit=${limit}`)
  }

  /** Fetch one full LLM audit record. */
  getLlmAuditDetail(seq: number): Promise<{ entry?: Record<string, unknown>; error?: string }> {
    return this.requestJson(`/api/llm-audit/${seq}`)
  }
}

/** Singleton client used by dashboard UI screens. */
export const dashboardApiClient = new DashboardApiClient('')
