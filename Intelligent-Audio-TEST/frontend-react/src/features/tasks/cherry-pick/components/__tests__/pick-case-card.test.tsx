/**
 * 挑选/购物车 compact 用例卡测试（18_挑选合并交互重设计.md §3.8.3/§4.2，INT-1047）。
 * 用例卡复用断言：PickCaseCard = CaseCard compact 变体（名称/CaseIdBadge/算法徽章/计数
 * + 三态勾选 + 展开三角；hideMeta 无默认行内操作钮）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { PickCaseCard } from '@/features/tasks/cherry-pick/components/pick-case-card'

/** 真实 GET /algorithm/options 派生的 value→name 替身（页面级 useAlgorithmLabels 下传） */
const ALGORITHM_LABELS: Record<string, string> = {
  'asr-v3': '通用识别引擎',
  voice_llm: '小艺语音大模型',
}

function renderCard(overrides: Partial<Parameters<typeof PickCaseCard>[0]> = {}) {
  const onToggle = vi.fn()
  const onToggleOpen = vi.fn()
  render(
    <PickCaseCard
      name='用例001'
      caseId='c1'
      algorithmType='asr-v3'
      algorithmLabels={ALGORITHM_LABELS}
      count={3}
      state='checked'
      onToggle={onToggle}
      open={false}
      onToggleOpen={onToggleOpen}
      {...overrides}
    />
  )
  return { onToggle, onToggleOpen }
}

describe('PickCaseCard（§3.8.3 用例节点 = CaseCard compact）', () => {
  it('渲染名称/CaseIdBadge/算法徽章/计数 + 勾选（R6 用例级）', () => {
    renderCard()
    expect(screen.getByText('用例001')).toBeInTheDocument()
    expect(screen.getByText('c1')).toBeInTheDocument() // CaseIdBadge 点击复制
    expect(screen.getByText('通用识别引擎')).toBeInTheDocument() // asr-v3 算法中文名
    expect(screen.getByText('3 条')).toBeInTheDocument()
    expect(screen.getByLabelText('选择 用例001')).toBeChecked()
  })

  it('算法徽章取真实选项中文名（ENUM 类型码 voice_llm → 小艺语音大模型）', () => {
    renderCard({ algorithmType: 'voice_llm' })
    expect(screen.getByText('小艺语音大模型')).toBeInTheDocument()
    expect(screen.queryByText('voice_llm')).not.toBeInTheDocument()
  })

  it('算法不在选项中（已下线 / 未加载）不渲染类型码', () => {
    renderCard({ algorithmType: 'unknown_algo' })
    expect(screen.queryByText('unknown_algo')).not.toBeInTheDocument()
  })

  it('勾选切换触发 onToggle（state 驱动，点击后翻转）', () => {
    const { onToggle } = renderCard({ state: 'unchecked' })
    const checkbox = screen.getByLabelText('选择 用例001')
    expect(checkbox).not.toBeChecked()
    fireEvent.click(checkbox)
    expect(onToggle).toHaveBeenCalledWith(true)
  })

  it('部分选中态：勾选框标记 indeterminate（R3 三态，父级部分选中）', () => {
    renderCard({ state: 'indeterminate' })
    const checkbox = screen.getByLabelText('选择 用例001')
    // base-ui Checkbox：indeterminate 以 aria-checked="mixed" 标记
    expect(checkbox).toHaveAttribute('aria-checked', 'mixed')
  })

  it('展开三角：收起 → 点击展开显示子树（设备/结果类型行）', () => {
    const { onToggleOpen } = renderCard()
    fireEvent.click(screen.getByLabelText('展开'))
    expect(onToggleOpen).toHaveBeenCalledTimes(1)
    render(
      <PickCaseCard
        name='用例001'
        count={3}
        state='unchecked'
        onToggle={() => {}}
        open
        onToggleOpen={() => {}}
      >
        <div aria-label='设备子树'>设备-01</div>
      </PickCaseCard>
    )
    expect(screen.getByLabelText('收起')).toBeInTheDocument()
    expect(screen.getByLabelText('设备子树')).toBeInTheDocument()
  })

  it('hideMeta：不渲染描述/最后编辑时间次行，无默认行内五钮（CaseCard 插槽收敛）', () => {
    renderCard()
    expect(screen.queryByText(/最后编辑时间/)).not.toBeInTheDocument()
    expect(screen.queryByText(/预览音频/)).not.toBeInTheDocument()
    expect(screen.queryByText(/编辑用例/)).not.toBeInTheDocument()
  })

  it('自定义 actions 插槽（购物车「移除该组」）渲染于卡片右区', () => {
    renderCard({
      actions: (
        <button type='button' aria-label='移除该组'>
          移除该组
        </button>
      ),
    })
    expect(screen.getByLabelText('移除该组')).toBeInTheDocument()
  })
})
