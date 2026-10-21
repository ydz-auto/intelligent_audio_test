/**
 * reportsApi.downloadCaseLogs 流式下载契约测试（INT-1071 返工，P2 真实进度/速度）
 * 覆盖：
 * - files 数组 → URL 编码 JSON query；缺省不带 query（整包兜底）
 * - JWT：localStorage auth_token 注入 Authorization（照 client.ts 拦截器）
 * - onProgress 收到真实已下载字节/总量 + 500ms 采样速率（速度 > 0）
 * - 非 2xx：JSON 错误体归拢为 Error（message/detail）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { reportsApi } from '../reportsApi'

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('reportsApi.downloadCaseLogs 流式下载', () => {
  it('files 数组 → URL 编码 JSON query；缺省不带 query（整包兜底）', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new Uint8Array([1, 2, 3]), { status: 200 })))

    await reportsApi.downloadCaseLogs(1201, 'case-1', ['a.txt', 'b.log'])
    const withFiles = vi.mocked(fetch).mock.calls[0]
    expect(String(withFiles[0])).toContain(`files=${encodeURIComponent(JSON.stringify(['a.txt', 'b.log']))}`)

    await reportsApi.downloadCaseLogs(1201, 'case-1')
    const withoutFiles = vi.mocked(fetch).mock.calls[1]
    expect(String(withoutFiles[0])).not.toContain('files=')
  })

  it('JWT：localStorage auth_token 注入 Authorization Bearer（照 client.ts）', async () => {
    localStorage.setItem('auth_token', 'tok-int1071')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new Uint8Array([1]), { status: 200 })))

    await reportsApi.downloadCaseLogs(1201, 'case-1')
    const headers = vi.mocked(fetch).mock.calls[0][1]?.headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer tok-int1071')
  })

  it('onProgress 收到真实已下载字节/总量，且跨 500ms 采样有速度', async () => {
    const total = 10
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new Uint8Array([1, 2, 3, 4, 5]))
        setTimeout(() => controller.enqueue(new Uint8Array([6, 7, 8, 9, 10])), 600)
        setTimeout(() => controller.close(), 650)
      },
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(stream, { status: 200, headers: { 'content-length': String(total) } })))

    const progress: { loaded: number; total: number; speed: number }[] = []
    const result = await reportsApi.downloadCaseLogs(1201, 'case-1', ['a.log'], (p) => progress.push(p))

    expect(result.size).toBe(total)
    expect(progress.length).toBeGreaterThanOrEqual(2)
    // 500ms 采样点：已下载 10/10，速度 > 0（10 字节 / ~0.6s）
    const sample = progress.find((p) => p.speed > 0)
    expect(sample).toBeTruthy()
    expect(sample?.loaded).toBe(total)
    expect(sample?.total).toBe(total)
    // 结束点：速度归 0、loaded=total
    const last = progress.at(-1)
    expect(last?.loaded).toBe(total)
    expect(last?.speed).toBe(0)
  })

  it('未知总量（无 content-length）时 total=0，仍上报已下载字节', async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new Uint8Array([1, 2]))
        controller.close()
      },
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(stream, { status: 200 })))

    const progress: { loaded: number; total: number; speed: number }[] = []
    await reportsApi.downloadCaseLogs(1201, 'case-1', [], (p) => progress.push(p))

    expect(progress.at(-1)?.loaded).toBe(2)
    expect(progress.at(-1)?.total).toBe(0)
  })

  it('非 2xx：JSON 错误体归拢 message/detail 抛出', async () => {
    const body = JSON.stringify({ message: '日志不存在', detail: 'no such log dir' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 404 })))

    await expect(reportsApi.downloadCaseLogs(1201, 'case-1')).rejects.toThrow('日志不存在')
  })

  it('非 2xx：非 JSON 错误体走状态码兜底', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('Not Found', { status: 404 })))

    await expect(reportsApi.downloadCaseLogs(1201, 'case-1')).rejects.toThrow(/HTTP 404/)
  })
})
