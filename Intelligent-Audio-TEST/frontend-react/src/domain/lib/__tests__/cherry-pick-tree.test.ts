/**
 * 挑选树联动规则单测（18_挑选合并功能交互重设计.md §3.2 R1-R10，INT-600）。
 * 纯函数测试：树构建 + 三态联动 + 批量选择 + 已选统计 + 购物车树/移除矩阵。
 */
import { describe, expect, it } from 'vitest'

import type {
  CartTreeBranch,
  CartTreeItem,
  CartTreeLeaf,
  CherryPickCandidate,
  PickTreeBranch,
  PickTreeItem,
  PickTreeLeaf,
} from '@/domain/models/cherryPick'
import {
  buildCartCaseView,
  buildCartDeviceView,
  buildCartResultTypeView,
  buildCartTaskView,
  buildPickCaseView,
  buildPickDeviceView,
  buildPickResultTypeView,
  buildPickTree,
  clearSelection,
  collectEntryIds,

  collectVisibleResultIds,
  computeSelectionStats,
  getBranchSelectionState,
  getCartBranchSelectionState,
  invertVisibleSelection,
  selectAllVisible,
  toggleBranchSelection,
  toggleCartBranchSelection,
  toggleCartLeafSelection,
  toggleLeafSelection,
} from '@/domain/lib/cherry-pick-tree'

/** 候选行样例：任务1042 → 用例c1 → 设备d1 → real-time/final；用例c2 → 设备d1 */
const CANDIDATES: CherryPickCandidate[] = [
  // 任务 A 用例 c1 设备 d1 real-time（2 行）
  { resultId: 1, taskId: 1042, taskName: '任务A', caseId: 'c1', caseName: '用例001', tags: ['拒识', '多轮拒识'], groupId: 'g1', groupName: '拒识', totalDuration: 12.09, rounds: 3, deviceId: 1, deviceName: '设备-01', apiId: null, apiName: null, resultType: 'real-time', algorithmType: 'CRM', executionStatus: 'completed', evaluationStatus: 'completed', evaluated: true, createdAt: '2026-10-15T09:00:00' },
  { resultId: 2, taskId: 1042, taskName: '任务A', caseId: 'c1', caseName: '用例001', tags: ['拒识', '多轮拒识'], groupId: 'g1', groupName: '拒识', totalDuration: 12.09, rounds: 3, deviceId: 1, deviceName: '设备-01', apiId: null, apiName: null, resultType: 'real-time', algorithmType: 'CRM', executionStatus: 'completed', evaluationStatus: 'completed', evaluated: true, createdAt: '2026-10-15T09:01:00' },
  // 任务 A 用例 c1 设备 d1 final（1 行）
  { resultId: 3, taskId: 1042, taskName: '任务A', caseId: 'c1', caseName: '用例001', tags: ['拒识', '多轮拒识'], groupId: 'g1', groupName: '拒识', totalDuration: 12.09, rounds: 3, deviceId: 1, deviceName: '设备-01', apiId: null, apiName: null, resultType: 'final', algorithmType: 'CRM', executionStatus: 'completed', evaluationStatus: 'evaluating', evaluated: false, createdAt: '2026-10-15T09:02:00' },
  // 任务 A 用例 c2 设备 d1 real-time（2 行）
  { resultId: 4, taskId: 1042, taskName: '任务A', caseId: 'c2', caseName: '用例002', tags: ['静默拒识'], groupId: 'g1', groupName: '拒识', totalDuration: 3.79, rounds: 2, deviceId: 1, deviceName: '设备-01', apiId: null, apiName: null, resultType: 'real-time', algorithmType: 'CRM', executionStatus: 'completed', evaluationStatus: 'completed', evaluated: true, createdAt: '2026-10-15T09:03:00' },
  { resultId: 5, taskId: 1042, taskName: '任务A', caseId: 'c2', caseName: '用例002', tags: ['静默拒识'], groupId: 'g1', groupName: '拒识', totalDuration: 3.79, rounds: 2, deviceId: 1, deviceName: '设备-01', apiId: null, apiName: null, resultType: 'real-time', algorithmType: 'CRM', executionStatus: 'completed', evaluationStatus: 'completed', evaluated: true, createdAt: '2026-10-15T09:04:00' },
  // 任务 B 用例 c3 设备 d2 real-time（1 行）——跨任务独立根（R8）；分组/标签/时长缺省（降级场景）
  { resultId: 6, taskId: 1041, taskName: '任务B', caseId: 'c3', caseName: '用例003', tags: [], groupId: null, groupName: null, totalDuration: null, rounds: null, deviceId: 2, deviceName: '设备-02', apiId: null, apiName: null, resultType: 'real-time', algorithmType: 'CRM', executionStatus: 'failed', evaluationStatus: 'failed', evaluated: true, createdAt: '2026-10-15T10:00:00' },
]

/** 建树辅助：返回任务级节点（按 key 查找） */
function findTask(items: PickTreeItem[], taskId: number): PickTreeBranch {
  const task = items.find(
    (t): t is PickTreeBranch =>
      t.kind === 'branch' && t.level === 'task' && t.key === `task:${taskId}`
  )
  if (!task) throw new Error(`task ${taskId} 未找到`)
  return task
}

function findCase(task: PickTreeBranch, caseId: string): PickTreeBranch {
  const c = task.children.find(
    (n): n is PickTreeBranch =>
      n.kind === 'branch' && n.level === 'case' && n.key.endsWith(`:${caseId}`)
  )
  if (!c) throw new Error(`case ${caseId} 未找到`)
  return c
}

function findDevice(caseNode: PickTreeBranch, deviceName: string): PickTreeBranch {
  const d = caseNode.children.find(
    (n): n is PickTreeBranch =>
      n.kind === 'branch' && n.level === 'device' && n.name === deviceName
  )
  if (!d) throw new Error(`device ${deviceName} 未找到`)
  return d
}

function findResultType(device: PickTreeBranch, rt: string): PickTreeBranch {
  const node = device.children.find(
    (n): n is PickTreeBranch =>
      n.kind === 'branch' && n.level === 'resultType' && n.name === rt
  )
  if (!node) throw new Error(`resultType ${rt} 未找到`)
  return node
}

