/**
 * 用例导出请求体（INT-2196「包含音频文件」）。
 * ZIP 包下发 include_audios（默认 false，与任务数据导出同名选项同口径）；Excel/JSON 不带。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  API_BASE_URL,
  setSessionExpiredHandler,
} from '@/infrastructure/api/client'
import { exportTestCases } from '@/infrastructure/api/testcases-api'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

/** 导出回字节流：用字符串体构造（jsdom 的 Blob 不能直接喂给 Response） */
function blobResponse(): Response {
  return new Response('PK', {
    status: 200,
    headers: { 'Content-Type': 'application/zip' },
  })
}

function lastBody(): Record<string, unknown> {
  const call = fetchMock.mock.calls.at(-1)
  if (!call) throw new Error('没有发起请求')
  return JSON.parse(String((call[1] as RequestInit).body)) as Record<string, unknown>
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  fetchMock.mockImplementation(() => Promise.resolve(blobResponse()))
  authTokenStore.clear()
  setSessionExpiredHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
  authTokenStore.clear()
  setSessionExpiredHandler(null)
})

describe('exportTestCases 请求体（INT-2196）', () => {
  it('ZIP + 勾选音频：include_audios=true 且走 /testcases/export', async () => {
    await exportTestCases(['tc-1'], 'zip', {
      includeReferenceParams: true,
      includeAudios: true,
    })

    expect(String((fetchMock.mock.calls.at(-1)?.[0] as string))).toBe(
      `${API_BASE_URL}/testcases/export`
    )
    expect(lastBody()).toEqual({
      ids: ['tc-1'],
      format: 'zip',
      include_reference_params: true,
      include_audios: true,
    })
  })

  it('ZIP 未勾选音频：仍显式下发 include_audios=false（默认不打包）', async () => {
    await exportTestCases(['tc-1'], 'zip')

    expect(lastBody()).toEqual({
      ids: ['tc-1'],
      format: 'zip',
      include_reference_params: true,
      include_audios: false,
    })
  })

  it('Excel 导出不带音频开关', async () => {
    await exportTestCases(['tc-1'], 'xlsx', { includeAudios: true })

    const body = lastBody()
    expect(body).toEqual({ ids: ['tc-1'], format: 'xlsx' })
    expect(body).not.toHaveProperty('include_audios')
  })
})
