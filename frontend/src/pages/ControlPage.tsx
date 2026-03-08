import type React from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
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
import { Textarea } from '@/components/ui/textarea'
import { StatusBadge } from '@/components/ui/status-badge'

import { formatDateTime, type ControlPanel } from '../lib/dashboardView'
import type {
  DirectivePayload,
  ModelBindingPointEntry,
  RegisteredModelEntry,
  TaskSummary,
} from '../types/dashboard'

const MODEL_CONNECTION_LABEL: Record<string, string> = {
  success: 'Success',
  fail: 'Fail',
}

interface ControlPageProps {
  activePanel: ControlPanel
  directive: DirectivePayload | null
  helpRequests: TaskSummary[]
  helpCount: number
  resolvingTaskId: string
  registeredModels: RegisteredModelEntry[]
  bindingPoints: ModelBindingPointEntry[]
  modelBindings: Record<string, string>
  sourcesJson: string
  modelType: 'llm' | 'embedding'
  modelBaseUrl: string
  modelApiPath: string
  modelName: string
  modelApiKey: string
  modelDesc: string
  modelRoocodeWrapper: boolean
  editingModelId: string
  deletingModelId: string
  injectTitle: string
  injectDescription: string
  injectPriority: number
  onChangePanel: (panel: ControlPanel) => void
  onResolveHelpRequest: (taskId: string) => void
  onSaveDirective: (event: React.FormEvent<HTMLFormElement>) => void
  onRegisterModel: (event: React.FormEvent<HTMLFormElement>) => void
  onDeleteModel: (model: RegisteredModelEntry) => void
  onStartEditingModel: (model: RegisteredModelEntry) => void
  onResetModelForm: () => void
  onSaveModelBindings: (event: React.FormEvent<HTMLFormElement>) => void
  onInjectTask: (event: React.FormEvent<HTMLFormElement>) => void
  setSourcesJson: (value: string) => void
  setModelType: (value: 'llm' | 'embedding') => void
  setModelBaseUrl: (value: string) => void
  setModelApiPath: (value: string) => void
  setModelName: (value: string) => void
  setModelApiKey: (value: string) => void
  setModelDesc: (value: string) => void
  setModelRoocodeWrapper: (value: boolean) => void
  setModelBindings: (updater: (current: Record<string, string>) => Record<string, string>) => void
  setInjectTitle: (value: string) => void
  setInjectDescription: (value: string) => void
  setInjectPriority: (value: number) => void
}

