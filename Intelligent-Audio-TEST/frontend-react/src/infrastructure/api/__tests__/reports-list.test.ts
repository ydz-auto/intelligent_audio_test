/**
 * reports 域 API 真实端点单测（接线卡 INT-643）：
 * fetchReportList 查询参数透传（snake_case）/ fetchReportCounts tab-counts /
 * fetchReportDetail / toggleReportFavorite POST·DELETE 分叉 / updateReport
 * summary 白名单 camelCase→snake_case / exportReports blob 下载。
 * 统一 mock 全局 fetch（client.ts 依赖），断言 URL 与请求体契约。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  API_BASE_URL,
  setSessionExpiredHandler,
} from '@/infrastructure/api/client'
import {
  exportReports,
  fetchReportCounts,
  fetchReportDetail,
  fetchReportList,
  fetchReportProgress,
  generateTaskReport,
  publishBenchmarkReport,
  secondaryCompareReports,
  toggleReportFavorite,
  updateReport,
} from '@/infrastructure/api/reports-api'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** 依序消费的 fetch mock */
function queueResponses(...responses: Response[]): void {
  fetchMock.mockImplementation(() => {
    const next = responses.shift()
    if (!next) throw new Error('fetch 调用超出 mock 队列')
    return Promise.resolve(next)
  })
}

