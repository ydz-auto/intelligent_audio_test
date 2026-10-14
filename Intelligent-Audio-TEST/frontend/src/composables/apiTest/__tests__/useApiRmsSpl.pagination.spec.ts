/**
 * INT-330 缺陷3：API RMS-SPL 映射列表分页 —— composable 单测。
 *
 * 锁定口径：
 * - 后端 per_page 钳制上限 100（rms_spl_query_service），前端按 total 循环翻页取全量，
 *   映射 >100 条不再静默截断
 * - total 虚报/空页时防御性终止，不无限拉取
 * - 客户端分页对齐设备侧：usePagination 切片 + 页码/页大小方法
 * - 服务端过滤参数（apiId/calibrationStatus）透传到每一页
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mocks = vi.hoisted(() => ({
  rmsGetAll: vi.fn(),
  apisGetAll: vi.fn(),
}))

vi.mock('../apiRmsSplPort', () => ({
  apiRmsSplPort: { getAll: mocks.rmsGetAll },
}))

vi.mock('../apisPort', () => ({
  apisPort: { getAll: mocks.apisGetAll },
}))

vi.mock('../../modal/useModal', () => ({
  getModalManager: vi.fn(() => ({ open: vi.fn(), close: vi.fn() })),
}))

vi.mock('../../modal/constants', () => ({
  MODAL_TYPES: {
    CRUD_FORM: 'CRUD_FORM',
    DETAIL_VIEW: 'DETAIL_VIEW',
    DELETE_CONFIRM: 'DELETE_CONFIRM',
    API_RMS_SPL_CALIBRATION: 'API_RMS_SPL_CALIBRATION',
  },
}))

vi.mock('../../modal/useNotification', () => ({
  useNotification: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}))

import { useApiRmsSpl } from '../useApiRmsSpl'

const makeItems = (n: number, startId = 1) =>
  Array.from({ length: n }, (_, i) => ({
    id: startId + i,
    apiId: 1,
    name: `映射 ${startId + i}`,
    calibrationStatus: 'uncalibrated',
  }))

beforeEach(() => {
  vi.clearAllMocks()
  mocks.apisGetAll.mockResolvedValue([])
})

describe('useApiRmsSpl 全量翻页拉取（INT-330 缺陷3）', () => {
  it('映射 120 条 > 单页 100：循环翻页取全量，不静默截断', async () => {
    mocks.rmsGetAll
      .mockResolvedValueOnce({ items: makeItems(100, 1), total: 120, page: 1, perPage: 100, pages: 2 })
      .mockResolvedValueOnce({ items: makeItems(20, 101), total: 120, page: 2, perPage: 100, pages: 2 })

    const vm = useApiRmsSpl()
    await vm.searchMappings()

    expect(vm.mappingData.value).toHaveLength(120)
    expect(mocks.rmsGetAll).toHaveBeenCalledTimes(2)
    expect(mocks.rmsGetAll).toHaveBeenNthCalledWith(1, expect.objectContaining({ page: 1, perPage: 100 }))
    expect(mocks.rmsGetAll).toHaveBeenNthCalledWith(2, expect.objectContaining({ page: 2, perPage: 100 }))
  })

  it('单页取尽（total ≤ perPage）时不发多余翻页请求', async () => {
    mocks.rmsGetAll.mockResolvedValueOnce({ items: makeItems(3), total: 3, page: 1, perPage: 100, pages: 1 })

    const vm = useApiRmsSpl()
    await vm.searchMappings()

    expect(vm.mappingData.value).toHaveLength(3)
    expect(mocks.rmsGetAll).toHaveBeenCalledTimes(1)
  })

  it('total 虚报时遇空页防御性终止，不无限拉取', async () => {
    mocks.rmsGetAll
      .mockResolvedValueOnce({ items: makeItems(100), total: 500, page: 1, perPage: 100, pages: 5 })
      .mockResolvedValue({ items: [], total: 500, page: 2, perPage: 100, pages: 5 })

    const vm = useApiRmsSpl()
    await vm.searchMappings()

    expect(mocks.rmsGetAll).toHaveBeenCalledTimes(2)
    expect(vm.mappingData.value).toHaveLength(100)
  })

  it('服务端过滤参数（apiId/calibrationStatus）透传到每一页', async () => {
    mocks.rmsGetAll
      .mockResolvedValueOnce({ items: makeItems(100), total: 101, page: 1, perPage: 100, pages: 2 })
      .mockResolvedValueOnce({ items: makeItems(1, 101), total: 101, page: 2, perPage: 100, pages: 2 })

    const vm = useApiRmsSpl()
    vm.apiFilter.value = '7'
    vm.calibrationFilter.value = 'calibrated'
    await vm.searchMappings()

    expect(mocks.rmsGetAll).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({ apiId: '7', calibrationStatus: 'calibrated', page: 1 }),
    )
    expect(mocks.rmsGetAll).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ apiId: '7', calibrationStatus: 'calibrated', page: 2 }),
    )
  })
})

describe('useApiRmsSpl 客户端分页（对齐设备侧交互）', () => {
  const load120 = () => {
    mocks.rmsGetAll
      .mockResolvedValueOnce({ items: makeItems(100, 1), total: 120, page: 1, perPage: 100, pages: 2 })
      .mockResolvedValueOnce({ items: makeItems(20, 101), total: 120, page: 2, perPage: 100, pages: 2 })
  }

  it('默认每页 10 条切片；翻页/改页大小行为正确', async () => {
    load120()
    const vm = useApiRmsSpl()
    await vm.searchMappings()

    expect(vm.totalItems.value).toBe(120)
    expect(vm.totalPages.value).toBe(12)
    expect(vm.paginatedMappings.value).toHaveLength(10)
    expect(vm.paginatedMappings.value[0].id).toBe(1)

    vm.goToPage(2)
    expect(vm.currentPage.value).toBe(2)
    expect(vm.paginatedMappings.value[0].id).toBe(11)

    vm.setPageSize(20)
    expect(vm.currentPage.value).toBe(1)
    expect(vm.paginatedMappings.value).toHaveLength(20)

    vm.nextPage()
    vm.prevPage()
    expect(vm.currentPage.value).toBe(1)
  })

  it('搜索过滤（前端口径）作用于当前全量数据集', async () => {
    load120()
    const vm = useApiRmsSpl()
    await vm.searchMappings()

    vm.searchTerm.value = '映射 101'
    expect(vm.filteredMappings.value).toHaveLength(1)
    expect(vm.totalItems.value).toBe(1)
    expect(vm.paginatedMappings.value[0].id).toBe(101)
  })
})