export function ControlPage(props: ControlPageProps) {
  const {
    activePanel,
    directive,
    helpRequests,
    helpCount,
    resolvingTaskId,
    registeredModels,
    bindingPoints,
    modelBindings,
    sourcesJson,
    modelType,
    modelBaseUrl,
    modelApiPath,
    modelName,
    modelApiKey,
    modelDesc,
    modelRoocodeWrapper,
    editingModelId,
    deletingModelId,
    injectTitle,
    injectDescription,
    injectPriority,
    onChangePanel,
    onResolveHelpRequest,
    onSaveDirective,
    onRegisterModel,
    onDeleteModel,
    onStartEditingModel,
    onResetModelForm,
    onSaveModelBindings,
    onInjectTask,
    setSourcesJson,
    setModelType,
    setModelBaseUrl,
    setModelApiPath,
    setModelName,
    setModelApiKey,
    setModelDesc,
    setModelRoocodeWrapper,
    setModelBindings,
    setInjectTitle,
    setInjectDescription,
    setInjectPriority,
  } = props

  const isEditingModel = Boolean(editingModelId)
  const isEmbeddingModel = modelType === 'embedding'
  const modelEndpointLabel = isEmbeddingModel ? 'API Path' : 'Base URL'
  const modelEndpointHint = isEmbeddingModel
    ? 'The full embedding endpoint path.'
    : 'The OpenAI-compatible API root for this provider.'

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant={activePanel === 'models' ? 'default' : 'outline'} onClick={() => onChangePanel('models')}>Models</Button>
        <Button size="sm" variant={activePanel === 'directive' ? 'default' : 'outline'} onClick={() => onChangePanel('directive')}>Directive</Button>
        <Button size="sm" variant={activePanel === 'help' ? 'default' : 'outline'} onClick={() => onChangePanel('help')}>Help Center {helpCount > 0 ? `(${helpCount})` : ''}</Button>
        <Button size="sm" variant={activePanel === 'inject' ? 'default' : 'outline'} onClick={() => onChangePanel('inject')}>Inject Task</Button>
      </div>

      {activePanel === 'models' && (
        <div className="space-y-4">
          <Card className="border-border/60 bg-card/70">
            <CardHeader>
              <CardTitle>Model Registry</CardTitle>
              <CardDescription>Reusable endpoints and secrets for runtime model routing.</CardDescription>
            </CardHeader>
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
                      <TableCell><code className="rounded bg-muted px-1.5 py-0.5 text-xs">{model.model_type}</code></TableCell>
                      <TableCell>
                        <div className="font-medium">{model.model_name}</div>
                        <div className="font-mono text-xs text-muted-foreground">{model.id}</div>
                        {model.connection_status && (
                          <div className="mt-1.5 flex items-center gap-2 text-xs">
                            <span className={`h-2 w-2 rounded-full ${model.connection_status === 'success' ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.5)]' : 'bg-red-500'}`} />
                            <span className={model.connection_status === 'success' ? 'font-semibold text-green-500' : 'font-semibold text-red-500'}>
                              {MODEL_CONNECTION_LABEL[model.connection_status] ?? model.connection_status}
                            </span>
                          </div>
                        )}
                        {model.connection_message && <div className="mt-1 text-xs text-muted-foreground">{model.connection_message}</div>}
                        {model.desc && <div className="mt-1.5 text-xs text-muted-foreground">{model.desc}</div>}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {model.model_type === 'embedding' ? model.api_path || '-' : model.base_url || '-'}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">{model.api_key_preview}</TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">{formatDateTime(model.created_at)}</TableCell>
                      <TableCell>
                        <div className="flex gap-2">
                          <Button size="sm" variant="outline" onClick={() => onStartEditingModel(model)}>Edit</Button>
                          <Button size="sm" variant="destructive" disabled={deletingModelId === model.id} onClick={() => onDeleteModel(model)}>
                            {deletingModelId === model.id ? 'Deleting...' : 'Delete'}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                  {registeredModels.length === 0 && (
                    <TableRow>
                      <TableCell className="py-8 text-center italic text-muted-foreground" colSpan={6}>No registered models yet</TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card className="border-border/60 bg-card/70">
            <CardHeader>
              <CardTitle>{isEditingModel ? 'Edit Model' : 'Register Model'}</CardTitle>
              <CardDescription>
                {isEditingModel ? 'Update one registered model. Leave AK empty to keep the current secret.' : 'Store reusable LLM base URLs or embedding API paths for dashboard binding.'}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form className="space-y-4" onSubmit={onRegisterModel}>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Model Type</label>
                    <Select value={modelType} onValueChange={(value: string) => setModelType(value as 'llm' | 'embedding')}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
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
                      onChange={(event) => isEmbeddingModel ? setModelApiPath(event.target.value) : setModelBaseUrl(event.target.value)}
                      placeholder={isEmbeddingModel ? 'https://.../embeddings' : 'https://example.com/v1'}
                      value={isEmbeddingModel ? modelApiPath : modelBaseUrl}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Model Name</label>
                    <Input onChange={(event) => setModelName(event.target.value)} placeholder="doubao-seed-1-6" value={modelName} />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium">AK</label>
                    <Input onChange={(event) => setModelApiKey(event.target.value)} placeholder="Input API key" type="password" value={modelApiKey} />
                  </div>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Description</label>
                  <Textarea onChange={(event) => setModelDesc(event.target.value)} value={modelDesc} />
                </div>
                <div className="flex items-center gap-3">
                  <input
                    checked={modelRoocodeWrapper}
                    className="h-4 w-4 cursor-pointer accent-primary"
                    id="roocode_wrapper"
                    onChange={(event) => setModelRoocodeWrapper(event.target.checked)}
                    type="checkbox"
                  />
                  <div>
                    <label className="cursor-pointer text-sm font-medium" htmlFor="roocode_wrapper">Enable Roo Code Wrapper</label>
                    <p className="text-xs text-muted-foreground">Inject Roo Code identity headers (HTTP-Referer, X-Title, User-Agent) into every request.</p>
                  </div>
                </div>
                <div className="flex justify-end gap-2">
                  <Button type="submit">{isEditingModel ? 'Save Changes' : 'Register Model'}</Button>
                  {isEditingModel && <Button onClick={onResetModelForm} type="button" variant="outline">Cancel</Button>}
                </div>
              </form>
            </CardContent>
          </Card>

          <Card className="border-border/60 bg-card/70">
            <CardHeader>
              <CardTitle>Model Bindings</CardTitle>
              <CardDescription>Map each runtime call site to one registered model.</CardDescription>
            </CardHeader>
            <CardContent>
              <form className="space-y-4" onSubmit={onSaveModelBindings}>
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {bindingPoints.map((bindingPoint) => {
                    const availableModels = registeredModels.filter((model) => model.model_type === bindingPoint.model_type)
                    return (
                      <div className="rounded-lg border border-border/60 bg-gradient-to-b from-primary/5 to-muted/30 p-4" key={bindingPoint.binding_point}>
                        <div className="mb-2 flex items-center justify-between">
                          <span className="text-sm font-semibold">{bindingPoint.label}</span>
                          <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{bindingPoint.model_type}</code>
                        </div>
                        <p className="mb-3 text-xs text-muted-foreground">{bindingPoint.description}</p>
                        <Select
                          onValueChange={(nextModelId: string) => {
                            const value = nextModelId === '__default__' ? '' : nextModelId
                            setModelBindings((current) => ({ ...current, [bindingPoint.binding_point]: value }))
                          }}
                          value={modelBindings[bindingPoint.binding_point] || '__default__'}
                        >
                          <SelectTrigger><SelectValue placeholder="Use default registered LLM" /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__default__">Use default registered LLM</SelectItem>
                            {availableModels.map((model) => (
                              <SelectItem key={model.id} value={model.id}>{model.model_name} · {model.api_key_preview}</SelectItem>
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

      {activePanel === 'directive' && directive && (
        <Card className="border-border/60 bg-card/70">
          <CardHeader>
            <CardTitle>Directive Editor</CardTitle>
            <CardDescription>Runtime control inputs and discovery/execution boundaries.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={onSaveDirective}>
              <div className="grid gap-4 md:grid-cols-3">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Status</label>
                  <Select defaultValue={directive.paused ? 'true' : 'false'} name="paused">
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="false">Running</SelectItem>
                      <SelectItem value="true">Paused</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Poll Interval (seconds)</label>
                  <Input defaultValue={directive.poll_interval_seconds} min={10} name="poll_interval_seconds" type="number" />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Max File Changes</label>
                  <Input defaultValue={directive.max_file_changes_per_task} min={1} name="max_file_changes_per_task" type="number" />
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Focus Areas</label>
                <Input defaultValue={directive.focus_areas.join(', ')} name="focus_areas" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Forbidden Paths</label>
                <Input defaultValue={directive.forbidden_paths.join(', ')} name="forbidden_paths" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Custom Instructions</label>
                <Textarea defaultValue={directive.custom_instructions} name="custom_instructions" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Task Sources (JSON)</label>
                <Textarea className="font-mono text-xs" onChange={(event) => setSourcesJson(event.target.value)} rows={8} value={sourcesJson} />
              </div>
              <div className="flex justify-end">
                <Button type="submit">Save Directive</Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {activePanel === 'help' && (
        <Card className="border-border/60 bg-card/70">
          <CardHeader>
            <CardTitle>Help Center</CardTitle>
            <CardDescription>Operator interventions required to unblock the agent.</CardDescription>
          </CardHeader>
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
                      <div className="font-mono text-xs text-muted-foreground">{task.id}</div>
                    </TableCell>
                    <TableCell>
                      <div className="max-w-[620px] whitespace-pre-wrap rounded bg-muted p-2 font-mono text-xs">
                        {task.human_help_request || 'No detail provided'}
                      </div>
                    </TableCell>
                    <TableCell><StatusBadge status={task.status} /></TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{formatDateTime(task.updated_at)}</TableCell>
                    <TableCell>
                      <Button disabled={resolvingTaskId === task.id} onClick={() => onResolveHelpRequest(task.id)} size="sm" variant="outline">
                        {resolvingTaskId === task.id ? 'Resolving...' : 'Resolve'}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {helpRequests.length === 0 && (
                  <TableRow>
                    <TableCell className="py-8 text-center italic text-muted-foreground" colSpan={5}>No unresolved human-help requests</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {activePanel === 'inject' && (
        <Card className="border-border/60 bg-card/70">
          <CardHeader>
            <CardTitle>Manual Input</CardTitle>
            <CardDescription>Create one explicit task for the scheduler to pick up.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={onInjectTask}>
              <div className="space-y-2">
                <label className="text-sm font-medium">Title</label>
                <Input onChange={(event) => setInjectTitle(event.target.value)} placeholder="Task title" value={injectTitle} />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Description</label>
                <Textarea onChange={(event) => setInjectDescription(event.target.value)} placeholder="What should the agent do?" value={injectDescription} />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Priority (1 = highest, 5 = lowest)</label>
                <Input
                  max={5}
                  min={1}
                  onChange={(event) => setInjectPriority(Number(event.target.value) || 2)}
                  type="number"
                  value={injectPriority}
                />
              </div>
              <div className="flex justify-end">
                <Button type="submit">Inject Task</Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
