import type React from 'react'

import { ControlPage } from '../pages/ControlPage'
import { DiscoveryPage } from '../pages/DiscoveryPage'
import { InboxPage } from '../pages/InboxPage'
import { MemoryAuditPage } from '../pages/MemoryAuditPage'
import { OverviewPage } from '../pages/OverviewPage'
import { WorkPage } from '../pages/WorkPage'
import type { ControlPanel, DashboardPage, MemoryPanel, WorkPanel, ActivityEvent } from '../lib/dashboardView'
import type { CycleSummary, DashboardSummaryPayload, DirectivePayload, ExperienceEntry, LlmAuditEntry, ModelBindingPointEntry, RegisteredModelEntry, TaskDetail, TaskEvent, TaskSummary, ThreadDetail, ThreadSummary } from '../types/dashboard'

interface OverviewRouteProps {
  summary: DashboardSummaryPayload | null
  summaryError: string
  onRetrySummary: () => void
  onNavigate: (page: DashboardPage) => void
  onOpenTaskDetail: (taskId: string) => void
  onOpenThread: (threadId: string) => void
}

interface WorkRouteProps {
  workPanel: WorkPanel
  cycles: CycleSummary[]
  summaryError: string
  taskDetail: TaskDetail | null
  taskEvents: TaskEvent[]
  tasks: TaskSummary[]
  onChangeWorkPanel: (panel: WorkPanel) => void
  onOpenTaskDetail: (taskId: string) => void
  onRetrySummary: () => void
}

interface InboxRouteProps {
  threadsError: string
  threads: ThreadSummary[]
  threadDetail: ThreadDetail | null
  replyingThreadId: string
  creatingThread: boolean
  onSelectThread: (threadId: string) => void
  onReplyToThread: (threadId: string, body: string) => Promise<void>
  onCreateThread: (title: string, description: string) => Promise<void>
  onCloseThread: (threadId: string, reason: string) => Promise<void>
  onBulkCloseThreads: (threadIds: string[]) => Promise<void>
  onRefreshThreads: () => void
}

interface DiscoveryRouteProps {
  discovery: unknown
  discoveryError: string
  onRetryDiscovery: () => void
}

interface MemoryRouteProps {
  memoryPanel: MemoryPanel
  activity: ActivityEvent[]
  activityError: string
  activityGroupBy: 'time' | 'task'
  activityPhase: string
  audit: LlmAuditEntry[]
  auditError: string
  auditDetail: LlmAuditEntry | null
  collapsedTasks: Set<string>
  experiences: ExperienceEntry[]
  experiencesError: string
  tasks: TaskSummary[]
  onChangeActivityGroupBy: (groupBy: 'time' | 'task') => void
  onChangeActivityModule: (module: string) => void
  onChangeMemoryPanel: (panel: MemoryPanel) => void
  onCloseAuditDetail: () => void
  onOpenAuditDetail: (seq: number) => void
  onRefreshActivity: () => void
  onRefreshAudit: () => void
  onRefreshExperiences: () => void
  onToggleCollapsedTask: (taskId: string) => void
}

interface ControlRouteProps {
  controlPanel: ControlPanel
  directive: DirectivePayload | null
  summaryError: string
  helpError: string
  helpCount: number
  helpRequests: TaskSummary[]
  bindingPoints: ModelBindingPointEntry[]
  deletingModelId: string
  editingModelId: string
  settingDefaultModelId: string
  injectDescription: string
  injectPriority: number
  injectTitle: string
  modelApiKey: string
  modelApiPath: string
  modelBaseUrl: string
  modelBindings: Record<string, string>
  modelDesc: string
  modelError: string
  modelsLoading: boolean
  modelName: string
  modelRoocodeWrapper: boolean
  modelType: 'llm' | 'embedding'
  registeredModels: RegisteredModelEntry[]
  resolvingTaskId: string
  sourcesJson: string
  onChangeControlPanel: (panel: ControlPanel) => void
  onDeleteModel: (model: RegisteredModelEntry) => void
  onInjectTask: (event: React.FormEvent<HTMLFormElement>) => void
  onRegisterModel: (event: React.FormEvent<HTMLFormElement>) => void
  onResetModelForm: () => void
  onResolveHelpRequest: (taskId: string) => void
  onSaveDirective: (event: React.FormEvent<HTMLFormElement>) => void
  onSaveModelBindings: (event: React.FormEvent<HTMLFormElement>) => void
  onSetDefaultModel: (model: RegisteredModelEntry) => void
  onStartEditingModel: (model: RegisteredModelEntry) => void
  setInjectDescription: (value: string) => void
  setInjectPriority: (value: number) => void
  setInjectTitle: (value: string) => void
  setModelApiKey: (value: string) => void
  setModelApiPath: (value: string) => void
  setModelBaseUrl: (value: string) => void
  setModelBindings: (updater: (current: Record<string, string>) => Record<string, string>) => void
  setModelDesc: (value: string) => void
  setModelName: (value: string) => void
  setModelRoocodeWrapper: (value: boolean) => void
  setModelType: (value: 'llm' | 'embedding') => void
  setSourcesJson: (value: string) => void
}

interface DashboardRouterProps {
  activePage: DashboardPage
  overview: OverviewRouteProps
  work: WorkRouteProps
  inbox: InboxRouteProps
  discovery: DiscoveryRouteProps
  memory: MemoryRouteProps
  control: ControlRouteProps
}

