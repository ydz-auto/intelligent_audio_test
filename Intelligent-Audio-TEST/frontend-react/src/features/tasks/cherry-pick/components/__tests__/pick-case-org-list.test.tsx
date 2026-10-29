/**
 * 用例层组织列表测试（18_挑选合并交互重设计.md §3.8.3 用例层组织，INT-1125 定稿 / INT-1127 实施）。
 * 设备/结果类型视图用例层与用例视图顶层共用：分组视图/标签视图 + 平铺/交叉；
 * INT-1497 §11-7：分支携真实分组/标签/时长 → 按真名聚合；字段缺省才落「未分组」/「未设置标签」兜底桶；
 * 组织控件可视图级单渲（showControls）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import type {
  PickCandidateTree,
  PickTreeBranch,
  PickTreeLeaf,
} from '@/domain/models/cherryPick'
import { buildPickCaseView } from '@/domain/lib/pick-candidate-tree'
import {
  PickCaseOrgControls,
  PickCaseOrgList,
} from '@/features/tasks/cherry-pick/components/pick-case-org-list'

/** count=1 叶父级渲染时探测那一条结果（SingleLeafProbe）→ 需要 QueryClient */
const fetchPageMock = vi.hoisted(() =>
  vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, perPage: 20 })
)
vi.mock('@/infrastructure/api/cherry-pick-api', () => ({
  fetchCherryPickCandidatePage: fetchPageMock,
}))

function withQueryClient(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

const LEAVES: PickTreeLeaf[] = [
  { kind: 'leaf', key: 'leaf:1', resultId: 1, taskName: '任务A', caseName: '用例001', deviceId: 1, deviceName: '设备-01', apiId: null, apiName: null, resultType: 'real-time', executionStatus: 'completed', evaluationStatus: 'completed', createdAt: '2026-10-15T09:00:00', added: false },
  { kind: 'leaf', key: 'leaf:2', resultId: 2, taskName: '任务A', caseName: '用例001', deviceId: 1, deviceName: '设备-01', apiId: null, apiName: null, resultType: 'real-time', executionStatus: 'completed', evaluationStatus: 'completed', createdAt: '2026-10-15T09:01:00', added: false },
]

/** 设备/API 层（buildPickCaseView 树形：用例卡 → 设备/API → result_type/任务 → 叶）。
 *  设备/API 名在这一级分支行渲染，叶行不再重复（INT-2132 核对 a231d8477 叶行去重前提）。 */
function deviceBranch(caseKey: string, leaves: PickTreeLeaf[]): PickTreeBranch {
  return {
    kind: 'branch',
    key: `pcv-device:${caseKey}:device:1`,
    level: 'device',
    name: '设备-01',
    count: leaves.length,
    resultIds: leaves.map((leaf) => leaf.resultId),
    children: leaves,
  }
}

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
    // 叶直挂设备层：避开叶明细分页（candidates）请求，层级语义与 buildPickCaseView 一致
    children: [deviceBranch('c1', LEAVES)],
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
    children: [deviceBranch('c2', [{ ...LEAVES[0], key: 'leaf:3', resultId: 3 }])],
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

/** 真实候选树（两任务同一用例/设备/result_type）：验证 buildPickCaseView 输出的
 *  用例卡 → 设备/API 层在 UI 上确实显示设备名（INT-2132 前提核对，非合成树形） */
const CANDIDATE_TREE: PickCandidateTree = {
  total: 2,
  taskCount: 2,
  meta: {
    tasks: [
      { taskId: 1, taskName: '任务A', taskStatus: 'completed' },
      { taskId: 2, taskName: '任务B', taskStatus: 'completed' },
    ],
    cases: [
      {
        caseId: 'c1',
        caseName: '用例001',
        algorithmType: null,
        tags: [],
        groupId: null,
        groupName: null,
        duration: null,
        rounds: null,
      },
    ],
    devices: [{ deviceId: 1, deviceName: '设备-01' }],
    apis: [],
  },
  tree: [1, 2].map((taskId) => ({
    taskId,
    count: 1,
    cases: [
      {
        caseId: 'c1',
        count: 1,
        devices: [
          {
            deviceId: 1,
            apiId: null,
            count: 1,
            resultTypes: [{ resultType: 'real-time', count: 1, resultIds: [taskId] }],
          },
        ],
      },
    ],
  })),
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

  it('用例卡展开 → 设备/API 层 → 结果行叶：设备名在上级层，叶行不重复', () => {
    setup({ expandSignal: { all: true, tick: 1 } })
    // 设备/API 名的落点 = 上级设备层分支行（buildPickCaseView：用例卡 → 设备/API → …）
    const deviceRow = screen.getByTestId('pick-branch-pcv-device:c1:device:1')
    expect(within(deviceRow).getByText('设备-01')).toBeInTheDocument()
    // a231d8477 叶行去重：树内叶行不再重复设备/API 名与结果类型
    const leafRow = screen.getByTestId('pick-leaf-1')
    expect(within(leafRow).queryByText('设备-01')).not.toBeInTheDocument()
    expect(within(leafRow).queryByText('real-time')).not.toBeInTheDocument()
    expect(screen.getByLabelText('结果 1')).toBeInTheDocument()
  })

  it('真实候选树（buildPickCaseView）：用例卡内设备/API 层显示设备名（叶行的设备名落点）', () => {
    render(
      withQueryClient(
        <PickCaseOrgList
          branches={buildPickCaseView(CANDIDATE_TREE)}
          selectedIds={new Set()}
          onToggleLeaf={vi.fn()}
          onToggleBranch={vi.fn()}
          org='group'
          subView='flat'
          onOrgChange={vi.fn()}
          onSubViewChange={vi.fn()}
          expandSignal={{ all: true, tick: 1 }}
        />
      )
    )
    // 设备名落在设备/API 层分支行（pick-tree.tsx 的行 data-testid = pick-branch-<key>）
    const deviceRow = screen.getByTestId('pick-branch-pcv-device:c1:device:1')
    expect(within(deviceRow).getByText('设备-01')).toBeInTheDocument()
    // 其下任务层分支行可见（叶明细按需分页，未单击展开不挂载）
    expect(screen.getByTestId('pick-branch-pcv-device:c1:device:1-task:1')).toBeInTheDocument()
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
