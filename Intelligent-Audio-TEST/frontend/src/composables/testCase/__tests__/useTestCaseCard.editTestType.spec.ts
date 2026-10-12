/**
 * INT-196 验收：用例管理编辑模态窗 testType 回填契约。
 *
 * 缺陷：openEditTestCaseModal 曾用 `testType || TestType.E2E` 兜底，
 * adapter 未映射 testType 时 API 用例编辑恒被锁成 E2E 表单。
 * 修复后编辑回填只信任域模型 testType；E2E 默认仅保留在新建入口。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mocks = vi.hoisted(() => ({
  openModal: vi.fn(),
  push: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.push }),
}))

vi.mock('../testcasesPort', () => ({
  testcasesPort: {
    getGroups: vi.fn(async () => ({ items: [] })),
    getOne: vi.fn(async () => ({})),
  },
}))

vi.mock('../../device/playbackPort', () => ({
  playbackPort: {
    getAll: vi.fn(async () => []),
  },
}))

vi.mock('../../modal/useModal', () => ({
  useModalControl: () => ({ open: mocks.openModal }),
}))

vi.mock('../../modal/useNotification', () => ({
  useNotification: () => ({
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  }),
}))

import { useTestCaseCard } from '../useTestCaseCard'
import { MODAL_TYPES } from '../../modal/constants'
import type { TestCase } from '../../../domain/model/testCase'

const makeCase = (overrides: Partial<TestCase>): TestCase =>
  ({
    id: 7,
    name: '登录接口冒烟',
    type: 'api',
    config: { rounds: [{ roundNumber: 1, audios: [] }], dimensions: [] },
    tags: [],
    groupName: '冒烟组',
    ...overrides,
  }) as TestCase

beforeEach(() => {
  vi.clearAllMocks()
  // open 返回 undefined → 不进入保存分支，仅捕获打开参数
  mocks.openModal.mockResolvedValue(undefined)
})

describe('INT-196：编辑模态窗 testType 回填（用例管理主缺陷场景）', () => {
  it('编辑 API 用例：模态窗按 API 形态打开，不回填 e2e', async () => {
    const { openEditTestCaseModal } = useTestCaseCard()

    await openEditTestCaseModal(makeCase({ testType: 'api' }))

    expect(mocks.openModal).toHaveBeenCalledTimes(1)
    const [modalType, options] = mocks.openModal.mock.calls[0]
    expect(modalType).toBe(MODAL_TYPES.TEST_CASE_RELATED)
    expect(options.mode).toBe('case')
    expect(options.title).toBe('编辑测试用例')
    expect(options.testType).toBe('api')
    expect(options.formData.testType).toBe('api')
  })

  it('编辑 E2E 用例：仍按 E2E 形态打开（回归）', async () => {
    const { openEditTestCaseModal } = useTestCaseCard()

    await openEditTestCaseModal(makeCase({ type: 'e2e', testType: 'e2e' }))

    const [, options] = mocks.openModal.mock.calls[0]
    expect(options.testType).toBe('e2e')
    expect(options.formData.testType).toBe('e2e')
  })

  it('testType 意外缺省：不再兜底成 e2e（切换器解锁、默认 API 形态的安全降级）', async () => {
    const { openEditTestCaseModal } = useTestCaseCard()

    await openEditTestCaseModal(makeCase({ type: undefined, testType: undefined }))

    const [, options] = mocks.openModal.mock.calls[0]
    expect(options.testType).toBeUndefined()
    expect(options.formData.testType).toBeUndefined()
  })
})

describe('INT-196：新建入口 E2E 默认保留', () => {
  it('新建用例不带 testType 时默认 e2e（口径不变）', async () => {
    const { openAddTestCaseModal } = useTestCaseCard()

    await openAddTestCaseModal('冒烟组')

    const [modalType, options] = mocks.openModal.mock.calls[0]
    expect(modalType).toBe(MODAL_TYPES.TEST_CASE_RELATED)
    expect(options.title).toBe('新增测试用例')
    expect(options.testType).toBe('e2e')
  })

  it('新建入口显式传 testType 时透传（API 视图新建 API 用例）', async () => {
    const { openAddTestCaseModal } = useTestCaseCard()

    await openAddTestCaseModal('冒烟组', { testType: 'api' })

    const [, options] = mocks.openModal.mock.calls[0]
    expect(options.testType).toBe('api')
  })
})
