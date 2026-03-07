import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { PhaseBadge } from '@/components/ui/phase-badge'
import { StatusBadge } from '@/components/ui/status-badge'

import { formatDateTime, formatTime, type ActivityEvent, type DashboardPage } from '../lib/dashboardView'
import type { BootstrapStatusPayload, CycleSummary, DashboardStats, DirectivePayload, TaskSummary } from '../types/dashboard'

interface OverviewPageProps {
  bootstrapStatus: BootstrapStatusPayload | null
  directive: DirectivePayload | null
  stats: DashboardStats
  tasks: TaskSummary[]
  cycles: CycleSummary[]
  helpRequests: TaskSummary[]
  activity: ActivityEvent[]
  onNavigate: (page: DashboardPage) => void
  onOpenTaskDetail: (taskId: string) => void
}

export function OverviewPage({
  bootstrapStatus,
  directive,
  stats,
  tasks,
  cycles,
  helpRequests,
  activity,
  onNavigate,
  onOpenTaskDetail,
}: OverviewPageProps) {
  const statusCards = [
    { label: 'Total Tasks', value: stats.total_tasks ?? 0 },
    { label: 'Total Cycles', value: stats.total_cycles ?? 0 },
    { label: 'Total Tokens', value: (stats.total_tokens ?? 0).toLocaleString() },
    { label: 'Needs Human', value: Number(stats.status_counts?.needs_human ?? 0) },
  ]
  const activeTask = tasks.find((task) => task.status === 'executing')
  const latestCycle = cycles[0]
  const latestEvents = [...activity].slice(-6).reverse()
  const recentTaskUpdates = tasks.slice(0, 5)

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {statusCards.map((card) => (
          <Card className="border-border/60 bg-card/70" key={card.label}>
            <CardHeader className="pb-3">
              <CardDescription className="text-[11px] uppercase tracking-[0.18em]">{card.label}</CardDescription>
              <CardTitle className="text-3xl">{card.value}</CardTitle>
            </CardHeader>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.3fr_0.9fr]">
        <Card className="border-border/60 bg-card/70">
          <CardHeader>
            <CardTitle>System Health</CardTitle>
            <CardDescription>Runtime readiness, operator controls, and current execution status.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-border/60 bg-muted/30 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Bootstrap</p>
              <p className="mt-2 text-sm text-foreground">
                {bootstrapStatus?.ready ? 'Ready for execution' : 'Setup incomplete'}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">{bootstrapStatus?.message ?? 'Loading bootstrap status...'}</p>
            </div>
            <div className="rounded-xl border border-border/60 bg-muted/30 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Runtime</p>
              <p className="mt-2 text-sm text-foreground">{directive?.paused ? 'Paused by directive' : 'Polling loop active'}</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {activeTask ? `Currently executing: ${activeTask.title}` : 'No task is executing right now.'}
              </p>
            </div>
            <div className="rounded-xl border border-border/60 bg-muted/30 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Latest Cycle</p>
              {latestCycle ? (
                <>
                  <div className="mt-2 flex items-center gap-2">
                    <span className="font-mono text-sm">#{latestCycle.id}</span>
                    <StatusBadge status={latestCycle.status} />
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">
                    {latestCycle.discovered} discovered, {latestCycle.executed} executed, {latestCycle.failed} failed.
                  </p>
                </>
              ) : (
                <p className="mt-2 text-sm text-muted-foreground">No cycle data yet.</p>
              )}
            </div>
            <div className="rounded-xl border border-border/60 bg-muted/30 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Needs Attention</p>
              <p className="mt-2 text-sm text-foreground">{helpRequests.length} unresolved human-help requests</p>
              <div className="mt-3 flex gap-2">
                <Button size="sm" variant="outline" onClick={() => onNavigate('control')}>Open Control</Button>
                <Button size="sm" variant="outline" onClick={() => onNavigate('discovery')}>Open Discovery</Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border/60 bg-card/70">
          <CardHeader>
            <CardTitle>Now Running</CardTitle>
            <CardDescription>Current task focus and latest observable events.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {activeTask ? (
              <button
                className="w-full rounded-xl border border-border/60 bg-muted/30 p-4 text-left transition hover:bg-muted/50"
                onClick={() => onOpenTaskDetail(activeTask.id)}
                type="button"
              >
                <div className="flex items-center gap-2">
                  <StatusBadge status={activeTask.status} />
                  <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{activeTask.source}</code>
                </div>
                <p className="mt-3 text-base font-medium">{activeTask.title}</p>
                <p className="mt-1 font-mono text-xs text-muted-foreground">{activeTask.id}</p>
              </button>
            ) : (
              <div className="rounded-xl border border-dashed border-border/60 bg-muted/20 p-6 text-sm text-muted-foreground">
                No active task. The scheduler is idle or between cycles.
              </div>
            )}

            <div className="space-y-2">
              {latestEvents.length > 0 ? latestEvents.map((event, idx) => (
                <div className="flex items-start gap-3 rounded-lg border border-border/50 bg-background/30 px-3 py-2 text-sm" key={idx}>
                  <span className="w-16 shrink-0 font-mono text-xs text-muted-foreground">{formatTime(String(event.ts ?? event.timestamp ?? ''))}</span>
                  <PhaseBadge phase={String(event.phase ?? 'system')} />
                  <div className="min-w-0 flex-1">
                    <p className="text-foreground">{String(event.detail ?? event.action ?? '')}</p>
                    {event.reasoning && <p className="mt-1 text-xs italic text-muted-foreground">{String(event.reasoning)}</p>}
                  </div>
                </div>
              )) : (
                <p className="text-sm text-muted-foreground">No recent activity events loaded yet.</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <Card className="border-border/60 bg-card/70">
          <CardHeader>
            <CardTitle>Recent Outcomes</CardTitle>
            <CardDescription>Latest task updates across the queue.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {recentTaskUpdates.length > 0 ? recentTaskUpdates.map((task) => (
              <button
                className="flex w-full items-center gap-3 rounded-xl border border-border/50 bg-background/25 px-3 py-3 text-left transition hover:bg-background/50"
                key={task.id}
                onClick={() => onOpenTaskDetail(task.id)}
                type="button"
              >
                <StatusBadge status={task.status} />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{task.title}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {task.updated_at ? `Updated ${formatDateTime(task.updated_at)}` : 'No timestamp'} · {task.source}
                  </p>
                </div>
              </button>
            )) : (
              <p className="text-sm text-muted-foreground">No tasks available yet.</p>
            )}
          </CardContent>
        </Card>

        <Card className="border-border/60 bg-card/70">
          <CardHeader>
            <CardTitle>Human Attention Queue</CardTitle>
            <CardDescription>Unresolved cases requiring operator input.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {helpRequests.length > 0 ? helpRequests.slice(0, 4).map((task) => (
              <div className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-4" key={task.id}>
                <div className="flex items-center gap-2">
                  <StatusBadge status={task.status} />
                  <span className="font-medium">{task.title}</span>
                </div>
                <p className="mt-2 line-clamp-3 whitespace-pre-wrap text-xs text-muted-foreground">
                  {task.human_help_request || 'No detail provided'}
                </p>
              </div>
            )) : (
              <div className="rounded-xl border border-dashed border-border/60 bg-muted/20 p-6 text-sm text-muted-foreground">
                No unresolved human-help requests.
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
