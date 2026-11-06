/**
 * 阶段 2 候选树（服务端 `candidates/tree`）→ 三视图 / 任务树单测（INT-1892 重做）。
 * 口径沿用 INT-1694：任务末级（叶的前一级）、用例层组织独立一层、用例节点 = 用例卡；
 * 叶明细不在树响应里 → 叶的父级节点携带 leafFilter，展开时按需分页拉 candidates。
 */
import { describe, expect, it } from 'vitest'

import type {
  PickCandidateTree,
  PickTreeBranch,
  PickTreeItem,
} from '@/domain/models/cherryPick'
import {
  PENDING_RESULT_TYPE_VALUE,
  UNKNOWN_CASE_NAME,
  UNKNOWN_DEVICE_NAME,
  buildLeafFilterKey,
  buildPickCaseView,
  buildPickDeviceView,
  buildPickResultTypeView,
  buildPickTaskTree,
  buildPickTaskView,
  buildResultIndex,
  computeSelectionStatsFromIndex,
  displayCaseName,
  displayDeviceName,
  invertVisibleSelection,
  isLeafParentBranch,
  isPendingResultType,
  resultTypeLabel,
  treeResultTypeVariety,
} from '@/domain/lib/pick-candidate-tree'

/** 候选树样例：任务A（c1 real-time/final + c2 real-time） + 任务B（c3 real-time） */
const TREE: PickCandidateTree = {
  total: 6,
  taskCount: 2,
  meta: {
    tasks: [
      { taskId: 1042, taskName: '任务A', taskStatus: 'completed' },
      { taskId: 1041, taskName: '任务B', taskStatus: 'failed' },
    ],
    cases: [
      {
        caseId: 'c1',
        caseName: '用例001',
        algorithmType: 'CRM',
        tags: ['拒识', '多轮拒识'],
        groupId: 'g1',
        groupName: '拒识',
        duration: 12.09,
        rounds: 3,
      },
      {
        caseId: 'c2',
        caseName: '用例002',
        algorithmType: 'CRM',
        tags: ['静默拒识'],
        groupId: 'g1',
        groupName: '拒识',
        duration: 3.79,
        rounds: 2,
      },
      {
        caseId: 'c3',
        caseName: '用例003',
        algorithmType: 'CRM',
        tags: [],
        groupId: null,
        groupName: null,
        duration: null,
        rounds: null,
      },
    ],
    devices: [
      { deviceId: 1, deviceName: '设备-01' },
      { deviceId: 2, deviceName: '设备-02' },
    ],
    apis: [],
  },
  tree: [
    {
      taskId: 1042,
      count: 5,
      cases: [
        {
          caseId: 'c1',
          count: 3,
          devices: [
            {
              deviceId: 1,
              apiId: null,
              count: 3,
              resultTypes: [
                { resultType: 'real-time', count: 2, resultIds: [1, 2] },
                { resultType: 'final', count: 1, resultIds: [3] },
              ],
            },
          ],
        },
        {
          caseId: 'c2',
          count: 2,
          devices: [
            {
              deviceId: 1,
              apiId: null,
              count: 2,
              resultTypes: [{ resultType: 'real-time', count: 2, resultIds: [4, 5] }],
            },
          ],
        },
      ],
    },
    {
      taskId: 1041,
      count: 1,
      cases: [
        {
          caseId: 'c3',
          count: 1,
          devices: [
            {
              deviceId: 2,
              apiId: null,
              count: 1,
              resultTypes: [{ resultType: 'real-time', count: 1, resultIds: [6] }],
            },
          ],
        },
      ],
    },
  ],
}

/** 单任务（只选任务A）：任务层省略场景 */
const SINGLE_TASK_TREE: PickCandidateTree = {
  ...TREE,
  total: 5,
  taskCount: 1,
  tree: [TREE.tree[0]],
}