describe('buildPickTree', () => {
  it('四级分组 + 结果行叶，计数正确', () => {
    const tree = buildPickTree(CANDIDATES)
    expect(tree).toHaveLength(2) // 任务 A/B
    const taskA = findTask(tree, 1042)
    expect(taskA.name).toBe('任务A')
    expect(taskA.count).toBe(5)
    expect(taskA.resultIds).toEqual([1, 2, 3, 4, 5])

    const c1 = findCase(taskA, 'c1')
    expect(c1.count).toBe(3)
    const d1 = findDevice(c1, '设备-01')
    expect(d1.count).toBe(3)
    const rt = findResultType(d1, 'real-time')
    expect(rt.count).toBe(2)
    expect(rt.children.filter((n) => n.kind === 'leaf')).toHaveLength(2)
  })

  it('设备与 API 二选一（api 型任务归入 device 层）', () => {
    const withApi: CherryPickCandidate[] = [
      {
        ...CANDIDATES[0],
        resultId: 100,
        deviceId: null,
        deviceName: null,
        apiId: 7,
        apiName: '识别API-v2',
      },
    ]
    const tree = buildPickTree(withApi)
    const taskA = findTask(tree, 1042)
    const c1 = findCase(taskA, 'c1')
    const apiNode = c1.children.find(
      (n): n is PickTreeBranch => n.kind === 'branch' && n.name === '识别API-v2'
    )
    expect(apiNode).toBeDefined()
    expect(apiNode?.count).toBe(1)
  })

  it('缺 case_name/device_name 时降级友好文案 + 截断 id（§11-2/INT-713 打回 #1）', () => {
    const unnamed = buildPickTree([{ ...CANDIDATES[0], caseName: null, deviceName: null }])
    const taskA = findTask(unnamed, 1042)
    const c1 = findCase(taskA, 'c1')
    expect(c1.name).toBe('用例不可用 c1')
    const d = c1.children.find((n) => n.kind === 'branch')
    expect(d && d.name).toBe('设备不可用 1')
    const firstChild = d && d.kind === 'branch' ? d.children[0] : undefined
    const leaf = firstChild && firstChild.kind === 'branch' ? firstChild.children[0] : null
    expect(leaf && leaf.kind === 'leaf' && leaf.caseName).toBe('用例不可用 c1')
  })

  it('缺 case_name 且 case_id 为 36 位 UUID → 不裸显 UUID，截断前 8 位（INT-713 打回 #1）', () => {
    const longId = '1e98e5e6-b2bb-472d-b923-de6dde206ebf'
    const orphan = buildPickTree([{ ...CANDIDATES[0], caseId: longId, caseName: null }])
    const taskA = findTask(orphan, 1042)
    const c1 = findCase(taskA, longId)
    expect(c1.name).toBe(`用例不可用 ${longId.slice(0, 8)}…`)
    expect(c1.name).not.toContain(longId)
    const d = c1.children.find((n) => n.kind === 'branch') as PickTreeBranch
    const rt = d.children[0] as PickTreeBranch
    const leaf = rt.children[0]
    expect(leaf.kind === 'leaf' && leaf.caseName).toBe(`用例不可用 ${longId.slice(0, 8)}…`)
  })

  it('候选未返 result_type → result_type 级折叠为「结果类型待补充」（§11-2/INT-713）', () => {
    const pending = buildPickTree([{ ...CANDIDATES[0], resultType: null }])
    const taskA = findTask(pending, 1042)
    const c1 = findCase(taskA, 'c1')
    const d1 = findDevice(c1, '设备-01')
    const rt = findResultType(d1, '结果类型待补充')
    expect(rt.count).toBe(1)
    const leaf = rt.children[0]
    expect(leaf.kind === 'leaf' && leaf.resultType).toBeNull()
  })

  it('R10 已加购叶标记', () => {
    const tree = buildPickTree(CANDIDATES, new Set([1, 6]))
    const taskA = findTask(tree, 1042)
    const c1 = findCase(taskA, 'c1')
    const d1 = findDevice(c1, '设备-01')
    const rt = findResultType(d1, 'real-time')
    const leaves = rt.children.filter((n) => n.kind === 'leaf')
    expect(leaves[0]).toMatchObject({ kind: 'leaf', resultId: 1, added: true })
    expect(leaves[1]).toMatchObject({ kind: 'leaf', resultId: 2, added: false })
  })
})

describe('buildPickTree 用例级元信息（§3.7.1）', () => {
  it('用例节点携带 caseId（CaseIdBadge）与 algorithmType（算法徽章）', () => {
    const tree = buildPickTree(CANDIDATES)
    const taskA = findTask(tree, 1042)
    const c1 = findCase(taskA, 'c1')
    expect(c1.caseId).toBe('c1')
    expect(c1.algorithmType).toBe('CRM')
    const c2 = findCase(taskA, 'c2')
    expect(c2.algorithmType).toBe('CRM')
  })

  it('缺 algorithmType → 算法徽章数据源为 null（§11-7 未落地区段）', () => {
    const tree = buildPickTree([{ ...CANDIDATES[0], algorithmType: null }])
    const taskA = findTask(tree, 1042)
    const c1 = findCase(taskA, 'c1')
    expect(c1.algorithmType).toBeNull()
  })

  it('用例节点携带 §11-7 真名：tags/groupId/groupName/totalDuration/rounds', () => {
    const tree = buildPickTree(CANDIDATES)
    const c1 = findCase(findTask(tree, 1042), 'c1')
    expect(c1.tags).toEqual(['拒识', '多轮拒识'])
    expect(c1.groupId).toBe('g1')
    expect(c1.groupName).toBe('拒识')
    expect(c1.totalDuration).toBe(12.09)
    expect(c1.rounds).toBe(3)
    // 缺省行（c3）→ 空标签 / null 分组，由用例层组织落兜底桶
    const c3 = findCase(findTask(tree, 1041), 'c3')
    expect(c3.tags).toEqual([])
    expect(c3.groupId).toBeNull()
    expect(c3.totalDuration).toBeNull()
  })
})

