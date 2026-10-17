/**
 * 音频试听配置弹窗测试（11_用例域.md §5.2）：
 * 播放模式 RadioGroup + 偏移量 →「开始试听」切音频播放器 stage
 * （进度条/播放暂停/停止/播放设备区），「返回试听配置」双向切换。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { TestCaseListItem } from '@/domain/models/testCase'
import { AudioPreviewConfigDialog } from '@/features/testcases/modals/audio-preview-config-dialog'

const CASE_ITEM: TestCaseListItem = {
  id: 'tc-001',
  name: '智能音箱-播放音乐-中文-客厅',
  description: '客厅环境播放中文音乐',
  groupId: 'g1',
  groupName: '智能音箱功能测试',
  type: 'e2e',
  tags: ['音箱'],
  algorithmType: 'asr-v3',
  createdAt: '2026-09-10 10:00',
  updatedAt: '2026-10-15 09:32',
  isFavorite: false,
  deleted: false,
  deletedAt: null,
  deletedByUserId: null,
  totalDuration: 156,
  rounds: 2,
}

const setupUser = () => userEvent.setup()

describe('AudioPreviewConfigDialog', () => {
  it('§5.2 试听配置：浏览器/实验室两种播放模式 + 偏移量输入', () => {
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={CASE_ITEM}
      />
    )
    expect(screen.getByText('音频试听配置')).toBeInTheDocument()
    expect(screen.getByText('浏览器播放')).toBeInTheDocument()
    expect(screen.getByText('实验室播放')).toBeInTheDocument()
    expect(screen.getByLabelText('偏移量秒数')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始试听' })).toBeInTheDocument()
  })

  it('§5.2 开始试听 → 音频播放器（标题/进度/播放暂停/停止/播放设备区）', async () => {
    const user = setupUser()
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={CASE_ITEM}
      />
    )
    await user.click(screen.getByRole('button', { name: '开始试听' }))
    expect(
      screen.getByText(`测试用例预览｜${CASE_ITEM.name} 音频`)
    ).toBeInTheDocument()
    expect(screen.getByLabelText('播放进度')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '播放' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '停止' })).toBeInTheDocument()
    expect(screen.getByText('播放设备（浏览器播放）')).toBeInTheDocument()
    // 播放/暂停切换
    await user.click(screen.getByRole('button', { name: '播放' }))
    expect(screen.getByRole('button', { name: '暂停' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '暂停' }))
    expect(screen.getByRole('button', { name: '播放' })).toBeInTheDocument()
  })

  it('§5.2 播放器「返回试听配置」双向切换回配置态', async () => {
    const user = setupUser()
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={CASE_ITEM}
      />
    )
    await user.click(screen.getByRole('button', { name: '开始试听' }))
    await user.click(screen.getByRole('button', { name: '返回试听配置' }))
    expect(screen.getByText('音频试听配置')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始试听' })).toBeInTheDocument()
  })
})
