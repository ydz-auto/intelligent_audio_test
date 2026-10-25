/**
 * 增量导出 / 增量导入弹窗测试（INT-1765 链路 2）：
 * ① 导出勾选项决定 include 请求体（取消「报告」→ 只导 dimensions）；
 * ② 增量导出只接受单任务（多选时给出原因并禁用）；
 * ③ 选增量包 → 预检展示源任务 / 本侧任务匹配 / 将被覆盖的维度行数与报告数 / warnings；
 * ④ 确认导入 → 调用 import-incremental，回执展示合并维度数、替换报告 id、批次号；
 * ⑤ 失败态（返工 F1/F2/F3）：预检失败有提示、导入失败三态文案按真实数据口径区分。
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/infrastructure/api/api-error'
import { DataExportDialog } from '../data-export-dialog'
import { DataImportDialog } from '../data-import-dialog'

const exportMock = vi.hoisted(() => vi.fn())
const exportIncrementalMock = vi.hoisted(() => vi.fn())
const previewImportMock = vi.hoisted(() => vi.fn())
const previewIncrementalMock = vi.hoisted(() => vi.fn())
const executeImportMock = vi.hoisted(() => vi.fn())
const executeIncrementalMock = vi.hoisted(() => vi.fn())
const progressMock = vi.hoisted(() => vi.fn())
const fetchTaskDetailMock = vi.hoisted(() => vi.fn())
const hasPermissionMock = vi.hoisted(() => vi.fn(() => true))
const navigateMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/data-transfer-api', () => ({
  exportTasks: exportMock,
  exportIncremental: exportIncrementalMock,
  previewImport: previewImportMock,
  previewIncrementalImport: previewIncrementalMock,
  executeImport: executeImportMock,
  executeIncrementalImport: executeIncrementalMock,
  getImportProgress: progressMock,
}))

vi.mock('@/infrastructure/api/tasks-list-api', () => ({
  fetchTaskDetail: fetchTaskDetailMock,
}))

vi.mock('@/application/hooks/use-permissions', () => ({
  usePermissions: () => ({ hasPermission: hasPermissionMock }),
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
}))

const TASK = { id: 12, name: '任务A', status: 'completed' }

function renderExport(tasks = [TASK]) {
  return render(
    <DataExportDialog mode='incremental' open onOpenChange={vi.fn()} tasks={tasks} />
  )
}

describe('DataExportDialog（增量）', () => {
  beforeEach(() => {
    exportIncrementalMock.mockReset()
    exportMock.mockReset()
    exportIncrementalMock.mockResolvedValue(new Blob(['zip']))
    Object.defineProperty(URL, 'createObjectURL', { value: vi.fn(() => 'blob:x'), configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true })
  })

  it('默认勾选两段：请求体 include=[dimensions, reports]', async () => {
    const user = userEvent.setup()
    renderExport()
    await user.click(screen.getByRole('button', { name: '开始导出增量' }))
    await waitFor(() => expect(exportIncrementalMock).toHaveBeenCalled())
    expect(exportIncrementalMock).toHaveBeenCalledWith([12], {
      include: ['dimensions', 'reports'],
    })
  })

  it('取消「报告」后请求体只含 dimensions', async () => {
    const user = userEvent.setup()
    renderExport()
    // base-ui Checkbox Root 为 role=checkbox 的自绘控件：勾选项顺序 = 评估维度、报告
    const boxes = screen.getAllByRole('checkbox')
    await user.click(boxes[1])
    await user.click(screen.getByRole('button', { name: '开始导出增量' }))
    await waitFor(() =>
      expect(exportIncrementalMock).toHaveBeenCalledWith([12], { include: ['dimensions'] })
    )
  })

  it('多选任务：提示只支持单任务并禁用导出', () => {
    renderExport([TASK, { id: 13, name: '任务B', status: 'completed' }])
    expect(screen.getByText(/增量导出只支持单个任务/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始导出增量' })).toBeDisabled()
  })
})

describe('DataImportDialog（增量）', () => {
  beforeEach(() => {
    previewIncrementalMock.mockReset()
    executeIncrementalMock.mockReset()
    progressMock.mockReset()
    fetchTaskDetailMock.mockReset()
    navigateMock.mockReset()
    progressMock.mockResolvedValue(null)
    fetchTaskDetailMock.mockResolvedValue({ id: 12, name: '任务A', status: 'completed' })
    previewIncrementalMock.mockResolvedValue({
      version: '1.1',
      exportedAt: '2026-10-25T12:00:00+08:00',
      source: 'B-host',
      sourceTaskId: 12,
      sourceTaskName: '任务A',
      sourceTaskStatus: 'completed',
      sourceTaskResultCount: 5,
      dimensionCount: 38,
      reportCount: 1,
      warnings: ['任务名与包内不一致'],
    })
  })

  async function uploadPackage() {
    render(<DataImportDialog mode='incremental' open onOpenChange={vi.fn()} />)
    // 弹窗内容经 Portal 挂到 body，不在 render 容器内
    await waitFor(() =>
      expect(document.querySelector('input[type=file]')).not.toBeNull()
    )
    const input = document.querySelector('input[type=file]') as HTMLInputElement
    const file = new File(['zip'], 'incremental_20261025.zip', { type: 'application/zip' })
    await userEvent.upload(input, file)
    return file
  }

  it('预检展示源任务、本侧匹配、将被覆盖的维度/报告数与 warnings', async () => {
    await uploadPackage()
    await waitFor(() => expect(screen.getByText('预检结果')).toBeInTheDocument())
    expect(screen.getAllByText(/#12/).length).toBeGreaterThan(0)
    expect(screen.getByText('任务匹配：本侧存在该任务')).toBeInTheDocument()
    expect(
      screen.getByText(/将被覆盖：维度评分 38 行 · 报告 1 份/)
    ).toBeInTheDocument()
    expect(screen.getByText('任务名与包内不一致')).toBeInTheDocument()
    expect(fetchTaskDetailMock).toHaveBeenCalledWith(12)
  })

  it('确认导入 → 调 import-incremental，回执展示合并维度/替换报告/批次号', async () => {
    executeIncrementalMock.mockResolvedValue({
      taskId: 12,
      mergedDimensions: 38,
      deletedDimensions: 36,
      skippedDimensions: [],
      insertedReports: 1,
      replacedReportId: 9001,
      targetResolvedBy: 'source_map',
      warnings: [],
      batchId: 'b0a1c2d3e4f5',
      rollbackAvailable: true,
    })
    const user = userEvent.setup()
    const file = await uploadPackage()
    await waitFor(() => expect(screen.getByText('预检结果')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '开始导入增量' }))
    await waitFor(() => expect(executeIncrementalMock).toHaveBeenCalledWith(file))
    await waitFor(() =>
      expect(screen.getByText('增量回导完成')).toBeInTheDocument()
    )
    expect(screen.getByText(/合并维度评分 38 行/)).toBeInTheDocument()
    expect(screen.getByText(/#9001/)).toBeInTheDocument()
    expect(screen.getByText(/批次号：b0a1c2d3e4f5/)).toBeInTheDocument()
  })

  /** 选包 → 预检通过 → 点「开始导入增量」 */
  async function runImport() {
    const user = userEvent.setup()
    await uploadPackage()
    await waitFor(() => expect(screen.getByText('预检结果')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '开始导入增量' }))
  }

  // ===== 失败态（返工 F1~F3）=====

  it('预检失败（后端 5xx）→ 展示后端原文 + 可操作引导，不再静默', async () => {
    previewIncrementalMock.mockRejectedValue(
      new ApiError({ httpStatus: 500, message: '增量包解析失败：manifest 缺失' })
    )
    await uploadPackage()
    await waitFor(() => expect(screen.getByText('增量包预检失败')).toBeInTheDocument())
    expect(screen.getByText('增量包解析失败：manifest 缺失')).toBeInTheDocument()
    expect(
      screen.getByText(/请确认这是「导出增量」产出的 1\.1 增量包/)
    ).toBeInTheDocument()
  })

  it('补偿自身失败（500 + 需人工介入）→ 人工介入口径，不说数据未被改动', async () => {
    executeIncrementalMock.mockRejectedValue(
      new ApiError({
        httpStatus: 500,
        message:
          '增量导入失败: boom；补偿回滚部分失败，需人工介入核查（batch_id=abc123def456，登记保留 7 天）: 报告替换回滚失败',
      })
    )
    await runImport()
    await waitFor(() =>
      expect(screen.getByText('增量回导失败：需人工介入')).toBeInTheDocument()
    )
    expect(screen.getByText(/补偿回滚部分失败，需人工介入核查/)).toBeInTheDocument()
    expect(screen.getByText(/批次号：abc123def456/)).toBeInTheDocument()
    expect(screen.queryByText(/原任务数据未被改动/)).toBeNull()
  })

  it('阶段失败（500，补偿成功）→ 已回滚口径', async () => {
    executeIncrementalMock.mockRejectedValue(
      new ApiError({ httpStatus: 500, message: '维度合并失败: 远端超时' })
    )
    await runImport()
    await waitFor(() =>
      expect(screen.getByText('增量回导失败：已回滚至导入前')).toBeInTheDocument()
    )
    expect(
      screen.getByText(/已回滚至导入前状态，原任务数据未被改动/)
    ).toBeInTheDocument()
  })

  it('前置校验 409（指纹不符）→ 未写入口径，不再误报已回滚', async () => {
    executeIncrementalMock.mockRejectedValue(
      new ApiError({
        httpStatus: 409,
        message: '源任务与增量包不匹配，拒绝合并（用例集指纹不符，sourceTaskId=12）',
      })
    )
    await runImport()
    await waitFor(() =>
      expect(screen.getByText('增量回导失败：未写入任何数据')).toBeInTheDocument()
    )
    expect(
      screen.getByText(/前置校验未通过，未写入任何数据（无需回滚）/)
    ).toBeInTheDocument()
    expect(screen.queryByText(/已回滚至导入前状态/)).toBeNull()
  })

  it('回执「查看任务详情」→ 任务详情路由 /tasks/:id', async () => {
    executeIncrementalMock.mockResolvedValue({
      taskId: 12,
      mergedDimensions: 38,
      deletedDimensions: 36,
      skippedDimensions: [],
      insertedReports: 1,
      replacedReportId: 9001,
      targetResolvedBy: 'source_map',
      warnings: [],
      batchId: 'b0a1c2d3e4f5',
      rollbackAvailable: true,
    })
    const user = userEvent.setup()
    await runImport()
    await waitFor(() =>
      expect(screen.getByText('增量回导完成')).toBeInTheDocument()
    )
    await user.click(screen.getByRole('button', { name: '查看任务详情' }))
    expect(navigateMock).toHaveBeenCalledWith({
      to: '/tasks/$tab',
      params: { tab: '12' },
    })
  })
})
