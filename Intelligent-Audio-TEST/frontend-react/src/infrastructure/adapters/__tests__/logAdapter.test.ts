/**
 * infrastructure/adapters/logAdapter 纯函数测试（17_配置运维.md §4：snake_case↔camelCase
 * 只在 infrastructure；查询参数显式 snake_case；数值兜底）。
 */
import { describe, expect, it } from 'vitest'

import {
  toLog,
  toLogClearDto,
  toLogMarkDto,
  toLogPage,
  toLogQueryDto,
  toLogRefreshRequestDto,
  toLogRefreshResult,
  toLogStatsData,
} from '@/infrastructure/adapters/logAdapter'
import type { LogItemDto, LogListDto } from '@/infrastructure/dto/log.dto'
import type { LogQuery } from '@/domain/models/log'

const itemDto: LogItemDto = {
  id: 12,
  time: '2026-10-19T10:00:00',
  level: 'ERROR',
  category: 'test',
  module: 'api',
  source: 'task_runner',
  content: '断言失败',
  mark: 'red',
  device_id: 7,
  task_id: 301,
  api_id: 5,
  test_case_id: 'tc-9',
  thread_id: 'thread-1',
  algorithm_type: 'asr',
}

describe('toLog', () => {
  it('snake_case DTO → camelCase Domain（全字段显式映射）', () => {
    expect(toLog(itemDto)).toEqual({
      id: 12,
      time: '2026-10-19T10:00:00',
      level: 'ERROR',
      category: 'test',
      module: 'api',
      source: 'task_runner',
      content: '断言失败',
      mark: 'red',
      deviceId: 7,
      taskId: 301,
      apiId: 5,
      testCaseId: 'tc-9',
      threadId: 'thread-1',
      algorithmType: 'asr',
    })
  })

  it('null 可选字段 → undefined（interfaces 层不出现 null）', () => {
    const log = toLog({ ...itemDto, mark: null, device_id: null, algorithm_type: null })
    expect(log.mark).toBeUndefined()
    expect(log.deviceId).toBeUndefined()
    expect(log.algorithmType).toBeUndefined()
  })
})

describe('toLogPage', () => {
  it('分页信封字段映射 + 数值兜底', () => {
    const dto: LogListDto = { items: [itemDto], total: 320, page: 2, pages: 16, per_page: 20 }
    const page = toLogPage(dto)
    expect(page.total).toBe(320)
    expect(page.page).toBe(2)
    expect(page.pages).toBe(16)
    expect(page.perPage).toBe(20)
    expect(page.items).toHaveLength(1)
    expect(page.items[0].id).toBe(12)
  })

  it('空/null DTO 兜底为空分页（无 undefined/NaN）', () => {
    const page = toLogPage(null)
    expect(page.items).toEqual([])
    expect(page.total).toBe(0)
    expect(page.page).toBe(1)
    expect(page.pages).toBe(1)
  })
})

describe('toLogStatsData', () => {
  it('五级计数数值兜底为 0', () => {
    expect(
      toLogStatsData({ total: 100, debug: 20, info: 40, warning: 25, error: 10, critical: 5 })
    ).toEqual({ total: 100, debug: 20, info: 40, warning: 25, error: 10, critical: 5 })
    expect(toLogStatsData(null)).toEqual({
      total: 0,
      debug: 0,
      info: 0,
      warning: 0,
      error: 0,
      critical: 0,
    })
  })
})

describe('toLogRefreshResult', () => {
  it('new_count/last_id 映射 + items 逐条转换', () => {
    const result = toLogRefreshResult({
      items: [itemDto],
      count: 1,
      new_count: 1,
      last_id: 99,
    })
    expect(result.newCount).toBe(1)
    expect(result.lastId).toBe(99)
    expect(result.items[0].algorithmType).toBe('asr')
  })
})

describe('toLogQueryDto', () => {
  it("camelCase → snake_case 显式映射，'all' 哨兵剔除", () => {
    const query: LogQuery = {
      page: 2,
      perPage: 20,
      keyword: '失败',
      startTime: '2026-10-19T09:00',
      endTime: '2026-10-19T18:00',
      category: 'test',
      module: 'all',
      mark: 'red',
      algorithmType: 'all',
      level: 'ERROR,INFO',
      deviceId: '7',
      taskId: '301',
      evaluationId: 'ev-1',
      userId: 'u-1',
      threadId: 'thread-1',
      contentInclude: '包含',
      contentExclude: '不包含',
    }
    expect(toLogQueryDto(query)).toEqual({
      page: 2,
      per_page: 20,
      keyword: '失败',
      start_time: '2026-10-19T09:00',
      end_time: '2026-10-19T18:00',
      category: 'test',
      mark: 'red',
      level: 'ERROR,INFO',
      device_id: '7',
      task_id: '301',
      evaluation_id: 'ev-1',
      user_id: 'u-1',
      thread_id: 'thread-1',
      content_include: '包含',
      content_exclude: '不包含',
    })
  })

  it('空查询只保留分页默认', () => {
    expect(toLogQueryDto({})).toEqual({})
  })
})

describe('toLogMarkDto / toLogClearDto / toLogRefreshRequestDto', () => {
  it('mark 默认 flagged；空字符串保留（取消标记）', () => {
    expect(toLogMarkDto({ logIds: [1, 2] })).toEqual({ log_ids: [1, 2], mark: 'flagged' })
    expect(toLogMarkDto({ logIds: [1], mark: '' })).toEqual({ log_ids: [1], mark: '' })
  })

  it('clear 请求体透传 before_datetime/keep_marked', () => {
    expect(toLogClearDto({ beforeDatetime: '2026-10-01T00:00', keepMarked: true })).toEqual({
      before_datetime: '2026-10-01T00:00',
      keep_marked: true,
    })
  })

  it('refresh last_id 数值化兜底 0', () => {
    expect(toLogRefreshRequestDto('42')).toEqual({ last_id: 42 })
    expect(toLogRefreshRequestDto(0)).toEqual({ last_id: 0 })
  })
})
