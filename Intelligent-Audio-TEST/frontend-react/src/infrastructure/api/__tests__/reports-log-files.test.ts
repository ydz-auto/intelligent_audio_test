/**
 * 报告日志文件列表 / 按选下载单测（INT-1067）。
 * fetchCaseLogFiles：GET /reports/{id}/cases/{cid}/logs snake_case → camelCase 映射；
 * downloadCaseLogs：?files= URL 编码 JSON 数组透传、缺省整包兼容、流式 onProgress 上报。
 * 统一 mock 全局 fetch（downloadCaseLogs 走流式 fetch，先例同 SSE 测试）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL } from '@/infrastructure/api/client'
import {
  downloadCaseLogs,
  fetchCaseLogFiles,
} from '@/infrastructure/api/reports-api'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function streamFromText(text: string, headers: Record<string, string> = {}): Response {
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(text))
        controller.close()
      },
    }),
    { status: 200, headers: { 'Content-Type': 'application/zip', ...headers } }
  )
}

/** text 的 UTF-8 字节数（Content-Length 与实际下载字节一致） */
function utf8Length(text: string): number {
  return new TextEncoder().encode(text).length
}

describe('报告日志文件列表 / 按选下载', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
    authTokenStore.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    authTokenStore.clear()
  })

  it('fetchCaseLogFiles：GET /reports/{id}/cases/{cid}/logs 且 updated_at → updatedAt（缺省省略）', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        success: true,
        code: 0,
        data: {
          items: [
            { name: 'case-1/audio.log', size: 1024, updated_at: '2026-10-20T10:00:00+08:00' },
            { name: 'business_logs/run.log', size: 2048 },
          ],
        },
      })
    )
    const files = await fetchCaseLogFiles(1201, 'case-1')
    expect(files).toEqual([
      { name: 'case-1/audio.log', size: 1024, updatedAt: '2026-10-20T10:00:00+08:00' },
      { name: 'business_logs/run.log', size: 2048, updatedAt: undefined },
    ])
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toBe(`${API_BASE_URL}/reports/1201/cases/case-1/logs`)
  })

  it('fetchCaseLogFiles：items 缺失时返回空数组（空态「该用例暂无日志文件」）', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ success: true, code: 0, data: { items: [] } }))
    const files = await fetchCaseLogFiles(1201, 'case-1')
    expect(files).toEqual([])
  })

  it('downloadCaseLogs：files 透传为 URL 编码 JSON 数组，返回 zip Blob', async () => {
    const text = 'PK\x03\x04zip-content'
    fetchMock.mockResolvedValue(streamFromText(text, { 'content-length': String(utf8Length(text)) }))
    const result = await downloadCaseLogs(1201, 'case-1', ['a.log', 'b.log'])
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url.startsWith(`${API_BASE_URL}/reports/1201/cases/case-1/logs/download?files=`)).toBe(true)
    const raw = decodeURIComponent(url.split('files=')[1])
    expect(JSON.parse(raw)).toEqual(['a.log', 'b.log'])
    expect(result.blob).toBeInstanceOf(Blob)
    expect(result.size).toBe(utf8Length(text))
  })

  it('downloadCaseLogs：不传 files 缺省整包（无 query），向后兼容', async () => {
    const text = 'PK\x03\x04zip-content'
    fetchMock.mockResolvedValue(streamFromText(text, { 'content-length': String(utf8Length(text)) }))
    await downloadCaseLogs(1201, 'case-1')
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toBe(`${API_BASE_URL}/reports/1201/cases/case-1/logs/download`)
  })

  it('downloadCaseLogs：onProgress 收到真实已下载字节 / 总量', async () => {
    const text = 'PK\x03\x04zip-content'
    fetchMock.mockResolvedValue(streamFromText(text, { 'content-length': String(utf8Length(text)) }))
    const onProgress = vi.fn()
    await downloadCaseLogs(1201, 'case-1', undefined, onProgress)
    expect(onProgress).toHaveBeenCalled()
    // 单块流：终报 loaded=received、total=Content-Length
    const last = onProgress.mock.calls.at(-1)?.[0] as { loaded: number; total: number; speed: number }
    expect(last.loaded).toBe(utf8Length(text))
    expect(last.total).toBe(utf8Length(text))
  })

  it('downloadCaseLogs：非 2xx 抛 ApiError（httpStatus 透传）', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: '所选日志文件不存在' }, 404)
    )
    await expect(downloadCaseLogs(1201, 'case-1', ['missing.log'])).rejects.toMatchObject({
      httpStatus: 404,
      detail: '所选日志文件不存在',
    })
  })
})
