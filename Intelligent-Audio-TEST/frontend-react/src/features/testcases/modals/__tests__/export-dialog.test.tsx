/**
 * 导出用例弹窗（11_用例域.md §5.7.2；INT-1642 接线）。
 * 导出范围（当前筛选 / 已选）+ 格式（ZIP 数据包 / Excel / JSON）→ 真实 POST /testcases/export，
 * 文件非空后触发下载；ZIP 支持「包含参考参数文件」开关；失败透出后端 message；空 id 集不发请求。
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { ExportDialog } from '@/features/testcases/modals/export-dialog'
import { downloadBlob } from '@/lib/download-blob'
import { ApiError } from '@/infrastructure/api/api-error'
import { exportTestCases } from '@/infrastructure/api/testcases-api'

vi.mock('@/infrastructure/api/testcases-api', () => ({
  exportTestCases: vi.fn(),
}))

vi.mock('@/lib/download-blob', () => ({
  downloadBlob: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

const mockedExport = vi.mocked(exportTestCases)
const mockedDownload = vi.mocked(downloadBlob)

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

const ZIP_RESULT = {
  blob: new Blob(['zip-bytes'], { type: 'application/zip' }),
  filename: 'testcases_export_20261024_120000.zip',
}

describe('ExportDialog 导出接线（INT-1642）', () => {
  beforeEach(() => {
    mockedExport.mockReset()
    mockedDownload.mockReset()
    mockedExport.mockResolvedValue(ZIP_RESULT)
  })

  it('按当前筛选导出：默认 ZIP 数据包（含参考参数）并下载非空文件', async () => {
    const user = userEvent.setup()
    const resolveFilteredIds = vi.fn().mockResolvedValue(['tc-1', 'tc-2'])
    renderDialog({ resolveFilteredIds })

    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() =>
      expect(mockedExport).toHaveBeenCalledWith(['tc-1', 'tc-2'], 'zip', {
        includeReferenceParams: true,
      })
    )
    expect(mockedDownload).toHaveBeenCalledWith(
      ZIP_RESULT.blob,
      ZIP_RESULT.filename,
      'application/zip'
    )
    expect(toast.success).toHaveBeenCalledWith(
      '已导出 2 个用例',
      expect.objectContaining({ description: ZIP_RESULT.filename })
    )
  })

  it('关闭「包含参考参数文件」后仍以 zip 导出且 includeReferenceParams=false', async () => {
    const user = userEvent.setup()
    renderDialog({ resolveFilteredIds: vi.fn().mockResolvedValue(['tc-1']) })

    await user.click(screen.getByRole('checkbox', { name: /包含参考参数文件/ }))
    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() =>
      expect(mockedExport).toHaveBeenCalledWith(['tc-1'], 'zip', {
        includeReferenceParams: false,
      })
    )
  })

  it('仅导出已选：用勾选 id，且切换后不再重新解析筛选 id', async () => {
    const user = userEvent.setup()
    const resolveFilteredIds = vi.fn().mockResolvedValue([])
    renderDialog({
      selectedCount: 2,
      selectedIds: ['tc-8', 'tc-9'],
      resolveFilteredIds,
    })

    // INT-2154：开窗即按「按当前筛选」统计一次范围预览
    await waitFor(() => expect(resolveFilteredIds).toHaveBeenCalledTimes(1))

    await user.click(screen.getByRole('radio', { name: /仅导出已选 2 个用例/ }))
    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() =>
      expect(mockedExport).toHaveBeenCalledWith(['tc-8', 'tc-9'], 'zip', {
        includeReferenceParams: true,
      })
    )
    // 已选范围不依赖筛选解析
    expect(resolveFilteredIds).toHaveBeenCalledTimes(1)
  })

  it('Excel 格式：format=xlsx', async () => {
    const user = userEvent.setup()
    renderDialog({ resolveFilteredIds: vi.fn().mockResolvedValue(['tc-1']) })

    await user.click(screen.getByRole('combobox'))
    await user.click(screen.getByRole('option', { name: 'Excel' }))
    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() =>
      expect(mockedExport).toHaveBeenCalledWith(['tc-1'], 'xlsx', {
        includeReferenceParams: true,
      })
    )
    // Excel 格式不展示参考参数选项
    expect(
      screen.queryByRole('checkbox', { name: /包含参考参数文件/ })
    ).not.toBeInTheDocument()
  })

  it('JSON 格式：format=json 且前端序列化信封落文件', async () => {
    mockedExport.mockResolvedValue({
      blob: new Blob(['{"test_cases":[]}'], { type: 'application/json' }),
      filename: 'testcases_export_20261024_120000.json',
    })
    const user = userEvent.setup()
    renderDialog({ resolveFilteredIds: vi.fn().mockResolvedValue(['tc-1']) })

    await user.click(screen.getByRole('combobox'))
    await user.click(screen.getByRole('option', { name: 'JSON' }))
    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() =>
      expect(mockedExport).toHaveBeenCalledWith(['tc-1'], 'json', {
        includeReferenceParams: true,
      })
    )
  })

  it('后端失败（空 ids 400 等）→ toast 透出后端 message', async () => {
    const user = userEvent.setup()
    mockedExport.mockRejectedValue(new Error('未指定要导出的用例ID'))
    renderDialog({ resolveFilteredIds: vi.fn().mockResolvedValue(['tc-1']) })

    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        '导出失败：未指定要导出的用例ID'
      )
    )
    expect(mockedDownload).not.toHaveBeenCalled()
  })

  // INT-2191：nginx 反代 60s 超时返回 504 HTML，ApiError.message 为空 → 旧版 toast「导出失败：」。
  it('INT-2191：504（HTML 错误体、无 message）→ 可读的超时提示，不出现空「导出失败：」', async () => {
    const user = userEvent.setup()
    mockedExport.mockRejectedValue(
      new ApiError({ httpStatus: 504, message: '' })
    )
    renderDialog({ resolveFilteredIds: vi.fn().mockResolvedValue(['tc-1']) })

    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        '导出失败：导出超时，请缩小筛选范围后重试'
      )
    )
    expect(mockedDownload).not.toHaveBeenCalled()
  })

  it('INT-2191：无业务码的非 504 失败 → 用 userMessage 的状态码兜底文案', async () => {
    const user = userEvent.setup()
    mockedExport.mockRejectedValue(
      new ApiError({ httpStatus: 502, message: '' })
    )
    renderDialog({ resolveFilteredIds: vi.fn().mockResolvedValue(['tc-1']) })

    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('导出失败：网关错误，请稍后重试')
    )
  })

  it('筛选结果为空：不发导出请求', async () => {
    const user = userEvent.setup()
    renderDialog({ resolveFilteredIds: vi.fn().mockResolvedValue([]) })

    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('当前筛选条件下没有可导出的用例')
    )
    expect(mockedExport).not.toHaveBeenCalled()
  })

  // 代码审计 P3-2：弹窗常驻挂载，范围不随开窗复位会停在「禁用 + 选中」的残留态。
  it('重开弹窗：导出范围复位为「按当前筛选」（不残留上次的「仅导出已选」）', async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    const props = {
      onOpenChange,
      selectedCount: 2,
      selectedIds: ['tc-8', 'tc-9'],
      resolveFilteredIds: vi.fn().mockResolvedValue([]),
    }
    const { rerender } = render(<ExportDialog open {...props} />)

    await user.click(screen.getByRole('radio', { name: /仅导出已选 2 个用例/ }))
    expect(
      screen.getByRole('radio', { name: /仅导出已选 2 个用例/ })
    ).toBeChecked()

    rerender(<ExportDialog open={false} {...props} />)
    rerender(<ExportDialog open {...props} />)

    await waitFor(() =>
      expect(
        screen.getByRole('radio', { name: /按当前筛选条件导出/ })
      ).toBeChecked()
    )
  })

  it('勾选清空后回落「按当前筛选」，不留在禁用选中态', async () => {
    const user = userEvent.setup()
    const resolveFilteredIds = vi.fn().mockResolvedValue(['tc-1'])
    const { rerender } = render(
      <ExportDialog
        open
        onOpenChange={vi.fn()}
        selectedCount={2}
        selectedIds={['tc-8', 'tc-9']}
        resolveFilteredIds={resolveFilteredIds}
      />
    )

    await user.click(screen.getByRole('radio', { name: /仅导出已选 2 个用例/ }))
    rerender(
      <ExportDialog
        open
        onOpenChange={vi.fn()}
        selectedCount={0}
        selectedIds={[]}
        resolveFilteredIds={resolveFilteredIds}
      />
    )

    await waitFor(() =>
      expect(
        screen.getByRole('radio', { name: /按当前筛选条件导出/ })
      ).toBeChecked()
    )
    await user.click(screen.getByRole('button', { name: /开始导出/ }))
    await waitFor(() =>
      expect(mockedExport).toHaveBeenCalledWith(['tc-1'], 'zip', {
        includeReferenceParams: true,
      })
    )
  })

  // INT-2154：导出范围必须可见——否则用户以为导出的是搜到的几条，实际导出全部筛选结果
  it('INT-2154：开窗即展示「将导出 N 条用例」与筛选摘要', async () => {
    renderDialog({
      resolveFilteredIds: vi.fn().mockResolvedValue(['tc-1', 'tc-2', 'tc-3']),
      filterSummary: '搜索：matrix',
    })

    await waitFor(() => expect(screen.getByText('3')).toBeInTheDocument())
    expect(screen.getByText(/将导出/)).toBeInTheDocument()
    expect(screen.getByText(/搜索：matrix/)).toBeInTheDocument()
  })

  it('INT-2154：未勾选用例时提示先去列表勾选', () => {
    renderDialog({ resolveFilteredIds: vi.fn().mockResolvedValue(['tc-1']) })

    expect(screen.getByText(/未选用例：先在列表勾选用例/)).toBeInTheDocument()
    expect(
      screen.getByRole('radio', { name: /仅导出已选 0 个用例/ })
    ).toBeDisabled()
  })

  it('INT-2154：范围统计失败时提示且导出仍按当前筛选执行', async () => {
    const user = userEvent.setup()
    const resolveFilteredIds = vi
      .fn()
      .mockRejectedValueOnce(new Error('ids 接口超时'))
      .mockResolvedValue(['tc-1'])
    renderDialog({ resolveFilteredIds })

    await waitFor(() =>
      expect(screen.getByText(/无法预先统计导出条数/)).toBeInTheDocument()
    )

    await user.click(screen.getByRole('button', { name: /开始导出/ }))
    await waitFor(() =>
      expect(mockedExport).toHaveBeenCalledWith(['tc-1'], 'zip', {
        includeReferenceParams: true,
      })
    )
  })

  it('INT-2154：JSON 实际导出行数与范围不一致时告警', async () => {
    mockedExport.mockResolvedValue({
      blob: new Blob(['{"test_cases":[]}'], { type: 'application/json' }),
      filename: 'testcases_export_20261024_120000.json',
      exportedCount: 1,
    })
    const user = userEvent.setup()
    renderDialog({ resolveFilteredIds: vi.fn().mockResolvedValue(['tc-1', 'tc-2']) })

    await waitFor(() => expect(screen.getByText('2')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() =>
      expect(toast.warning).toHaveBeenCalledWith(
        '导出条数与筛选范围不一致：请求 2 条，实际 1 条',
        expect.objectContaining({ description: 'testcases_export_20261024_120000.json' })
      )
    )
    expect(mockedDownload).toHaveBeenCalled()
  })
})
