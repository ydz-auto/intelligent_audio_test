// -*- coding: utf-8 -*-
/**
 * AlgorithmConfigPage.vue 组件单元测试
 *
 * 覆盖：列表加载、搜索过滤、分页、CRUD操作、Tab切换、详情视图、normalizeAlgorithmFields
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'

// Mock fetch
const mockFetch = vi.fn()
global.fetch = mockFetch as any

// Mock window.alert
global.alert = vi.fn()

// Mock console.error (re-created in beforeEach)
let consoleErrorSpy: any

// Mock AlgorithmConfigModal 组件（避免渲染复杂子组件）
// vi.mock 路径相对于测试文件解析；组件从 src/views/ 导入 '../components/algorithm/...'
// 从测试文件 src/components/algorithm/__tests__/ 到 src/components/algorithm/ 是 '../../algorithm/'
// 但 vi.mock 需要匹配组件中使用的模块说明符解析后的路径
vi.mock('../../../components/algorithm/AlgorithmConfigModal.vue', () => ({
  default: defineComponent({
    name: 'AlgorithmConfigModal',
    props: ['visible', 'mode', 'editData'],
    emits: ['update:visible', 'select', 'success'],
    template: '<div class="mock-modal" v-if="visible"></div>',
  }),
}))

// Mock PaginationComponent
vi.mock('../../../components/common/data/PaginationComponent.vue', () => ({
  default: defineComponent({
    name: 'PaginationComponent',
    props: ['currentPage', 'pageSize', 'totalItems'],
    emits: ['prev-page', 'next-page', 'go-to-page', 'page-size-change'],
    template: '<div class="mock-pagination"></div>',
  }),
}))

// Mock useModalControl — 组件从 src/views/ 导入 '../composables/modal/useModal' → src/composables/modal/useModal
// 从测试文件 src/components/algorithm/__tests__/ 到 src/composables/modal/useModal 是 '../../../composables/modal/useModal'
const mockOpenConfirm = vi.fn()
vi.mock('../../../composables/modal/useModal', () => ({
  useModalControl: () => ({
    open: mockOpenConfirm,
  }),
  MODAL_TYPES: { BASIC_CONFIRM: 'basicConfirm' },
}))

// 导入被测组件
import AlgorithmConfigPage from '../../../views/AlgorithmConfig/AlgorithmConfigPage.vue'

// 辅助函数
function makeOkResponse(body: any) {
  return { ok: true, json: async () => body }
}

function successData(data: any, total?: number) {
  return { success: true, data: total !== undefined ? { data, total } : data }
}

beforeEach(() => {
  // resetAllMocks 清除调用历史、实现和 once-queue，避免测试间状态泄漏
  vi.resetAllMocks()
  // 重新设置全局 mock
  global.fetch = mockFetch as any
  global.alert = vi.fn()
  mockOpenConfirm.mockResolvedValue(false) // 默认取消
  consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  if (consoleErrorSpy) {
    consoleErrorSpy.mockRestore()
  }
})

describe('AlgorithmConfigPage - 列表加载与渲染', () => {
  it('TC-FE-PG-001: onMounted 加载', async () => {
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([], 0)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    mount(AlgorithmConfigPage)
    await flushPromises()
    // 两个 API 调用：loadAlgorithms + loadGroups
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('TC-FE-PG-002: loadAlgorithms 成功', async () => {
    const algos = [{ type: 'asr', name: 'ASR', status: 'online' }]
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData(algos, 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    expect(wrapper.text()).toContain('asr')
    expect(wrapper.text()).toContain('ASR')
  })

  it('TC-FE-PG-003: loadAlgorithms 失败-success=false', async () => {
    mockFetch.mockResolvedValueOnce(makeOkResponse({ success: false, message: 'error' }))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    // 列表为空
    expect(wrapper.text()).toContain('暂无数据')
  })

  it('TC-FE-PG-004: loadAlgorithms 网络错误', async () => {
    mockFetch.mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    expect(console.error).toHaveBeenCalled()
  })

  it('TC-FE-PG-007: loading状态显示', async () => {
    let resolveFetch: any
    mockFetch.mockReturnValueOnce(new Promise(resolve => { resolveFetch = resolve }))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await nextTick()
    expect(wrapper.text()).toContain('加载中')
    resolveFetch(makeOkResponse(successData([], 0)))
    await flushPromises()
  })

  it('TC-FE-PG-008: 空数据显示', async () => {
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([], 0)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    expect(wrapper.text()).toContain('暂无数据')
  })

  it('TC-FE-PG-009: 有数据渲染表格行', async () => {
    const algos = [{ type: 'asr', name: 'ASR', status: 'online', group_name: '翻译' }]
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData(algos, 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    const rows = wrapper.findAll('tbody tr')
    expect(rows.length).toBeGreaterThan(0)
  })
})

describe('AlgorithmConfigPage - 搜索与过滤', () => {
  it('TC-FE-PG-010: 按类型搜索', async () => {
    const algos = [
      { type: 'asr', name: 'ASR', status: 'online' },
      { type: 'tts', name: 'TTS', status: 'online' },
    ]
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData(algos, 2)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    const input = wrapper.find('.search-input')
    await input.setValue('asr')
    await input.trigger('input')
    await nextTick()
    expect(wrapper.text()).toContain('asr')
    expect(wrapper.text()).not.toContain('tts')
  })

  it('TC-FE-PG-011: 按名称搜索', async () => {
    const algos = [
      { type: 'asr', name: '语音识别', status: 'online' },
      { type: 'tts', name: '语音合成', status: 'online' },
    ]
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData(algos, 2)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    const input = wrapper.find('.search-input')
    await input.setValue('识别')
    await input.trigger('input')
    await nextTick()
    expect(wrapper.text()).toContain('语音识别')
    expect(wrapper.text()).not.toContain('语音合成')
  })

  it('TC-FE-PG-012: 无搜索词返回全部', async () => {
    const algos = [
      { type: 'asr', name: 'ASR', status: 'online' },
      { type: 'tts', name: 'TTS', status: 'online' },
    ]
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData(algos, 2)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    const rows = wrapper.findAll('tbody tr')
    expect(rows.length).toBe(2)
  })

  it('TC-FE-PG-017: 搜索重置页码', async () => {
    const algos = Array.from({ length: 15 }, (_, i) => ({ type: `algo${i}`, name: `算法${i}`, status: 'online' }))
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData(algos, 15)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    // 跳到第2页
    wrapper.vm.handleNextPage()
    await nextTick()
    expect(wrapper.vm.currentPage).toBe(2)
    // 搜索重置
    const input = wrapper.find('.search-input')
    await input.setValue('algo0')
    await input.trigger('input')
    await nextTick()
    expect(wrapper.vm.currentPage).toBe(1)
  })
})

describe('AlgorithmConfigPage - 分页', () => {
  it('TC-FE-PG-019: 上一页（非第一页）', async () => {
    const algos = Array.from({ length: 15 }, (_, i) => ({ type: `a${i}`, name: `n${i}`, status: 'online' }))
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData(algos, 15)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    wrapper.vm.handleNextPage()
    await nextTick()
    expect(wrapper.vm.currentPage).toBe(2)
    wrapper.vm.handlePrevPage()
    await nextTick()
    expect(wrapper.vm.currentPage).toBe(1)
  })

  it('TC-FE-PG-020: 上一页（第一页不变）', async () => {
    const algos = [{ type: 'asr', name: 'ASR', status: 'online' }]
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData(algos, 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    wrapper.vm.handlePrevPage()
    await nextTick()
    expect(wrapper.vm.currentPage).toBe(1)
  })

  it('TC-FE-PG-021: 下一页（非最后页）', async () => {
    const algos = Array.from({ length: 15 }, (_, i) => ({ type: `a${i}`, name: `n${i}`, status: 'online' }))
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData(algos, 15)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    wrapper.vm.handleNextPage()
    await nextTick()
    expect(wrapper.vm.currentPage).toBe(2)
  })

  it('TC-FE-PG-022: 下一页（最后页不变）', async () => {
    const algos = [{ type: 'asr', name: 'ASR', status: 'online' }]
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData(algos, 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    wrapper.vm.handleNextPage()
    await nextTick()
    expect(wrapper.vm.currentPage).toBe(1)
  })

  it('TC-FE-PG-023: 跳转指定页', async () => {
    const algos = Array.from({ length: 25 }, (_, i) => ({ type: `a${i}`, name: `n${i}`, status: 'online' }))
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData(algos, 25)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    wrapper.vm.handleGoToPage(3)
    await nextTick()
    expect(wrapper.vm.currentPage).toBe(3)
  })

  it('TC-FE-PG-024: 修改每页条数', async () => {
    const algos = [{ type: 'asr', name: 'ASR', status: 'online' }]
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData(algos, 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    wrapper.vm.handlePageSizeChange(20)
    await nextTick()
    expect(wrapper.vm.pageSize).toBe(20)
    expect(wrapper.vm.currentPage).toBe(1)
  })
})

describe('AlgorithmConfigPage - CRUD操作', () => {
  it('TC-FE-PG-027: 新建算法', async () => {
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([], 0)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    wrapper.vm.handleCreate()
    await nextTick()
    expect(wrapper.vm.modalMode).toBe('create')
    expect(wrapper.vm.currentAlgorithm).toBeNull()
    expect(wrapper.vm.modalVisible).toBe(true)
  })

  it('TC-FE-PG-028: 编辑算法', async () => {
    const algo = { type: 'asr', name: 'ASR', status: 'online', group_name: '翻译' }
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([algo], 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    wrapper.vm.handleEdit(algo)
    await flushPromises()
    expect(wrapper.vm.modalMode).toBe('edit')
    expect(wrapper.vm.modalVisible).toBe(true)
  })

  it('TC-FE-PG-029: loadAlgorithmDetail 成功', async () => {
    const algo = { type: 'asr', name: 'ASR', status: 'online' }
    const detail = { type: 'asr', name: 'ASR', status: 'online', device_params: [] }
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([algo], 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
      .mockResolvedValueOnce(makeOkResponse(successData(detail)))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    await wrapper.vm.loadAlgorithmDetail('asr')
    expect(wrapper.vm.currentAlgorithm).toBeTruthy()
    expect(wrapper.vm.currentAlgorithm.type).toBe('asr')
  })

  it('TC-FE-PG-030: loadAlgorithmDetail 失败', async () => {
    const algo = { type: 'asr', name: 'ASR', status: 'online' }
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([algo], 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
      .mockResolvedValueOnce(makeOkResponse({ success: false }))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    const before = wrapper.vm.currentAlgorithm
    await wrapper.vm.loadAlgorithmDetail('asr')
    // currentAlgorithm 不应被更新
    expect(wrapper.vm.currentAlgorithm).toBe(before)
  })

  it('TC-FE-PG-031: 复制算法-确认', async () => {
    mockOpenConfirm.mockResolvedValueOnce(true)
    const algo = { type: 'asr', name: 'ASR', status: 'online' }
    const detail = { type: 'asr', name: 'ASR', status: 'online' }
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([algo], 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
      .mockResolvedValueOnce(makeOkResponse(successData(detail)))
      .mockResolvedValueOnce(makeOkResponse(successData({})))
      .mockResolvedValueOnce(makeOkResponse(successData([], 0)))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    await wrapper.vm.handleClone(algo)
    await flushPromises()
    // 复制后应调用 loadAlgorithms
    expect(mockFetch).toHaveBeenCalledTimes(5)
  })

  it('TC-FE-PG-032: 复制算法-取消', async () => {
    mockOpenConfirm.mockResolvedValueOnce(false)
    const algo = { type: 'asr', name: 'ASR', status: 'online' }
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([algo], 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    await wrapper.vm.handleClone(algo)
    await flushPromises()
    // 取消后不应再调用 API
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('TC-FE-PG-037: 删除-确认', async () => {
    mockOpenConfirm.mockResolvedValueOnce(true)
    const algo = { type: 'asr', name: 'ASR', status: 'online' }
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([algo], 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
      .mockResolvedValueOnce(makeOkResponse(successData({})))
      .mockResolvedValueOnce(makeOkResponse(successData([], 0)))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    await wrapper.vm.confirmDelete(algo)
    await flushPromises()
    expect(mockFetch).toHaveBeenCalledTimes(4)
  })

  it('TC-FE-PG-038: 删除-取消', async () => {
    mockOpenConfirm.mockResolvedValueOnce(false)
    const algo = { type: 'asr', name: 'ASR', status: 'online' }
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([algo], 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    await wrapper.vm.confirmDelete(algo)
    await flushPromises()
    // 取消删除后不应有额外 API 调用
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('TC-FE-PG-039: executeDelete record为空', async () => {
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([], 0)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    await wrapper.vm.executeDelete(null)
    // 不应有删除 API 调用
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('TC-FE-PG-040: 删除成功且在详情页', async () => {
    mockOpenConfirm.mockResolvedValueOnce(true)
    const algo = { type: 'asr', name: 'ASR', status: 'online' }
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([algo], 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
      .mockResolvedValueOnce(makeOkResponse(successData({})))
      .mockResolvedValueOnce(makeOkResponse(successData([], 0)))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    // 切换到详情页
    wrapper.vm.activeTab = 'detail'
    await nextTick()
    await wrapper.vm.confirmDelete(algo)
    await flushPromises()
    // 删除后应切回列表
    expect(wrapper.vm.activeTab).toBe('list')
  })

  it('TC-FE-PG-041: 删除成功且在列表页', async () => {
    mockOpenConfirm.mockResolvedValueOnce(true)
    const algo = { type: 'asr', name: 'ASR', status: 'online' }
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([algo], 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
      .mockResolvedValueOnce(makeOkResponse(successData({})))
      .mockResolvedValueOnce(makeOkResponse(successData([], 0)))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    // 已在列表页
    expect(wrapper.vm.activeTab).toBe('list')
    await wrapper.vm.confirmDelete(algo)
    await flushPromises()
    expect(wrapper.vm.activeTab).toBe('list')
  })

  it('TC-FE-PG-042: 删除失败', async () => {
    mockOpenConfirm.mockResolvedValueOnce(true)
    const algo = { type: 'asr', name: 'ASR', status: 'online' }
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([algo], 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
      .mockResolvedValueOnce(makeOkResponse({ success: false, message: 'fail' }))
      .mockResolvedValueOnce(makeOkResponse(successData([], 0)))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    await wrapper.vm.confirmDelete(algo)
    await flushPromises()
    expect(console.error).toHaveBeenCalled()
  })
})

describe('AlgorithmConfigPage - Tab切换与详情视图', () => {
  it('TC-FE-PG-043: 切换到list清除currentAlgorithm', async () => {
    const algo = { type: 'asr', name: 'ASR', status: 'online' }
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([algo], 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    wrapper.vm.currentAlgorithm = algo as any
    wrapper.vm.handleTabChange('list')
    await nextTick()
    expect(wrapper.vm.currentAlgorithm).toBeNull()
  })

  it('TC-FE-PG-044: 切换到detail保留currentAlgorithm', async () => {
    const algo = { type: 'asr', name: 'ASR', status: 'online' }
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([algo], 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    wrapper.vm.currentAlgorithm = algo as any
    wrapper.vm.handleTabChange('detail')
    await nextTick()
    expect(wrapper.vm.currentAlgorithm).toEqual(algo)
  })

  it('TC-FE-PG-047: group_name有值显示标签', async () => {
    const algos = [{ type: 'asr', name: 'ASR', status: 'online', group_name: '翻译' }]
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData(algos, 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    expect(wrapper.text()).toContain('翻译')
  })

  it('TC-FE-PG-048: group_name为空显示横线', async () => {
    const algos = [{ type: 'asr', name: 'ASR', status: 'online' }]
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData(algos, 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    expect(wrapper.text()).toContain('-')
  })

  it('TC-FE-PG-049: status=online显示上线', async () => {
    const algos = [{ type: 'asr', name: 'ASR', status: 'online' }]
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData(algos, 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    expect(wrapper.text()).toContain('上线')
  })

  it('TC-FE-PG-050: status=offline显示下线', async () => {
    const algos = [{ type: 'asr', name: 'ASR', status: 'offline' }]
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData(algos, 1)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    expect(wrapper.text()).toContain('下线')
  })
})

describe('AlgorithmConfigPage - normalizeAlgorithmFields', () => {
  it('TC-FE-PG-058: camelCase字段优先', async () => {
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([], 0)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    const result = wrapper.vm.normalizeAlgorithmFields({
      groupId: 1,
      groupName: '翻译',
      displayOrder: 5,
      deviceParams: [{ param_code: 'a' }],
      apiParams: [],
      caseParams: [],
    })
    expect(result.group_id).toBe(1)
    expect(result.group_name).toBe('翻译')
    expect(result.display_order).toBe(5)
    expect(result.device_params).toHaveLength(1)
  })

  it('TC-FE-PG-059: snake_case字段回退', async () => {
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([], 0)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    const result = wrapper.vm.normalizeAlgorithmFields({
      group_id: 2,
      group_name: '识别',
      display_order: 3,
      device_params: [],
      api_params: [],
      case_params: [],
    })
    expect(result.group_id).toBe(2)
    expect(result.group_name).toBe('识别')
    expect(result.display_order).toBe(3)
  })

  it('TC-FE-PG-060: mappings缺失使用默认空对象', async () => {
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([], 0)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    const result = wrapper.vm.normalizeAlgorithmFields({})
    expect(result.mappings).toEqual({ device: [], api: [], evaluation: [] })
  })
})

describe('AlgorithmConfigPage - getGroupName', () => {
  it('TC-FE-PG-055: 已知分组', async () => {
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([], 0)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    expect(wrapper.vm.getGroupName('basic')).toBe('基本配置')
    expect(wrapper.vm.getGroupName('model')).toBe('模型配置')
    expect(wrapper.vm.getGroupName('advanced')).toBe('高级选项')
  })

  it('TC-FE-PG-056: 未知分组', async () => {
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([], 0)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    expect(wrapper.vm.getGroupName('unknown')).toBe('unknown')
  })

  it('TC-FE-PG-057: 空分组返回横线', async () => {
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData([], 0)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    expect(wrapper.vm.getGroupName(undefined)).toBe('-')
  })
})

describe('AlgorithmConfigPage - 过滤重置页码', () => {
  it('TC-FE-PG-018: 过滤重置页码', async () => {
    const algos = Array.from({ length: 15 }, (_, i) => ({ type: `a${i}`, name: `n${i}`, status: 'online' }))
    mockFetch.mockResolvedValueOnce(makeOkResponse(successData(algos, 15)))
      .mockResolvedValueOnce(makeOkResponse(successData([])))
    const wrapper = mount(AlgorithmConfigPage)
    await flushPromises()
    wrapper.vm.handleNextPage()
    await nextTick()
    expect(wrapper.vm.currentPage).toBe(2)
    wrapper.vm.handleFilter()
    await nextTick()
    expect(wrapper.vm.currentPage).toBe(1)
  })
})
