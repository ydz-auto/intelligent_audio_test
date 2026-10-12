/**
 * INT-215 回归：收藏标记 / 回收站字段（isFavorite/deleted/deletedAt/deletedByUserId）
 * 在各实体 DTO → Domain 映射中的契约。
 *
 * 缺陷背景（P3/P6）：前端全库零 deletedAt/deletedBy 展示、用例收藏态在
 * 列表不可见（actions 静态生成）。锁定 adapter 字段映射不被回退；
 * NULL（AUTH_MODE=off）容忍为 undefined / false，由视图层显示「—」。
 */
import { describe, it, expect } from 'vitest'
import { toTestCase, toTagViewItem } from '../testCaseAdapter'
import { toTask } from '../taskAdapter'
import { toReportListItem } from '../reportAdapter'
import type { TestCaseDto, TagViewItemDto } from '../../dto/testCaseDto'

describe('INT-215：toTestCase 收藏 / 回收站字段映射', () => {
  it('snake_case 字段 → camelCase（含删除人/删除时间）', () => {
    const domain = toTestCase({
      id: 'tc-1',
      name: '已删用例',
      is_favorite: true,
      deleted: true,
      deleted_at: '2026-10-12T10:00:00',
      deleted_by_user_id: 7,
    } as TestCaseDto)
    expect(domain.isFavorite).toBe(true)
    expect(domain.deleted).toBe(true)
    expect(domain.deletedAt).toBe('2026-10-12T10:00:00')
    expect(domain.deletedByUserId).toBe(7)
  })

  it('AUTH_MODE=off（NULL）容忍：isFavorite/deleted 缺省、deletedAt/deletedByUserId null → undefined', () => {
    const domain = toTestCase({
      id: 'tc-2',
      name: '活跃用例',
      is_favorite: null,
      deleted: null,
      deleted_at: null,
      deleted_by_user_id: null,
    } as unknown as TestCaseDto)
    expect(domain.isFavorite).toBeUndefined()
    expect(domain.deleted).toBe(false)
    expect(domain.deletedAt).toBeUndefined()
    expect(domain.deletedByUserId).toBeUndefined()
  })
})

describe('INT-215：标签视图内层用例同口径映射（回收站+标签视图断链回归）', () => {
  it('camelCase 顶层字段 isFavorite/deleted/deletedAt/deletedByUserId 透传', () => {
    const domain = toTagViewItem({
      tag: '回归',
      testCases: [
        {
          id: 'tc-9',
          name: '标签内已删用例',
          isFavorite: false,
          deleted: true,
          deletedAt: '2026-10-12T09:00:00',
          deletedByUserId: 3,
        },
      ],
    } as unknown as TagViewItemDto)
    const tc = domain.testCases[0]
    expect(tc.isFavorite).toBe(false)
    expect(tc.deleted).toBe(true)
    expect(tc.deletedAt).toBe('2026-10-12T09:00:00')
    expect(tc.deletedByUserId).toBe(3)
  })
})

describe('INT-215：toTask 回收站字段映射', () => {
  it('deleted_at/deleted_by_user_id → deletedAt/deletedByUserId', () => {
    const task = toTask({
      id: 1,
      name: '已删任务',
      status: 'completed',
      tags: [],
      devices: [],
      apis: [],
      deleted: true,
      deleted_at: '2026-10-12T08:00:00',
      deleted_by_user_id: 5,
    } as any)
    expect(task.deleted).toBe(true)
    expect(task.deletedAt).toBe('2026-10-12T08:00:00')
    expect(task.deletedByUserId).toBe(5)
  })

  it('活跃任务（NULL 字段）容忍为 undefined', () => {
    const task = toTask({
      id: 2,
      name: '活跃任务',
      status: 'pending',
      tags: [],
      devices: [],
      apis: [],
      deleted: false,
      deleted_at: null,
      deleted_by_user_id: null,
    } as any)
    expect(task.deletedAt).toBeUndefined()
    expect(task.deletedByUserId).toBeUndefined()
  })
})

describe('INT-215：toReportListItem 回收站字段映射（report_service 补齐后生效）', () => {
  const base = {
    id: 11,
    name: '已删报告',
    type: 'task',
    task_name: '任务A',
    summary: {},
    status: 'draft',
    created_at: '2026-10-12T07:00:00',
  } as any

  it('deleted_at/deleted_by_user_id → deletedAt/deletedByUserId', () => {
    const item = toReportListItem({ ...base, deleted: true, deleted_at: '2026-10-12T06:00:00', deleted_by_user_id: 9 })
    expect(item.deleted).toBe(true)
    expect(item.deletedAt).toBe('2026-10-12T06:00:00')
    expect(item.deletedByUserId).toBe(9)
  })

  it('后端未返回字段（现状）容忍为 undefined，视图层显示「—」', () => {
    const item = toReportListItem({ ...base })
    expect(item.deleted).toBeUndefined()
    expect(item.deletedAt).toBeUndefined()
    expect(item.deletedByUserId).toBeUndefined()
  })
})
