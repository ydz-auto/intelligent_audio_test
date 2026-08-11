import { algorithmApi } from '../../utils/api'
import { useModalControl, MODAL_TYPES } from '../../composables/modal/useModal'
import { normalizeParamFields, normalizeCaseParamFields } from './algorithmParamHelpers'
import type { AlgorithmRecord, AlgorithmGroup, Dimension } from './algorithmTypes'

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

  async function loadAlgorithms() {
    try {
      const result = await algorithmApi.getDefinitions()
      algorithms.value = result.data || []
    } catch (error) {
      console.error('加载算法列表失败:', error)
    }
  }

  async function loadGroups() {
    try {
      const result = await algorithmApi.getGroups()
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
    formState.group_id = null
    formState.description = ''
    formState.status = 'online'
    formState.statusSwitch = true
    formState.icon = ''
    formState.display_order = 0
    formState.device_params = []
    formState.api_params = []
    formState.case_params = []
    formState.mappings = { device: [], api: [], evaluation: [] }
    formState.associated_dimensions = []
    formState.reference_params = []
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
    console.log('handleOk:', { mode: effectiveMode.value, formState: JSON.stringify(formState) })
    if (effectiveMode.value === 'select') {
      if (props.editData) {
        emit('select', props.editData)
        emit('update:visible', false)
      }
      return
    }

    if (!formState.type || !formState.name) {
      alert('请填写必填字段')
      return
    }
    if (creatingNewGroup.value && !newGroupName.value.trim()) {
      alert('请填写新分组名称')
      return
    }
    if (!creatingNewGroup.value && !formState.group_id) {
      alert('请填写必填字段')
      return
    }

    await saveAlgorithm()
  }

  async function saveAlgorithm() {
    try {
      formState.status = formState.statusSwitch ? 'online' : 'offline'

      // 若选择了新建分组，先创建分组并回填 group_id
      if (creatingNewGroup.value) {
        const newGroup = await algorithmApi.createGroup({ name: newGroupName.value.trim() })
        await loadGroups()
        formState.group_id = newGroup.id ?? null
        creatingNewGroup.value = false
        newGroupName.value = ''
      }

      const bodyData: any = {
        type: formState.type,
        name: formState.name,
        group_id: formState.group_id,
        description: formState.description,
        status: formState.status,
        icon: formState.icon,
        display_order: formState.display_order,
        device_params: formState.device_params,
        api_params: formState.api_params,
        case_params: formState.case_params,
        mappings: formState.mappings,
        associated_dimensions: formState.associated_dimensions,
        reference_params: formState.reference_params
      }

      if (effectiveMode.value === 'edit') {
        await algorithmApi.updateDefinition(formState.type, bodyData)
      } else {
        await algorithmApi.createDefinition(bodyData)
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

  async function handleEdit(record: AlgorithmRecord) {
    try {
      const result = await algorithmApi.getDefinition(record.type)
      if (result) {
        const editData = result
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
            id: d.id,
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
        paramConfigType.value = 'device'
        creatingNewGroup.value = false
        newGroupName.value = ''
        internalMode.value = 'edit'
      }
    } catch (error) {
      console.error('加载算法详情失败:', error)
    }
  }

  function handleSelect(record: AlgorithmRecord) {
    emit('select', record)
    emit('update:visible', false)
  }

  async function handleToggleStatus(record: AlgorithmRecord) {
    const newStatus = record.status === 'online' ? 'offline' : 'online'
    const action = newStatus === 'offline' ? '禁用' : '启用'

    try {
      await algorithmApi.updateDefinition(record.type, { status: newStatus })
      loadAlgorithms()
    } catch (error) {
      console.error(`${action}失败:`, error)
    }
  }

  async function confirmDelete(record: AlgorithmRecord) {
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

  async function executeDelete(record: AlgorithmRecord) {
    if (!record) return

    try {
      await algorithmApi.deleteDefinition(record.type)
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
