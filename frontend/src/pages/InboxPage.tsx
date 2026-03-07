import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import type { ThreadDetail, ThreadSummary } from '../types/dashboard'
import { formatDateTime } from '../lib/dashboardView'

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
  onRefresh,
  replying,
  creating,
}: InboxPageProps) {
  const [replyText, setReplyText] = useState('')
  const [newTitle, setNewTitle] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [showNewForm, setShowNewForm] = useState(false)

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

  return (
    <div className="flex gap-4 min-h-0">
      {/* Thread list */}
      <div className="w-80 shrink-0 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Threads
          </p>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={onRefresh}>Refresh</Button>
            <Button size="sm" onClick={() => setShowNewForm((v) => !v)}>+ New</Button>
          </div>
        </div>

        {showNewForm && (
          <Card className="border-border/60 bg-card/80">
            <CardContent className="space-y-2 p-3">
              <Input
                placeholder="Title"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
              />
              <Textarea
                placeholder="Description (optional)"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                rows={3}
              />
              <div className="flex gap-2">
                <Button size="sm" onClick={() => void handleCreate()} disabled={creating || !newTitle.trim()}>
                  {creating ? 'Sending…' : 'Send'}
                </Button>
                <Button size="sm" variant="outline" onClick={() => setShowNewForm(false)}>Cancel</Button>
              </div>
            </CardContent>
          </Card>
        )}

        {active.length === 0 && closed.length === 0 && (
          <p className="text-sm text-muted-foreground">No threads yet.</p>
        )}

        {active.length > 0 && (
          <div className="space-y-1">
            {active.map((t) => (
              <ThreadRow
                key={t.id}
                thread={t}
                isSelected={threadDetail?.thread.id === t.id}
                onClick={() => onSelectThread(t.id)}
              />
            ))}
          </div>
        )}

        {closed.length > 0 && (
          <>
            <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mt-4">Closed</p>
            <div className="space-y-1">
              {closed.map((t) => (
                <ThreadRow
                  key={t.id}
                  thread={t}
                  isSelected={threadDetail?.thread.id === t.id}
                  onClick={() => onSelectThread(t.id)}
                />
              ))}
            </div>
          </>
        )}
      </div>

      {/* Thread detail */}
      <div className="flex-1 min-w-0">
        {!threadDetail ? (
          <Card className="border-border/60 bg-card/80 h-full flex items-center justify-center">
            <p className="text-sm text-muted-foreground">Select a thread to view the conversation.</p>
          </Card>
        ) : (
          <Card className="border-border/60 bg-card/80">
            <CardHeader className="flex flex-row items-start justify-between gap-4 pb-3">
              <div className="min-w-0">
                <p className="font-semibold text-foreground truncate">{threadDetail.thread.title}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Created by {threadDetail.thread.created_by} · {formatDateTime(threadDetail.thread.created_at)}
                </p>
                {threadDetail.task_ids.length > 0 && (
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Tasks: {threadDetail.task_ids.map((id) => <code key={id} className="mx-0.5">{id}</code>)}
                  </p>
                )}
              </div>
              <Badge variant={STATUS_LABELS[threadDetail.thread.status]?.variant ?? 'outline'}>
                {STATUS_LABELS[threadDetail.thread.status]?.label ?? threadDetail.thread.status}
              </Badge>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Messages */}
              <div className="space-y-3 max-h-[480px] overflow-y-auto pr-1">
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

              {/* Reply box */}
              {threadDetail.thread.status !== 'closed' && (
                <div className="flex gap-2 pt-2 border-t border-border/40">
                  <Textarea
                    placeholder="Type your reply…"
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    rows={2}
                    className="flex-1"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void handleReply()
                    }}
                  />
                  <Button
                    onClick={() => void handleReply()}
                    disabled={replying || !replyText.trim()}
                    className="self-end"
                  >
                    {replying ? 'Sending…' : 'Send'}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}

function ThreadRow({
  thread,
  isSelected,
  onClick,
}: {
  thread: ThreadSummary
  isSelected: boolean
  onClick: () => void
}) {
  const statusInfo = STATUS_LABELS[thread.status] ?? { label: thread.status, variant: 'outline' as const }
  return (
    <button
      type="button"
      className={`w-full rounded-xl px-3 py-2.5 text-left transition ${
        isSelected
          ? 'bg-primary text-primary-foreground'
          : 'bg-transparent hover:bg-muted/70 text-foreground'
      }`}
      onClick={onClick}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium truncate flex-1">{thread.title}</p>
        <Badge
          variant={isSelected ? 'outline' : statusInfo.variant}
          className={`shrink-0 text-[10px] ${isSelected ? 'border-primary-foreground/40 text-primary-foreground' : ''}`}
        >
          {statusInfo.label}
        </Badge>
      </div>
      <p className={`text-xs mt-0.5 ${isSelected ? 'text-primary-foreground/70' : 'text-muted-foreground'}`}>
        {thread.created_by} · {formatDateTime(thread.updated_at)}
      </p>
    </button>
  )
}
