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
import { TaskStatus, ApiEndpointStatus, ApiEndpointStatusType, TestType } from '@/domain/enums'

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

  // 参数配置页签搜索/过滤（纯前端行为，数据已在本地列表，不涉及重新请求）
  const paramSearchKeyword = ref('')
  const caseParamSearchKeyword = ref('')
  const paramDirectionFilter = ref('all')
  const paramRequiredFilter = ref('all')
  const caseParamTypeFilter = ref('all')
  const caseParamScopeFilter = ref('all')
  // 参考参数页签搜索/过滤
  const referenceSearchKeyword = ref('')
  const referenceTypeFilter = ref('all')
  const referenceMergeFilter = ref('all')
  // 关联维度页签搜索
  const dimensionSearchKeyword = ref('')
  // 每次打开弹窗自增，强制重建 MappingEditor，重置其内部过滤状态
  const mappingEditorKey = ref(0)
  // 列头过滤状态（ColumnFilter 的 v-model 值，'all' 表示不过滤）
  const deviceApiFilters = reactive({
    paramCode: 'all',
    paramName: 'all',
    direction: 'all',
    paramType: 'all',
    required: 'all'
  })
  const caseFilters = reactive({
    paramCode: 'all',
    paramName: 'all',
    paramType: 'all',
    scope: 'all',
    required: 'all',
    defaultValue: 'all',
    annotationCode: 'all',
    fieldPath: 'all',
    helpText: 'all'
  })
  const referenceFilters = reactive({
    code: 'all',
    annotationCode: 'all',
    name: 'all',
    type: 'all',
    annotationFormat: 'all',
    fieldPath: 'all',
    mergeMode: 'all',
    helpText: 'all'
  })
  const dimensionFilters = reactive({
    dimensionId: 'all',
    isDefault: 'all'
  })

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

  // 参数配置搜索框：按当前页签路由到设备/API 或 用例参数 的关键字
  const paramSearchModel = computed({
    get: () => (paramConfigType.value === 'case' ? caseParamSearchKeyword.value : paramSearchKeyword.value),
    set: (v: string) => {
      if (paramConfigType.value === 'case') caseParamSearchKeyword.value = v
      else paramSearchKeyword.value = v
    }
  })

  // 列头过滤下拉的可选值
  const directionOptions = [
    { value: 'input', label: '输入' },
    { value: 'output', label: '输出' }
  ]
  const requiredOptions = [
    { value: 'required', label: '必填' },
    { value: 'optional', label: '选填' }
  ]
  const deviceApiTypeOptions = [
    { value: 'text', label: '文本' },
    { value: 'audio_stream', label: '音频流' },
    { value: 'audio_file', label: '音频文件' },
    { value: 'text_file', label: '文本文件' },
    { value: 'rttm', label: 'RTTM标注' },
    { value: 'stm', label: 'STM标注' },
    { value: 'json', label: 'JSON结构化' }
  ]
  const caseTypeOptions = [
    { value: 'text', label: '文本' },
    { value: 'number', label: '数字' },
    { value: 'textarea', label: '多行文本' },
    { value: 'switch', label: '开关' },
    { value: 'slider', label: '滑块' },
    { value: 'audio_select', label: '音频选择' },
    { value: 'device_select', label: '设备选择' },
    { value: 'json', label: 'JSON结构化' }
  ]
  const scopeOptions = [
    { value: 'common', label: '通用' },
    { value: TestType.API, label: 'API' },
    { value: TestType.E2E, label: 'E2E' }
  ]
  const referenceTypeOptions = [
    { value: 'text', label: '文本' },
    { value: 'audio', label: '音频' },
    { value: 'json', label: 'JSON' },
    { value: 'rttm', label: 'RTTM' },
    { value: 'stm', label: 'STM' }
  ]
  const referenceFormatOptions = [
    { value: 'text', label: '文本' },
    { value: 'json', label: 'JSON' },
    { value: 'rttm', label: 'RTTM' },
    { value: 'stm', label: 'STM' },
    { value: 'boolean', label: '布尔' }
  ]
  const mergeOptions = [
    { value: 'join', label: '拼接' },
    { value: 'collect', label: '收集数组' },
    { value: 'first', label: '取第一个' }
  ]
  const dimensionFilterOptions = computed(() =>
    availableDimensions.value.map(d => ({ value: String(d.id), label: d.name }))
  )

  // 列头下拉过滤选项：返回某列的非空去重取值
  function distinctValues(list: any[], key: string): string[] {
    const set = new Set<string>()
    for (const item of list) {
      const v = item?.[key]
      if (v !== undefined && v !== null && String(v).trim() !== '') {
        set.add(String(v))
      }
    }
    return Array.from(set)
  }

  // 设备/API 参数表格过滤：搜索 + 方向/必填（含列头过滤）
  const filteredCurrentParams = computed(() => {
    let list = currentParams.value
    const kw = paramSearchKeyword.value.trim().toLowerCase()
    if (kw) {
      list = list.filter(p =>
        (p.paramCode || '').toLowerCase().includes(kw) ||
        (p.paramName || '').toLowerCase().includes(kw)
      )
    }
    const hf = deviceApiFilters
    if (hf.paramCode !== 'all') {
      const v = String(hf.paramCode).toLowerCase()
      list = list.filter(p => (p.paramCode || '').toLowerCase().includes(v))
    }
    if (hf.paramName !== 'all') {
      const v = String(hf.paramName).toLowerCase()
      list = list.filter(p => (p.paramName || '').toLowerCase().includes(v))
    }
    if (hf.direction !== 'all') {
      list = list.filter(p => p.direction === hf.direction)
    }
    if (hf.paramType !== 'all') {
      list = list.filter(p => p.paramType === hf.paramType)
    }
    if (hf.required !== 'all') {
      const req = hf.required === 'required'
      list = list.filter(p => !!p.required === req)
    }
    if (paramDirectionFilter.value !== 'all') {
      list = list.filter(p => p.direction === paramDirectionFilter.value)
    }
    if (paramRequiredFilter.value !== 'all') {
      const req = paramRequiredFilter.value === 'required'
      list = list.filter(p => !!p.required === req)
    }
    return list
  })

  // 用例参数表格过滤：搜索 + 类型/范围/必填（含列头过滤）
  const filteredCaseParams = computed(() => {
    let list = formState.caseParams
    const kw = caseParamSearchKeyword.value.trim().toLowerCase()
    if (kw) {
      list = list.filter(p =>
        (p.paramCode || '').toLowerCase().includes(kw) ||
        (p.paramName || '').toLowerCase().includes(kw) ||
        (p.annotationCode || '').toLowerCase().includes(kw) ||
        (p.fieldPath || '').toLowerCase().includes(kw) ||
        (p.helpText || '').toLowerCase().includes(kw)
      )
    }
    const hf = caseFilters
    if (hf.paramCode !== 'all') {
      const v = String(hf.paramCode).toLowerCase()
      list = list.filter(p => (p.paramCode || '').toLowerCase().includes(v))
    }
    if (hf.paramName !== 'all') {
      const v = String(hf.paramName).toLowerCase()
      list = list.filter(p => (p.paramName || '').toLowerCase().includes(v))
    }
    if (hf.paramType !== 'all') {
      list = list.filter(p => p.paramType === hf.paramType)
    }
    if (hf.scope !== 'all') {
      list = list.filter(p => p.scope === hf.scope)
    }
    if (hf.required !== 'all') {
      const req = hf.required === 'required'
      list = list.filter(p => !!p.required === req)
    }
    if (hf.defaultValue !== 'all') {
      const v = String(hf.defaultValue).toLowerCase()
      list = list.filter(p => (p.defaultValue || '').toLowerCase().includes(v))
    }
    if (hf.annotationCode !== 'all') {
      const v = String(hf.annotationCode).toLowerCase()
      list = list.filter(p => (p.annotationCode || '').toLowerCase().includes(v))
    }
    if (hf.fieldPath !== 'all') {
      const v = String(hf.fieldPath).toLowerCase()
      list = list.filter(p => (p.fieldPath || '').toLowerCase().includes(v))
    }
    if (hf.helpText !== 'all') {
      const v = String(hf.helpText).toLowerCase()
      list = list.filter(p => (p.helpText || '').toLowerCase().includes(v))
    }
    if (caseParamTypeFilter.value !== 'all') {
      list = list.filter(p => p.paramType === caseParamTypeFilter.value)
    }
    if (caseParamScopeFilter.value !== 'all') {
      list = list.filter(p => p.scope === caseParamScopeFilter.value)
    }
    if (paramRequiredFilter.value !== 'all') {
      const req = paramRequiredFilter.value === 'required'
      list = list.filter(p => !!p.required === req)
    }
    return list
  })

  // 参考参数表格过滤：搜索 + 类型/合并（含列头过滤）
  const filteredReferenceParams = computed(() => {
    let list = formState.referenceParams
    const kw = referenceSearchKeyword.value.trim().toLowerCase()
    if (kw) {
      list = list.filter(p =>
        (p.code || '').toLowerCase().includes(kw) ||
        (p.annotationCode || '').toLowerCase().includes(kw) ||
        (p.name || '').toLowerCase().includes(kw) ||
        (p.fieldPath || '').toLowerCase().includes(kw) ||
        (p.helpText || '').toLowerCase().includes(kw)
      )
    }
    const hf = referenceFilters
    if (hf.code !== 'all') {
      const v = String(hf.code).toLowerCase()
      list = list.filter(p => (p.code || '').toLowerCase().includes(v))
    }
    if (hf.annotationCode !== 'all') {
      const v = String(hf.annotationCode).toLowerCase()
      list = list.filter(p => (p.annotationCode || '').toLowerCase().includes(v))
    }
    if (hf.name !== 'all') {
      const v = String(hf.name).toLowerCase()
      list = list.filter(p => (p.name || '').toLowerCase().includes(v))
    }
    if (hf.type !== 'all') {
      list = list.filter(p => p.type === hf.type)
    }
    if (hf.annotationFormat !== 'all') {
      list = list.filter(p => p.annotationFormat === hf.annotationFormat)
    }
    if (hf.fieldPath !== 'all') {
      const v = String(hf.fieldPath).toLowerCase()
      list = list.filter(p => (p.fieldPath || '').toLowerCase().includes(v))
    }
    if (hf.mergeMode !== 'all') {
      list = list.filter(p => p.mergeMode === hf.mergeMode)
    }
    if (hf.helpText !== 'all') {
      const v = String(hf.helpText).toLowerCase()
      list = list.filter(p => (p.helpText || '').toLowerCase().includes(v))
    }
    if (referenceTypeFilter.value !== 'all') {
      list = list.filter(p => p.type === referenceTypeFilter.value)
    }
    if (referenceMergeFilter.value !== 'all') {
      list = list.filter(p => p.mergeMode === referenceMergeFilter.value)
    }
    return list
  })

  // 关联维度表格过滤：按维度名称搜索 + 维度/默认筛选
  const filteredDimensions = computed(() => {
    let list = formState.associatedDimensions
    const kw = dimensionSearchKeyword.value.trim().toLowerCase()
    if (kw) {
      list = list.filter(dim => {
        const dimObj = availableDimensions.value.find(x => x.id === dim.dimensionId)
        return (dimObj?.name || '').toLowerCase().includes(kw)
      })
    }
    if (dimensionFilters.dimensionId !== 'all') {
      const targetId = Number(dimensionFilters.dimensionId)
      list = list.filter(dim => dim.dimensionId === targetId)
    }
    if (dimensionFilters.isDefault !== 'all') {
      const isDef = dimensionFilters.isDefault === 'default'
      list = list.filter(dim => !!dim.isDefault === isDef)
    }
    return list
  })

  function resetFilters() {
    paramSearchKeyword.value = ''
    caseParamSearchKeyword.value = ''
    paramDirectionFilter.value = 'all'
    paramRequiredFilter.value = 'all'
    caseParamTypeFilter.value = 'all'
    caseParamScopeFilter.value = 'all'
    referenceSearchKeyword.value = ''
    referenceTypeFilter.value = 'all'
    referenceMergeFilter.value = 'all'
    dimensionSearchKeyword.value = ''
    Object.assign(deviceApiFilters, { paramCode: 'all', paramName: 'all', direction: 'all', paramType: 'all', required: 'all' })
    Object.assign(caseFilters, { paramCode: 'all', paramName: 'all', paramType: 'all', scope: 'all', required: 'all', defaultValue: 'all', annotationCode: 'all', fieldPath: 'all', helpText: 'all' })
    Object.assign(referenceFilters, { code: 'all', annotationCode: 'all', name: 'all', type: 'all', annotationFormat: 'all', fieldPath: 'all', mergeMode: 'all', helpText: 'all' })
    Object.assign(dimensionFilters, { dimensionId: 'all', isDefault: 'all' })
  }

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
      // 每次打开都重置搜索/过滤状态，避免残留过滤导致数据不显示
      resetFilters()
      mappingEditorKey.value++
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
    paramSearchModel,
    paramDirectionFilter,
    paramRequiredFilter,
    caseParamTypeFilter,
    caseParamScopeFilter,
    referenceSearchKeyword,
    referenceTypeFilter,
    referenceMergeFilter,
    dimensionSearchKeyword,
    mappingEditorKey,
    deviceApiFilters,
    caseFilters,
    referenceFilters,
    dimensionFilters,
    directionOptions,
    requiredOptions,
    deviceApiTypeOptions,
    caseTypeOptions,
    scopeOptions,
    referenceTypeOptions,
    referenceFormatOptions,
    mergeOptions,
    dimensionFilterOptions,
    distinctValues,
    filteredCurrentParams,
    filteredCaseParams,
    filteredReferenceParams,
    filteredDimensions,
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
