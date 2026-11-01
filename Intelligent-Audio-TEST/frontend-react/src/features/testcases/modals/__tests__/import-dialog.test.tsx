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
  audioPackageCount: 0,
}

const IMPORT_RESULT = {
  importedCount: 2,
  updatedCount: 1,
  skippedCount: 1,
  copiedCount: 0,
  errors: [],
  audioRegisteredCount: 0,
  audioReusedCount: 0,
  audioFailed: [],
  audioOrphanedIds: [],
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

  it('预检行级错误：列出错误行并提示仍可导入其余行（INT-2155）', async () => {
    mockedPreview.mockResolvedValue({
      ...PREVIEW,
      totalRows: 2,
      duplicates: [],
      duplicateCount: 0,
      errors: ['第2行: 用例名称不能为空'],
    })
    const user = userEvent.setup()
    renderDialog()
    const file = makeFile()

    selectFile(file)

    expect(await screen.findByText(/错误 1 行/)).toBeInTheDocument()
    expect(screen.getByText('第2行: 用例名称不能为空')).toBeInTheDocument()
    expect(screen.getByText(/其余 1 条可正常导入/)).toBeInTheDocument()
    // 错误行与重复处理策略分开呈现：策略区仍在
    expect(screen.getByText('重复用例处理')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '仍导入其余 1 条' }))
    await waitFor(() => expect(mockedImport).toHaveBeenCalledWith(file, 'skip'))
  })

  it('预检全部行报错：不允许导入', async () => {
    mockedPreview.mockResolvedValue({
      ...PREVIEW,
      totalRows: 1,
      duplicates: [],
      duplicateCount: 0,
      errors: ['第1行: 用例名称不能为空'],
    })
    renderDialog()

    selectFile(makeFile())

    expect(await screen.findByText(/没有可导入的行/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始导入' })).toBeDisabled()
  })
})

describe('ImportDialog 音频回导回执（INT-2215）', () => {
  beforeEach(() => {
    mockedPreview.mockReset()
    mockedImport.mockReset()
    mockedPreview.mockResolvedValue(PREVIEW)
    mockedImport.mockResolvedValue(IMPORT_RESULT)
  })

  /** 选文件 → 预检 → 执行导入，等回执阶段的「完成」按钮出现 */
  const runImport = async () => {
    const user = userEvent.setup()
    renderDialog()
    selectFile(makeFile())
    await screen.findByText(/共 3 条用例/)
    await user.click(screen.getByRole('button', { name: '开始导入' }))
    await screen.findByRole('button', { name: '完成' })
  }

  it('回执带音频计数时展示「登记 / 复用 / 失败」汇总', async () => {
    mockedImport.mockResolvedValue({
      ...IMPORT_RESULT,
      audioRegisteredCount: 4,
      audioReusedCount: 2,
      audioFailed: [{ sourceId: '101', reason: 'md5_mismatch' }],
    })

    await runImport()

    const summary = await screen.findByText(/音频：/)
    expect(summary).toHaveTextContent(
      /音频：登记 4 \/ 复用 2 \/ 失败 1/
    )
  })

  it('音频失败逐条展示，且不并入行级 errors 计数', async () => {
    mockedImport.mockResolvedValue({
      ...IMPORT_RESULT,
      audioRegisteredCount: 0,
      audioReusedCount: 0,
      errors: [],
      audioFailed: [
        { sourceId: '101', reason: 'md5_mismatch' },
        { sourceId: '102', reason: 'invalid_audio_content' },
      ],
    })

    await runImport()

    expect(
      await screen.findByText('音频 101 回导失败：md5_mismatch')
    ).toBeInTheDocument()
    expect(
      screen.getByText('音频 102 回导失败：invalid_audio_content')
    ).toBeInTheDocument()
    // 行级 errors 为空 → 不出现「部分用例导入失败」，音频失败不重复计数
    expect(screen.queryByText(/部分用例导入失败/)).not.toBeInTheDocument()
  })

  it('孤儿音频非空时提示未被用例引用的音频 id', async () => {
    mockedImport.mockResolvedValue({
      ...IMPORT_RESULT,
      audioRegisteredCount: 3,
      audioOrphanedIds: [201, 202],
    })

    await runImport()

    expect(
      await screen.findByText(/未被用例引用的已登记音频：201、202/)
    ).toBeInTheDocument()
  })

  it('非 ZIP / 老后端四字段缺省：不出现音频区', async () => {
    mockedImport.mockResolvedValue({ ...IMPORT_RESULT })

    await runImport()

    expect(await screen.findByText(/新增/)).toBeInTheDocument()
    expect(screen.queryByText(/音频：/)).not.toBeInTheDocument()
    expect(screen.queryByText(/未被用例引用的已登记音频/)).not.toBeInTheDocument()
  })

  it('预览 audioPackageCount > 0 时展示「包内音频 N 条可回导」', async () => {
    mockedPreview.mockResolvedValue({ ...PREVIEW, audioPackageCount: 3 })

    renderDialog()
    selectFile(makeFile())

    expect(
      await screen.findByText(/包内音频 3 条可回导/)
    ).toBeInTheDocument()
  })

  it('预览 audioPackageCount 为 0 时不展示音频提示', async () => {
    renderDialog()
    selectFile(makeFile())

    expect(await screen.findByText(/共 3 条用例/)).toBeInTheDocument()
    expect(screen.queryByText(/条可回导/)).not.toBeInTheDocument()
  })
})