describe('buildPickCaseView（A 组用例视图：用例 → 设备/API → result_type → 任务 → 叶）', () => {
  it('顶层即用例节点，任务在最末一级（叶的前一级），叶挂在任务节点下', () => {
    const view = buildPickCaseView(CANDIDATES)
    expect(view).toHaveLength(3) // c1 / c2 / c3
    expect(view.every((n) => n.kind === 'branch' && n.level === 'case')).toBe(true)

    const c1Node = view.find((n) => n.kind === 'branch' && n.caseId === 'c1') as PickTreeBranch
    expect(c1Node.count).toBe(3)
    const d1 = c1Node.children.find(
      (n): n is PickTreeBranch => n.kind === 'branch' && n.level === 'device'
    ) as PickTreeBranch
    expect(d1?.name).toBe('设备-01')
    const rt = d1.children.find(
      (n): n is PickTreeBranch => n.kind === 'branch' && n.level === 'resultType'
    ) as PickTreeBranch
    expect(rt?.name).toBe('real-time')
    expect(rt?.count).toBe(2)
    // result_type 之下是任务层（t1/t2 两个任务 → 任务层出现）
    const taskNodes = rt.children.filter(
      (n): n is PickTreeBranch => n.kind === 'branch' && n.level === 'task'
    )
    expect(taskNodes.map((t) => t.name)).toEqual(['任务A'])
    expect(taskNodes[0].resultIds).toEqual([1, 2])
    expect(taskNodes[0].children.every((n) => n.kind === 'leaf')).toBe(true)
  })

  it('同一用例跨两个任务 → 用例卡只出现一次，上层共享、任务层分叉', () => {
    // 用例 c1 同时存在于任务 A（real-time/final）与任务 B（real-time）
    const multiTask = buildPickCaseView([
      ...CANDIDATES.slice(0, 3),
      { ...CANDIDATES[0], resultId: 10, taskId: 1041, taskName: '任务B' },
    ])
    const c1Nodes = multiTask.filter(
      (n) => n.kind === 'branch' && n.caseId === 'c1'
    ) as PickTreeBranch[]
    expect(c1Nodes).toHaveLength(1) // 用例卡只出现一次
    expect(c1Nodes[0].count).toBe(4) // 跨任务聚合计数（3 来自任务A + 1 来自任务B）
    const d1Nodes = c1Nodes[0].children.filter(
      (n): n is PickTreeBranch => n.kind === 'branch' && n.level === 'device'
    )
    expect(d1Nodes).toHaveLength(1) // 设备层共享，不按任务分簇
    const rt = d1Nodes[0].children.find(
      (n): n is PickTreeBranch => n.kind === 'branch' && n.level === 'resultType'
    ) as PickTreeBranch
    const taskNodes = rt.children.filter(
      (n): n is PickTreeBranch => n.kind === 'branch' && n.level === 'task'
    )
    expect(taskNodes.map((t) => t.name)).toEqual(['任务A', '任务B'])
    expect(taskNodes[0].resultIds).toEqual([1, 2])
    expect(taskNodes[1].resultIds).toEqual([10])
    // 任务 key 带 taskId；任务之上的 key 不带 taskId 命名空间
    expect(taskNodes[0].key.endsWith('-task:1042')).toBe(true)
    expect(taskNodes[1].key.endsWith('-task:1041')).toBe(true)
    expect(rt.key.includes('task:')).toBe(false)
  })

  it('只选 1 个任务（阶段 2 单任务）→ 任务层恒定单值，省略不渲染', () => {
    const singleTask = CANDIDATES.filter((c) => c.taskId === 1042)
    const view = buildPickCaseView(singleTask)
    const c1Node = view.find((n) => n.kind === 'branch' && n.caseId === 'c1') as PickTreeBranch
    const d1 = c1Node.children[0] as PickTreeBranch
    for (const rt of d1.children as PickTreeBranch[]) {
      expect(rt.children.every((n) => n.kind === 'leaf')).toBe(true)
    }
  })

  it('与共享 selectedResultIds 联动：勾选用例级 = 选中其下全部设备×结果类型×任务×结果行（R6）', () => {
    const view = buildPickCaseView(CANDIDATES)
    const c1Node = view.find((n) => n.kind === 'branch' && n.caseId === 'c1') as PickTreeBranch
    const next = toggleBranchSelection(c1Node, new Set(), true)
    expect(next).toEqual(new Set([1, 2, 3]))
    expect(getBranchSelectionState(c1Node, next)).toBe('checked')
  })

  it('R10 已加购标记与任务视角同源', () => {
    const view = buildPickCaseView(CANDIDATES, new Set([6]))
    const c3Node = view.find((n) => n.kind === 'branch' && n.caseId === 'c3') as PickTreeBranch
    const d2 = c3Node.children[0] as PickTreeBranch
    const rt = d2.children[0] as PickTreeBranch
    const taskNode = rt.children[0] as PickTreeBranch
    const leaf = taskNode.children[0]
    expect(leaf.kind === 'leaf' && leaf.added).toBe(true)
  })
})

describe('buildPickDeviceView（A 组设备视图：设备/API → result_type → 用例 → 任务 → 叶）', () => {
  it('顶层即设备节点，设备下 result_type → 用例 → 任务 → 叶', () => {
    const view = buildPickDeviceView(CANDIDATES)
    expect(view).toHaveLength(2) // 设备-01 / 设备-02
    expect(view.every((n) => n.kind === 'branch' && n.level === 'device')).toBe(true)

    const d1 = view.find((n) => n.kind === 'branch' && n.name === '设备-01') as PickTreeBranch
    expect(d1.count).toBe(5)
    const rtNames = d1.children.map((n) => (n.kind === 'branch' ? n.name : ''))
    expect(rtNames).toEqual(['real-time', 'final'])

    const rt = d1.children.find(
      (n): n is PickTreeBranch => n.kind === 'branch' && n.level === 'resultType' && n.name === 'final'
    ) as PickTreeBranch
    const c1Node = rt.children.find(
      (n): n is PickTreeBranch => n.kind === 'branch' && n.caseId === 'c1'
    ) as PickTreeBranch
    expect(c1Node.name).toBe('用例001')
    const taskNodes = c1Node.children.filter(
      (n): n is PickTreeBranch => n.kind === 'branch' && n.level === 'task'
    )
    expect(taskNodes.map((t) => t.name)).toEqual(['任务A'])
    const leaves = taskNodes[0].children.filter((n): n is PickTreeLeaf => n.kind === 'leaf')
    expect(leaves).toHaveLength(1)
    expect(leaves[0].resultId).toBe(3)
  })

  it('同一设备/result_type/用例跨两任务 → 上层共享，仅任务层分叉', () => {
    const view = buildPickDeviceView([
      ...CANDIDATES.slice(0, 3),
      { ...CANDIDATES[0], resultId: 10, taskId: 1041, taskName: '任务B' },
    ])
    const d1 = view.find((n) => n.kind === 'branch' && n.name === '设备-01') as PickTreeBranch
    expect(d1.count).toBe(4)
    const rt = d1.children.find(
      (n): n is PickTreeBranch => n.kind === 'branch' && n.name === 'real-time'
    ) as PickTreeBranch
    const c1Nodes = rt.children.filter(
      (n): n is PickTreeBranch => n.kind === 'branch' && n.level === 'case' && n.caseId === 'c1'
    )
    expect(c1Nodes).toHaveLength(1) // 用例卡只出现一次
    const taskNodes = c1Nodes[0].children.filter(
      (n): n is PickTreeBranch => n.kind === 'branch' && n.level === 'task'
    )
    expect(taskNodes.map((t) => t.name)).toEqual(['任务A', '任务B'])
  })

  it('单任务 → 任务层省略（用例卡下直接是叶）', () => {
    const view = buildPickDeviceView(CANDIDATES.filter((c) => c.taskId === 1042))
    const d1 = view.find((n) => n.kind === 'branch' && n.name === '设备-01') as PickTreeBranch
    const rt = d1.children[0] as PickTreeBranch
    const c1Node = rt.children[0] as PickTreeBranch
    expect(c1Node.children.every((n) => n.kind === 'leaf')).toBe(true)
  })

  it('同一设备下多 result_type 各成独立分支（R4/R5 容器语义可复用）', () => {
    const view = buildPickDeviceView(CANDIDATES)
    const d1 = view.find((n) => n.kind === 'branch' && n.name === '设备-01') as PickTreeBranch
    const rts = d1.children.filter((n) => n.kind === 'branch')
    expect(rts.map((r) => (r.kind === 'branch' ? r.level : ''))).toEqual([
      'resultType',
      'resultType',
    ])
  })

  it('R4 取消设备 → 其下 result_type / 用例 / 任务 / 结果行全部取消', () => {
    const view = buildPickDeviceView(CANDIDATES)
    const d1 = view.find((n) => n.kind === 'branch' && n.name === '设备-01') as PickTreeBranch
    const all = toggleBranchSelection(d1, new Set(), true)
    expect(all).toEqual(new Set([1, 2, 3, 4, 5]))
    const next = toggleBranchSelection(d1, all, false)
    expect(next.size).toBe(0)
  })
})

