/**
 * 任务域 adapter 键形态断言（INT-2239）：
 * 后端 snake_case DTO → camelCase 领域对象，转换只在本层发生；领域侧不得残留下划线键。
 */
import { describe, expect, it } from 'vitest'

import {
  toCherryPickTask,
  toPublishedTaskDetail,
  toPublishedTaskExecuteResult,
  toPublishedTaskItem,
  toTaskDetail,
  toTaskListItem,
} from '@/infrastructure/adapters/dto/task-adapter'
import type {
  PublishedTaskDetailDto,
  PublishedTaskItemDto,
  TaskDetailDto,
  TaskListItemDto,
} from '@/infrastructure/dto/task.dto'

/**
 * 递归收集对象里的 snake_case 键（领域对象侧应为空）。
 * `config` / `algorithmParams` / 快照体是后端不透明明文，按原字节透传，
 * 其内部键不做转换，故不参与扫描。
 */
const RAW_PAYLOAD_KEYS = new Set(['config', 'algorithmParams', 'snapshotConfig', 'reportSnapshot'])

function snakeKeys(value: unknown, path = ''): string[] {
  if (Array.isArray(value)) return value.flatMap((v, i) => snakeKeys(v, `${path}[${i}]`))
  if (value == null || typeof value !== 'object') return []
  return Object.entries(value as Record<string, unknown>).flatMap(([k, v]) => {
    const here = path ? `${path}.${k}` : k
    if (RAW_PAYLOAD_KEYS.has(k)) return []
    return k.includes('_') ? [here, ...snakeKeys(v, here)] : snakeKeys(v, here)
  })
}

const listItemDto: TaskListItemDto = {
  id: 419,
  name: '接线测试_任务域',
  description: 'adapter 键形态',
  status: 'completed',
  execution_status: 'completed',
  evaluation_status: 'completed',
  device_types: ['e2e'],
  config: {},
  algorithm_type: 'asr_streaming',
  algorithm_params: { beam_size: 8 },
  started_at: '2026-10-30T10:00:00',
  completed_at: '2026-10-30T10:05:00',
  total_cases: 12,
  case_count: 12,
  device_count: 1,
  completed_cases: 10,
  failed_cases: 2,
  tags: ['回归'],
  created_at: '2026-10-30T09:59:00',
  updated_at: '2026-10-30T10:06:00',
  is_favorite: true,
  is_cherry_pick: true,
  merge_type: 'picked',
  source_task_count: 2,
  source_result_count: 3,
  deleted: false,
  deleted_at: null,
  deleted_by_user_id: null,
  reports: {
    count: 1,
    reports: [
      { id: 7, name: '报告A', status: 'draft', type: 'task', created_at: '2026-10-30T10:07:00' },
    ],
  },
  devices: [{ id: 9, name: 'pura90小艺', status: 'online', model: 'P90' }],
  apis: [{ id: 3, name: 'ASR 接口', status: 'online' }],
  source_tasks: [
    {
      id: 400,
      name: '源任务',
      status: 'completed',
      total_cases: 6,
      completed_cases: 6,
      failed_cases: 0,
      created_at: '2026-10-29T09:00:00',
    },
  ],
}

const detailDto: TaskDetailDto = {
  id: 419,
  name: '接线测试_任务域',
  description: null,
  status: 'completed',
  execution_status: 'completed',
  evaluation_status: 'completed',
  device_types: ['e2e'],
  config: { concurrent_tasks: 3 },
  algorithm_type: 'asr_streaming',
  algorithm_params: null,
  started_at: '2026-10-30T10:00:00',
  completed_at: '2026-10-30T10:05:00',
  expected_total_time: '5 分钟',
  expected_complete_time: '2026-10-30T10:05:00',
  used_time: '5 分钟',
  total_cases: 1,
  case_count: 1,
  device_count: 1,
  completed_cases: 1,
  failed_cases: 0,
  tags: [],
  cases: [
    {
      case_id: '929e5dbb-2279-4b66-8cb4-23da895db367',
      name: '用例A',
      status: 'completed',
      execution_status: 'completed',
      evaluation_status: 'completed',
      started_at: '2026-10-30T10:00:00',
      completed_at: '2026-10-30T10:01:00',
      duration: 60,
      rounds_count: 2,
      error_message: null,
      group_name: '分组A',
      tags: ['回归'],
      evaluation_dimensions: [{ id: 72, name: '逐轮话轮评估' }],
      reviewed: true,
      target_count: 1,
      targets: [
        {
          task_case_id: 9001,
          target_type: 'device',
          device_type: 'smart_speaker',
          device_id: '9',
          api_id: null,
          target_name: 'pura90小艺',
          status: 'completed',
          execution_status: 'completed',
          evaluation_status: 'completed',
          started_at: '2026-10-30T10:00:00',
          completed_at: '2026-10-30T10:01:00',
          duration: 60,
          error_message: null,
        },
      ],
    },
  ],
  devices: [{ id: 9, name: 'pura90小艺', status: 'online', model: 'P90' }],
  apis: [{ id: 3, name: 'ASR 接口', status: 'online' }],
  review_count: 2,
  created_at: '2026-10-30T09:59:00',
  updated_at: '2026-10-30T10:06:00',
  created_by_user_id: 1,
}

