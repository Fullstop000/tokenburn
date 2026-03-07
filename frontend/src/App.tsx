import type React from 'react'
import { useCallback, useEffect, useState } from 'react'

import { Toaster, toast } from 'sonner'

import { DashboardShell } from './app/DashboardShell'
import { dashboardApiClient } from './api/dashboardApi'
import { DiscoveryPage } from './pages/DiscoveryPage'
import { InboxPage } from './pages/InboxPage'
import { MemoryAuditPage } from './pages/MemoryAuditPage'
import { OverviewPage } from './pages/OverviewPage'
import { WorkPage } from './pages/WorkPage'
import { ControlPage } from './pages/ControlPage'
import './App.css'

import {
  formatTime,
  type ActivityEvent,
  type ControlPanel,
  type DashboardPage,
  type MemoryPanel,
  type WorkPanel,
} from './lib/dashboardView'
import type {
  BootstrapStatusPayload,
  CycleSummary,
  DashboardStats,
  DiscoveryPayload,
  DirectivePayload,
  ExperienceEntry,
  LlmAuditEntry,
  ModelBindingPointEntry,
  RegisteredModelEntry,
  TaskDetail,
  TaskEvent,
  TaskSummary,
  ThreadDetail,
  ThreadSummary,
} from './types/dashboard'

