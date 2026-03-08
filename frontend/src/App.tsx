import { useCallback, useState } from 'react'

import { Toaster, toast } from 'sonner'

import { DashboardRouter } from './app/DashboardRouter'
import { DashboardShell } from './app/DashboardShell'
import { useDashboardData } from './app/useDashboardData'
import { useDashboardNavigation } from './app/navigation'
import { useControlPageState } from './app/useControlPageState'
import { useInboxState } from './app/useInboxState'
import { useMemoryState } from './app/useMemoryState'
import { usePollingEffect } from './app/usePollingEffect'
import { dashboardApiClient } from './api/dashboardApi'
import './App.css'

import type {
  TaskDetail,
  TaskEvent,
} from './types/dashboard'

function friendlyLoadError(scope: string, error: unknown): string {
  const message = String(error)
  if (message.includes('Failed to fetch')) {
    return `${scope} is unavailable right now. Check whether the dashboard backend is running, then try again.`
  }
  if (message.includes('Request failed (500)')) {
    return `${scope} could not be loaded because the dashboard API returned an internal error. You can keep using the last visible data and retry after the backend is healthy.`
  }
  if (message.includes('Request failed (404)')) {
    return `${scope} is not available from this dashboard build yet.`
  }
  return `${scope} could not be loaded right now. ${message}`
}

