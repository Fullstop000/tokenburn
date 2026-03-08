import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

import type { BootstrapStatusPayload, DirectivePayload } from '../types/dashboard'
import type { DashboardPage } from '../lib/dashboardView'

const PAGE_LABELS: Record<DashboardPage, string> = {
  overview: 'Overview',
  work: 'Work',
  inbox: 'Inbox',
  discovery: 'Discovery',
  memory: 'Memory & Audit',
  control: 'Control',
}

interface DashboardShellProps {
  activePage: DashboardPage
  bootstrapStatus: BootstrapStatusPayload | null
  directive: DirectivePayload | null
  metaText: string
  pauseLoading: boolean
  inboxUnread?: number
  onNavigate: (page: DashboardPage) => void
  onTogglePause: () => void
  children: React.ReactNode
}

export function DashboardShell({
  activePage,
  bootstrapStatus,
  directive,
  metaText,
  pauseLoading,
  inboxUnread = 0,
  onNavigate,
  onTogglePause,
  children,
}: DashboardShellProps) {
  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,hsl(var(--primary)/0.18),transparent_32%),radial-gradient(circle_at_top_right,hsl(185_80%_55%/0.12),transparent_28%),linear-gradient(180deg,hsl(var(--background)),hsl(222_42%_8%))]">
      <main className="mx-auto flex min-h-screen max-w-[1580px] gap-6 px-4 py-5 md:px-6">
        <aside className="hidden w-[260px] shrink-0 lg:block">
          <div className="sticky top-5 space-y-4">
            <Card className="border-border/60 bg-card/80 backdrop-blur">
              <CardContent className="space-y-5 p-5">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-primary">Sprout Agent V2</p>
                  <h1 className="mt-2 font-serif text-2xl font-semibold tracking-tight text-foreground">Control Plane</h1>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Human-facing observability and runtime control for the autonomous loop.
                  </p>
                </div>

                <nav className="space-y-1">
                  {Object.entries(PAGE_LABELS).map(([page, label]) => {
                    const isActive = activePage === page
                    return (
                      <button
                        key={page}
                        className={`flex w-full items-center justify-between rounded-xl px-3 py-3 text-left text-sm transition ${
                          isActive
                            ? 'bg-primary text-primary-foreground shadow-[0_12px_24px_hsl(var(--primary)/0.18)]'
                            : 'bg-transparent text-foreground/80 hover:bg-muted/70 hover:text-foreground'
                        }`}
                        onClick={() => onNavigate(page as DashboardPage)}
                        type="button"
                      >
                        <span className="font-medium">{label}</span>
                        <span className={`text-xs ${isActive ? 'text-primary-foreground/80' : 'text-muted-foreground'}`}>
                          {page === 'inbox' && inboxUnread > 0
                            ? <span className="rounded-full bg-amber-500 px-1.5 py-0.5 text-[10px] font-bold text-white">{inboxUnread}</span>
                            : `0${Object.keys(PAGE_LABELS).indexOf(page) + 1}`}
                        </span>
                      </button>
                    )
                  })}
                </nav>

                <div className="rounded-xl border border-border/60 bg-muted/35 p-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Runtime</p>
                  <p className="mt-2 text-sm text-foreground">
                    {directive?.paused ? 'Paused by operator' : 'Live and polling'}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">{metaText}</p>
                </div>
              </CardContent>
            </Card>
          </div>
        </aside>

        <section className="min-w-0 flex-1 space-y-4">
          <header className="flex flex-col gap-4 rounded-2xl border border-border/60 bg-card/75 p-4 shadow-sm backdrop-blur md:flex-row md:items-end md:justify-between">
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2 lg:hidden">
                {Object.entries(PAGE_LABELS).map(([page, label]) => (
                  <Button
                    key={page}
                    size="sm"
                    variant={activePage === page ? 'default' : 'outline'}
                    onClick={() => onNavigate(page as DashboardPage)}
                  >
                    {label}
                  </Button>
                ))}
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-primary">{PAGE_LABELS[activePage]}</p>
                <h2 className="mt-1 font-serif text-3xl font-semibold tracking-tight text-foreground">{PAGE_LABELS[activePage]}</h2>
              </div>
            </div>

            <div className="flex flex-col items-start gap-2 md:items-end">
              {directive && (
                <Button
                  variant={directive.paused ? 'destructive' : 'default'}
                  onClick={onTogglePause}
                  disabled={pauseLoading}
                  className="min-w-[148px]"
                >
                  <span className={`mr-2 h-2.5 w-2.5 rounded-full ${directive.paused ? 'bg-red-300' : 'bg-green-300 animate-pulse-dot'}`} />
                  {pauseLoading ? 'Working...' : directive.paused ? 'Resume Agent' : 'Pause Agent'}
                </Button>
              )}
              <p className="font-mono text-xs text-muted-foreground">{metaText}</p>
            </div>
          </header>

          {bootstrapStatus?.requires_setup && (
            <Card className="border-amber-500/30 bg-amber-500/10">
              <CardContent className="flex flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-300">Initialization Required</p>
                  <p className="mt-1 text-sm text-amber-50/90">{bootstrapStatus.message}</p>
                </div>
                <Button variant="outline" onClick={() => onNavigate('control')}>Open Control</Button>
              </CardContent>
            </Card>
          )}

          {children}
        </section>
      </main>
    </div>
  )
}
