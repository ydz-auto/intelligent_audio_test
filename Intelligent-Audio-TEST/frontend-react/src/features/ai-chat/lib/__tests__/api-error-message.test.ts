/**
 * 通用异常文案收敛（INT-2473 返工 P2-1）：`ApiError` 的 message 恒空的两条路径
 * 已由 `ApiError.userMessage` 覆盖，这里只钉「非 ApiError / 空 message 落到兜底」。
 */
import { describe, expect, it } from 'vitest'

import { NETWORK_FAILED_COPY } from '@/domain/models/auth'
import { ApiError } from '@/infrastructure/api/api-error'

import { resolveApiErrorMessage } from '../api-error-message'

const FALLBACK = '保存失败（版本可能已变化，请刷新后重试）'

describe('resolveApiErrorMessage', () => {
  it('网络层失败（message 为空）→ 网络文案，不是兜底也不是空串', () => {
    const error = new ApiError({
      httpStatus: null,
      message: '',
      detail: 'Failed to fetch',
      isNetworkError: true,
    })
    expect(resolveApiErrorMessage(error, FALLBACK)).toBe(NETWORK_FAILED_COPY)
  })

  it('服务端有 message → 原样使用', () => {
    const error = new ApiError({ httpStatus: 409, message: '版本已变化' })
    expect(resolveApiErrorMessage(error, FALLBACK)).toBe('版本已变化')
  })

  it('非 ApiError：有 message 用 message，空 message 用兜底', () => {
    expect(resolveApiErrorMessage(new Error('boom'), FALLBACK)).toBe('boom')
    expect(resolveApiErrorMessage(new Error(''), FALLBACK)).toBe(FALLBACK)
  })

  it('非 Error 异常 → 兜底', () => {
    expect(resolveApiErrorMessage(undefined, FALLBACK)).toBe(FALLBACK)
    expect(resolveApiErrorMessage('oops', FALLBACK)).toBe(FALLBACK)
  })
})