/** 单结果类型（全部 real-time）：result_type 层省略场景（多任务） */
const SINGLE_TYPE_TREE: PickCandidateTree = {
  ...TREE,
  total: 5,
  tree: [
    {
      taskId: 1042,
      count: 4,
      cases: [
        {
          caseId: 'c1',
          count: 2,
          devices: [
            {
              deviceId: 1,
              apiId: null,
              count: 2,
              resultTypes: [{ resultType: 'real-time', count: 2, resultIds: [1, 2] }],
            },
          ],
        },
        {
          caseId: 'c2',
          count: 2,
          devices: [
            {
              deviceId: 1,
              apiId: null,
              count: 2,
              resultTypes: [{ resultType: 'real-time', count: 2, resultIds: [4, 5] }],
            },
          ],
        },
      ],
    },
    {
      taskId: 1041,
      count: 1,
      cases: [
        {
          caseId: 'c3',
          count: 1,
          devices: [
            {
              deviceId: 2,
              apiId: null,
              count: 1,
              resultTypes: [{ resultType: 'real-time', count: 1, resultIds: [6] }],
            },
          ],
        },
      ],
    },
  ],
}

function branch(item: PickTreeItem): PickTreeBranch {
  if (item.kind !== 'branch') throw new Error('期望分支节点')
  return item
}

function childrenOf(node: PickTreeBranch): PickTreeBranch[] {
  return node.children.map(branch)
}

describe('缺值桶与缺名兜底（INT-1824 §8.2.8）', () => {
  it("'default' / 空串 / null 同归「结果类型待补充」", () => {
    expect(isPendingResultType('default')).toBe(true)
    expect(isPendingResultType('')).toBe(true)
    expect(isPendingResultType(null)).toBe(true)
    expect(isPendingResultType('real-time')).toBe(false)
    expect(resultTypeLabel('default')).toBe('结果类型待补充')
    expect(resultTypeLabel('final')).toBe('final')
    expect(PENDING_RESULT_TYPE_VALUE).toBe('default')
  })

  it('用例查不到 / 名字等于 case_id → 「未知用例」（不裸显 UUID）', () => {
    expect(displayCaseName(undefined)).toBe(UNKNOWN_CASE_NAME)
    expect(
      displayCaseName({
        caseId: 'c1',
        caseName: 'c1',
        algorithmType: null,
        tags: [],
        groupId: null,
        groupName: null,
        duration: null,
        rounds: null,
      })
    ).toBe(UNKNOWN_CASE_NAME)
  })

  it('设备软删（device_name=null）→ 「未知设备」', () => {
    expect(displayCaseName(TREE.meta.cases[0])).toBe('用例001')
    expect(displayDeviceName(undefined)).toBe(UNKNOWN_DEVICE_NAME)
    expect(displayDeviceName({ deviceId: 1, deviceName: null })).toBe(UNKNOWN_DEVICE_NAME)
    expect(displayDeviceName({ deviceId: 1, deviceName: '设备-01' })).toBe('设备-01')
  })

  it('buildLeafFilterKey 对同一组合稳定、不同组合相异', () => {
    const a = buildLeafFilterKey({
      taskIds: [1, 2],
      caseIds: ['c1'],
      deviceId: 3,
      apiId: null,
      resultType: 'default',
    })
    const b = buildLeafFilterKey({
      taskIds: [1, 2],
      caseIds: ['c1'],
      deviceId: 3,
      apiId: null,
      resultType: 'default',
    })
    const c = buildLeafFilterKey({
      taskIds: [1],
      caseIds: ['c1'],
      deviceId: 3,
      apiId: null,
      resultType: 'default',
    })
    expect(a).toBe(b)
    expect(a).not.toBe(c)
  })
})

