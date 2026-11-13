/**
 * 任务 → 报告解析失败文案（INT-2473 返工 P2-2 残留）。
 *
 * 复核方实测两条 message 恒为空的路径都会把错误块漏成「该任务暂无关联报告」：
 * fetch 网络层失败（`isNetworkError`）与「只有 detail / 只有 HTTP 状态」的错误体。
 * 本文件把这两条钉成断言，防止有人改回 `error.message`。
 */
import { describe, expect, it } from 'vitest'

import { ApiError } from '@/infrastructure/api/api-error'
import { NETWORK_FAILED_COPY } from '@/domain/models/auth'

import {
  resolveTaskReportErrorMessage,
  TASK_REPORT_RESOLVE_FALLBACK_COPY,
} from '../task-report-error'

describe('resolveTaskReportErrorMessage', () => {
  it('网络层失败（message 为空）→ 网络文案，不是空串', () => {
    const error = new ApiError({
      httpStatus: null,
      message: '',
      detail: 'Failed to fetch',
      isNetworkError: true,
    })
    expect(error.message).toBe('')
    expect(resolveTaskReportErrorMessage(error)).toBe(NETWORK_FAILED_COPY)
  })

  it('HTTP 500 空响应体（message 为空）→ HTTP 兜底文案，不是空串', () => {
    const error = new ApiError({ httpStatus: 500, message: '' })
    expect(error.message).toBe('')
    expect(resolveTaskReportErrorMessage(error)).toBe('服务器内部错误，请稍后重试')
  })

  it('错误体只有 detail（网关 {"detail": ...}）→ 用 detail', () => {
    const error = new ApiError({
      httpStatus: 401,
      message: '',
      detail: '缺少认证令牌',
    })
    expect(resolveTaskReportErrorMessage(error)).toBe('缺少认证令牌')
  })

  it('服务端有 message → 原样使用', () => {
    const error = new ApiError({ httpStatus: 500, message: '报告服务暂不可用' })
    expect(resolveTaskReportErrorMessage(error)).toBe('报告服务暂不可用')
  })

  it('非 ApiError 的异常：有 message 用 message，空 message 用固定兜底', () => {
    expect(resolveTaskReportErrorMessage(new Error('boom'))).toBe('boom')
    expect(resolveTaskReportErrorMessage(new Error(''))).toBe(
      TASK_REPORT_RESOLVE_FALLBACK_COPY
    )
    expect(resolveTaskReportErrorMessage(undefined)).toBe(
      TASK_REPORT_RESOLVE_FALLBACK_COPY
    )
  })
})
