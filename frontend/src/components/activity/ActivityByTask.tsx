import { PhaseBadge } from '@/components/ui/phase-badge'

import { eventBadgeLabel, eventBadgeVariant, eventDisplayName, formatTime, formatActivityMessage, groupActivityByTask, type ActivityEvent } from '../../lib/dashboardView'
import type { TaskSummary } from '../../types/dashboard'

interface ActivityByTaskProps {
  activity: ActivityEvent[]
  collapsedTasks: Set<string>
  onToggle: (id: string) => void
  tasks: TaskSummary[]
}

export function ActivityByTask({ activity, collapsedTasks, onToggle, tasks }: ActivityByTaskProps) {
  const { global, groups } = groupActivityByTask(activity, tasks)

  return (
    <div className="space-y-2">
      {global.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-border/60 bg-card/60">
          <div className="flex items-center gap-2 bg-muted/50 px-4 py-3">
            <span className="text-muted-foreground">●</span>
            <span className="font-medium">Global Events</span>
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{global.length}</span>
          </div>
          <div className="divide-y divide-border/60">
            {global.map((event, idx) => (
                <div className="flex items-center gap-3 px-4 py-2 text-sm" key={`global-${idx}`}>
                  <span className="w-20 shrink-0 font-mono text-xs text-muted-foreground">{formatTime(String(event.ts ?? event.timestamp ?? ''))}</span>
                  <PhaseBadge phase={eventBadgeVariant(event)} label={eventBadgeLabel(event)} />
                  <span className="text-foreground">{formatActivityMessage(event)}</span>
                </div>
              ))}
          </div>
        </div>
      )}

      {groups.map((group) => {
        const isCollapsed = collapsedTasks.has(group.taskId)
        const lastEvent = group.events[group.events.length - 1]
        return (
          <div className="overflow-hidden rounded-xl border border-border/60 bg-card/60" key={group.taskId}>
            <button
              className="flex w-full items-center gap-2 bg-muted/45 px-4 py-3 text-left transition hover:bg-muted/70"
              onClick={() => onToggle(group.taskId)}
              type="button"
            >
              <span className={`text-xs text-muted-foreground transition-transform ${isCollapsed ? '-rotate-90' : ''}`}>▾</span>
              <PhaseBadge
                phase={eventBadgeVariant(lastEvent)}
                label={eventBadgeLabel(lastEvent)}
              />
              <span className="truncate font-medium">{group.title}</span>
              <span className="font-mono text-xs text-muted-foreground">{group.taskId.slice(0, 8)}</span>
              <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{group.events.length}</span>
            </button>
            {!isCollapsed && (
              <div className="divide-y divide-border/60">
                {group.events.map((event, idx) => {
                  const success = event.success
                  const reasoning = String(event.reasoning ?? '')
                  return (
                    <div className={`flex items-start gap-3 px-4 py-3 text-sm ${success === false ? 'bg-destructive/5' : ''}`} key={idx}>
                      <span className="w-16 shrink-0 font-mono text-xs text-muted-foreground">
                        {formatTime(String(event.ts ?? event.timestamp ?? ''))}
                      </span>
                      <PhaseBadge phase={eventBadgeVariant(event)} label={eventBadgeLabel(event)} />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono font-medium">{eventDisplayName(event)}</span>
                          <span className="text-muted-foreground">{formatActivityMessage(event)}</span>
                          {success === true && <span className="font-bold text-green-500">✓</span>}
                          {success === false && <span className="font-bold text-destructive">✗</span>}
                        </div>
                        {reasoning && <p className="mt-1 text-xs italic text-muted-foreground">{reasoning}</p>}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}

      {global.length === 0 && groups.length === 0 && (
        <p className="py-8 text-center italic text-muted-foreground">No activity events</p>
      )}
    </div>
  )
}
