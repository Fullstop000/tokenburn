import { useCallback, useEffect, useState } from 'react'

import { dashboardApiClient } from '../api/dashboardApi'
import type { ControlPanel, DashboardPage } from '../lib/dashboardView'
import type {
  DirectivePayload,
  ModelBindingPointEntry,
  RegisteredModelEntry,
} from '../types/dashboard'

interface UseControlPageStateArgs {
  directive: DirectivePayload | null
  navigateToPage: (page: DashboardPage) => void
  onRefreshHelpCenter: () => Promise<void>
  onRefreshSummary: () => Promise<void>
  friendlyLoadError: (scope: string, error: unknown) => string
  setControlPanel: (panel: ControlPanel) => void
  showToast: (message: string, ok?: boolean) => void
}

export function useControlPageState({
  directive,
  friendlyLoadError,
  navigateToPage,
  onRefreshHelpCenter,
  onRefreshSummary,
  setControlPanel,
  showToast,
}: UseControlPageStateArgs) {
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
  const [modelRoocodeWrapper, setModelRoocodeWrapper] = useState(false)
  const [editingModelId, setEditingModelId] = useState('')
  const [deletingModelId, setDeletingModelId] = useState('')
  const [resolvingTaskId, setResolvingTaskId] = useState('')
  const [modelError, setModelError] = useState('')

  useEffect(() => {
    setSourcesJson(JSON.stringify(directive?.task_sources ?? {}, null, 2))
  }, [directive])

  const resetModelForm = useCallback((): void => {
    setEditingModelId('')
    setModelType('llm')
    setModelBaseUrl('')
    setModelApiPath('')
    setModelName('')
    setModelApiKey('')
    setModelDesc('')
    setModelRoocodeWrapper(false)
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
      setModelError('')
    } catch (error) {
      setModelError(friendlyLoadError('Model registry', error))
      throw error
    }
  }, [friendlyLoadError])

  const startEditingModel = useCallback((model: RegisteredModelEntry): void => {
    setEditingModelId(model.id)
    setModelType(model.model_type)
    setModelBaseUrl(model.base_url ?? '')
    setModelApiPath(model.api_path ?? '')
    setModelName(model.model_name)
    setModelApiKey('')
    setModelDesc(model.desc ?? '')
    setModelRoocodeWrapper(model.roocode_wrapper ?? false)
    setControlPanel('models')
    navigateToPage('control')
  }, [navigateToPage, setControlPanel])

  const resolveHelpRequest = useCallback(async (taskId: string): Promise<void> => {
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
      await Promise.all([onRefreshSummary(), onRefreshHelpCenter()])
    } catch (error) {
      showToast(`Resolve failed: ${String(error)}`, false)
    } finally {
      setResolvingTaskId('')
    }
  }, [onRefreshHelpCenter, onRefreshSummary, resolvingTaskId, showToast])

  const saveDirective = useCallback(async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
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
      await onRefreshSummary()
    } catch (error) {
      showToast(`Save directive failed: ${String(error)}`, false)
    }
  }, [directive, onRefreshSummary, showToast, sourcesJson])

  const injectTask = useCallback(async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
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
      await onRefreshSummary()
    } catch (error) {
      showToast(`Inject task failed: ${String(error)}`, false)
    }
  }, [injectDescription, injectPriority, injectTitle, onRefreshSummary, showToast])

  const registerModel = useCallback(async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
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
        roocode_wrapper: modelRoocodeWrapper,
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
      await Promise.all([refreshModels(), onRefreshSummary()])
    } catch (error) {
      showToast(`${editingModelId ? 'Update' : 'Register'} model failed: ${String(error)}`, false)
    }
  }, [
    editingModelId,
    modelApiKey,
    modelApiPath,
    modelBaseUrl,
    modelDesc,
    modelName,
    modelRoocodeWrapper,
    modelType,
    onRefreshSummary,
    refreshModels,
    resetModelForm,
    showToast,
  ])

  const deleteModel = useCallback(async (model: RegisteredModelEntry): Promise<void> => {
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
      await Promise.all([refreshModels(), onRefreshSummary()])
    } catch (error) {
      showToast(`Delete model failed: ${String(error)}`, false)
    } finally {
      setDeletingModelId('')
    }
  }, [deletingModelId, editingModelId, onRefreshSummary, refreshModels, resetModelForm, showToast])

  const saveModelBindings = useCallback(async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    try {
      const payload = await dashboardApiClient.saveModelBindings({ bindings: modelBindings })
      if (payload.error) {
        showToast(payload.error, false)
        return
      }
      showToast('Model bindings saved')
      await Promise.all([refreshModels(), onRefreshSummary()])
    } catch (error) {
      showToast(`Save model bindings failed: ${String(error)}`, false)
    }
  }, [modelBindings, onRefreshSummary, refreshModels, showToast])

  return {
    bindingPoints,
    deleteModel,
    deletingModelId,
    editingModelId,
    injectDescription,
    injectPriority,
    injectTask,
    injectTitle,
    modelApiKey,
    modelApiPath,
    modelBaseUrl,
    modelBindings,
    modelError,
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
  }
}
