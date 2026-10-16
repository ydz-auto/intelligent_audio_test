/**
 * INT-340：人工复核覆盖提醒（useReviewOverwrite）接线单测
 *
 * 覆盖（端口层 mock）：
 * - 无复核结果 → 放行（不弹确认）
 * - 有复核结果整任务重跑 → 弹确认，确认后放行 / 取消阻断
 * - 选择性（selected）选中用例无复核 → 放行；选中用例有复核 → 弹确认
 * - 详情读取失败 → 降级放行
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mocks = vi.hoisted(() => ({
  getOne: vi.fn(),
  openModal: vi.fn(),
}))

vi.mock('@/composables/task/tasksPort', () => ({
  tasksPort: { getOne: mocks.getOne },
}))

vi.mock('@/composables/modal/useModal', () => ({
  MODAL_TYPES: { BASIC_CONFIRM: 'basicConfirm' },
}))

import { confirmReviewOverwrite } from '../useReviewOverwrite'

describe('confirmReviewOverwrite (INT-340)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const modalControl = { open: mocks.openModal }

  it('无复核结果时直接放行（不弹确认）', async () => {
    mocks.getOne.mockResolvedValue({ id: 1, reviewCount: 0 })
    const ok = await confirmReviewOverwrite(modalControl, 1, undefined, '重新执行')
    expect(ok).toBe(true)
    expect(mocks.openModal).not.toHaveBeenCalled()
  })

  it('有复核结果整任务重跑时弹确认；确认后放行', async () => {
    mocks.getOne.mockResolvedValue({ id: 1, reviewCount: 3, cases: [] })
    mocks.openModal.mockResolvedValue({ confirmed: true })
    const ok = await confirmReviewOverwrite(modalControl, 1, { mode: 'all' }, '重新执行')
    expect(ok).toBe(true)
    expect(mocks.openModal).toHaveBeenCalled()
    expect(mocks.openModal.mock.calls[0][1].content).toContain('3 条人工复核结果')
  })

  it('有复核结果整任务重跑时弹确认；取消阻断', async () => {
    mocks.getOne.mockResolvedValue({ id: 1, reviewCount: 3, cases: [] })
    mocks.openModal.mockResolvedValue({ confirmed: false })
    const ok = await confirmReviewOverwrite(modalControl, 1, { mode: 'all' }, '重新评估')
    expect(ok).toBe(false)
  })

  it('选择性（selected）选中用例无复核 → 放行不弹确认', async () => {
    mocks.getOne.mockResolvedValue({
      id: 1, reviewCount: 2,
      cases: [
        { caseId: 'A', reviewed: true },
        { caseId: 'B', reviewed: true },
        { caseId: 'C', reviewed: false },
      ],
    })
    const ok = await confirmReviewOverwrite(
      modalControl, 1, { mode: 'selected', caseIds: ['C'] }, '重新执行')
    expect(ok).toBe(true)
    expect(mocks.openModal).not.toHaveBeenCalled()
  })

  it('选择性（selected）选中用例有复核 → 弹确认并按选中条数提示', async () => {
    mocks.getOne.mockResolvedValue({
      id: 1, reviewCount: 2,
      cases: [
        { caseId: 'A', reviewed: true },
        { caseId: 'B', reviewed: true },
      ],
    })
    mocks.openModal.mockResolvedValue({ confirmed: true })
    const ok = await confirmReviewOverwrite(
      modalControl, 1, { mode: 'selected', caseIds: ['A'] }, '重新执行')
    expect(ok).toBe(true)
    expect(mocks.openModal.mock.calls[0][1].content).toContain('1 条人工复核结果')
  })

  it('详情读取失败时降级放行（不阻断主流程）', async () => {
    mocks.getOne.mockRejectedValue(new Error('boom'))
    const ok = await confirmReviewOverwrite(modalControl, 1, undefined, '重新执行')
    expect(ok).toBe(true)
    expect(mocks.openModal).not.toHaveBeenCalled()
  })

  it('确认模态关闭（reject）视为取消', async () => {
    mocks.getOne.mockResolvedValue({ id: 1, reviewCount: 1, cases: [] })
    mocks.openModal.mockRejectedValue(new Error('closed'))
    const ok = await confirmReviewOverwrite(modalControl, 1, undefined, '重新执行')
    expect(ok).toBe(false)
  })
})
