/**
 * 用例导入模板下载（INT-1673 P3-2）：
 * GET /testcases/template/download 以 blob 取 xlsx 附件（不走 JSON 信封），
 * 前端按后端 Content-Disposition 同口径生成文件名。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL } from '@/infrastructure/api/client'
import {
  buildTestCaseTemplateFilename,
  downloadTestCaseTemplate,
} from '@/infrastructure/api/testcases-api'

const fetchMock = vi.fn()

/** jsdom 的 Response 构造 Blob body 缺 .stream()，改用最小响应对象（blob 读取路径） */
function xlsxResponse(): Response {
  const blob = new Blob(['xlsx-bytes'], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  return {
    ok: true,
    status: 200,
    headers: new Headers({
      'Content-Type':
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'Content-Disposition':
        'attachment; filename=testcase_template_20261024_024350.xlsx',
    }),
    blob: async () => blob,
  } as unknown as Response
}

describe('用例导入模板下载（INT-1673）', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('GET /testcases/template/download 以 blob 响应类型请求并返回文件流', async () => {
    fetchMock.mockResolvedValue(xlsxResponse())
    const { blob, filename } = await downloadTestCaseTemplate()

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_BASE_URL}/testcases/template/download`)
    expect(init.method).toBe('GET')
    expect(blob).toBeInstanceOf(Blob)
    expect(blob.size).toBeGreaterThan(0)
    expect(filename).toMatch(/^testcase_template_\d{8}_\d{6}\.xlsx$/)
  })

  it('文件名与后端同口径：testcase_template_YYYYmmdd_HHMMSS.xlsx', () => {
    expect(
      buildTestCaseTemplateFilename(new Date(2026, 9, 24, 2, 43, 50))
    ).toBe('testcase_template_20261024_024350.xlsx')
  })

  it('接口失败（404/500）抛错由调用方 toast 透出，不伪装成已下载', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ message: '模板生成失败' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      })
    )
    await expect(downloadTestCaseTemplate()).rejects.toThrow('模板生成失败')
  })
})
