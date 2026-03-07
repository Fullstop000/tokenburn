import { useCallback, useEffect, useMemo, useState } from 'react'
import { dashboardApiClient } from './api/dashboardApi'
import type {
  CycleSummary,
  BootstrapStatusPayload,
  DashboardStats,
  DirectivePayload,
  ExperienceEntry,
  LlmAuditEntry,
  ModelBindingPointEntry,
  RegisteredModelEntry,
  TaskDetail,
  TaskEvent,
  TaskSummary,
} from './types/dashboard'

// shadcn/ui components
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

import { Toaster, toast } from 'sonner'

// Custom components
import { StatusBadge } from '@/components/ui/status-badge'
import { PhaseBadge } from '@/components/ui/phase-badge'
import { PriorityBadge } from '@/components/ui/priority-badge'

import './App.css'

type DashboardTab = 'tasks' | 'detail' | 'cycles' | 'activity' | 'audit' | 'help' | 'experience' | 'models' | 'control' | 'inject'

const MODEL_CONNECTION_LABEL: Record<string, string> = {
  success: 'Success',
  fail: 'Fail',
}

function formatTime(iso?: string): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return iso.slice(11, 19) || iso
  }
}

function formatDateTime(iso?: string): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    return d.toLocaleString('en-GB', {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
  } catch {
    return iso
  }
}

interface TaskGroup {
  taskId: string
  title: string
  events: Record<string, unknown>[]
}

function groupActivityByTask(
  events: Record<string, unknown>[],
  taskList: TaskSummary[],
): { global: Record<string, unknown>[]; groups: TaskGroup[] } {
  const titleMap = new Map<string, string>()
  for (const t of taskList) titleMap.set(t.id, t.title)

  const global: Record<string, unknown>[] = []
  const byTask = new Map<string, Record<string, unknown>[]>()

  for (const ev of events) {
    const tid = String(ev.task_id ?? '')
    if (!tid) {
      global.push(ev)
    } else {
      const arr = byTask.get(tid)
      if (arr) arr.push(ev)
      else byTask.set(tid, [ev])
    }
  }

  const groups: TaskGroup[] = []
  for (const [taskId, evts] of byTask) {
    groups.push({
      taskId,
      title: titleMap.get(taskId) ?? `Task ${taskId.slice(0, 8)}`,
      events: evts,
    })
  }
  groups.sort((a, b) => {
    const aTs = String(a.events[a.events.length - 1]?.timestamp ?? '')
    const bTs = String(b.events[b.events.length - 1]?.timestamp ?? '')
    return bTs.localeCompare(aTs)
  })

  return { global, groups }
}

