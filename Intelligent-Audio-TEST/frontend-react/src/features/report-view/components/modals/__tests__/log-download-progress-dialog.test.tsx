/**
 * 日志下载进度 Dialog 组件测试（INT-1067，15_报告域.md §4.10b）。
 * 受控展示：正在下载日志（{n} 个文件）+ 进度% + 已下载·所选总量 + 速度；
 * done 态显示「下载完成」+「完成」钮。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { LogDownloadProgressDialog } from '../log-download-progress-dialog'

function renderProgress(props: Partial<Parameters<typeof LogDownloadProgressDialog>[0]> = {}) {
  const onComplete = vi.fn()
  render(
    <LogDownloadProgressDialog
      open
      onOpenChange={vi.fn()}
      caseName='唤醒场景-远场'
      fileCount={2}
      downloaded={1024}
      totalSize={3072}
      speed={512000}
      done={false}
      onComplete={onComplete}
      {...props}
    />
  )
  return { onComplete }
}

describe('LogDownloadProgressDialog', () => {
  it('下载中：显示文件数 / 进度% / 已下载·总量 / 速度', () => {
    renderProgress()
    expect(screen.getByText(/正在下载「唤醒场景-远场」的执行日志（2 个文件）/)).toBeInTheDocument()
    expect(screen.getByText('33%')).toBeInTheDocument()
    expect(screen.getByText('1.0 KB / 3.0 KB')).toBeInTheDocument()
    expect(screen.getByText('500.0 KB/s')).toBeInTheDocument()
    expect(screen.getByText('正在下载日志')).toBeInTheDocument()
  })

  it('完成态：显示「下载完成」，点击「完成」触发 onComplete', async () => {
    const { onComplete } = renderProgress({ done: true, downloaded: 3072 })
    expect(screen.getByText('下载完成')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '完成' }))
    expect(onComplete).toHaveBeenCalled()
  })
})
