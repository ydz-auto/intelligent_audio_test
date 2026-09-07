import { algorithmPort } from '../../composables/algorithm/algorithmPort'
import { useModalControl, MODAL_TYPES } from '../../composables/modal/useModal'
import { normalizeParamFields, normalizeCaseParamFields } from './algorithmParamHelpers'
import { useNotification } from '../../composables/modal/useNotification'
import type { AlgorithmDefinition, AlgorithmGroup, Dimension } from '@/domain'
import { ApiEndpointStatus, ApiEndpointStatusType } from '@/domain/enums'

// source 合法值校验：仅允许 case/reference/device/api
const VALID_SOURCES = ['case', 'reference', 'device', 'api']

export function normalizeMappings(raw: any): { device: any[]; api: any[]; evaluation: any[] } {
  const empty = { device: [], api: [], evaluation: [] }
  if (!raw) return empty
  const convert = (arr: any[]) => (arr || []).map((m: any) => {
    // source 非法值修复：非合法值默认归为 'case'
    const source = (!m.source || !VALID_SOURCES.includes(m.source)) ? 'case' : m.source
    return {
      id: m.id,
      source,
      sourceParam: m.sourceParam ?? '',
      paramName: m.paramName ?? m.sourceParam ?? '',
      dimensionId: m.dimensionId ?? null,
      dimensionName: m.dimensionName ?? '',
      targetParam: m.targetParam ?? '',
      transformType: m.transformType ?? 'none',
      sourceDirection: m.sourceDirection ?? 'output'
    }
  })
  return {
    device: convert(raw.device),
    api: convert(raw.api),
    evaluation: convert(raw.evaluation)
  }
}