describe('buildPickResultTypeView（A 组结果类型视图：result_type → 设备/API → 用例 → 任务 → 叶）', () => {
  it('顶层即 result_type 节点，其下设备 → 用例 → 任务 → 叶', () => {
    const view = buildPickResultTypeView(CANDIDATES)
    const rt = view.find((n) => n.kind === 'branch' && n.name === 'real-time') as PickTreeBranch
    expect(rt.count).toBe(5) // real-time 跨任务聚合
    const devices = rt.children.filter((n) => n.kind === 'branch' && n.level === 'device')
    expect(devices.map((d) => (d.kind === 'branch' ? d.name : ''))).toEqual(['设备-01', '设备-02'])
    const d1 = devices.find((n) => n.kind === 'branch' && n.name === '设备-01') as PickTreeBranch
    const cases = d1.children.filter((n) => n.kind === 'branch' && n.level === 'case')
    expect(cases).toHaveLength(2) // c1 / c2
    // 每个用例卡下 = 任务层 → 叶
    for (const c of cases as PickTreeBranch[]) {
      const tasks = c.children.filter(
        (n): n is PickTreeBranch => n.kind === 'branch' && n.level === 'task'
      )
      expect(tasks.length).toBeGreaterThan(0)
      expect(tasks.every((t) => t.children.every((n) => n.kind === 'leaf'))).toBe(true)
    }
  })

  it('缺 result_type → 折叠为「结果类型待补充」（§3.7.1 PENDING 口径）', () => {
    const view = buildPickResultTypeView([{ ...CANDIDATES[0], resultType: null }])
    expect(view).toHaveLength(1)
    expect(view[0].name).toBe('结果类型待补充')
    expect(view[0].count).toBe(1)
  })

  it('R5 取消 result_type → 仅清该 result_type 下结果行（跨设备/用例/任务全清）', () => {
    const view = buildPickResultTypeView(CANDIDATES)
    const rt = view.find((n) => n.kind === 'branch' && n.name === 'real-time') as PickTreeBranch
    const all = toggleBranchSelection(rt, new Set(), true)
    expect(all).toEqual(new Set([1, 2, 4, 5, 6]))
    const next = toggleBranchSelection(rt, all, false)
    expect(next.size).toBe(0)
  })
})

describe('三视图勾选一致性（§3.8.3：共享同一 selectedResultIds）', () => {
  it('用例/设备/结果类型三视图叶结果集一致（同一候选行源重建，叶集 = 全部 resultId）', () => {
    const caseView = buildPickCaseView(CANDIDATES)
    const deviceView = buildPickDeviceView(CANDIDATES)
    const rtView = buildPickResultTypeView(CANDIDATES)
    const leavesOf = (items: PickTreeItem[]): number[] => {
      const ids: number[] = []
      const walk = (nodes: PickTreeItem[]) => {
        for (const n of nodes) {
          if (n.kind === 'leaf') ids.push(n.resultId)
          else walk(n.children)
        }
      }
      walk(items)
      return ids.sort((a, b) => a - b)
    }
    const expected = [1, 2, 3, 4, 5, 6]
    expect(leavesOf(caseView)).toEqual(expected)
    expect(leavesOf(deviceView)).toEqual(expected)
    expect(leavesOf(rtView)).toEqual(expected)
  })

  it('三视图任务层一致：任务节点均在最末一级（叶的前一级）', () => {
    const views = [
      buildPickCaseView(CANDIDATES),
      buildPickDeviceView(CANDIDATES),
      buildPickResultTypeView(CANDIDATES),
    ]
    for (const view of views) {
      const taskNodes: PickTreeBranch[] = []
      const walk = (nodes: PickTreeItem[]) => {
        for (const n of nodes) {
          if (n.kind === 'leaf') continue
          if (n.level === 'task') {
            taskNodes.push(n)
            continue
          }
          walk(n.children)
        }
      }
      walk(view)
      expect(taskNodes.length).toBeGreaterThan(0)
      for (const t of taskNodes) {
        expect(t.children.every((n) => n.kind === 'leaf')).toBe(true)
      }
    }
  })
})

describe('R1/R2 父级勾选全子 / 取消全子', () => {
  it('R1 勾选任务级 → 全部子孙选中', () => {
    const tree = buildPickTree(CANDIDATES)
    const taskA = findTask(tree, 1042)
    const next = toggleBranchSelection(taskA, new Set(), true)
    expect(next).toEqual(new Set([1, 2, 3, 4, 5]))
    expect(getBranchSelectionState(taskA, next)).toBe('checked')
  })

  it('R2 取消任务级 → 全部子孙取消，不留残留', () => {
    const tree = buildPickTree(CANDIDATES)
    const taskA = findTask(tree, 1042)
    const next = toggleBranchSelection(taskA, new Set([1, 2, 3, 4, 5]), false)
    expect(next.size).toBe(0)
  })

  it('R1/R6 勾选用例级 = 选中其下全部 device × result_type × 结果行（跨设备/结果类型全含）', () => {
    const tree = buildPickTree(CANDIDATES)
    const taskA = findTask(tree, 1042)
    const c1 = findCase(taskA, 'c1')
    const next = toggleBranchSelection(c1, new Set(), true)
    expect(next).toEqual(new Set([1, 2, 3]))
    expect(getBranchSelectionState(c1, next)).toBe('checked')
  })
})

describe('R3 部分选中 indeterminate', () => {
  it('子级部分选中 → 父级 indeterminate；全选 → checked', () => {
    const tree = buildPickTree(CANDIDATES)
    const taskA = findTask(tree, 1042)
    const c1 = findCase(taskA, 'c1')
    const d1 = findDevice(c1, '设备-01')
    const rt = findResultType(d1, 'real-time')

    const afterOne = toggleLeafSelection(
      rt.children[0] as PickTreeLeaf,
      new Set()
    )
    expect(getBranchSelectionState(rt, afterOne)).toBe('indeterminate')
    expect(getBranchSelectionState(d1, afterOne)).toBe('indeterminate')
    expect(getBranchSelectionState(c1, afterOne)).toBe('indeterminate')
    expect(getBranchSelectionState(taskA, afterOne)).toBe('indeterminate')

    const allRt = toggleBranchSelection(rt, afterOne, true)
    expect(getBranchSelectionState(rt, allRt)).toBe('checked')
    expect(getBranchSelectionState(d1, allRt)).toBe('indeterminate') // final 未选
  })
})

