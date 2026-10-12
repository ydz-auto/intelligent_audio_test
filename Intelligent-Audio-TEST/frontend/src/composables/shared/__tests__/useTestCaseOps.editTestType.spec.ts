/**
 * INT-196 验收：TestFlow 编辑入口（useTestCaseOps）testType 回填契约。
 *
 * handleOpenEditModal 两条分支：
 * - E2E 模式：曾用 `testType || TestType.E2E` 兜底，修复后只信任域模型 testType；
 * - API 模式：委托 useTestCaseCard.openEditTestCaseModal（INT-196 修复后的路径）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const mocks = vi.hoisted(() => ({
  openModal: vi.fn(),
  openEditTestCaseModal: vi.fn(),
  handleModalSave: vi.fn(),
}))

vi.mock('pinia', () => ({
  storeToRefs: (store: Record<string, unknown>) => store,
}))

vi.mock('../../../store/testCaseStore', () => ({
  useTestCaseStore: () => ({
    testCases: ref([]),
    testCaseGroups: ref({}),
    tags: ref([]),
    isLoading: ref(false),
    paginationInfo: ref({}),
    tagViewData: ref({}),
    tagViewPagination: ref({}),
    tagViewLoading: ref(false),
    fetchTestCases: vi.fn(),
    fetchTagView: vi.fn(),
    loadMoreTagView: vi.fn(),
    refreshTagView: vi.fn(),
  }),
}))

vi.mock('../../testCase/useTestCaseCard', () => ({
  useTestCaseCard: () => ({
    formData: ref<Record<string, unknown>>({}),
    groupFormData: ref({}),
    editingTestCase: ref(null),
    editingGroup: ref(null),
    openAddTestCaseModal: vi.fn(),
    openEditTestCaseModal: mocks.openEditTestCaseModal,
    openCreateGroupModal: vi.fn(),
    openEditGroupModal: vi.fn(),
    openImportTestCaseModal: vi.fn(),
    openExportTestCaseModal: vi.fn(),
    handleModalSave: mocks.handleModalSave,
    handleTestCaseAction: vi.fn(),
  }),
}))

vi.mock('../../e2e/useE2eTest', () => ({
  useE2eTest: () => ({
    e2eTestCases: ref([]),
    e2eTestCaseGroups: ref({}),
    tags: ref([]),
    isLoading: ref(false),
    paginationInfo: ref({}),
    tagViewData: ref({}),
    tagViewPagination: ref({}),
    tagViewLoading: ref(false),
    initializeE2eTests: vi.fn(),
    fetchTagView: vi.fn(),
    loadMoreTagView: vi.fn(),
  }),
}))

vi.mock('../../modal/useModal', () => ({
  useModalControl: () => ({ open: mocks.openModal }),
  MODAL_TYPES: { TEST_CASE_RELATED: 'testCase' },
}))

vi.mock('../../modal/useDeleteConfirm', () => ({
  useDeleteConfirm: () => ({
    confirmDeleteGroup: vi.fn(),
    confirmDeleteTestCase: vi.fn(),
  }),
}))

import { useTestCaseOps } from '../useTestCaseOps'
import { MODAL_TYPES } from '../../modal/constants'
import type { TestCase } from '../../../domain/model/testCase'

const makeCase = (overrides: Partial<TestCase>): TestCase =>
  ({
    id: 9,
    name: 'E2E 播放回归',
    type: 'e2e',
    testType: 'e2e',
    config: { rounds: [{ roundNumber: 1, audios: [] }], dimensions: [] },
    tags: [],
    groupName: '回归组',
    ...overrides,
  }) as TestCase

const setupOps = (testType: 'api' | 'e2e') =>
  useTestCaseOps({
    testType,
    selectedAlgorithmType: ref<string | null>(null),
    addLog: vi.fn(),
  })

beforeEach(() => {
  vi.clearAllMocks()
  mocks.openModal.mockResolvedValue(undefined)
})

describe('INT-196：TestFlow 编辑入口 testType 回填', () => {
  it('E2E 模式编辑 E2E 用例：模态窗按 E2E 形态打开（回归）', async () => {
    const { handleOpenEditModal } = setupOps('e2e')

    await handleOpenEditModal(makeCase({ testType: 'e2e' }))

    expect(mocks.openModal).toHaveBeenCalledTimes(1)
    const [modalType, options] = mocks.openModal.mock.calls[0]
    expect(modalType).toBe(MODAL_TYPES.TEST_CASE_RELATED)
    expect(options.testType).toBe('e2e')
    expect(options.formData.testType).toBe('e2e')
  })

  it('E2E 模式 testType 缺省：不再兜底成 e2e（旧行为是恒回填）', async () => {
    const { handleOpenEditModal } = setupOps('e2e')

    await handleOpenEditModal(makeCase({ type: undefined, testType: undefined }))

    const [, options] = mocks.openModal.mock.calls[0]
    expect(options.testType).toBeUndefined()
    expect(options.formData.testType).toBeUndefined()
  })

  it('API 模式：委托 useTestCaseCard.openEditTestCaseModal（INT-196 修复后路径）', async () => {
    const { handleOpenEditModal } = setupOps('api')
    const apiCase = makeCase({ type: 'api', testType: 'api', name: 'API 用例' })

    await handleOpenEditModal(apiCase)

    expect(mocks.openEditTestCaseModal).toHaveBeenCalledTimes(1)
    expect(mocks.openEditTestCaseModal).toHaveBeenCalledWith(apiCase)
    expect(mocks.openModal).not.toHaveBeenCalled()
  })
})
