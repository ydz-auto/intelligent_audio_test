/**
 * 日志 WS DTO 映射测试（INT-928 接线）：锁定 Socket.IO /ws/logs task_log 真实契约
 * （socketio_server.py broadcast_log wire {task_id, log}，log 载荷 = _websocket_mixin
 * log_payload 子集：id/time/level/module/content/mark/task_id/test_case_id/category/source，
 * snake_case）→ Domain LogItem（camelCase）；缺失字段（device_id/api_id/thread_id/
 * algorithm_type）置 null。
 */
import { describe, expect, it } from 'vitest'

import { toLogFromWs } from '@/infrastructure/dto/log.dto'

describe('log.dto toLogFromWs', () => {
  it('task_log wire → LogItem（snake_case→camelCase 收敛 + 缺失字段 null）', () => {
    const log = toLogFromWs({
      task_id: '42',
      log: {
        id: 1001,
        time: '2026-10-19 10:00:00',
        level: 'ERROR',
        module: 'api',
        content: '接口调用失败',
        mark: '',
        task_id: 42,
        test_case_id: 'TC-001',
        category: 'test',
        source: 'run_all',
      },
    })
    expect(log).toEqual({
      id: 1001,
      time: '2026-10-19 10:00:00',
      level: 'ERROR',
      category: 'test',
      module: 'api',
      source: 'run_all',
      content: '接口调用失败',
      mark: '',
      deviceId: null,
      taskId: 42,
      apiId: null,
      testCaseId: 'TC-001',
      threadId: null,
      algorithmType: null,
    })
  })

  it('空载荷容错：log 缺失返回 null', () => {
    expect(toLogFromWs(null)).toBeNull()
    expect(toLogFromWs({ task_id: null, log: null })).toBeNull()
    expect(toLogFromWs(undefined)).toBeNull()
  })
})
