/**
 * 容器组成纯函数单测（18_挑选合并功能交互重设计.md §5.5.3/§5.5.4/§5.5.8，INT-1711）。
 * 覆盖：§11-8 未落地时的降级装配（状态取同 source_case_id 的容器用例行）、
 * 摘要口径、筛选联动、用例层组织。
 */
import { describe, expect, it } from 'vitest'

import {
  filterCompositionEntries,
  filterMissingEntries,
  groupCompositionEntries,
  organizeCompositionCases,
  summarizeComposition,
  toCompositionEntries,
} from '@/domain/lib/container-composition'
import type { ContainerSourceTrace } from '@/domain/models/cherryPick'
import type { TaskApiBrief, TaskCaseBrief, TaskDeviceBrief } from '@/domain/models/task'

const CASE_A = '11111111-1111-1111-1111-111111111111'
const CASE_B = '22222222-2222-2222-2222-222222222222'

function caseBrief(
  caseId: string,
  name: string,
  execution: string,
  evaluation: string,
  groupName: string | null = null,
  tags: string[] = []
): TaskCaseBrief {
  return {
    case_id: caseId,
    name,
    status: execution,
    execution_status: execution,
    evaluation_status: evaluation,
    started_at: null,
    completed_at: null,
    duration: null,
    error_message: null,
    group_name: groupName,
    tags,
    evaluation_dimensions: [],
    reviewed: false,
  }
}

const CASES: TaskCaseBrief[] = [
  caseBrief(CASE_A, '用例 A', 'completed', 'completed', '分组一', ['标签一']),
  caseBrief(CASE_B, '用例 B', 'failed', 'pending', null, []),
]

const DEVICES: TaskDeviceBrief[] = [
  { id: 9, name: 'pura90小艺', status: 'online', model: null },
]
const APIS: TaskApiBrief[] = [{ id: 3, name: '语音API', status: 'online' }]

/** 表实测形态：source 端点只到 id 级（无 status / result_type / 名称） */
const TRACE: ContainerSourceTrace = {
  taskId: 580,
  isCherryPick: true,
  total: 3,
  groups: [
    {
      sourceTaskId: 419,
      sourceTaskName: '任务419',
      sourceTaskStatus: null,
      results: [
        {
          resultId: 5714,
          sourceCaseId: CASE_A,
          sourceDeviceId: 9,
          sourceApiId: null,
          missing: false,
          resultType: null,
          executionStatus: null,
          evaluated: null,
          caseName: null,
          deviceName: null,
          apiName: null,
          createdAt: '2026-10-20T10:00:00',
        },
      ],
    },
    {
      sourceTaskId: 384,
      sourceTaskName: null,
      sourceTaskStatus: null,
      results: [
        {
          resultId: 3792,
          sourceCaseId: CASE_B,
          sourceDeviceId: null,
          sourceApiId: 3,
          missing: false,
          resultType: null,
          executionStatus: null,
          evaluated: null,
          caseName: null,
          deviceName: null,
          apiName: null,
          createdAt: null,
        },
        {
          resultId: 3796,
          sourceCaseId: CASE_B,
          sourceDeviceId: null,
          sourceApiId: 3,
          missing: true,
          resultType: null,
          executionStatus: null,
          evaluated: null,
          caseName: null,
          deviceName: null,
          apiName: null,
          createdAt: null,
        },
      ],
    },
  ],
}

