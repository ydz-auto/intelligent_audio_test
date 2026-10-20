/**
 * INT-1010 回归：批量弹窗「取消」时不得产生未捕获 promise rejection。
 *
 * 缺陷：GlobalModalContainer 在弹窗 cancel 时对 `modalControl.open` 返回的 Promise 调用
 * `reject()`（无 reason）；useTestCaseBatchActions 各批量入口没有 try/catch 包裹，
 * 取消即产生 `Uncaught (in promise)`。修复后在调用方统一吞掉取消 rejection，
 * 按「未确认（undefined）」处理，与各调用点 `if (result?.xxx)` 判空语义一致。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const mocks = vi.hoisted(() => {
  const storeMethods = {
    fetchCaseIdsByFilter: vi.fn(),
    batchUpdateSPL: vi.fn(),
    batchUpdatePlaybackDevices: vi.fn(),
    batchUpdateNoise: vi.fn(),
    batchUpdateAlgorithmParams: vi.fn(),
    batchUpdateDimensions: vi.fn(),
    batchCopyCases: vi.fn(),
    batchMoveCases: vi.fn(),
    batchAutoGenerateName: vi.fn(),
    batchAddTags: vi.fn(),
    batchRemoveTags: vi.fn(),
    batchRenameTag: vi.fn(),
    batchRefreshReference: vi.fn(),
    pollRefreshTaskStatus: vi.fn(),
    copyGroupCases: vi.fn(),
    deleteTagCases: vi.fn(),
    copyTagCases: vi.fn(),
    fetchTestCases: vi.fn(),
    refreshTagView: vi.fn(),
  }
  return {
    openModal: vi.fn(),
    storeMethods,
    mockStore: storeMethods,
  }
})

vi.mock('../../modal/useModal', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../modal/useModal')>()
  return {
    ...actual,
    useModalControl: () => ({ open: mocks.openModal }),
  }
})

vi.mock('../../modal/useNotification', () => ({
  useNotification: () => ({
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  }),
}))

vi.mock('../../../store/testCaseStore', () => ({
  useTestCaseStore: () => mocks.mockStore,
}))

import { useTestCaseBatchActions } from '../useTestCaseBatchActions'
import { MODAL_TYPES } from '../../modal/constants'
import type { TestCase } from '../../../domain/model/testCase'

const makeCase = (overrides: Partial<TestCase>): TestCase =>
  ({
    id: 1,
    name: '批量取消用例',
    type: 'e2e',
    testType: 'e2e',
    algorithmType: 'shuangliu',
    config: { rounds: [], dimensions: [] },
    tags: [],
    groupName: '冒烟组',
    ...overrides,
  }) as TestCase

const setUp = () => {
  const filteredTestCases = ref<Record<string, TestCase[]>>({ '冒烟组': [makeCase({})] })
  const selectedCases = ref<(string | number)[]>([])
  const algorithmTypeFilter = ref('')
  return useTestCaseBatchActions(filteredTestCases, selectedCases, algorithmTypeFilter)
}

beforeEach(() => {
  vi.clearAllMocks()
  for (const fn of Object.values(mocks.storeMethods)) {
    fn.mockReset()
  }
})

describe('INT-1010：批量弹窗取消不产生未捕获 rejection（取消 = 静默返回 undefined）', () => {
  it('批量算法参数弹窗取消：open reject 被吞掉，不调用批量更新，函数正常返回', async () => {
    mocks.openModal.mockRejectedValue(undefined) // GlobalModalContainer 取消时 reject() 无 reason
    const { handleUpdateAlgorithmParams } = setUp()

    await expect(handleUpdateAlgorithmParams('冒烟组')).resolves.toBeUndefined()

    expect(mocks.openModal).toHaveBeenCalledWith(
      MODAL_TYPES.BATCH_ALGORITHM_PARAMS,
      expect.objectContaining({ title: '批量设置用例专属参数', caseCount: 1 })
    )
    expect(mocks.storeMethods.batchUpdateAlgorithmParams).not.toHaveBeenCalled()
  })

  it('批量弹窗取消（无 reason）与打开失败（有 reason）都按 undefined 处理', async () => {
    mocks.openModal.mockRejectedValue(new Error('Modal type not registered'))
    const { handleUpdateAlgorithmParams } = setUp()

    await expect(handleUpdateAlgorithmParams('冒烟组')).resolves.toBeUndefined()
    expect(mocks.storeMethods.batchUpdateAlgorithmParams).not.toHaveBeenCalled()
  })

  it('批量算法参数弹窗确认：正常走批量更新（取消修复不破坏确认路径）', async () => {
    mocks.openModal.mockResolvedValue({
      algorithmType: 'shuangliu',
      params: { sampleRate: 16000 },
      roundMode: 'all',
      roundNumbers: [],
    })
    mocks.storeMethods.batchUpdateAlgorithmParams.mockResolvedValue(true)
    const { handleUpdateAlgorithmParams } = setUp()

    await expect(handleUpdateAlgorithmParams('冒烟组')).resolves.toBeUndefined()

    expect(mocks.openModal).toHaveBeenCalledWith(MODAL_TYPES.BATCH_ALGORITHM_PARAMS, expect.anything())
    expect(mocks.storeMethods.batchUpdateAlgorithmParams).toHaveBeenCalledWith(
      [1],
      { sampleRate: 16000 },
      { roundMode: 'all', roundNumbers: [] }
    )
  })
})

describe('INT-1010：同类批量入口全部取消安全', () => {
  it('批量设置声压取消：不产生 rejection，不调批量更新', async () => {
    mocks.openModal.mockRejectedValue(undefined)
    const { handleUpdateSPL } = setUp()

    await expect(handleUpdateSPL('冒烟组')).resolves.toBeUndefined()
    expect(mocks.openModal).toHaveBeenCalledWith(
      MODAL_TYPES.BATCH_SPL,
      expect.objectContaining({ title: '批量设置声压级' })
    )
    expect(mocks.storeMethods.batchUpdateSPL).not.toHaveBeenCalled()
  })

  it('批量设置评价维度取消：不产生 rejection', async () => {
    mocks.openModal.mockRejectedValue(undefined)
    const { handleUpdateDimensions } = setUp()

    await expect(handleUpdateDimensions('冒烟组')).resolves.toBeUndefined()
    expect(mocks.openModal).toHaveBeenCalledWith(
      MODAL_TYPES.BATCH_DIMENSION,
      expect.objectContaining({ title: '批量设置评价维度' })
    )
    expect(mocks.storeMethods.batchUpdateDimensions).not.toHaveBeenCalled()
  })

  it('批量管理标签取消：不产生 rejection', async () => {
    mocks.openModal.mockRejectedValue(undefined)
    const { handleUpdateTags } = setUp()

    await expect(handleUpdateTags('冒烟组')).resolves.toBeUndefined()
    expect(mocks.openModal).toHaveBeenCalledWith(
      MODAL_TYPES.BATCH_TAGS,
      expect.objectContaining({ title: '批量管理用例标签' })
    )
    expect(mocks.storeMethods.batchAddTags).not.toHaveBeenCalled()
  })

  it('批量通过标签自动生成名称取消：不产生 rejection', async () => {
    mocks.openModal.mockRejectedValue(undefined)
    const { handleAutoGenerateName } = setUp()

    await expect(handleAutoGenerateName('冒烟组')).resolves.toBeUndefined()
    expect(mocks.openModal).toHaveBeenCalledWith(
      MODAL_TYPES.BASIC_CONFIRM,
      expect.objectContaining({ title: '批量通过标签自动生成用例名' })
    )
    expect(mocks.storeMethods.batchAutoGenerateName).not.toHaveBeenCalled()
  })

  it('复制分组取消：不再落入 catch 打错误日志（原有 try/catch 仍保护 store 失败）', async () => {
    mocks.openModal.mockRejectedValue(undefined)
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { handleCopyGroup } = setUp()

    await expect(handleCopyGroup('冒烟组')).resolves.toBeUndefined()
    expect(mocks.storeMethods.copyGroupCases).not.toHaveBeenCalled()
    expect(errorSpy).not.toHaveBeenCalled()
    errorSpy.mockRestore()
  })
})
