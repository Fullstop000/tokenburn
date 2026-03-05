/** Summary row returned by /api/tasks. */
export interface TaskSummary {
  id: string
  title: string
  description: string
  source: string
  status: string
  priority: number
  updated_at?: string
  branch_name?: string
  pr_url?: string
  token_cost?: number
  time_cost_seconds?: number
}

/** Full task payload returned by /api/tasks/:id. */
export interface TaskDetail extends TaskSummary {
  created_at?: string
  plan?: string
  execution_log?: string
  verification_result?: string
  error_message?: string
  whats_learned?: string
  cycle_id?: number
}

/** Timeline row returned alongside task detail. */
export interface TaskEvent {
  created_at?: string
  event_type: string
  detail?: string
}

/** Cycle summary item returned by /api/cycles. */
export interface CycleSummary {
  id: number
  started_at?: string
  completed_at?: string
  status: string
  discovered: number
  executed: number
  completed: number
  failed: number
}

/** Aggregated stats payload from /api/stats. */
export interface DashboardStats {
  total_tasks?: number
  total_cycles?: number
  total_tokens?: number
  status_counts?: Record<string, number>
}

/** Config for one discovery task source. */
export interface TaskSourceSetting {
  enabled: boolean
  priority: number
}

/** Directive document read and written by dashboard control panel. */
export interface DirectivePayload {
  paused: boolean
  focus_areas: string[]
  forbidden_paths: string[]
  max_file_changes_per_task: number
  custom_instructions: string
  poll_interval_seconds: number
  task_sources: Record<string, TaskSourceSetting>
}

/** LLM audit entry summary row. */
export interface LlmAuditEntry {
  seq: number
  ts?: string
  model?: string
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  duration_ms?: number
  error?: string
}