function App() {
  const {
    activePage,
    controlPanel,
    memoryPanel,
    setActivePage,
    setControlPanel,
    setMemoryPanel,
    setWorkPanel,
    workPanel,
  } = useDashboardNavigation()
  const [taskDetail, setTaskDetail] = useState<TaskDetail | null>(null)
  const [taskEvents, setTaskEvents] = useState<TaskEvent[]>([])

  const [pauseLoading, setPauseLoading] = useState(false)
  const [activityError, setActivityError] = useState('')
  const [discoveryError, setDiscoveryError] = useState('')
  const [auditError, setAuditError] = useState('')
  const [threadsError, setThreadsError] = useState('')
  const [experiencesError, setExperiencesError] = useState('')

  const showToast = (message: string, ok = true): void => {
    if (ok) toast.success(message)
    else toast.error(message)
  }

  const {
    bootstrapStatus,
    cycles,
    directive,
    helpCount,
    helpError,
    helpRequests,
    metaText,
    refreshHelpCenter,
    refreshSummary,
    summary,
    summaryError,
    tasks,
  } = useDashboardData({ friendlyLoadError })

  const {
    bindingPoints,
    deleteModel,
    deletingModelId,
    editingModelId,
    injectDescription,
    injectPriority,
    injectTask,
    injectTitle,
    modelApiKey,
    modelError,
    modelApiPath,
    modelBaseUrl,
    modelBindings,
    modelDesc,
    modelName,
    modelRoocodeWrapper,
    modelType,
    refreshModels,
    registerModel,
    registeredModels,
    resetModelForm,
    resolveHelpRequest,
    resolvingTaskId,
    saveDirective,
    saveModelBindings,
    setInjectDescription,
    setInjectPriority,
    setInjectTitle,
    setModelApiKey,
    setModelApiPath,
    setModelBaseUrl,
    setModelBindings,
    setModelDesc,
    setModelName,
    setModelRoocodeWrapper,
    setModelType,
    setSourcesJson,
    sourcesJson,
    startEditingModel,
  } = useControlPageState({
    directive,
    friendlyLoadError,
    navigateToPage: setActivePage,
    onRefreshHelpCenter: refreshHelpCenter,
    onRefreshSummary: refreshSummary,
    setControlPanel,
    showToast,
  })

  const pollModels = useCallback(async (): Promise<void> => {
    try {
      await refreshModels()
    } catch {
      // Control state already stores a friendly inline error for model refresh failures.
    }
  }, [refreshModels])

  const openTaskDetail = useCallback(async (taskId: string): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getTaskDetail(taskId)
      if (payload.error || !payload.task) {
        showToast(payload.error ?? 'Task not found', false)
        return
      }
      setTaskDetail(payload.task)
      setTaskEvents(payload.events ?? [])
      setWorkPanel('detail')
      setActivePage('work')
    } catch (error) {
      showToast(`Failed to load task detail: ${String(error)}`, false)
    }
  }, [setActivePage, setWorkPanel])

  const {
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
  } = useInboxState({
    friendlyLoadError,
    onError: setThreadsError,
    onNavigateToInbox: () => setActivePage('inbox'),
    showToast,
  })

  const {
    activity,
    activityGroupBy,
    activityPhase,
    audit,
    auditDetail,
    collapsedTasks,
    discovery,
    experiences,
    openAuditDetail,
    refreshActivity,
    refreshAudit,
    refreshDiscovery,
    refreshExperiences,
    setActivityGroupBy,
    setActivityPhase,
    setAuditDetail,
    toggleCollapsedTask,
  } = useMemoryState({
    friendlyLoadError,
    onActivityError: setActivityError,
    onAuditError: setAuditError,
    onDiscoveryError: setDiscoveryError,
    onExperiencesError: setExperiencesError,
    showToast,
  })

  const togglePause = async (): Promise<void> => {
    if (pauseLoading || !directive) return
    setPauseLoading(true)
    try {
      const result = directive.paused ? await dashboardApiClient.resume() : await dashboardApiClient.pause()
      showToast(result.paused ? 'Agent paused' : 'Agent resumed')
      await refreshSummary()
    } catch (error) {
      showToast(`Toggle pause failed: ${String(error)}`, false)
    } finally {
      setPauseLoading(false)
    }
  }

  usePollingEffect(refreshSummary, 5000)
  usePollingEffect(refreshActivity, activePage === 'discovery' ? 3000 : 5000)
  usePollingEffect(refreshDiscovery, activePage === 'discovery' ? 3000 : 8000)
  usePollingEffect(refreshAudit, activePage === 'memory' ? 5000 : null)
  usePollingEffect(refreshHelpCenter, 5000)
  usePollingEffect(refreshThreads, activePage === 'inbox' ? 3000 : 8000)
  usePollingEffect(refreshExperiences, activePage === 'memory' ? 8000 : null)
  usePollingEffect(pollModels, activePage === 'control' ? 8000 : null)

  return (
    <>
      <Toaster position="bottom-right" richColors />
      <DashboardShell
        activePage={activePage}
        bootstrapStatus={bootstrapStatus}
        directive={directive}
        metaText={metaText}
        inboxUnread={inboxUnread}
        onNavigate={setActivePage}
        onTogglePause={() => void togglePause()}
        pauseLoading={pauseLoading}
      >
        <DashboardRouter
          activePage={activePage}
          control={{
            bindingPoints,
            controlPanel,
            deletingModelId,
            directive,
            editingModelId,
            helpCount,
            helpError,
            helpRequests,
            injectDescription,
            injectPriority,
            injectTitle,
            modelApiKey,
            modelApiPath,
            modelBaseUrl,
            modelBindings,
            modelDesc,
            modelError,
            modelName,
            modelRoocodeWrapper,
            modelType,
            onChangeControlPanel: setControlPanel,
            onDeleteModel: deleteModel,
            onInjectTask: (event) => void injectTask(event),
            onRegisterModel: (event) => void registerModel(event),
            onResetModelForm: resetModelForm,
            onResolveHelpRequest: (taskId) => void resolveHelpRequest(taskId),
            onSaveDirective: (event) => void saveDirective(event),
            onSaveModelBindings: (event) => void saveModelBindings(event),
            onStartEditingModel: startEditingModel,
            registeredModels,
            resolvingTaskId,
            setInjectDescription,
            setInjectPriority,
            setInjectTitle,
            setModelApiKey,
            setModelApiPath,
            setModelBaseUrl,
            setModelBindings: (updater) => setModelBindings((current) => updater(current)),
            setModelDesc,
            setModelName,
            setModelRoocodeWrapper,
            setModelType,
            setSourcesJson,
            sourcesJson,
            summaryError,
          }}
          discovery={{
            discovery,
            discoveryError,
            onRetryDiscovery: () => void refreshDiscovery(),
          }}
          inbox={{
            creatingThread,
            onBulkCloseThreads: bulkCloseThreads,
            onCloseThread: closeThread,
            onCreateThread: createThread,
            onRefreshThreads: () => void refreshThreads(),
            onReplyToThread: replyToThread,
            onSelectThread: (id) => void openThreadDetail(id),
            replyingThreadId,
            threadDetail,
            threads,
            threadsError,
          }}
          memory={{
            activity,
            activityError,
            activityGroupBy,
            activityPhase,
            audit,
            auditDetail,
            auditError,
            collapsedTasks,
            experiences,
            experiencesError,
            memoryPanel,
            onChangeActivityGroupBy: setActivityGroupBy,
            onChangeActivityModule: setActivityPhase,
            onChangeMemoryPanel: setMemoryPanel,
            onCloseAuditDetail: () => setAuditDetail(null),
            onOpenAuditDetail: (seq) => void openAuditDetail(seq),
            onRefreshActivity: () => void refreshActivity(),
            onRefreshAudit: () => void refreshAudit(),
            onRefreshExperiences: () => void refreshExperiences(),
            onToggleCollapsedTask: toggleCollapsedTask,
            tasks,
          }}
          overview={{
            onNavigate: setActivePage,
            onOpenTaskDetail: (taskId) => void openTaskDetail(taskId),
            onOpenThread: (threadId) => void revealThread(threadId),
            onRetrySummary: () => void refreshSummary(),
            summary,
            summaryError,
          }}
          work={{
            cycles,
            onChangeWorkPanel: setWorkPanel,
            onOpenTaskDetail: (taskId) => void openTaskDetail(taskId),
            onRetrySummary: () => void refreshSummary(),
            summaryError,
            taskDetail,
            taskEvents,
            tasks,
            workPanel,
          }}
        />
      </DashboardShell>
    </>
  )
}

export default App