describe('toTaskListItem', () => {
  it('snake_case DTO → camelCase 领域对象，且无下划线残留', () => {
    const item = toTaskListItem(listItemDto)

    expect(snakeKeys(item)).toEqual([])
    expect(item.executionStatus).toBe('completed')
    expect(item.evaluationStatus).toBe('completed')
    expect(item.deviceTypes).toEqual(['e2e'])
    expect(item.algorithmType).toBe('asr_streaming')
    expect(item.algorithmParams).toEqual({ beam_size: 8 })
    expect(item.totalCases).toBe(12)
    expect(item.caseCount).toBe(12)
    expect(item.completedCases).toBe(10)
    expect(item.failedCases).toBe(2)
    expect(item.createdAt).toBe('2026-10-30T09:59:00')
    expect(item.updatedAt).toBe('2026-10-30T10:06:00')
    expect(item.isFavorite).toBe(true)
    expect(item.isCherryPick).toBe(true)
    expect(item.mergeType).toBe('picked')
    expect(item.sourceTaskCount).toBe(2)
    expect(item.sourceResultCount).toBe(3)
    expect(item.deletedByUserId).toBeNull()
    // 派生字段
    expect(item.apiCount).toBe(1)
    // 嵌套对象同样 camelCase
    expect(item.reports?.reports[0].createdAt).toBe('2026-10-30T10:07:00')
    expect(item.sourceTasks[0]).toMatchObject({
      id: 400,
      totalCases: 6,
      completedCases: 6,
      failedCases: 0,
    })
    expect(snakeKeys(item.sourceTasks)).toEqual([])
  })

  it('后端缺省 merge_type/is_cherry_pick 时按普通任务处理', () => {
    const item = toTaskListItem({
      ...listItemDto,
      is_cherry_pick: null,
      merge_type: null,
      source_task_count: null,
      source_tasks: [],
      case_count: null,
      total_cases: 4,
    })

    expect(item.isCherryPick).toBe(false)
    expect(item.mergeType).toBeNull()
    expect(item.sourceTaskCount).toBeNull()
    expect(item.caseCount).toBe(4)
  })
})

describe('toTaskDetail', () => {
  it('详情与嵌套用例/目标全部 camelCase，无下划线残留', () => {
    const detail = toTaskDetail(detailDto)

    expect(snakeKeys(detail)).toEqual([])
    expect(detail.executionStatus).toBe('completed')
    expect(detail.expectedTotalTime).toBe('5 分钟')
    expect(detail.expectedCompleteTime).toBe('2026-10-30T10:05:00')
    expect(detail.usedTime).toBe('5 分钟')
    expect(detail.reviewCount).toBe(2)
    // INT-2446：创建人 id 映射到领域对象（姓名不在详情接口，application 层另查）
    expect(detail.createdByUserId).toBe(1)
    // 派生字段（config 内部是后端配置原文，键不转换）
    expect(detail.concurrency).toBe(3)
    expect(detail.apiCount).toBe(1)

    const brief = detail.cases[0]
    expect(brief.caseId).toBe('929e5dbb-2279-4b66-8cb4-23da895db367')
    expect(brief.roundsCount).toBe(2)
    expect(brief.groupName).toBe('分组A')
    expect(brief.evaluationDimensions).toEqual([{ id: 72, name: '逐轮话轮评估' }])
    expect(brief.reviewed).toBe(true)
    expect(brief.targetCount).toBe(1)

    const target = brief.targets?.[0]
    expect(target).toMatchObject({
      taskCaseId: 9001,
      targetType: 'device',
      deviceType: 'smart_speaker',
      deviceId: '9',
      apiId: null,
      targetName: 'pura90小艺',
      executionStatus: 'completed',
      evaluationStatus: 'completed',
    })
  })

  it('review_count 缺省容错为 0、concurrency 非数值时为 null、created_by_user_id 缺省为 null', () => {
    const detail = toTaskDetail({
      ...detailDto,
      review_count: null,
      config: { concurrent_tasks: '3' },
      cases: [],
      created_by_user_id: undefined,
    })

    expect(detail.reviewCount).toBe(0)
    expect(detail.concurrency).toBeNull()
    expect(detail.createdByUserId).toBeNull()
  })
})

