/**
 * INT-302：ReexecuteOptionsModal 组件单测（重执行/重评估范围选择模态窗）。
 *
 * 锁定口径：
 * - 范围三选（全部/仅失败/手动选择）默认全部；确认载荷 mode 对应
 * - actionType='retry' 无维度步；'reevaluate' 渲染维度勾选且默认全选
 * - 手动选择：checkbox 勾选/全选 + 标签/分组过滤，底部计数
 * - 数据源为本任务已执行用例集（tasksPort.getOne(taskId).cases），非全库
 * - 维度候选集从本任务用例聚合（cases[].evaluationDimensions 去重），不拉全库（F3）
 * - F1：重评估维度步可见时 0 维度禁用确认（空 dimensionIds 后端=全量重评，语义反转）
 * - F4：重新提取设备输出勾选恢复（默认不勾选，仅重评估渲染，随确认载荷下发）
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

/** 本任务已执行用例集（含标签/分组，供过滤交互；F3：含评估维度聚合） */
const TASK_CASES = [
  {
    caseId: 'c1', name: '用例一', groupName: '组A', tags: ['标签1'],
    evaluationDimensions: [{ id: 7, name: 'WER' }, { id: 9, name: '时延' }],
  },
  {
    caseId: 'c2', name: '用例二', groupName: '组A', tags: [],
    evaluationDimensions: [{ id: 7, name: 'WER' }, { id: 8, name: 'CER' }],
  },
  { caseId: 'c3', name: '用例三', groupName: '组B', tags: ['标签2'] },
]

const mountModal = (actionType: 'retry' | 'reevaluate' = 'retry') =>
  mount(ReexecuteOptionsModal, {
    props: { modalId: 'm1', content: '请选择执行范围', actionType, taskId: 9 },
  })

const findConfirmButton = (w: ReturnType<typeof mount>) =>
  w.findAll('button').find(b => b.text().includes('确认'))!

describe('ReexecuteOptionsModal（INT-302）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getOne.mockResolvedValue({ cases: TASK_CASES })
  })

  it('默认勾选"全部"，直接确认 → mode=all（旧语义不变）', async () => {
    const w = mountModal('retry')
    await flushPromises()

    await findConfirmButton(w).trigger('click')

    expect(w.emitted('confirm')![0][0]).toMatchObject({
      mode: 'all', caseIds: [], dimensionIds: [], reextractDeviceOutput: false,
    })
  })

  it('actionType=retry 不渲染维度步；reevaluate 渲染且维度默认全选', async () => {
    const retryW = mountModal('retry')
    await flushPromises()
    expect(retryW.find('.dimension-selector').exists()).toBe(false)

    const reevalW = mountModal('reevaluate')
    await flushPromises()
    expect(reevalW.find('.dimension-selector').exists()).toBe(true)
    // 默认全选：聚合去重后 3 个维度（7/9/8）checkbox 均勾选
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

    const confirmBtn = findConfirmButton(w)
    expect(confirmBtn.text()).toContain('已选 2 个用例')
    await confirmBtn.trigger('click')

    expect(w.emitted('confirm')![0][0]).toMatchObject({ mode: 'selected', caseIds: ['c1', 'c3'] })
  })

  it('手动选择未勾选任何用例：确认按钮禁用', async () => {
    const w = mountModal('retry')
    await flushPromises()

    await w.findAll('.reexecute-option')[2].trigger('click')
    expect((findConfirmButton(w).element as HTMLButtonElement).disabled).toBe(true)
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
    await findConfirmButton(w).trigger('click')
    expect(w.emitted('confirm')![0][0]).toMatchObject({ mode: 'selected', caseIds: ['c1'] })
  })

  it('reevaluate 取消部分维度勾选：确认载荷携带剩余维度（全选时空数组）', async () => {
    const w = mountModal('reevaluate')
    await flushPromises()

    // 取消维度 7（WER；聚合顺序 7/9/8）
    const checks = w.findAll('.dimension-item input[type="checkbox"]')
    await checks[0].setValue(false)

    await findConfirmButton(w).trigger('click')
    expect(w.emitted('confirm')![0][0]).toMatchObject({ mode: 'all', dimensionIds: [9, 8] })
  })

  it('F1：重评估维度全部取消勾选 → 确认按钮禁用（0 维度不发空 dimensionIds）', async () => {
    const w = mountModal('reevaluate')
    await flushPromises()

    const checks = w.findAll('.dimension-item input[type="checkbox"]')
    await checks[0].setValue(false)
    await checks[1].setValue(false)
    await checks[2].setValue(false)

    expect((findConfirmButton(w).element as HTMLButtonElement).disabled).toBe(true)
    await findConfirmButton(w).trigger('click')
    expect(w.emitted('confirm')).toBeUndefined()
  })

  it('F3：维度候选集从本任务用例聚合去重，不拉全库维度', async () => {
    const w = mountModal('reevaluate')
    await flushPromises()

    // c1(7,9) + c2(7,8) 聚合去重 → 7/9/8；名称取任务用例配置
    const names = w.findAll('.dimension-item-name').map(n => n.text())
    expect(names).toEqual(['WER', '时延', 'CER'])
    // 全库维度接口不再被调用（消除 500 条截断隐患）
    expect(mocks.dimensionGetAll).not.toHaveBeenCalled()
  })

  it('F3：任务用例均无评估维度配置 → 无维度步且确认可用（旧语义可重评）', async () => {
    mocks.getOne.mockResolvedValue({
      cases: [{ caseId: 'c1', name: '用例一', groupName: '', tags: [] }],
    })
    const w = mountModal('reevaluate')
    await flushPromises()

    expect(w.find('.dimension-selector').exists()).toBe(false)
    expect((findConfirmButton(w).element as HTMLButtonElement).disabled).toBe(false)
    await findConfirmButton(w).trigger('click')
    expect(w.emitted('confirm')![0][0]).toMatchObject({
      mode: 'all', dimensionIds: [], reextractDeviceOutput: false,
    })
  })

  it('F4：重评估渲染"重新提取设备输出"勾选，默认不勾选；勾选后随确认载荷下发', async () => {
    const retryW = mountModal('retry')
    await flushPromises()
    expect(retryW.find('.reextract-option').exists()).toBe(false)

    const w = mountModal('reevaluate')
    await flushPromises()
    const reextractInput = w.find('.reextract-option input[type="checkbox"]')
    expect(reextractInput.exists()).toBe(true)
    expect((reextractInput.element as HTMLInputElement).checked).toBe(false)

    await reextractInput.setValue(true)
    await findConfirmButton(w).trigger('click')
    expect(w.emitted('confirm')![0][0]).toMatchObject({
      mode: 'all', reextractDeviceOutput: true,
    })
  })

  it('数据源为本任务用例集（tasksPort.getOne(taskId)），非全库用例', async () => {
    mountModal('retry')
    await flushPromises()
    expect(mocks.getOne).toHaveBeenCalledWith(9)
    expect(mocks.dimensionGetAll).not.toHaveBeenCalled()
  })
})
