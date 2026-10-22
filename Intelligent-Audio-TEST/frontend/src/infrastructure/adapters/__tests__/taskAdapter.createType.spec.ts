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

  it('INT-1115：targetModes → 请求体 target_modes 透传（保选中顺序、snake_case 键）', () => {
    const dto = toTaskCreateDto({
      name: '混选逐目标任务',
      caseIds: ['1', '2'],
      deviceIds: [3],
      apiIds: [5],
      targetModes: [
        { targetType: 'device', targetId: 3, mode: 'serial' },
        { targetType: 'api', targetId: 5, mode: 'parallel' },
      ],
    })
    expect(dto.device_ids).toEqual([3])
    expect(dto.api_ids).toEqual([5])
    expect(dto.target_modes).toEqual([
      { target_type: 'device', target_id: 3, mode: 'serial' },
      { target_type: 'api', target_id: 5, mode: 'parallel' },
    ])
    // 废弃顶层旧字段：TaskCreateDto 已移除 execution_mode/serial_first（不再携带）
    expect('execution_mode' in dto).toBe(false)
    expect('serial_first' in dto).toBe(false)
  })

  it('INT-1115：targetModes 缺省 → 请求体 target_modes 空数组（= 全目标并行，零回归）', () => {
    const dto = toTaskCreateDto({
      name: '并行任务',
      caseIds: ['1'],
      apiIds: [5],
    } as TaskCreateDraft)
    expect(dto.target_modes).toEqual([])
    expect('execution_mode' in dto).toBe(false)
    expect('serial_first' in dto).toBe(false)
  })
})
