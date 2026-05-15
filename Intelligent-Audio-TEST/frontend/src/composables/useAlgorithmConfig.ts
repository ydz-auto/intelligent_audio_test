// -*- coding: utf-8 -*-
/**
 * 算法配置 Composables
 *
 * 提供算法相关的状态管理和 API 调用
 */

import { ref, computed, onMounted } from 'vue'
import { algorithmApi } from '../utils/api'

// 简单的消息提示函数，替代 Ant Design message
function showMessage(type: 'error' | 'success' | 'info' | 'warning', content: string) {
  // 创建消息元素
  const message = document.createElement('div')
  message.className = `custom-message custom-message-${type}`
  message.textContent = content
  message.style.position = 'fixed'
  message.style.top = '20px'
  message.style.right = '20px'
  message.style.padding = '12px 20px'
  message.style.borderRadius = '4px'
  message.style.color = '#fff'
  message.style.zIndex = '9999'
  message.style.fontSize = '14px'
  message.style.boxShadow = '0 2px 8px rgba(0, 0, 0, 0.15)'
  message.style.transition = 'all 0.3s ease'
  message.style.opacity = '0'
  message.style.transform = 'translateX(100%)'

  // 设置不同类型的背景色
  switch (type) {
    case 'success':
      message.style.backgroundColor = '#52c41a'
      break
    case 'error':
      message.style.backgroundColor = '#ff4d4f'
      break
    case 'info':
      message.style.backgroundColor = '#1890ff'
      break
    case 'warning':
      message.style.backgroundColor = '#faad14'
      break
  }

  // 添加到页面
  document.body.appendChild(message)

  // 显示动画
  setTimeout(() => {
    message.style.opacity = '1'
    message.style.transform = 'translateX(0)'
  }, 10)

  // 3秒后移除
  setTimeout(() => {
    message.style.opacity = '0'
    message.style.transform = 'translateX(100%)'
    setTimeout(() => {
      if (message.parentNode) {
        message.parentNode.removeChild(message)
      }
    }, 300)
  }, 3000)
}

const message = {
  error: (content: string) => showMessage('error', content),
  success: (content: string) => showMessage('success', content),
  info: (content: string) => showMessage('info', content),
  warning: (content: string) => showMessage('warning', content)
}

export interface AlgorithmDefinition {
  type: string
  name: string
  group_id?: number
  group_name?: string
  description?: string
  status: string
  icon?: string
  display_order: number
  params?: AlgorithmParam[]
  mappings?: {
    device: ParamMapping[]
    api: ParamMapping[]
    evaluation: ParamMapping[]
  }
}

export interface AlgorithmParam {
  id: number
  algorithm_type: string
  param_code: string
  param_name?: string
  param_type: string
  required: boolean
  default_value?: string
  options_source?: string
  options_field?: string
  options_label_field?: string
  validation_rules?: string
  help_text?: string
  component?: string
  ui_order: number
  ui_group: string
  hidden: boolean
}

export interface ParamMapping {
  source_param: string
  target_key: string
  transform_type: 'none' | 'uppercase' | 'lowercase' | 'json_parse'
}

export interface FormSchema {
  algorithmType: string
  algorithmName: string
  group_id?: number
  group_name?: string
  description?: string
  groups: {
    name: string
    label: string
    fields: FormField[]
  }[]
  fields: FormField[]
}

export interface FormField {
  fieldCode: string
  fieldName: string
  fieldType: string
  required: boolean
  defaultValue?: any
  component?: string
  options?: { value: string; label: string }[]
  validation?: string
  helpText?: string
  hidden: boolean
  uiOrder: number
  uiGroup: string
}

const algorithms = ref<AlgorithmDefinition[]>([])
const loading = ref(false)
const selectedAlgorithm = ref<AlgorithmDefinition | null>(null)
const formSchemas = ref<Map<string, FormSchema>>(new Map())

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

export async function loadAlgorithmDetail(algorithmType: string): Promise<any> {
  try {
    const result = await algorithmApi.getDefinition(algorithmType)
    return result
  } catch (error) {
    console.error('加载算法详情失败:', error)
    return null
  }
}

