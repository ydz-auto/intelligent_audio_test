/**
 * notificationAdapter SSE→Domain 映射单测（INT-731 通知中心接线）。
 * 重点回归：task_progress 后端字段为 total_progress（P2-1 返修，非 progress），
 * 事件形状对照 shared/schemas/socket_payloads.py TaskProgressPayload。
 */
import { describe, expect, it } from 'vitest'

import {
  mapSseEventToNotification,
  notificationDotClass,
} from '@/infrastructure/adapters/notificationAdapter'
import type { SseEvent } from '@/infrastructure/realtime/sse'

function makeEvent(eventType: string, data: unknown): SseEvent {
  return { channel: 'task_events', eventType, data, id: undefined }
}

describe('mapSseEventToNotification', () => {
  it('task_progress 读后端 total_progress（P2-1：非 progress，进度不再恒 0%）', () => {
    const item = mapSseEventToNotification(
      makeEvent('task_progress', {
        task_id: 7,
        status: 'running',
        total_progress: 50.4,
        execution_status: 'executing',
      })
    )
    expect(item).not.toBeNull()
    expect(item?.kind).toBe('task')
    expect(item?.content).toBe('进度 50%')
    expect(item?.taskId).toBe('7')
  })

  it('task_progress 缺 total_progress 时进度为 0（兜底，非 NaN）', () => {
    const item = mapSseEventToNotification(
      makeEvent('task_progress', { task_id: 9, status: 'pending' })
    )
    expect(item?.content).toBe('进度 0%')
  })

  it('task_progress 无 task_id 不进通知中心', () => {
    expect(
      mapSseEventToNotification(makeEvent('task_progress', { total_progress: 10 }))
    ).toBeNull()
  })

  it('report_generated 成功 → 报告行', () => {
    const item = mapSseEventToNotification(
      makeEvent('report_generated', { taskId: 3, reportId: 12, success: true })
    )
    expect(item?.kind).toBe('report')
    expect(item?.title).toBe('报告 #12')
    expect(item?.content).toBe('报告已生成')
  })

  it('report_generated 失败 → error 行且带错误信息', () => {
    const item = mapSseEventToNotification(
      makeEvent('report_generated', { taskId: 3, success: false, error: '超时' })
    )
    expect(item?.kind).toBe('error')
    expect(item?.content).toBe('超时')
  })

  it('import_progress 按 percentage 取标题', () => {
    const item = mapSseEventToNotification(
      makeEvent('import_progress', { current_table: 'cases', percentage: 100 })
    )
    expect(item?.kind).toBe('import')
    expect(item?.title).toBe('数据导入完成')
  })

  it('task_log 仅 ERROR/WARNING 进通知中心', () => {
    const error = mapSseEventToNotification(
      makeEvent('task_log', {
        task_id: 5,
        log_payload: { level: 'ERROR', module: 'api', content: '请求失败', time: '2026-10-18T16:00:00Z' },
      })
    )
    expect(error?.kind).toBe('error')
    expect(error?.content).toBe('请求失败')

    const info = mapSseEventToNotification(
      makeEvent('task_log', {
        task_id: 5,
        log_payload: { level: 'INFO', module: 'api', content: 'ok' },
      })
    )
    expect(info).toBeNull()
  })

  it('高频帧 realtime_frame / realtime_summary 不进通知中心', () => {
    expect(mapSseEventToNotification(makeEvent('realtime_frame', {}))).toBeNull()
    expect(mapSseEventToNotification(makeEvent('realtime_summary', {}))).toBeNull()
  })
})

describe('notificationDotClass', () => {
  it('语义类型 → 语义 token 色点（任务=info、报告=success、导入=chart-3、错误=destructive）', () => {
    expect(notificationDotClass('task')).toBe('bg-info')
    expect(notificationDotClass('report')).toBe('bg-success')
    expect(notificationDotClass('import')).toBe('bg-chart-3')
    expect(notificationDotClass('error')).toBe('bg-destructive')
    expect(notificationDotClass(undefined)).toBe('bg-info')
  })
})