describe('用例视图（用例卡 → 设备/API → result_type → 任务 → 叶）', () => {
  it('顶层用例平铺（首层组织由 PickCaseOrgList 聚合），用例节点携带真名元信息', () => {
    const view = buildPickCaseView(TREE)
    expect(view.map((c) => c.caseId)).toEqual(['c1', 'c2', 'c3'])
    const c1 = view[0]
    expect(c1.level).toBe('case')
    expect(c1.name).toBe('用例001')
    expect(c1.count).toBe(3)
    expect(c1.resultIds).toEqual([1, 2, 3])
    expect(c1.tags).toEqual(['拒识', '多轮拒识'])
    expect(c1.groupName).toBe('拒识')
    expect(c1.algorithmType).toBe('CRM')
    expect(c1.totalDuration).toBe(12.09)
    expect(c1.rounds).toBe(3)
  })

  it('用例 → 设备/API → result_type → 任务 → 叶（多任务时任务在最末一级）', () => {
    const c1 = buildPickCaseView(TREE)[0]
    const device = childrenOf(c1)[0]
    expect(device.level).toBe('device')
    expect(device.name).toBe('设备-01')
    expect(childrenOf(device).map((rt) => rt.name)).toEqual(['real-time', 'final'])

    const rt = childrenOf(device)[0]
    expect(rt.level).toBe('resultType')
    expect(rt.count).toBe(2)
    expect(rt.resultIds).toEqual([1, 2])

    const task = childrenOf(rt)[0]
    expect(task.level).toBe('task')
    expect(task.name).toBe('任务A')
    expect(task.count).toBe(2)
    expect(isLeafParentBranch(task)).toBe(true)
    expect(task.leafFilter).toEqual({
      taskIds: [1042],
      caseIds: ['c1'],
      deviceId: 1,
      apiId: null,
      resultType: 'real-time',
    })
  })

  it('跨任务共享上层节点：任务B 的用例 c3 在任务层才出现', () => {
    const c3 = buildPickCaseView(TREE)[2]
    const device = childrenOf(c3)[0]
    expect(device.name).toBe('设备-02')
    const task = childrenOf(childrenOf(device)[0])[0]
    expect(task.name).toBe('任务B')
    expect(task.leafFilter?.taskIds).toEqual([1041])
  })

  it('单任务：任务层省略，result_type 节点自身即叶的父级（leafFilter 覆盖全部任务）', () => {
    const c1 = buildPickCaseView(SINGLE_TASK_TREE)[0]
    const device = childrenOf(c1)[0]
    const rt = childrenOf(device)[0]
    expect(rt.level).toBe('resultType')
    expect(isLeafParentBranch(rt)).toBe(true)
    expect(rt.leafFilter).toEqual({
      taskIds: [1042],
      caseIds: ['c1'],
      deviceId: 1,
      apiId: null,
      resultType: 'real-time',
    })
  })

  it('单结果类型：result_type 层省略（用例 → 设备 → 任务）', () => {
    const c1 = buildPickCaseView(SINGLE_TYPE_TREE)[0]
    const device = childrenOf(c1)[0]
    expect(childrenOf(device).map((n) => n.level)).toEqual(['task'])
  })

  it('单任务 + 单结果类型：任务层与 result_type 层同时省略（用例 → 设备 → 叶）', () => {
    const single = { ...SINGLE_TASK_TREE, tree: [SINGLE_TYPE_TREE.tree[0]] }
    const c1 = buildPickCaseView(single)[0]
    const device = childrenOf(c1)[0]
    expect(device.level).toBe('device')
    expect(isLeafParentBranch(device)).toBe(true)
    expect(device.leafFilter?.taskIds).toEqual([1042])
    expect(device.leafFilter?.resultType).toBe('real-time')
  })
})

describe('设备视图（设备/API → result_type → 组织层 → 用例卡 → 任务 → 叶）', () => {
  it('result_type 之下是组织层组头，组头下挂用例卡', () => {
    const device = buildPickDeviceView(TREE)[0]
    expect(device.level).toBe('device')
    expect(device.name).toBe('设备-01')
    const rt = childrenOf(device)[0]
    expect(rt.level).toBe('resultType')
    expect(rt.name).toBe('real-time')

    const org = childrenOf(rt)[0]
    expect(org.level).toBe('caseOrg')
    expect(org.orgKind).toBe('group')
    expect(org.name).toBe('拒识')
    expect(org.count).toBe(4)
    expect(org.resultIds.sort()).toEqual([1, 2, 4, 5])

    const caseNode = childrenOf(org)[0]
    expect(caseNode.level).toBe('case')
    expect(caseNode.caseId).toBe('c1')
    const task = childrenOf(caseNode)[0]
    expect(task.level).toBe('task')
    expect(isLeafParentBranch(task)).toBe(true)
    expect(task.leafFilter).toEqual({
      taskIds: [1042],
      caseIds: ['c1'],
      deviceId: 1,
      apiId: null,
      resultType: 'real-time',
    })
  })

  it('单任务：用例卡自身即叶的父级（用例卡 → 叶明细）', () => {
    const rt = childrenOf(buildPickDeviceView(SINGLE_TASK_TREE)[0])[0]
    const caseNode = childrenOf(childrenOf(rt)[0])[0]
    expect(caseNode.level).toBe('case')
    expect(isLeafParentBranch(caseNode)).toBe(true)
    expect(caseNode.leafFilter).toEqual({
      taskIds: [1042],
      caseIds: ['c1'],
      deviceId: 1,
      apiId: null,
      resultType: 'real-time',
    })
  })

  it('单结果类型：设备 → 组织层（result_type 层省略）', () => {
    const device = buildPickDeviceView(SINGLE_TYPE_TREE)[0]
    expect(childrenOf(device).map((n) => n.level)).toEqual(['caseOrg'])
  })

  it('标签视图：按标签聚合，多标签用例在各自组内各出现一次', () => {
    const device = buildPickDeviceView(TREE, 'tag', 'flat')[0]
    const rt = childrenOf(device)[0]
    const orgNames = childrenOf(rt).map((o) => o.name)
    expect(orgNames).toContain('拒识')
    expect(orgNames).toContain('多轮拒识')
  })

  it('交叉子视图：组内再按另一维度分子组', () => {
    const device = buildPickDeviceView(TREE, 'group', 'byTag')[0]
    const org = childrenOf(childrenOf(device)[0])[0]
    const sub = childrenOf(org)
    expect(sub.length).toBeGreaterThan(0)
    expect(sub.every((n) => n.level === 'caseOrg')).toBe(true)
  })
})

