/**
 * 导入用例弹窗（11_用例域.md §5.7.1）。
 * 选文件 → POST /testcases/import/preview（重复清单）→ 选重复策略 → POST /testcases/import，
 * 回执展示新增/覆盖/跳过/副本计数；失败透出后端 message。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ImportDialog } from '@/features/testcases/modals/import-dialog'
import {
  importTestCases,
  previewTestCasesImport,
} from '@/infrastructure/api/testcases-api'

vi.mock('@/infrastructure/api/testcases-api', () => ({
  previewTestCasesImport: vi.fn(),
  importTestCases: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

const mockedPreview = vi.mocked(previewTestCasesImport)
const mockedImport = vi.mocked(importTestCases)

const PREVIEW = {
  totalRows: 3,
  duplicates: [
    {
      row: 1,
      name: '用例A',
      id: 'c1',
      existingId: 'c1',
      existingName: '用例A',
      matchedBy: 'id' as const,
    },
  ],
  duplicateCount: 1,
  duplicateScanTruncated: false,
  errors: [],
}

const IMPORT_RESULT = {
  importedCount: 2,
  updatedCount: 1,
  skippedCount: 1,
  copiedCount: 0,
  errors: [],
}

const makeFile = () =>
  new File(['zip-bytes'], 'testcases_export.zip', { type: 'application/zip' })

const selectFile = (file: File) => {
  fireEvent.change(screen.getByLabelText('选择导入文件'), {
    target: { files: [file] },
  })
}

const renderDialog = (props: Partial<Parameters<typeof ImportDialog>[0]> = {}) =>
  render(<ImportDialog open onOpenChange={vi.fn()} {...props} />)

describe('ImportDialog 导入接线', () => {
  beforeEach(() => {
    mockedPreview.mockReset()
    mockedImport.mockReset()
    mockedPreview.mockResolvedValue(PREVIEW)
    mockedImport.mockResolvedValue(IMPORT_RESULT)
  })

  it('选文件后预检并展示重复清单；默认跳过策略执行导入', async () => {
    const user = userEvent.setup()
    const onImported = vi.fn()
    renderDialog({ onImported })
    const file = makeFile()

    selectFile(file)

    await waitFor(() => expect(mockedPreview).toHaveBeenCalledWith(file))
    expect(await screen.findByText(/共 3 条用例/)).toBeInTheDocument()
    expect(screen.getByText(/重复 1 条/)).toBeInTheDocument()
    expect(screen.getByText('用例A')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /开始导入/ }))

    await waitFor(() => expect(mockedImport).toHaveBeenCalledWith(file, 'skip'))
    await waitFor(() => expect(screen.getByText(/新增/)).toBeInTheDocument())
    expect(onImported).toHaveBeenCalledTimes(1)
  })

  it('选择「覆盖已有用例」后以 overwrite 执行导入', async () => {
    const user = userEvent.setup()
    renderDialog()

    selectFile(makeFile())
    await screen.findByText(/共 3 条用例/)

    await user.click(screen.getByRole('radio', { name: /覆盖已有用例/ }))
    await user.click(screen.getByRole('button', { name: /开始导入/ }))

    await waitFor(() =>
      expect(mockedImport).toHaveBeenCalledWith(expect.any(File), 'overwrite')
    )
  })

  it('选择「另存副本」后以 copy 执行导入', async () => {
    const user = userEvent.setup()
    renderDialog()

    selectFile(makeFile())
    await screen.findByText(/共 3 条用例/)

    await user.click(screen.getByRole('radio', { name: /另存副本/ }))
    await user.click(screen.getByRole('button', { name: /开始导入/ }))

    await waitFor(() =>
      expect(mockedImport).toHaveBeenCalledWith(expect.any(File), 'copy')
    )
  })

  it('预检失败：展示后端 message 且不允许导入', async () => {
    mockedPreview.mockRejectedValue(new Error('仅支持 JSON, CSV, Excel 或 ZIP 格式的导入'))
    renderDialog()

    selectFile(makeFile())

    expect(await screen.findByText('预检失败')).toBeInTheDocument()
    expect(screen.getByText(/仅支持 JSON, CSV, Excel 或 ZIP/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始导入' })).toBeDisabled()
    expect(mockedImport).not.toHaveBeenCalled()
  })

  it('导入回执展示逐行错误（超过 5 条折叠计数）', async () => {
    mockedImport.mockResolvedValue({
      ...IMPORT_RESULT,
      importedCount: 0,
      updatedCount: 0,
      skippedCount: 0,
      errors: Array.from({ length: 7 }, (_, i) => `第${i + 1}行: 用例名称不能为空`),
    })
    const user = userEvent.setup()
    renderDialog()

    selectFile(makeFile())
    await screen.findByText(/共 3 条用例/)
    await user.click(screen.getByRole('button', { name: /开始导入/ }))

    await waitFor(() =>
      expect(screen.getByText(/部分用例导入失败（7）/)).toBeInTheDocument()
    )
    expect(screen.getByText(/仅展示前 5 条，共 7 条/)).toBeInTheDocument()
  })
})