describe('R4/R5 device 与 result_type 取消语义', () => {
  it('R4 取消 device → 其下 result_type 与结果行全部取消', () => {
    const tree = buildPickTree(CANDIDATES)
    const taskA = findTask(tree, 1042)
    const c1 = findCase(taskA, 'c1')
    const d1 = findDevice(c1, '设备-01')
    // 预选整棵 taskA
    const selected = toggleBranchSelection(taskA, new Set(), true)
    const next = toggleBranchSelection(d1, selected, false)
    expect(next).toEqual(new Set([4, 5])) // c2 仍选
    expect(getBranchSelectionState(d1, next)).toBe('unchecked')
    // c1 唯一设备即 d1，取消后整组无选中 → unchecked；任务级因 c2 仍选转 indeterminate
    expect(getBranchSelectionState(c1, next)).toBe('unchecked')
    expect(getBranchSelectionState(taskA, next)).toBe('indeterminate')
  })

  it('R5 取消 result_type → 仅清其下结果行，device 保持部分选中', () => {
    const tree = buildPickTree(CANDIDATES)
    const taskA = findTask(tree, 1042)
    const c1 = findCase(taskA, 'c1')
    const d1 = findDevice(c1, '设备-01')
    const rt = findResultType(d1, 'real-time')
    const selected = toggleBranchSelection(taskA, new Set(), true)
    const next = toggleBranchSelection(rt, selected, false)
    expect(next).toEqual(new Set([3, 4, 5])) // final + c2 保留
    expect(getBranchSelectionState(rt, next)).toBe('unchecked')
    expect(getBranchSelectionState(d1, next)).toBe('indeterminate') // final 仍选
  })
})

describe('R7 任务级勾选 = 整任务全部结果行', () => {
  it('任务节点勾选含全部结果 id（等价旧「合并任务」选取全集）', () => {
    const tree = buildPickTree(CANDIDATES)
    const taskA = findTask(tree, 1042)
    const next = toggleBranchSelection(taskA, new Set(), true)
    expect(new Set([1, 2, 3, 4, 5])).toEqual(next)
  })
})

describe('R8 跨任务独立', () => {
  it('不同任务互为独立根，勾选互不影响', () => {
    const tree = buildPickTree(CANDIDATES)
    const taskA = findTask(tree, 1042)
    const taskB = findTask(tree, 1041)
    const selectA = toggleBranchSelection(taskA, new Set(), true)
    expect(selectA).toEqual(new Set([1, 2, 3, 4, 5]))
    expect(getBranchSelectionState(taskB, selectA)).toBe('unchecked')

    const selectBoth = toggleBranchSelection(taskB, selectA, true)
    expect(selectBoth).toEqual(new Set([1, 2, 3, 4, 5, 6]))
  })
})

describe('R9 全选当前筛选 / 反选', () => {
  it('全选当前筛选 = 命中全部 result_id 选中', () => {
    const tree = buildPickTree(CANDIDATES)
    const next = selectAllVisible(tree, new Set())
    expect(next).toEqual(new Set([1, 2, 3, 4, 5, 6]))
  })

  it('反选 = 当前页可见节点取反，已选跨页项保留', () => {
    const tree = buildPickTree(CANDIDATES)
    // 预选跨页 id 9（模拟上一页选中项，不在当前树）
    const next = invertVisibleSelection(tree, new Set([9]))
    expect(next).toEqual(new Set([1, 2, 3, 4, 5, 6, 9]))
    expect(next.has(9)).toBe(true)
  })

  it('清空 = 空集', () => {
    expect(clearSelection()).toEqual(new Set())
  })
})

describe('已选汇总统计', () => {
  it('统计结果条数/任务数/设备数/用例数', () => {
    const tree = buildPickTree(CANDIDATES)
    // 选任务A的 c1-real-time 2条 + 任务B 1条 → 3 结果 / 2 任务 / 2 设备 / 2 用例
    const selected = new Set([1, 2, 6])
    const stats = computeSelectionStats(tree, selected)
    expect(stats.results).toBe(3)
    expect(stats.tasks).toBe(2)
    expect(stats.devices).toBe(2)
    expect(stats.cases).toBe(2)
  })
})

