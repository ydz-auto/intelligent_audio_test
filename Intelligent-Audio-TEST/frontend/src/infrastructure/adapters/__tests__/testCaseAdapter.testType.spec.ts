/**
 * INT-196 验收：列表项 type → Domain testType 派生契约。
 *
 * 缺陷回归：toTestCase/toTagViewCase 曾不映射 testType，编辑回填
 * `|| TestType.E2E` 把 API 用例恒锁成 E2E 表单。修复后：
 * - 后端 derive_case_test_type 口径恒为 'api'/'e2e'，映射透传；
 * - 非法/缺省值不映射（undefined），由 CaseForm 解锁切换器安全降级，
 *   不再被兜底成 E2E。
 */
import { describe, it, expect } from 'vitest'
import { toTestCase, toTagViewItem } from '../testCaseAdapter'
import type { TestCaseDto, TagViewItemDto } from '../../dto/testCaseDto'

const baseDto = {
  id: 101,
  name: 'API 冒烟用例',
} as any

describe('INT-196：toTestCase type→testType 派生', () => {
  it("type='api' → testType='api'（API 用例编辑按 API 形态）", () => {
    const domain = toTestCase({ ...baseDto, type: 'api' } as TestCaseDto)
    expect(domain.type).toBe('api')
    expect(domain.testType).toBe('api')
  })

  it("type='e2e' → testType='e2e'（E2E 编辑形态回归）", () => {
    const domain = toTestCase({ ...baseDto, type: 'e2e' } as TestCaseDto)
    expect(domain.type).toBe('e2e')
    expect(domain.testType).toBe('e2e')
  })

  it('type 缺省（undefined）→ testType 不映射为 undefined，不再恒回填 e2e', () => {
    const domain = toTestCase({ ...baseDto } as TestCaseDto)
    expect(domain.type).toBeUndefined()
    expect(domain.testType).toBeUndefined()
  })

  it('type=null → testType 不映射为 undefined', () => {
    const domain = toTestCase({ ...baseDto, type: null } as TestCaseDto)
    expect(domain.testType).toBeUndefined()
  })

  it('type 非法值 → 不映射（不用 E2E 兜底吞掉异常数据）', () => {
    const domain = toTestCase({ ...baseDto, type: 'webrtc' } as TestCaseDto)
    expect(domain.type).toBe('webrtc')
    expect(domain.testType).toBeUndefined()
  })
})

describe('INT-196：toTagViewItem 标签视图内层用例同口径派生', () => {
  const tagItem = {
    tag: '回归',
    testCases: [
      { id: 1, name: '标签内 API 用例', type: 'api' },
      { id: 2, name: '标签内 E2E 用例', type: 'e2e' },
      { id: 3, name: '标签内缺省用例' },
    ],
  } as any as TagViewItemDto

  it('内层用例按 type 派生 testType，缺省不映射', () => {
    const [apiCase, e2eCase, missingCase] = toTagViewItem(tagItem).testCases
    expect(apiCase.testType).toBe('api')
    expect(e2eCase.testType).toBe('e2e')
    expect(missingCase.testType).toBeUndefined()
  })
})
