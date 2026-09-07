// -*- coding: utf-8 -*-
/**
 * 算法配置 Composables
 *
 * 提供算法相关的状态管理和 API 调用
 * Application 层只见 camelCase Domain 字段，snake_case 转换由 infrastructure 层负责
 */
import { ref, computed } from 'vue'
import { algorithmPort } from './algorithmPort'
import { useNotification } from '../modal/useNotification'
import type {
  AlgorithmDefinition,
  AlgorithmOption,
  AlgorithmDimensions,
  AlgorithmCaseParam,
  FormSchema,
} from '../../domain/model/algorithm'

const { error: notifyError, success: notifySuccess } = useNotification()

const algorithms = ref<AlgorithmDefinition[]>([])
const loading = ref(false)
const selectedAlgorithm = ref<AlgorithmDefinition | null>(null)
const formSchemas = ref<Map<string, FormSchema>>(new Map())
// 用例专属参数缓存，避免循环 watch 触发的重复请求
const caseParamCache = ref<Map<string, AlgorithmCaseParam[]>>(new Map())

export function getAlgorithmIcon(groupName?: string): string {
  const iconMap: Record<string, string> = {
    '翻译': 'fa-globe',
    '语音识别': 'fa-microphone',
    '声纹识别': 'fa-user',
    '语音合成': 'fa-volume-up',
    'asr': 'fa-microphone',
    'tts': 'fa-volume-up',
    'nlu': 'fa-brain',
    'speaker_recognition': 'fa-user',
    'speaker_verification': 'fa-check-circle',
    'speaker_identification': 'fa-search',
    'asr_eval': 'fa-chart-bar',
    'translation': 'fa-globe',
    'general': 'fa-cog'
  }
  return iconMap[groupName || ''] || iconMap['general'] || 'fa-cog'
}

export async function loadAlgorithmDetail(algorithmType: string): Promise<AlgorithmDefinition | null> {
  try {
    return await algorithmPort.getDefinition(algorithmType)
  } catch (error) {
    console.error('加载算法详情失败:', error)
    return null
  }
}

export function useAlgorithmConfig() {
  async function loadAlgorithms(): Promise<AlgorithmDefinition[]> {
    loading.value = true
    try {
      const result = await algorithmPort.getDefinitions()
      algorithms.value = result?.data ?? []
      return algorithms.value
    } catch (error) {
      notifyError('加载算法列表失败')
      return []
    } finally {
      loading.value = false
    }
  }

  async function getAlgorithm(algorithmType: string): Promise<AlgorithmDefinition | null> {
    try {
      return await algorithmPort.getDefinition(algorithmType)
    } catch (error) {
      notifyError('获取算法详情失败')
      return null
    }
  }

  async function getAlgorithmOptions(): Promise<AlgorithmOption[]> {
    try {
      const result = await algorithmPort.getOptions()
      return result?.algorithms ?? []
    } catch (error) {
      notifyError('获取算法选项失败')
      return []
    }
  }

  async function getFormSchema(algorithmType: string): Promise<FormSchema | null> {
    if (formSchemas.value.has(algorithmType)) {
      return formSchemas.value.get(algorithmType) || null
    }

    try {
      const schema = await algorithmPort.getFormSchema(algorithmType)
      if (schema) {
        formSchemas.value.set(algorithmType, schema)
        return schema
      }
      return null
    } catch (error) {
      notifyError('获取表单Schema失败')
      return null
    }
  }

  async function getAssociatedDimensions(algorithmType: string): Promise<AlgorithmDimensions | null> {
    try {
      return await algorithmPort.getDimensions(algorithmType)
    } catch (error) {
      return null
    }
  }

  async function createAlgorithm(data: Partial<AlgorithmDefinition>): Promise<boolean> {
    try {
      await algorithmPort.createDefinition(data)
      notifySuccess('创建成功')
      await loadAlgorithms()
      return true
    } catch (error) {
      notifyError('创建失败')
      return false
    }
  }

  async function updateAlgorithm(algorithmType: string, data: Partial<AlgorithmDefinition>): Promise<boolean> {
    try {
      await algorithmPort.updateDefinition(algorithmType, data)
      notifySuccess('更新成功')
      await loadAlgorithms()
      return true
    } catch (error) {
      notifyError('更新失败')
      return false
    }
  }

  async function deleteAlgorithm(algorithmType: string): Promise<boolean> {
    try {
      await algorithmPort.deleteDefinition(algorithmType)
      notifySuccess('删除成功')
      await loadAlgorithms()
      return true
    } catch (error) {
      notifyError('删除失败')
      return false
    }
  }

  function selectAlgorithm(algorithm: AlgorithmDefinition | null) {
    selectedAlgorithm.value = algorithm
  }

  function getAlgorithmByType(type: string): AlgorithmDefinition | undefined {
    return algorithms.value.find(a => a.type === type)
  }

  function getAlgorithmsByGroup(groupId: number): AlgorithmDefinition[] {
    return algorithms.value.filter(a => a.groupId === groupId)
  }

  async function getCaseAlgorithmParams(algorithmType: string): Promise<AlgorithmCaseParam[]> {
    if (!algorithmType) return []
    // 命中缓存直接返回，避免循环 watch 导致的重复请求
    if (caseParamCache.value.has(algorithmType)) {
      return caseParamCache.value.get(algorithmType) || []
    }
    try {
      const result = await algorithmPort.getCaseParams(algorithmType)
      const params = result?.parameters ?? []
      caseParamCache.value.set(algorithmType, params)
      return params
    } catch (error) {
      console.error('获取用例参数定义失败:', error)
      return []
    }
  }

  function clearFormSchemaCache() {
    formSchemas.value.clear()
    caseParamCache.value.clear()
  }

  return {
    algorithms: computed(() => algorithms.value),
    loading: computed(() => loading.value),
    selectedAlgorithm: computed(() => selectedAlgorithm.value),

    loadAlgorithms,
    getAlgorithm,
    getAlgorithmOptions,
    getFormSchema,
    getAssociatedDimensions,
    getCaseAlgorithmParams,
    createAlgorithm,
    updateAlgorithm,
    deleteAlgorithm,
    selectAlgorithm,
    getAlgorithmByType,
    getAlgorithmsByGroup,
    clearFormSchemaCache
  }
}

export function useAlgorithmForm(algorithmType: string | null) {
  const schema = ref<FormSchema | null>(null)
  const formData = ref<Record<string, any>>({})
  const loading = ref(false)

  async function loadSchema() {
    if (!algorithmType) {
      schema.value = null
      return
    }

    loading.value = true
    try {
      // getFormSchema 定义在 useAlgorithmConfig() 内部，此处通过调用一次获取（模块级函数会复用 formSchemas 缓存）
      const configApi = useAlgorithmConfig()
      const schemaData = await configApi.getFormSchema(algorithmType)
      schema.value = schemaData
    } finally {
      loading.value = false
    }
  }

  function updateFormData(key: string, value: any) {
    formData.value[key] = value
  }

  function resetForm() {
    formData.value = {}

    schema.value?.fields?.forEach(field => {
      if (field.defaultValue !== undefined && !field.hidden) {
        formData.value[field.fieldCode] = field.defaultValue
      }
    })
  }

  function getValues(): Record<string, any> {
    return { ...formData.value }
  }

  return {
    schema: computed(() => schema.value),
    formData: computed(() => formData.value),
    loading: computed(() => loading.value),

    loadSchema,
    updateFormData,
    resetForm,
    getValues
  }
}