describe('购物车树与移除矩阵（§4.2/§4.3）', () => {
  const cartGroups = [
    {
      taskId: 1042,
      taskName: '任务A',
      entries: [
        { itemId: 'a1', resultId: 1, sourceTaskId: 1042, sourceTaskName: '任务A', sourceCaseId: 'c1', sourceCaseName: '用例001', sourceDeviceId: 1, sourceDeviceName: '设备-01', sourceApiId: null, sourceApiName: null, sourceResultType: 'real-time', executionStatus: 'completed', evaluationStatus: 'completed', invalid: false },
        { itemId: 'a2', resultId: 2, sourceTaskId: 1042, sourceTaskName: '任务A', sourceCaseId: 'c1', sourceCaseName: '用例001', sourceDeviceId: 1, sourceDeviceName: '设备-01', sourceApiId: null, sourceApiName: null, sourceResultType: 'real-time', executionStatus: 'completed', evaluationStatus: 'completed', invalid: true },
        { itemId: 'a3', resultId: 4, sourceTaskId: 1042, sourceTaskName: '任务A', sourceCaseId: 'c2', sourceCaseName: '用例002', sourceDeviceId: 1, sourceDeviceName: '设备-01', sourceApiId: null, sourceApiName: null, sourceResultType: null, executionStatus: 'completed', evaluationStatus: 'completed', invalid: false },
      ],
    },
  ]

  it('购物车树按任务→用例→设备→result_type 分组同构（§3.7.2：同一设备多 result_type 各成独立分支）', () => {
    const tree = buildCartTaskView(cartGroups)
    expect(tree).toHaveLength(1)
    expect(tree[0].count).toBe(3)
    expect(tree[0].entryIds).toEqual(['a1', 'a2', 'a3'])
    const caseNode = tree[0].children[0] as CartTreeBranch
    expect(caseNode.name).toBe('用例001')
    expect(caseNode.count).toBe(2)
    const deviceNode = caseNode.children[0] as CartTreeBranch
    expect(deviceNode.name).toBe('设备-01')
    expect(deviceNode.count).toBe(2)
    const rt = deviceNode.children[0] as CartTreeBranch
    expect(rt.level).toBe('resultType')
    expect(rt.name).toBe('real-time')
    expect(rt.count).toBe(2)
    expect(rt.entryIds).toEqual(['a1', 'a2'])
    const leaves = rt.children.filter((n): n is CartTreeLeaf => n.kind === 'leaf')
    expect(leaves).toHaveLength(2)
    expect(leaves[1].invalid).toBe(true)
  })

  it('同一设备下多个 result_type 各成独立并列分支（不压平为平铺叶）', () => {
    const multiRt = [
      {
        taskId: 1042,
        taskName: '任务A',
        entries: [
          { ...cartGroups[0].entries[0], itemId: 'r1', sourceResultType: 'real-time' },
          { ...cartGroups[0].entries[1], itemId: 'f1', sourceResultType: 'final' },
        ],
      },
    ]
    const tree = buildCartTaskView(multiRt)
    const caseNode = tree[0].children[0] as CartTreeBranch
    const deviceNode = caseNode.children[0] as CartTreeBranch
    const rtNames = deviceNode.children.map((n) => (n.kind === 'branch' ? n.name : ''))
    expect(rtNames).toEqual(['real-time', 'final'])
    const rtBranches = deviceNode.children.filter(
      (n): n is CartTreeBranch => n.kind === 'branch'
    )
    expect(rtBranches[0].count).toBe(1)
    expect(rtBranches[1].count).toBe(1)
  })

  it('历史快照缺 source_result_type → 折叠为「结果类型待补充」单组（§3.7.2/§11-5）', () => {
    const tree = buildCartTaskView(cartGroups)
    const caseNode = tree[0].children[1] as CartTreeBranch // c2（a3 无 source_result_type）
    expect(caseNode.name).toBe('用例002')
    const deviceNode = caseNode.children[0] as CartTreeBranch
    const rt = deviceNode.children[0] as CartTreeBranch
    expect(rt.level).toBe('resultType')
    expect(rt.name).toBe('结果类型待补充')
    expect(rt.count).toBe(1)
    const leaf = rt.children[0]
    expect(leaf.kind === 'leaf' && leaf.entryId === 'a3').toBe(true)
  })

  it('购物车条目缺 source_case_name/device_name → 友好降级文案 + 截断 id（INT-713 打回 #1）', () => {
    const orphanGroups = [
      {
        taskId: 1042,
        taskName: '任务A',
        entries: [
          {
            ...cartGroups[0].entries[0],
            itemId: 'x1',
            sourceCaseId: '1e98e5e6-b2bb-472d-b923-de6dde206ebf',
            sourceCaseName: null,
            sourceDeviceId: 9,
            sourceDeviceName: null,
          },
        ],
      },
    ]
    const tree = buildCartTaskView(orphanGroups)
    const caseNode = tree[0].children[0] as CartTreeBranch
    expect(caseNode.name).toBe('用例不可用 1e98e5e6…')
    const deviceNode = caseNode.children[0] as CartTreeBranch
    expect(deviceNode.name).toBe('设备不可用 9')
    const rt = deviceNode.children[0] as CartTreeBranch
    const leaf = rt.children[0]
    expect(leaf.kind === 'leaf' && leaf.caseName).toBe('用例不可用 1e98e5e6…')
  })

  it('节点级批量移除：收集 node 全部条目 id', () => {
    const tree = buildCartTaskView(cartGroups)
    const ids = collectEntryIds(tree)
    expect(ids).toEqual(['a1', 'a2', 'a3'])
    const caseNode = tree[0].children[0] as CartTreeBranch
    expect(collectEntryIds([caseNode])).toEqual(['a1', 'a2'])
    const deviceNode = caseNode.children[0] as CartTreeBranch
    expect(collectEntryIds([deviceNode])).toEqual(['a1', 'a2'])
    const rt = deviceNode.children[0] as CartTreeBranch
    expect(collectEntryIds([rt])).toEqual(['a1', 'a2'])
  })

  it('购物车节点勾选/取消（批量移除选择 R1-R5 同构）', () => {
    const tree = buildCartTaskView(cartGroups)
    const caseNode = tree[0].children[0] as CartTreeBranch
    const selected = toggleCartBranchSelection(caseNode, new Set(), true)
    expect(selected).toEqual(new Set(['a1', 'a2']))
    expect(getCartBranchSelectionState(caseNode, selected)).toBe('checked')
    const next = toggleCartBranchSelection(caseNode, selected, false)
    expect(next.size).toBe(0)
  })

  it('单条移除选择 toggleCartLeafSelection', () => {
    const tree = buildCartTaskView(cartGroups)
    const caseNode = tree[0].children[0] as CartTreeBranch
    const deviceNode = caseNode.children[0] as CartTreeBranch
    const rt = deviceNode.children[0] as CartTreeBranch
    const leaves = rt.children.filter((n): n is CartTreeLeaf => n.kind === 'leaf')
    const leaf = leaves[0]
    expect(leaf.kind).toBe('leaf')
    const once = toggleCartLeafSelection(leaf, new Set())
    expect(once).toEqual(new Set(['a1']))
    const twice = toggleCartLeafSelection(leaf, once)
    expect(twice.size).toBe(0)
  })
})