export function useAlgorithmConfig() {
  async function loadAlgorithms(): Promise<AlgorithmDefinition[]> {
    loading.value = true
    try {
      const response = await fetch('/api/v1/algorithm/definitions')
      const result = await response.json()
      if (result.success) {
        algorithms.value = result.data.data || []
        return algorithms.value
      }
      message.error(result.message || '加载算法列表失败')
      return []
    } catch (error) {
      message.error('加载算法列表失败')
      return []
    } finally {
      loading.value = false
    }
  }

  async function getAlgorithm(algorithmType: string): Promise<AlgorithmDefinition | null> {
    try {
      const response = await fetch(`/api/v1/algorithm/definitions/${algorithmType}`)
      const result = await response.json()
      if (result.success) {
        return result.data
      }
      return null
    } catch (error) {
      message.error('获取算法详情失败')
      return null
    }
  }

  async function getAlgorithmOptions(): Promise<{ value: string; name: string; group_id?: number; group_name?: string }[]> {
    try {
      const response = await fetch('/api/v1/algorithm/options')
      const result = await response.json()
      if (result.success) {
        return result.data.algorithms || []
      }
      return []
    } catch (error) {
      message.error('获取算法选项失败')
      return []
    }
  }

  async function getFormSchema(algorithmType: string): Promise<FormSchema | null> {
    if (formSchemas.value.has(algorithmType)) {
      return formSchemas.value.get(algorithmType) || null
    }

    try {
      const response = await fetch(`/api/v1/algorithm/form-schema/${algorithmType}`)
      const result = await response.json()
      if (result.success && result.data) {
        const schema = result.data as FormSchema
        formSchemas.value.set(algorithmType, schema)
        return schema
      }
      return null
    } catch (error) {
      message.error('获取表单Schema失败')
      return null
    }
  }

  async function getParamOptions(algorithmType: string): Promise<Record<string, { value: string; label: string }[]>> {
    try {
      const response = await fetch(`/api/v1/algorithm/params/${algorithmType}/options`)
      const result = await response.json()
      if (result.success) {
        return result.data.options || {}
      }
      return {}
    } catch (error) {
      return {}
    }
  }

  async function getAssociatedDimensions(algorithmType: string): Promise<{
    dimensions: Array<{ id: number; name: string; description?: string; type?: string; weight: number; is_default: boolean }>;
    dimension_ids: number[];
    default_dimension_id: number | null;
    weights: Record<number, number>;
  } | null> {
    try {
      const response = await fetch(`/api/v1/algorithm/dimensions/${algorithmType}`)
      const result = await response.json()
      if (result.success) {
        return result.data
      }
      return null
    } catch (error) {
      return null
    }
  }

  async function createAlgorithm(data: Partial<AlgorithmDefinition>): Promise<boolean> {
    try {
      const response = await fetch('/api/v1/algorithm/definitions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      })
      const result = await response.json()
      if (result.success) {
        message.success('创建成功')
        await loadAlgorithms()
        return true
      }
      message.error(result.message || '创建失败')
      return false
    } catch (error) {
      message.error('创建失败')
      return false
    }
  }

  async function updateAlgorithm(algorithmType: string, data: Partial<AlgorithmDefinition>): Promise<boolean> {
    try {
      const response = await fetch(`/api/v1/algorithm/definitions/${algorithmType}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      })
      const result = await response.json()
      if (result.success) {
        message.success('更新成功')
        await loadAlgorithms()
        return true
      }
      message.error(result.message || '更新失败')
      return false
    } catch (error) {
      message.error('更新失败')
      return false
    }
  }

  async function deleteAlgorithm(algorithmType: string): Promise<boolean> {
    try {
      const response = await fetch(`/api/v1/algorithm/definitions/${algorithmType}`, {
        method: 'DELETE'
      })
      const result = await response.json()
      if (result.success) {
        message.success('删除成功')
        await loadAlgorithms()
        return true
      }
      message.error(result.message || '删除失败')
      return false
    } catch (error) {
      message.error('删除失败')
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
    return algorithms.value.filter(a => a.group_id === groupId)
  }

  function clearFormSchemaCache() {
    formSchemas.value.clear()
  }

  return {
    algorithms: computed(() => algorithms.value),
    loading: computed(() => loading.value),
    selectedAlgorithm: computed(() => selectedAlgorithm.value),

    loadAlgorithms,
    getAlgorithm,
    getAlgorithmOptions,
    getFormSchema,
    getParamOptions,
    getAssociatedDimensions,
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
  const paramOptions = ref<Record<string, { value: string; label: string }[]>>({})
  const formData = ref<Record<string, any>>({})
  const loading = ref(false)

  async function loadSchema() {
    if (!algorithmType) {
      schema.value = null
      return
    }

    loading.value = true
    try {
      const [schemaData, optionsData] = await Promise.all([
        getFormSchema(algorithmType),
        getParamOptions(algorithmType)
      ])
      schema.value = schemaData
      paramOptions.value = optionsData
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
    paramOptions: computed(() => paramOptions.value),
    formData: computed(() => formData.value),
    loading: computed(() => loading.value),

    loadSchema,
    updateFormData,
    resetForm,
    getValues
  }
}
