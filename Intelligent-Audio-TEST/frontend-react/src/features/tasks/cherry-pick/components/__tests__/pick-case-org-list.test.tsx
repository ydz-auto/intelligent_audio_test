/**
 * 用例层组织列表测试（18_挑选合并交互重设计.md §3.8.3 用例层组织，INT-1125 定稿 / INT-1127 实施）。
 * 设备/结果类型视图用例层与用例视图顶层共用：分组视图/标签视图 + 平铺/交叉；
 * INT-1497 §11-7：分支携真实分组/标签/时长 → 按真名聚合；字段缺省才落「未分组」/「未设置标签」兜底桶；
 * 组织控件可视图级单渲（showControls）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { PickTreeBranch, PickTreeLeaf } from '@/domain/models/cherryPick'
import {
  PickCaseOrgControls,
  PickCaseOrgList,
} from '@/features/tasks/cherry-pick/components/pick-case-org-list'

const LEAVES: PickTreeLeaf[] = [
  { kind: 'leaf', key: 'leaf:1', resultId: 1, taskName: '任务A', caseName: '用例001', deviceName: '设备-01', apiName: null, resultType: 'real-time', executionStatus: 'completed', evaluationStatus: 'completed', createdAt: '2026-10-15T09:00:00', added: false },
  { kind: 'leaf', key: 'leaf:2', resultId: 2, taskName: '任务A', caseName: '用例001', deviceName: '设备-01', apiName: null, resultType: 'real-time', executionStatus: 'completed', evaluationStatus: 'completed', createdAt: '2026-10-15T09:01:00', added: false },
]

const CASE_BRANCHES: PickTreeBranch[] = [
  {
    kind: 'branch',
    key: 'dv-case:device:1:real-time:c1',
    level: 'case',
    name: '用例001',
    caseId: 'c1',
    algorithmType: 'asr-v3',
    count: 2,
    resultIds: [1, 2],
    children: LEAVES,
  },
  {
    kind: 'branch',
    key: 'dv-case:device:1:real-time:c2',
    level: 'case',
    name: '用例002',
    caseId: 'c2',
    algorithmType: null,
    count: 1,
    resultIds: [3],
    children: [
      { ...LEAVES[0], key: 'leaf:3', resultId: 3 },
    ],
  },
]

/** §11-7 真名分支：c1/c2 同组「拒识用例组」，c1 双标签、c2 无标签，c3 无分组 */
const REAL_BRANCHES: PickTreeBranch[] = [
  {
    ...CASE_BRANCHES[0],
    key: 'pcase:c1',
    tags: ['拒识', '多轮拒识'],
    groupId: 'g1',
    groupName: '拒识用例组',
    totalDuration: 12.09,
    rounds: 3,
  },
  {
    ...CASE_BRANCHES[1],
    key: 'pcase:c2',
    tags: [],
    groupId: 'g1',
    groupName: '拒识用例组',
    totalDuration: null,
    rounds: null,
  },
  {
    ...CASE_BRANCHES[1],
    key: 'pcase:c3',
    name: '用例003',
    caseId: 'c3',
    tags: ['静默拒识'],
    groupId: null,
    groupName: null,
    totalDuration: 3.5,
    rounds: 2,
    children: [],
  },
]

/** 真实 GET /algorithm/options 派生的 value→name 替身（页面级 useAlgorithmLabels 下传） */
const ALGORITHM_LABELS: Record<string, string> = {
  'asr-v3': '通用识别引擎',
}

function setup(
  props: Partial<Parameters<typeof PickCaseOrgList>[0]> = {}
) {
  const onToggleLeaf = vi.fn()
  const onToggleBranch = vi.fn()
  const onOrgChange = vi.fn()
  const onSubViewChange = vi.fn()
  render(
    <PickCaseOrgList
      branches={CASE_BRANCHES}
      selectedIds={new Set()}
      onToggleLeaf={onToggleLeaf}
      onToggleBranch={onToggleBranch}
      org='group'
      subView='flat'
      onOrgChange={onOrgChange}
      onSubViewChange={onSubViewChange}
      algorithmLabels={ALGORITHM_LABELS}
      {...props}
    />
  )
  return { onToggleLeaf, onToggleBranch, onOrgChange, onSubViewChange }
}

