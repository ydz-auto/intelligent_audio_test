/**
 * 参数历史回滚 API 契约单测（INT-2341）。
 *
 * 后端两种回执都要归一：API 作用域只回 paramsRestored / mappingsRestored（含 detail），
 * 设备作用域回 created/updated/deleted。锁 snake_case 只在 infrastructure 层消化。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  fetchParamHistory,
  restoreParamHistory,
} from '@/infrastructure/api/param-history-api'
import { setSessionExpiredHandler } from '@/infrastructure/api/client'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function ok(data: unknown): Response {
  return jsonResponse({ success: true, code: 0, data })
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  authTokenStore.clear()
  setSessionExpiredHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
  authTokenStore.clear()
  setSessionExpiredHandler(null)
})

describe('restoreParamHistory', () => {
  it('API 作用域回执：读出 paramsRestored / mappingsRestored（0 也要保留）', async () => {
    fetchMock.mockResolvedValueOnce(
      ok({
        paramsRestored: 1,
        mappingsRestored: 0,
        detail: { params_updated: 1 },
      })
    )

    const result = await restoreParamHistory(9)

    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/algorithm/param-history/9/restore')
    expect(result).toMatchObject({ paramsRestored: 1, mappingsRestored: 0 })
  })

  it('设备作用域回执：created/updated/deleted 计数原样归一', async () => {
    fetchMock.mockResolvedValueOnce(
      ok({
        paramsCreated: 2,
        paramsUpdated: 1,
        paramsDeleted: 0,
        mappingsCreated: 0,
        mappingsUpdated: 1,
        mappingsDeleted: 0,
      })
    )

    const result = await restoreParamHistory(9)

    expect(result).toMatchObject({
      paramsCreated: 2,
      paramsUpdated: 1,
      paramsDeleted: 0,
      mappingsUpdated: 1,
    })
    expect(result.paramsRestored).toBeUndefined()
  })

  it('只回 detail（snake_case）时也能收敛出计数', async () => {
    fetchMock.mockResolvedValueOnce(
      ok({ detail: { params_created: 3, mappings_deleted: 1 } })
    )

    const result = await restoreParamHistory(9)

    expect(result).toMatchObject({ paramsCreated: 3, mappingsDeleted: 1 })
  })
})

describe('fetchParamHistory', () => {
  it('按 scope / scope_id / algorithm_type 读取版本列表', async () => {
    fetchMock.mockResolvedValueOnce(ok([]))

    await fetchParamHistory('api', 21, 'voice_llm')

    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v1/algorithm/param-history?scope=api&scope_id=21&algorithm_type=voice_llm'
    )
  })
})
