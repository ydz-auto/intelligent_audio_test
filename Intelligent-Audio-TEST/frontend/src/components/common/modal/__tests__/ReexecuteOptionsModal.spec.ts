/**
 * INT-302：ReexecuteOptionsModal 组件单测（重执行/重评估范围选择模态窗）。
 *
 * 锁定口径：
 * - 范围三选（全部/仅失败/手动选择）默认全部；确认载荷 mode 对应
 * - actionType='retry' 无维度步；'reevaluate' 渲染维度勾选且默认全选
 * - 手动选择：checkbox 勾选/全选 + 标签/分组过滤，底部计数
 * - 数据源为本任务已执行用例集（tasksPort.getOne(taskId).cases），非全库
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  getOne: vi.fn(),
  dimensionGetAll: vi.fn(),
}))

vi.mock('../../../../composables/task/tasksPort', () => ({
  tasksPort: { getOne: mocks.getOne },
}))

vi.mock('../../../../composables/evaluation/evaluationPort', () => ({
  evaluationPort: { getAll: mocks.dimensionGetAll },
}))

import ReexecuteOptionsModal from '../ReexecuteOptionsModal.vue'

/** 本任务已执行用例集（含标签/分组，供过滤交互） */
const TASK_CASES = [
  { caseId: 'c1', name: '用例一', groupName: '组A', tags: ['标签1'] },
  { caseId: 'c2', name: '用例二', groupName: '组A', tags: [] },
  { caseId: 'c3', name: '用例三', groupName: '组B', tags: ['标签2'] },
]

const DIMENSIONS = { items: [{ id: 7, name: 'WER' }, { id: 8, name: 'CER' }, { id: 9, name: '时延' }] }

const mountModal = (actionType: 'retry' | 'reevaluate' = 'retry') =>
  mount(ReexecuteOptionsModal, {
    props: { modalId: 'm1', content: '请选择执行范围', actionType, taskId: 9 },
  })

describe('ReexecuteOptionsModal（INT-302）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getOne.mockResolvedValue({ cases: TASK_CASES })
    mocks.dimensionGetAll.mockResolvedValue(DIMENSIONS)
  })

  it('默认勾选"全部"，直接确认 → mode=all（旧语义不变）', async () => {
    const w = mountModal('retry')
    await flushPromises()

    const confirmBtn = w.findAll('button').find(b => b.text().includes('确认'))!
    await confirmBtn.trigger('click')

    expect(w.emitted('confirm')![0][0]).toMatchObject({ mode: 'all', caseIds: [], dimensionIds: [] })
  })

  it('actionType=retry 不渲染维度步；reevaluate 渲染且维度默认全选', async () => {
    const retryW = mountModal('retry')
    await flushPromises()
    expect(retryW.find('.dimension-selector').exists()).toBe(false)

    const reevalW = mountModal('reevaluate')
    await flushPromises()
    expect(reevalW.find('.dimension-selector').exists()).toBe(true)
    // 默认全选：3 个维度 checkbox 均勾选
    const checks = reevalW.findAll('.dimension-item input[type="checkbox"]')
    expect(checks.length).toBe(3)
    expect(checks.every(c => (c.element as HTMLInputElement).checked)).toBe(true)
  })

  it('手动选择：勾选 2 个用例后确认 → mode=selected + caseIds', async () => {
    const w = mountModal('retry')
    await flushPromises()

    // 切到手动选择
    await w.findAll('.reexecute-option')[2].trigger('click')
    const checks = w.findAll('.case-item input[type="checkbox"]')
    expect(checks.length).toBe(3)
    await checks[0].setValue(true)
    await checks[2].setValue(true)

    const confirmBtn = w.findAll('button').find(b => b.text().includes('确认'))!
    expect(confirmBtn.text()).toContain('已选 2 个用例')
    await confirmBtn.trigger('click')

    expect(w.emitted('confirm')![0][0]).toMatchObject({ mode: 'selected', caseIds: ['c1', 'c3'] })
  })

  it('手动选择未勾选任何用例：确认按钮禁用', async () => {
    const w = mountModal('retry')
    await flushPromises()

    await w.findAll('.reexecute-option')[2].trigger('click')
    const confirmBtn = w.findAll('button').find(b => b.text().includes('确认'))!
    expect((confirmBtn.element as HTMLButtonElement).disabled).toBe(true)
  })

  it('标签过滤：按标签筛选后仅显示命中用例，全选只追加可见集', async () => {
    const w = mountModal('retry')
    await flushPromises()

    await w.findAll('.reexecute-option')[2].trigger('click')
    // 标签1 → 仅 c1
    const filterSelect = w.find('.filter-select-input')
    await filterSelect.setValue('标签1')
    expect(w.findAll('.case-item').length).toBe(1)

    // 全选可见集 → 仅 c1 入选
    await w.find('.select-all-label input').setValue(true)
    const confirmBtn = w.findAll('button').find(b => b.text().includes('确认'))!
    await confirmBtn.trigger('click')
    expect(w.emitted('confirm')![0][0]).toMatchObject({ mode: 'selected', caseIds: ['c1'] })
  })

  it('reevaluate 取消部分维度勾选：确认载荷携带剩余维度（全选时空数组）', async () => {
    const w = mountModal('reevaluate')
    await flushPromises()

    // 取消维度 7
    const checks = w.findAll('.dimension-item input[type="checkbox"]')
    await checks[0].setValue(false)

    const confirmBtn = w.findAll('button').find(b => b.text().includes('确认'))!
    await confirmBtn.trigger('click')
    expect(w.emitted('confirm')![0][0]).toMatchObject({ mode: 'all', dimensionIds: [8, 9] })
  })

  it('数据源为本任务用例集（tasksPort.getOne(taskId)），非全库用例', async () => {
    mountModal('retry')
    await flushPromises()
    expect(mocks.getOne).toHaveBeenCalledWith(9)
    expect(mocks.dimensionGetAll).not.toHaveBeenCalled()
  })
})
