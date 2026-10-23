/**
 * INT-1624 设备导入导出接线：devicesApi exportDeviceResource/importDeviceResource。
 * 覆盖三页签资源端点映射、format/ids query、blob 文件流（不走信封）、
 * FormData 字段名 file、ResourceImportResult snake→camel。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL, setSessionExpiredHandler } from '@/infrastructure/api/client'
import {
  buildDeviceExportFilename,
  exportDeviceResource,
  importDeviceResource,
} from '@/infrastructure/api/devicesApi'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function queueResponses(...responses: Response[]): void {
  fetchMock.mockImplementation(() => {
    const next = responses.shift()
    if (!next) throw new Error('fetch 调用超出 mock 队列')
    return Promise.resolve(next)
  })
}

function lastCall(index = 0): [string, RequestInit] {
  return fetchMock.mock.calls[index] as [string, RequestInit]
}

describe('设备导出文件名（INT-816 后端命名口径）', () => {
  const at = new Date(2026, 9, 24, 9, 30, 5)

  it('三资源前缀 + 时间戳 + 扩展名', () => {
    expect(buildDeviceExportFilename('test', 'json', at)).toBe('test_devices_20261024_093005.json')
    expect(buildDeviceExportFilename('playback', 'excel', at)).toBe(
      'playback_devices_20261024_093005.xlsx'
    )
    expect(buildDeviceExportFilename('api', 'json', at)).toBe('apis_20261024_093005.json')
  })
})

describe('exportDeviceResource（GET /{resource}/export，文件流）', () => {
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

  it('测试设备 JSON：format=json、不带 ids，返回 blob', async () => {
    queueResponses(new Response(new Uint8Array([0x7b, 0x7d]), { status: 200 }))
    const { blob, filename } = await exportDeviceResource('test', { format: 'json' })
    const [url, init] = lastCall()
    expect(url).toBe(`${API_BASE_URL}/test-devices/export?format=json`)
    expect(init.method).toBe('GET')
    expect(blob.size).toBe(2)
    expect(filename).toMatch(/^test_devices_\d{8}_\d{6}\.json$/)
  })

  it('播放设备 Excel + 选中 ids：format=excel、ids 逗号分隔', async () => {
    queueResponses(new Response(new Uint8Array([0x50, 0x4b]), { status: 200 }))
    const { filename } = await exportDeviceResource('playback', {
      format: 'excel',
      ids: [3, 5],
    })
    const [url] = lastCall()
    expect(url).toBe(`${API_BASE_URL}/playback-devices/export?format=excel&ids=3%2C5`)
    expect(filename).toMatch(/^playback_devices_\d{8}_\d{6}\.xlsx$/)
  })

  it('空 id 集按不传处理（不误导出全量）', async () => {
    queueResponses(new Response(new Uint8Array([]), { status: 200 }))
    await exportDeviceResource('api', { format: 'json', ids: [] })
    const [url] = lastCall()
    expect(url).toBe(`${API_BASE_URL}/apis/export?format=json`)
  })
})

describe('importDeviceResource（POST /{resource}/import，multipart file）', () => {
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

  it('字段名 file + 计数报告 snake→camel', async () => {
    queueResponses(
      jsonResponse({
        success: true,
        code: 0,
        message: '成功导入 1 个，更新 2 个，跳过 1 个',
        data: {
          imported_count: 1,
          updated_count: 2,
          skipped_count: 1,
          errors: ['第3行: 缺少匹配键 serial_number'],
        },
      })
    )
    const file = new File(['{}'], 'devices.json', { type: 'application/json' })
    const result = await importDeviceResource('test', file)
    const [url, init] = lastCall()
    expect(url).toBe(`${API_BASE_URL}/test-devices/import`)
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    expect((init.body as FormData).get('file')).toBeInstanceOf(File)
    expect(result).toEqual({
      importedCount: 1,
      updatedCount: 2,
      skippedCount: 1,
      errors: ['第3行: 缺少匹配键 serial_number'],
    })
  })

  it('errors 缺失收敛为空数组', async () => {
    queueResponses(
      jsonResponse({
        success: true,
        code: 0,
        data: { imported_count: 0, updated_count: 0, skipped_count: 0 },
      })
    )
    const result = await importDeviceResource(
      'api',
      new File(['{}'], 'apis.json', { type: 'application/json' })
    )
    expect(result.errors).toEqual([])
  })
})
