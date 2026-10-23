/**
 * INT-1628：三资源导入导出端点接线（对齐后端 INT-816）
 *
 * 覆盖：
 * 1) 导出 URL 与当前资源一一对应（test-devices / playback-devices / apis），format/ids 进 query；
 * 2) 文件名取自响应 Content-Disposition（缺头时按资源+扩展名兜底）；
 * 3) 导入 multipart 字段名 file，响应 snake_case → camelCase 计数。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}))

import { request } from '../../http/client'
import { devicesApi } from '../devicesApi'
import { playbackApi } from '../playbackApi'
import { apisApi } from '../apisApi'

const mockedRequest = vi.mocked(request)

/** 构造带响应头的 Blob（http/client 以 __responseHeaders 非枚举属性传递） */
function blobWithDisposition(filename: string): Blob {
  const blob = new Blob(['{}'], { type: 'application/json' })
  Object.defineProperty(blob, '__responseHeaders', {
    value: { 'content-disposition': `attachment; filename=${filename}` },
    enumerable: false,
    configurable: true,
  })
  return blob
}

beforeEach(() => {
  mockedRequest.mockReset()
})

describe('INT-1628 三资源导出端点', () => {
  it('测试设备：GET /test-devices/export?format=json，文件名取自 Content-Disposition', async () => {
    mockedRequest.mockResolvedValueOnce(blobWithDisposition('test_devices_20261024_101500.json'))
    const file = await devicesApi.exportFile({ format: 'json' })

    expect(mockedRequest).toHaveBeenCalledWith(
      'GET',
      '/test-devices/export',
      null,
      expect.objectContaining({ params: { format: 'json' }, responseType: 'blob' }),
    )
    expect(file.filename).toBe('test_devices_20261024_101500.json')
    expect(file.blob).toBeInstanceOf(Blob)
  })

  it('播放设备：ids 白名单走 CSV query；缺 Content-Disposition 时按 excel 兜底 .xlsx', async () => {
    mockedRequest.mockResolvedValueOnce(new Blob(['x']))
    const file = await playbackApi.exportFile({ format: 'excel', ids: [3, 4] })

    expect(mockedRequest).toHaveBeenCalledWith(
      'GET',
      '/playback-devices/export',
      null,
      expect.objectContaining({ params: { format: 'excel', ids: '3,4' }, responseType: 'blob' }),
    )
    expect(file.filename).toMatch(/^playback_devices_\d{8}_\d{6}\.xlsx$/)
  })

  it('API 配置：GET /apis/export（不串资源）', async () => {
    mockedRequest.mockResolvedValueOnce(blobWithDisposition('apis_20261024_101500.json'))
    const file = await apisApi.exportFile({ format: 'json', ids: ['1'] })

    expect(mockedRequest).toHaveBeenCalledWith(
      'GET',
      '/apis/export',
      null,
      expect.objectContaining({ params: { format: 'json', ids: '1' }, responseType: 'blob' }),
    )
    expect(file.filename).toBe('apis_20261024_101500.json')
  })

  it('filename*=UTF-8 中文文件名可解析', async () => {
    const blob = new Blob(['{}'])
    Object.defineProperty(blob, '__responseHeaders', {
      value: { 'content-disposition': "attachment; filename*=UTF-8''%E8%AE%BE%E5%A4%87.json" },
      enumerable: false,
      configurable: true,
    })
    mockedRequest.mockResolvedValueOnce(blob)
    const file = await devicesApi.exportFile({ format: 'json' })
    expect(file.filename).toBe('设备.json')
  })
})

describe('INT-1628 三资源导入端点', () => {
  it('测试设备：POST /test-devices/import multipart file=，计数 camelCase', async () => {
    mockedRequest.mockResolvedValueOnce({
      imported_count: 2,
      updated_count: 1,
      skipped_count: 1,
      errors: ['第3行: 缺少匹配键 serial_number'],
    })
    const upload = new File(['{"test_devices":[]}'], 'devices.json', { type: 'application/json' })
    const report = await devicesApi.importFile(upload)

    const [, url, body, options] = mockedRequest.mock.calls[0]
    expect(url).toBe('/test-devices/import')
    expect(body).toBeInstanceOf(FormData)
    expect((body as FormData).get('file')).toBeInstanceOf(File)
    expect(options).toMatchObject({ isMultipart: true })
    expect(report).toEqual({
      importedCount: 2,
      updatedCount: 1,
      skippedCount: 1,
      errors: ['第3行: 缺少匹配键 serial_number'],
    })
  })

  it('播放设备 / API 导入端点各自独立', async () => {
    mockedRequest.mockResolvedValue({ imported_count: 0, updated_count: 0, skipped_count: 0, errors: [] })
    await playbackApi.importFile(new File(['a,b'], 'playback.csv'))
    await apisApi.importFile(new File(['{}'], 'apis.json'))
    expect(mockedRequest.mock.calls.map((call) => call[1])).toEqual([
      '/playback-devices/import',
      '/apis/import',
    ])
  })

  it('计数缺失/非法时归一为 0，errors 非数组归一为空', async () => {
    mockedRequest.mockResolvedValueOnce({ imported_count: 'x', errors: 'bad' })
    const report = await devicesApi.importFile(new File(['{}'], 'devices.json'))
    expect(report).toEqual({ importedCount: 0, updatedCount: 0, skippedCount: 0, errors: [] })
  })
})