describe('结果类型视图（result_type → 设备/API → 组织层 → 用例卡 → 任务 → 叶）', () => {
  it('顶层按 result_type 分组，设备之下是组织层', () => {
    const view = buildPickResultTypeView(TREE)
    expect(view.map((n) => n.name)).toEqual(['real-time', 'final'])
    const rt = view[0]
    expect(rt.count).toBe(5)
    expect(rt.resultIds.sort()).toEqual([1, 2, 4, 5, 6])

    const device = childrenOf(rt)[0]
    expect(device.level).toBe('device')
    expect(device.name).toBe('设备-01')
    const org = childrenOf(device)[0]
    expect(org.level).toBe('caseOrg')
    const caseNode = childrenOf(org)[0]
    expect(caseNode.level).toBe('case')
    expect(childrenOf(caseNode)[0].level).toBe('task')
  })

  it('缺值桶 result_type 显示「结果类型待补充」，叶过滤取 default', () => {
    const pendingTree: PickCandidateTree = {
      ...SINGLE_TASK_TREE,
      tree: [
        {
          taskId: 1042,
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
                  resultTypes: [{ resultType: 'default', count: 1, resultIds: [9] }],
                },
              ],
            },
          ],
        },
      ],
    }
    const rt = buildPickResultTypeView(pendingTree)[0]
    expect(rt.name).toBe('结果类型待补充')
    const caseNode = childrenOf(childrenOf(childrenOf(rt)[0])[0])[0]
    expect(caseNode.level).toBe('case')
    expect(caseNode.leafFilter?.resultType).toBe('default')
  })
})

describe('任务视角树（快捷加购弹窗：任务 → 用例卡 → 设备/API → result_type → 叶）', () => {
  it('任务在第一级，用例节点携带元信息，result_type 节点是叶的父级', () => {
    const tasks = buildPickTaskTree(TREE)
    expect(tasks.map((t) => t.name)).toEqual(['任务A', '任务B'])
    const taskA = tasks[0]
    expect(taskA.level).toBe('task')
    expect(taskA.count).toBe(5)
    const c1 = childrenOf(taskA)[0]
    expect(c1.level).toBe('case')
    expect(c1.caseId).toBe('c1')
    const device = childrenOf(c1)[0]
    const rt = childrenOf(device)[0]
    expect(rt.level).toBe('resultType')
    expect(isLeafParentBranch(rt)).toBe(true)
    expect(rt.leafFilter).toEqual({
      taskIds: [1042],
      caseIds: ['c1'],
      deviceId: 1,
      apiId: null,
      resultType: 'real-time',
    })
  })

  it('空树 → 空视图', () => {
    expect(buildPickTaskTree(undefined)).toEqual([])
    expect(buildPickCaseView(undefined)).toEqual([])
    expect(buildPickDeviceView(undefined)).toEqual([])
    expect(buildPickResultTypeView(undefined)).toEqual([])
  })
})

