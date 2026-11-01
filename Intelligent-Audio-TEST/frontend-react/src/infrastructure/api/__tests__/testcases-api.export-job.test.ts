/**
 * 异步导出作业 API（INT-2312 后端 3 端点；INT-2315 React 接线）。
 * 校验请求体与同步导出同构、snake_case→camelCase 归一、429 接管、下载 410 语义。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  API_BASE_URL,
  setSessionExpiredHandler,
} from '@/infrastructure/api/client'
import { ApiError } from '@/infrastructure/api/api-error'
import {
  downloadTestCaseExportJob,
  getTestCaseExportJob,
  isExportJobEndpointUnavailable,
  submitTestCaseExportJob,
} from '@/infrastructure/api/testcases-api'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
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
  authTokenStore.clear()
  setSessionExpiredHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
  authTokenStore.clear()
})

describe('submitTestCaseExportJob', () => {
  it('ZIP：请求体与同步导出同构，202 回执映射为 camelCase 作业', async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse({
          task_id: 'job-1',
          status: 'queued',
          total: 580,
          created_at: '2026-11-01T10:00:00+08:00',
          expires_at: '2026-11-02T10:00:00+08:00',
          poll_after_ms: 1500,
        }, 202)
      )
    )

    const { job, resumed } = await submitTestCaseExportJob(['tc-1', 'tc-2'], 'zip', {
      includeReferenceParams: false,
      includeAudios: true,
    })

    expect(String(fetchMock.mock.calls.at(-1)?.[0])).toBe(
      `${API_BASE_URL}/testcases/export/jobs`
    )
    expect(lastBody()).toEqual({
      ids: ['tc-1', 'tc-2'],
      format: 'zip',
      include_reference_params: false,
      include_audios: true,
    })
    expect(job.taskId).toBe('job-1')
    expect(job.status).toBe('queued')
    expect(job.total).toBe(580)
    expect(job.pollAfterMs).toBe(1500)
    expect(resumed).toBe(false)
  })

  it('Excel：不带 ZIP 两个包选项', async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse({ task_id: 'job-2', status: 'queued' }, 202))
    )

    await submitTestCaseExportJob(['tc-1'], 'xlsx')

    expect(lastBody()).toEqual({ ids: ['tc-1'], format: 'xlsx' })
  })

  it('429「已有导出任务在进行」：从错误体 data 接管在办作业，不抛错', async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(
          {
            success: false,
            code: 203,
            message: '已有导出任务在进行',
            data: { task_id: 'job-9', status: 'running' },
          },
          429
        )
      )
    )

    const { job, resumed } = await submitTestCaseExportJob(['tc-1'], 'zip')

    expect(resumed).toBe(true)
    expect(job.taskId).toBe('job-9')
    expect(job.status).toBe('running')
  })

  it('429 队列已满（无 data）→ 仍按错误抛出', async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(
          { success: false, code: 203, message: '导出任务队列已满，请稍后重试' },
          429
        )
      )
    )

    await expect(submitTestCaseExportJob(['tc-1'], 'zip')).rejects.toBeInstanceOf(ApiError)
  })
})

describe('getTestCaseExportJob', () => {
  it('状态/阶段/进度/产物 snake_case → camelCase', async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse({
          task_id: 'job-1',
          status: 'done',
          phase: null,
          progress: {
            total: 3,
            processed: 3,
            exported: 2,
            missing: [{ id: 'tc-3', reason: 'not_found' }],
          },
          result: {
            format: 'zip',
            filename: 'testcases_export_20261101_101500.zip',
            size: 2048,
            path: 'oss://testcase_exports/job-1/x.zip',
            download_url: 'http://127.0.0.1:9000/bucket/x.zip?sig=1',
          },
          error: null,
        })
      )
    )

    const job = await getTestCaseExportJob('job-1')

    expect(String(fetchMock.mock.calls.at(-1)?.[0])).toBe(
      `${API_BASE_URL}/testcases/export/jobs/job-1`
    )
    expect(job.status).toBe('done')
    expect(job.phase).toBeNull()
    expect(job.progress).toEqual({
      total: 3,
      processed: 3,
      exported: 2,
      missing: [{ id: 'tc-3', reason: 'not_found' }],
    })
    expect(job.result?.filename).toBe('testcases_export_20261101_101500.zip')
    expect(job.result?.downloadUrl).toBe(
      'http://127.0.0.1:9000/bucket/x.zip?sig=1'
    )
  })

  it('任务不存在 → 404 ApiError（轮询据此判定任务丢失）', async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse({ success: false, code: 203, message: '导出任务不存在' }, 404)
      )
    )

    await expect(getTestCaseExportJob('nope')).rejects.toMatchObject({ httpStatus: 404 })
  })
})

describe('downloadTestCaseExportJob', () => {
  it('done → 回字节流', async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        new Response('PK', {
          status: 200,
          headers: { 'Content-Type': 'application/zip' },
        })
      )
    )

    const blob = await downloadTestCaseExportJob('job-1')

    expect(String(fetchMock.mock.calls.at(-1)?.[0])).toBe(
      `${API_BASE_URL}/testcases/export/jobs/job-1/download`
    )
    expect(blob.size).toBeGreaterThan(0)
  })

  it('产物过期 → 410 ApiError', async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(
          { success: false, code: 203, message: '导出文件已过期，请重新导出' },
          410
        )
      )
    )

    await expect(downloadTestCaseExportJob('job-1')).rejects.toMatchObject({
      httpStatus: 410,
    })
  })
})

describe('isExportJobEndpointUnavailable', () => {
  it('404 / 405 / 501 判定为端点不可用（回退同步导出）', () => {
    expect(isExportJobEndpointUnavailable(new ApiError({ httpStatus: 404 }))).toBe(true)
    expect(isExportJobEndpointUnavailable(new ApiError({ httpStatus: 405 }))).toBe(true)
    expect(isExportJobEndpointUnavailable(new ApiError({ httpStatus: 501 }))).toBe(true)
  })

  it('400 / 429 / 网络错误不算端点不可用', () => {
    expect(isExportJobEndpointUnavailable(new ApiError({ httpStatus: 400 }))).toBe(false)
    expect(isExportJobEndpointUnavailable(new ApiError({ httpStatus: 429 }))).toBe(false)
    expect(isExportJobEndpointUnavailable(new Error('boom'))).toBe(false)
  })
})