describe('购物车三视图树构建（A 组，INT-1694 二次口径：任务在最末一级）', () => {
  /** 跨任务样例：任务A 用例c1/c2 设备-01；任务B 用例c1 设备-02、用例c2 设备-01 */
  const multiCartGroups = [
    {
      taskId: 1042,
      taskName: '任务A',
      entries: [
        { itemId: 'a1', resultId: 1, sourceTaskId: 1042, sourceTaskName: '任务A', sourceCaseId: 'c1', sourceCaseName: '用例001', sourceDeviceId: 1, sourceDeviceName: '设备-01', sourceApiId: null, sourceApiName: null, sourceResultType: 'real-time', executionStatus: 'completed', evaluationStatus: 'completed', invalid: false },
        { itemId: 'a2', resultId: 2, sourceTaskId: 1042, sourceTaskName: '任务A', sourceCaseId: 'c2', sourceCaseName: '用例002', sourceDeviceId: 1, sourceDeviceName: '设备-01', sourceApiId: null, sourceApiName: null, sourceResultType: 'final', executionStatus: 'completed', evaluationStatus: 'completed', invalid: false },
        { itemId: 'a3', resultId: 5, sourceTaskId: 1042, sourceTaskName: '任务A', sourceCaseId: 'c2', sourceCaseName: '用例002', sourceDeviceId: 1, sourceDeviceName: '设备-01', sourceApiId: null, sourceApiName: null, sourceResultType: null, executionStatus: 'completed', evaluationStatus: 'completed', invalid: true },
      ],
    },
    {
      taskId: 1043,
      taskName: '任务B',
      entries: [
        { itemId: 'b1', resultId: 3, sourceTaskId: 1043, sourceTaskName: '任务B', sourceCaseId: 'c1', sourceCaseName: '用例001', sourceDeviceId: 2, sourceDeviceName: '设备-02', sourceApiId: null, sourceApiName: null, sourceResultType: 'real-time', executionStatus: 'completed', evaluationStatus: 'completed', invalid: false },
        { itemId: 'b2', resultId: 4, sourceTaskId: 1043, sourceTaskName: '任务B', sourceCaseId: 'c2', sourceCaseName: '用例002', sourceDeviceId: 1, sourceDeviceName: '设备-01', sourceApiId: null, sourceApiName: null, sourceResultType: 'real-time', executionStatus: 'completed', evaluationStatus: 'completed', invalid: false },
      ],
    },
  ]

  const collectCases = (items: CartTreeItem[]) =>
    items.filter((n): n is CartTreeBranch => n.kind === 'branch' && n.level === 'case')
  const collectDevices = (items: CartTreeItem[]) =>
    items.filter((n): n is CartTreeBranch => n.kind === 'branch' && n.level === 'device')
  const collectResultTypes = (items: CartTreeItem[]) =>
    items.filter((n): n is CartTreeBranch => n.kind === 'branch' && n.level === 'resultType')
  const collectTasks = (items: CartTreeItem[]) =>
    items.filter((n): n is CartTreeBranch => n.kind === 'branch' && n.level === 'task')
  const collectLeaves = (branch: CartTreeBranch) =>
    branch.children.filter((n): n is CartTreeLeaf => n.kind === 'leaf')

  it('用例视图：用例（跨任务聚合，只出现一次）→ 设备 → result_type → 任务 → 叶', () => {
    const tree = buildCartCaseView(multiCartGroups)
    const cases = collectCases(tree)
    expect(cases).toHaveLength(2)
    expect(cases[0].name).toBe('用例001')
    expect(cases[0].count).toBe(2)
    expect(cases[0].entryIds).toEqual(['a1', 'b1'])
    // 用例001 下：设备-01（a1）+ 设备-02（b1）
    const devices = collectDevices(cases[0].children)
    expect(devices.map((d) => d.name)).toEqual(['设备-01', '设备-02'])
    // 设备-01 → real-time → 任务（a1 属任务A）
    const rt = collectResultTypes(devices[0].children)[0]
    expect(rt.name).toBe('real-time')
    const tasks = collectTasks(rt.children)
    expect(tasks.map((t) => t.name)).toEqual(['任务A'])
    expect(collectLeaves(tasks[0]).map((l) => l.entryId)).toEqual(['a1'])
    // 设备-02 → real-time → 任务B → 叶 b1
    const rt2 = collectResultTypes(devices[1].children)[0]
    const tasks2 = collectTasks(rt2.children)
    expect(tasks2.map((t) => t.name)).toEqual(['任务B'])
    expect(collectLeaves(tasks2[0])[0].entryId).toBe('b1')
  })

  it('用例视图：快照缺 source_result_type → 折叠「结果类型待补充」单组（§11-5 不变）', () => {
    const tree = buildCartCaseView(multiCartGroups)
    const c2 = collectCases(tree).find((c) => c.name === '用例002') as CartTreeBranch
    const device = collectDevices(c2.children)[0]
    const pending = collectResultTypes(device.children).find((r) => r.name === '结果类型待补充')
    expect(pending).toBeDefined()
    expect(pending!.entryIds).toEqual(['a3'])
    const taskNode = collectTasks(pending!.children)[0]
    expect(collectLeaves(taskNode)[0].invalid).toBe(true)
  })

  it('用例视图：同一用例/设备/result_type 跨两任务 → 上层共享，仅任务层分叉', () => {
    const shared = [
      { taskId: 1042, taskName: '任务A', entries: [multiCartGroups[0].entries[0]] },
      {
        taskId: 1043,
        taskName: '任务B',
        entries: [
          {
            ...multiCartGroups[0].entries[0],
            itemId: 'b9',
            resultId: 9,
            sourceTaskId: 1043,
            sourceTaskName: '任务B',
          },
        ],
      },
    ]
    const tree = buildCartCaseView(shared)
    const cases = collectCases(tree)
    expect(cases).toHaveLength(1) // 用例卡只出现一次
    expect(cases[0].count).toBe(2)
    const devices = collectDevices(cases[0].children)
    expect(devices).toHaveLength(1) // 设备层共享
    const rts = collectResultTypes(devices[0].children)
    expect(rts).toHaveLength(1) // result_type 层共享
    const tasks = collectTasks(rts[0].children)
    expect(tasks.map((t) => t.name)).toEqual(['任务A', '任务B'])
    expect(tasks[0].entryIds).toEqual(['a1'])
    expect(tasks[1].entryIds).toEqual(['b9'])
  })

  it('设备视图：设备 → result_type → 用例（PickCaseCard 子树）→ 任务 → 叶', () => {
    const tree = buildCartDeviceView(multiCartGroups)
    const devices = collectDevices(tree)
    expect(devices).toHaveLength(2)
    expect(devices[0].name).toBe('设备-01')
    expect(devices[0].count).toBe(4) // a1/a2/a3/b2 同设备
    const rts = collectResultTypes(devices[0].children)
    expect(rts.map((r) => r.name)).toEqual(['real-time', 'final', '结果类型待补充'])
    const realtime = rts[0]
    expect(realtime.entryIds).toEqual(['a1', 'b2'])
    const realtimeCases = collectCases(realtime.children)
    expect(realtimeCases.map((c) => c.name)).toEqual(['用例001', '用例002'])
    expect(collectTasks(realtimeCases[0].children).map((t) => t.name)).toEqual(['任务A'])
    expect(collectTasks(realtimeCases[1].children).map((t) => t.name)).toEqual(['任务B'])
    expect(collectLeaves(collectTasks(realtimeCases[0].children)[0])[0].entryId).toBe('a1')
    expect(collectLeaves(collectTasks(realtimeCases[1].children)[0])[0].entryId).toBe('b2')
  })

  it('结果类型视图：result_type → 设备 → 用例（PickCaseCard 子树）→ 任务 → 叶', () => {
    const tree = buildCartResultTypeView(multiCartGroups)
    const rts = collectResultTypes(tree)
    expect(rts.map((r) => r.name)).toEqual(['real-time', 'final', '结果类型待补充'])
    expect(rts[0].count).toBe(3) // a1/b1/b2
    const devices = collectDevices(rts[0].children)
    expect(devices.map((d) => d.name)).toEqual(['设备-01', '设备-02'])
    const device0Cases = collectCases(devices[0].children)
    expect(device0Cases.map((c) => c.name)).toEqual(['用例001', '用例002'])
    const taskOfA1 = collectTasks(device0Cases[0].children)[0]
    expect(taskOfA1.name).toBe('任务A')
    expect(collectLeaves(taskOfA1)[0].entryId).toBe('a1')
    const device1Cases = collectCases(devices[1].children)
    expect(device1Cases.map((c) => c.name)).toEqual(['用例001'])
    const taskOfB1 = collectTasks(device1Cases[0].children)[0]
    expect(taskOfB1.name).toBe('任务B')
    expect(collectLeaves(taskOfB1)[0].entryId).toBe('b1')
  })

  it('购物车只有一个来源任务 → A 组任务层省略（叶直挂 result_type）', () => {
    const single = [multiCartGroups[0]]
    const caseTree = buildCartCaseView(single)
    const device = collectDevices(collectCases(caseTree)[0].children)[0]
    const rt = collectResultTypes(device.children)[0]
    expect(rt.children.every((n) => n.kind === 'leaf')).toBe(true)
    const deviceTree = buildCartDeviceView(single)
    const rt2 = collectResultTypes(collectDevices(deviceTree)[0].children)[0]
    const caseNode = collectCases(rt2.children)[0]
    expect(caseNode.children.every((n) => n.kind === 'leaf')).toBe(true)
  })

  it('三视图共享同一购物车条目集（同一 entryId 集，§4.2 切换不丢条目）', () => {
    const allIds = multiCartGroups.flatMap((g) => g.entries.map((e) => e.itemId)).sort()
    const caseTree = buildCartCaseView(multiCartGroups)
    const deviceTree = buildCartDeviceView(multiCartGroups)
    const rtTree = buildCartResultTypeView(multiCartGroups)
    expect(collectEntryIds(caseTree).sort()).toEqual(allIds)
    expect(collectEntryIds(deviceTree).sort()).toEqual(allIds)
    expect(collectEntryIds(rtTree).sort()).toEqual(allIds)
    // 勾选/移除矩阵在三种视图下对同一 entryId 集一致（节点级批量选择）
    const caseTop = caseTree[0]
    const deviceTop = deviceTree[0]
    const rtTop = rtTree[0]
    const selected = toggleCartBranchSelection(deviceTop, new Set(), true)
    expect(getCartBranchSelectionState(deviceTop, selected)).toBe('checked')
    expect(getCartBranchSelectionState(caseTop, selected)).toBe('indeterminate')
    expect(getCartBranchSelectionState(rtTop, selected)).toBe('indeterminate')
  })
})