export function useAlgorithmCrudOps(
  props: any,
  emit: any,
  formState: any,
  effectiveMode: any,
  internalMode: any,
  algorithms: any,
  groups: any,
  availableDimensions: any,
  fetchAllDimensions: () => Promise<any>,
  clearFormSchemaCache: () => void,
  savePendingReferenceParams: () => Promise<void>,
  creatingNewGroup: any,
  newGroupName: any,
  activeTab: any,
  paramConfigType: any
) {
  const modalControl = useModalControl()
  const notification = useNotification()

  async function loadAlgorithms() {
    try {
      const result = await algorithmPort.getDefinitions()
      algorithms.value = result.data || []
    } catch (error) {
      console.error('加载算法列表失败:', error)
    }
  }

  async function loadGroups() {
    try {
      const result = await algorithmPort.getGroups()
      groups.value = result.data || []
    } catch (error) {
      console.error('加载分组列表失败:', error)
    }
  }

  async function loadDimensions() {
    try {
      const dimensions = await fetchAllDimensions()
      availableDimensions.value = dimensions as Dimension[]
    } catch (error) {
      console.error('加载评估维度失败:', error)
    }
  }

  function resetForm() {
    formState.type = ''
    formState.name = ''
    formState.groupId = null
    formState.description = ''
    formState.status = ApiEndpointStatus.ONLINE
    formState.statusSwitch = true
    formState.icon = ''
    formState.displayOrder = 0
    formState.deviceParams = []
    formState.apiParams = []
    formState.caseParams = []
    formState.mappings = { device: [], api: [], evaluation: [] }
    formState.associatedDimensions = []
    formState.referenceParams = []
    creatingNewGroup.value = false
    newGroupName.value = ''
    activeTab.value = 'basic'
    paramConfigType.value = 'device'
  }

  function handleCancel() {
    if (internalMode.value !== props.mode && props.mode === 'list') {
      internalMode.value = 'list'
    } else {
      emit('update:visible', false)
    }
  }

  async function handleOk() {
    if (effectiveMode.value === 'select') {
      if (props.editData) {
        emit('select', props.editData)
        emit('update:visible', false)
      }
      return
    }

    if (!formState.type || !formState.name) {
      notification.warning('请填写必填字段')
      return
    }
    if (creatingNewGroup.value && !newGroupName.value.trim()) {
      notification.warning('请填写新分组名称')
      return
    }
    if (!creatingNewGroup.value && !formState.groupId) {
      notification.warning('请填写必填字段')
      return
    }

    await saveAlgorithm()
  }

  async function saveAlgorithm() {
    try {
      formState.status = formState.statusSwitch ? ApiEndpointStatus.ONLINE : ApiEndpointStatus.OFFLINE

      // 若选择了新建分组，先创建分组并回填 groupId
      if (creatingNewGroup.value) {
        const newGroup = await algorithmPort.createGroup({ name: newGroupName.value.trim() })
        await loadGroups()
        formState.groupId = newGroup.id ?? null
        creatingNewGroup.value = false
        newGroupName.value = ''
      }

      // 提交 bodyData 为 camelCase Domain 字段，algorithmPort 内部做 snake_case 转换
      const bodyData: any = {
        type: formState.type,
        name: formState.name,
        groupId: formState.groupId,
        description: formState.description,
        status: formState.status,
        icon: formState.icon,
        displayOrder: formState.displayOrder,
        deviceParams: formState.deviceParams,
        apiParams: formState.apiParams,
        caseParams: formState.caseParams,
        mappings: formState.mappings,
        associatedDimensions: formState.associatedDimensions,
        referenceParams: formState.referenceParams
      }

      if (effectiveMode.value === 'edit') {
        await algorithmPort.updateDefinition(formState.type, bodyData)
      } else {
        await algorithmPort.createDefinition(bodyData)
        // 新建模式下参考参数无法随 createDefinition 保存，算法创建成功后统一补存
        await savePendingReferenceParams()
      }
      // 清除算法参数缓存，确保用例页面能获取最新参数定义
      clearFormSchemaCache()
      emit('success')
      emit('update:visible', false)
      loadAlgorithms()
    } catch (error) {
      console.error('操作失败:', error)
    }
  }

  function handleCreate() {
    resetForm()
    internalMode.value = 'create'
  }

  async function handleEdit(record: AlgorithmDefinition) {
    try {
      const result = await algorithmPort.getDefinition(record.type)
      if (result) {
        const editData = result as any
        const deviceParams = (editData.deviceParams || []).map(normalizeParamFields).map((p: any) => ({ ...p }))
        const apiParams = (editData.apiParams || []).map(normalizeParamFields).map((p: any) => ({ ...p }))
        const caseParams = (editData.caseParams || []).map(normalizeCaseParamFields).map((p: any) => ({ ...p }))
        const refConfig = editData.referenceParams

        Object.assign(formState, {
          type: editData.type,
          name: editData.name,
          groupId: editData.groupId ?? null,
          description: editData.description || '',
          status: editData.status as ApiEndpointStatusType,
          statusSwitch: editData.status === ApiEndpointStatus.ONLINE,
          icon: editData.icon || '',
          displayOrder: editData.displayOrder || 0,
          deviceParams: deviceParams,
          apiParams: apiParams,
          caseParams: caseParams,
          params: editData.params || [],
          mappings: normalizeMappings(editData.mappings),
          associatedDimensions: (editData.associatedDimensions || []).map((d: any) => ({
            id: d.id,
            dimensionId: d.dimensionId ?? null,
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
        paramConfigType.value = 'device'
        creatingNewGroup.value = false
        newGroupName.value = ''
        internalMode.value = 'edit'
      }
    } catch (error) {
      console.error('加载算法详情失败:', error)
    }
  }

  function handleSelect(record: AlgorithmDefinition) {
    emit('select', record)
    emit('update:visible', false)
  }

  async function handleToggleStatus(record: AlgorithmDefinition) {
    const newStatus = record.status === ApiEndpointStatus.ONLINE ? ApiEndpointStatus.OFFLINE : ApiEndpointStatus.ONLINE
    const action = newStatus === ApiEndpointStatus.OFFLINE ? '禁用' : '启用'

    try {
      await algorithmPort.updateDefinition(record.type, { status: newStatus })
      loadAlgorithms()
    } catch (error) {
      console.error(`${action}失败:`, error)
    }
  }

  async function confirmDelete(record: AlgorithmDefinition) {
    const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '确认删除',
      content: `确定要删除算法「${record.name}」吗？此操作不可恢复。`,
      confirmText: '删除',
      cancelText: '取消',
      danger: true
    })

    if (confirmed) {
      await executeDelete(record)
    }
  }

  async function executeDelete(record: AlgorithmDefinition) {
    if (!record) return

    try {
      await algorithmPort.deleteDefinition(record.type)
      loadAlgorithms()
    } catch (error) {
      console.error('删除失败:', error)
    }
  }

  function handleSearch() {
  }

  return {
    modalControl,
    loadAlgorithms,
    loadGroups,
    loadDimensions,
    resetForm,
    handleCancel,
    handleOk,
    saveAlgorithm,
    handleCreate,
    handleEdit,
    handleSelect,
    handleToggleStatus,
    confirmDelete,
    executeDelete,
    handleSearch,
  }
}
