import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { PhaseBadge } from '@/components/ui/phase-badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

import { ActivityByTask } from '../components/activity/ActivityByTask'
import { formatActivityMessage, formatDateTime, formatTime, type ActivityEvent, type MemoryPanel } from '../lib/dashboardView'
import type { ExperienceEntry, LlmAuditEntry, TaskSummary } from '../types/dashboard'

interface MemoryAuditPageProps {
  activePanel: MemoryPanel
  activity: ActivityEvent[]
  activityPhase: string
  activityGroupBy: 'time' | 'task'
  collapsedTasks: Set<string>
  tasks: TaskSummary[]
  audit: LlmAuditEntry[]
  auditDetail: LlmAuditEntry | null
  experiences: ExperienceEntry[]
  onChangePanel: (panel: MemoryPanel) => void
  onRefreshActivity: () => void
  onRefreshAudit: () => void
  onRefreshExperiences: () => void
  onOpenAuditDetail: (seq: number) => void
  onCloseAuditDetail: () => void
  onChangeActivityPhase: (phase: string) => void
  onChangeActivityGroupBy: (groupBy: 'time' | 'task') => void
  onToggleCollapsedTask: (taskId: string) => void
}

export function MemoryAuditPage({
  activePanel,
  activity,
  activityPhase,
  activityGroupBy,
  collapsedTasks,
  tasks,
  audit,
  auditDetail,
  experiences,
  onChangePanel,
  onRefreshActivity,
  onRefreshAudit,
  onRefreshExperiences,
  onOpenAuditDetail,
  onCloseAuditDetail,
  onChangeActivityPhase,
  onChangeActivityGroupBy,
  onToggleCollapsedTask,
}: MemoryAuditPageProps) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant={activePanel === 'activity' ? 'default' : 'outline'} onClick={() => onChangePanel('activity')}>Activity Feed</Button>
        <Button size="sm" variant={activePanel === 'audit' ? 'default' : 'outline'} onClick={() => onChangePanel('audit')}>LLM Audit</Button>
        <Button size="sm" variant={activePanel === 'experience' ? 'default' : 'outline'} onClick={() => onChangePanel('experience')}>Experience Memory</Button>
      </div>

      {activePanel === 'activity' && (
        <Card className="border-border/60 bg-card/70">
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center gap-3">
              <div className="min-w-[150px]">
                <Select value={activityPhase || '__all__'} onValueChange={(value: string) => onChangeActivityPhase(value === '__all__' ? '' : value)}>
                  <SelectTrigger className="w-[150px]">
                    <SelectValue placeholder="All phases" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all__">All phases</SelectItem>
                    <SelectItem value="cycle">cycle</SelectItem>
                    <SelectItem value="discover">discover</SelectItem>
                    <SelectItem value="value">value</SelectItem>
                    <SelectItem value="plan">plan</SelectItem>
                    <SelectItem value="execute">execute</SelectItem>
                    <SelectItem value="verify">verify</SelectItem>
                    <SelectItem value="git">git</SelectItem>
                    <SelectItem value="decision">decision</SelectItem>
                    <SelectItem value="system">system</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex rounded-md bg-muted p-0.5">
                <Button size="sm" variant={activityGroupBy === 'time' ? 'secondary' : 'ghost'} onClick={() => onChangeActivityGroupBy('time')}>Timeline</Button>
                <Button size="sm" variant={activityGroupBy === 'task' ? 'secondary' : 'ghost'} onClick={() => onChangeActivityGroupBy('task')}>By Task</Button>
              </div>
              <Button size="sm" variant="outline" onClick={onRefreshActivity}>Refresh</Button>
            </div>
          </CardHeader>
          <CardContent>
            {activityGroupBy === 'time' ? (
              <div className="space-y-1 activity-scroll">
                {activity.length > 0 ? [...activity].reverse().map((event, idx) => {
                  const taskId = String(event.task_id ?? '')
                  return (
                    <div className="flex items-start gap-3 border-b py-2 text-sm last:border-0" key={idx}>
                      <span className="w-20 shrink-0 font-mono text-xs text-muted-foreground">{formatTime(String(event.ts ?? event.timestamp ?? ''))}</span>
                      <PhaseBadge phase={String(event.phase ?? '?')} />
                      <span className="text-foreground">
                        {taskId && <code className="mr-2 rounded bg-muted px-1 py-0.5 text-xs">{taskId.slice(0, 8)}</code>}
                        {formatActivityMessage(event)}
                      </span>
                    </div>
                  )
                }) : (
                  <p className="py-8 text-center italic text-muted-foreground">No activity events</p>
                )}
              </div>
            ) : (
              <div className="max-h-[75vh] overflow-y-auto">
                <ActivityByTask
                  activity={activity}
                  collapsedTasks={collapsedTasks}
                  onToggle={onToggleCollapsedTask}
                  tasks={tasks}
                />
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {activePanel === 'audit' && (
        <Card className="border-border/60 bg-card/70">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>LLM Audit</CardTitle>
              <CardDescription>Prompt and completion previews recorded for reviewability.</CardDescription>
            </div>
            <Button size="sm" variant="outline" onClick={onRefreshAudit}>Refresh</Button>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Seq</TableHead>
                  <TableHead>Model</TableHead>
                  <TableHead>Prompt / Completion</TableHead>
                  <TableHead className="text-right">Latency</TableHead>
                  <TableHead className="text-right">Time</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...audit].reverse().map((entry) => (
                  <TableRow className="cursor-pointer" key={entry.seq} onClick={() => onOpenAuditDetail(entry.seq)}>
                    <TableCell className="font-mono">{entry.seq}</TableCell>
                    <TableCell><code className="rounded bg-muted px-1.5 py-0.5 text-xs">{entry.model ?? '-'}</code></TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {(entry.prompt_tokens ?? 0).toLocaleString()} / {(entry.completion_tokens ?? 0).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs text-muted-foreground">
                      {entry.duration_ms ? `${(entry.duration_ms / 1000).toFixed(1)}s` : '-'}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs text-muted-foreground">{formatTime(entry.ts)}</TableCell>
                  </TableRow>
                ))}
                {audit.length === 0 && (
                  <TableRow>
                    <TableCell className="py-8 text-center italic text-muted-foreground" colSpan={5}>No audit entries</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {activePanel === 'experience' && (
        <Card className="border-border/60 bg-card/70">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Experience Memory</CardTitle>
              <CardDescription>Long-term learnings extracted from task execution outcomes.</CardDescription>
            </div>
            <Button size="sm" variant="outline" onClick={onRefreshExperiences}>Refresh</Button>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Task ID</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead className="min-w-[260px]">Summary</TableHead>
                  <TableHead className="text-right">Confidence</TableHead>
                  <TableHead className="text-right">Applied Count</TableHead>
                  <TableHead>Outcome</TableHead>
                  <TableHead className="text-right">Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {experiences.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell className="font-mono text-xs">{entry.task_id || '-'}</TableCell>
                    <TableCell><code className="rounded bg-muted px-1.5 py-0.5 text-xs">{entry.category}</code></TableCell>
                    <TableCell>
                      <div className="text-sm">{entry.summary}</div>
                      {entry.detail && <div className="mt-1 text-xs text-muted-foreground">{entry.detail}</div>}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">{typeof entry.confidence === 'number' ? entry.confidence.toFixed(2) : '-'}</TableCell>
                    <TableCell className="text-right">{Number(entry.applied_count ?? 0)}</TableCell>
                    <TableCell><code className="rounded bg-muted px-1.5 py-0.5 text-xs">{entry.source_outcome || '-'}</code></TableCell>
                    <TableCell className="text-right font-mono text-xs text-muted-foreground">{formatDateTime(entry.created_at)}</TableCell>
                  </TableRow>
                ))}
                {experiences.length === 0 && (
                  <TableRow>
                    <TableCell className="py-8 text-center italic text-muted-foreground" colSpan={7}>No experience entries yet</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Dialog onOpenChange={onCloseAuditDetail} open={!!auditDetail}>
        <DialogContent className="max-h-[80vh] max-w-3xl overflow-auto">
          <DialogHeader>
            <DialogTitle>Audit Entry #{auditDetail?.seq}</DialogTitle>
            <DialogDescription>
              Model: {auditDetail?.model} · {auditDetail?.duration_ms ? `${(auditDetail.duration_ms / 1000).toFixed(1)}s` : '-'}
            </DialogDescription>
          </DialogHeader>
          {auditDetail && (
            <pre className="overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(auditDetail, null, 2)}</pre>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