describe('购物车任务视图（B 组，INT-1694：任务在第一级，下分三子模式）', () => {
  const groups = [
    {
      taskId: 1042,
      taskName: '任务A',
      entries: [
        { itemId: 'a1', resultId: 1, sourceTaskId: 1042, sourceTaskName: '任务A', sourceCaseId: 'c1', sourceCaseName: '用例001', sourceDeviceId: 1, sourceDeviceName: '设备-01', sourceApiId: null, sourceApiName: null, sourceResultType: 'real-time', executionStatus: 'completed', evaluationStatus: 'completed', invalid: false },
      ],
    },
    {
      taskId: 1043,
      taskName: '任务B',
      entries: [
        { itemId: 'b1', resultId: 3, sourceTaskId: 1043, sourceTaskName: '任务B', sourceCaseId: 'c1', sourceCaseName: '用例001', sourceDeviceId: 2, sourceDeviceName: '设备-02', sourceApiId: null, sourceApiName: null, sourceResultType: 'final', executionStatus: 'completed', evaluationStatus: 'completed', invalid: false },
      ],
    },
  ]
  const branches = (items: CartTreeItem[]) =>
    items.filter((n): n is CartTreeBranch => n.kind === 'branch')
  const leavesOf = (branch: CartTreeBranch) =>
    branch.children.filter((n): n is CartTreeLeaf => n.kind === 'leaf')

  it('用例子模式：任务 → 用例 → 设备 → result_type → 叶（任务已在第一级，不再重复任务层）', () => {
    const tree = buildCartTaskView(groups, 'case')
    const tasks = branches(tree)
    expect(tasks.map((t) => t.level)).toEqual(['task', 'task'])
    expect(tasks.map((t) => t.name)).toEqual(['任务A', '任务B'])
    expect(tasks[0].entryIds).toEqual(['a1'])
    const caseNode = branches(tasks[0].children)[0]
    expect(caseNode.level).toBe('case')
    expect(caseNode.name).toBe('用例001')
    const device = branches(caseNode.children)[0]
    expect(device.level).toBe('device')
    expect(device.name).toBe('设备-01')
    const rt = branches(device.children)[0]
    expect(rt.level).toBe('resultType')
    expect(rt.name).toBe('real-time')
    expect(leavesOf(rt).map((l) => l.entryId)).toEqual(['a1'])
  })

  it('设备子模式：任务 → 设备 → result_type → 用例 → 叶', () => {
    const tree = buildCartTaskView(groups, 'device')
    const taskA = branches(tree)[0]
    const device = branches(taskA.children)[0]
    expect(device.level).toBe('device')
    expect(device.name).toBe('设备-01')
    const rt = branches(device.children)[0]
    expect(rt.level).toBe('resultType')
    const caseNode = branches(rt.children)[0]
    expect(caseNode.level).toBe('case')
    expect(leavesOf(caseNode).map((l) => l.entryId)).toEqual(['a1'])
  })

  it('结果类型子模式：任务 → result_type → 设备 → 用例 → 叶', () => {
    const tree = buildCartTaskView(groups, 'resultType')
    const taskB = branches(tree)[1]
    const rt = branches(taskB.children)[0]
    expect(rt.level).toBe('resultType')
    expect(rt.name).toBe('final')
    const device = branches(rt.children)[0]
    expect(device.level).toBe('device')
    expect(device.name).toBe('设备-02')
    const caseNode = branches(device.children)[0]
    expect(caseNode.level).toBe('case')
    expect(leavesOf(caseNode).map((l) => l.entryId)).toEqual(['b1'])
  })

  it('任务视图子树 key 带 taskId 命名空间（同一用例在两任务下不撞键）', () => {
    const tree = buildCartTaskView(groups, 'case')
    const [taskA, taskB] = branches(tree)
    const caseA = branches(taskA.children)[0]
    const caseB = branches(taskB.children)[0]
    expect(caseA.name).toBe(caseB.name) // 同名用例
    expect(caseA.key).not.toBe(caseB.key) // key 带 taskId 命名空间
    expect(caseA.key).toContain('tv1042')
    expect(caseB.key).toContain('tv1043')
    expect(taskA.key).toBe('cart-task:1042')
  })

  it('任务视图即使只有 1 个任务也保留任务层（任务即该视图的第一级）', () => {
    const tree = buildCartTaskView([groups[0]], 'case')
    expect(branches(tree)).toHaveLength(1)
    expect(branches(tree)[0].level).toBe('task')
  })
})

describe('叶 toggle', () => {
  it('toggleLeafSelection 单条取反', () => {
    const tree = buildPickTree(CANDIDATES)
    const taskA = findTask(tree, 1042)
    const c1 = findCase(taskA, 'c1')
    const d1 = findDevice(c1, '设备-01')
    const rt = findResultType(d1, 'real-time')
    const leaf = rt.children[0] as PickTreeLeaf
    const once = toggleLeafSelection(leaf, new Set())
    expect(once).toEqual(new Set([1]))
    const twice = toggleLeafSelection(leaf, once)
    expect(twice.size).toBe(0)
  })

  it('collectVisibleResultIds 收集全部叶', () => {
    const tree = buildPickTree(CANDIDATES)
    const ids = collectVisibleResultIds(tree)
    expect(ids.sort()).toEqual([1, 2, 3, 4, 5, 6])
  })
})