describe('toCompositionEntries（§5.5.3 数据装配 + §5.5.4 降级口径）', () => {
  it('非容器（trace=null）→ 空条目', () => {
    expect(toCompositionEntries(null, CASES, DEVICES, APIS)).toEqual([])
  })

  it('名称由容器详情 join（用例 / 设备 / API），条目形状与购物车同构', () => {
    const entries = toCompositionEntries(TRACE, CASES, DEVICES, APIS)
    expect(entries).toHaveLength(3)

    const first = entries[0]
    expect(first.itemId).toBe('result:5714')
    expect(first.resultId).toBe(5714)
    expect(first.sourceTaskId).toBe(419)
    expect(first.sourceTaskName).toBe('任务419')
    expect(first.sourceCaseName).toBe('用例 A')
    expect(first.sourceDeviceId).toBe(9)
    expect(first.sourceDeviceName).toBe('pura90小艺')
    // §11-8 未落地：result_type 保持 null（树内折叠「结果类型待补充」）
    expect(first.sourceResultType).toBeNull()

    expect(entries[1].sourceTaskName).toBe('任务 384') // 缺名降级
    expect(entries[1].sourceApiName).toBe('语音API')
  })

  it('执行 / 评估状态降级取同 source_case_id 的容器用例行', () => {
    const entries = toCompositionEntries(TRACE, CASES, DEVICES, APIS)
    const a = entries[0]
    const b = entries[1]

    expect(a.executionStatus).toBe('completed')
    expect(a.evaluated).toBe(true)
    expect(a.statusFromCase).toBe(true)

    expect(b.executionStatus).toBe('failed')
    expect(b.evaluated).toBe(false)
    expect(b.evaluationStatus).toBe('pending')
  })

  it('§11-8 字段回来后直取结果级真值，不再降级', () => {
    const trace: ContainerSourceTrace = {
      ...TRACE,
      groups: [
        {
          ...TRACE.groups[0],
          results: [
            {
              ...TRACE.groups[0].results[0],
              resultType: 'real-time',
              executionStatus: 'failed',
              evaluated: true,
              caseName: '结果级用例名',
              deviceName: '结果级设备名',
            },
          ],
        },
      ],
    }
    const [entry] = toCompositionEntries(trace, CASES, DEVICES, APIS)
    expect(entry.sourceResultType).toBe('real-time')
    expect(entry.executionStatus).toBe('failed')
    expect(entry.statusFromCase).toBe(false)
    expect(entry.evaluated).toBe(true)
    expect(entry.sourceCaseName).toBe('结果级用例名')
    expect(entry.sourceDeviceName).toBe('结果级设备名')
  })

  it('失效条目标记 invalid（§5.5.6）', () => {
    const entries = toCompositionEntries(TRACE, CASES, DEVICES, APIS)
    expect(entries[2].invalid).toBe(true)
    expect(filterMissingEntries(entries).map((e) => e.resultId)).toEqual([3796])
  })
})

describe('groupCompositionEntries / summarizeComposition', () => {
  const entries = toCompositionEntries(TRACE, CASES, DEVICES, APIS)

  it('按来源任务分组且保持 source 顺序', () => {
    const groups = groupCompositionEntries(entries)
    expect(groups.map((g) => g.taskId)).toEqual([419, 384])
    expect(groups.map((g) => g.taskName)).toEqual(['任务419', '任务 384'])
    expect(groups[1].entries).toHaveLength(2)
  })

  it('摘要口径：条数 / 失败 / 未评估 / 失效 / 任务 / 用例 / 设备', () => {
    expect(summarizeComposition(entries)).toEqual({
      total: 3,
      failed: 2,
      unevaluated: 2,
      missing: 1,
      taskCount: 2,
      caseCount: 2,
      deviceCount: 2,
    })
  })
})

describe('filterCompositionEntries（§5.5.4 筛选联动）', () => {
  const entries = toCompositionEntries(TRACE, CASES, DEVICES, APIS)

  it('执行状态 facet', () => {
    expect(filterCompositionEntries(entries, 'completed').map((e) => e.resultId)).toEqual([
      5714,
    ])
    expect(filterCompositionEntries(entries, 'failed').map((e) => e.resultId)).toEqual([
      3792, 3796,
    ])
    expect(filterCompositionEntries(entries, 'stopped')).toEqual([])
  })

  it('评估状态 facet', () => {
    expect(
      filterCompositionEntries(entries, 'all', 'evaluated').map((e) => e.resultId)
    ).toEqual([5714])
    expect(
      filterCompositionEntries(entries, 'all', 'unevaluated').map((e) => e.resultId)
    ).toEqual([3792, 3796])
  })
})

describe('organizeCompositionCases（用例层组织）', () => {
  const entries = toCompositionEntries(TRACE, CASES, DEVICES, APIS)

  it('分组视图：有分组名的成组，无分组的落「未分组」', () => {
    const groups = organizeCompositionCases(entries, 'group', 'flat')
    expect(groups.map((g) => g.label)).toEqual(['分组一', '未分组'])
    expect(groups[0].units.map((u) => u.caseName)).toEqual(['用例 A'])
    expect(groups[1].units.map((u) => u.caseName)).toEqual(['用例 B'])
  })

  it('标签视图：多标签用例在命中标签各出现一次，无标签落「未设置标签」', () => {
    const groups = organizeCompositionCases(entries, 'tag', 'flat')
    expect(groups.map((g) => g.label).sort()).toEqual(['标签一', '未设置标签'].sort())
  })

  it('交叉子视图产生二级分组', () => {
    const groups = organizeCompositionCases(entries, 'group', 'byTag')
    expect(groups[0].subGroups.length).toBeGreaterThan(0)
  })
})
