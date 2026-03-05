import { useCallback, useEffect, useMemo, useState } from 'react'
import { dashboardApiClient } from './api/dashboardApi'
import type {
  CycleSummary,
  DashboardStats,
  DirectivePayload,
  LlmAuditEntry,
  TaskDetail,
  TaskEvent,
  TaskSummary,
} from './types/dashboard'
import './App.css'

type DashboardTab = 'tasks' | 'detail' | 'cycles' | 'activity' | 'audit' | 'control' | 'inject'

const STATUS_CLASS: Record<string, string> = {
  queued: 'badge-queued',
  planning: 'badge-planning',
  running: 'badge-running',
  executing: 'badge-executing',
  completed: 'badge-completed',
  failed: 'badge-failed',
  cancelled: 'badge-cancelled',
  discovered: 'badge-discovered',
}

const PHASE_CLASS: Record<string, string> = {
  cycle: 'phase-cycle',
  discover: 'phase-discover',
  value: 'phase-value',
  plan: 'phase-plan',
  execute: 'phase-execute',
  verify: 'phase-verify',
  git: 'phase-git',
  decision: 'phase-decision',
  system: 'phase-system',
}

function formatTime(iso?: string): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return iso.slice(11, 19) || iso
  }
}

function formatDateTime(iso?: string): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    return d.toLocaleString('en-GB', {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
  } catch {
    return iso
  }
}

interface TaskGroup {
  taskId: string
  title: string
  events: Record<string, unknown>[]
}

function groupActivityByTask(
  events: Record<string, unknown>[],
  taskList: TaskSummary[],
): { global: Record<string, unknown>[]; groups: TaskGroup[] } {
  const titleMap = new Map<string, string>()
  for (const t of taskList) titleMap.set(t.id, t.title)

  const global: Record<string, unknown>[] = []
  const byTask = new Map<string, Record<string, unknown>[]>()

  for (const ev of events) {
    const tid = String(ev.task_id ?? '')
    if (!tid) {
      global.push(ev)
    } else {
      const arr = byTask.get(tid)
      if (arr) arr.push(ev)
      else byTask.set(tid, [ev])
    }
  }

  const groups: TaskGroup[] = []
  for (const [taskId, evts] of byTask) {
    groups.push({
      taskId,
      title: titleMap.get(taskId) ?? `Task ${taskId.slice(0, 8)}`,
      events: evts,
    })
  }
  groups.sort((a, b) => {
    const aTs = String(a.events[a.events.length - 1]?.timestamp ?? '')
    const bTs = String(b.events[b.events.length - 1]?.timestamp ?? '')
    return bTs.localeCompare(aTs)
  })

  return { global, groups }
}

