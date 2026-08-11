import { ref, reactive, computed, watch } from 'vue'
import { useDimensions } from '../../composables/shared/useDimensions'
import { useAlgorithmConfig } from '../../composables/algorithm/useAlgorithmConfig'
import { PARAM_CODE_PRESETS, FEATURE_BUNDLES, NEW_GROUP_SENTINEL } from './algorithmConstants'
import { normalizeParamFields, normalizeCaseParamFields } from './algorithmParamHelpers'
import { useAlgorithmParamOps } from './useAlgorithmParamOps'
import { useAlgorithmDimensionOps } from './useAlgorithmDimensionOps'
import { useAlgorithmMappingOps } from './useAlgorithmMappingOps'
import { useAlgorithmFeatureBundles } from './useAlgorithmFeatureBundles'
import { useAlgorithmCrudOps } from './useAlgorithmCrudOps'
import type { AlgorithmGroup, Dimension, AlgorithmRecord, ModalProps } from './algorithmTypes'

// Re-export types so existing imports from './AlgorithmConfigModal' keep working
export type { AlgorithmRecord, ModalProps }

export function useAlgorithmConfigModal(props: ModalProps, emit: any) {
  const internalMode = ref<'list' | 'create' | 'edit' | 'select'>(props.mode)

  watch(() => props.mode, (newMode) => {
    internalMode.value = newMode
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

  const algorithms = ref<AlgorithmRecord[]>([])
  const groups = ref<AlgorithmGroup[]>([])
  const availableDimensions = ref<Dimension[]>([])

  const { fetchAllDimensions } = useDimensions()

  const mainDimensions = computed(() => {
    return availableDimensions.value.filter(d => d.dimensionType === 'main' || !d.dimensionType)
  })

  const formState = reactive({
    type: '',
    name: '',
    group_id: null as number | null,
    description: '',
    status: 'online' as 'online' | 'offline',
    statusSwitch: true,
    icon: '',
    display_order: 0,
    device_params: [] as any[],
    api_params: [] as any[],
    case_params: [] as any[],
    mappings: {
      device: [] as any[],
      api: [] as any[],
      evaluation: [] as any[]
    },
    associated_dimensions: [] as { dimension_id: number | null; weight: number; is_default: boolean }[],
    reference_params: [] as { code: string; name: string; type: string; annotation_code: string; annotation_format: string; field_path: string; merge_mode: string; help_text: string }[]
  })

  // 新建分组支持：选择「+ 新建分组」后展示输入框，保存算法时先创建分组再回填 group_id
  const newGroupName = ref('')
  const creatingNewGroup = ref(false)

  const groupSelectValue = computed<number | string | null>({
    get: () => (creatingNewGroup.value ? NEW_GROUP_SENTINEL : formState.group_id),
    set: (val) => {
      if (val === NEW_GROUP_SENTINEL) {
        creatingNewGroup.value = true
        newGroupName.value = ''
      } else {
        creatingNewGroup.value = false
        formState.group_id = val === null ? null : (Number(val) as number | null)
      }
    }
  })

  const currentParams = computed(() => {
    if (paramConfigType.value === 'device') {
      return formState.device_params
    } else if (paramConfigType.value === 'api') {
      return formState.api_params
    }
    return []
  })

  const availableParams = computed(() => {
    const params = paramConfigType.value === 'device' ? formState.device_params : formState.api_params
    return params
      .filter(param => param.param_code && !param.hidden)
      .map(param => ({
        code: param.param_code,
        name: param.param_name || param.param_code,
        direction: param.direction
      }))
  })

  const caseParams = computed(() => {
    return (formState.case_params || [])
      .filter(param => param.param_code && !param.hidden)
      .map(param => ({
        code: param.param_code,
        name: param.param_name || param.param_code,
        direction: param.direction
      }))
  })

  const referenceParams = computed(() => {
    return (formState.reference_params || [])
      .filter(param => param.code)
      .map(param => ({
        code: param.code,
        name: param.name || param.code,
        direction: 'reference'
      }))
  })

  const deviceParams = computed(() => {
    return (formState.device_params || [])
      .filter(param => param.param_code && !param.hidden)
      .map(param => ({
        code: param.param_code,
        name: param.param_name || param.param_code,
        direction: param.direction
      }))
  })

  const deviceOutputParams = computed(() => {
    const existingCodes = new Set(deviceParams.value.map(p => p.code))
    return (formState.device_params || [])
      .filter(param => param.param_code && !param.hidden && param.direction === 'output' && !existingCodes.has(param.param_code))
      .map(param => ({
        code: param.param_code,
        name: param.param_name || param.param_code,
        direction: 'output'
      }))
  })

  const apiParams = computed(() => {
    return (formState.api_params || [])
      .filter(param => param.param_code && !param.hidden)
      .map(param => ({
        code: param.param_code,
        name: param.param_name || param.param_code,
        direction: param.direction
      }))
  })

  const apiOutputParams = computed(() => {
    const existingCodes = new Set(apiParams.value.map(p => p.code))
    return (formState.api_params || [])
      .filter(param => param.param_code && !param.hidden && param.direction === 'output' && !existingCodes.has(param.param_code))
      .map(param => ({
        code: param.param_code,
        name: param.param_name || param.param_code,
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
      '翻译': 'pending',
      '语音识别': 'completed',
      '声纹识别': 'in-progress',
      '语音合成': 'failed'
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

  watch(() => [props.mode, props.editData], ([mode, editData]) => {
    console.log('watch mode:', mode, 'editData:', editData)
    if (mode === 'edit' && editData) {
      const deviceParams = ((editData.deviceParams ?? editData.device_params) || []).map(normalizeParamFields).map(p => ({ ...p }))
      const apiParams = ((editData.apiParams ?? editData.api_params) || []).map(normalizeParamFields).map(p => ({ ...p }))
      const caseParams = ((editData.caseParams ?? editData.case_params) || []).map(normalizeCaseParamFields).map(p => ({ ...p }))
      const refConfig = editData.reference_params ?? editData.referenceConfig ?? editData.reference_config ?? editData.referenceParams

      Object.assign(formState, {
        type: editData.type,
        name: editData.name,
        group_id: editData.groupId ?? editData.group_id ?? null,
        description: editData.description || '',
        status: editData.status as 'online' | 'offline',
        statusSwitch: editData.status === 'online',
        icon: editData.icon || '',
        display_order: (editData.displayOrder ?? editData.display_order) || 0,
        device_params: deviceParams,
        api_params: apiParams,
        case_params: caseParams,
        params: editData.params || [],
        mappings: JSON.parse(JSON.stringify(editData.mappings || { device: [], api: [], evaluation: [] })),
        associated_dimensions: ((editData.associatedDimensions ?? editData.associated_dimensions) || []).map((d: any) => ({
          dimension_id: d.dimensionId ?? d.dimension_id,
          weight: d.weight ?? 1.0,
          is_default: d.isDefault ?? d.is_default ?? false
        })),
        reference_params: (refConfig || []).map((p: any) => ({
          id: p.id,
          code: p.code || '',
          name: p.name || '',
          type: p.type || 'text',
          annotation_code: p.annotation_code || p.code || '',
          annotation_format: p.annotation_format || '',
          field_path: p.field_path || '',
          merge_mode: p.merge_mode || 'join',
          help_text: p.help_text || ''
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
