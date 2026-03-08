import { useCallback, useState } from 'react'

import { dashboardApiClient } from '../api/dashboardApi'
import type { ThreadDetail, ThreadSummary } from '../types/dashboard'

interface UseInboxStateArgs {
  showToast: (message: string, ok?: boolean) => void
  onError: (message: string) => void
  onNavigateToInbox: () => void
  friendlyLoadError: (scope: string, error: unknown) => string
}

export function useInboxState({
  showToast,
  onError,
  onNavigateToInbox,
  friendlyLoadError,
}: UseInboxStateArgs) {
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [threadDetail, setThreadDetail] = useState<ThreadDetail | null>(null)
  const [inboxUnread, setInboxUnread] = useState(0)
  const [replyingThreadId, setReplyingThreadId] = useState('')
  const [creatingThread, setCreatingThread] = useState(false)

  const refreshThreads = useCallback(async (): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getThreads()
      setThreads(payload.threads ?? [])
      setInboxUnread((payload.threads ?? []).filter((t) => t.status === 'waiting_reply').length)
      onError('')
    } catch (error) {
      onError(friendlyLoadError('Inbox threads', error))
    }
  }, [friendlyLoadError, onError])

  const openThreadDetail = useCallback(async (threadId: string): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getThreadDetail(threadId)
      if (payload.error) {
        showToast(payload.error, false)
        return
      }
      setThreadDetail(payload as ThreadDetail)
    } catch (error) {
      showToast(`Failed to load thread: ${String(error)}`, false)
    }
  }, [showToast])

  const revealThread = useCallback(async (threadId: string): Promise<void> => {
    onNavigateToInbox()
    await openThreadDetail(threadId)
  }, [onNavigateToInbox, openThreadDetail])

  const replyToThread = useCallback(async (threadId: string, body: string): Promise<void> => {
    if (replyingThreadId) return
    setReplyingThreadId(threadId)
    try {
      const payload = await dashboardApiClient.replyToThread(threadId, body)
      if (payload.error) {
        showToast(payload.error, false)
        return
      }
      showToast('Reply sent')
      await Promise.all([refreshThreads(), openThreadDetail(threadId)])
    } catch (error) {
      showToast(`Reply failed: ${String(error)}`, false)
    } finally {
      setReplyingThreadId('')
    }
  }, [openThreadDetail, refreshThreads, replyingThreadId, showToast])

  const createThread = useCallback(async (title: string, description: string): Promise<void> => {
    if (creatingThread) return
    setCreatingThread(true)
    try {
      const payload = await dashboardApiClient.createThread({ title, description })
      if (payload.error) {
        showToast(payload.error, false)
        return
      }
      showToast('Thread created — task queued')
      await refreshThreads()
      if (payload.thread_id) await openThreadDetail(payload.thread_id)
    } catch (error) {
      showToast(`Create thread failed: ${String(error)}`, false)
    } finally {
      setCreatingThread(false)
    }
  }, [creatingThread, openThreadDetail, refreshThreads, showToast])

  const bulkCloseThreads = useCallback(async (threadIds: string[]): Promise<void> => {
    try {
      const payload = await dashboardApiClient.bulkCloseThreads(threadIds)
      if (payload.error) {
        showToast(payload.error, false)
        return
      }
      showToast(`Closed ${payload.closed ?? threadIds.length} threads`)
      await refreshThreads()
      if (threadDetail && threadIds.includes(threadDetail.thread.id)) {
        await openThreadDetail(threadDetail.thread.id)
      }
    } catch (error) {
      showToast(`Bulk close failed: ${String(error)}`, false)
    }
  }, [openThreadDetail, refreshThreads, showToast, threadDetail])

  const closeThread = useCallback(async (threadId: string, reason: string): Promise<void> => {
    try {
      const payload = await dashboardApiClient.closeThread(threadId, reason)
      if (payload.error) {
        showToast(payload.error, false)
        return
      }
      showToast('Thread closed')
      await refreshThreads()
      await openThreadDetail(threadId)
    } catch (error) {
      showToast(`Close thread failed: ${String(error)}`, false)
    }
  }, [openThreadDetail, refreshThreads, showToast])

  return {
    bulkCloseThreads,
    closeThread,
    createThread,
    creatingThread,
    inboxUnread,
    openThreadDetail,
    refreshThreads,
    replyToThread,
    replyingThreadId,
    revealThread,
    threadDetail,
    threads,
  }
}