function ActivityByTask({
  activity,
  collapsedTasks,
  onToggle,
  tasks,
}: {
  activity: Record<string, unknown>[]
  collapsedTasks: Set<string>
  onToggle: (id: string) => void
  tasks: TaskSummary[]
}) {
  const { global, groups } = useMemo(
    () => groupActivityByTask(activity, tasks),
    [activity, tasks],
  )

  return (
    <div className="activity-grouped">
      {global.length > 0 ? (
        <div className="task-group">
          <div className="task-group-header">
            <span className="task-group-icon">●</span>
            <span className="task-group-title">Global Events</span>
            <span className="task-group-count">{global.length}</span>
          </div>
          <div className="task-group-events">
            {global.map((ev, idx) => {
              const phase = String(ev.phase ?? '')
              const ts = String(ev.ts ?? ev.timestamp ?? '')
              const msg = String(ev.message ?? ev.detail ?? ev.event ?? JSON.stringify(ev))
              return (
                <div className="activity-item" key={`g-${idx}`}>
                  <span className="activity-ts">{formatTime(ts)}</span>
                  <span className={`activity-phase ${PHASE_CLASS[phase] ?? 'phase-system'}`}>{phase || '?'}</span>
                  <span className="activity-msg">{msg}</span>
                </div>
              )
            })}
          </div>
        </div>
      ) : null}

      {groups.map((group) => {
        const isCollapsed = collapsedTasks.has(group.taskId)
        const lastPhase = String(group.events[group.events.length - 1]?.phase ?? '')
        return (
          <div className="task-group" key={group.taskId}>
            <div
              className="task-group-header"
              onClick={() => onToggle(group.taskId)}
            >
              <span className={`task-group-chevron ${isCollapsed ? 'collapsed' : ''}`}>▾</span>
              <span className={`task-group-phase-dot ${PHASE_CLASS[lastPhase] ?? 'phase-system'}`} />
              <span className="task-group-title">{group.title}</span>
              <span className="task-group-id">{group.taskId.slice(0, 8)}</span>
              <span className="task-group-count">{group.events.length}</span>
            </div>
            {!isCollapsed ? (
              <div className="task-group-events">
                {group.events.map((ev, idx) => {
                  const phase = String(ev.phase ?? '')
                  const ts = String(ev.ts ?? ev.timestamp ?? '')
                  const action = String(ev.action ?? '')
                  const msg = String(ev.message ?? ev.detail ?? ev.event ?? '')
                  const success = ev.success
                  const reasoning = String(ev.reasoning ?? '')
                  return (
                    <div className={`activity-item-grouped ${success === false ? 'is-error' : ''}`} key={idx}>
                      <span className="activity-ts">{formatTime(ts)}</span>
                      <span className={`activity-phase ${PHASE_CLASS[phase] ?? 'phase-system'}`}>{phase}</span>
                      <div className="activity-body">
                        <span className="activity-action">{action}</span>
                        {msg ? <span className="activity-detail">{msg}</span> : null}
                        {success === true ? <span className="activity-ok">✓</span> : null}
                        {success === false ? <span className="activity-fail">✗</span> : null}
                        {reasoning ? <span className="activity-reasoning">{reasoning}</span> : null}
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : null}
          </div>
        )
      })}

      {global.length === 0 && groups.length === 0 ? (
        <p className="log-empty">No activity events</p>
      ) : null}
    </div>
  )
}

function DashboardRoot() {
  const [activeTab, setActiveTab] = useState<DashboardTab>('tasks')
  const [metaText, setMetaText] = useState<string>('Loading...')
  const [toastText, setToastText] = useState<string>('')
  const [toastOk, setToastOk] = useState<boolean>(true)

  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [cycles, setCycles] = useState<CycleSummary[]>([])
  const [stats, setStats] = useState<DashboardStats>({})
  const [directive, setDirective] = useState<DirectivePayload | null>(null)

  const [taskDetail, setTaskDetail] = useState<TaskDetail | null>(null)
  const [taskEvents, setTaskEvents] = useState<TaskEvent[]>([])

  const [activity, setActivity] = useState<Record<string, unknown>[]>([])
  const [activityPhase, setActivityPhase] = useState<string>('')
  const [activityGroupBy, setActivityGroupBy] = useState<'time' | 'task'>('task')
  const [collapsedTasks, setCollapsedTasks] = useState<Set<string>>(new Set())

  const [audit, setAudit] = useState<LlmAuditEntry[]>([])
  const [auditDetail, setAuditDetail] = useState<Record<string, unknown> | null>(null)

  const [injectTitle, setInjectTitle] = useState<string>('')
  const [injectDescription, setInjectDescription] = useState<string>('')
  const [injectPriority, setInjectPriority] = useState<number>(2)
  const [sourcesJson, setSourcesJson] = useState<string>('{}')

  const [pauseLoading, setPauseLoading] = useState<boolean>(false)

  const showToast = (message: string, ok = true): void => {
    setToastText(message)
    setToastOk(ok)
    window.setTimeout(() => setToastText(''), 2800)
  }

  const refreshSummary = useCallback(async (): Promise<void> => {
    try {
      const [taskPayload, cyclePayload, statsPayload, directivePayload] = await Promise.all([
        dashboardApiClient.getTasks(),
        dashboardApiClient.getCycles(),
        dashboardApiClient.getStats(),
        dashboardApiClient.getDirective(),
      ])

      setTasks(taskPayload.tasks ?? [])
      setCycles(cyclePayload.cycles ?? [])
      setStats(statsPayload)
      setDirective(directivePayload)
      setSourcesJson(JSON.stringify(directivePayload.task_sources ?? {}, null, 2))
      setMetaText(`updated ${formatTime(taskPayload.updated_at)} · auto-refresh 5s`)
    } catch (error) {
      const message = `Refresh failed: ${String(error)}`
      setMetaText(message)
      showToast(message, false)
    }
  }, [])

  const togglePause = async (): Promise<void> => {
    if (pauseLoading || !directive) return
    setPauseLoading(true)
    try {
      const result = directive.paused
        ? await dashboardApiClient.resume()
        : await dashboardApiClient.pause()
      showToast(result.paused ? 'Agent paused' : 'Agent resumed')
      await refreshSummary()
    } catch (error) {
      showToast(`Toggle pause failed: ${String(error)}`, false)
    } finally {
      setPauseLoading(false)
    }
  }

  const openTaskDetail = useCallback(async (taskId: string): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getTaskDetail(taskId)
      if (payload.error || !payload.task) {
        showToast(payload.error ?? 'Task not found', false)
        return
      }
      setTaskDetail(payload.task)
      setTaskEvents(payload.events ?? [])
      setActiveTab('detail')
    } catch (error) {
      showToast(`Failed to load task detail: ${String(error)}`, false)
    }
  }, [])

  const refreshActivity = useCallback(async (): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getActivity(300, activityPhase)
      setActivity(payload.events)
    } catch (error) {
      showToast(`Failed to refresh activity: ${String(error)}`, false)
    }
  }, [activityPhase])

  const refreshAudit = useCallback(async (): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getLlmAudit(100)
      setAudit(payload.entries)
    } catch (error) {
      showToast(`Failed to refresh audit: ${String(error)}`, false)
    }
  }, [])

  const openAuditDetail = useCallback(async (seq: number): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getLlmAuditDetail(seq)
      if (payload.error || !payload.entry) {
        showToast(payload.error ?? 'Audit entry not found', false)
        return
      }
      setAuditDetail(payload.entry)
    } catch (error) {
      showToast(`Failed to load audit detail: ${String(error)}`, false)
    }
  }, [])

  const saveDirective = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    if (!directive) {
      showToast('Directive not loaded', false)
      return
    }

    try {
      const form = new FormData(event.currentTarget)
      const payload: DirectivePayload = {
        paused: String(form.get('paused')) === 'true',
        poll_interval_seconds: Number(form.get('poll_interval_seconds') ?? 120),
        max_file_changes_per_task: Number(form.get('max_file_changes_per_task') ?? 10),
        focus_areas: String(form.get('focus_areas') ?? '')
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
        forbidden_paths: String(form.get('forbidden_paths') ?? '')
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
        custom_instructions: String(form.get('custom_instructions') ?? ''),
        task_sources: JSON.parse(sourcesJson),
      }

      await dashboardApiClient.saveDirective(payload)
      showToast('Directive saved')
      await refreshSummary()
    } catch (error) {
      showToast(`Save directive failed: ${String(error)}`, false)
    }
  }

  const injectTask = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    const title = injectTitle.trim()
    if (!title) {
      showToast('Title required', false)
      return
    }

    try {
      await dashboardApiClient.injectTask({
        title,
        description: injectDescription,
        priority: injectPriority,
      })
      showToast('Task injected')
      setInjectTitle('')
      setInjectDescription('')
      setInjectPriority(2)
      await refreshSummary()
    } catch (error) {
      showToast(`Inject task failed: ${String(error)}`, false)
    }
  }

  useEffect(() => {
    const kickoffId = window.setTimeout(() => void refreshSummary(), 0)
    const timerId = window.setInterval(() => void refreshSummary(), 5000)
    return () => {
      window.clearTimeout(kickoffId)
      window.clearInterval(timerId)
    }
  }, [refreshSummary])

  useEffect(() => {
    if (activeTab !== 'activity') return
    const kickoffId = window.setTimeout(() => void refreshActivity(), 0)
    const timerId = window.setInterval(() => void refreshActivity(), 3000)
    return () => {
      window.clearTimeout(kickoffId)
      window.clearInterval(timerId)
    }
  }, [activeTab, refreshActivity])

  useEffect(() => {
    if (activeTab !== 'audit') return
    const kickoffId = window.setTimeout(() => void refreshAudit(), 0)
    const timerId = window.setInterval(() => void refreshAudit(), 5000)
    return () => {
      window.clearTimeout(kickoffId)
      window.clearInterval(timerId)
    }
  }, [activeTab, refreshAudit])

  const sortedStatus = useMemo(() => {
    return Object.entries(stats.status_counts ?? {}).sort((left, right) => Number(right[1]) - Number(left[1]))
  }, [stats])

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">TokenBurn Agent V2</p>
          <h1>Control Plane</h1>
        </div>
        <div className="hero-actions">
          {directive ? (
            <button
              type="button"
              className={`pause-btn ${directive.paused ? 'is-paused' : 'is-running'}`}
              disabled={pauseLoading}
              onClick={() => void togglePause()}
            >
              <span className="status-dot" />
              {pauseLoading ? '...' : directive.paused ? 'Resume Agent' : 'Pause Agent'}
            </button>
          ) : null}
          <p className="meta">{metaText}</p>
        </div>
      </header>

      <section className="stat-grid">
        <article className="stat-card"><p>Total Tasks</p><strong>{stats.total_tasks ?? 0}</strong></article>
        <article className="stat-card"><p>Total Cycles</p><strong>{stats.total_cycles ?? 0}</strong></article>
        <article className="stat-card"><p>Total Tokens</p><strong>{(stats.total_tokens ?? 0).toLocaleString()}</strong></article>
        {sortedStatus.map(([status, count]) => (
          <article className="stat-card" key={status}><p>{status}</p><strong>{String(count)}</strong></article>
        ))}
      </section>

      <nav className="tabbar">
        <button data-active={activeTab === 'tasks'} onClick={() => setActiveTab('tasks')}>Tasks</button>
        {taskDetail ? <button data-active={activeTab === 'detail'} onClick={() => setActiveTab('detail')}>Detail</button> : null}
        <button data-active={activeTab === 'cycles'} onClick={() => setActiveTab('cycles')}>Cycles</button>
        <button data-active={activeTab === 'activity'} onClick={() => setActiveTab('activity')}>Activity</button>
        <button data-active={activeTab === 'audit'} onClick={() => setActiveTab('audit')}>LLM Audit</button>
        <button data-active={activeTab === 'control'} onClick={() => setActiveTab('control')}>Control</button>
        <button data-active={activeTab === 'inject'} onClick={() => setActiveTab('inject')}>Inject</button>
      </nav>

      {/* ── Tasks Table ─── */}
      {activeTab === 'tasks' ? (
        <section className="panel">
          <table>
            <thead>
              <tr>
                <th style={{ minWidth: 260 }}>Task</th>
                <th>Status</th>
                <th>Priority</th>
                <th>Source</th>
                <th>Tokens</th>
                <th>Time</th>
                <th>PR</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.id} onClick={() => void openTaskDetail(task.id)}>
                  <td>
                    <strong>{task.title}</strong>
                    <small>{task.id}</small>
                  </td>
                  <td>
                    <span className={`badge ${STATUS_CLASS[task.status] ?? ''}`}>
                      {task.status}
                    </span>
                  </td>
                  <td>
                    <span className={`priority priority-${task.priority}`}>P{task.priority}</span>
                  </td>
                  <td><span className="source-tag">{task.source}</span></td>
                  <td className="numeric">{task.token_cost ? task.token_cost.toLocaleString() : '-'}</td>
                  <td className="numeric">{task.time_cost_seconds ? `${task.time_cost_seconds.toFixed(1)}s` : '-'}</td>
                  <td>
                    {task.pr_url
                      ? <a className="pr-link" href={task.pr_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>PR</a>
                      : <span className="numeric">-</span>}
                  </td>
                </tr>
              ))}
              {tasks.length === 0 ? (
                <tr><td colSpan={7} className="log-empty">No tasks yet</td></tr>
              ) : null}
            </tbody>
          </table>
        </section>
      ) : null}

      {/* ── Task Detail ─── */}
      {activeTab === 'detail' && taskDetail ? (
        <section className="panel">
          <div className="detail-header">
            <h2>{taskDetail.title}</h2>
            <dl className="detail-meta">
              <div>
                <dt>Status</dt>
                <dd><span className={`badge ${STATUS_CLASS[taskDetail.status] ?? ''}`}>{taskDetail.status}</span></dd>
              </div>
              <div>
                <dt>Priority</dt>
                <dd><span className={`priority priority-${taskDetail.priority}`}>P{taskDetail.priority}</span></dd>
              </div>
              <div>
                <dt>Source</dt>
                <dd><span className="source-tag">{taskDetail.source}</span></dd>
              </div>
              <div>
                <dt>Created</dt>
                <dd style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{formatDateTime(taskDetail.created_at)}</dd>
              </div>
              <div>
                <dt>Updated</dt>
                <dd style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{formatDateTime(taskDetail.updated_at)}</dd>
              </div>
              {taskDetail.token_cost ? (
                <div>
                  <dt>Tokens</dt>
                  <dd style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{taskDetail.token_cost.toLocaleString()}</dd>
                </div>
              ) : null}
              {taskDetail.time_cost_seconds ? (
                <div>
                  <dt>Duration</dt>
                  <dd style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{taskDetail.time_cost_seconds.toFixed(1)}s</dd>
                </div>
              ) : null}
              {taskDetail.branch_name ? (
                <div>
                  <dt>Branch</dt>
                  <dd style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{taskDetail.branch_name}</dd>
                </div>
              ) : null}
              {taskDetail.pr_url ? (
                <div>
                  <dt>PR</dt>
                  <dd><a className="pr-link" href={taskDetail.pr_url} target="_blank" rel="noreferrer">View Pull Request</a></dd>
                </div>
              ) : null}
            </dl>
          </div>

          <div className="detail-body">
            {taskDetail.description ? (
              <div className="detail-section">
                <h3 className="detail-section-title">Description</h3>
                <p style={{ margin: 0, lineHeight: 1.6, fontSize: 13 }}>{taskDetail.description}</p>
              </div>
            ) : null}

            {taskDetail.error_message ? (
              <div className="detail-section">
                <h3 className="detail-section-title" style={{ color: 'var(--danger)' }}>Error</h3>
                <pre style={{ borderColor: 'rgba(248,81,73,0.3)', color: 'var(--danger)' }}>{taskDetail.error_message}</pre>
              </div>
            ) : null}

            {taskDetail.plan ? (
              <div className="detail-section">
                <h3 className="detail-section-title">Execution Plan</h3>
                <pre>{taskDetail.plan}</pre>
              </div>
            ) : null}

            {taskDetail.execution_log ? (
              <div className="detail-section">
                <h3 className="detail-section-title">Execution Log</h3>
                <pre>{taskDetail.execution_log}</pre>
              </div>
            ) : null}

            {taskDetail.verification_result ? (
              <div className="detail-section">
                <h3 className="detail-section-title">Verification</h3>
                <pre>{taskDetail.verification_result}</pre>
              </div>
            ) : null}

            {taskDetail.whats_learned ? (
              <div className="detail-section">
                <h3 className="detail-section-title">What Was Learned</h3>
                <pre>{taskDetail.whats_learned}</pre>
              </div>
            ) : null}

            <div className="detail-section">
              <h3 className="detail-section-title">
                Events <span className="count">{taskEvents.length}</span>
              </h3>
              {taskEvents.length > 0 ? (
                <div className="timeline">
                  {taskEvents.map((ev, idx) => (
                    <div className="timeline-item" key={idx}>
                      <span className="timeline-type">{ev.event_type}</span>
                      <span className="timeline-time">{formatTime(ev.created_at)}</span>
                      {ev.detail ? <div className="timeline-detail">{ev.detail}</div> : null}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="log-empty">No events recorded</p>
              )}
            </div>
          </div>
        </section>
      ) : null}

      {/* ── Cycles Table ─── */}
      {activeTab === 'cycles' ? (
        <section className="panel">
          <table>
            <thead>
              <tr>
                <th>Cycle</th>
                <th>Status</th>
                <th>Started</th>
                <th>Completed</th>
                <th>Discovered</th>
                <th>Executed</th>
                <th>Completed</th>
                <th>Failed</th>
              </tr>
            </thead>
            <tbody>
              {cycles.map((cycle) => (
                <tr key={cycle.id}>
                  <td className="numeric">#{cycle.id}</td>
                  <td><span className={`badge ${STATUS_CLASS[cycle.status] ?? ''}`}>{cycle.status}</span></td>
                  <td className="numeric">{formatDateTime(cycle.started_at)}</td>
                  <td className="numeric">{formatDateTime(cycle.completed_at)}</td>
                  <td className="numeric">{cycle.discovered}</td>
                  <td className="numeric">{cycle.executed}</td>
                  <td className="numeric">{cycle.completed}</td>
                  <td className="numeric">{cycle.failed > 0 ? <span style={{ color: 'var(--danger)' }}>{cycle.failed}</span> : cycle.failed}</td>
                </tr>
              ))}
              {cycles.length === 0 ? (
                <tr><td colSpan={8} className="log-empty">No cycles yet</td></tr>
              ) : null}
            </tbody>
          </table>
        </section>
      ) : null}

      {/* ── Activity Feed ─── */}
      {activeTab === 'activity' ? (
        <section className="panel">
          <div className="toolbar">
            <select value={activityPhase} onChange={(event) => setActivityPhase(event.target.value)}>
              <option value="">All phases</option>
              <option value="cycle">cycle</option>
              <option value="discover">discover</option>
              <option value="value">value</option>
              <option value="plan">plan</option>
              <option value="execute">execute</option>
              <option value="verify">verify</option>
              <option value="git">git</option>
              <option value="decision">decision</option>
              <option value="system">system</option>
            </select>
            <div className="view-toggle">
              <button
                type="button"
                className={activityGroupBy === 'time' ? 'active' : ''}
                onClick={() => setActivityGroupBy('time')}
              >Timeline</button>
              <button
                type="button"
                className={activityGroupBy === 'task' ? 'active' : ''}
                onClick={() => setActivityGroupBy('task')}
              >By Task</button>
            </div>
            <button type="button" onClick={() => void refreshActivity()}>Refresh</button>
          </div>

          {activityGroupBy === 'time' ? (
            <div className="activity-feed">
              {activity.length > 0 ? (
                [...activity].reverse().map((ev, idx) => {
                  const phase = String(ev.phase ?? '')
                  const ts = String(ev.ts ?? ev.timestamp ?? '')
                  const msg = String(ev.message ?? ev.detail ?? ev.event ?? JSON.stringify(ev))
                  const taskId = String(ev.task_id ?? '')
                  return (
                    <div className="activity-item" key={idx}>
                      <span className="activity-ts">{formatTime(ts)}</span>
                      <span className={`activity-phase ${PHASE_CLASS[phase] ?? 'phase-system'}`}>{phase || '?'}</span>
                      <span className="activity-msg">
                        {taskId ? <span className="activity-task-id">{taskId.slice(0, 8)}</span> : null}
                        {msg}
                      </span>
                    </div>
                  )
                })
              ) : (
                <p className="log-empty">No activity events</p>
              )}
            </div>
          ) : (
            <ActivityByTask
              activity={activity}
              collapsedTasks={collapsedTasks}
              onToggle={(id) => {
                setCollapsedTasks((prev) => {
                  const next = new Set(prev)
                  if (next.has(id)) next.delete(id)
                  else next.add(id)
                  return next
                })
              }}
              tasks={tasks}
            />
          )}
        </section>
      ) : null}

      {/* ── LLM Audit ─── */}
      {activeTab === 'audit' ? (
        <section className="panel">
          <table>
            <thead>
              <tr>
                <th>Seq</th>
                <th>Model</th>
                <th>Prompt / Completion</th>
                <th>Latency</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {[...audit].reverse().map((entry) => (
                <tr key={entry.seq} onClick={() => void openAuditDetail(entry.seq)}>
                  <td className="numeric">{entry.seq}</td>
                  <td><span className="source-tag">{entry.model ?? '-'}</span></td>
                  <td className="numeric">{`${(entry.prompt_tokens ?? 0).toLocaleString()} / ${(entry.completion_tokens ?? 0).toLocaleString()}`}</td>
                  <td className="numeric">{entry.duration_ms ? `${(entry.duration_ms / 1000).toFixed(1)}s` : '-'}</td>
                  <td className="numeric">{formatTime(entry.ts)}</td>
                </tr>
              ))}
              {audit.length === 0 ? (
                <tr><td colSpan={5} className="log-empty">No audit entries</td></tr>
              ) : null}
            </tbody>
          </table>
          {auditDetail ? (
            <div style={{ padding: 16, borderTop: '1px solid var(--line)' }}>
              <h3 className="detail-section-title" style={{ marginBottom: 10 }}>
                Audit Entry #{String(auditDetail.seq ?? '')}
              </h3>
              <pre>{JSON.stringify(auditDetail, null, 2)}</pre>
            </div>
          ) : null}
        </section>
      ) : null}

      {/* ── Control Panel ─── */}
      {activeTab === 'control' && directive ? (
        <section className="panel panel-padded">
          <form onSubmit={(event) => void saveDirective(event)}>
            <div className="field-grid">
              <label>Status
                <select name="paused" defaultValue={directive.paused ? 'true' : 'false'}>
                  <option value="false">Running</option>
                  <option value="true">Paused</option>
                </select>
              </label>
              <label>Poll Interval (seconds)
                <input name="poll_interval_seconds" type="number" min={10} defaultValue={directive.poll_interval_seconds} />
              </label>
              <label>Max File Changes
                <input name="max_file_changes_per_task" type="number" min={1} defaultValue={directive.max_file_changes_per_task} />
              </label>
            </div>
            <label>Focus Areas
              <input name="focus_areas" defaultValue={directive.focus_areas.join(', ')} />
            </label>
            <label>Forbidden Paths
              <input name="forbidden_paths" defaultValue={directive.forbidden_paths.join(', ')} />
            </label>
            <label>Custom Instructions
              <textarea name="custom_instructions" defaultValue={directive.custom_instructions} />
            </label>
            <label>Task Sources (JSON)
              <textarea value={sourcesJson} onChange={(event) => setSourcesJson(event.target.value)} rows={8} />
            </label>
            <button type="submit">Save Directive</button>
          </form>
        </section>
      ) : null}

      {/* ── Inject Task ─── */}
      {activeTab === 'inject' ? (
        <section className="panel panel-padded">
          <form onSubmit={(event) => void injectTask(event)}>
            <label>Title
              <input value={injectTitle} onChange={(event) => setInjectTitle(event.target.value)} placeholder="Task title" />
            </label>
            <label>Description
              <textarea value={injectDescription} onChange={(event) => setInjectDescription(event.target.value)} placeholder="What should the agent do?" />
            </label>
            <label>Priority (1 = highest, 5 = lowest)
              <input type="number" min={1} max={5} value={injectPriority} onChange={(event) => setInjectPriority(Number(event.target.value) || 2)} />
            </label>
            <button type="submit">Inject Task</button>
          </form>
        </section>
      ) : null}

      {toastText ? <div className={`toast ${toastOk ? 'ok' : 'error'}`}>{toastText}</div> : null}
    </main>
  )
}

export default DashboardRoot