describe('reports 域 API 真实端点', () => {
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

  it('fetchReportList：GET /reports 且查询参数 snake_case 透传', async () => {
    queueResponses(
      jsonResponse({
        success: true,
        code: 0,
        data: {
          items: [
            {
              id: 1201,
              name: '旗舰音箱全量回归 · 第 3 轮报告',
              type: 'task',
              task_name: '智能音箱旗舰机型全量回归 · 第 3 轮',
              algorithm_type: 'asr_streaming',
              summary: { total_cases: 48, completed_cases: 48, failed_cases: 3, pass_rate: 93.8 },
              status: 'published',
              is_favorite: true,
              created_at: '2026-10-15T09:20:00',
            },
          ],
          total: 1,
          page: 1,
          per_page: 20,
          pages: 1,
        },
      })
    )
    const data = await fetchReportList({
      page: 1,
      per_page: 20,
      report_type: 'comparison',
      status: 'published',
      keyword: '回归',
      sort_by: 'created_at',
      order: 'desc',
      favorite: false,
      deleted: false,
    })
    expect(data.items).toHaveLength(1)
    expect(data.items[0].is_favorite).toBe(true)
    expect(data.total).toBe(1)

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain(`${API_BASE_URL}/reports`)
    const query = new URLSearchParams(url.split('?')[1])
    expect(query.get('report_type')).toBe('comparison')
    expect(query.get('status')).toBe('published')
    expect(query.get('keyword')).toBe('回归')
    expect(query.get('sort_by')).toBe('created_at')
    expect(query.get('order')).toBe('desc')
    expect(query.get('favorite')).toBe('false')
    expect(query.get('deleted')).toBe('false')
    expect(init.method).toBe('GET')
  })

  it('fetchReportCounts：GET /reports/tab-counts 返回四键计数', async () => {
    queueResponses(
      jsonResponse({
        success: true,
        code: 0,
        data: { all: 11, draft: 3, published: 8, comparison: 2 },
      })
    )
    const counts = await fetchReportCounts()
    expect(counts).toEqual({ all: 11, draft: 3, published: 8, comparison: 2 })
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toBe(`${API_BASE_URL}/reports/tab-counts`)
  })

  it('fetchReportDetail：GET /reports/{id} 返回详情', async () => {
    queueResponses(
      jsonResponse({
        success: true,
        code: 0,
        data: {
          id: 1201,
          name: '旗舰音箱全量回归 · 第 3 轮报告',
          type: 'task',
          task_id: 1042,
          task_type: 'e2e',
          task_name: '智能音箱旗舰机型全量回归 · 第 3 轮',
          algorithm_type: 'asr_streaming',
          status: 'published',
          summary: {
            total_cases: 48,
            completed_cases: 48,
            failed_cases: 3,
            resources: ['device_1'],
            resource_headers: [],
            raw_data: [],
            metric_data: [],
            tag_metric_data: [],
            case_categories: [],
            all_case_tags: [],
            all_metrics: [],
            case_type_stats: [],
            device_stats: [],
            api_stats: [],
            devices: [],
            apis: [],
          },
          created_at: '2026-10-15T09:20:00',
        },
      })
    )
    const detail = await fetchReportDetail(1201)
    expect(detail.id).toBe(1201)
    expect(detail.type).toBe('task')
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toBe(`${API_BASE_URL}/reports/1201`)
  })

  it('toggleReportFavorite：favorite=true POST、false DELETE', async () => {
    queueResponses(
      jsonResponse({ success: true, code: 0, data: { entity_type: 'report', entity_id: '1201' } }),
      jsonResponse({ success: true, code: 0, data: { entity_type: 'report', entity_id: '1201' } })
    )
    await toggleReportFavorite(1201, true)
    await toggleReportFavorite(1201, false)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const [favUrl, favInit] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(favUrl).toBe(`${API_BASE_URL}/reports/1201/favorite`)
    expect(favInit.method).toBe('POST')
    const [unfavUrl, unfavInit] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(unfavUrl).toBe(`${API_BASE_URL}/reports/1201/favorite`)
    expect(unfavInit.method).toBe('DELETE')
  })

  it('updateReport：summary 白名单 camelCase → snake_case 请求体', async () => {
    queueResponses(jsonResponse({ success: true, code: 0, data: {} }))
    await updateReport(1201, {
      name: '改名',
      summary: {
        caseCategories: [{ category_id: 'grp-wakeup', category_name: '唤醒场景' }],
        allCaseTags: [{ tag_id: 't-01', tag_name: '远场' }],
        resourceHeaders: [{ key: 'device_1', label: '设备' }],
        analysisConclusion: '结论',
      },
    })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_BASE_URL}/reports/1201`)
    expect(init.method).toBe('PUT')
    const body = JSON.parse(String(init.body)) as Record<string, unknown>
    expect(body.name).toBe('改名')
    const summary = body.summary as Record<string, unknown>
    expect(summary.case_categories).toEqual([{ category_id: 'grp-wakeup', category_name: '唤醒场景' }])
    expect(summary.all_case_tags).toEqual([{ tag_id: 't-01', tag_name: '远场' }])
    expect(summary.resource_headers).toEqual([{ key: 'device_1', label: '设备' }])
    expect(summary.analysisConclusion).toBe('结论')
    expect(summary.caseCategories).toBeUndefined()
    expect(summary.allCaseTags).toBeUndefined()
  })

  it('exportReports：POST /reports/export 以 blob 响应类型请求', async () => {
    const blob = new Blob(['csv-data'], { type: 'text/csv' })
    // jsdom 的 Response 构造 Blob body 缺 .stream()，改用最小 fetch 响应对象（blob 读取路径）
    fetchMock.mockResolvedValue({ ok: true, status: 200, blob: async () => blob })
    const result = await exportReports({ ids: [1201], format: 'csv' })
    expect(result).toBeInstanceOf(Blob)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_BASE_URL}/reports/export`)
    expect(init.method).toBe('POST')
  })

  it('publishBenchmarkReport：POST /benchmarks/reports 空 payload，report_id → reportId', async () => {
    queueResponses(
      jsonResponse({
        success: true,
        code: 0,
        data: {
          id: 5,
          report_id: 1185,
          task_id: null,
          suite: '',
          category: '',
          source: 'platform_test',
          published_at: '2026-10-16T08:00:00',
        },
        message: 'Benchmark 报告发布成功',
      })
    )
    const result = await publishBenchmarkReport()
    expect(result).toEqual({ reportId: 1185 })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_BASE_URL}/benchmarks/reports`)
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{}')
  })

  it('secondaryCompareReports：POST /reports/secondary-compare 异步契约 {reportKey,status}', async () => {
    queueResponses(
      jsonResponse({
        success: true,
        code: 0,
        data: { reportKey: [2, 65], status: 'generating' },
        message: '对比报告生成中，请稍后',
      })
    )
    const result = await secondaryCompareReports({ report_ids: [65, 2], description: '对比' })
    expect(result).toEqual({ reportKey: [2, 65], status: 'generating' })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_BASE_URL}/reports/secondary-compare`)
    expect(init.method).toBe('POST')
    const body = JSON.parse(String(init.body)) as Record<string, unknown>
    expect(body.report_ids).toEqual([65, 2])
    expect(body.description).toBe('对比')
  })

  it('generateTaskReport：POST /reports/generate-task 异步契约 {taskId,status}（无 report_id）', async () => {
    queueResponses(
      jsonResponse({
        success: true,
        code: 0,
        data: { taskId: 1042, status: 'generating' },
        message: '报告生成中，请稍后刷新',
      })
    )
    const result = await generateTaskReport({ task_id: 1042, name: '任务报告' })
    expect(result).toEqual({ taskId: 1042, status: 'generating' })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_BASE_URL}/reports/generate-task`)
    expect(init.method).toBe('POST')
    const body = JSON.parse(String(init.body)) as Record<string, unknown>
    expect(body.task_id).toBe(1042)
    expect(body.name).toBe('任务报告')
  })

  it('fetchReportProgress：GET /reports/{id}/progress 返回进度契约', async () => {
    queueResponses(
      jsonResponse({
        success: true,
        code: 0,
        data: { report_id: 1185, task_id: 1042, status: 'completed', progress: 100, report_status: 'draft' },
      })
    )
    const result = await fetchReportProgress(1185)
    expect(result).toEqual({
      report_id: 1185,
      task_id: 1042,
      status: 'completed',
      progress: 100,
      report_status: 'draft',
    })
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toBe(`${API_BASE_URL}/reports/1185/progress`)
  })
})
