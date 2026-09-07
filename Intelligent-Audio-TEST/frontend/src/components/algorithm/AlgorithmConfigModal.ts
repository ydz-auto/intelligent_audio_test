import { ref, reactive, computed, watch } from 'vue'
import { useDimensions } from '../../composables/shared/useDimensions'
import { useAlgorithmConfig } from '../../composables/algorithm/useAlgorithmConfig'
import { PARAM_CODE_PRESETS, FEATURE_BUNDLES, NEW_GROUP_SENTINEL } from './algorithmConstants'
import { normalizeParamFields, normalizeCaseParamFields } from './algorithmParamHelpers'
import { useAlgorithmParamOps } from './useAlgorithmParamOps'
import { useAlgorithmDimensionOps } from './useAlgorithmDimensionOps'
import { useAlgorithmMappingOps } from './useAlgorithmMappingOps'
import { useAlgorithmFeatureBundles } from './useAlgorithmFeatureBundles'
import { useAlgorithmCrudOps, normalizeMappings } from './useAlgorithmCrudOps'
import type { AlgorithmGroup, Dimension, AlgorithmDefinition } from '@/domain'
import { TaskStatus, ApiEndpointStatus, ApiEndpointStatusType } from '@/domain/enums'

// 组件级 Modal 契约：可见性 / 模式 / 编辑数据
export interface ModalProps {
  visible: boolean
  mode?: 'list' | 'create' | 'edit' | 'select'
  editData?: AlgorithmDefinition | null
}