describe('已发布任务 / 挑选合并', () => {
  const publishedItemDto: PublishedTaskItemDto = {
    id: 55,
    source_task_id: 419,
    name: '发布版 v3',
    description: null,
    type: 'e2e',
    algorithm_type: 'asr_streaming',
    status: 'published',
    benchmark: false,
    version: 3,
    is_current: true,
    version_count: 3,
    published_by: '接线测试_admin',
    published_at: '2026-10-30T11:00:00',
    archived_at: null,
    created_at: '2026-10-30T11:00:00',
  }

  it('toPublishedTaskItem：snake → camel', () => {
    const item = toPublishedTaskItem(publishedItemDto)

    expect(snakeKeys(item)).toEqual([])
    expect(item.sourceTaskId).toBe(419)
    expect(item.algorithmType).toBe('asr_streaming')
    expect(item.isCurrent).toBe(true)
    expect(item.versionCount).toBe(3)
    expect(item.publishedBy).toBe('接线测试_admin')
    expect(item.publishedAt).toBe('2026-10-30T11:00:00')
    expect(item.createdAt).toBe('2026-10-30T11:00:00')
  })

  it('toPublishedTaskDetail：快照与执行历史 camel', () => {
    const dto: PublishedTaskDetailDto = {
      ...publishedItemDto,
      task_group_id: 9,
      snapshot_config: { taskSnapshot: { schemaVersion: 2 } },
      has_task_snapshot: true,
      publish_reason: '基线',
      archived_by: null,
      source_task_name: '接线测试_任务域',
      source_task_status: 'completed',
      source_task_total_cases: 12,
      source_task_completed_cases: 12,
      report_snapshot: null,
      has_report_snapshot: false,
      versions: [publishedItemDto],
      execution_history: [
        {
          task_id: 601,
          task_name: '发布执行',
          version: 3,
          status: 'completed',
          total_cases: 12,
          completed_cases: 12,
          created_at: '2026-10-30T12:00:00',
          completed_at: '2026-10-30T12:05:00',
        },
      ],
    }
    const detail = toPublishedTaskDetail(dto)

    expect(snakeKeys(detail)).toEqual([])
    expect(detail.taskGroupId).toBe(9)
    expect(detail.snapshotConfig).toEqual({ taskSnapshot: { schemaVersion: 2 } })
    expect(detail.hasTaskSnapshot).toBe(true)
    expect(detail.publishReason).toBe('基线')
    expect(detail.sourceTaskTotalCases).toBe(12)
    expect(detail.sourceTaskCompletedCases).toBe(12)
    expect(detail.hasReportSnapshot).toBe(false)
    expect(detail.versions[0].isCurrent).toBe(true)
    expect(detail.executionHistory[0]).toMatchObject({
      taskId: 601,
      taskName: '发布执行',
      totalCases: 12,
      completedCases: 12,
      createdAt: '2026-10-30T12:00:00',
      completedAt: '2026-10-30T12:05:00',
    })
  })

  it('toPublishedTaskExecuteResult：执行结果 camel', () => {
    const result = toPublishedTaskExecuteResult({
      task_id: 601,
      task_name: '发布执行',
      published_task_id: 55,
      published_task_version: 3,
    })

    expect(result).toEqual({
      taskId: 601,
      taskName: '发布执行',
      publishedTaskId: 55,
      publishedTaskVersion: 3,
    })
  })

  it('toCherryPickTask：挑选项 camel', () => {
    const task = toCherryPickTask(listItemDto)

    expect(snakeKeys(task)).toEqual([])
    expect(task.executionStatus).toBe('completed')
    expect(task.totalCases).toBe(12)
    expect(task.sourceTaskCount).toBe(1)
    expect(task.sourceTaskIds).toEqual([400])
    expect(task.createdAt).toBe('2026-10-30T09:59:00')
    expect(task.isFavorite).toBe(true)
  })
})
