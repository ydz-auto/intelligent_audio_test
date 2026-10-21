/**
 * INT-1110 返工 P1 回归：设备视图 / 结果类型视图叶行层级与去重。
 *
 * 缺陷（审计 01a15ddf 实证）：PickTreeNodeRow 叶行渲染条件
 * `node.level === 'resultType' || ...` 无条件平铺 resultType 节点的 resultIds——
 * 设备/结果类型视图中 resultType 节点携带 case 子级（叶由用例卡内 pt-case-leaves 呈现），
 * 平铺叶行 + 卡内叶行并存 → 同一条结果出现 2 个 checkbox。
 *
 * 修复：叶行仅在「最深分组节点」渲染（`node.level !== 'case' && node.children.length === 0`），
 * 设备/结果类型视图的叶只由用例卡呈现。
 *
 * 本 spec 用多任务多结果数据挂载真实 PickTree，锁死：
 * ① 三视图叶行总数 = 候选结果数（不重复）；
 * ② 设备/结果类型视图所有叶行都在用例卡（.pt-case-leaves）内（层级正确）；
 * ③ 用例视图叶行平铺在 result_type 节点下（无 .pt-case-leaves）。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

// TestCaseCard 会 loadAlgorithms（走 API），桩掉避免真实网络
vi.mock('../../../../composables/algorithm/useAlgorithmLabels', () => ({
  useAlgorithmLabels: () => ({
    loadAlgorithms: () => {},
    getAlgorithmLabel: (t: string) => t,
    algorithmOptions: [],
    algorithms: [],
  }),
}))

import PickTree from '../PickTree.vue'
import {
  buildPickCaseViewTree, buildPickDeviceViewTree, buildPickResultTypeViewTree,
  type PickTreeNode,
} from '../pickTree'
import type { PickCandidate } from '../../../../infrastructure/api/cherryPickApi'

/** 多任务多结果候选（三视图同源：2 任务 / 3 用例 / 3 设备 / 4 结果类型 / 5 结果） */
const CANDIDATES: PickCandidate[] = [
  { resultId: 1, taskId: 1, taskName: '任务1', taskStatus: 'completed', caseId: 'C1', caseName: '用例C1', deviceId: 7, deviceName: '设备7', resultType: 'real-time', executionStatus: 'completed', evaluated: true },
  { resultId: 2, taskId: 1, taskName: '任务1', taskStatus: 'completed', caseId: 'C1', caseName: '用例C1', deviceId: 7, deviceName: '设备7', resultType: 'final', executionStatus: 'completed', evaluated: true },
  { resultId: 3, taskId: 1, taskName: '任务1', taskStatus: 'completed', caseId: 'C2', caseName: '用例C2', deviceId: 8, deviceName: '设备8', resultType: 'default', executionStatus: 'failed', evaluated: false },
  { resultId: 4, taskId: 2, taskName: '任务2', taskStatus: 'completed', caseId: 'C3', caseName: '用例C3', deviceId: 9, deviceName: '设备9', resultType: 'real-time', executionStatus: 'completed', evaluated: true },
  { resultId: 5, taskId: 2, taskName: '任务2', taskStatus: 'completed', caseId: 'C3', caseName: '用例C3', deviceId: 9, deviceName: '设备9', resultType: 'streaming', executionStatus: 'completed', evaluated: true },
]

const EXPECTED_LEAF = 5

/** 全部节点 key 展开（含用例卡 key——设备/结果类型视图叶行在用例卡展开区内；无子级节点也要开） */
function allExpandKeys(roots: PickTreeNode[]): Set<string> {
  const keys = new Set<string>()
  const walk = (nodes: PickTreeNode[]) => {
    for (const n of nodes) {
      keys.add(n.key)
      walk(n.children)
    }
  }
  walk(roots)
  return keys
}

function mountTree(roots: PickTreeNode[]) {
  return mount(PickTree, {
    props: {
      roots,
      selected: new Set<number>(),
      expandedKeys: allExpandKeys(roots),
      alreadyAdded: new Set<number>(),
      leafMeta: new Map(CANDIDATES.map((c) => [c.resultId, c])),
    },
  })
}

describe('PickTree 三视图叶行去重（INT-1110 返工 P1）', () => {
  it('用例视图：5 条结果各渲染 1 条叶行（平铺在 result_type 节点下，无卡内叶）', () => {
    const w = mountTree(buildPickCaseViewTree(CANDIDATES))
    // 用例视图 case 节点恒有子级 → 无 .pt-case-leaves；叶行平铺在 result_type 节点下
    expect(w.findAll('.pt-case-leaves')).toHaveLength(0)
    expect(w.findAll('.pt-leaf')).toHaveLength(EXPECTED_LEAF)
    expect(w.findAll('.pt-leaf input.pt-checkbox')).toHaveLength(EXPECTED_LEAF)
  })

  it('设备视图：叶行只在用例卡内呈现，5 条结果不重复、无 result_type 平铺叶', () => {
    const w = mountTree(buildPickDeviceViewTree(CANDIDATES))
    expect(w.findAll('.pt-leaf')).toHaveLength(EXPECTED_LEAF)
    // 层级正确：全部叶行都在用例卡展开区（.pt-case-leaves）内
    expect(w.findAll('.pt-leaf').every((el) => el.element.closest('.pt-case-leaves') !== null)).toBe(true)
    expect(w.findAll('.pt-case-leaves .pt-leaf input.pt-checkbox')).toHaveLength(EXPECTED_LEAF)
  })

  it('结果类型视图：叶行只在用例卡内呈现，5 条结果不重复、无 result_type 根平铺叶', () => {
    const w = mountTree(buildPickResultTypeViewTree(CANDIDATES))
    expect(w.findAll('.pt-leaf')).toHaveLength(EXPECTED_LEAF)
    expect(w.findAll('.pt-leaf').every((el) => el.element.closest('.pt-case-leaves') !== null)).toBe(true)
    expect(w.findAll('.pt-case-leaves .pt-leaf input.pt-checkbox')).toHaveLength(EXPECTED_LEAF)
  })

  it('设备/结果类型视图不存在卡外平铺叶行（复现审计 P1 的原始断言：同一结果只出现 1 次）', () => {
    for (const roots of [buildPickDeviceViewTree(CANDIDATES), buildPickResultTypeViewTree(CANDIDATES)]) {
      const w = mountTree(roots)
      // 卡外平铺叶（错误层级，审计实证）——修复后应为 0
      const flatOutsideCard = w.findAll('.pt-leaf').filter(
        (el) => el.element.closest('.pt-case-leaves') === null,
      )
      expect(flatOutsideCard).toHaveLength(0)
    }
  })
})
