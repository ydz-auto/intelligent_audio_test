/**
 * INT-293：SPL 图表翻页重绘 + 列表截断提示。
 *
 * 锁定契约：
 * 1. 翻页只改变 paginatedMappings、不改变 filteredMappings 时，initCharts 也会被重新触发
 *    （第 2 页 canvas 不再空白）——initModalWatchers 注册 paginatedMappings watch，翻页后重绘。
 * 2. searchMappings 记录服务端 total；超过 SPL_MAPPING_FETCH_LIMIT(100) 时
 *    mappingListTruncated 置位（列表不再静默截断，页面给出提示）。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { nextTick } from 'vue'

const splPort = vi.hoisted(() => ({ getAll: vi.fn(), getStats: vi.fn() }))
const playbackPort = vi.hoisted(() => ({ getAll: vi.fn() }))
const notifications = vi.hoisted(() => ({ error: vi.fn(), show: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() }))
const chartCtor = vi.hoisted(() => vi.fn())
const chartDestroy = vi.hoisted(() => vi.fn())

vi.mock('@/composables/device/splPort', () => ({ splPort }))
vi.mock('@/composables/device/playbackPort', () => ({ playbackPort }))
vi.mock('@/composables/modal/useNotification', () => ({ useNotification: () => notifications }))
vi.mock('@/composables/modal/useModal', () => ({
  getModalManager: () => ({ open: vi.fn(), close: vi.fn(), closeAll: vi.fn(), getActiveModals: () => [], updateModalProps: vi.fn(), registerModal: vi.fn() }),
  provideModal: vi.fn(),
}))
vi.mock('@/composables/modal/constants', () => ({
  MODAL_TYPES: { CRUD_FORM: 'CRUD_FORM', DETAIL_VIEW: 'DETAIL_VIEW', DELETE_CONFIRM: 'DELETE_CONFIRM', IMPORT_EXPORT: 'IMPORT_EXPORT' },
}))
vi.mock('chart.js/auto', () => ({
  default: class ChartMock {
    destroy() { chartDestroy() }
    constructor(...args: any[]) { chartCtor(...args) }
  },
}))

import { useSplMapping, SPL_MAPPING_FETCH_LIMIT } from '../useSplMapping'

/** 构造带 id 标记的假 canvas（getContext 返回对象携带 __canvasId，供断言 Chart 绑定到哪个画布） */
function fakeCanvas(id: string) {
  const ctx: any = { __canvasId: id }
  const canvas: any = { id, parentElement: {} }
  canvas.getContext = vi.fn(() => ctx)
  canvas.getBoundingClientRect = vi.fn(() => ({ width: 300, height: 150 }))
  return canvas
}

beforeEach(() => {
  vi.clearAllMocks()
  splPort.getAll.mockResolvedValue({ items: [], total: 0 })
  splPort.getStats.mockResolvedValue({ total: 0, calibrated: 0, uncalibrated: 0, associatedDevices: 0 })
  playbackPort.getAll.mockResolvedValue([])
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('useSplMapping 翻页重绘（INT-293）', () => {
  it('翻页改变 paginatedMappings 时触发 initCharts，为第 2 页映射重建图表', async () => {
    // 7 条映射、默认每页 6 条 → 第 2 页只有 1 条（模拟 >6 条时的翻页场景）
    const items = Array.from({ length: 7 }, (_, i) => ({
      id: i + 1,
      name: `m${i + 1}`,
      calibrationStatus: 'uncalibrated',
    }))
    const canvasById = new Map<string, any>()
    items.forEach(m => canvasById.set(`chart-${m.id}`, fakeCanvas(`chart-${m.id}`)))

    // 模拟 v-for 按当前页渲染：仅可见页的 canvas 存在于 DOM
    const visibleIds = new Set<string>()
    document.getElementById = vi.fn((id: string) => (visibleIds.has(id) ? canvasById.get(id) : null)) as any
    const container = document.createElement('div')
    container.className = 'spl-mapping-view'
    document.body.appendChild(container)

    const view = useSplMapping()
    view.mappingData.value = items as any

    view.initModalWatchers()

    // 第 2 页：仅 chart-7 可见 → 翻页后应为该 canvas 创建图表
    visibleIds.clear()
    visibleIds.add('chart-7')
    view.handlePageChange(2)
    await nextTick() // watcher 触发 → 调度 initCharts
    await nextTick() // initCharts 内 await nextTick 后开始创建
    await nextTick() // initCharts 主体完成

    const createdCanvasIds = chartCtor.mock.calls.map(c => c[0]?.__canvasId).filter(Boolean)
    expect(createdCanvasIds).toContain('chart-7')
  })
})

describe('useSplMapping 列表截断提示（INT-293）', () => {
  it('服务端 total 超过 SPL_MAPPING_FETCH_LIMIT 时 mappingListTruncated 置位', async () => {
    const view = useSplMapping()
    splPort.getAll.mockResolvedValue({
      items: Array.from({ length: SPL_MAPPING_FETCH_LIMIT }, (_, i) => ({ id: i + 1, name: `m${i + 1}` })),
      total: SPL_MAPPING_FETCH_LIMIT + 50,
    })

    await view.searchMappings()

    expect(view.mappingTotal.value).toBe(SPL_MAPPING_FETCH_LIMIT + 50)
    expect(view.mappingListTruncated.value).toBe(true)
  })

  it('服务端 total 未超过上限时 mappingListTruncated 为 false', async () => {
    const view = useSplMapping()
    splPort.getAll.mockResolvedValue({ items: [{ id: 1, name: 'm1' }], total: 1 })

    await view.searchMappings()

    expect(view.mappingTotal.value).toBe(1)
    expect(view.mappingListTruncated.value).toBe(false)
  })
})
