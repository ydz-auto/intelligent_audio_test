/**
 * 日志文件选择 Dialog 组件测试（INT-1067，15_报告域.md §4.10a）。
 * 覆盖：文件列表渲染（文件名 + 大小）、默认全选、逐行取消勾选、
 * 全选/反选工具行、空态「该用例暂无日志文件」、错误态重试、确认回传所选文件。
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ReportCaseItem, ReportLogFile } from '@/domain/models/report'

import { LogFileSelectDialog } from '../log-file-select-dialog'

const fetchCaseLogFilesMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/reports-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/infrastructure/api/reports-api')>()
  return { ...actual, fetchCaseLogFiles: fetchCaseLogFilesMock }
})

const caseItem: ReportCaseItem = {
  id: 'case-1',
  name: '唤醒场景-远场',
  tags: [],
  metrics: {},
  results: [],
  audios: [],
}

const logFiles: ReportLogFile[] = [
  { name: 'case-1/audio.log', size: 1024 },
  { name: 'case-1/exec.log', size: 2048 },
]

function renderDialog(onConfirm: (files: ReportLogFile[]) => void = vi.fn()) {
  return render(
    <LogFileSelectDialog
      open
      onOpenChange={vi.fn()}
      reportId={1201}
      caseItem={caseItem}
      onConfirm={onConfirm}
    />
  )
}

describe('LogFileSelectDialog', () => {
  beforeEach(() => {
    fetchCaseLogFilesMock.mockReset()
  })

  it('打开后拉取文件列表，默认全选，确认回传全部文件', async () => {
    fetchCaseLogFilesMock.mockResolvedValue(logFiles)
    const onConfirm = vi.fn()
    renderDialog(onConfirm)

    expect(await screen.findByText('下载日志 — 唤醒场景-远场')).toBeInTheDocument()
    expect(screen.getByText('case-1/audio.log')).toBeInTheDocument()
    expect(screen.getByText('case-1/exec.log')).toBeInTheDocument()
    // 默认全选：已选 2 个 / 共 2 个 · 总大小 3.0 KB
    expect(screen.getByText(/已选 2 个 \/ 共 2 个 · 总大小/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '下载所选文件' }))
    expect(onConfirm).toHaveBeenCalledWith(logFiles)
  })

  it('逐行取消勾选后，确认只回传未勾选文件，且已选合计联动', async () => {
    fetchCaseLogFilesMock.mockResolvedValue(logFiles)
    const onConfirm = vi.fn()
    renderDialog(onConfirm)

    await screen.findByText('case-1/audio.log')
    // 取消第一行
    await userEvent.click(screen.getByRole('checkbox', { name: '选择日志文件 case-1/audio.log' }))
    expect(screen.getByText(/已选 1 个 \/ 共 2 个 · 总大小 2.0 KB/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '下载所选文件' }))
    expect(onConfirm).toHaveBeenCalledWith([logFiles[1]])
  })

  it('全选/反选工具行：全选 → 反选（清空）→ 下载按钮禁用', async () => {
    fetchCaseLogFilesMock.mockResolvedValue(logFiles)
    renderDialog()

    await screen.findByText('case-1/audio.log')
    // 全选状态（默认）→ 显示「反选」，点击清空
    await userEvent.click(screen.getByRole('button', { name: '反选' }))
    expect(screen.getByText(/已选 0 个 \/ 共 2 个 · 总大小 —/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '下载所选文件' })).toBeDisabled()
  })

  it('空列表显示「该用例暂无日志文件」且下载按钮禁用', async () => {
    fetchCaseLogFilesMock.mockResolvedValue([])
    renderDialog()

    expect(await screen.findByText('该用例暂无日志文件')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '下载所选文件' })).toBeDisabled()
  })

  it('拉取失败显示错误态，「请重试」重新拉取', async () => {
    fetchCaseLogFilesMock.mockRejectedValueOnce(new Error('网络错误'))
    renderDialog()

    expect(await screen.findByText('日志文件加载失败')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '下载所选文件' })).toBeDisabled()

    fetchCaseLogFilesMock.mockResolvedValueOnce(logFiles)
    await userEvent.click(screen.getByRole('button', { name: '请重试' }))
    expect(await screen.findByText('case-1/audio.log')).toBeInTheDocument()
    await waitFor(() => expect(fetchCaseLogFilesMock).toHaveBeenCalledTimes(2))
  })
})
