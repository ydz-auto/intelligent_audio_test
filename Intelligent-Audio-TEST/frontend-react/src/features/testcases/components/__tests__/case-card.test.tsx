/**
 * 用例卡测试（V9.7.10 TestCaseCard 等价移植，11_用例域.md §3.5 卡片流）：
 * 名称/算法徽章/标签（分类角标 + 数据驱动色）/时长/轮次/行内操作五钮；
 * 收藏星标实心 amber；回收站态卡 muted + 恢复/彻底删除 + 删除元信息。
 * INT-486 用例不分类型口径：不渲染类型徽章。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { TestCaseListItem } from '@/domain/models/testCase'
import { MOCK_TAGS } from '@/infrastructure/mock/testcases-mock'
import { CaseCard, type CaseCardCallbacks } from '@/features/testcases/components/case-card'

const makeCase = (overrides: Partial<TestCaseListItem> = {}): TestCaseListItem => ({
  id: 'tc-001',
  name: '智能音箱-播放音乐-中文-客厅',
  description: '客厅环境播放中文音乐',
  groupId: 'g1',
  groupName: '智能音箱功能测试',
  type: 'e2e',
  tags: ['音箱', '中文', '客厅'],
  algorithmType: 'asr-v3',
  createdAt: '2026-09-10 10:00',
  updatedAt: '2026-10-15 09:32',
  isFavorite: true,
  deleted: false,
  deletedAt: null,
  deletedByUserId: null,
  totalDuration: 156,
  rounds: 2,
  ...overrides,
})

const noopCallbacks: CaseCardCallbacks = {
  onPreview: vi.fn(),
  onCopy: vi.fn(),
  onFavorite: vi.fn(),
  onEdit: vi.fn(),
  onDelete: vi.fn(),
  onRestore: vi.fn(),
  onPurge: vi.fn(),
}

describe('CaseCard', () => {
  it('渲染名称/算法徽章/时长/轮次与标签分类角标', () => {
    render(
      <CaseCard
        caseItem={makeCase()}
        selected={false}
        tagRegistry={MOCK_TAGS}
        callbacks={noopCallbacks}
        onToggleSelect={vi.fn()}
      />
    )
    expect(screen.getByText('智能音箱-播放音乐-中文-客厅')).toBeInTheDocument()
    expect(screen.getByText('通用识别引擎')).toBeInTheDocument() // asr-v3 算法中文名
    expect(screen.getByText('2 轮')).toBeInTheDocument()
    expect(screen.getByText('2m 36s')).toBeInTheDocument()
    // INT-487 分类角标
    expect(screen.getByText('设备类型')).toBeInTheDocument()
    expect(screen.getByText('语种')).toBeInTheDocument()
  })

  it('行内操作五钮：预览/复制/收藏/编辑/删除', () => {
    render(
      <CaseCard
        caseItem={makeCase()}
        selected={false}
        tagRegistry={MOCK_TAGS}
        callbacks={noopCallbacks}
        onToggleSelect={vi.fn()}
      />
    )
    expect(screen.getByLabelText('预览音频')).toBeInTheDocument()
    expect(screen.getByLabelText('复制用例')).toBeInTheDocument()
    expect(screen.getByLabelText('编辑用例')).toBeInTheDocument()
    expect(screen.getByLabelText('删除用例')).toBeInTheDocument()
    // 收藏态按钮文案为「取消收藏」，星标实心 amber
    const starBtn = screen.getByLabelText('取消收藏')
    expect(starBtn.querySelector('svg')).toHaveClass('fill-amber-400')
  })

  it('点击行内操作触发对应回调', () => {
    const callbacks: CaseCardCallbacks = {
      ...noopCallbacks,
      onPreview: vi.fn(),
      onEdit: vi.fn(),
    }
    render(
      <CaseCard
        caseItem={makeCase()}
        selected={false}
        tagRegistry={MOCK_TAGS}
        callbacks={callbacks}
        onToggleSelect={vi.fn()}
      />
    )
    fireEvent.click(screen.getByLabelText('预览音频'))
    expect(callbacks.onPreview).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByLabelText('编辑用例'))
    expect(callbacks.onEdit).toHaveBeenCalledTimes(1)
  })

  it('回收站态：删除元信息 + 恢复/彻底删除两钮，不渲染普通五钮', () => {
    render(
      <CaseCard
        caseItem={makeCase({
          deleted: true,
          deletedAt: '2026-10-10 14:20',
          deletedByUserId: 1001,
          isFavorite: false,
        })}
        selected={false}
        tagRegistry={MOCK_TAGS}
        callbacks={noopCallbacks}
        onToggleSelect={vi.fn()}
      />
    )
    expect(screen.getByText(/删除时间 2026-10-10 14:20/)).toBeInTheDocument()
    expect(screen.getByText(/删除人 用户#1001/)).toBeInTheDocument()
    expect(screen.getByLabelText('恢复用例')).toBeInTheDocument()
    expect(screen.getByLabelText('彻底删除（不可恢复）')).toBeInTheDocument()
    expect(screen.queryByLabelText('编辑用例')).not.toBeInTheDocument()
    // INT-486：不渲染类型徽章
    expect(screen.queryByText(/E2E测试|API测试/)).not.toBeInTheDocument()
  })
})
