/**
 * 挑选树联动规则单测（18_挑选合并功能交互重设计.md §3.2 R1-R10，INT-600）。
 * 纯函数测试：树构建 + 三态联动 + 批量选择 + 已选统计 + 购物车树/移除矩阵。
 */
import { describe, expect, it } from 'vitest'

import type {
  CartTreeBranch,
  CartTreeLeaf,
  CherryPickCandidate,
  PickTreeBranch,
  PickTreeItem,
  PickTreeLeaf,
} from '@/domain/models/cherryPick'
import {
  buildCartTree,
  buildPickCaseView,
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
  { resultId: 1, taskId: 1042, taskName: '任务A', caseId: 'c1', caseName: '用例001', deviceId: 1, deviceName: '设备-01', apiId: null, apiName: null, resultType: 'real-time', algorithmType: 'CRM', executionStatus: 'completed', evaluationStatus: 'completed', evaluated: true, createdAt: '2026-10-15T09:00:00' },
  { resultId: 2, taskId: 1042, taskName: '任务A', caseId: 'c1', caseName: '用例001', deviceId: 1, deviceName: '设备-01', apiId: null, apiName: null, resultType: 'real-time', algorithmType: 'CRM', executionStatus: 'completed', evaluationStatus: 'completed', evaluated: true, createdAt: '2026-10-15T09:01:00' },
  // 任务 A 用例 c1 设备 d1 final（1 行）
  { resultId: 3, taskId: 1042, taskName: '任务A', caseId: 'c1', caseName: '用例001', deviceId: 1, deviceName: '设备-01', apiId: null, apiName: null, resultType: 'final', algorithmType: 'CRM', executionStatus: 'completed', evaluationStatus: 'evaluating', evaluated: false, createdAt: '2026-10-15T09:02:00' },
  // 任务 A 用例 c2 设备 d1 real-time（2 行）
  { resultId: 4, taskId: 1042, taskName: '任务A', caseId: 'c2', caseName: '用例002', deviceId: 1, deviceName: '设备-01', apiId: null, apiName: null, resultType: 'real-time', algorithmType: 'CRM', executionStatus: 'completed', evaluationStatus: 'completed', evaluated: true, createdAt: '2026-10-15T09:03:00' },
  { resultId: 5, taskId: 1042, taskName: '任务A', caseId: 'c2', caseName: '用例002', deviceId: 1, deviceName: '设备-01', apiId: null, apiName: null, resultType: 'real-time', algorithmType: 'CRM', executionStatus: 'completed', evaluationStatus: 'completed', evaluated: true, createdAt: '2026-10-15T09:04:00' },
  // 任务 B 用例 c3 设备 d2 real-time（1 行）——跨任务独立根（R8）
  { resultId: 6, taskId: 1041, taskName: '任务B', caseId: 'c3', caseName: '用例003', deviceId: 2, deviceName: '设备-02', apiId: null, apiName: null, resultType: 'real-time', algorithmType: 'CRM', executionStatus: 'failed', evaluationStatus: 'failed', evaluated: true, createdAt: '2026-10-15T10:00:00' },
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
    const leaf = d && d.kind === 'branch' ? d.children[0].children[0] : null
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
})

