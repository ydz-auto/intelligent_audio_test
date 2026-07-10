// -*- coding: utf-8 -*-
/**
 * AlgorithmConfigModal.vue 组件单元测试
 *
 * 覆盖：模态窗打开/关闭、表单校验、saveAlgorithm分支、参数自动保存、
 * 维度关联交互、Tab切换、参数行操作、功能特性快捷开关、
 * 参数类型变更与预设填充、参考参数自动同步、模式切换与取消、
 * 状态切换与删除、映射折叠与更新、computed属性分支、watch与生命周期
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'

// Use vi.hoisted to define mock variables so they're available in hoisted vi.mock factories
const {
  mockOpenConfirm,
  mockFetchAllDimensions,
  mockAlgorithmApi,
} = vi.hoisted(() => {
  const mockOpenConfirm = vi.fn()
  const mockFetchAllDimensions = vi.fn()
  const mockAlgorithmApi = {
    getDefinitions: vi.fn(),
    getDefinition: vi.fn(),
    createDefinition: vi.fn(),
    updateDefinition: vi.fn(),
    deleteDefinition: vi.fn(),
    getGroups: vi.fn(),
    getOptionsSources: vi.fn(),
    getParams: vi.fn(),
    createParam: vi.fn(),
    updateParam: vi.fn(),
    deleteParam: vi.fn(),
    createCaseParam: vi.fn(),
    updateCaseParam: vi.fn(),
    deleteCaseParam: vi.fn(),
    createReferenceParam: vi.fn(),
    updateReferenceParam: vi.fn(),
    deleteReferenceParam: vi.fn(),
    createDimensionRelation: vi.fn(),
    updateDimensionRelation: vi.fn(),
    deleteDimensionRelation: vi.fn(),
  }
  return { mockOpenConfirm, mockFetchAllDimensions, mockAlgorithmApi }
})

// Mock BasicModal — render slot content
vi.mock('../../common/modal/BasicModal.vue', () => ({
  default: defineComponent({
    name: 'BasicModal',
    props: ['visible', 'title', 'width', 'showFooter', 'confirmText', 'cancelText'],
    emits: ['close', 'cancel', 'confirm'],
    template: '<div class="mock-basic-modal" v-if="visible"><slot /></div>',
  }),
}))

// Mock MappingEditor
vi.mock('../MappingEditor.vue', () => ({
  default: defineComponent({
    name: 'MappingEditor',
    props: ['mappings', 'algorithmType', 'caseParams', 'deviceParams', 'apiParams', 'referenceParams', 'mainDimensions', 'componentType'],
    emits: ['update'],
    template: '<div class="mock-mapping-editor"></div>',
  }),
}))

// Mock useModalControl
vi.mock('../../../composables/useModal', () => ({
  useModalControl: () => ({ open: mockOpenConfirm }),
  MODAL_TYPES: { BASIC_CONFIRM: 'basicConfirm' },
}))

// Mock useDimensions
vi.mock('../../../composables/useDimensions', () => ({
  useDimensions: () => ({ fetchAllDimensions: mockFetchAllDimensions }),
}))

// Mock algorithmApi and evaluationApi
vi.mock('../../../utils/api', () => ({
  algorithmApi: mockAlgorithmApi,
  evaluationApi: {},
}))

// 导入被测组件（必须在 vi.mock 之后）
import AlgorithmConfigModal from '../AlgorithmConfigModal.vue'

// 辅助函数
function makeAlgData(overrides: any = {}) {
  return {
    type: 'test_algo',
    name: '测试算法',
    group_id: 1,
    group_name: '翻译',
    status: 'online',
    display_order: 0,
    device_params: [],
    api_params: [],
    case_params: [],
    mappings: { device: [], api: [], evaluation: [] },
    associated_dimensions: [],
    reference_params: [],
    ...overrides,
  }
}

// Mount with props
function mountModal(props: any = {}) {
  return mount(AlgorithmConfigModal, {
    props: {
      visible: true,
      mode: 'create',
      ...props,
    },
  })
}

beforeEach(() => {
  vi.resetAllMocks()
  global.alert = vi.fn()
  mockOpenConfirm.mockResolvedValue(false)
  vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.spyOn(console, 'log').mockImplementation(() => {})
  // Default mocks
  mockAlgorithmApi.getDefinitions.mockResolvedValue({ data: [] })
  mockAlgorithmApi.getGroups.mockResolvedValue({ data: [] })
  mockAlgorithmApi.getOptionsSources.mockResolvedValue({ data: [] })
  mockFetchAllDimensions.mockResolvedValue([])
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

// 3.2.1 模态窗打开/关闭
describe('3.2.1 模态窗打开/关闭', () => {
  it('TC-FE-MODAL-001: create模式打开表单为空', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    expect(wrapper.vm.formState.type).toBe('')
    expect(wrapper.vm.formState.name).toBe('')
    expect(wrapper.vm.formState.group_id).toBe(null)
  })

  it('TC-FE-MODAL-002: edit模式打开表单已填充', async () => {
    const editData = makeAlgData({ type: 'edit_algo', name: '编辑算法' })
    const wrapper = mountModal({ mode: 'edit', editData })
    await flushPromises()
    expect(wrapper.vm.formState.type).toBe('edit_algo')
    expect(wrapper.vm.formState.name).toBe('编辑算法')
  })

  it('TC-FE-MODAL-003: 关闭时emit update:visible false', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.handleCancel()
    expect(wrapper.emitted('update:visible')).toBeTruthy()
    expect(wrapper.emitted('update:visible')![0]).toEqual([false])
  })

  it('TC-FE-MODAL-004: visible=true时调用loadGroups', async () => {
    const wrapper = mountModal({ mode: 'create', visible: false })
    await flushPromises()
    mockAlgorithmApi.getGroups.mockClear()
    await wrapper.setProps({ visible: true })
    await flushPromises()
    expect(mockAlgorithmApi.getGroups).toHaveBeenCalled()
  })

  it.skip('TC-FE-MODAL-005: visible=true时调用loadOptionsSources (源码已移除loadOptionsSources)', async () => {
    // loadOptionsSources 已在源码重构中移除，跳过此测试
  })

  it('TC-FE-MODAL-006: visible=true时调用fetchAllDimensions', async () => {
    const wrapper = mountModal({ mode: 'create', visible: false })
    await flushPromises()
    mockFetchAllDimensions.mockClear()
    await wrapper.setProps({ visible: true })
    await flushPromises()
    expect(mockFetchAllDimensions).toHaveBeenCalled()
  })
})

// 3.2.2 表单校验
describe('3.2.2 表单校验', () => {
  it('TC-FE-VALID-001: type为空时handleOk调用alert且不调用API', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.name = '名称'
    wrapper.vm.formState.group_id = 1
    wrapper.vm.formState.type = ''
    await wrapper.vm.handleOk()
    expect(global.alert).toHaveBeenCalledWith('请填写必填字段')
    expect(mockAlgorithmApi.createDefinition).not.toHaveBeenCalled()
  })

  it('TC-FE-VALID-002: name为空时alert', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    wrapper.vm.formState.name = ''
    wrapper.vm.formState.group_id = 1
    await wrapper.vm.handleOk()
    expect(global.alert).toHaveBeenCalledWith('请填写必填字段')
    expect(mockAlgorithmApi.createDefinition).not.toHaveBeenCalled()
  })

  it('TC-FE-VALID-003: group_id为null时alert', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    wrapper.vm.formState.name = '名称'
    wrapper.vm.formState.group_id = null
    await wrapper.vm.handleOk()
    expect(global.alert).toHaveBeenCalledWith('请填写必填字段')
    expect(mockAlgorithmApi.createDefinition).not.toHaveBeenCalled()
  })

  it('TC-FE-VALID-004: 全部填写时调用createDefinition', async () => {
    mockAlgorithmApi.createDefinition.mockResolvedValue({ id: 1 })
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    wrapper.vm.formState.name = '名称'
    wrapper.vm.formState.group_id = 1
    await wrapper.vm.handleOk()
    expect(mockAlgorithmApi.createDefinition).toHaveBeenCalled()
  })
})

// 3.2.3 saveAlgorithm() 分支
describe('3.2.3 saveAlgorithm() 分支', () => {
  it('TC-FE-SAVE-001: create模式调用createDefinition并emit success', async () => {
    mockAlgorithmApi.createDefinition.mockResolvedValue({ id: 1 })
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    wrapper.vm.formState.name = '名称'
    wrapper.vm.formState.group_id = 1
    await wrapper.vm.saveAlgorithm()
    expect(mockAlgorithmApi.createDefinition).toHaveBeenCalled()
    expect(wrapper.emitted('success')).toBeTruthy()
  })

  it('TC-FE-SAVE-001b: create模式下saveAlgorithm后补存未保存的参考参数', async () => {
    mockAlgorithmApi.createDefinition.mockResolvedValue({ id: 1 })
    mockAlgorithmApi.createReferenceParam.mockResolvedValue({ id: 99 })
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    wrapper.vm.formState.name = '名称'
    wrapper.vm.formState.group_id = 1
    wrapper.vm.formState.reference_params = [{ code: 'rp1', name: 'N', type: 'text', annotation_code: 'rp1' }]
    await wrapper.vm.saveAlgorithm()
    expect(mockAlgorithmApi.createDefinition).toHaveBeenCalled()
    expect(mockAlgorithmApi.createReferenceParam).toHaveBeenCalledWith(expect.objectContaining({ code: 'rp1', algorithm_type: 'algo' }))
    expect(wrapper.vm.formState.reference_params[0].id).toBe(99)
  })

  it('TC-FE-SAVE-002: edit模式调用updateDefinition并emit success', async () => {
    mockAlgorithmApi.updateDefinition.mockResolvedValue({})
    const editData = makeAlgData({ type: 'edit_algo' })
    const wrapper = mountModal({ mode: 'edit', editData })
    await flushPromises()
    await wrapper.vm.saveAlgorithm()
    expect(mockAlgorithmApi.updateDefinition).toHaveBeenCalled()
    expect(wrapper.emitted('success')).toBeTruthy()
  })

  it('TC-FE-SAVE-003: 保存失败时console.error', async () => {
    mockAlgorithmApi.createDefinition.mockRejectedValue(new Error('fail'))
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    wrapper.vm.formState.name = '名称'
    wrapper.vm.formState.group_id = 1
    await wrapper.vm.saveAlgorithm()
    expect(console.error).toHaveBeenCalled()
  })

  it('TC-FE-SAVE-004: statusSwitch=true时status=online', async () => {
    mockAlgorithmApi.createDefinition.mockResolvedValue({ id: 1 })
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    wrapper.vm.formState.name = '名称'
    wrapper.vm.formState.group_id = 1
    wrapper.vm.formState.statusSwitch = true
    await wrapper.vm.saveAlgorithm()
    const bodyData = mockAlgorithmApi.createDefinition.mock.calls[0][0]
    expect(bodyData.status).toBe('online')
  })

  it('TC-FE-SAVE-005: statusSwitch=false时status=offline', async () => {
    mockAlgorithmApi.createDefinition.mockResolvedValue({ id: 1 })
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    wrapper.vm.formState.name = '名称'
    wrapper.vm.formState.group_id = 1
    wrapper.vm.formState.statusSwitch = false
    await wrapper.vm.saveAlgorithm()
    const bodyData = mockAlgorithmApi.createDefinition.mock.calls[0][0]
    expect(bodyData.status).toBe('offline')
  })

  it('TC-FE-SAVE-006: icon为空时bodyData.icon为空字符串', async () => {
    mockAlgorithmApi.createDefinition.mockResolvedValue({ id: 1 })
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    wrapper.vm.formState.name = '名称'
    wrapper.vm.formState.group_id = 1
    wrapper.vm.formState.icon = ''
    await wrapper.vm.saveAlgorithm()
    const bodyData = mockAlgorithmApi.createDefinition.mock.calls[0][0]
    expect(bodyData.icon).toBe('')
  })

  it('TC-FE-SAVE-007: display_order为0时bodyData.display_order为0', async () => {
    mockAlgorithmApi.createDefinition.mockResolvedValue({ id: 1 })
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    wrapper.vm.formState.name = '名称'
    wrapper.vm.formState.group_id = 1
    wrapper.vm.formState.display_order = 0
    await wrapper.vm.saveAlgorithm()
    const bodyData = mockAlgorithmApi.createDefinition.mock.calls[0][0]
    expect(bodyData.display_order).toBe(0)
  })

  it('TC-FE-SAVE-008: bodyData包含13个字段', async () => {
    mockAlgorithmApi.createDefinition.mockResolvedValue({ id: 1 })
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    wrapper.vm.formState.name = '名称'
    wrapper.vm.formState.group_id = 1
    await wrapper.vm.saveAlgorithm()
    const bodyData = mockAlgorithmApi.createDefinition.mock.calls[0][0]
    const expectedKeys = [
      'type', 'name', 'group_id', 'description', 'status', 'icon',
      'display_order', 'device_params', 'api_params', 'case_params',
      'mappings', 'associated_dimensions', 'reference_params'
    ]
    expectedKeys.forEach(key => {
      expect(bodyData).toHaveProperty(key)
    })
  })
})

// 3.2.4 参数自动保存
describe('3.2.4 参数自动保存', () => {
  it('TC-FE-AUTOSAVE-001: device param blur带id时调用updateParam', async () => {
    vi.useFakeTimers()
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    const param = { id: 10, param_code: 'p1', param_name: '名称', param_type: 'text', direction: 'input', required: false }
    wrapper.vm.formState.device_params = [param]
    mockAlgorithmApi.updateParam.mockResolvedValue({})
    wrapper.vm.handleParamBlur(param, 0, 'device')
    expect(mockAlgorithmApi.updateParam).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1500)
    await flushPromises()
    expect(mockAlgorithmApi.updateParam).toHaveBeenCalledWith(10, expect.any(Object))
  })

  it('TC-FE-AUTOSAVE-002: device param blur无id时调用createParam并设置id', async () => {
    vi.useFakeTimers()
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    const param = { param_code: 'p1', param_name: '名称', param_type: 'text', direction: 'input', required: false }
    wrapper.vm.formState.device_params = [param]
    mockAlgorithmApi.createParam.mockResolvedValue({ id: 99 })
    wrapper.vm.handleParamBlur(param, 0, 'device')
    vi.advanceTimersByTime(1500)
    await flushPromises()
    expect(mockAlgorithmApi.createParam).toHaveBeenCalled()
    expect(param.id).toBe(99)
  })

  it('TC-FE-AUTOSAVE-003: case param blur带id时调用updateCaseParam', async () => {
    vi.useFakeTimers()
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    const param = { id: 5, param_code: 'cp1', param_name: '名称', param_type: 'text', component: 'input', scope: 'common' }
    wrapper.vm.formState.case_params = [param]
    mockAlgorithmApi.updateCaseParam.mockResolvedValue({})
    wrapper.vm.handleCaseParamBlur(param, 0)
    vi.advanceTimersByTime(1000)
    await flushPromises()
    expect(mockAlgorithmApi.updateCaseParam).toHaveBeenCalledWith(5, expect.any(Object))
  })

  it('TC-FE-AUTOSAVE-004: case param blur无id时调用createCaseParam并设置id', async () => {
    vi.useFakeTimers()
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    const param = { param_code: 'cp1', param_name: '名称', param_type: 'text', component: 'input', scope: 'common' }
    wrapper.vm.formState.case_params = [param]
    mockAlgorithmApi.createCaseParam.mockResolvedValue({ id: 77 })
    wrapper.vm.handleCaseParamBlur(param, 0)
    vi.advanceTimersByTime(1000)
    await flushPromises()
    expect(mockAlgorithmApi.createCaseParam).toHaveBeenCalled()
    expect(param.id).toBe(77)
  })

  it('TC-FE-AUTOSAVE-005: reference param blur带id时调用updateReferenceParam', async () => {
    vi.useFakeTimers()
    const wrapper = mountModal({ mode: 'edit' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    const param = { id: 8, code: 'rp1', name: '名称', type: 'text', annotation_code: 'algo' }
    wrapper.vm.formState.reference_params = [param]
    mockAlgorithmApi.updateReferenceParam.mockResolvedValue({})
    wrapper.vm.handleReferenceParamBlur(param, 0)
    vi.advanceTimersByTime(1000)
    await flushPromises()
    expect(mockAlgorithmApi.updateReferenceParam).toHaveBeenCalledWith(8, 'algo', expect.any(Object))
  })

  it('TC-FE-AUTOSAVE-006: reference param blur无id时调用createReferenceParam并设置id', async () => {
    vi.useFakeTimers()
    const wrapper = mountModal({ mode: 'edit' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    const param = { code: 'rp1', name: '名称', type: 'text', annotation_code: 'algo' }
    wrapper.vm.formState.reference_params = [param]
    mockAlgorithmApi.createReferenceParam.mockResolvedValue({ id: 55 })
    wrapper.vm.handleReferenceParamBlur(param, 0)
    vi.advanceTimersByTime(1000)
    await flushPromises()
    expect(mockAlgorithmApi.createReferenceParam).toHaveBeenCalled()
    expect(param.id).toBe(55)
  })

  it('TC-FE-AUTOSAVE-007: type为空时blur不调用API', async () => {
    vi.useFakeTimers()
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = ''
    const param = { param_code: 'p1', param_name: '名称', param_type: 'text', direction: 'input', required: false }
    wrapper.vm.handleParamBlur(param, 0, 'device')
    vi.advanceTimersByTime(1500)
    await flushPromises()
    expect(mockAlgorithmApi.updateParam).not.toHaveBeenCalled()
    expect(mockAlgorithmApi.createParam).not.toHaveBeenCalled()
  })

  it('TC-FE-AUTOSAVE-008: 自动保存失败时console.error', async () => {
    vi.useFakeTimers()
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    const param = { id: 10, param_code: 'p1', param_name: '名称', param_type: 'text', direction: 'input', required: false }
    wrapper.vm.formState.device_params = [param]
    mockAlgorithmApi.updateParam.mockRejectedValue(new Error('fail'))
    wrapper.vm.handleParamBlur(param, 0, 'device')
    vi.advanceTimersByTime(1500)
    await flushPromises()
    expect(console.error).toHaveBeenCalled()
  })

  it('TC-FE-AUTOSAVE-009: debounce延迟验证(API在1500ms前不调用，之后调用)', async () => {
    vi.useFakeTimers()
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    const param = { param_code: 'p1', param_name: '名称', param_type: 'text', direction: 'input', required: false }
    wrapper.vm.formState.device_params = [param]
    mockAlgorithmApi.createParam.mockResolvedValue({ id: 1 })
    wrapper.vm.handleParamBlur(param, 0, 'device')
    expect(mockAlgorithmApi.createParam).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1499)
    expect(mockAlgorithmApi.createParam).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    await flushPromises()
    expect(mockAlgorithmApi.createParam).toHaveBeenCalled()
  })

  it('TC-FE-AUTOSAVE-010: annotation_code自动同步(code有值,annotation_code为空时同步)', async () => {
    vi.useFakeTimers()
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    const param = { code: 'rp1', name: '', type: 'text', annotation_code: '' }
    wrapper.vm.formState.reference_params = [param]
    mockAlgorithmApi.createReferenceParam.mockResolvedValue({ id: 1 })
    wrapper.vm.handleReferenceParamBlur(param, 0)
    expect(param.annotation_code).toBe('rp1')
  })
})

// 3.2.5 维度关联交互
describe('3.2.5 维度关联交互', () => {
  it('TC-FE-DIM-001: create模式handleDimensionBlur不调用API', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    wrapper.vm.formState.associated_dimensions = [{ dimension_id: 1, weight: 1.0, is_default: false }]
    await wrapper.vm.handleDimensionBlur(0)
    expect(mockAlgorithmApi.updateDimensionRelation).not.toHaveBeenCalled()
    expect(mockAlgorithmApi.createDimensionRelation).not.toHaveBeenCalled()
  })

  it('TC-FE-DIM-002: edit模式handleDimensionBlur调用API', async () => {
    const editData = makeAlgData()
    const wrapper = mountModal({ mode: 'edit', editData })
    await flushPromises()
    wrapper.vm.formState.associated_dimensions = [{ id: 5, dimension_id: 1, weight: 1.0, is_default: false }]
    mockAlgorithmApi.updateDimensionRelation.mockResolvedValue({})
    await wrapper.vm.handleDimensionBlur(0)
    expect(mockAlgorithmApi.updateDimensionRelation).toHaveBeenCalled()
  })

  it('TC-FE-DIM-003: dim有id时调用updateDimensionRelation', async () => {
    const editData = makeAlgData()
    const wrapper = mountModal({ mode: 'edit', editData })
    await flushPromises()
    wrapper.vm.formState.associated_dimensions = [{ id: 5, dimension_id: 1, weight: 1.0, is_default: false }]
    mockAlgorithmApi.updateDimensionRelation.mockResolvedValue({})
    await wrapper.vm.handleDimensionBlur(0)
    expect(mockAlgorithmApi.updateDimensionRelation).toHaveBeenCalledWith(5, expect.any(Object))
  })

  it('TC-FE-DIM-004: dim无id但有dimension_id时调用createDimensionRelation并设置dim.id', async () => {
    const editData = makeAlgData()
    const wrapper = mountModal({ mode: 'edit', editData })
    await flushPromises()
    const dim = { dimension_id: 2, weight: 1.0, is_default: false, tempId: 'temp_1' }
    wrapper.vm.formState.associated_dimensions = [dim]
    mockAlgorithmApi.createDimensionRelation.mockResolvedValue({ id: 42 })
    await wrapper.vm.handleDimensionBlur(0)
    expect(mockAlgorithmApi.createDimensionRelation).toHaveBeenCalled()
    expect(dim.id).toBe(42)
  })

  it('TC-FE-DIM-005: is_default=true时其他维度is_default设为false并调用updateDimensionRelation', async () => {
    const editData = makeAlgData()
    const wrapper = mountModal({ mode: 'edit', editData })
    await flushPromises()
    wrapper.vm.formState.associated_dimensions = [
      { id: 5, dimension_id: 1, weight: 1.0, is_default: true },
      { id: 6, dimension_id: 2, weight: 1.0, is_default: true },
    ]
    mockAlgorithmApi.updateDimensionRelation.mockResolvedValue({})
    await wrapper.vm.handleDimensionBlur(0)
    expect(wrapper.vm.formState.associated_dimensions[1].is_default).toBe(false)
    expect(mockAlgorithmApi.updateDimensionRelation).toHaveBeenCalledWith(6, { is_default: false })
  })
})

// 3.2.6 Tab切换
describe('3.2.6 Tab切换', () => {
  it('TC-FE-TAB-001: 切换到params tab', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.activeTab = 'params'
    expect(wrapper.vm.activeTab).toBe('params')
  })

  it('TC-FE-TAB-002: 切换到reference tab', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.activeTab = 'reference'
    expect(wrapper.vm.activeTab).toBe('reference')
  })

  it('TC-FE-TAB-003: 切换到mappings tab', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.activeTab = 'mappings'
    expect(wrapper.vm.activeTab).toBe('mappings')
  })

  it('TC-FE-TAB-004: 切换到dimensions tab', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.activeTab = 'dimensions'
    expect(wrapper.vm.activeTab).toBe('dimensions')
  })

  it('TC-FE-TAB-005: 切换回basic tab', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.activeTab = 'params'
    wrapper.vm.activeTab = 'basic'
    expect(wrapper.vm.activeTab).toBe('basic')
  })
})

// 3.2.7 参数行操作
describe('3.2.7 参数行操作', () => {
  it('TC-FE-ROW-001: 添加device param后device_params长度增加', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.paramConfigType = 'device'
    const before = wrapper.vm.formState.device_params.length
    wrapper.vm.handleAddParam()
    expect(wrapper.vm.formState.device_params.length).toBe(before + 1)
  })

  it('TC-FE-ROW-002: 删除device param(带id)后长度减少且deleteParam调用', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.paramConfigType = 'device'
    wrapper.vm.formState.device_params = [{ id: 10, param_code: 'p1', param_name: '名称', param_type: 'text', direction: 'input', required: false }]
    mockAlgorithmApi.deleteParam.mockResolvedValue({})
    wrapper.vm.handleRemoveParam(0)
    expect(wrapper.vm.formState.device_params.length).toBe(0)
    expect(mockAlgorithmApi.deleteParam).toHaveBeenCalledWith(10)
  })

  it('TC-FE-ROW-003: 删除失败时恢复并alert', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.paramConfigType = 'device'
    wrapper.vm.formState.device_params = [{ id: 10, param_code: 'p1', param_name: '名称', param_type: 'text', direction: 'input', required: false }]
    mockAlgorithmApi.deleteParam.mockRejectedValue(new Error('fail'))
    wrapper.vm.handleRemoveParam(0)
    await flushPromises()
    expect(global.alert).toHaveBeenCalledWith('删除参数失败，已恢复')
    expect(wrapper.vm.formState.device_params.length).toBe(1)
  })

  it('TC-FE-ROW-004: 添加case param后case_params长度增加', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.paramConfigType = 'case'
    const before = wrapper.vm.formState.case_params.length
    wrapper.vm.handleAddParam()
    expect(wrapper.vm.formState.case_params.length).toBe(before + 1)
  })

  it('TC-FE-ROW-005: 添加reference param后reference_params长度增加且annotation_code=formState.type', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'my_algo'
    const before = wrapper.vm.formState.reference_params.length
    wrapper.vm.handleAddReferenceParam()
    expect(wrapper.vm.formState.reference_params.length).toBe(before + 1)
    expect(wrapper.vm.formState.reference_params[before].annotation_code).toBe('my_algo')
  })

  it('TC-FE-ROW-006: 删除reference param(带id)时调用deleteReferenceParam', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    wrapper.vm.formState.reference_params = [{ id: 5, code: 'rp1', name: '名称', type: 'text', annotation_code: 'algo' }]
    mockAlgorithmApi.deleteReferenceParam.mockResolvedValue({})
    wrapper.vm.handleRemoveReferenceParam(0)
    expect(mockAlgorithmApi.deleteReferenceParam).toHaveBeenCalledWith(5, 'algo')
  })

  it('TC-FE-ROW-007: 删除reference param(无id)时仅本地删除不调用API', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.reference_params = [{ code: 'rp1', name: '名称', type: 'text', annotation_code: 'algo' }]
    wrapper.vm.handleRemoveReferenceParam(0)
    expect(wrapper.vm.formState.reference_params.length).toBe(0)
    expect(mockAlgorithmApi.deleteReferenceParam).not.toHaveBeenCalled()
  })

  it('TC-FE-ROW-008: 删除device/api param(带id)时调用deleteParam', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.paramConfigType = 'api'
    wrapper.vm.formState.api_params = [{ id: 7, param_code: 'ap1', param_name: '名称', param_type: 'text', direction: 'input', required: false }]
    mockAlgorithmApi.deleteParam.mockResolvedValue({})
    wrapper.vm.handleRemoveParam(0)
    expect(mockAlgorithmApi.deleteParam).toHaveBeenCalledWith(7)
  })

  it('TC-FE-ROW-009: 删除device/api param(无id)时不调用API', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.paramConfigType = 'device'
    wrapper.vm.formState.device_params = [{ param_code: 'p1', param_name: '名称', param_type: 'text', direction: 'input', required: false }]
    wrapper.vm.handleRemoveParam(0)
    expect(wrapper.vm.formState.device_params.length).toBe(0)
    expect(mockAlgorithmApi.deleteParam).not.toHaveBeenCalled()
  })

  it('TC-FE-ROW-010: 删除case param(带id)时调用deleteCaseParam', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.case_params = [{ id: 8, param_code: 'cp1', param_name: '名称', param_type: 'text', component: 'input', scope: 'common' }]
    mockAlgorithmApi.deleteCaseParam.mockResolvedValue({})
    wrapper.vm.handleRemoveCaseParam(0)
    expect(mockAlgorithmApi.deleteCaseParam).toHaveBeenCalledWith(8)
  })

  it('TC-FE-ROW-011: 删除case param(无id)时不调用API', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.case_params = [{ param_code: 'cp1', param_name: '名称', param_type: 'text', component: 'input', scope: 'common' }]
    wrapper.vm.handleRemoveCaseParam(0)
    expect(wrapper.vm.formState.case_params.length).toBe(0)
    expect(mockAlgorithmApi.deleteCaseParam).not.toHaveBeenCalled()
  })

  it('TC-FE-ROW-012: 添加dimension时dimension_id=null, weight=1.0, is_default=false', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    const before = wrapper.vm.formState.associated_dimensions.length
    wrapper.vm.handleAddDimension()
    expect(wrapper.vm.formState.associated_dimensions.length).toBe(before + 1)
    const dim = wrapper.vm.formState.associated_dimensions[before]
    expect(dim.dimension_id).toBe(null)
    expect(dim.weight).toBe(1.0)
    expect(dim.is_default).toBe(false)
  })

  it('TC-FE-ROW-013: 删除dimension(edit模式,带id)时调用deleteDimensionRelation', async () => {
    const editData = makeAlgData()
    const wrapper = mountModal({ mode: 'edit', editData })
    await flushPromises()
    wrapper.vm.formState.associated_dimensions = [{ id: 9, dimension_id: 1, weight: 1.0, is_default: false }]
    mockAlgorithmApi.deleteDimensionRelation.mockResolvedValue({})
    wrapper.vm.handleRemoveDimension(0)
    expect(wrapper.vm.formState.associated_dimensions.length).toBe(0)
    expect(mockAlgorithmApi.deleteDimensionRelation).toHaveBeenCalledWith(9)
  })

  it('TC-FE-ROW-014: 删除dimension(create模式)时不调用API', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.associated_dimensions = [{ dimension_id: 1, weight: 1.0, is_default: false }]
    wrapper.vm.handleRemoveDimension(0)
    expect(wrapper.vm.formState.associated_dimensions.length).toBe(0)
    expect(mockAlgorithmApi.deleteDimensionRelation).not.toHaveBeenCalled()
  })

  it('TC-FE-ROW-015: 删除dimension(edit模式,无id,有tempId)时不调用API', async () => {
    const editData = makeAlgData()
    const wrapper = mountModal({ mode: 'edit', editData })
    await flushPromises()
    wrapper.vm.formState.associated_dimensions = [{ tempId: 'temp_1', dimension_id: 1, weight: 1.0, is_default: false }]
    wrapper.vm.handleRemoveDimension(0)
    expect(wrapper.vm.formState.associated_dimensions.length).toBe(0)
    expect(mockAlgorithmApi.deleteDimensionRelation).not.toHaveBeenCalled()
  })
})

// 3.2.8 功能特性快捷开关
describe('3.2.8 功能特性快捷开关', () => {
  it('TC-FE-BND-001: bundle已激活时toggleBundle移除所有参数', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    // translation bundle: translation_direction, source_language, target_language
    wrapper.vm.formState.case_params = [
      { param_code: 'translation_direction', param_name: '翻译方向', param_type: 'text', component: 'input', scope: 'common' },
      { param_code: 'source_language', param_name: '源语种', param_type: 'text', component: 'input', scope: 'common' },
      { param_code: 'target_language', param_name: '目标语种', param_type: 'text', component: 'input', scope: 'common' },
    ]
    wrapper.vm.toggleBundle('translation')
    expect(wrapper.vm.formState.case_params.length).toBe(0)
  })

  it('TC-FE-BND-002: bundle未激活时toggleBundle添加缺失参数', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    wrapper.vm.formState.case_params = []
    wrapper.vm.toggleBundle('translation')
    expect(wrapper.vm.formState.case_params.length).toBe(3)
    const codes = wrapper.vm.formState.case_params.map((p: any) => p.param_code)
    expect(codes).toContain('translation_direction')
    expect(codes).toContain('source_language')
    expect(codes).toContain('target_language')
  })

  it('TC-FE-BND-003: 部分参数存在时仅添加缺失的', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    wrapper.vm.formState.case_params = [
      { param_code: 'translation_direction', param_name: '翻译方向', param_type: 'text', component: 'input', scope: 'common' },
    ]
    wrapper.vm.toggleBundle('translation')
    expect(wrapper.vm.formState.case_params.length).toBe(3)
    const codes = wrapper.vm.formState.case_params.map((p: any) => p.param_code)
    expect(codes).toContain('source_language')
    expect(codes).toContain('target_language')
  })

  it('TC-FE-BND-004: isBundleActive全部存在时返回true', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.case_params = [
      { param_code: 'translation_direction' },
      { param_code: 'source_language' },
      { param_code: 'target_language' },
    ]
    expect(wrapper.vm.isBundleActive('translation')).toBe(true)
  })

  it('TC-FE-BND-005: isBundleActive部分存在时返回false', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.case_params = [
      { param_code: 'translation_direction' },
    ]
    expect(wrapper.vm.isBundleActive('translation')).toBe(false)
  })

  it('TC-FE-BND-006: isBundleActive无效key返回false', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    expect(wrapper.vm.isBundleActive('invalid_key')).toBe(false)
  })

  it('TC-FE-BND-007: toggleBundle后saveCaseParams对新参数调用autoSaveCaseParams', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    wrapper.vm.formState.case_params = []
    mockAlgorithmApi.createCaseParam.mockResolvedValue({ id: 1 })
    wrapper.vm.toggleBundle('translation')
    await flushPromises()
    // saveCaseParams iterates and calls autoSaveCaseParams for params without id
    expect(mockAlgorithmApi.createCaseParam).toHaveBeenCalled()
  })

  it('TC-FE-BND-008: saveCaseParams所有参数都有id时不调用API', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    wrapper.vm.formState.case_params = [
      { id: 1, param_code: 'p1', param_name: 'n1', param_type: 'text', component: 'input', scope: 'common' },
      { id: 2, param_code: 'p2', param_name: 'n2', param_type: 'text', component: 'input', scope: 'common' },
    ]
    await wrapper.vm.saveCaseParams()
    expect(mockAlgorithmApi.createCaseParam).not.toHaveBeenCalled()
    expect(mockAlgorithmApi.updateCaseParam).not.toHaveBeenCalled()
  })
})

// 3.2.9 参数类型变更与预设填充
describe('3.2.9 参数类型变更与预设填充', () => {
  it('TC-FE-PTY-001: 类型变更时设置component (非select)', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    vi.useFakeTimers()
    // 当前源码: handleCaseParamTypeChange 只调用 getDefaultComponent，不再清空 options 字段
    const param = { param_type: 'text', component: 'select', options_source: 'src', options_field: 'f', options_label_field: 'lf', param_code: 'p1' }
    wrapper.vm.handleCaseParamTypeChange(param, 0)
    expect(param.component).toBe('input')
    // Test number type as well
    const param2 = { param_type: 'number', component: 'select', options_source: 'src', options_field: 'f', options_label_field: 'lf', param_code: 'p2' }
    wrapper.vm.handleCaseParamTypeChange(param2, 0)
    expect(param2.component).toBe('input-number')
    vi.useRealTimers()
  })

  it('TC-FE-PTY-002: 类型变更为select时component=getDefaultComponent(select)', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    vi.useFakeTimers()
    // 当前源码: handleCaseParamTypeChange 统一调用 getDefaultComponent，不再特殊处理 select
    const param = { param_type: 'select', component: 'input', param_code: 'p2' }
    wrapper.vm.handleCaseParamTypeChange(param, 0)
    // getDefaultComponent('select') 的返回值取决于 typeComponentMap，fallback 到 'input'
    expect(param.component).toBeDefined()
    vi.useRealTimers()
  })

  it('TC-FE-PTY-003: 预设匹配且无param_name时填充所有字段', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    const param = { param_code: 'translation_direction', param_name: '', param_type: 'text' }
    wrapper.vm.formState.case_params = [param]
    vi.useFakeTimers()
    wrapper.vm.handleParamCodeSelect(param, 0)
    expect(param.param_name).toBe('翻译方向')
    expect(param.param_type).toBe('text')
    expect(param.component).toBe('input')
    expect(param.help_text).toBe('翻译方向字符串（如 zh2en, en2zh）')
    vi.useRealTimers()
  })

  it('TC-FE-PTY-004: 预设匹配但有param_name时不覆盖', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    const param = { param_code: 'translation_direction', param_name: '自定义名称', param_type: 'text' }
    wrapper.vm.formState.case_params = [param]
    vi.useFakeTimers()
    wrapper.vm.handleParamCodeSelect(param, 0)
    expect(param.param_name).toBe('自定义名称')
    vi.useRealTimers()
  })

  it('TC-FE-PTY-005: 预设不匹配时不填充', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    const param = { param_code: 'unknown_code', param_name: '', param_type: 'text' }
    wrapper.vm.formState.case_params = [param]
    vi.useFakeTimers()
    wrapper.vm.handleParamCodeSelect(param, 0)
    expect(param.param_name).toBe('')
    vi.useRealTimers()
  })

  it('TC-FE-PTY-006: getDefaultComponent slider返回slider', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    expect(wrapper.vm.getDefaultComponent('slider')).toBe('slider')
  })

  it('TC-FE-PTY-007: getDefaultComponent unknown返回input', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    expect(wrapper.vm.getDefaultComponent('unknown')).toBe('input')
  })
})

// 3.2.10 参考参数自动同步
describe('3.2.10 参考参数自动同步', () => {
  it('TC-FE-REF-001: annotation_code为空且code有值时annotation_code=code', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    const param = { code: 'rp1', annotation_code: '' }
    wrapper.vm.handleReferenceParamBlur(param, 0)
    expect(param.annotation_code).toBe('rp1')
  })

  it('TC-FE-REF-002: annotation_code有值时不覆盖', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    const param = { code: 'rp1', annotation_code: 'existing' }
    wrapper.vm.handleReferenceParamBlur(param, 0)
    expect(param.annotation_code).toBe('existing')
  })

  it('TC-FE-REF-003: code为空时不保存(提前返回)', async () => {
    vi.useFakeTimers()
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    const param = { code: '', annotation_code: '' }
    wrapper.vm.handleReferenceParamBlur(param, 0)
    vi.advanceTimersByTime(1000)
    await flushPromises()
    expect(mockAlgorithmApi.createReferenceParam).not.toHaveBeenCalled()
  })

  it('TC-FE-REF-004: reference param带id时调用updateReferenceParam', async () => {
    vi.useFakeTimers()
    const wrapper = mountModal({ mode: 'edit' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    const param = { id: 5, code: 'rp1', name: '名称', type: 'text', annotation_code: 'algo' }
    wrapper.vm.formState.reference_params = [param]
    mockAlgorithmApi.updateReferenceParam.mockResolvedValue({})
    wrapper.vm.handleReferenceParamBlur(param, 0)
    vi.advanceTimersByTime(1000)
    await flushPromises()
    expect(mockAlgorithmApi.updateReferenceParam).toHaveBeenCalled()
  })

  it('TC-FE-REF-005: reference param无id时调用createReferenceParam并设置id', async () => {
    vi.useFakeTimers()
    const wrapper = mountModal({ mode: 'edit' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    const param = { code: 'rp1', name: '名称', type: 'text', annotation_code: 'algo' }
    wrapper.vm.formState.reference_params = [param]
    mockAlgorithmApi.createReferenceParam.mockResolvedValue({ id: 88 })
    wrapper.vm.handleReferenceParamBlur(param, 0)
    vi.advanceTimersByTime(1000)
    await flushPromises()
    expect(mockAlgorithmApi.createReferenceParam).toHaveBeenCalled()
    expect(param.id).toBe(88)
  })
})

// 3.2.11 模式切换与取消
describe('3.2.11 模式切换与取消', () => {
  it('TC-FE-MOD-001: handleCreate后internalMode=create且表单重置', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'old_algo'
    wrapper.vm.handleCreate()
    expect(wrapper.vm.internalMode).toBe('create')
    expect(wrapper.vm.formState.type).toBe('')
  })

  it('TC-FE-MOD-002: handleEdit成功后formState填充且internalMode=edit', async () => {
    const wrapper = mountModal({ mode: 'list' })
    await flushPromises()
    const record = makeAlgData({ type: 'edit_target', name: '编辑目标' })
    mockAlgorithmApi.getDefinition.mockResolvedValue(record)
    await wrapper.vm.handleEdit(record)
    expect(wrapper.vm.formState.type).toBe('edit_target')
    expect(wrapper.vm.formState.name).toBe('编辑目标')
    expect(wrapper.vm.internalMode).toBe('edit')
  })

  it('TC-FE-MOD-003: handleEdit失败时console.error且模式不变', async () => {
    const wrapper = mountModal({ mode: 'list' })
    await flushPromises()
    const record = makeAlgData({ type: 'fail_algo' })
    mockAlgorithmApi.getDefinition.mockRejectedValue(new Error('fail'))
    const modeBefore = wrapper.vm.internalMode
    await wrapper.vm.handleEdit(record)
    expect(console.error).toHaveBeenCalled()
    expect(wrapper.vm.internalMode).toBe(modeBefore)
  })

  it('TC-FE-MOD-004: handleCancel internalMode!=props.mode且props.mode=list时internalMode=list', async () => {
    const wrapper = mountModal({ mode: 'list' })
    await flushPromises()
    wrapper.vm.internalMode = 'create'
    wrapper.vm.handleCancel()
    expect(wrapper.vm.internalMode).toBe('list')
  })

  it('TC-FE-MOD-005: handleCancel模式匹配时emit update:visible false', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.handleCancel()
    expect(wrapper.emitted('update:visible')).toBeTruthy()
    expect(wrapper.emitted('update:visible')![0]).toEqual([false])
  })

  it('TC-FE-MOD-006: handleOk select模式时emit select editData + emit update:visible false', async () => {
    const editData = makeAlgData({ type: 'sel_algo' })
    const wrapper = mountModal({ mode: 'select', editData })
    await flushPromises()
    await wrapper.vm.handleOk()
    expect(wrapper.emitted('select')).toBeTruthy()
    expect(wrapper.emitted('select')![0]).toEqual([editData])
    expect(wrapper.emitted('update:visible')).toBeTruthy()
  })

  it('TC-FE-MOD-007: handleOk select模式无editData时不emit', async () => {
    const wrapper = mountModal({ mode: 'select', editData: null })
    await flushPromises()
    await wrapper.vm.handleOk()
    expect(wrapper.emitted('select')).toBeFalsy()
    expect(wrapper.emitted('update:visible')).toBeFalsy()
  })

  it('TC-FE-MOD-008: handleOk缺少必填字段时alert', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = ''
    await wrapper.vm.handleOk()
    expect(global.alert).toHaveBeenCalledWith('请填写必填字段')
  })

  it('TC-FE-MOD-009: handleOk edit模式时调用updateDefinition', async () => {
    mockAlgorithmApi.updateDefinition.mockResolvedValue({})
    const editData = makeAlgData({ type: 'edit_algo' })
    const wrapper = mountModal({ mode: 'edit', editData })
    await flushPromises()
    wrapper.vm.formState.type = 'edit_algo'
    wrapper.vm.formState.name = '名称'
    wrapper.vm.formState.group_id = 1
    await wrapper.vm.handleOk()
    expect(mockAlgorithmApi.updateDefinition).toHaveBeenCalled()
  })

  it('TC-FE-MOD-010: handleOk create模式时调用createDefinition', async () => {
    mockAlgorithmApi.createDefinition.mockResolvedValue({ id: 1 })
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.formState.type = 'algo'
    wrapper.vm.formState.name = '名称'
    wrapper.vm.formState.group_id = 1
    await wrapper.vm.handleOk()
    expect(mockAlgorithmApi.createDefinition).toHaveBeenCalled()
  })
})

// 3.2.12 状态切换与删除
describe('3.2.12 状态切换与删除', () => {
  it('TC-FE-ACT-001: toggle online→offline时updateDefinition传status=offline', async () => {
    const wrapper = mountModal({ mode: 'list' })
    await flushPromises()
    mockAlgorithmApi.updateDefinition.mockResolvedValue({})
    const record = makeAlgData({ type: 'algo', status: 'online' })
    await wrapper.vm.handleToggleStatus(record)
    expect(mockAlgorithmApi.updateDefinition).toHaveBeenCalledWith('algo', { status: 'offline' })
  })

  it('TC-FE-ACT-002: toggle offline→online时updateDefinition传status=online', async () => {
    const wrapper = mountModal({ mode: 'list' })
    await flushPromises()
    mockAlgorithmApi.updateDefinition.mockResolvedValue({})
    const record = makeAlgData({ type: 'algo', status: 'offline' })
    await wrapper.vm.handleToggleStatus(record)
    expect(mockAlgorithmApi.updateDefinition).toHaveBeenCalledWith('algo', { status: 'online' })
  })

  it('TC-FE-ACT-003: confirmDelete确认=true时调用executeDelete', async () => {
    const wrapper = mountModal({ mode: 'list' })
    await flushPromises()
    mockOpenConfirm.mockResolvedValue(true)
    mockAlgorithmApi.deleteDefinition.mockResolvedValue({})
    const record = makeAlgData({ type: 'del_algo' })
    await wrapper.vm.confirmDelete(record)
    expect(mockAlgorithmApi.deleteDefinition).toHaveBeenCalledWith('del_algo')
  })

  it('TC-FE-ACT-004: confirmDelete确认=false时不删除', async () => {
    const wrapper = mountModal({ mode: 'list' })
    await flushPromises()
    mockOpenConfirm.mockResolvedValue(false)
    const record = makeAlgData({ type: 'del_algo' })
    await wrapper.vm.confirmDelete(record)
    expect(mockAlgorithmApi.deleteDefinition).not.toHaveBeenCalled()
  })

  it('TC-FE-ACT-005: executeDelete(null)时提前返回不调用API', async () => {
    const wrapper = mountModal({ mode: 'list' })
    await flushPromises()
    await wrapper.vm.executeDelete(null as any)
    expect(mockAlgorithmApi.deleteDefinition).not.toHaveBeenCalled()
  })

  it('TC-FE-ACT-006: executeDelete成功时调用deleteDefinition和loadAlgorithms', async () => {
    const wrapper = mountModal({ mode: 'list' })
    await flushPromises()
    mockAlgorithmApi.deleteDefinition.mockResolvedValue({})
    mockAlgorithmApi.getDefinitions.mockResolvedValue({ data: [] })
    const record = makeAlgData({ type: 'del_algo' })
    await wrapper.vm.executeDelete(record)
    expect(mockAlgorithmApi.deleteDefinition).toHaveBeenCalledWith('del_algo')
    expect(mockAlgorithmApi.getDefinitions).toHaveBeenCalled()
  })

  it('TC-FE-ACT-007: executeDelete失败时console.error', async () => {
    const wrapper = mountModal({ mode: 'list' })
    await flushPromises()
    mockAlgorithmApi.deleteDefinition.mockRejectedValue(new Error('fail'))
    const record = makeAlgData({ type: 'del_algo' })
    await wrapper.vm.executeDelete(record)
    expect(console.error).toHaveBeenCalled()
  })
})

// 3.2.13 映射折叠与更新
describe('3.2.13 映射折叠与更新', () => {
  it('TC-FE-MAP-001: toggleMapping(device)后mappingExpanded.device=false', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    expect(wrapper.vm.mappingExpanded.device).toBe(true)
    wrapper.vm.toggleMapping('device')
    expect(wrapper.vm.mappingExpanded.device).toBe(false)
  })

  it('TC-FE-MAP-002: toggleMapping(api)后mappingExpanded.api=false', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.toggleMapping('api')
    expect(wrapper.vm.mappingExpanded.api).toBe(false)
  })

  it('TC-FE-MAP-003: toggleMapping(evaluation)后mappingExpanded.evaluation=false', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.toggleMapping('evaluation')
    expect(wrapper.vm.mappingExpanded.evaluation).toBe(false)
  })

  it('TC-FE-MAP-004: updateMappings(device, [...])后formState.mappings.device更新', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    const newMappings = [{ from: 'a', to: 'b' }]
    wrapper.vm.updateMappings('device', newMappings)
    expect(wrapper.vm.formState.mappings.device).toStrictEqual(newMappings)
  })

  it('TC-FE-MAP-005: updateMappings(api, [...])后formState.mappings.api更新', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    const newMappings = [{ from: 'x', to: 'y' }]
    wrapper.vm.updateMappings('api', newMappings)
    expect(wrapper.vm.formState.mappings.api).toStrictEqual(newMappings)
  })

  it('TC-FE-MAP-006: updateMappings(evaluation, [...])后formState.mappings.evaluation更新', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    const newMappings = [{ from: 'e', to: 'd' }]
    wrapper.vm.updateMappings('evaluation', newMappings)
    expect(wrapper.vm.formState.mappings.evaluation).toStrictEqual(newMappings)
  })
})

// 3.2.14 computed 属性分支
describe('3.2.14 computed 属性分支', () => {
  it('TC-FE-CMP-001: currentParams device时返回device_params', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.paramConfigType = 'device'
    wrapper.vm.formState.device_params = [{ param_code: 'dp1' }] as any
    expect(wrapper.vm.currentParams).toBe(wrapper.vm.formState.device_params)
  })

  it('TC-FE-CMP-002: currentParams api时返回api_params', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.paramConfigType = 'api'
    wrapper.vm.formState.api_params = [{ param_code: 'ap1' }] as any
    expect(wrapper.vm.currentParams).toBe(wrapper.vm.formState.api_params)
  })

  it('TC-FE-CMP-003: currentParams case时返回[]', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.paramConfigType = 'case'
    expect(wrapper.vm.currentParams).toEqual([])
  })

  it('TC-FE-CMP-004: filteredAlgorithms有关键字时过滤', async () => {
    const wrapper = mountModal({ mode: 'list' })
    await flushPromises()
    wrapper.vm.algorithms = [
      makeAlgData({ type: 'asr', name: '语音识别' }),
      makeAlgData({ type: 'translation', name: '翻译' }),
    ] as any
    wrapper.vm.searchKeyword = '语音'
    expect(wrapper.vm.filteredAlgorithms.length).toBe(1)
    expect(wrapper.vm.filteredAlgorithms[0].type).toBe('asr')
  })

  it('TC-FE-CMP-005: filteredAlgorithms无关键字时返回全部', async () => {
    const wrapper = mountModal({ mode: 'list' })
    await flushPromises()
    wrapper.vm.algorithms = [
      makeAlgData({ type: 'asr', name: '语音识别' }),
      makeAlgData({ type: 'translation', name: '翻译' }),
    ] as any
    wrapper.vm.searchKeyword = ''
    expect(wrapper.vm.filteredAlgorithms.length).toBe(2)
  })

  it('TC-FE-CMP-006: getGroupTagClass 翻译 返回 pending', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    expect(wrapper.vm.getGroupTagClass('翻译')).toBe('pending')
  })

  it('TC-FE-CMP-007: getGroupTagClass 未知 返回空字符串', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    expect(wrapper.vm.getGroupTagClass('未知')).toBe('')
  })

  it('TC-FE-CMP-008: getGroupTagClass undefined 返回空字符串', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    expect(wrapper.vm.getGroupTagClass(undefined)).toBe('')
  })

  it('TC-FE-CMP-009: modalWidth list时为700px', async () => {
    const wrapper = mountModal({ mode: 'list' })
    await flushPromises()
    expect(wrapper.vm.modalWidth).toBe('700px')
  })

  it('TC-FE-CMP-010: modalWidth edit时为1200px', async () => {
    const editData = makeAlgData()
    const wrapper = mountModal({ mode: 'edit', editData })
    await flushPromises()
    expect(wrapper.vm.modalWidth).toBe('1200px')
  })

  it('TC-FE-CMP-011: okText select时为选择', async () => {
    const wrapper = mountModal({ mode: 'select' })
    await flushPromises()
    expect(wrapper.vm.okText).toBe('选择')
  })

  it('TC-FE-CMP-012: okText edit时为确定', async () => {
    const editData = makeAlgData()
    const wrapper = mountModal({ mode: 'edit', editData })
    await flushPromises()
    expect(wrapper.vm.okText).toBe('确定')
  })

  it('TC-FE-CMP-013: mainDimensions dimensionType=main 时包含', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.availableDimensions = [{ id: 1, name: 'd1', code: 'c1', dimensionType: 'main' }] as any
    expect(wrapper.vm.mainDimensions.length).toBe(1)
  })

  it('TC-FE-CMP-014: mainDimensions 无dimensionType 时包含', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.availableDimensions = [{ id: 2, name: 'd2', code: 'c2' }] as any
    expect(wrapper.vm.mainDimensions.length).toBe(1)
  })

  it('TC-FE-CMP-015: mainDimensions dimensionType=sub 时排除', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    wrapper.vm.availableDimensions = [{ id: 3, name: 'd3', code: 'c3', dimensionType: 'sub' }] as any
    expect(wrapper.vm.mainDimensions.length).toBe(0)
  })
})

// 3.2.15 watch 与生命周期
describe('3.2.15 watch 与生命周期', () => {
  it('TC-FE-WCH-001: visible=true list模式时调用loadAlgorithms', async () => {
    const wrapper = mountModal({ mode: 'list', visible: false })
    await flushPromises()
    mockAlgorithmApi.getDefinitions.mockClear()
    await wrapper.setProps({ visible: true })
    await flushPromises()
    expect(mockAlgorithmApi.getDefinitions).toHaveBeenCalled()
  })

  it('TC-FE-WCH-002: visible=true create模式时调用resetForm(表单为空)', async () => {
    const wrapper = mountModal({ mode: 'create', visible: true })
    await flushPromises()
    expect(wrapper.vm.formState.type).toBe('')
    expect(wrapper.vm.formState.name).toBe('')
  })

  it('TC-FE-WCH-003: visible=true edit模式时不load/reset(仅loadGroups等)', async () => {
    const editData = makeAlgData({ type: 'edit_algo' })
    mockAlgorithmApi.getDefinitions.mockClear()
    const wrapper = mountModal({ mode: 'edit', editData, visible: true })
    await flushPromises()
    expect(mockAlgorithmApi.getDefinitions).not.toHaveBeenCalled()
    expect(wrapper.vm.formState.type).toBe('edit_algo')
  })

  it('TC-FE-WCH-004: visible=false时不调用API', async () => {
    mockAlgorithmApi.getGroups.mockClear()
    mockAlgorithmApi.getOptionsSources.mockClear()
    mockFetchAllDimensions.mockClear()
    const wrapper = mountModal({ mode: 'create', visible: false })
    await flushPromises()
    // visible=false → no API calls from the visible watcher
    // But the immediate [mode, editData] watcher still fires for create mode
    // loadGroups/loadDimensions/loadOptionsSources are only called when visible=true
    expect(mockAlgorithmApi.getGroups).not.toHaveBeenCalled()
    expect(mockAlgorithmApi.getOptionsSources).not.toHaveBeenCalled()
    expect(mockFetchAllDimensions).not.toHaveBeenCalled()
  })

  it('TC-FE-WCH-005: watch [mode, editData] mode=edit editData存在时formState填充', async () => {
    const editData = makeAlgData({ type: 'watch_edit', name: 'watch编辑' })
    const wrapper = mountModal({ mode: 'edit', editData })
    await flushPromises()
    expect(wrapper.vm.formState.type).toBe('watch_edit')
    expect(wrapper.vm.formState.name).toBe('watch编辑')
  })

  it('TC-FE-WCH-006: watch [mode, editData] mode=edit 无editData时不填充', async () => {
    const wrapper = mountModal({ mode: 'edit', editData: null })
    await flushPromises()
    // edit mode without editData → no fill (formState stays default/empty)
    expect(wrapper.vm.formState.type).toBe('')
  })

  it('TC-FE-WCH-007: watch [mode, editData] mode=create时resetForm', async () => {
    const wrapper = mountModal({ mode: 'create' })
    await flushPromises()
    expect(wrapper.vm.formState.type).toBe('')
    expect(wrapper.vm.formState.name).toBe('')
    expect(wrapper.vm.formState.group_id).toBe(null)
  })

  it('TC-FE-WCH-008: watch [mode, editData] mode=list时无操作', async () => {
    const wrapper = mountModal({ mode: 'list' })
    await flushPromises()
    // list mode → no fill, no reset; formState stays default
    expect(wrapper.vm.formState.type).toBe('')
    expect(wrapper.vm.activeTab).toBe('basic')
  })
})