export function useAlgorithmConfigModal(props: ModalProps, emit: any) {
  // props.mode 为可选（ModalProps.mode?: ...），兜底为 'list'，避免 undefined 流入内部状态
  const internalMode = ref<'list' | 'create' | 'edit' | 'select'>(props.mode ?? 'list')

  watch(() => props.mode, (newMode) => {
    internalMode.value = newMode ?? 'list'
  })

  const effectiveMode = computed(() => internalMode.value)

  const { clearFormSchemaCache } = useAlgorithmConfig()

  const formTabs = [
    { key: 'basic', label: '基本信息' },
    { key: 'params', label: '参数配置' },
    { key: 'reference', label: '参考参数' },
    { key: 'mappings', label: '参数映射' },
    { key: 'dimensions', label: '关联维度' }
  ]

  const modalWidth = computed(() => {
    if (effectiveMode.value === 'list') return '700px'
    return '1200px'
  })

  const title = computed(() => {
    const titles = {
      list: '算法配置管理',
      create: '新建算法',
      edit: '编辑算法',
      select: '选择算法'
    }
    return titles[effectiveMode.value]
  })

  const okText = computed(() => {
    if (effectiveMode.value === 'select') return '选择'
    return '确定'
  })

  const cancelText = computed(() => '取消')

  const searchKeyword = ref('')
  const activeTab = ref('basic')
  const paramConfigType = ref<'device' | 'api' | 'case'>('device')

  const algorithms = ref<AlgorithmDefinition[]>([])
  const groups = ref<AlgorithmGroup[]>([])
  const availableDimensions = ref<Dimension[]>([])

  const { fetchAllDimensions } = useDimensions()

  // 不再按 dimensionType 过滤，返回全部维度
  const mainDimensions = computed(() => availableDimensions.value)

  const formState = reactive({
    type: '',
    name: '',
    groupId: null as number | null,
    description: '',
    status: ApiEndpointStatus.ONLINE,
    statusSwitch: true,
    icon: '',
    displayOrder: 0,
    deviceParams: [] as any[],
    apiParams: [] as any[],
    caseParams: [] as any[],
    mappings: {
      device: [] as any[],
      api: [] as any[],
      evaluation: [] as any[]
    },
    associatedDimensions: [] as { dimensionId: number | null; weight: number; isDefault: boolean }[],
    // 参考参数条目含后端 id 与前端新增行的临时 tempId（供列表 :key 使用）
    referenceParams: [] as { id?: number; tempId?: string; code: string; name: string; type: string; annotationCode: string; annotationFormat: string; fieldPath: string; mergeMode: string; helpText: string }[]
  })

  // 新建分组支持：选择「+ 新建分组」后展示输入框，保存算法时先创建分组再回填 groupId
  const newGroupName = ref('')
  const creatingNewGroup = ref(false)

  const groupSelectValue = computed<number | string | null>({
    get: () => (creatingNewGroup.value ? NEW_GROUP_SENTINEL : formState.groupId),
    set: (val) => {
      if (val === NEW_GROUP_SENTINEL) {
        creatingNewGroup.value = true
        newGroupName.value = ''
      } else {
        creatingNewGroup.value = false
        formState.groupId = val === null ? null : (Number(val) as number | null)
      }
    }
  })

  const currentParams = computed(() => {
    if (paramConfigType.value === 'device') {
      return formState.deviceParams
    } else if (paramConfigType.value === 'api') {
      return formState.apiParams
    }
    return []
  })

  const availableParams = computed(() => {
    const params = paramConfigType.value === 'device' ? formState.deviceParams : formState.apiParams
    return params
      .filter(param => param.paramCode && !param.hidden)
      .map(param => ({
        code: param.paramCode,
        name: param.paramName || param.paramCode,
        direction: param.direction
      }))
  })

  const caseParams = computed(() => {
    return (formState.caseParams || [])
      .filter(param => param.paramCode && !param.hidden)
      .map(param => ({
        code: param.paramCode,
        name: param.paramName || param.paramCode,
        direction: param.direction
      }))
  })

  const referenceParams = computed(() => {
    return (formState.referenceParams || [])
      .filter(param => param.code)
      .map(param => ({
        code: param.code,
        name: param.name || param.code,
        direction: 'reference'
      }))
  })

  const deviceParams = computed(() => {
    return (formState.deviceParams || [])
      .filter(param => param.paramCode && !param.hidden)
      .map(param => ({
        code: param.paramCode,
        name: param.paramName || param.paramCode,
        direction: param.direction
      }))
  })

  const deviceOutputParams = computed(() => {
    const existingCodes = new Set(deviceParams.value.map(p => p.code))
    return (formState.deviceParams || [])
      .filter(param => param.paramCode && !param.hidden && param.direction === 'output' && !existingCodes.has(param.paramCode))
      .map(param => ({
        code: param.paramCode,
        name: param.paramName || param.paramCode,
        direction: 'output'
      }))
  })

  const apiParams = computed(() => {
    return (formState.apiParams || [])
      .filter(param => param.paramCode && !param.hidden)
      .map(param => ({
        code: param.paramCode,
        name: param.paramName || param.paramCode,
        direction: param.direction
      }))
  })

  const apiOutputParams = computed(() => {
    const existingCodes = new Set(apiParams.value.map(p => p.code))
    return (formState.apiParams || [])
      .filter(param => param.paramCode && !param.hidden && param.direction === 'output' && !existingCodes.has(param.paramCode))
      .map(param => ({
        code: param.paramCode,
        name: param.paramName || param.paramCode,
        direction: 'output'
      }))
  })

  const filteredAlgorithms = computed(() => {
    if (!searchKeyword.value) return algorithms.value
    return algorithms.value.filter(a =>
      a.type.includes(searchKeyword.value) ||
      a.name.includes(searchKeyword.value)
    )
  })

  function getGroupTagClass(groupName: string | undefined): string {
    if (!groupName) return ''
    const classes: Record<string, string> = {
      '翻译': TaskStatus.PENDING,
      '语音识别': TaskStatus.COMPLETED,
      '声纹识别': 'in-progress',
      '语音合成': TaskStatus.FAILED
    }
    return classes[groupName] || ''
  }

  watch(() => props.visible, (visible) => {
    if (visible) {
      if (effectiveMode.value === 'list') {
        loadAlgorithms()
      } else if (effectiveMode.value === 'create') {
        resetForm()
      }
      loadGroups()
      loadDimensions()
    }
  })

  watch(() => [props.mode, props.editData] as const, ([mode, editData]) => {
    if (mode === 'edit' && editData) {
      // algorithmApi 已返回 camelCase Domain 字段
      const data = editData as AlgorithmDefinition
      const deviceParams = (data.deviceParams || []).map(normalizeParamFields).map((p: any) => ({ ...p }))
      const apiParams = (data.apiParams || []).map(normalizeParamFields).map((p: any) => ({ ...p }))
      const caseParams = (data.caseParams || []).map(normalizeCaseParamFields).map((p: any) => ({ ...p }))
      const refConfig = data.referenceParams

      Object.assign(formState, {
        type: data.type,
        name: data.name,
        groupId: data.groupId ?? null,
        description: data.description || '',
        status: data.status as ApiEndpointStatusType,
        statusSwitch: data.status === ApiEndpointStatus.ONLINE,
        icon: data.icon || '',
        displayOrder: data.displayOrder || 0,
        deviceParams: deviceParams,
        apiParams: apiParams,
        caseParams: caseParams,
        params: data.params || [],
        mappings: normalizeMappings(data.mappings),
        associatedDimensions: (data.associatedDimensions || []).map((d: any) => ({
          dimensionId: d.dimensionId,
          weight: d.weight ?? 1.0,
          isDefault: d.isDefault ?? false
        })),
        referenceParams: (refConfig || []).map((p: any) => ({
          id: p.id,
          code: p.code || '',
          name: p.name || '',
          type: p.type || 'text',
          annotationCode: p.annotationCode || p.code || '',
          annotationFormat: p.annotationFormat || '',
          fieldPath: p.fieldPath || '',
          mergeMode: p.mergeMode || 'join',
          helpText: p.helpText || ''
        }))
      })
    } else if (mode === 'create') {
      resetForm()
    }
  }, { immediate: true })

  // Param ID counter shared by param ops and dimension ops
  const paramIdCounter = { value: 0 }

  // Parameter operations (add/remove/autosave)
  const {
    handleAddParam,
    handleRemoveCaseParam,
    handleAddReferenceParam,
    handleRemoveReferenceParam,
    handleCaseParamTypeChange,
    handleParamBlur,
    handleParamCodeSelect,
    handleCaseParamBlur,
    autoSaveCaseParams,
    handleReferenceParamBlur,
    savePendingReferenceParams,
    handleRemoveParam,
  } = useAlgorithmParamOps(formState, paramConfigType, effectiveMode, paramIdCounter)

  // Mapping operations
  const {
    mappingExpanded,
    updateMappings,
    toggleMapping,
  } = useAlgorithmMappingOps(formState)

  // Dimension operations
  const {
    handleAddDimension,
    handleRemoveDimension,
    handleDimensionChange,
    handleDimensionBlur,
  } = useAlgorithmDimensionOps(formState, effectiveMode, paramIdCounter)

  // Feature bundles (toggle/save case params by bundle)
  const {
    isBundleActive,
    toggleBundle,
  } = useAlgorithmFeatureBundles(formState, clearFormSchemaCache, autoSaveCaseParams)

  // Algorithm CRUD operations
  const {
    loadAlgorithms,
    loadGroups,
    loadDimensions,
    resetForm,
    handleCancel,
    handleOk,
    handleCreate,
    handleEdit,
    handleSelect,
    handleToggleStatus,
    confirmDelete,
    handleSearch,
  } = useAlgorithmCrudOps(
    props,
    emit,
    formState,
    effectiveMode,
    internalMode,
    algorithms,
    groups,
    availableDimensions,
    fetchAllDimensions,
    clearFormSchemaCache,
    savePendingReferenceParams,
    creatingNewGroup,
    newGroupName,
    activeTab,
    paramConfigType
  )

  return {
    PARAM_CODE_PRESETS,
    FEATURE_BUNDLES,
    title,
    modalWidth,
    effectiveMode,
    okText,
    cancelText,
    handleCancel,
    handleOk,
    handleCreate,
    searchKeyword,
    handleSearch,
    filteredAlgorithms,
    getGroupTagClass,
    handleEdit,
    handleToggleStatus,
    handleSelect,
    confirmDelete,
    formTabs,
    activeTab,
    formState,
    groupSelectValue,
    groups,
    NEW_GROUP_SENTINEL,
    creatingNewGroup,
    newGroupName,
    paramConfigType,
    isBundleActive,
    toggleBundle,
    currentParams,
    handleParamBlur,
    handleCaseParamBlur,
    handleCaseParamTypeChange,
    handleRemoveParam,
    handleParamCodeSelect,
    handleRemoveCaseParam,
    handleAddParam,
    handleAddReferenceParam,
    handleReferenceParamBlur,
    handleRemoveReferenceParam,
    caseParams,
    referenceParams,
    deviceParams,
    deviceOutputParams,
    apiParams,
    apiOutputParams,
    mappingExpanded,
    toggleMapping,
    updateMappings,
    mainDimensions,
    availableDimensions,
    handleAddDimension,
    handleDimensionBlur,
    handleDimensionChange,
    handleRemoveDimension,
  }
}
