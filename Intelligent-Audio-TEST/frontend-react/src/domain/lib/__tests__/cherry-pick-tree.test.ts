/**
 * 挑选联动规则与购物车树单测（18_挑选合并功能交互重设计.md §3.2 R1-R10，INT-600）。
 * 阶段 2 三视图/任务树已改为服务端候选树构建，对应单测见 pick-candidate-tree.test.ts；
 * 本文件保留勾选联动、用例层组织与购物车树/移除矩阵（INT-1694 口径）。
 */
import { describe, expect, it } from 'vitest'

import type {
  CartTreeBranch,
  CartTreeItem,
  CartTreeLeaf,
  PickTreeLeaf,
} from '@/domain/models/cherryPick'
import {
  groupCasesByCaseGroup,
  groupCasesByTag,
} from '@/domain/lib/sub-view-aggregation'
import {
  buildCartCaseView,
  buildCartDeviceView,
  buildCartResultTypeView,
  buildCartTaskView,
  clearSelection,
  collectEntryIds,
  getBranchSelectionState,
  getCartBranchSelectionState,
  hasResultTypeVariety,
  toggleBranchSelection,
  toggleCartBranchSelection,
  toggleCartLeafSelection,
  toggleLeafSelection,
} from '@/domain/lib/cherry-pick-tree'

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
    // 单一种类 result_type → 该层省略，叶直接挂在设备下
    const leaf = deviceNode.children[0]
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
  const collectOrgs = (items: CartTreeItem[]) =>
    items.filter((n): n is CartTreeBranch => n.kind === 'branch' && n.level === 'caseOrg')
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
      {
        taskId: 1042,
        taskName: '任务A',
        entries: [
          multiCartGroups[0].entries[0], // a1 real-time
          // 第二种 result_type 仅用于让该层出现（单一种类时整层省略，见「结果类型只有 1 种」用例组）
          {
            ...multiCartGroups[0].entries[0],
            itemId: 'a2f',
            resultId: 12,
            sourceResultType: 'final',
          },
        ],
      },
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
    expect(cases[0].count).toBe(3)
    const devices = collectDevices(cases[0].children)
    expect(devices).toHaveLength(1) // 设备层共享
    const rts = collectResultTypes(devices[0].children)
    expect(rts.map((r) => r.name)).toEqual(['real-time', 'final']) // result_type 层共享，不按任务分簇
    const tasks = collectTasks(rts[0].children)
    expect(tasks.map((t) => t.name)).toEqual(['任务A', '任务B'])
    expect(tasks[0].entryIds).toEqual(['a1'])
    expect(tasks[1].entryIds).toEqual(['b9'])
  })

  it('设备视图：设备 → result_type → 组织层 → 用例（PickCaseCard 子树）→ 任务 → 叶', () => {
    const tree = buildCartDeviceView(multiCartGroups)
    const devices = collectDevices(tree)
    expect(devices).toHaveLength(2)
    expect(devices[0].name).toBe('设备-01')
    expect(devices[0].count).toBe(4) // a1/a2/a3/b2 同设备
    const rts = collectResultTypes(devices[0].children)
    expect(rts.map((r) => r.name)).toEqual(['real-time', 'final', '结果类型待补充'])
    const realtime = rts[0]
    expect(realtime.entryIds).toEqual(['a1', 'b2'])
    // 组织层：result_type 之下、用例卡之上（快照缺 tags/group → 「未分组」兜底桶）
    const orgs = collectOrgs(realtime.children)
    expect(orgs).toHaveLength(1)
    expect(orgs[0].name).toBe('未分组')
    expect(orgs[0].orgKind).toBe('group')
    expect(orgs[0].entryIds).toEqual(['a1', 'b2'])
    const realtimeCases = collectCases(orgs[0].children)
    expect(realtimeCases.map((c) => c.name)).toEqual(['用例001', '用例002'])
    expect(collectTasks(realtimeCases[0].children).map((t) => t.name)).toEqual(['任务A'])
    expect(collectTasks(realtimeCases[1].children).map((t) => t.name)).toEqual(['任务B'])
    expect(collectLeaves(collectTasks(realtimeCases[0].children)[0])[0].entryId).toBe('a1')
    expect(collectLeaves(collectTasks(realtimeCases[1].children)[0])[0].entryId).toBe('b2')
  })

  it('结果类型视图：result_type → 设备 → 组织层 → 用例（PickCaseCard 子树）→ 任务 → 叶', () => {
    const tree = buildCartResultTypeView(multiCartGroups)
    const rts = collectResultTypes(tree)
    expect(rts.map((r) => r.name)).toEqual(['real-time', 'final', '结果类型待补充'])
    expect(rts[0].count).toBe(3) // a1/b1/b2
    const devices = collectDevices(rts[0].children)
    expect(devices.map((d) => d.name)).toEqual(['设备-01', '设备-02'])
    // 组织层：设备/API 之下、用例卡之上
    const orgs0 = collectOrgs(devices[0].children)
    expect(orgs0).toHaveLength(1)
    expect(orgs0[0].name).toBe('未分组')
    const device0Cases = collectCases(orgs0[0].children)
    expect(device0Cases.map((c) => c.name)).toEqual(['用例001', '用例002'])
    const taskOfA1 = collectTasks(device0Cases[0].children)[0]
    expect(taskOfA1.name).toBe('任务A')
    expect(collectLeaves(taskOfA1)[0].entryId).toBe('a1')
    const device1Cases = collectCases(collectOrgs(devices[1].children)[0].children)
    expect(device1Cases.map((c) => c.name)).toEqual(['用例001'])
    const taskOfB1 = collectTasks(device1Cases[0].children)[0]
    expect(taskOfB1.name).toBe('任务B')
    expect(collectLeaves(taskOfB1)[0].entryId).toBe('b1')
  })

  it('购物车只有一个来源任务 → 任务层仍恒显（购物车/复核抽屉与阶段 2 单任务省略口径相反）', () => {
    const single = [multiCartGroups[0]]
    const caseTree = buildCartCaseView(single)
    const device = collectDevices(collectCases(caseTree)[0].children)[0]
    const rt = collectResultTypes(device.children)[0]
    const caseTasks = collectTasks(rt.children)
    expect(caseTasks.map((t) => t.name)).toEqual(['任务A'])
    expect(collectLeaves(caseTasks[0])[0].entryId).toBe('a1')
    const deviceTree = buildCartDeviceView(single)
    const rt2 = collectResultTypes(collectDevices(deviceTree)[0].children)[0]
    const caseNode = collectCases(collectOrgs(rt2.children)[0].children)[0]
    const deviceTasks = collectTasks(caseNode.children)
    expect(deviceTasks.map((t) => t.name)).toEqual(['任务A'])
    expect(collectLeaves(deviceTasks[0])[0].entryId).toBe('a1')
    const rtTree = buildCartResultTypeView(single)
    const rtCase = collectCases(
      collectOrgs(collectDevices(collectResultTypes(rtTree)[0].children)[0].children)[0].children
    )[0]
    expect(collectTasks(rtCase.children).map((t) => t.name)).toEqual(['任务A'])
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

describe('购物车用例层组织接 INT-1693 真名（tags/group_id/group_name）', () => {
  /** 任务A：用例001/002 同分组「拒识」（标签不同）；用例003 为历史条目（缺 tags/group） */
  const groups = [
    {
      taskId: 1042,
      taskName: '任务A',
      entries: [
        { itemId: 'a1', resultId: 1, sourceTaskId: 1042, sourceTaskName: '任务A', sourceCaseId: 'c1', sourceCaseName: '用例001', sourceDeviceId: 1, sourceDeviceName: '设备-01', sourceApiId: null, sourceApiName: null, sourceResultType: 'real-time', sourceTags: ['拒识', '多轮拒识'], sourceGroupId: 'g1', sourceGroupName: '拒识', executionStatus: 'completed', evaluationStatus: 'completed', invalid: false },
        { itemId: 'a2', resultId: 2, sourceTaskId: 1042, sourceTaskName: '任务A', sourceCaseId: 'c2', sourceCaseName: '用例002', sourceDeviceId: 1, sourceDeviceName: '设备-01', sourceApiId: null, sourceApiName: null, sourceResultType: 'real-time', sourceTags: ['静默拒识'], sourceGroupId: 'g1', sourceGroupName: '拒识', executionStatus: 'completed', evaluationStatus: 'completed', invalid: false },
        { itemId: 'a3', resultId: 3, sourceTaskId: 1042, sourceTaskName: '任务A', sourceCaseId: 'c3', sourceCaseName: '用例003', sourceDeviceId: 1, sourceDeviceName: '设备-01', sourceApiId: null, sourceApiName: null, sourceResultType: 'final', sourceTags: [], sourceGroupId: null, sourceGroupName: null, executionStatus: 'completed', evaluationStatus: 'completed', invalid: false },
      ],
    },
  ]

  /** 与 PickCaseOrgList 同口径：用例分支 → 聚合入参 */
  const orgItems = (cases: CartTreeBranch[]) =>
    cases.map((b) => ({
      tags: b.tags ?? [],
      groupId: b.groupId ?? null,
      groupName: b.groupName ?? null,
      totalDuration: b.totalDuration ?? null,
    }))

  it('用例视图顶层组头：按真分组聚合，历史条目仍落「未分组」（标签视图按真标签名）', () => {
    const cases = buildCartCaseView(groups).filter(
      (n): n is CartTreeBranch => n.kind === 'branch' && n.level === 'case'
    )
    expect(cases.map((c) => c.name)).toEqual(['用例001', '用例002', '用例003'])

    const groupHeads = groupCasesByCaseGroup(orgItems(cases))
    expect(groupHeads.map((g) => [g.label, g.cases.length])).toEqual([
      ['拒识', 2],
      ['未分组', 1],
    ])

    const tagHeads = groupCasesByTag(orgItems(cases), [])
    expect(tagHeads.map((g) => g.label)).toEqual(
      expect.arrayContaining(['拒识', '多轮拒识', '静默拒识', '未设置标签'])
    )
  })

  it('设备视图 caseOrg 组头：显示真实分组名（历史条目组仍为「未分组」）', () => {
    const deviceTree = buildCartDeviceView(groups)
    const device = deviceTree.find(
      (n): n is CartTreeBranch => n.kind === 'branch' && n.level === 'device'
    )!
    const byRt = (rt: string) =>
      device.children.find(
        (n): n is CartTreeBranch => n.kind === 'branch' && n.level === 'resultType' && n.name === rt
      )!
    const realtimeOrg = byRt('real-time').children.filter(
      (n): n is CartTreeBranch => n.kind === 'branch' && n.level === 'caseOrg'
    )
    expect(realtimeOrg.map((o) => [o.name, o.count, o.entryIds])).toEqual([
      ['拒识', 2, ['a1', 'a2']],
    ])
    expect(realtimeOrg[0].orgKind).toBe('group')

    const finalOrg = byRt('final').children.filter(
      (n): n is CartTreeBranch => n.kind === 'branch' && n.level === 'caseOrg'
    )
    expect(finalOrg.map((o) => [o.name, o.count])).toEqual([['未分组', 1]])

    // 结果类型视图：result_type → 设备 → caseOrg，组头同为真名
    const rtTree = buildCartResultTypeView(groups)
    const realtimeRt = rtTree.find(
      (n): n is CartTreeBranch => n.kind === 'branch' && n.level === 'resultType' && n.name === 'real-time'
    )!
    const rtDevice = realtimeRt.children.find(
      (n): n is CartTreeBranch => n.kind === 'branch' && n.level === 'device'
    )!
    expect(
      rtDevice.children
        .filter((n): n is CartTreeBranch => n.kind === 'branch' && n.level === 'caseOrg')
        .map((o) => o.name)
    ).toEqual(['拒识'])
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

  it('设备子模式：任务 → 设备 → result_type → 组织层 → 用例 → 叶', () => {
    const tree = buildCartTaskView(groups, 'device')
    const taskA = branches(tree)[0]
    const device = branches(taskA.children)[0]
    expect(device.level).toBe('device')
    expect(device.name).toBe('设备-01')
    const rt = branches(device.children)[0]
    expect(rt.level).toBe('resultType')
    // 组织层：任务内组织（result_type 之下、用例卡之上）
    const org = branches(rt.children)[0]
    expect(org.level).toBe('caseOrg')
    expect(org.name).toBe('未分组')
    expect(org.orgKind).toBe('group')
    const caseNode = branches(org.children)[0]
    expect(caseNode.level).toBe('case')
    expect(leavesOf(caseNode).map((l) => l.entryId)).toEqual(['a1'])
  })

  it('结果类型子模式：任务 → result_type → 设备 → 组织层 → 用例 → 叶', () => {
    const tree = buildCartTaskView(groups, 'resultType')
    const taskB = branches(tree)[1]
    const rt = branches(taskB.children)[0]
    expect(rt.level).toBe('resultType')
    expect(rt.name).toBe('final')
    const device = branches(rt.children)[0]
    expect(device.level).toBe('device')
    expect(device.name).toBe('设备-02')
    // 组织层：任务内组织（设备/API 之下、用例卡之上）
    const org = branches(device.children)[0]
    expect(org.level).toBe('caseOrg')
    expect(org.entryIds).toEqual(['b1'])
    const caseNode = branches(org.children)[0]
    expect(caseNode.level).toBe('case')
    expect(leavesOf(caseNode).map((l) => l.entryId)).toEqual(['b1'])
  })

  it('设备 / 结果类型子模式：切组织维度不改变检查组头与条目集（任务内组织不跨任务）', () => {
    const allIds = groups.flatMap((g) => g.entries.map((e) => e.itemId)).sort()
    for (const org of ['group', 'tag'] as const) {
      for (const sv of ['flat', 'byTag'] as const) {
        for (const sub of ['device', 'resultType'] as const) {
          const tree = buildCartTaskView(groups, sub, org, sv)
          expect(collectEntryIds(tree).sort()).toEqual(allIds)
          // 任务内组织层：每个任务节点下的 caseOrg 组头只含本任务条目
          for (const task of branches(tree)) {
            const own = new Set(task.entryIds)
            const walk = (items: CartTreeItem[]) => {
              for (const n of items) {
                if (n.kind !== 'branch') continue
                if (n.level === 'caseOrg') {
                  expect(n.entryIds.every((id) => own.has(id))).toBe(true)
                }
                walk(n.children)
              }
            }
            walk(task.children)
          }
        }
      }
    }
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

describe('结果类型只有 1 种 → 树内省略 result_type 层（购物车，任务层恒显）', () => {
  /** 购物车：两个任务，全部 default → 单一种类（任务层恒显） */
  const singleTypeCart = [
    {
      taskId: 1042,
      taskName: '任务A',
      entries: [
        { itemId: 'a1', resultId: 1, sourceTaskId: 1042, sourceTaskName: '任务A', sourceCaseId: 'c1', sourceCaseName: '用例001', sourceDeviceId: 1, sourceDeviceName: '设备-01', sourceApiId: null, sourceApiName: null, sourceResultType: 'default', executionStatus: 'completed', evaluationStatus: 'completed', invalid: false },
      ],
    },
    {
      taskId: 1043,
      taskName: '任务B',
      entries: [
        { itemId: 'b1', resultId: 2, sourceTaskId: 1043, sourceTaskName: '任务B', sourceCaseId: 'c1', sourceCaseName: '用例001', sourceDeviceId: 1, sourceDeviceName: '设备-01', sourceApiId: null, sourceApiName: null, sourceResultType: 'default', executionStatus: 'completed', evaluationStatus: 'completed', invalid: false },
      ],
    },
  ]

  it('购物车用例视图：用例 → 设备 → 任务 → 叶（任务层恒显，result_type 层省略）', () => {
    const tree = buildCartCaseView(singleTypeCart)
    const caseNode = tree[0] as CartTreeBranch
    expect(caseNode.level).toBe('case')
    const device = caseNode.children[0] as CartTreeBranch
    expect(device.level).toBe('device')
    const tasks = device.children as CartTreeBranch[]
    expect(tasks.map((t) => t.name)).toEqual(['任务A', '任务B'])
    expect(tasks[0].entryIds).toEqual(['a1'])
    expect(tasks[0].children.every((n) => n.kind === 'leaf')).toBe(true)
  })

  it('购物车设备视图：设备 → 组织层 → 用例 → 任务 → 叶', () => {
    const tree = buildCartDeviceView(singleTypeCart)
    const device = tree[0] as CartTreeBranch
    expect(device.level).toBe('device')
    const org = device.children[0] as CartTreeBranch
    expect(org.level).toBe('caseOrg')
    const caseNode = org.children[0] as CartTreeBranch
    expect(caseNode.level).toBe('case')
    expect((caseNode.children as CartTreeBranch[]).map((t) => t.name)).toEqual(['任务A', '任务B'])
  })

  it('购物车任务视图设备子模式：任务 → 设备 → 组织层 → 用例 → 叶（任务内同样省略）', () => {
    const tree = buildCartTaskView(singleTypeCart, 'device')
    const taskA = tree[0] as CartTreeBranch
    expect(taskA.level).toBe('task')
    const device = taskA.children[0] as CartTreeBranch
    expect(device.level).toBe('device')
    const org = device.children[0] as CartTreeBranch
    expect(org.level).toBe('caseOrg')
    const caseNode = org.children[0] as CartTreeBranch
    expect(caseNode.level).toBe('case')
    expect(caseNode.children.every((n) => n.kind === 'leaf')).toBe(true)
  })
})

describe('叶 toggle / 勾选态', () => {
  const leaf: PickTreeLeaf = {
    kind: 'leaf',
    key: 'leaf:1',
    resultId: 1,
    taskName: '任务A',
    caseName: '用例001',
    deviceId: 1,
    deviceName: '设备-01',
    apiId: null,
    apiName: null,
    resultType: 'real-time',
    executionStatus: 'completed',
    evaluationStatus: 'completed',
    createdAt: '2026-10-15T09:00:00',
    added: false,
  }

  it('toggleLeafSelection 单条取反', () => {
    const once = toggleLeafSelection(leaf, new Set())
    expect(once).toEqual(new Set([1]))
    const twice = toggleLeafSelection(leaf, once)
    expect(twice.size).toBe(0)
  })

  it('toggleBranchSelection 全选/取消整组', () => {
    const branch = {
      kind: 'branch' as const,
      key: 'b',
      level: 'task' as const,
      name: '任务A',
      count: 2,
      resultIds: [1, 2],
      children: [],
    }
    expect(toggleBranchSelection(branch, new Set(), true)).toEqual(new Set([1, 2]))
    expect(toggleBranchSelection(branch, new Set([1, 2, 9]), false)).toEqual(new Set([9]))
  })

  it('getBranchSelectionState 三态', () => {
    const branch = {
      kind: 'branch' as const,
      key: 'b',
      level: 'task' as const,
      name: '任务A',
      count: 2,
      resultIds: [1, 2],
      children: [],
    }
    expect(getBranchSelectionState(branch, new Set())).toBe('unchecked')
    expect(getBranchSelectionState(branch, new Set([1]))).toBe('indeterminate')
    expect(getBranchSelectionState(branch, new Set([1, 2]))).toBe('checked')
  })

  it('clearSelection 清空', () => {
    expect(clearSelection()).toEqual(new Set())
  })
})
describe('结果类型种类判定（负责人 2026-10-24T12:39Z：<2 种隐藏结果类型视图入口）', () => {
  it('全部同一种 → 无区分度', () => {
    expect(hasResultTypeVariety(['default', 'default', 'default'])).toBe(false)
  })

  it('≥2 种 → 有区分度', () => {
    expect(hasResultTypeVariety(['default', 'real-time'])).toBe(true)
    expect(hasResultTypeVariety(['default', null])).toBe(true)
  })

  it('null / 空串折叠为「结果类型待补充」兜底桶，同值不算两种', () => {
    expect(hasResultTypeVariety([null, undefined, '', ''])).toBe(false)
    expect(hasResultTypeVariety([null, 'default'])).toBe(true)
  })

  it('空集（加载中/无候选）→ 无区分度', () => {
    expect(hasResultTypeVariety([])).toBe(false)
  })
})
