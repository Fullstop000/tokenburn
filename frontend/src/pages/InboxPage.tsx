import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { StatusBadge } from '@/components/ui/status-badge'
import { PriorityBadge } from '@/components/ui/priority-badge'
import { dashboardApiClient } from '../api/dashboardApi'
import type { TaskDetail, TaskEvent, ThreadDetail, ThreadSummary } from '../types/dashboard'
import { formatDateTime, formatTime } from '../lib/dashboardView'

const STATUS_LABELS: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  open: { label: 'Open', variant: 'secondary' },
  waiting_reply: { label: 'Waiting for you', variant: 'destructive' },
  replied: { label: 'Replied', variant: 'default' },
  closed: { label: 'Closed', variant: 'outline' },
}

interface InboxPageProps {
  threads: ThreadSummary[]
  threadDetail: ThreadDetail | null
  onSelectThread: (threadId: string) => void
  onReply: (threadId: string, body: string) => Promise<void>
  onCreateThread: (title: string, description: string) => Promise<void>
  onCloseThread: (threadId: string, reason: string) => Promise<void>
  onBulkClose: (threadIds: string[]) => Promise<void>
  onRefresh: () => void
  replying: boolean
  creating: boolean
}

export function InboxPage({
  threads,
  threadDetail,
  onSelectThread,
  onReply,
  onCreateThread,
  onCloseThread,
  onBulkClose,
  onRefresh,
  replying,
  creating,
}: InboxPageProps) {
  const [replyText, setReplyText] = useState('')
  const [newTitle, setNewTitle] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [showNewForm, setShowNewForm] = useState(false)
  const [showCloseForm, setShowCloseForm] = useState(false)
  const [closeReason, setCloseReason] = useState('')
  const [closing, setClosing] = useState(false)
  const [taskModal, setTaskModal] = useState<{ detail: TaskDetail; events: TaskEvent[] } | null>(null)
  const [loadingTaskId, setLoadingTaskId] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const activeStatuses = ['waiting_reply', 'open', 'replied']
  const active = threads.filter((t) => activeStatuses.includes(t.status))
  const closed = threads.filter((t) => t.status === 'closed')

  const handleReply = async () => {
    if (!threadDetail || !replyText.trim() || replying) return
    await onReply(threadDetail.thread.id, replyText.trim())
    setReplyText('')
  }

  const handleCreate = async () => {
    if (!newTitle.trim() || creating) return
    await onCreateThread(newTitle.trim(), newDescription.trim())
    setNewTitle('')
    setNewDescription('')
    setShowNewForm(false)
  }

  const handleClose = async () => {
    if (!threadDetail || closing) return
    setClosing(true)
    await onCloseThread(threadDetail.thread.id, closeReason.trim())
    setClosing(false)
    setCloseReason('')
    setShowCloseForm(false)
  }

  const handleBulkClose = async () => {
    if (selected.size === 0) return
    await onBulkClose([...selected])
    setSelected(new Set())
  }

  const openTaskModal = async (taskId: string) => {
    if (loadingTaskId) return
    setLoadingTaskId(taskId)
    try {
      const payload = await dashboardApiClient.getTaskDetail(taskId)
      if (payload.task) {
        setTaskModal({ detail: payload.task as TaskDetail, events: (payload.events ?? []) as TaskEvent[] })
      }
    } finally {
      setLoadingTaskId('')
    }
  }

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const selectableIds = active.map((t) => t.id)
  const allSelected = selectableIds.length > 0 && selectableIds.every((id) => selected.has(id))
  const toggleSelectAll = () => {
    setSelected(allSelected ? new Set() : new Set(selectableIds))
  }

  return (
    <div className="flex gap-4 min-h-0 h-full">
      {/* Thread list */}
      <div className="w-80 shrink-0 flex flex-col gap-2 min-h-0">
        {/* Toolbar */}
        <div className="flex items-center justify-between gap-2 shrink-0">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Inbox
          </p>
          <div className="flex gap-1.5">
            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={onRefresh}>
              Refresh
            </Button>
            <Button size="sm" className="h-7 px-2 text-xs" onClick={() => setShowNewForm((v) => !v)}>
              + New
            </Button>
          </div>
        </div>

        {/* New thread form */}
        {showNewForm && (
          <Card className="border-border/60 bg-card/80 shrink-0">
            <CardContent className="space-y-2 p-3">
              <Input
                placeholder="Title"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                className="h-8 text-sm"
              />
              <Textarea
                placeholder="Description (optional)"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                rows={2}
                className="text-sm"
              />
              <div className="flex gap-1.5">
                <Button size="sm" className="h-7 px-3 text-xs" onClick={() => void handleCreate()} disabled={creating || !newTitle.trim()}>
                  {creating ? 'Sending…' : 'Send'}
                </Button>
                <Button size="sm" variant="outline" className="h-7 px-3 text-xs" onClick={() => setShowNewForm(false)}>
                  Cancel
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Batch action bar */}
        {selected.size > 0 && (
          <div className="flex items-center justify-between rounded-lg bg-muted/60 border border-border/40 px-3 py-1.5 shrink-0">
            <span className="text-xs text-muted-foreground">{selected.size} selected</span>
            <Button
              size="sm"
              variant="outline"
              className="h-6 px-2 text-xs"
              onClick={() => void handleBulkClose()}
            >
              Close {selected.size}
            </Button>
          </div>
        )}

        {/* Active threads */}
        <div className="flex-1 min-h-0 overflow-y-auto space-y-px">
          {threads.length === 0 && (
            <p className="text-sm text-muted-foreground py-6 text-center">No threads yet.</p>
          )}

          {active.length > 0 && (
            <div className="space-y-px">
              <div className="flex items-center gap-2 px-2 pb-1">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleSelectAll}
                  className="h-3.5 w-3.5 rounded border-border accent-primary cursor-pointer"
                />
                <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                  Active · {active.length}
                </span>
              </div>
              {active.map((t) => (
                <ThreadRow
                  key={t.id}
                  thread={t}
                  isSelected={threadDetail?.thread.id === t.id}
                  isChecked={selected.has(t.id)}
                  onCheck={() => toggleSelect(t.id)}
                  onClick={() => onSelectThread(t.id)}
                />
              ))}
            </div>
          )}

          {closed.length > 0 && (
            <div className="space-y-px mt-3">
              <div className="px-2 pb-1">
                <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                  Closed · {closed.length}
                </span>
              </div>
              {closed.map((t) => (
                <ThreadRow
                  key={t.id}
                  thread={t}
                  isSelected={threadDetail?.thread.id === t.id}
                  isChecked={false}
                  onCheck={() => {}}
                  onClick={() => onSelectThread(t.id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Thread detail */}
      <div className="flex-1 min-w-0 flex flex-col min-h-0">
        {!threadDetail ? (
          <Card className="border-border/60 bg-card/80 flex-1 flex items-center justify-center">
            <p className="text-sm text-muted-foreground">Select a thread to view the conversation.</p>
          </Card>
        ) : (
          <Card className="border-border/60 bg-card/80 flex flex-col flex-1 min-h-0">
            <CardHeader className="flex flex-row items-start justify-between gap-4 pb-3 shrink-0">
              <div className="min-w-0">
                <p className="font-semibold text-foreground truncate">{threadDetail.thread.title}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Created by {threadDetail.thread.created_by} · {formatDateTime(threadDetail.thread.created_at)}
                </p>
                {threadDetail.task_ids.length > 0 && (
                  <p className="text-xs text-muted-foreground mt-1 flex flex-wrap items-center gap-1">
                    <span>Tasks:</span>
                    {threadDetail.task_ids.map((id) => (
                      <button
                        key={id}
                        type="button"
                        onClick={() => void openTaskModal(id)}
                        disabled={Boolean(loadingTaskId)}
                        className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground hover:bg-primary hover:text-primary-foreground transition disabled:opacity-50"
                      >
                        {loadingTaskId === id ? '…' : id}
                      </button>
                    ))}
                  </p>
                )}
              </div>
              <Badge variant={STATUS_LABELS[threadDetail.thread.status]?.variant ?? 'outline'}>
                {STATUS_LABELS[threadDetail.thread.status]?.label ?? threadDetail.thread.status}
              </Badge>
            </CardHeader>

            <CardContent className="flex flex-col flex-1 min-h-0 gap-3 pt-0">
              {/* Messages */}
              <div className="flex-1 min-h-0 overflow-y-auto space-y-3 pr-1">
                {threadDetail.messages.length === 0 && (
                  <p className="text-sm text-muted-foreground">No messages yet.</p>
                )}
                {threadDetail.messages.map((m) => (
                  <div
                    key={m.id}
                    className={`flex ${m.role === 'human' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap ${
                        m.role === 'human'
                          ? 'bg-primary text-primary-foreground rounded-br-sm'
                          : 'bg-muted text-foreground rounded-bl-sm'
                      }`}
                    >
                      <p>{m.body}</p>
                      <p className={`text-[10px] mt-1 ${m.role === 'human' ? 'text-primary-foreground/60' : 'text-muted-foreground'}`}>
                        {m.role === 'human' ? 'You' : 'Sprout'} · {formatDateTime(m.created_at)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>

              {/* Reply + action area */}
              {threadDetail.thread.status !== 'closed' && (
                <div className="shrink-0 space-y-2 pt-2 border-t border-border/40">
                  {/* Inline close form */}
                  {showCloseForm && (
                    <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-3 space-y-2">
                      <p className="text-xs font-semibold text-destructive uppercase tracking-wide">Close thread</p>
                      <Textarea
                        placeholder="Reason (optional)"
                        value={closeReason}
                        onChange={(e) => setCloseReason(e.target.value)}
                        rows={2}
                        className="text-sm"
                      />
                      <div className="flex gap-1.5">
                        <Button
                          size="sm"
                          variant="destructive"
                          className="h-7 px-3 text-xs"
                          onClick={() => void handleClose()}
                          disabled={closing}
                        >
                          {closing ? 'Closing…' : 'Confirm close'}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 px-3 text-xs"
                          onClick={() => { setShowCloseForm(false); setCloseReason('') }}
                        >
                          Cancel
                        </Button>
                      </div>
                    </div>
                  )}

                  {/* Textarea + [Close | Send] button group */}
                  <div className="flex gap-2">
                    <Textarea
                      placeholder="Type your reply…"
                      value={replyText}
                      onChange={(e) => setReplyText(e.target.value)}
                      rows={2}
                      className="flex-1 text-sm"
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void handleReply()
                      }}
                    />
                    {/* Button group */}
                    <div className="flex flex-col gap-0 self-end rounded-md overflow-hidden border border-border/60 shrink-0">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="rounded-none border-b border-border/60 h-8 px-3 text-xs text-destructive hover:bg-destructive/10 hover:text-destructive"
                        onClick={() => setShowCloseForm((v) => !v)}
                      >
                        Close
                      </Button>
                      <Button
                        size="sm"
                        className="rounded-none h-8 px-3 text-xs"
                        onClick={() => void handleReply()}
                        disabled={replying || !replyText.trim()}
                      >
                        {replying ? '…' : 'Send'}
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* Task detail modal */}
      {taskModal && (
        <Dialog open onOpenChange={(open) => { if (!open) setTaskModal(null) }}>
          <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="pr-6">{taskModal.detail.title}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 text-sm">
              <div className="flex flex-wrap gap-3 text-muted-foreground">
                <span>Status: <StatusBadge status={taskModal.detail.status} /></span>
                <span>Priority: <PriorityBadge priority={taskModal.detail.priority} /></span>
                <span>Source: <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{taskModal.detail.source}</code></span>
                <span>Created: <span className="font-mono text-xs">{formatDateTime(taskModal.detail.created_at)}</span></span>
                <span>Updated: <span className="font-mono text-xs">{formatDateTime(taskModal.detail.updated_at)}</span></span>
              </div>

              {taskModal.detail.description && (
                <section>
                  <h3 className="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">Description</h3>
                  <p className="leading-relaxed">{taskModal.detail.description}</p>
                </section>
              )}

              {taskModal.detail.human_help_request && (
                <section>
                  <h3 className="mb-1.5 text-xs font-semibold uppercase text-amber-400">Human Help Request</h3>
                  <pre className="overflow-auto rounded-md border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-50/90">{taskModal.detail.human_help_request}</pre>
                </section>
              )}

              {taskModal.detail.error_message && (
                <section>
                  <h3 className="mb-1.5 text-xs font-semibold uppercase text-destructive">Error</h3>
                  <pre className="overflow-auto rounded-md border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">{taskModal.detail.error_message}</pre>
                </section>
              )}

              {taskModal.detail.plan && (
                <section>
                  <h3 className="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">Execution Plan</h3>
                  <pre className="overflow-auto rounded-md bg-muted p-3 text-xs">{taskModal.detail.plan}</pre>
                </section>
              )}

              {taskModal.detail.execution_log && (
                <section>
                  <h3 className="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">Execution Log</h3>
                  <pre className="overflow-auto rounded-md bg-muted p-3 text-xs">{taskModal.detail.execution_log}</pre>
                </section>
              )}

              {taskModal.detail.verification_result && (
                <section>
                  <h3 className="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">Verification</h3>
                  <pre className="overflow-auto rounded-md bg-muted p-3 text-xs">{taskModal.detail.verification_result}</pre>
                </section>
              )}

              {taskModal.detail.whats_learned && (
                <section>
                  <h3 className="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">What Was Learned</h3>
                  <pre className="overflow-auto rounded-md bg-muted p-3 text-xs">{taskModal.detail.whats_learned}</pre>
                </section>
              )}

              {taskModal.events.length > 0 && (
                <section>
                  <h3 className="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">
                    Events <span className="rounded-full bg-muted px-2 py-0.5">{taskModal.events.length}</span>
                  </h3>
                  <div className="space-y-1.5">
                    {taskModal.events.map((ev, idx) => (
                      <div key={idx} className="flex items-start gap-3 border-l-2 border-muted pl-3">
                        <span className="font-mono text-xs font-semibold text-primary">{ev.event_type}</span>
                        <span className="font-mono text-xs text-muted-foreground">{formatTime(ev.created_at)}</span>
                        {ev.detail && <span className="text-xs text-muted-foreground">{ev.detail}</span>}
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </div>
            <DialogFooter showCloseButton />
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}

function ThreadRow({
  thread,
  isSelected,
  isChecked,
  onCheck,
  onClick,
}: {
  thread: ThreadSummary
  isSelected: boolean
  isChecked: boolean
  onCheck: () => void
  onClick: () => void
}) {
  const statusInfo = STATUS_LABELS[thread.status] ?? { label: thread.status, variant: 'outline' as const }
  const isClosed = thread.status === 'closed'
  return (
    <div
      className={`group flex items-center gap-1.5 rounded-xl px-1.5 py-0.5 transition ${
        isSelected ? 'bg-primary/10' : 'hover:bg-muted/50'
      }`}
    >
      {!isClosed ? (
        <input
          type="checkbox"
          checked={isChecked}
          onChange={(e) => { e.stopPropagation(); onCheck() }}
          onClick={(e) => e.stopPropagation()}
          className="h-3.5 w-3.5 shrink-0 rounded border-border accent-primary cursor-pointer"
        />
      ) : (
        <div className="w-3.5 shrink-0" />
      )}
      <button
        type="button"
        className="flex-1 min-w-0 rounded-lg px-2 py-2 text-left"
        onClick={onClick}
      >
        <div className="flex items-start justify-between gap-2">
          <p className={`text-sm font-medium truncate flex-1 ${isSelected ? 'text-primary' : 'text-foreground'}`}>
            {thread.title}
          </p>
          <Badge variant={statusInfo.variant} className="shrink-0 text-[10px]">
            {statusInfo.label}
          </Badge>
        </div>
        <p className="text-xs mt-0.5 text-muted-foreground">
          {thread.created_by} · {formatDateTime(thread.updated_at)}
        </p>
      </button>
    </div>
  )
}
