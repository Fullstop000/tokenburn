import { ArrowRight, FolderKanban, ListTodo, Orbit, ScrollText } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { InlineNotice } from '@/components/ui/inline-notice'
import { PriorityBadge } from '@/components/ui/priority-badge'
import { StatusBadge } from '@/components/ui/status-badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

import { formatDateTime, formatTime, type WorkPanel } from '../lib/dashboardView'
import type { CycleSummary, TaskDetail, TaskEvent, TaskSummary } from '../types/dashboard'

interface WorkPageProps {
  activePanel: WorkPanel
  tasks: TaskSummary[]
  cycles: CycleSummary[]
  taskDetail: TaskDetail | null
  taskEvents: TaskEvent[]
  errorMessage?: string
  onRetry?: () => void
  onChangePanel: (panel: WorkPanel) => void
  onOpenTaskDetail: (taskId: string) => void
}

function panelButtonClass(active: boolean): string {
  return active
    ? 'rounded-full bg-stone-950 text-stone-50 hover:bg-stone-800'
    : 'rounded-full border-stone-200 bg-white text-stone-700 hover:bg-stone-50'
}

function surfaceClass(): string {
  return 'rounded-[1.75rem] border border-stone-200 bg-white/88 shadow-[0_20px_50px_rgba(53,44,34,0.06)]'
}

function prStatusClass(status?: string): string {
  switch (status) {
    case 'merged':
      return 'bg-emerald-100 text-emerald-800'
    case 'closed':
      return 'bg-rose-100 text-rose-800'
    case 'draft':
      return 'bg-amber-100 text-amber-800'
    case 'open':
      return 'bg-sky-100 text-sky-800'
    default:
      return 'bg-stone-100 text-stone-600'
  }
}

function prStatusLabel(status?: string): string {
  if (!status) {
    return 'Linked'
  }
  return status[0].toUpperCase() + status.slice(1)
}