function ActivityByTask({
  activity,
  collapsedTasks,
  onToggle,
  tasks,
}: {
  activity: Record<string, unknown>[]
  collapsedTasks: Set<string>
  onToggle: (id: string) => void
  tasks: TaskSummary[]
}) {
  const { global, groups } = useMemo(
    () => groupActivityByTask(activity, tasks),
    [activity, tasks],
  )

  return (
    <div className="space-y-1">
      {global.length > 0 && (
        <div className="border rounded-lg overflow-hidden">
          <div className="bg-muted/50 px-4 py-2 flex items-center gap-2">
            <span className="text-muted-foreground">●</span>
            <span className="font-medium">Global Events</span>
            <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">{global.length}</span>
          </div>
          <div className="divide-y">
            {global.map((ev, idx) => {
              const phase = String(ev.phase ?? '')
              const ts = String(ev.ts ?? ev.timestamp ?? '')
              const msg = String(ev.message ?? ev.detail ?? ev.event ?? JSON.stringify(ev))
              return (
                <div className="px-4 py-2 flex items-center gap-3 text-sm" key={`g-${idx}`}>
                  <span className="text-xs text-muted-foreground font-mono w-20 shrink-0">{formatTime(ts)}</span>
                  <PhaseBadge phase={phase || '?'} />
                  <span className="text-foreground">{msg}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {groups.map((group) => {
        const isCollapsed = collapsedTasks.has(group.taskId)
        const lastPhase = String(group.events[group.events.length - 1]?.phase ?? '')
        return (
          <div className="border rounded-lg overflow-hidden" key={group.taskId}>
            <button
              className="w-full bg-muted/50 px-4 py-2 flex items-center gap-2 hover:bg-muted transition-colors text-left"
              onClick={() => onToggle(group.taskId)}
            >
              <span className={`text-xs text-muted-foreground transition-transform ${isCollapsed ? '-rotate-90' : ''}`}>▾</span>
              <PhaseBadge phase={lastPhase || 'system'} />
              <span className="font-medium truncate">{group.title}</span>
              <span className="text-xs text-muted-foreground font-mono">{group.taskId.slice(0, 8)}</span>
              <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full ml-auto">{group.events.length}</span>
            </button>
            {!isCollapsed && (
              <div className="divide-y">
                {group.events.map((ev, idx) => {
                  const phase = String(ev.phase ?? '')
                  const ts = String(ev.ts ?? ev.timestamp ?? '')
                  const action = String(ev.action ?? '')
                  const msg = String(ev.message ?? ev.detail ?? ev.event ?? '')
                  const success = ev.success
                  const reasoning = String(ev.reasoning ?? '')
                  return (
                    <div className={`px-4 py-2 flex items-start gap-3 text-sm ${success === false ? 'bg-destructive/5' : ''}`} key={idx}>
                      <span className="text-xs text-muted-foreground font-mono w-16 shrink-0">{formatTime(ts)}</span>
                      <PhaseBadge phase={phase || 'system'} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-mono font-medium">{action}</span>
                          {msg && <span className="text-muted-foreground">{msg}</span>}
                          {success === true && <span className="text-green-500 font-bold">✓</span>}
                          {success === false && <span className="text-destructive font-bold">✗</span>}
                        </div>
                        {reasoning && <p className="text-xs text-muted-foreground italic mt-1">{reasoning}</p>}
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
        <p className="text-muted-foreground text-center py-8 italic">No activity events</p>
      )}
    </div>
  )
}

function DashboardRoot() {
  const [activeTab, setActiveTab] = useState<DashboardTab>('tasks')
  const [metaText, setMetaText] = useState<string>('Loading...')

  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [cycles, setCycles] = useState<CycleSummary[]>([])
  const [stats, setStats] = useState<DashboardStats>({})
  const [directive, setDirective] = useState<DirectivePayload | null>(null)
  const [bootstrapStatus, setBootstrapStatus] = useState<BootstrapStatusPayload | null>(null)

  const [taskDetail, setTaskDetail] = useState<TaskDetail | null>(null)
  const [taskEvents, setTaskEvents] = useState<TaskEvent[]>([])

  const [activity, setActivity] = useState<Record<string, unknown>[]>([])
  const [activityPhase, setActivityPhase] = useState<string>('')
  const [activityGroupBy, setActivityGroupBy] = useState<'time' | 'task'>('task')
  const [collapsedTasks, setCollapsedTasks] = useState<Set<string>>(new Set())

  const [audit, setAudit] = useState<LlmAuditEntry[]>([])
  const [auditDetail, setAuditDetail] = useState<LlmAuditEntry | null>(null)
  const [helpRequests, setHelpRequests] = useState<TaskSummary[]>([])
  const [helpCount, setHelpCount] = useState<number>(0)
  const [experiences, setExperiences] = useState<ExperienceEntry[]>([])
  const [registeredModels, setRegisteredModels] = useState<RegisteredModelEntry[]>([])
  const [bindingPoints, setBindingPoints] = useState<ModelBindingPointEntry[]>([])
  const [modelBindings, setModelBindings] = useState<Record<string, string>>({})

  const [injectTitle, setInjectTitle] = useState<string>('')
  const [injectDescription, setInjectDescription] = useState<string>('')
  const [injectPriority, setInjectPriority] = useState<number>(2)
  const [sourcesJson, setSourcesJson] = useState<string>('{}')
  const [modelType, setModelType] = useState<'llm' | 'embedding'>('llm')
  const [modelBaseUrl, setModelBaseUrl] = useState<string>('')
  const [modelApiPath, setModelApiPath] = useState<string>('')
  const [modelName, setModelName] = useState<string>('')
  const [modelApiKey, setModelApiKey] = useState<string>('')
  const [modelDesc, setModelDesc] = useState<string>('')
  const [editingModelId, setEditingModelId] = useState<string>('')
  const [deletingModelId, setDeletingModelId] = useState<string>('')

  const [pauseLoading, setPauseLoading] = useState<boolean>(false)
  const [resolvingTaskId, setResolvingTaskId] = useState<string>('')

  const showToast = (message: string, ok = true): void => {
    if (ok) {
      toast.success(message)
    } else {
      toast.error(message)
    }
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

  const togglePause = async (): Promise<void> => {
    if (pauseLoading || !directive) return
    setPauseLoading(true)
    try {
      const result = directive.paused
        ? await dashboardApiClient.resume()
        : await dashboardApiClient.pause()
      showToast(result.paused ? 'Agent paused' : 'Agent resumed')
      await refreshSummary()
    } catch (error) {
      showToast(`Toggle pause failed: ${String(error)}`, false)
    } finally {
      setPauseLoading(false)
    }
  }

  const openTaskDetail = useCallback(async (taskId: string): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getTaskDetail(taskId)
      if (payload.error || !payload.task) {
        showToast(payload.error ?? 'Task not found', false)
        return
      }
      setTaskDetail(payload.task)
      setTaskEvents(payload.events ?? [])
      setActiveTab('detail')
    } catch (error) {
      showToast(`Failed to load task detail: ${String(error)}`, false)
    }
  }, [])

  const refreshActivity = useCallback(async (): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getActivity(300, activityPhase)
      setActivity(payload.events)
    } catch (error) {
      showToast(`Failed to refresh activity: ${String(error)}`, false)
    }
  }, [activityPhase])

  const refreshAudit = useCallback(async (): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getLlmAudit(100)
      setAudit(payload.entries)
    } catch (error) {
      showToast(`Failed to refresh audit: ${String(error)}`, false)
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

  const refreshHelpCenter = useCallback(async (): Promise<void> => {
    try {
      const payload = await dashboardApiClient.getHelpCenter()
      setHelpRequests(payload.requests ?? [])
    } catch (error) {
      showToast(`Failed to refresh help center: ${String(error)}`, false)
    }
  }, [])

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
  }, [])

  const resolveHelpRequest = async (taskId: string): Promise<void> => {
    if (resolvingTaskId) return
    const resolution = window.prompt(
      'Describe what you resolved (or leave blank):',
      '',
    )
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
        focus_areas: String(form.get('focus_areas') ?? '')
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
        forbidden_paths: String(form.get('forbidden_paths') ?? '')
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
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
      await dashboardApiClient.injectTask({
        title,
        description: injectDescription,
        priority: injectPriority,
      })
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
      if (editingModelId === model.id) {
        resetModelForm()
      }
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
    if (activeTab !== 'activity') return
    const kickoffId = window.setTimeout(() => void refreshActivity(), 0)
    const timerId = window.setInterval(() => void refreshActivity(), 3000)
    return () => {
      window.clearTimeout(kickoffId)
      window.clearInterval(timerId)
    }
  }, [activeTab, refreshActivity])

  useEffect(() => {
    if (activeTab !== 'audit') return
    const kickoffId = window.setTimeout(() => void refreshAudit(), 0)
    const timerId = window.setInterval(() => void refreshAudit(), 5000)
    return () => {
      window.clearTimeout(kickoffId)
      window.clearInterval(timerId)
    }
  }, [activeTab, refreshAudit])

  useEffect(() => {
    if (activeTab !== 'help') return
    const kickoffId = window.setTimeout(() => void refreshHelpCenter(), 0)
    const timerId = window.setInterval(() => void refreshHelpCenter(), 5000)
    return () => {
      window.clearTimeout(kickoffId)
      window.clearInterval(timerId)
    }
  }, [activeTab, refreshHelpCenter])

  useEffect(() => {
    if (activeTab !== 'experience') return
    const kickoffId = window.setTimeout(() => void refreshExperiences(), 0)
    const timerId = window.setInterval(() => void refreshExperiences(), 8000)
    return () => {
      window.clearTimeout(kickoffId)
      window.clearInterval(timerId)
    }
  }, [activeTab, refreshExperiences])

  useEffect(() => {
    if (activeTab !== 'models') return
    const kickoffId = window.setTimeout(() => void refreshModels(), 0)
    const timerId = window.setInterval(() => void refreshModels(), 8000)
    return () => {
      window.clearTimeout(kickoffId)
      window.clearInterval(timerId)
    }
  }, [activeTab, refreshModels])

  useEffect(() => {
    if (!bootstrapStatus?.requires_setup) return
    if (activeTab !== 'models') {
      setActiveTab('models')
    }
  }, [activeTab, bootstrapStatus])

  const sortedStatus = useMemo(() => {
    return Object.entries(stats.status_counts ?? {}).sort((left, right) => Number(right[1]) - Number(left[1]))
  }, [stats])
  const isEditingModel = Boolean(editingModelId)
  const isEmbeddingModel = modelType === 'embedding'
  const modelEndpointLabel = isEmbeddingModel ? 'API Path' : 'Base URL'
  const modelEndpointHint = isEmbeddingModel
    ? 'The full embedding endpoint path, for example `https://ark-cn-beijing.bytedance.net/api/v3/embeddings/multimodal`.'
    : 'The OpenAI-compatible API root for this provider, for example `https://example.com/v1`.'
  const modelEndpointPlaceholder = isEmbeddingModel
    ? 'https://ark-cn-beijing.bytedance.net/api/v3/embeddings/multimodal'
    : 'https://example.com/v1'
  const modelFormTitle = isEditingModel ? 'Edit Model' : 'Register Model'
  const modelFormSubtitle = isEditingModel
    ? 'Update one registered model. Leave AK empty to keep the current secret.'
    : 'Store reusable LLM base URLs or embedding API paths for dashboard binding.'

  return (
    <div className="min-h-screen bg-background">
      <Toaster position="bottom-right" richColors />
      <main className="max-w-[1400px] mx-auto px-6 py-5 pb-16">
        {/* Header */}
        <header className="flex justify-between items-end gap-4 mb-5 pb-5 border-b">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-primary mb-1">Sprout Agent V2</p>
            <h1 className="text-3xl font-bold tracking-tight">Control Plane</h1>
          </div>
          <div className="flex flex-col items-end gap-2">
            {directive && (
              <Button
                variant={directive.paused ? 'destructive' : 'default'}
                onClick={() => void togglePause()}
                disabled={pauseLoading}
                className="min-w-[140px]"
              >
                <span className={`mr-2 h-2 w-2 rounded-full ${directive.paused ? 'bg-red-300' : 'bg-green-300 animate-pulse'}`} />
                {pauseLoading ? '...' : directive.paused ? 'Resume Agent' : 'Pause Agent'}
              </Button>
            )}
            <p className="text-xs text-muted-foreground font-mono">{metaText}</p>
          </div>
        </header>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-5">
          {bootstrapStatus?.requires_setup && (
            <Card className="border-yellow-500/30 bg-yellow-500/10 col-span-full md:col-span-2">
              <CardHeader className="py-3">
                <CardTitle className="text-sm text-yellow-600">Initialization Required</CardTitle>
                <CardDescription className="text-xs">{bootstrapStatus.message}</CardDescription>
              </CardHeader>
            </Card>
          )}
          <Card>
            <CardHeader className="py-3">
              <CardDescription className="text-xs uppercase">Total Tasks</CardDescription>
              <CardTitle className="text-2xl">{stats.total_tasks ?? 0}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="py-3">
              <CardDescription className="text-xs uppercase">Total Cycles</CardDescription>
              <CardTitle className="text-2xl">{stats.total_cycles ?? 0}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="py-3">
              <CardDescription className="text-xs uppercase">Total Tokens</CardDescription>
              <CardTitle className="text-2xl">{(stats.total_tokens ?? 0).toLocaleString()}</CardTitle>
            </CardHeader>
          </Card>
          {sortedStatus.map(([status, count]) => (
            <Card key={status}>
              <CardHeader className="py-3">
                <CardDescription className="text-xs uppercase">{status}</CardDescription>
                <CardTitle className="text-2xl">{String(count)}</CardTitle>
              </CardHeader>
            </Card>
          ))}
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as DashboardTab)} className="mb-4">
          <TabsList className="flex-wrap h-auto">
            <TabsTrigger value="tasks">Tasks</TabsTrigger>
            {taskDetail && <TabsTrigger value="detail">Detail</TabsTrigger>}
            <TabsTrigger value="cycles">Cycles</TabsTrigger>
            <TabsTrigger value="activity">Activity</TabsTrigger>
            <TabsTrigger value="audit">LLM Audit</TabsTrigger>
            <TabsTrigger value="help">
              Help Center {helpCount > 0 && `(${helpCount})`}
            </TabsTrigger>
            <TabsTrigger value="experience">Experience</TabsTrigger>
            <TabsTrigger value="models">Models</TabsTrigger>
            <TabsTrigger value="control">Control</TabsTrigger>
            <TabsTrigger value="inject">Inject</TabsTrigger>
          </TabsList>
        </Tabs>

        {/* Tasks Tab */}
        {activeTab === 'tasks' && (
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="min-w-[260px]">Task</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Priority</TableHead>
                    <TableHead>Source</TableHead>
                    <TableHead className="text-right">Tokens</TableHead>
                    <TableHead className="text-right">Time</TableHead>
                    <TableHead>PR</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tasks.map((task) => (
                    <TableRow key={task.id} className="cursor-pointer" onClick={() => void openTaskDetail(task.id)}>
                      <TableCell>
                        <div className="font-medium">{task.title}</div>
                        <div className="text-xs text-muted-foreground font-mono">{task.id}</div>
                      </TableCell>
                      <TableCell><StatusBadge status={task.status} /></TableCell>
                      <TableCell><PriorityBadge priority={task.priority} /></TableCell>
                      <TableCell>
                        <code className="text-xs bg-muted px-1.5 py-0.5 rounded">{task.source}</code>
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs text-muted-foreground">
                        {task.token_cost ? task.token_cost.toLocaleString() : '-'}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs text-muted-foreground">
                        {task.time_cost_seconds ? `${task.time_cost_seconds.toFixed(1)}s` : '-'}
                      </TableCell>
                      <TableCell>
                        {task.pr_url ? (
                          <a href={task.pr_url} target="_blank" rel="noreferrer" className="text-primary hover:underline text-sm" onClick={(e) => e.stopPropagation()}>
                            PR ↗
                          </a>
                        ) : (
                          <span className="text-muted-foreground text-xs">-</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                  {tasks.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center text-muted-foreground py-8 italic">
                        No tasks yet
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

        {/* Detail Tab */}
        {activeTab === 'detail' && taskDetail && (
          <Card>
            <CardHeader>
              <CardTitle>{taskDetail.title}</CardTitle>
              <CardDescription className="flex flex-wrap gap-4 mt-2">
                <span>Status: <StatusBadge status={taskDetail.status} /></span>
                <span>Priority: <PriorityBadge priority={taskDetail.priority} /></span>
                <span>Source: <code className="bg-muted px-1.5 py-0.5 rounded text-xs">{taskDetail.source}</code></span>
                <span>Created: <span className="font-mono text-xs">{formatDateTime(taskDetail.created_at)}</span></span>
                <span>Updated: <span className="font-mono text-xs">{formatDateTime(taskDetail.updated_at)}</span></span>
                {taskDetail.token_cost && (
                  <span>Tokens: <span className="font-mono text-xs">{taskDetail.token_cost.toLocaleString()}</span></span>
                )}
                {taskDetail.time_cost_seconds && (
                  <span>Duration: <span className="font-mono text-xs">{taskDetail.time_cost_seconds.toFixed(1)}s</span></span>
                )}
                {taskDetail.branch_name && (
                  <span>Branch: <span className="font-mono text-xs">{taskDetail.branch_name}</span></span>
                )}
                {taskDetail.pr_url && (
                  <span>
                    PR: <a href={taskDetail.pr_url} target="_blank" rel="noreferrer" className="text-primary hover:underline">View Pull Request ↗</a>
                  </span>
                )}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {taskDetail.description && (
                <div>
                  <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-2">Description</h3>
                  <p className="text-sm leading-relaxed">{taskDetail.description}</p>
                </div>
              )}
              {taskDetail.error_message && (
                <div>
                  <h3 className="text-sm font-semibold uppercase text-destructive mb-2">Error</h3>
                  <pre className="bg-destructive/5 border border-destructive/20 text-destructive p-3 rounded-md text-xs overflow-auto">{taskDetail.error_message}</pre>
                </div>
              )}
              {taskDetail.human_help_request && (
                <div>
                  <h3 className="text-sm font-semibold uppercase text-yellow-600 mb-2">Human Help Request</h3>
                  <pre className="bg-yellow-500/5 border border-yellow-500/20 text-yellow-600 p-3 rounded-md text-xs overflow-auto">{taskDetail.human_help_request}</pre>
                </div>
              )}
              {taskDetail.plan && (
                <div>
                  <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-2">Execution Plan</h3>
                  <pre className="bg-muted p-3 rounded-md text-xs overflow-auto">{taskDetail.plan}</pre>
                </div>
              )}
              {taskDetail.execution_log && (
                <div>
                  <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-2">Execution Log</h3>
                  <pre className="bg-muted p-3 rounded-md text-xs overflow-auto">{taskDetail.execution_log}</pre>
                </div>
              )}
              {taskDetail.verification_result && (
                <div>
                  <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-2">Verification</h3>
                  <pre className="bg-muted p-3 rounded-md text-xs overflow-auto">{taskDetail.verification_result}</pre>
                </div>
              )}
              {taskDetail.whats_learned && (
                <div>
                  <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-2">What Was Learned</h3>
                  <pre className="bg-muted p-3 rounded-md text-xs overflow-auto">{taskDetail.whats_learned}</pre>
                </div>
              )}
              <div>
                <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-2">
                  Events <span className="bg-muted px-2 py-0.5 rounded-full text-xs">{taskEvents.length}</span>
                </h3>
                {taskEvents.length > 0 ? (
                  <div className="space-y-2">
                    {taskEvents.map((ev, idx) => (
                      <div key={idx} className="flex items-start gap-3 text-sm border-l-2 border-muted pl-3">
                        <span className="font-mono text-xs text-primary font-semibold">{ev.event_type}</span>
                        <span className="font-mono text-xs text-muted-foreground">{formatTime(ev.created_at)}</span>
                        {ev.detail && <span className="text-muted-foreground">{ev.detail}</span>}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-muted-foreground italic">No events recorded</p>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Cycles Tab */}
        {activeTab === 'cycles' && (
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Cycle</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Started</TableHead>
                    <TableHead>Completed</TableHead>
                    <TableHead className="text-right">Discovered</TableHead>
                    <TableHead className="text-right">Executed</TableHead>
                    <TableHead className="text-right">Completed</TableHead>
                    <TableHead className="text-right">Failed</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {cycles.map((cycle) => (
                    <TableRow key={cycle.id}>
                      <TableCell className="font-mono">#{cycle.id}</TableCell>
                      <TableCell><StatusBadge status={cycle.status} /></TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">{formatDateTime(cycle.started_at)}</TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">{formatDateTime(cycle.completed_at)}</TableCell>
                      <TableCell className="text-right">{cycle.discovered}</TableCell>
                      <TableCell className="text-right">{cycle.executed}</TableCell>
                      <TableCell className="text-right">{cycle.completed}</TableCell>
                      <TableCell className={`text-right ${cycle.failed > 0 ? 'text-destructive font-semibold' : ''}`}>{cycle.failed}</TableCell>
                    </TableRow>
                  ))}
                  {cycles.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={8} className="text-center text-muted-foreground py-8 italic">
                        No cycles yet
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

        {/* Activity Tab */}
        {activeTab === 'activity' && (
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center gap-3 flex-wrap">
                <Select value={activityPhase || '__all__'} onValueChange={(v) => setActivityPhase(v === '__all__' ? '' : v)}>
                  <SelectTrigger className="w-[140px]">
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
                <div className="flex bg-muted rounded-md p-0.5">
                  <Button
                    variant={activityGroupBy === 'time' ? 'secondary' : 'ghost'}
                    size="sm"
                    onClick={() => setActivityGroupBy('time')}
                  >
                    Timeline
                  </Button>
                  <Button
                    variant={activityGroupBy === 'task' ? 'secondary' : 'ghost'}
                    size="sm"
                    onClick={() => setActivityGroupBy('task')}
                  >
                    By Task
                  </Button>
                </div>
                <Button variant="outline" size="sm" onClick={() => void refreshActivity()}>Refresh</Button>
              </div>
            </CardHeader>
            <CardContent>
              {activityGroupBy === 'time' ? (
                <div className="space-y-1 max-h-[70vh] overflow-y-auto">
                  {activity.length > 0 ? (
                    [...activity].reverse().map((ev, idx) => {
                      const phase = String(ev.phase ?? '')
                      const ts = String(ev.ts ?? ev.timestamp ?? '')
                      const msg = String(ev.message ?? ev.detail ?? ev.event ?? JSON.stringify(ev))
                      const taskId = String(ev.task_id ?? '')
                      return (
                        <div className="flex items-start gap-3 text-sm py-2 border-b last:border-0" key={idx}>
                          <span className="text-xs text-muted-foreground font-mono w-20 shrink-0">{formatTime(ts)}</span>
                          <PhaseBadge phase={phase || '?'} />
                          <span className="text-foreground">
                            {taskId && <code className="text-xs bg-muted px-1 py-0.5 rounded mr-2">{taskId.slice(0, 8)}</code>}
                            {msg}
                          </span>
                        </div>
                      )
                    })
                  ) : (
                    <p className="text-muted-foreground text-center py-8 italic">No activity events</p>
                  )}
                </div>
              ) : (
                <div className="max-h-[75vh] overflow-y-auto">
                  <ActivityByTask
                    activity={activity}
                    collapsedTasks={collapsedTasks}
                    onToggle={(id) => {
                      setCollapsedTasks((prev) => {
                        const next = new Set(prev)
                        if (next.has(id)) next.delete(id)
                        else next.add(id)
                        return next
                      })
                    }}
                    tasks={tasks}
                  />
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Audit Tab */}
        {activeTab === 'audit' && (
          <Card>
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
                    <TableRow key={entry.seq} className="cursor-pointer" onClick={() => void openAuditDetail(entry.seq)}>
                      <TableCell className="font-mono">{entry.seq}</TableCell>
                      <TableCell>
                        <code className="text-xs bg-muted px-1.5 py-0.5 rounded">{entry.model ?? '-'}</code>
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {`${(entry.prompt_tokens ?? 0).toLocaleString()} / ${(entry.completion_tokens ?? 0).toLocaleString()}`}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs text-muted-foreground">
                        {entry.duration_ms ? `${(entry.duration_ms / 1000).toFixed(1)}s` : '-'}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs text-muted-foreground">{formatTime(entry.ts)}</TableCell>
                    </TableRow>
                  ))}
                  {audit.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-muted-foreground py-8 italic">
                        No audit entries
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

        {/* Help Center Tab */}
        {activeTab === 'help' && (
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="min-w-[240px]">Task</TableHead>
                    <TableHead>Need Human Help</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Updated</TableHead>
                    <TableHead>Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {helpRequests.map((task) => (
                    <TableRow key={task.id}>
                      <TableCell>
                        <div className="font-medium">{task.title}</div>
                        <div className="text-xs text-muted-foreground font-mono">{task.id}</div>
                      </TableCell>
                      <TableCell>
                        <div className="max-w-[620px] whitespace-pre-wrap text-xs font-mono bg-muted p-2 rounded">
                          {task.human_help_request || 'No detail provided'}
                        </div>
                      </TableCell>
                      <TableCell><StatusBadge status={task.status} /></TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">{formatDateTime(task.updated_at)}</TableCell>
                      <TableCell>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => void resolveHelpRequest(task.id)}
                          disabled={resolvingTaskId === task.id}
                        >
                          {resolvingTaskId === task.id ? 'Resolving...' : 'Resolve'}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                  {helpRequests.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-muted-foreground py-8 italic">
                        No unresolved human-help requests
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

        {/* Experience Tab */}
        {activeTab === 'experience' && (
          <Card>
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
                  {experiences.map((exp) => (
                    <TableRow key={exp.id}>
                      <TableCell className="font-mono text-xs">{exp.task_id || '-'}</TableCell>
                      <TableCell>
                        <code className="text-xs bg-muted px-1.5 py-0.5 rounded">{exp.category}</code>
                      </TableCell>
                      <TableCell>
                        <div className="text-sm">{exp.summary}</div>
                        {exp.detail && <div className="text-xs text-muted-foreground mt-1">{exp.detail}</div>}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs">
                        {typeof exp.confidence === 'number' ? exp.confidence.toFixed(2) : '-'}
                      </TableCell>
                      <TableCell className="text-right">{Number(exp.applied_count ?? 0)}</TableCell>
                      <TableCell>
                        <code className="text-xs bg-muted px-1.5 py-0.5 rounded">{exp.source_outcome || '-'}</code>
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs text-muted-foreground">{formatDateTime(exp.created_at)}</TableCell>
                    </TableRow>
                  ))}
                  {experiences.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center text-muted-foreground py-8 italic">
                        No experience entries yet
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

        {/* Models Tab */}
        {activeTab === 'models' && (
          <div className="space-y-4">
            <Card>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Type</TableHead>
                      <TableHead className="min-w-[320px]">Model</TableHead>
                      <TableHead className="min-w-[320px]">Endpoint</TableHead>
                      <TableHead>AK</TableHead>
                      <TableHead>Created</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {registeredModels.map((model) => (
                      <TableRow key={model.id}>
                        <TableCell>
                          <code className="text-xs bg-muted px-1.5 py-0.5 rounded">{model.model_type}</code>
                        </TableCell>
                        <TableCell>
                          <div className="font-medium">{model.model_name}</div>
                          <div className="text-xs text-muted-foreground font-mono">{model.id}</div>
                          {model.connection_status && (
                            <div className="flex items-center gap-2 mt-1.5 text-xs">
                              <span className={`h-2 w-2 rounded-full ${model.connection_status === 'success' ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.5)]' : 'bg-red-500'}`} />
                              <span className={model.connection_status === 'success' ? 'text-green-500 font-semibold' : 'text-red-500 font-semibold'}>
                                {MODEL_CONNECTION_LABEL[model.connection_status] ?? model.connection_status}
                              </span>
                              {model.connection_checked_at && (
                                <span className="text-muted-foreground">{formatTime(model.connection_checked_at)}</span>
                              )}
                            </div>
                          )}
                          {model.connection_message && (
                            <div className="text-xs text-muted-foreground mt-1">{model.connection_message}</div>
                          )}
                          {model.desc && <div className="text-xs text-muted-foreground mt-1.5">{model.desc}</div>}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {model.model_type === 'embedding' ? model.api_path || '-' : model.base_url || '-'}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">{model.api_key_preview}</TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">{formatDateTime(model.created_at)}</TableCell>
                        <TableCell>
                          <div className="flex gap-2">
                            <Button size="sm" variant="outline" onClick={() => startEditingModel(model)}>Edit</Button>
                            <Button
                              size="sm"
                              variant="destructive"
                              onClick={() => void deleteModel(model)}
                              disabled={deletingModelId === model.id}
                            >
                              {deletingModelId === model.id ? 'Deleting...' : 'Delete'}
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                    {registeredModels.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={6} className="text-center text-muted-foreground py-8 italic">
                          No registered models yet
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <p className="text-xs font-semibold uppercase tracking-wider text-primary mb-1">Registry</p>
                <CardTitle>{modelFormTitle}</CardTitle>
                <CardDescription>{modelFormSubtitle}</CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={(event) => void registerModel(event)} className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label className="text-sm font-medium">Model Type</label>
                      <p className="text-xs text-muted-foreground">Choose whether this endpoint serves chat/completion calls or embedding vectors.</p>
                      <Select value={modelType} onValueChange={(v) => setModelType(v as 'llm' | 'embedding')}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="llm">LLM</SelectItem>
                          <SelectItem value="embedding">Embedding</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-medium">{modelEndpointLabel}</label>
                      <p className="text-xs text-muted-foreground">{modelEndpointHint}</p>
                      <Input
                        value={isEmbeddingModel ? modelApiPath : modelBaseUrl}
                        onChange={(e) => isEmbeddingModel ? setModelApiPath(e.target.value) : setModelBaseUrl(e.target.value)}
                        placeholder={modelEndpointPlaceholder}
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-medium">Model Name</label>
                      <p className="text-xs text-muted-foreground">The remote model identifier sent in the `model` field, such as `doubao-seed-1-6`.</p>
                      <Input value={modelName} onChange={(e) => setModelName(e.target.value)} placeholder="doubao-seed-1-6" />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-medium">AK</label>
                      <p className="text-xs text-muted-foreground">
                        {isEditingModel
                          ? 'Optional during edit. Leave empty to keep the current API key.'
                          : 'The API key or access key used to authenticate requests to this endpoint.'}
                      </p>
                      <Input value={modelApiKey} onChange={(e) => setModelApiKey(e.target.value)} placeholder="Input API key" type="password" />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Description</label>
                    <p className="text-xs text-muted-foreground">Optional note for humans. Use it to explain purpose, owner, region, quota, or intended binding.</p>
                    <Textarea
                      value={modelDesc}
                      onChange={(e) => setModelDesc(e.target.value)}
                      placeholder="Example: Primary production LLM for planning and task scoring."
                    />
                  </div>
                  <div className="flex gap-2 justify-end">
                    <Button type="submit">{isEditingModel ? 'Save Changes' : 'Register Model'}</Button>
                    {isEditingModel && (
                      <Button type="button" variant="outline" onClick={() => resetModelForm()}>Cancel</Button>
                    )}
                  </div>
                </form>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <p className="text-xs font-semibold uppercase tracking-wider text-primary mb-1">Routing</p>
                <CardTitle>Binding Points</CardTitle>
                <CardDescription>Map each runtime call site to one registered model.</CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={(event) => void saveModelBindings(event)} className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {bindingPoints.map((bindingPoint) => {
                      const availableModels = registeredModels.filter((model) => model.model_type === bindingPoint.model_type)
                      return (
                        <div key={bindingPoint.binding_point} className="border rounded-lg p-4 bg-gradient-to-b from-primary/5 to-muted/30">
                          <div className="flex items-center justify-between mb-2">
                            <span className="font-semibold text-sm">{bindingPoint.label}</span>
                            <code className="text-xs bg-muted px-1.5 py-0.5 rounded">{bindingPoint.model_type}</code>
                          </div>
                          <p className="text-xs text-muted-foreground mb-3">{bindingPoint.description}</p>
                          <Select
                            value={modelBindings[bindingPoint.binding_point] || '__default__'}
                            onValueChange={(nextModelId) => {
                              const value = nextModelId === '__default__' ? '' : nextModelId
                              setModelBindings((current) => ({ ...current, [bindingPoint.binding_point]: value }))
                            }}
                          >
                            <SelectTrigger>
                              <SelectValue placeholder="Use default registered LLM" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="__default__">Use default registered LLM</SelectItem>
                              {availableModels.map((model) => (
                                <SelectItem key={model.id} value={model.id}>
                                  {model.model_name} · {model.api_key_preview}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      )
                    })}
                  </div>
                  <div className="flex justify-end">
                    <Button type="submit">Save Bindings</Button>
                  </div>
                </form>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Control Tab */}
        {activeTab === 'control' && directive && (
          <Card>
            <CardContent className="pt-6">
              <form onSubmit={(event) => void saveDirective(event)} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Status</label>
                    <Select name="paused" defaultValue={directive.paused ? 'true' : 'false'}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="false">Running</SelectItem>
                        <SelectItem value="true">Paused</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Poll Interval (seconds)</label>
                    <Input name="poll_interval_seconds" type="number" min={10} defaultValue={directive.poll_interval_seconds} />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Max File Changes</label>
                    <Input name="max_file_changes_per_task" type="number" min={1} defaultValue={directive.max_file_changes_per_task} />
                  </div>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Focus Areas</label>
                  <Input name="focus_areas" defaultValue={directive.focus_areas.join(', ')} />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Forbidden Paths</label>
                  <Input name="forbidden_paths" defaultValue={directive.forbidden_paths.join(', ')} />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Custom Instructions</label>
                  <Textarea name="custom_instructions" defaultValue={directive.custom_instructions} />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Task Sources (JSON)</label>
                  <Textarea value={sourcesJson} onChange={(e) => setSourcesJson(e.target.value)} rows={8} className="font-mono text-xs" />
                </div>
                <div className="flex justify-end">
                  <Button type="submit">Save Directive</Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        {/* Inject Tab */}
        {activeTab === 'inject' && (
          <Card>
            <CardContent className="pt-6">
              <form onSubmit={(event) => void injectTask(event)} className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Title</label>
                  <Input value={injectTitle} onChange={(e) => setInjectTitle(e.target.value)} placeholder="Task title" />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Description</label>
                  <Textarea value={injectDescription} onChange={(e) => setInjectDescription(e.target.value)} placeholder="What should the agent do?" />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Priority (1 = highest, 5 = lowest)</label>
                  <Input
                    type="number"
                    min={1}
                    max={5}
                    value={injectPriority}
                    onChange={(e) => setInjectPriority(Number(e.target.value) || 2)}
                  />
                </div>
                <div className="flex justify-end">
                  <Button type="submit">Inject Task</Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}
      </main>

      {/* Audit Detail Dialog */}
      <Dialog open={!!auditDetail} onOpenChange={() => setAuditDetail(null)}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>Audit Entry #{auditDetail?.seq}</DialogTitle>
            <DialogDescription>
              Model: {auditDetail?.model} · {auditDetail?.duration_ms ? `${(auditDetail.duration_ms / 1000).toFixed(1)}s` : '-'}
            </DialogDescription>
          </DialogHeader>
          {auditDetail && (
            <pre className="bg-muted p-4 rounded-md text-xs overflow-auto">{JSON.stringify(auditDetail, null, 2)}</pre>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default DashboardRoot
