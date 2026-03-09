/** Summary row returned by /api/tasks. */
export interface TaskSummary {
  id: string
  title: string
  description: string
  source: string
  status: string
  priority: number
  human_help_request?: string
  updated_at?: string
  branch_name?: string
  pr_url?: string
  prompt_token_cost?: number
  completion_token_cost?: number
  token_cost?: number
  time_cost_seconds?: number
}

/** Full task payload returned by /api/tasks/:id. */
export interface TaskDetail extends TaskSummary {
  created_at?: string
  plan?: string
  execution_trace?: string
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
  input_tokens?: number
  output_tokens?: number
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

/** Long-term memory row returned by /api/experiences. */
export interface ExperienceEntry {
  id: string
  task_id: string
  category: string
  summary: string
  detail?: string
  tags?: string
  confidence?: number
  created_at?: string
  applied_count?: number
  source_outcome?: string
}

/** Registered model row returned by dashboard model APIs. */
export interface RegisteredModelEntry {
  id: string
  model_type: 'llm' | 'embedding'
  base_url: string
  api_path: string
  model_name: string
  api_key_preview: string
  desc: string
  roocode_wrapper: boolean
  connection_status?: 'success' | 'fail'
  connection_message?: string
  connection_checked_at?: string
  created_at?: string
  updated_at?: string
}

/** One configurable runtime binding point shown in the dashboard. */
export interface ModelBindingPointEntry {
  binding_point: string
  label: string
  description: string
  model_type: 'llm' | 'embedding'
  default_model_id: string
  default_model_name: string
}

/** Saved model selection for one binding point. */
export interface ModelBindingEntry {
  model_id: string
  updated_at?: string
}

/** Full payload for dashboard model registry screen. */
export interface ModelRegistryPayload {
  models: RegisteredModelEntry[]
  bindings: Record<string, ModelBindingEntry>
  binding_points: ModelBindingPointEntry[]
}

/** Startup readiness payload used by setup flow. */
export interface BootstrapStatusPayload {
  ready: boolean
  requires_setup: boolean
  missing: string[]
  recommended_tab: string
  message: string
}

/** One thread in the Inbox. */
export interface ThreadSummary {
  id: string
  title: string
  status: string
  created_by: string
  created_at?: string
  updated_at?: string
}

/** One message inside a thread. */
export interface ThreadMessage {
  id: string
  role: 'agent' | 'human'
  body: string
  created_at?: string
}

/** Full thread detail with messages and linked task ids. */
export interface ThreadDetail {
  thread: ThreadSummary
  messages: ThreadMessage[]
  task_ids: string[]
}

/** Recent discovery projection derived from observer activity. */
export interface DiscoveryEventEntry {
  module?: string
  family?: string
  event_name?: string
  phase?: string
  action?: string
  detail?: string
  reasoning?: string
  task_id?: string
  timestamp?: string
  ts?: string
  success?: boolean
  data?: Record<string, unknown>
  task?: Partial<TaskDetail>
  message?: string
  event?: string
  [key: string]: unknown
}

export interface DiscoveryPayload {
  strategy?: DiscoveryEventEntry | null
  latest_funnel?: DiscoveryEventEntry | null
  candidates: DiscoveryEventEntry[]
  scored: DiscoveryEventEntry[]
  filtered_out: DiscoveryEventEntry[]
  queued: DiscoveryEventEntry[]
  counts: {
    candidates: number
    scored: number
    filtered_out: number
    queued: number
  }
}

export type DashboardSummaryPage = 'overview' | 'work' | 'discovery' | 'memory' | 'control' | 'inbox'

export type DashboardSummaryAction =
  | { kind: 'task'; label: string; taskId: string }
  | { kind: 'thread'; label: string; threadId: string }
  | { kind: 'page'; label: string; page: DashboardSummaryPage }

export interface DashboardSummaryMetric {
  label: string
  value: string
  hint: string
}

export interface DashboardSummaryChange {
  id: string
  label: string
  title: string
  why: string
  timestamp: string
  meta: string
  tone: 'default' | 'success' | 'warning'
  action: DashboardSummaryAction
}

export interface DashboardSummaryAttentionItem {
  id: string
  label: string
  title: string
  detail: string
  tone: 'default' | 'warning'
  action: DashboardSummaryAction
}

export interface DashboardSummaryDestination {
  page: DashboardSummaryPage
  label: string
  description: string
  countLabel?: string
}

export interface DashboardSummaryBriefing {
  eyebrow: string
  title: string
  summary: string
  statusLine: string
  updatedLabel: string
  metrics: DashboardSummaryMetric[]
  notes: string[]
  activeTask?: TaskSummary
  latestCycle?: CycleSummary
}

export interface DashboardSummaryPayload {
  updated_at: string
  briefing: DashboardSummaryBriefing
  changes: DashboardSummaryChange[]
  attention: DashboardSummaryAttentionItem[]
  destinations: DashboardSummaryDestination[]
}