export function DashboardRouter(props: DashboardRouterProps) {
  const { activePage, control, discovery, inbox, memory, overview, work } = props

  if (activePage === 'overview') {
    return (
      <OverviewPage
        errorMessage={overview.summaryError}
        onRetry={overview.onRetrySummary}
        onNavigate={overview.onNavigate}
        onOpenTaskDetail={overview.onOpenTaskDetail}
        onOpenThread={overview.onOpenThread}
        summary={overview.summary}
      />
    )
  }

  if (activePage === 'work') {
    return (
      <WorkPage
        activePanel={work.workPanel}
        cycles={work.cycles}
        errorMessage={work.summaryError}
        onChangePanel={work.onChangeWorkPanel}
        onOpenTaskDetail={work.onOpenTaskDetail}
        onRetry={work.onRetrySummary}
        taskDetail={work.taskDetail}
        taskEvents={work.taskEvents}
        tasks={work.tasks}
      />
    )
  }

  if (activePage === 'inbox') {
    return (
      <InboxPage
        creating={inbox.creatingThread}
        errorMessage={inbox.threadsError}
        onBulkClose={inbox.onBulkCloseThreads}
        onCloseThread={inbox.onCloseThread}
        onCreateThread={inbox.onCreateThread}
        onRefresh={inbox.onRefreshThreads}
        onReply={inbox.onReplyToThread}
        onSelectThread={inbox.onSelectThread}
        replying={Boolean(inbox.replyingThreadId)}
        threadDetail={inbox.threadDetail}
        threads={inbox.threads}
      />
    )
  }

  if (activePage === 'discovery') {
    return <DiscoveryPage discovery={discovery.discovery as never} errorMessage={discovery.discoveryError} onRetry={discovery.onRetryDiscovery} />
  }

  if (activePage === 'memory') {
    return (
      <MemoryAuditPage
        activePanel={memory.memoryPanel}
        activity={memory.activity}
        activityError={memory.activityError}
        activityGroupBy={memory.activityGroupBy}
        activityModule={memory.activityPhase}
        audit={memory.audit}
        auditDetail={memory.auditDetail}
        auditError={memory.auditError}
        collapsedTasks={memory.collapsedTasks}
        experienceError={memory.experiencesError}
        experiences={memory.experiences}
        onChangeActivityGroupBy={memory.onChangeActivityGroupBy}
        onChangeActivityModule={memory.onChangeActivityModule}
        onChangePanel={memory.onChangeMemoryPanel}
        onCloseAuditDetail={memory.onCloseAuditDetail}
        onOpenAuditDetail={memory.onOpenAuditDetail}
        onRefreshActivity={memory.onRefreshActivity}
        onRefreshAudit={memory.onRefreshAudit}
        onRefreshExperiences={memory.onRefreshExperiences}
        onToggleCollapsedTask={memory.onToggleCollapsedTask}
        tasks={memory.tasks}
      />
    )
  }

  return (
    <ControlPage
      activePanel={control.controlPanel}
      bindingPoints={control.bindingPoints}
      deletingModelId={control.deletingModelId}
      directive={control.directive}
      directiveError={control.summaryError}
      editingModelId={control.editingModelId}
      helpCount={control.helpCount}
      helpError={control.helpError}
      helpRequests={control.helpRequests}
      injectDescription={control.injectDescription}
      injectPriority={control.injectPriority}
      injectTitle={control.injectTitle}
      modelApiKey={control.modelApiKey}
      modelApiPath={control.modelApiPath}
      modelBaseUrl={control.modelBaseUrl}
      modelBindings={control.modelBindings}
      modelDesc={control.modelDesc}
      modelError={control.modelError}
      modelsLoading={control.modelsLoading}
      modelName={control.modelName}
      modelRoocodeWrapper={control.modelRoocodeWrapper}
      modelType={control.modelType}
      onChangePanel={control.onChangeControlPanel}
      onDeleteModel={control.onDeleteModel}
      onInjectTask={control.onInjectTask}
      onRegisterModel={control.onRegisterModel}
      onResetModelForm={control.onResetModelForm}
      onResolveHelpRequest={control.onResolveHelpRequest}
      onSaveDirective={control.onSaveDirective}
      onSaveModelBindings={control.onSaveModelBindings}
      onSetDefaultModel={control.onSetDefaultModel}
      onStartEditingModel={control.onStartEditingModel}
      registeredModels={control.registeredModels}
      resolvingTaskId={control.resolvingTaskId}
      settingDefaultModelId={control.settingDefaultModelId}
      setInjectDescription={control.setInjectDescription}
      setInjectPriority={control.setInjectPriority}
      setInjectTitle={control.setInjectTitle}
      setModelApiKey={control.setModelApiKey}
      setModelApiPath={control.setModelApiPath}
      setModelBaseUrl={control.setModelBaseUrl}
      setModelBindings={control.setModelBindings}
      setModelDesc={control.setModelDesc}
      setModelName={control.setModelName}
      setModelRoocodeWrapper={control.setModelRoocodeWrapper}
      setModelType={control.setModelType}
      setSourcesJson={control.setSourcesJson}
      sourcesJson={control.sourcesJson}
    />
  )
}
