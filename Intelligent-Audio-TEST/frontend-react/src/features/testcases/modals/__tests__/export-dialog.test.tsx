/**
 * 导出用例弹窗（11_用例域.md §5.7.2；INT-1642 接线）。
 * 导出范围（当前筛选 / 已选）+ 格式（JSON / Excel）→ 真实 POST /testcases/export，
 * 文件非空后触发下载；失败透出后端 message；空 id 集不发请求。
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import { ExportDialog } from '@/features/testcases/modals/export-dialog'
import { downloadBlob } from '@/lib/download-blob'
import { exportTestCases } from '@/infrastructure/api/testcases-api'

vi.mock('@/infrastructure/api/testcases-api', () => ({
  exportTestCases: vi.fn(),
}))

vi.mock('@/lib/download-blob', () => ({
  downloadBlob: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
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

const JSON_RESULT = {
  blob: new Blob(['{"test_cases":[]}'], { type: 'application/json' }),
  filename: 'testcases_export_20261024_120000.json',
}

describe('ExportDialog 导出接线（INT-1642）', () => {
  beforeEach(() => {
    mockedExport.mockReset()
    mockedDownload.mockReset()
    mockedExport.mockResolvedValue(JSON_RESULT)
  })

  it('按当前筛选导出：调 POST /testcases/export 并下载非空文件', async () => {
    const user = userEvent.setup()
    const resolveFilteredIds = vi.fn().mockResolvedValue(['tc-1', 'tc-2'])
    renderDialog({ resolveFilteredIds })

    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() =>
      expect(mockedExport).toHaveBeenCalledWith(['tc-1', 'tc-2'], 'json')
    )
    expect(mockedDownload).toHaveBeenCalledWith(
      JSON_RESULT.blob,
      JSON_RESULT.filename,
      'application/json'
    )
    expect(toast.success).toHaveBeenCalledWith(
      '已导出 2 个用例',
      expect.objectContaining({ description: JSON_RESULT.filename })
    )
  })

  it('仅导出已选：用勾选 id 且不再解析筛选 id', async () => {
    const user = userEvent.setup()
    const resolveFilteredIds = vi.fn().mockResolvedValue([])
    renderDialog({
      selectedCount: 2,
      selectedIds: ['tc-8', 'tc-9'],
      resolveFilteredIds,
    })

    await user.click(screen.getByRole('radio', { name: /仅导出已选 2 个用例/ }))
    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() =>
      expect(mockedExport).toHaveBeenCalledWith(['tc-8', 'tc-9'], 'json')
    )
    expect(resolveFilteredIds).not.toHaveBeenCalled()
  })

  it('Excel 格式：format=xlsx', async () => {
    const user = userEvent.setup()
    renderDialog({ resolveFilteredIds: vi.fn().mockResolvedValue(['tc-1']) })

    await user.click(screen.getByRole('combobox'))
    await user.click(screen.getByRole('option', { name: 'Excel' }))
    await user.click(screen.getByRole('button', { name: /开始导出/ }))

    await waitFor(() =>
      expect(mockedExport).toHaveBeenCalledWith(['tc-1'], 'xlsx')
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
      expect(mockedExport).toHaveBeenCalledWith(['tc-1'], 'json')
    )
  })
})