export function WorkPage({
  activePanel,
  tasks,
  cycles,
  taskDetail,
  taskEvents,
  errorMessage,
  onRetry,
  onChangePanel,
  onOpenTaskDetail,
}: WorkPageProps) {
  const panels: Array<{ id: WorkPanel; label: string; icon: typeof ListTodo; description: string }> = [
    { id: 'tasks', label: 'Task Inbox', icon: ListTodo, description: 'Queue health, status, and cost at a glance.' },
    { id: 'detail', label: 'Task Detail', icon: ScrollText, description: 'Execution trace, verification, and local history.' },
    { id: 'cycles', label: 'Cycle Timeline', icon: Orbit, description: 'How discovery and execution changed over recent cycles.' },
  ]

  return (
    <div className="space-y-5">
      {errorMessage && (
        <InlineNotice
          detail={errorMessage}
          onAction={onRetry}
          title="Work data is stale"
          tone="warning"
        />
      )}
      <section className="flex flex-wrap items-start justify-between gap-4 rounded-[1.5rem] border border-stone-200 bg-[linear-gradient(180deg,rgba(249,246,239,0.92),rgba(255,255,255,0.92))] px-5 py-5 shadow-[0_16px_40px_rgba(53,44,34,0.05)]">
        <div className="space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500">Work</p>
          <h3 className="font-serif text-3xl tracking-[-0.03em] text-stone-950">Read the queue before you intervene</h3>
          <p className="max-w-3xl text-sm leading-6 text-stone-600">
            Tasks, details, and cycles now share the same review-desk language as the homepage. Choose the view that matches the depth you need.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {panels.map((panel) => {
            const Icon = panel.icon
            return (
              <Button
                className={panelButtonClass(activePanel === panel.id)}
                key={panel.id}
                size="sm"
                variant="outline"
                onClick={() => onChangePanel(panel.id)}
              >
                <Icon className="h-4 w-4" />
                {panel.label}
              </Button>
            )
          })}
        </div>
      </section>

      {activePanel === 'tasks' && (
        <section className={surfaceClass()}>
          <div className="flex flex-col gap-3 border-b border-stone-200 px-6 py-5 md:flex-row md:items-end md:justify-between">
            <div className="space-y-1">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">Task Inbox</p>
              <h4 className="font-serif text-3xl tracking-[-0.03em] text-stone-950">Current queue and shipped work</h4>
            </div>
            <p className="max-w-xl text-sm leading-6 text-stone-600">
              Priorities, token cost, and PR links stay visible, but the table now reads like a review surface instead of an operations console.
            </p>
          </div>

          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-stone-200">
                  <TableHead className="min-w-[280px] text-stone-500">Task</TableHead>
                  <TableHead className="text-stone-500">Status</TableHead>
                  <TableHead className="text-stone-500">Priority</TableHead>
                  <TableHead className="text-stone-500">Source</TableHead>
                  <TableHead className="text-right text-stone-500">Input</TableHead>
                  <TableHead className="text-right text-stone-500">Output</TableHead>
                  <TableHead className="text-right text-stone-500">Total</TableHead>
                  <TableHead className="text-right text-stone-500">Time</TableHead>
                  <TableHead className="text-stone-500">PR</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tasks.map((task) => (
                  <TableRow className="cursor-pointer border-stone-100 hover:bg-stone-50/80" key={task.id} onClick={() => onOpenTaskDetail(task.id)}>
                    <TableCell>
                      <div className="space-y-1">
                        <div className="font-medium text-stone-950">{task.title}</div>
                        <div className="font-mono text-xs text-stone-500">{task.id}</div>
                      </div>
                    </TableCell>
                    <TableCell><StatusBadge status={task.status} /></TableCell>
                    <TableCell><PriorityBadge priority={task.priority} /></TableCell>
                    <TableCell><code className="rounded-full bg-stone-100 px-2 py-1 text-xs text-stone-700">{task.source}</code></TableCell>
                    <TableCell className="text-right font-mono text-xs text-stone-600">
                      {task.prompt_token_cost ? task.prompt_token_cost.toLocaleString() : '-'}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs text-stone-600">
                      {task.completion_token_cost ? task.completion_token_cost.toLocaleString() : '-'}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs text-stone-600">
                      {task.token_cost ? task.token_cost.toLocaleString() : '-'}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs text-stone-600">
                      {task.time_cost_seconds ? `${task.time_cost_seconds.toFixed(1)}s` : '-'}
                    </TableCell>
                    <TableCell>
                      {task.pr_url ? (
                        <div className="flex flex-col items-start gap-2">
                          <a
                            className="inline-flex items-center gap-1 text-sm text-stone-900 underline-offset-4 hover:underline"
                            href={task.pr_url}
                            onClick={(event) => event.stopPropagation()}
                            rel="noreferrer"
                            target="_blank"
                          >
                            {task.pr_number ? `PR #${task.pr_number}` : 'PR'}
                            <ArrowRight className="h-3.5 w-3.5" />
                          </a>
                          <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${prStatusClass(task.pr_status)}`}>
                            {prStatusLabel(task.pr_status)}
                          </span>
                        </div>
                      ) : (
                        <span className="text-xs text-stone-400">-</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {tasks.length === 0 && (
                  <TableRow className="border-stone-100">
                    <TableCell className="py-10 text-center italic text-stone-500" colSpan={9}>
                      No tasks yet
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </section>
      )}

      {activePanel === 'detail' && (
        <section className={`${surfaceClass()} overflow-hidden`}>
          <div className="flex flex-col gap-3 border-b border-stone-200 bg-[linear-gradient(180deg,rgba(249,246,239,0.92),rgba(255,255,255,0.92))] px-6 py-5 md:flex-row md:items-end md:justify-between">
            <div className="space-y-1">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">Task Detail</p>
              <h4 className="font-serif text-3xl tracking-[-0.03em] text-stone-950">{taskDetail?.title ?? 'Select a task to inspect'}</h4>
            </div>
            <p className="max-w-xl text-sm leading-6 text-stone-600">
              Execution trace, verification output, and task-local events stay together so review can happen in one place.
            </p>
          </div>

          <div className="space-y-6 px-6 py-6">
            {taskDetail ? (
              <>
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                  <div className="rounded-2xl border border-stone-200 bg-stone-50/80 p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">Status</p>
                    <div className="mt-3"><StatusBadge status={taskDetail.status} /></div>
                  </div>
                  <div className="rounded-2xl border border-stone-200 bg-stone-50/80 p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">Priority</p>
                    <div className="mt-3"><PriorityBadge priority={taskDetail.priority} /></div>
                  </div>
                  <div className="rounded-2xl border border-stone-200 bg-stone-50/80 p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">Token Cost</p>
                    <p className="mt-3 font-mono text-sm text-stone-700">
                      {(taskDetail.token_cost ?? 0).toLocaleString()} total
                    </p>
                    <p className="mt-1 font-mono text-xs text-stone-500">
                      {(taskDetail.prompt_token_cost ?? 0).toLocaleString()} in / {(taskDetail.completion_token_cost ?? 0).toLocaleString()} out
                    </p>
                  </div>
                  <div className="rounded-2xl border border-stone-200 bg-stone-50/80 p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">Timestamps</p>
                    <p className="mt-2 text-sm text-stone-700">Created {formatDateTime(taskDetail.created_at)}</p>
                    <p className="mt-1 text-sm text-stone-700">Updated {formatDateTime(taskDetail.updated_at)}</p>
                  </div>
                  <div className="rounded-2xl border border-stone-200 bg-stone-50/80 p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">Pull Request</p>
                    {taskDetail.pr_url ? (
                      <div className="mt-3 space-y-2">
                        <a
                          className="inline-flex items-center gap-1 text-sm text-stone-900 underline-offset-4 hover:underline"
                          href={taskDetail.pr_url}
                          rel="noreferrer"
                          target="_blank"
                        >
                          {taskDetail.pr_number ? `PR #${taskDetail.pr_number}` : 'Open PR'}
                          <ArrowRight className="h-3.5 w-3.5" />
                        </a>
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold ${prStatusClass(taskDetail.pr_status)}`}>
                          {prStatusLabel(taskDetail.pr_status)}
                        </span>
                        {taskDetail.pr_title && (
                          <p className="text-sm text-stone-600">{taskDetail.pr_title}</p>
                        )}
                      </div>
                    ) : (
                      <p className="mt-3 text-sm text-stone-400">No PR linked</p>
                    )}
                  </div>
                </div>

                <div className="space-y-5">
                  {taskDetail.description && (
                    <section className="rounded-[1.5rem] border border-stone-200 bg-white p-5">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">Description</p>
                      <p className="mt-3 text-sm leading-7 text-stone-700">{taskDetail.description}</p>
                    </section>
                  )}

                  <section className="rounded-[1.5rem] border border-stone-200 bg-white p-5">
                    <div className="flex items-center gap-2">
                      <FolderKanban className="h-4 w-4 text-stone-500" />
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">Events</p>
                      <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-500">{taskEvents.length}</span>
                    </div>
                    {taskEvents.length > 0 ? (
                      <div className="mt-4 space-y-3">
                        {taskEvents.map((event, idx) => (
                          <div className="flex items-start gap-3 border-l-2 border-stone-200 pl-3 text-sm" key={idx}>
                            <span className="font-mono text-xs font-semibold text-stone-700">{event.event_type}</span>
                            <span className="font-mono text-xs text-stone-500">{formatTime(event.created_at)}</span>
                            {event.detail && <span className="text-stone-600">{event.detail}</span>}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="mt-4 italic text-stone-500">No events recorded</p>
                    )}
                  </section>

                  {taskDetail.error_message && (
                    <section className="rounded-[1.5rem] border border-rose-200 bg-rose-50/90 p-5">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-rose-700">Error</p>
                      <pre className="mt-3 overflow-auto rounded-2xl bg-white/70 p-4 text-xs text-rose-800">{taskDetail.error_message}</pre>
                    </section>
                  )}

                  {taskDetail.human_help_request && (
                    <section className="rounded-[1.5rem] border border-amber-200 bg-amber-50/95 p-5">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-700">Human Help Request</p>
                      <pre className="mt-3 overflow-auto rounded-2xl bg-white/70 p-4 text-xs text-amber-900">{taskDetail.human_help_request}</pre>
                    </section>
                  )}

                  {taskDetail.whats_learned && (
                    <section className="rounded-[1.5rem] border border-stone-200 bg-white p-5">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">What Was Learned</p>
                      <pre className="mt-3 overflow-auto rounded-2xl bg-stone-100 p-4 text-xs text-stone-800">{taskDetail.whats_learned}</pre>
                    </section>
                  )}

                  {taskDetail.plan && (
                    <section className="rounded-[1.5rem] border border-stone-200 bg-white p-5">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">Execution Plan</p>
                      <pre className="mt-3 overflow-auto rounded-2xl bg-stone-100 p-4 text-xs text-stone-800">{taskDetail.plan}</pre>
                    </section>
                  )}

                  {taskDetail.execution_log && (
                    <section className="rounded-[1.5rem] border border-stone-200 bg-white p-5">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">Execution Log</p>
                      <pre className="mt-3 overflow-auto rounded-2xl bg-stone-100 p-4 text-xs text-stone-800">{taskDetail.execution_log}</pre>
                    </section>
                  )}

                  {taskDetail.verification_result && (
                    <section className="rounded-[1.5rem] border border-stone-200 bg-white p-5">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">Verification</p>
                      <pre className="mt-3 overflow-auto rounded-2xl bg-stone-100 p-4 text-xs text-stone-800">{taskDetail.verification_result}</pre>
                    </section>
                  )}
                </div>
              </>
            ) : (
              <div className="rounded-[1.5rem] border border-dashed border-stone-300 bg-stone-50/80 p-8 text-sm text-stone-600">
                No task selected yet.
              </div>
            )}
          </div>
        </section>
      )}

      {activePanel === 'cycles' && (
        <section className={surfaceClass()}>
          <div className="flex flex-col gap-3 border-b border-stone-200 px-6 py-5 md:flex-row md:items-end md:justify-between">
            <div className="space-y-1">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">Cycle Timeline</p>
              <h4 className="font-serif text-3xl tracking-[-0.03em] text-stone-950">Recent agent cycles</h4>
            </div>
            <p className="max-w-xl text-sm leading-6 text-stone-600">
              Review discovery and execution volume over time without leaving the work surface.
            </p>
          </div>

          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-stone-200">
                  <TableHead className="text-stone-500">Cycle</TableHead>
                  <TableHead className="text-stone-500">Status</TableHead>
                  <TableHead className="text-stone-500">Started</TableHead>
                  <TableHead className="text-stone-500">Completed</TableHead>
                  <TableHead className="text-right text-stone-500">Discovered</TableHead>
                  <TableHead className="text-right text-stone-500">Executed</TableHead>
                  <TableHead className="text-right text-stone-500">Completed</TableHead>
                  <TableHead className="text-right text-stone-500">Failed</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cycles.map((cycle) => (
                  <TableRow className="border-stone-100 hover:bg-stone-50/80" key={cycle.id}>
                    <TableCell className="font-mono text-stone-700">#{cycle.id}</TableCell>
                    <TableCell><StatusBadge status={cycle.status} /></TableCell>
                    <TableCell className="font-mono text-xs text-stone-600">{formatDateTime(cycle.started_at)}</TableCell>
                    <TableCell className="font-mono text-xs text-stone-600">{formatDateTime(cycle.completed_at)}</TableCell>
                    <TableCell className="text-right text-stone-700">{cycle.discovered}</TableCell>
                    <TableCell className="text-right text-stone-700">{cycle.executed}</TableCell>
                    <TableCell className="text-right text-stone-700">{cycle.completed}</TableCell>
                    <TableCell className={`text-right ${cycle.failed > 0 ? 'font-semibold text-rose-700' : 'text-stone-700'}`}>{cycle.failed}</TableCell>
                  </TableRow>
                ))}
                {cycles.length === 0 && (
                  <TableRow className="border-stone-100">
                    <TableCell className="py-10 text-center italic text-stone-500" colSpan={8}>
                      No cycles yet
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </section>
      )}
    </div>
  )
}
