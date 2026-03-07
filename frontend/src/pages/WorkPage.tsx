import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
  onChangePanel: (panel: WorkPanel) => void
  onOpenTaskDetail: (taskId: string) => void
}

export function WorkPage({
  activePanel,
  tasks,
  cycles,
  taskDetail,
  taskEvents,
  onChangePanel,
  onOpenTaskDetail,
}: WorkPageProps) {
  const panels: WorkPanel[] = ['tasks', 'detail', 'cycles']

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {panels.map((panel) => (
          <Button
            key={panel}
            size="sm"
            variant={activePanel === panel ? 'default' : 'outline'}
            onClick={() => onChangePanel(panel)}
          >
            {panel === 'tasks' ? 'Task Inbox' : panel === 'detail' ? 'Task Detail' : 'Cycle Timeline'}
          </Button>
        ))}
      </div>

      {activePanel === 'tasks' && (
        <Card className="border-border/60 bg-card/70">
          <CardHeader>
            <CardTitle>Task Inbox</CardTitle>
            <CardDescription>Current queue, execution status, and shipped changes.</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="min-w-[260px]">Task</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Priority</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead className="text-right">Tokens</TableHead>
                  <TableHead className="text-right">Time</TableHead>
                  <TableHead>PR</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tasks.map((task) => (
                  <TableRow className="cursor-pointer" key={task.id} onClick={() => onOpenTaskDetail(task.id)}>
                    <TableCell>
                      <div className="font-medium">{task.title}</div>
                      <div className="font-mono text-xs text-muted-foreground">{task.id}</div>
                    </TableCell>
                    <TableCell><StatusBadge status={task.status} /></TableCell>
                    <TableCell><PriorityBadge priority={task.priority} /></TableCell>
                    <TableCell><code className="rounded bg-muted px-1.5 py-0.5 text-xs">{task.source}</code></TableCell>
                    <TableCell className="text-right font-mono text-xs text-muted-foreground">
                      {task.token_cost ? task.token_cost.toLocaleString() : '-'}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs text-muted-foreground">
                      {task.time_cost_seconds ? `${task.time_cost_seconds.toFixed(1)}s` : '-'}
                    </TableCell>
                    <TableCell>
                      {task.pr_url ? (
                        <a
                          className="text-sm text-primary hover:underline"
                          href={task.pr_url}
                          onClick={(event) => event.stopPropagation()}
                          rel="noreferrer"
                          target="_blank"
                        >
                          PR ↗
                        </a>
                      ) : (
                        <span className="text-xs text-muted-foreground">-</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {tasks.length === 0 && (
                  <TableRow>
                    <TableCell className="py-8 text-center italic text-muted-foreground" colSpan={7}>
                      No tasks yet
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {activePanel === 'detail' && (
        <Card className="border-border/60 bg-card/70">
          <CardHeader>
            <CardTitle>{taskDetail?.title ?? 'Task Detail'}</CardTitle>
            <CardDescription>
              {taskDetail ? 'Execution trace, verification, and task-local event history.' : 'Select a task from the inbox to inspect its detail.'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {taskDetail ? (
              <>
                <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
                  <span>Status: <StatusBadge status={taskDetail.status} /></span>
                  <span>Priority: <PriorityBadge priority={taskDetail.priority} /></span>
                  <span>Source: <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{taskDetail.source}</code></span>
                  <span>Created: <span className="font-mono text-xs">{formatDateTime(taskDetail.created_at)}</span></span>
                  <span>Updated: <span className="font-mono text-xs">{formatDateTime(taskDetail.updated_at)}</span></span>
                </div>

                {taskDetail.description && (
                  <section>
                    <h3 className="mb-2 text-sm font-semibold uppercase text-muted-foreground">Description</h3>
                    <p className="text-sm leading-relaxed">{taskDetail.description}</p>
                  </section>
                )}

                {taskDetail.error_message && (
                  <section>
                    <h3 className="mb-2 text-sm font-semibold uppercase text-destructive">Error</h3>
                    <pre className="overflow-auto rounded-md border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">{taskDetail.error_message}</pre>
                  </section>
                )}

                {taskDetail.human_help_request && (
                  <section>
                    <h3 className="mb-2 text-sm font-semibold uppercase text-amber-400">Human Help Request</h3>
                    <pre className="overflow-auto rounded-md border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-50/90">{taskDetail.human_help_request}</pre>
                  </section>
                )}

                {taskDetail.plan && (
                  <section>
                    <h3 className="mb-2 text-sm font-semibold uppercase text-muted-foreground">Execution Plan</h3>
                    <pre className="overflow-auto rounded-md bg-muted p-3 text-xs">{taskDetail.plan}</pre>
                  </section>
                )}

                {taskDetail.execution_log && (
                  <section>
                    <h3 className="mb-2 text-sm font-semibold uppercase text-muted-foreground">Execution Log</h3>
                    <pre className="overflow-auto rounded-md bg-muted p-3 text-xs">{taskDetail.execution_log}</pre>
                  </section>
                )}

                {taskDetail.verification_result && (
                  <section>
                    <h3 className="mb-2 text-sm font-semibold uppercase text-muted-foreground">Verification</h3>
                    <pre className="overflow-auto rounded-md bg-muted p-3 text-xs">{taskDetail.verification_result}</pre>
                  </section>
                )}

                {taskDetail.whats_learned && (
                  <section>
                    <h3 className="mb-2 text-sm font-semibold uppercase text-muted-foreground">What Was Learned</h3>
                    <pre className="overflow-auto rounded-md bg-muted p-3 text-xs">{taskDetail.whats_learned}</pre>
                  </section>
                )}

                <section>
                  <h3 className="mb-2 text-sm font-semibold uppercase text-muted-foreground">
                    Events <span className="rounded-full bg-muted px-2 py-0.5 text-xs">{taskEvents.length}</span>
                  </h3>
                  {taskEvents.length > 0 ? (
                    <div className="space-y-2">
                      {taskEvents.map((event, idx) => (
                        <div className="flex items-start gap-3 border-l-2 border-muted pl-3 text-sm" key={idx}>
                          <span className="font-mono text-xs font-semibold text-primary">{event.event_type}</span>
                          <span className="font-mono text-xs text-muted-foreground">{formatTime(event.created_at)}</span>
                          {event.detail && <span className="text-muted-foreground">{event.detail}</span>}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="italic text-muted-foreground">No events recorded</p>
                  )}
                </section>
              </>
            ) : (
              <div className="rounded-xl border border-dashed border-border/60 bg-muted/20 p-6 text-sm text-muted-foreground">
                No task selected yet.
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {activePanel === 'cycles' && (
        <Card className="border-border/60 bg-card/70">
          <CardHeader>
            <CardTitle>Cycle Timeline</CardTitle>
            <CardDescription>Discovery and execution volume across recent cycles.</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Cycle</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Completed</TableHead>
                  <TableHead className="text-right">Discovered</TableHead>
                  <TableHead className="text-right">Executed</TableHead>
                  <TableHead className="text-right">Completed</TableHead>
                  <TableHead className="text-right">Failed</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cycles.map((cycle) => (
                  <TableRow key={cycle.id}>
                    <TableCell className="font-mono">#{cycle.id}</TableCell>
                    <TableCell><StatusBadge status={cycle.status} /></TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{formatDateTime(cycle.started_at)}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{formatDateTime(cycle.completed_at)}</TableCell>
                    <TableCell className="text-right">{cycle.discovered}</TableCell>
                    <TableCell className="text-right">{cycle.executed}</TableCell>
                    <TableCell className="text-right">{cycle.completed}</TableCell>
                    <TableCell className={`text-right ${cycle.failed > 0 ? 'font-semibold text-destructive' : ''}`}>{cycle.failed}</TableCell>
                  </TableRow>
                ))}
                {cycles.length === 0 && (
                  <TableRow>
                    <TableCell className="py-8 text-center italic text-muted-foreground" colSpan={8}>
                      No cycles yet
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
