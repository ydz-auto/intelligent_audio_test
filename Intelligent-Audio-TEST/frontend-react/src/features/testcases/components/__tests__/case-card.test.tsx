/**
 * 用例卡测试（V9.7.10 TestCaseCard 等价移植，11_用例域.md §3.5 卡片流）：
 * 名称/算法徽章/标签（分类角标 + 数据驱动色）/时长/轮次/行内操作五钮；
 * 收藏星标实心 amber；回收站态卡 muted + 恢复/彻底删除 + 删除元信息。
 * INT-486 用例不分类型口径：不渲染类型徽章。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { TestCaseListItem } from '@/domain/models/testCase'
import { MOCK_TAGS } from '@/infrastructure/mock/testcases-mock'
import { Badge } from '@/components/ui/badge'
import { CaseCard, type CaseCardCallbacks } from '@/features/testcases/components/case-card'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

/** 本地演示管理员（permissions '*'）：算法名映射取真实 GET /algorithm/options（INT-1506） */
const ADMIN_USER = {
  id: 'mock-user-001',
  username: 'demo_admin',
  displayName: '演示管理员',
  roleName: '超级管理员',
  permissions: ['*'],
}

/** 算法选项 query 缓存（照 useAlgorithmOptions 的 queryKey / 响应形态） */
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
queryClient.setQueryData(['shell', 'algorithm', 'options'], [
  { value: 'asr-v3', name: '通用识别引擎' },
])

/** CaseCard 读算法名映射（useAlgorithmLabelMap → useQuery），需 QueryClient 上下文 */
const renderCard = (ui: ReactElement) =>
  render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)

/** 算法类型码 → 中文名（真实 GET /algorithm/options value→name 的测试替身，INT-1687） */
const ALGORITHM_LABELS: Record<string, string> = {
  'asr-v3': '通用识别引擎',
  'asr-stream': '流式识别引擎',
}