function App() {
  const [activePage, setActivePage] = useState<DashboardPage>('overview')
  const [workPanel, setWorkPanel] = useState<WorkPanel>('tasks')
  const [memoryPanel, setMemoryPanel] = useState<MemoryPanel>('activity')
  const [controlPanel, setControlPanel] = useState<ControlPanel>('models')
  const [metaText, setMetaText] = useState('Loading...')

  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [cycles, setCycles] = useState<CycleSummary[]>([])
  const [stats, setStats] = useState<DashboardStats>({})
  const [directive, setDirective] = useState<DirectivePayload | null>(null)
  const [bootstrapStatus, setBootstrapStatus] = useState<BootstrapStatusPayload | null>(null)

  const [taskDetail, setTaskDetail] = useState<TaskDetail | null>(null)
  const [taskEvents, setTaskEvents] = useState<TaskEvent[]>([])

  const [activity, setActivity] = useState<ActivityEvent[]>([])
  const [discovery, setDiscovery] = useState<DiscoveryPayload | null>(null)
  const [activityPhase, setActivityPhase] = useState('')
  const [activityGroupBy, setActivityGroupBy] = useState<'time' | 'task'>('task')
  const [collapsedTasks, setCollapsedTasks] = useState<Set<string>>(new Set())

  const [audit, setAudit] = useState<LlmAuditEntry[]>([])
  const [auditDetail, setAuditDetail] = useState<LlmAuditEntry | null>(null)
  const [helpRequests, setHelpRequests] = useState<TaskSummary[]>([])
  const [helpCount, setHelpCount] = useState(0)
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [threadDetail, setThreadDetail] = useState<ThreadDetail | null>(null)
  const [inboxUnread, setInboxUnread] = useState(0)
  const [replyingThreadId, setReplyingThreadId] = useState('')
  const [creatingThread, setCreatingThread] = useState(false)
  const [experiences, setExperiences] = useState<ExperienceEntry[]>([])
  const [registeredModels, setRegisteredModels] = useState<RegisteredModelEntry[]>([])
  const [bindingPoints, setBindingPoints] = useState<ModelBindingPointEntry[]>([])
  const [modelBindings, setModelBindings] = useState<Record<string, string>>({})

  const [injectTitle, setInjectTitle] = useState('')
  const [injectDescription, setInjectDescription] = useState('')
  const [injectPriority, setInjectPriority] = useState(2)
  const [sourcesJson, setSourcesJson] = useState('{}')
  const [modelType, setModelType] = useState<'llm' | 'embedding'>('llm')
  const [modelBaseUrl, setModelBaseUrl] = useState('')
  const [modelApiPath, setModelApiPath] = useState('')
  const [modelName, setModelName] = useState('')
  const [modelApiKey, setModelApiKey] = useState('')
  const [modelDesc, setModelDesc] = useState('')
  const [editingModelId, setEditingModelId] = useState('')
  const [deletingModelId, setDeletingModelId] = useState('')

  const [pauseLoading, setPauseLoading] = useState(false)
  const [resolvingTaskId, setResolvingTaskId] = useState('')

  const showToast = (message: string, ok = true): void => {
    if (ok) toast.success(message)
    else toast.error(message)
  }

  const refreshSummary = useCallback(async (): Promise<void> => {
    try {
      const [taskPayload, cyclePayload, statsPayload, directivePayload, bootstrapPayload] = await Promise.all([
        dashboardApiClient.getTasks(),
        dashboardApiClient.getCycles(),
        dashboardApiClient.getStats(),
        dashboardApiClient.getDirective(),
        dashboardApiClient.getBootstrapStatus(),
      ])
      setTasks(taskPayload.tasks ?? [])
      setCycles(cyclePayload.cycles ?? [])
      setStats(statsPayload)
      setHelpCount(Number(statsPayload.status_counts?.needs_human ?? 0))
      setDirective(directivePayload)
      setBootstrapStatus(bootstrapPayload)
      setSourcesJson(JSON.stringify(directivePayload.task_sources ?? {}, null, 2))
      setMetaText(`updated ${formatTime(taskPayload.updated_at)} · auto-refresh 5s`)
    } catch (error) {
      const message = `Refresh failed: ${String(error)}`
      setMetaText(message)
      showToast(message, false)
    }
  }, [])

  const refreshActivity = useCallback(async (): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getActivity(300, activityPhase)
      setActivity((payload.events ?? []) as ActivityEvent[])
    } catch (error) {
      showToast(`Failed to refresh activity: ${String(error)}`, false)
    }
  }, [activityPhase])

  const refreshDiscovery = useCallback(async (): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getDiscovery(24)
      setDiscovery(payload)
    } catch (error) {
      showToast(`Failed to refresh discovery: ${String(error)}`, false)
    }
  }, [])

  const refreshAudit = useCallback(async (): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getLlmAudit(100)
      setAudit(payload.entries)
    } catch (error) {
      showToast(`Failed to refresh audit: ${String(error)}`, false)
    }
  }, [])

  const refreshHelpCenter = useCallback(async (): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getHelpCenter()
      setHelpRequests(payload.requests ?? [])
    } catch (error) {
      showToast(`Failed to refresh help center: ${String(error)}`, false)
    }
  }, [])

  const refreshThreads = useCallback(async (): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getThreads()
      setThreads(payload.threads ?? [])
      setInboxUnread((payload.threads ?? []).filter((t) => t.status === 'waiting_reply').length)
    } catch (error) {
      showToast(`Failed to refresh inbox: ${String(error)}`, false)
    }
  }, [])

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
  }, [])

  const replyToThread = async (threadId: string, body: string): Promise<void> => {
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
  }

  const createThread = async (title: string, description: string): Promise<void> => {
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
  }

  const refreshExperiences = useCallback(async (): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getExperiences(200)
      setExperiences(payload.experiences ?? [])
    } catch (error) {
      showToast(`Failed to refresh experiences: ${String(error)}`, false)
    }
  }, [])

  const refreshModels = useCallback(async (): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getModels()
      setRegisteredModels(payload.models ?? [])
      setBindingPoints(payload.binding_points ?? [])
      setModelBindings(
        Object.fromEntries(
          Object.entries(payload.bindings ?? {}).map(([bindingPoint, binding]) => [bindingPoint, binding.model_id ?? '']),
        ),
      )
    } catch (error) {
      showToast(`Failed to refresh model registry: ${String(error)}`, false)
    }
  }, [])

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
  }, [])

  const openAuditDetail = useCallback(async (seq: number): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getLlmAuditDetail(seq)
      if (payload.error || !payload.entry) {
        showToast(payload.error ?? 'Audit entry not found', false)
        return
      }
      setAuditDetail(payload.entry as unknown as LlmAuditEntry)
    } catch (error) {
      showToast(`Failed to load audit detail: ${String(error)}`, false)
    }
  }, [])

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

  const resetModelForm = useCallback((): void => {
    setEditingModelId('')
    setModelType('llm')
    setModelBaseUrl('')
    setModelApiPath('')
    setModelName('')
    setModelApiKey('')
    setModelDesc('')
  }, [])

  const startEditingModel = useCallback((model: RegisteredModelEntry): void => {
    setEditingModelId(model.id)
    setModelType(model.model_type)
    setModelBaseUrl(model.base_url ?? '')
    setModelApiPath(model.api_path ?? '')
    setModelName(model.model_name)
    setModelApiKey('')
    setModelDesc(model.desc ?? '')
    setControlPanel('models')
    setActivePage('control')
  }, [])

  const resolveHelpRequest = async (taskId: string): Promise<void> => {
    if (resolvingTaskId) return
    const resolution = window.prompt('Describe what you resolved (or leave blank):', '')
    if (resolution === null) return
    setResolvingTaskId(taskId)
    try {
      const payload = await dashboardApiClient.resolveHelpRequest({
        task_id: taskId,
        resolution: resolution || 'Resolved via dashboard',
      })
      if (payload.error) {
        showToast(payload.error, false)
        return
      }
      showToast('Marked resolved, agent will continue verification')
      await Promise.all([refreshSummary(), refreshHelpCenter()])
    } catch (error) {
      showToast(`Resolve failed: ${String(error)}`, false)
    } finally {
      setResolvingTaskId('')
    }
  }

  const saveDirective = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    if (!directive) {
      showToast('Directive not loaded', false)
      return
    }
    try {
      const form = new FormData(event.currentTarget)
      const payload: DirectivePayload = {
        paused: String(form.get('paused')) === 'true',
        poll_interval_seconds: Number(form.get('poll_interval_seconds') ?? 120),
        max_file_changes_per_task: Number(form.get('max_file_changes_per_task') ?? 10),
        focus_areas: String(form.get('focus_areas') ?? '').split(',').map((item) => item.trim()).filter(Boolean),
        forbidden_paths: String(form.get('forbidden_paths') ?? '').split(',').map((item) => item.trim()).filter(Boolean),
        custom_instructions: String(form.get('custom_instructions') ?? ''),
        task_sources: JSON.parse(sourcesJson),
      }
      await dashboardApiClient.saveDirective(payload)
      showToast('Directive saved')
      await refreshSummary()
    } catch (error) {
      showToast(`Save directive failed: ${String(error)}`, false)
    }
  }

  const injectTask = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    const title = injectTitle.trim()
    if (!title) {
      showToast('Title required', false)
      return
    }
    try {
      await dashboardApiClient.injectTask({ title, description: injectDescription, priority: injectPriority })
      showToast('Task injected')
      setInjectTitle('')
      setInjectDescription('')
      setInjectPriority(2)
      await refreshSummary()
    } catch (error) {
      showToast(`Inject task failed: ${String(error)}`, false)
    }
  }

  const registerModel = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    const baseUrl = modelBaseUrl.trim()
    const apiPath = modelApiPath.trim()
    const trimmedModelName = modelName.trim()
    const apiKey = modelApiKey.trim()
    const isEmbeddingRegistration = modelType === 'embedding'
    const hasRequiredEndpoint = isEmbeddingRegistration ? Boolean(apiPath) : Boolean(baseUrl)
    const requiresApiKey = !editingModelId
    if (!hasRequiredEndpoint || !trimmedModelName || (requiresApiKey && !apiKey)) {
      const message = requiresApiKey
        ? `${isEmbeddingRegistration ? 'API path' : 'Base URL'}, model name, and AK are required`
        : `${isEmbeddingRegistration ? 'API path' : 'Base URL'} and model name are required`
      showToast(message, false)
      return
    }
    try {
      const modelPayload = {
        model_type: modelType,
        base_url: baseUrl,
        api_path: apiPath,
        model_name: trimmedModelName,
        api_key: apiKey,
        desc: modelDesc.trim(),
      }
      const payload = editingModelId
        ? await dashboardApiClient.updateModel(editingModelId, modelPayload)
        : await dashboardApiClient.registerModel(modelPayload)
      if (payload.error) {
        showToast(payload.error, false)
        return
      }
      showToast(editingModelId ? 'Model updated' : 'Model registered')
      resetModelForm()
      await Promise.all([refreshModels(), refreshSummary()])
    } catch (error) {
      showToast(`${editingModelId ? 'Update' : 'Register'} model failed: ${String(error)}`, false)
    }
  }

  const deleteModel = async (model: RegisteredModelEntry): Promise<void> => {
    if (deletingModelId) return
    const confirmed = window.confirm(`Delete model "${model.model_name}"? Related bindings will be cleared.`)
    if (!confirmed) return
    setDeletingModelId(model.id)
    try {
      const payload = await dashboardApiClient.deleteModel(model.id)
      if (payload.error) {
        showToast(payload.error, false)
        return
      }
      if (editingModelId === model.id) resetModelForm()
      showToast('Model deleted')
      await Promise.all([refreshModels(), refreshSummary()])
    } catch (error) {
      showToast(`Delete model failed: ${String(error)}`, false)
    } finally {
      setDeletingModelId('')
    }
  }

  const saveModelBindings = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    try {
      const payload = await dashboardApiClient.saveModelBindings({ bindings: modelBindings })
      if (payload.error) {
        showToast(payload.error, false)
        return
      }
      showToast('Model bindings saved')
      await Promise.all([refreshModels(), refreshSummary()])
    } catch (error) {
      showToast(`Save model bindings failed: ${String(error)}`, false)
    }
  }

  useEffect(() => {
    const kickoffId = window.setTimeout(() => void refreshSummary(), 0)
    const timerId = window.setInterval(() => void refreshSummary(), 5000)
    return () => {
      window.clearTimeout(kickoffId)
      window.clearInterval(timerId)
    }
  }, [refreshSummary])

  useEffect(() => {
    const kickoffId = window.setTimeout(() => void refreshActivity(), 0)
    const timerId = window.setInterval(() => void refreshActivity(), activePage === 'discovery' ? 3000 : 5000)
    return () => {
      window.clearTimeout(kickoffId)
      window.clearInterval(timerId)
    }
  }, [refreshActivity, activePage])

  useEffect(() => {
    const kickoffId = window.setTimeout(() => void refreshDiscovery(), 0)
    const timerId = window.setInterval(() => void refreshDiscovery(), activePage === 'discovery' ? 3000 : 8000)
    return () => {
      window.clearTimeout(kickoffId)
      window.clearInterval(timerId)
    }
  }, [refreshDiscovery, activePage])

  useEffect(() => {
    if (activePage !== 'memory') return
    const kickoffId = window.setTimeout(() => void refreshAudit(), 0)
    const timerId = window.setInterval(() => void refreshAudit(), 5000)
    return () => {
      window.clearTimeout(kickoffId)
      window.clearInterval(timerId)
    }
  }, [activePage, refreshAudit])

  useEffect(() => {
    const kickoffId = window.setTimeout(() => void refreshHelpCenter(), 0)
    const timerId = window.setInterval(() => void refreshHelpCenter(), 5000)
    return () => {
      window.clearTimeout(kickoffId)
      window.clearInterval(timerId)
    }
  }, [refreshHelpCenter])

  useEffect(() => {
    const kickoffId = window.setTimeout(() => void refreshThreads(), 0)
    const timerId = window.setInterval(() => void refreshThreads(), activePage === 'inbox' ? 3000 : 8000)
    return () => {
      window.clearTimeout(kickoffId)
      window.clearInterval(timerId)
    }
  }, [refreshThreads, activePage])

  useEffect(() => {
    if (activePage !== 'memory') return
    const kickoffId = window.setTimeout(() => void refreshExperiences(), 0)
    const timerId = window.setInterval(() => void refreshExperiences(), 8000)
    return () => {
      window.clearTimeout(kickoffId)
      window.clearInterval(timerId)
    }
  }, [activePage, refreshExperiences])

  useEffect(() => {
    if (activePage !== 'control') return
    const kickoffId = window.setTimeout(() => void refreshModels(), 0)
    const timerId = window.setInterval(() => void refreshModels(), 8000)
    return () => {
      window.clearTimeout(kickoffId)
      window.clearInterval(timerId)
    }
  }, [activePage, refreshModels])

  let pageContent: React.ReactNode
  if (activePage === 'overview') {
    pageContent = (
      <OverviewPage
        activity={activity}
        bootstrapStatus={bootstrapStatus}
        cycles={cycles}
        directive={directive}
        helpRequests={helpRequests}
        onNavigate={setActivePage}
        onOpenTaskDetail={(taskId) => void openTaskDetail(taskId)}
        stats={stats}
        tasks={tasks}
      />
    )
  } else if (activePage === 'work') {
    pageContent = (
      <WorkPage
        activePanel={workPanel}
        cycles={cycles}
        onChangePanel={setWorkPanel}
        onOpenTaskDetail={(taskId) => void openTaskDetail(taskId)}
        taskDetail={taskDetail}
        taskEvents={taskEvents}
        tasks={tasks}
      />
    )
  } else if (activePage === 'inbox') {
    pageContent = (
      <InboxPage
        threads={threads}
        threadDetail={threadDetail}
        onSelectThread={(id) => void openThreadDetail(id)}
        onReply={(id, body) => replyToThread(id, body)}
        onCreateThread={(title, desc) => createThread(title, desc)}
        onRefresh={() => void refreshThreads()}
        replying={Boolean(replyingThreadId)}
        creating={creatingThread}
      />
    )
  } else if (activePage === 'discovery') {
    pageContent = <DiscoveryPage discovery={discovery} />
  } else if (activePage === 'memory') {
    pageContent = (
      <MemoryAuditPage
        activePanel={memoryPanel}
        activity={activity}
        activityGroupBy={activityGroupBy}
        activityPhase={activityPhase}
        audit={audit}
        auditDetail={auditDetail}
        collapsedTasks={collapsedTasks}
        experiences={experiences}
        onChangeActivityGroupBy={setActivityGroupBy}
        onChangeActivityPhase={setActivityPhase}
        onChangePanel={setMemoryPanel}
        onCloseAuditDetail={() => setAuditDetail(null)}
        onOpenAuditDetail={(seq) => void openAuditDetail(seq)}
        onRefreshActivity={() => void refreshActivity()}
        onRefreshAudit={() => void refreshAudit()}
        onRefreshExperiences={() => void refreshExperiences()}
        onToggleCollapsedTask={(taskId) => {
          setCollapsedTasks((current) => {
            const next = new Set(current)
            if (next.has(taskId)) next.delete(taskId)
            else next.add(taskId)
            return next
          })
        }}
        tasks={tasks}
      />
    )
  } else {
    pageContent = (
      <ControlPage
        activePanel={controlPanel}
        bindingPoints={bindingPoints}
        deletingModelId={deletingModelId}
        directive={directive}
        editingModelId={editingModelId}
        helpCount={helpCount}
        helpRequests={helpRequests}
        injectDescription={injectDescription}
        injectPriority={injectPriority}
        injectTitle={injectTitle}
        modelApiKey={modelApiKey}
        modelApiPath={modelApiPath}
        modelBaseUrl={modelBaseUrl}
        modelBindings={modelBindings}
        modelDesc={modelDesc}
        modelName={modelName}
        modelType={modelType}
        onChangePanel={setControlPanel}
        onDeleteModel={(model) => void deleteModel(model)}
        onInjectTask={(event) => void injectTask(event)}
        onRegisterModel={(event) => void registerModel(event)}
        onResetModelForm={resetModelForm}
        onResolveHelpRequest={(taskId) => void resolveHelpRequest(taskId)}
        onSaveDirective={(event) => void saveDirective(event)}
        onSaveModelBindings={(event) => void saveModelBindings(event)}
        onStartEditingModel={startEditingModel}
        registeredModels={registeredModels}
        resolvingTaskId={resolvingTaskId}
        setInjectDescription={setInjectDescription}
        setInjectPriority={setInjectPriority}
        setInjectTitle={setInjectTitle}
        setModelApiKey={setModelApiKey}
        setModelApiPath={setModelApiPath}
        setModelBaseUrl={setModelBaseUrl}
        setModelBindings={(updater) => setModelBindings((current) => updater(current))}
        setModelDesc={setModelDesc}
        setModelName={setModelName}
        setModelType={setModelType}
        setSourcesJson={setSourcesJson}
        sourcesJson={sourcesJson}
      />
    )
  }

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
        {pageContent}
      </DashboardShell>
    </>
  )
}

export default App
