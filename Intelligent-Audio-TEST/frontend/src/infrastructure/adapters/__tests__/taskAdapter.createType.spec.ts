/**
 * INT-282 验收：toTaskCreateDto type 契约映射。
 *
 * 缺陷回归：实装 TestFlow 建任务载荷丢失 type 字段（基线 V9.7.10
 * apiTest.ts:443-449 显式 type:'api'）。修复后 adapter 显式透传 type；
 * 注：V9.7.31 后端 task.type 已废弃（差异#2 收尾，TaskCreateRequest
 * extra="ignore" 静默忽略），映射仅作基线契约兼容留痕，任务归类由
 * 用例级 TaskCase.device_type 派生。
 */
import { describe, it, expect } from 'vitest'
import { toTaskCreateDto } from '../taskAdapter'
import type { TaskCreateDraft } from '../../../domain/model/task'

describe('INT-282：toTaskCreateDto type 映射', () => {
  it("type='api' → 请求体显式携带 type（对齐基线 apiTest 契约）", () => {
    const dto = toTaskCreateDto({
      name: 'API测试任务',
      type: 'api',
      caseIds: ['1', '2'],
      apiIds: [3],
    })
    expect(dto.type).toBe('api')
    expect(dto.case_ids).toEqual(['1', '2'])
    expect(dto.api_ids).toEqual([3])
  })

  it("type='e2e' → 请求体显式携带 type（对齐 useE2eExecution 基线契约）", () => {
    const dto = toTaskCreateDto({
      name: 'E2E测试任务',
      type: 'e2e',
      caseIds: ['7'],
      deviceIds: [9],
    })
    expect(dto.type).toBe('e2e')
    expect(dto.device_ids).toEqual([9])
  })

  it('type 缺省 → 不携带该键（旧调用方兼容，不发 undefined 噪音）', () => {
    const dto = toTaskCreateDto({
      name: '无 type 旧草稿',
      caseIds: ['1'],
    } as TaskCreateDraft)
    expect(dto.type).toBeUndefined()
  })
})
