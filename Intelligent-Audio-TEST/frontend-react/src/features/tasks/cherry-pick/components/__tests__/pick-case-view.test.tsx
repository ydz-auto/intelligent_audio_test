/**
 * 挑选用例视图测试（18_挑选合并交互重设计.md §3.8.3，INT-1047/INT-1127）。
 * 用例节点 = CaseCard compact；组织维度照用例管理页（分组/标签 + 平铺/交叉），
 * 候选未返分组/标签字段 → 全落「未分组」/「未设置标签」兜底桶；
 * 用例卡展开 → 设备/result_type → 结果行叶（复用 PickTree 层级行，叶携来源任务名）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { PickTreeBranch, PickTreeLeaf } from '@/domain/models/cherryPick'
import { PickCaseView } from '@/features/tasks/cherry-pick/components/pick-case-view'

const LEAVES: PickTreeLeaf[] = [
  { kind: 'leaf', key: 'leaf:1', resultId: 1, taskName: '任务A', caseName: '用例001', deviceName: '设备-01', apiName: null, resultType: 'real-time', executionStatus: 'completed', evaluationStatus: 'completed', createdAt: '2026-10-15T09:00:00', added: false },
  { kind: 'leaf', key: 'leaf:2', resultId: 2, taskName: '任务A', caseName: '用例001', deviceName: '设备-01', apiName: null, resultType: 'real-time', executionStatus: 'completed', evaluationStatus: 'completed', createdAt: '2026-10-15T09:01:00', added: false },
]

const BRANCHES: PickTreeBranch[] = [
  {
    kind: 'branch',
    key: 'pcase:c1',
    level: 'case',
    name: '用例001',
    caseId: 'c1',
    algorithmType: 'asr-v3',
    count: 2,
    resultIds: [1, 2],
    children: [
      {
        kind: 'branch',
        key: 'pcase-device:c1:device:1',
        level: 'device',
        name: '设备-01',
        count: 2,
        resultIds: [1, 2],
        children: [
          {
            kind: 'branch',
            key: 'pcase-resultType:c1:device:1:real-time',
            level: 'resultType',
            name: 'real-time',
            count: 2,
            resultIds: [1, 2],
            children: LEAVES,
          },
        ],
      },
    ],
  },
]

function setup(overrides: Partial<Parameters<typeof PickCaseView>[0]> = {}) {
  const onToggleLeaf = vi.fn()
  const onToggleBranch = vi.fn()
  const onOrgChange = vi.fn()
  const onSubViewChange = vi.fn()
  render(
    <PickCaseView
      branches={BRANCHES}
      selectedIds={new Set()}
      onToggleLeaf={onToggleLeaf}
      onToggleBranch={onToggleBranch}
      org='group'
      subView='flat'
      onOrgChange={onOrgChange}
      onSubViewChange={onSubViewChange}
      {...overrides}
    />
  )
  return { onToggleLeaf, onToggleBranch, onOrgChange, onSubViewChange }
}

describe('PickCaseView（§3.8.3 用例视图组织维度）', () => {
  it('分组视图 + 平铺：未分组兜底桶 + 用例卡（名称/算法/计数）', () => {
    setup()
    expect(screen.getByText('未分组')).toBeInTheDocument()
    expect(screen.getByText('用例001')).toBeInTheDocument()
    expect(screen.getByText('通用识别引擎')).toBeInTheDocument() // asr-v3 算法中文名
    expect(screen.getByText('2 条')).toBeInTheDocument()
  })

  it('标签视图 → 未设置标签兜底桶（候选无标签字段，§11-7 落地前；org 受控于 usePickOrg）', () => {
    setup({ org: 'tag' })
    expect(screen.getByText('未设置标签')).toBeInTheDocument()
  })

  it('用例卡展开 → 设备/result_type 子树 + 叶携来源任务名（复用 PickTree 层级行）', () => {
    setup({ expandSignal: { all: true, tick: 1 } })
    expect(screen.getAllByText('设备-01').length).toBeGreaterThan(0) // 分支行 + 叶行设备名
    expect(screen.getAllByText('real-time').length).toBeGreaterThan(0) // result_type 分支 + 叶徽章
    expect(screen.getAllByText('任务A').length).toBeGreaterThan(0) // 叶行来源任务名消歧
  })

  it('勾选用例卡触发 onToggleBranch（R6 用例级 = 其下全部结果）', () => {
    const { onToggleBranch } = setup()
    fireEvent.click(screen.getByLabelText('选择 用例001'))
    expect(onToggleBranch).toHaveBeenCalledTimes(1)
    expect(onToggleBranch).toHaveBeenCalledWith(BRANCHES[0], true)
  })

  it('叶行勾选触发 onToggleLeaf（三视图共享 selectedResultIds）', () => {
    const { onToggleLeaf } = setup({ expandSignal: { all: true, tick: 1 } })
    fireEvent.click(screen.getByLabelText('结果 1'))
    expect(onToggleLeaf).toHaveBeenCalledTimes(1)
  })
})