describe('PickCaseOrgList（§3.8.3 用例层组织，INT-1125）', () => {
  it('分组视图 + 平铺：未分组兜底桶 + 用例卡（名称/算法/计数）', () => {
    setup()
    expect(screen.getByText('未分组')).toBeInTheDocument()
    expect(screen.getByText('用例001')).toBeInTheDocument()
    expect(screen.getByText('用例002')).toBeInTheDocument()
    expect(screen.getByText('通用识别引擎')).toBeInTheDocument() // asr-v3 算法中文名
    expect(screen.getAllByText('2 条').length).toBeGreaterThan(0)
  })

  it('标签视图 → 未设置标签兜底桶（分支缺省标签字段）', () => {
    setup({ org: 'tag' })
    expect(screen.getByText('未设置标签')).toBeInTheDocument()
  })

  it('分组视图按真实分组名聚合（§11-7）：真名桶 + 缺省行落「未分组」，卡显真实标签/时长/轮次', () => {
    setup({ branches: REAL_BRANCHES })
    expect(screen.getByText('拒识用例组')).toBeInTheDocument()
    expect(screen.getByText('未分组')).toBeInTheDocument() // 仅 c3（groupId=null）落兜底桶
    expect(screen.getByText('用例001')).toBeInTheDocument()
    expect(screen.getAllByText('拒识').length).toBeGreaterThan(0) // 用例卡标签行真名
    expect(screen.getByText('12s')).toBeInTheDocument() // duration 12.09 → 时长徽章
    expect(screen.getByText('3 轮')).toBeInTheDocument() // rounds 徽章
  })

  it('标签视图按真实标签聚合（§11-7）：多标签用例多次呈现，无标签用例落「未设置标签」', () => {
    setup({ branches: REAL_BRANCHES, org: 'tag' })
    expect(screen.getAllByText('多轮拒识').length).toBeGreaterThan(0) // 标签子组头 + 用例卡标签
    expect(screen.getAllByText('静默拒识').length).toBeGreaterThan(0)
    expect(screen.getByText('未设置标签')).toBeInTheDocument() // c2 tags=[]
    expect(screen.queryByText('未分组')).not.toBeInTheDocument() // 标签视图不出现分组兜底桶
  })

  it('分组视图 + 按标签交叉：未设置标签子组头', () => {
    setup({ org: 'group', subView: 'byTag' })
    expect(screen.getByText('未设置标签')).toBeInTheDocument()
    expect(screen.getByText('用例001')).toBeInTheDocument()
  })

  it('标签视图 + 按用例分组交叉：未分组子组头', () => {
    setup({ org: 'tag', subView: 'byGroup' })
    expect(screen.getByText('未分组')).toBeInTheDocument()
    expect(screen.getByText('用例001')).toBeInTheDocument()
  })

  it('组织控件切换回调 org/subView（org 状态提升阶段 2、三视图共享）', () => {
    const { onOrgChange, onSubViewChange } = setup()
    fireEvent.click(screen.getByText('标签视图'))
    expect(onOrgChange).toHaveBeenCalledWith('tag')
    expect(onSubViewChange).toHaveBeenCalledWith('flat')
    fireEvent.click(screen.getByText('按标签'))
    expect(onSubViewChange).toHaveBeenCalledWith('byTag')
  })

  it('showControls=false 时不渲染组织控件（设备/结果类型视图节点内嵌，视图级已单渲）', () => {
    setup({ showControls: false })
    expect(screen.queryByText('分组视图')).not.toBeInTheDocument()
    expect(screen.queryByText('平铺')).not.toBeInTheDocument()
    expect(screen.getByText('未分组')).toBeInTheDocument()
  })

  it('用例卡展开 → 结果行叶（设备/结果类型视图用例下叶直挂，复用 PickTree 层级行）', () => {
    setup({ expandSignal: { all: true, tick: 1 } })
    // 叶行不再显示来源任务名（INT-1694：任务已是树内节点）
    expect(screen.getAllByText('设备-01').length).toBeGreaterThan(0)
    expect(screen.getByLabelText('结果 1')).toBeInTheDocument()
  })

  it('勾选用例卡触发 onToggleBranch（R6 用例级 = 其下全部结果）', () => {
    const { onToggleBranch } = setup()
    fireEvent.click(screen.getByLabelText('选择 用例001'))
    expect(onToggleBranch).toHaveBeenCalledTimes(1)
    expect(onToggleBranch).toHaveBeenCalledWith(CASE_BRANCHES[0], true)
  })

  it('叶行勾选触发 onToggleLeaf（三视图共享 selectedResultIds）', () => {
    const { onToggleLeaf } = setup({ expandSignal: { all: true, tick: 1 } })
    fireEvent.click(screen.getByLabelText('结果 1'))
    expect(onToggleLeaf).toHaveBeenCalledTimes(1)
  })
})

describe('PickCaseOrgControls（设备/结果类型视图视图级组织控件）', () => {
  it('分组视图/标签视图 Tabs + 平铺/交叉子视图选项随维度切换', () => {
    const onOrgChange = vi.fn()
    const onSubViewChange = vi.fn()
    render(
      <PickCaseOrgControls
        org='group'
        subView='flat'
        onOrgChange={onOrgChange}
        onSubViewChange={onSubViewChange}
      />
    )
    expect(screen.getByText('分组视图')).toBeInTheDocument()
    expect(screen.getByText('标签视图')).toBeInTheDocument()
    expect(screen.getByText('平铺')).toBeInTheDocument()
    expect(screen.getByText('按标签')).toBeInTheDocument()
    fireEvent.click(screen.getByText('标签视图'))
    expect(onOrgChange).toHaveBeenCalledWith('tag')
    expect(onSubViewChange).toHaveBeenCalledWith('flat')
  })
})
