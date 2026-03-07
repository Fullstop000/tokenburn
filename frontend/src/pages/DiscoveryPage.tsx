import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { PhaseBadge } from '@/components/ui/phase-badge'

import { buildDiscoverySnapshot, formatActivityMessage, formatTime, type ActivityEvent } from '../lib/dashboardView'

interface DiscoveryPageProps {
  activity: ActivityEvent[]
}

function EventList({
  title,
  subtitle,
  events,
}: {
  title: string
  subtitle: string
  events: ActivityEvent[]
}) {
  return (
    <Card className="border-border/60 bg-card/70">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{subtitle}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {events.length > 0 ? events.map((event, idx) => (
          <div className="rounded-xl border border-border/50 bg-background/25 p-3" key={idx}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-muted-foreground">{formatTime(String(event.ts ?? event.timestamp ?? ''))}</span>
              <PhaseBadge phase={String(event.phase ?? 'discover')} />
              <span className="font-mono text-xs">{String(event.action ?? '')}</span>
            </div>
            <p className="mt-2 text-sm text-foreground">{formatActivityMessage(event)}</p>
            {event.reasoning && <p className="mt-2 text-xs italic text-muted-foreground">{String(event.reasoning)}</p>}
          </div>
        )) : (
          <div className="rounded-xl border border-dashed border-border/60 bg-muted/20 p-5 text-sm text-muted-foreground">
            Not wired yet for this run. The backend has not emitted these events recently.
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function DiscoveryPage({ activity }: DiscoveryPageProps) {
  const snapshot = buildDiscoverySnapshot(activity)

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[1.05fr_1.35fr]">
        <Card className="border-border/60 bg-card/70">
          <CardHeader>
            <CardTitle>Discovery Funnel</CardTitle>
            <CardDescription>The latest observable discovery pass, reconstructed from observer events.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-xl border border-border/60 bg-muted/30 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Strategy</p>
              {snapshot.strategy ? (
                <>
                  <p className="mt-2 text-sm text-foreground">{formatActivityMessage(snapshot.strategy)}</p>
                  {snapshot.strategy.reasoning && <p className="mt-1 text-xs italic text-muted-foreground">{String(snapshot.strategy.reasoning)}</p>}
                </>
              ) : (
                <p className="mt-2 text-sm text-muted-foreground">No explicit strategy event yet. Backend support can be added later.</p>
              )}
            </div>
            <div className="rounded-xl border border-border/60 bg-muted/30 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Latest Funnel</p>
              <p className="mt-2 text-sm text-foreground">
                {snapshot.latestFunnel ? formatActivityMessage(snapshot.latestFunnel) : 'No funnel event observed yet.'}
              </p>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-xl border border-border/60 bg-background/20 p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Raw Candidates</p>
                <p className="mt-2 text-3xl font-semibold">{snapshot.candidates.length}</p>
              </div>
              <div className="rounded-xl border border-border/60 bg-background/20 p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Queued Outcomes</p>
                <p className="mt-2 text-3xl font-semibold">{snapshot.queued.length}</p>
              </div>
              <div className="rounded-xl border border-border/60 bg-background/20 p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Value Scores</p>
                <p className="mt-2 text-3xl font-semibold">{snapshot.scored.length}</p>
              </div>
              <div className="rounded-xl border border-border/60 bg-background/20 p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Filtered Out</p>
                <p className="mt-2 text-3xl font-semibold">{snapshot.filteredOut.length}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <EventList
          events={snapshot.candidates}
          subtitle="Raw discovery candidates before value filtering."
          title="Candidate Review"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <EventList events={snapshot.scored} subtitle="Heuristic or LLM scoring decisions for candidates." title="Value Scores" />
        <EventList events={snapshot.filteredOut} subtitle="Candidates excluded from the queue and the recorded reason." title="Filtered Out" />
        <EventList events={snapshot.queued} subtitle="Tasks that made it through the funnel and entered the task queue." title="Queued Outcomes" />
      </div>
    </div>
  )
}