describe('已选规模统计与反选（不依赖叶明细是否加载）', () => {
  it('按结果归属索引统计结果/任务/设备/用例数', () => {
    const index = buildResultIndex(TREE)
    expect(index.get(1)).toMatchObject({
      taskId: 1042,
      taskName: '任务A',
      caseId: 'c1',
      caseName: '用例001',
      deviceName: '设备-01',
    })
    expect(computeSelectionStatsFromIndex(index, new Set([1, 2, 4, 6]))).toEqual({
      results: 4,
      tasks: 2,
      devices: 2,
      cases: 3,
    })
  })

  it('反选：按树根节点 resultIds 恰好翻转一次（标签视图重复出现不互相抵消）', () => {
    const rt = buildPickDeviceView(TREE, 'tag', 'flat')
    const next = invertVisibleSelection(rt, new Set([1]))
    expect(next.has(1)).toBe(false)
    expect(next.has(6)).toBe(true)
    const back = invertVisibleSelection(rt, next)
    expect(back).toEqual(new Set([1]))
  })
})

describe('结果类型种类判定（<2 种隐藏结果类型视图入口）', () => {
  it('两种 → 有区分度；一种 → 无', () => {
    expect(treeResultTypeVariety(TREE)).toBe(true)
    expect(treeResultTypeVariety(SINGLE_TYPE_TREE)).toBe(false)
    expect(treeResultTypeVariety(undefined)).toBe(false)
  })
})

describe('buildPickTaskView（B 组任务视图：任务首级 + 三子模式）', () => {
  it('任务在第 1 级，子树只含该任务条目（key 带 taskId 命名空间）', () => {
    const branches = buildPickTaskView(TREE)
    expect(branches.map((b) => b.level)).toEqual(['task', 'task'])
    expect(branches[0].key).toBe('ptv-task:1042')
    expect(branches[0].name).toBe('任务A')
    expect(branches[0].count).toBe(5)
    expect(branches[1].resultIds).toEqual([6])
  })

  it('用例子模式：任务 → 用例层组织 → 用例卡 → 设备 → result_type（叶过滤收窄到该任务）', () => {
    const taskA = buildPickTaskView(TREE, 'case')[0]
    const org = taskA.children[0] as PickTreeBranch
    expect(org.level).toBe('caseOrg')
    const caseC1 = org.children.find(
      (c) => c.kind === 'branch' && c.caseId === 'c1'
    ) as PickTreeBranch
    expect(caseC1.level).toBe('case')
    const device = caseC1.children[0] as PickTreeBranch
    expect(device.level).toBe('device')
    expect(device.name).toBe('设备-01')
    const rt = device.children[0] as PickTreeBranch
    expect(rt.level).toBe('resultType')
    expect(rt.name).toBe('real-time')
    expect(rt.leafFilter?.taskIds).toEqual([1042])
    expect(rt.leafFilter?.caseIds).toEqual(['c1'])
  })

  it('设备子模式：任务 → 设备/API → result_type → 组织 → 用例卡（叶父级按任务收窄）', () => {
    const taskA = buildPickTaskView(TREE, 'device')[0]
    const device = taskA.children[0] as PickTreeBranch
    expect(device.level).toBe('device')
    const rt = device.children[0] as PickTreeBranch
    expect(rt.level).toBe('resultType')
    expect(rt.name).toBe('real-time')
    const org = rt.children[0] as PickTreeBranch
    expect(org.level).toBe('caseOrg')
    const caseC1 = org.children[0] as PickTreeBranch
    expect(caseC1.level).toBe('case')
    expect(isLeafParentBranch(caseC1)).toBe(true)
    expect(caseC1.leafFilter?.taskIds).toEqual([1042])
  })

  it('结果类型子模式：任务 → result_type → 设备/API → 组织 → 用例卡', () => {
    const taskA = buildPickTaskView(TREE, 'resultType')[0]
    const rt = taskA.children.find(
      (c) => c.kind === 'branch' && c.level === 'resultType'
    ) as PickTreeBranch
    expect(rt.name).toBe('real-time')
    const device = rt.children[0] as PickTreeBranch
    expect(device.level).toBe('device')
    expect((device.children[0] as PickTreeBranch).level).toBe('caseOrg')
  })
})