const makeCase = (overrides: Partial<TestCaseListItem> = {}): TestCaseListItem => ({
  id: 'tc-001',
  name: '智能音箱-播放音乐-中文-客厅',
  description: '客厅环境播放中文音乐',
  groupId: 'g1',
  groupName: '智能音箱功能测试',
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
  beforeEach(() => {
    useAuthStore.setState({ user: ADMIN_USER })
  })

  it('渲染名称/算法徽章/时长/轮次与标签分类角标', () => {
    renderCard(
      <CaseCard
        caseItem={makeCase()}
        selected={false}
        tagRegistry={MOCK_TAGS}
        algorithmLabels={ALGORITHM_LABELS}
        callbacks={noopCallbacks}
        onToggleSelect={vi.fn()}
      />
    )
    expect(screen.getByText('智能音箱-播放音乐-中文-客厅')).toBeInTheDocument()
    expect(screen.getByText('通用识别引擎')).toBeInTheDocument() // asr-v3 → 真实选项中文名
    expect(screen.getByText('2 轮')).toBeInTheDocument()
    expect(screen.getByText('2m 36s')).toBeInTheDocument()
    // INT-487 分类角标
    expect(screen.getByText('设备类型')).toBeInTheDocument()
    expect(screen.getByText('语种')).toBeInTheDocument()
  })

  it('INT-1687：算法名未命中真实选项时不显示类型码（徽章整枚不渲染）', () => {
    const { container } = render(
      <CaseCard
        caseItem={makeCase({ algorithmType: 'voice_llm' })}
        selected={false}
        tagRegistry={MOCK_TAGS}
        algorithmLabels={ALGORITHM_LABELS}
        callbacks={noopCallbacks}
      />
    )
    expect(screen.queryByText('voice_llm')).not.toBeInTheDocument()
    // 其余徽章（时长/轮次）照常渲染
    expect(screen.getByText('2 轮')).toBeInTheDocument()
    expect(container.textContent).not.toContain('voice_llm')
  })

  it('行内操作五钮：预览/复制/收藏/编辑/删除', () => {
    renderCard(
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
    renderCard(
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

  it('INT-595 §3.3.2：无关联音频（audioCount=0）时预览钮置灰，Tooltip 说明，点击不触发回调', () => {
    const callbacks: CaseCardCallbacks = { ...noopCallbacks, onPreview: vi.fn() }
    renderCard(
      <CaseCard
        caseItem={makeCase({ audioCount: 0 })}
        selected={false}
        tagRegistry={MOCK_TAGS}
        callbacks={callbacks}
        onToggleSelect={vi.fn()}
      />
    )
    const previewBtn = screen.getByLabelText('预览音频')
    expect(previewBtn).toBeDisabled()
    expect(previewBtn).toHaveAttribute('aria-disabled', 'true')
    fireEvent.click(previewBtn)
    expect(callbacks.onPreview).not.toHaveBeenCalled()
    // 其余四钮仍可用
    expect(screen.getByLabelText('复制用例')).not.toBeDisabled()
  })

  it('回收站态：删除元信息 + 恢复/彻底删除两钮，不渲染普通五钮', () => {
    renderCard(
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

describe('CaseCard 全站统一插槽（INT-1046：报告/任务域消费）', () => {
  it('报告式：hideMeta + 自定义 actions + expandedContent，不渲染默认五钮', () => {
    renderCard(
      <CaseCard
        caseItem={makeCase({
          algorithmType: null,
          tags: ['音箱'],
          totalDuration: null,
          rounds: undefined,
        })}
        selected={false}
        showCheckbox={false}
        tagRegistry={[]}
        leading={<span aria-label='状态点' />}
        titleExtra={<Badge variant='outline'>未分类</Badge>}
        hideMeta
        actions={
          <button type='button' aria-label='下载日志'>
            下载日志
          </button>
        }
        expandedContent={<div>展开详情区</div>}
      />
    )
    expect(screen.getByLabelText('状态点')).toBeInTheDocument()
    expect(screen.getByText('未分类')).toBeInTheDocument()
    expect(screen.getByLabelText('下载日志')).toBeInTheDocument()
    expect(screen.getByText('展开详情区')).toBeInTheDocument()
    // 报告侧无勾选/无默认五钮/无描述次行
    expect(screen.queryByLabelText(/选择 /)).not.toBeInTheDocument()
    expect(screen.queryByLabelText('预览音频')).not.toBeInTheDocument()
    expect(screen.queryByText(/最后编辑时间/)).not.toBeInTheDocument()
    // 数据缺省不落空徽章（报告无时长/轮次/算法）
    expect(screen.queryByText(/轮/)).not.toBeInTheDocument()
  })

  it('任务式：可点击名称 + meta 次行 + badgeLeading + footer，勾选回调生效', () => {
    const onNameClick = vi.fn()
    const onToggle = vi.fn()
    renderCard(
      <CaseCard
        caseItem={makeCase({ tags: [] })}
        selected={false}
        tagRegistry={[]}
        onToggleSelect={(id, checked) => onToggle(id, checked)}
        onNameClick={onNameClick}
        meta={<span className='meta-line'>远场唤醒</span>}
        badgeLeading={<span className='status-badge'>执行中</span>}
        footer={<button type='button'>人工复核</button>}
      />
    )
    expect(screen.getByText('远场唤醒')).toBeInTheDocument()
    expect(screen.getByText('执行中')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '人工复核' })).toBeInTheDocument()
    // 名称可点击 → 详情回调
    fireEvent.click(screen.getByText('智能音箱-播放音乐-中文-客厅'))
    expect(onNameClick).toHaveBeenCalledTimes(1)
    // 勾选回调走 onToggleSelect（id + checked）
    fireEvent.click(screen.getByLabelText('选择 智能音箱-播放音乐-中文-客厅'))
    expect(onToggle).toHaveBeenCalledWith('tc-001', true)
  })
})