describe('buildPickCaseView（§3.7.3 用例视角：用例→来源任务→设备→result_type→结果行）', () => {
  it('按 caseId 跨任务聚合：同一用例多任务各自挂「设备→result_type」子树', () => {
    // 用例 c1 同时存在于任务 A（real-time/final）与任务 B（real-time）
    const multiTask = buildPickCaseView([
      ...CANDIDATES.slice(0, 3),
      { ...CANDIDATES[0], resultId: 10, taskId: 1041, taskName: '任务B' },
    ])
    const c1Node = multiTask.find(
      (n): n is PickTreeBranch => n.kind === 'branch' && n.caseId === 'c1'
    )
    expect(c1Node).toBeDefined()
    expect(c1Node?.count).toBe(4) // 跨任务聚合计数（3 来自任务A + 1 来自任务B）
    expect(c1Node?.resultIds).toEqual([1, 2, 3, 10])

    const tasks = c1Node?.children.filter(
      (n): n is PickTreeBranch => n.kind === 'branch' && n.level === 'task'
    )
    expect(tasks).toHaveLength(2)
    const taskB = tasks?.find((t) => t.name === '任务B')
    expect(taskB?.count).toBe(1)
    expect(taskB?.resultIds).toEqual([10])
    const d1 = taskB?.children.find(
      (n): n is PickTreeBranch => n.kind === 'branch' && n.level === 'device'
    )
    expect(d1?.count).toBe(1)
    const rt = d1?.children.find(
      (n): n is PickTreeBranch => n.kind === 'branch' && n.level === 'resultType'
    )
    expect(rt?.name).toBe('real-time')
    expect(rt?.resultIds).toEqual([10])
  })

  it('默认收起至用例级：顶层即用例节点（collapsible 由组件控制，树结构顶层 = 用例）', () => {
    const view = buildPickCaseView(CANDIDATES)
    expect(view).toHaveLength(3) // c1 / c2 / c3
    expect(view.every((n) => n.kind === 'branch' && n.level === 'case')).toBe(true)
  })

  it('与任务视角共享同一 selectedResultIds：勾选用例级 = 选中其下全部任务×设备×结果行', () => {
    const view = buildPickCaseView(CANDIDATES)
    const c1Node = view.find((n) => n.kind === 'branch' && n.caseId === 'c1') as PickTreeBranch
    const next = toggleBranchSelection(c1Node, new Set(), true)
    expect(next).toEqual(new Set([1, 2, 3]))
    expect(getBranchSelectionState(c1Node, next)).toBe('checked')
  })

  it('取消任务级节点仅清该任务下的结果行，用例保持部分选中', () => {
    const multiTask = buildPickCaseView([
      ...CANDIDATES.slice(0, 3),
      { ...CANDIDATES[0], resultId: 10, taskId: 1041, taskName: '任务B' },
    ])
    const c1Node = multiTask.find(
      (n) => n.kind === 'branch' && n.caseId === 'c1'
    ) as PickTreeBranch
    const all = toggleBranchSelection(c1Node, new Set(), true)
    const taskB = c1Node.children.find(
      (n): n is PickTreeBranch => n.kind === 'branch' && n.name === '任务B'
    ) as PickTreeBranch
    const next = toggleBranchSelection(taskB, all, false)
    expect(next).toEqual(new Set([1, 2, 3])) // 任务B 的 10 被清，用例保持部分选中
    expect(getBranchSelectionState(c1Node, next)).toBe('indeterminate')
  })

  it('R10 已加购标记与任务视角同源', () => {
    const view = buildPickCaseView(CANDIDATES, new Set([6]))
    const c3Node = view.find((n) => n.kind === 'branch' && n.caseId === 'c3') as PickTreeBranch
    const taskB = c3Node.children[0] as PickTreeBranch
    const d2 = taskB.children[0] as PickTreeBranch
    const rt = d2.children[0] as PickTreeBranch
    const leaf = rt.children[0]
    expect(leaf.kind === 'leaf' && leaf.added).toBe(true)
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
    const tree = buildCartTree(cartGroups)
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
    const tree = buildCartTree(multiRt)
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
    const tree = buildCartTree(cartGroups)
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
    const tree = buildCartTree(orphanGroups)
    const caseNode = tree[0].children[0] as CartTreeBranch
    expect(caseNode.name).toBe('用例不可用 1e98e5e6…')
    const deviceNode = caseNode.children[0] as CartTreeBranch
    expect(deviceNode.name).toBe('设备不可用 9')
    const rt = deviceNode.children[0] as CartTreeBranch
    const leaf = rt.children[0]
    expect(leaf.kind === 'leaf' && leaf.caseName).toBe('用例不可用 1e98e5e6…')
  })

  it('节点级批量移除：收集 node 全部条目 id', () => {
    const tree = buildCartTree(cartGroups)
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
    const tree = buildCartTree(cartGroups)
    const caseNode = tree[0].children[0] as CartTreeBranch
    const selected = toggleCartBranchSelection(caseNode, new Set(), true)
    expect(selected).toEqual(new Set(['a1', 'a2']))
    expect(getCartBranchSelectionState(caseNode, selected)).toBe('checked')
    const next = toggleCartBranchSelection(caseNode, selected, false)
    expect(next.size).toBe(0)
  })

  it('单条移除选择 toggleCartLeafSelection', () => {
    const tree = buildCartTree(cartGroups)
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
