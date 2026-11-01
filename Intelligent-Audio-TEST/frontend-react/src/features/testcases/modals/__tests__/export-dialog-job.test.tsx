/**
 * 导出用例弹窗·异步作业主路径（INT-2315）。
 * 提交作业 → 轮询进度 → 自动下载 → 失败文案 / 429 接管 / 停止轮询 / 产物过期。
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { ExportDialog } from '@/features/testcases/modals/export-dialog'
import { downloadBlob } from '@/lib/download-blob'
import { ApiError } from '@/infrastructure/api/api-error'
import {
  downloadTestCaseExportJob,
  exportTestCases,
  fetchExportJobDownloadUrl,
  getTestCaseExportJob,
  submitTestCaseExportJob,
} from '@/infrastructure/api/testcases-api'

vi.mock('@/infrastructure/api/testcases-api', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('@/infrastructure/api/testcases-api')
  >()
  return {
    ...actual,
    exportTestCases: vi.fn(),
    submitTestCaseExportJob: vi.fn(),
    getTestCaseExportJob: vi.fn(),
    downloadTestCaseExportJob: vi.fn(),
    fetchExportJobDownloadUrl: vi.fn(),
  }
})

vi.mock('@/lib/download-blob', () => ({
  downloadBlob: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

const mockedExport = vi.mocked(exportTestCases)
const mockedDownload = vi.mocked(downloadBlob)
const mockedSubmit = vi.mocked(submitTestCaseExportJob)
const mockedGetJob = vi.mocked(getTestCaseExportJob)
const mockedDownloadJob = vi.mocked(downloadTestCaseExportJob)
const mockedDownloadUrl = vi.mocked(fetchExportJobDownloadUrl)

const renderDialog = (props: Partial<Parameters<typeof ExportDialog>[0]> = {}) =>
  render(
    <ExportDialog
      open
      onOpenChange={vi.fn()}
      selectedCount={0}
      selectedIds={[]}
      {...props}
    />
  )

const JOB_DONE = {
  taskId: 'job-1',
  status: 'done' as const,
  phase: null,
  progress: { total: 2, processed: 2, exported: 2, missing: [] },
  result: {
    format: 'zip' as const,
    filename: 'testcases_export_20261101_101500.zip',
    size: 2048,
    downloadUrl: 'http://127.0.0.1:9000/bucket/export.zip?sig=1',
  },
  error: null,
  total: 2,
  createdAt: null,
  expiresAt: null,
  pollAfterMs: 1000,
}

const JOB_RUNNING = {
  taskId: 'job-1',
  status: 'running' as const,
  phase: 'fetching' as const,
  progress: { total: 2, processed: 1, exported: 1, missing: [] },
  result: null,
  error: null,
  total: 2,
  createdAt: null,
  expiresAt: null,
  pollAfterMs: 200,
}

const EXPORT_BLOB = new Blob(['zip-bytes'], { type: 'application/zip' })

describe('ExportDialog 异步导出作业（INT-2315）', () => {
  beforeEach(() => {
    mockedExport.mockReset()
    mockedDownload.mockReset()
    mockedSubmit.mockReset()
    mockedGetJob.mockReset()
    mockedDownloadJob.mockReset()
    mockedDownloadUrl.mockReset()
    window.sessionStorage.clear()
  })

  it('提交作业 → 轮询看到进度 → done 用直链下载并提示实际导出条数', async () => {
    const user = userEvent.setup()
    mockedSubmit.mockResolvedValue({
      job: { ...JOB_RUNNING, status: 'queued', phase: null, progress: null },
      resumed: false,
    })
    mockedGetJob.mockResolvedValueOnce(JOB_RUNNING).mockResolvedValueOnce(JOB_DONE)
    mockedDownloadUrl.mockResolvedValue(EXPORT_BLOB)
    renderDialog({ resolveFilteredIds: vi.fn().mockResolvedValue(['tc-1', 'tc-2']) })

    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() =>
      expect(mockedSubmit).toHaveBeenCalledWith(['tc-1', 'tc-2'], 'zip', {
        includeReferenceParams: true,
        includeAudios: false,
      })
    )
    // 进度区：阶段文案 + processed / total（契约第 2 条）
    await waitFor(() => expect(screen.getByText('1 / 2')).toBeInTheDocument())
    expect(screen.getByText('正在读取用例')).toBeInTheDocument()

    await waitFor(() =>
      expect(mockedDownload).toHaveBeenCalledWith(
        EXPORT_BLOB,
        JOB_DONE.result.filename,
        'application/zip'
      )
    )
    expect(mockedDownloadUrl).toHaveBeenCalledWith(JOB_DONE.result.downloadUrl)
    expect(mockedDownloadJob).not.toHaveBeenCalled()
    expect(toast.success).toHaveBeenCalledWith(
      '已导出 2 个用例',
      expect.objectContaining({ description: JOB_DONE.result.filename })
    )
  })

  it('download_url 缺省（后端本地降级）→ 走 GET /jobs/{id}/download 取字节', async () => {
    const user = userEvent.setup()
    mockedSubmit.mockResolvedValue({ job: JOB_DONE, resumed: false })
    mockedGetJob.mockResolvedValue({
      ...JOB_DONE,
      result: { ...JOB_DONE.result, downloadUrl: null },
    })
    mockedDownloadJob.mockResolvedValue(EXPORT_BLOB)
    renderDialog({ resolveFilteredIds: vi.fn().mockResolvedValue(['tc-1']) })

    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() => expect(mockedDownloadJob).toHaveBeenCalledWith('job-1'))
    expect(mockedDownloadUrl).not.toHaveBeenCalled()
    expect(mockedDownload).toHaveBeenCalledWith(
      EXPORT_BLOB,
      JOB_DONE.result.filename,
      'application/zip'
    )
  })

  it('failed：toast 显示后端 error.message', async () => {
    const user = userEvent.setup()
    mockedSubmit.mockResolvedValue({ job: JOB_RUNNING, resumed: false })
    mockedGetJob.mockResolvedValue({
      ...JOB_RUNNING,
      status: 'failed',
      phase: null,
      error: { code: 'EXPORT_STORAGE_FAILED', message: '导出文件保存失败，请重试' },
    })
    renderDialog({ resolveFilteredIds: vi.fn().mockResolvedValue(['tc-1']) })

    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('导出文件保存失败，请重试')
    )
    expect(mockedDownload).not.toHaveBeenCalled()
  })

  it.each([
    ['EXPORT_NO_DATA', '没有可导出的用例'],
    ['EXPORT_STORAGE_FAILED', '导出文件保存失败，请重试'],
    ['GATEWAY_RESTARTED', '服务重启导致导出中断，请重新导出'],
  ])('failed：%s 缺 message 时给中文兜底「%s」', async (code, copy) => {
    const user = userEvent.setup()
    mockedSubmit.mockResolvedValue({ job: JOB_RUNNING, resumed: false })
    mockedGetJob.mockResolvedValue({
      ...JOB_RUNNING,
      status: 'failed',
      phase: null,
      error: { code, message: null },
    })
    renderDialog({ resolveFilteredIds: vi.fn().mockResolvedValue(['tc-1']) })

    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(copy))
  })

  it('提交 429：接管已有作业继续轮询，不报错', async () => {
    const user = userEvent.setup()
    // 429 的错误体解析（data.task_id）在 API 层完成并回传 resumed=true，见
    // testcases-api.export-job.test.ts「429 已有导出任务在进行」
    mockedSubmit.mockResolvedValue({
      job: { ...JOB_RUNNING, taskId: 'job-9' },
      resumed: true,
    })
    mockedGetJob.mockResolvedValue({ ...JOB_DONE, taskId: 'job-9' })
    mockedDownloadUrl.mockResolvedValue(EXPORT_BLOB)
    renderDialog({ resolveFilteredIds: vi.fn().mockResolvedValue(['tc-1']) })

    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() =>
      expect(mockedGetJob).toHaveBeenCalledWith('job-9', expect.anything())
    )
    expect(toast.info).toHaveBeenCalledWith('已有导出任务在进行，已接管继续跟踪')
    expect(toast.error).not.toHaveBeenCalled()
    await waitFor(() => expect(mockedDownload).toHaveBeenCalled())
  })

  it('关闭弹窗即停止轮询', async () => {
    const user = userEvent.setup()
    mockedSubmit.mockResolvedValue({ job: JOB_RUNNING, resumed: false })
    mockedGetJob.mockResolvedValue({ ...JOB_RUNNING, pollAfterMs: 300 })
    const props = {
      onOpenChange: vi.fn(),
      resolveFilteredIds: vi.fn().mockResolvedValue(['tc-1']),
    }
    const { rerender } = render(<ExportDialog open {...props} />)

    await user.click(screen.getByRole('button', { name: /开始导出/ }))
    await waitFor(() => expect(mockedGetJob).toHaveBeenCalledTimes(1))

    rerender(<ExportDialog open={false} {...props} />)
    const callsAtClose = mockedGetJob.mock.calls.length
    await new Promise((resolve) => setTimeout(resolve, 450))
    expect(mockedGetJob.mock.calls.length).toBe(callsAtClose)
  })

  it('组件卸载即停止轮询', async () => {
    const user = userEvent.setup()
    mockedSubmit.mockResolvedValue({ job: JOB_RUNNING, resumed: false })
    mockedGetJob.mockResolvedValue({ ...JOB_RUNNING, pollAfterMs: 300 })
    const { unmount } = render(
      <ExportDialog
        open
        onOpenChange={vi.fn()}
        resolveFilteredIds={vi.fn().mockResolvedValue(['tc-1'])}
      />
    )

    await user.click(screen.getByRole('button', { name: /开始导出/ }))
    await waitFor(() => expect(mockedGetJob).toHaveBeenCalledTimes(1))

    unmount()
    const callsAtUnmount = mockedGetJob.mock.calls.length
    await new Promise((resolve) => setTimeout(resolve, 450))
    expect(mockedGetJob.mock.calls.length).toBe(callsAtUnmount)
  })

  it('下载 410（产物已过期）→ 提示重新导出', async () => {
    const user = userEvent.setup()
    mockedSubmit.mockResolvedValue({ job: JOB_DONE, resumed: false })
    mockedGetJob.mockResolvedValue({
      ...JOB_DONE,
      result: { ...JOB_DONE.result, downloadUrl: null },
    })
    mockedDownloadJob.mockRejectedValue(
      new ApiError({ httpStatus: 410, message: '导出文件已过期，请重新导出' })
    )
    renderDialog({ resolveFilteredIds: vi.fn().mockResolvedValue(['tc-1']) })

    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('导出文件已过期，请重新导出')
    )
    expect(mockedDownload).not.toHaveBeenCalled()
  })

  it('重开弹窗：提示「上次导出仍在进行」并可继续跟踪', async () => {
    const user = userEvent.setup()
    mockedSubmit.mockResolvedValue({ job: JOB_RUNNING, resumed: false })
    mockedGetJob.mockResolvedValue({ ...JOB_RUNNING, pollAfterMs: 300 })
    const props = {
      onOpenChange: vi.fn(),
      resolveFilteredIds: vi.fn().mockResolvedValue(['tc-1']),
    }
    const { rerender } = render(<ExportDialog open {...props} />)

    await user.click(screen.getByRole('button', { name: /开始导出/ }))
    await waitFor(() => expect(mockedGetJob).toHaveBeenCalled())

    rerender(<ExportDialog open={false} {...props} />)
    rerender(<ExportDialog open {...props} />)

    expect(screen.getByText(/上次导出仍在进行/)).toBeInTheDocument()

    mockedGetJob.mockReset()
    mockedGetJob.mockResolvedValue(JOB_DONE)
    mockedDownloadUrl.mockResolvedValue(EXPORT_BLOB)
    await user.click(screen.getByRole('button', { name: '继续跟踪' }))

    await waitFor(() =>
      expect(mockedGetJob).toHaveBeenCalledWith('job-1', expect.anything())
    )
    await waitFor(() => expect(mockedDownload).toHaveBeenCalled())
  })
})
