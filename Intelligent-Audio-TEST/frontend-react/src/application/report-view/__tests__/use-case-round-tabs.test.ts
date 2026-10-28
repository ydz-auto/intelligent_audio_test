/**
 * 用例卡轮次轴单测（15_报告域.md §3.3.7「轮次轴 = Tab」，INT-1774）。
 * 覆盖：候选 Tab 装配（整体仅有 @overall 数据才出现 / chips 收窄）、默认激活轮次、
 * 单轮用例不产 Tab 且按基础维度键取值、chips 全清「未选择轮次」、chips 只勾 1 个的取值口径。
 * 原 `report-case-view-model.test.ts` 的 `defaultLeafRounds` 断言迁到这里（列集已无默认轮次口径）。
 */
import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ReportCaseItem } from '@/domain/models/report'

import {
  buildCandidateRoundTabs,
  defaultActiveRoundTag,
  useCaseRoundTabs,
} from '../use-case-round-tabs'

/** 用例项夹具：一行 = 一个资源，metrics 为后端实测的 list 格式 */
function caseWith(metricNames: string[], resource = 'r1'): ReportCaseItem {
  return {
    id: 'c1',
    name: '用例',
    metrics: [
      {
        resource,
        metrics: metricNames.map((metric) => ({ metric, value: 1, round_number: null })),
      },
    ],
  } as unknown as ReportCaseItem
}

describe('候选轮次 Tab（chips 已选 ∩ 本用例有数据的轮次）', () => {
  it('多轮用例按轮次升序、「整体」末位', () => {
    const tabs = buildCandidateRoundTabs(
      ['A@overall', 'A@round:2', 'A@round:1'],
      []
    )
    expect(tabs.map((t) => t.roundTag)).toEqual(['round:1', 'round:2', 'overall'])
    expect(tabs.map((t) => t.label)).toEqual(['第 1 轮', '第 2 轮', '整体'])
  })

  it('无 @overall 评估数据时不出「整体」Tab', () => {
    const tabs = buildCandidateRoundTabs(['A@round:1', 'A@round:2'], [])
    expect(tabs.map((t) => t.roundTag)).toEqual(['round:1', 'round:2'])
  })

  it('单轮用例（指标键无轮次后缀）不产 Tab', () => {
    expect(buildCandidateRoundTabs(['A', 'B'], [])).toEqual([])
  })

  it('轮次标记来自执行结果 / 参考 / 用例参数字段时也计入候选', () => {
    const tabs = buildCandidateRoundTabs(['A@round:1'], [
      { paramCode: 'transcript@round:2' },
      { paramCode: 'ref', roundNumber: 3 },
    ])
    expect(tabs.map((t) => t.roundTag)).toEqual(['round:1', 'round:2', 'round:3'])
  })

  it('chips 收窄后候选随之减少', () => {
    const tabs = buildCandidateRoundTabs(
      ['A@overall', 'A@round:1', 'A@round:2'],
      [],
      ['round:2']
    )
    expect(tabs.map((t) => t.roundTag)).toEqual(['round:2'])
  })
})

describe('默认激活轮次（有整体取整体，否则首个有数据轮次）', () => {
  it('有 @overall 取「整体」', () => {
    const tabs = buildCandidateRoundTabs(['A@overall', 'A@round:1'], [])
    expect(defaultActiveRoundTag(tabs)).toBe('overall')
  })

  it('无整体取首个有数据轮次', () => {
    const tabs = buildCandidateRoundTabs(['A@round:2', 'A@round:1'], [])
    expect(defaultActiveRoundTag(tabs)).toBe('round:1')
  })

  it('无轮次不产 Tab（返回 null）', () => {
    expect(defaultActiveRoundTag(buildCandidateRoundTabs(['A'], []))).toBeNull()
  })
})

describe('一张卡一个轮次轴（useCaseRoundTabs）', () => {
  it('多轮用例：默认激活「整体」，切 Tab 只换当前轮次标记', () => {
    const { result } = renderHook(() =>
      useCaseRoundTabs(caseWith(['A@overall', 'A@round:1', 'A@round:2']), ['round:1', 'round:2', 'overall'], false)
    )
    expect(result.current.roundTabs.map((t) => t.label)).toEqual(['第 1 轮', '第 2 轮', '整体'])
    expect(result.current.activeRoundTab).toBe('整体')
    expect(result.current.activeRoundTag).toBe('overall')
    expect(result.current.noRoundSelected).toBe(false)
  })

  it('chips 只勾 1 个：Tab 栏不渲染，取值仍用该唯一轮次后缀（不回退基础维度键）', () => {
    const { result } = renderHook(() =>
      useCaseRoundTabs(caseWith(['A@overall', 'A@round:1', 'A@round:2']), ['round:1'], false)
    )
    expect(result.current.roundTabs).toEqual([])
    expect(result.current.activeRoundTag).toBe('round:1')
  })

  it('chips 全清：无 Tab、标记为 null、noRoundSelected = true', () => {
    const { result } = renderHook(() =>
      useCaseRoundTabs(caseWith(['A@overall', 'A@round:1', 'A@round:2']), [], true)
    )
    expect(result.current.roundTabs).toEqual([])
    expect(result.current.activeRoundTag).toBeNull()
    expect(result.current.noRoundSelected).toBe(true)
  })

  it('单轮用例（指标键无轮次后缀）：不产 Tab、按基础维度键取值、空 chips 不算「全清」', () => {
    const { result } = renderHook(() => useCaseRoundTabs(caseWith(['A', 'B']), [], false))
    expect(result.current.roundTabs).toEqual([])
    expect(result.current.activeRoundTag).toBeNull()
    expect(result.current.noRoundSelected).toBe(false)
    expect(result.current.currentRoundMetricKeys).toEqual(['A', 'B'])
  })

  it('单轮用例即便参考字段带轮次标记，也不按轮次后缀取指标值', () => {
    const item = caseWith(['A', 'B'])
    item.algorithmResults = [{ paramCode: 'query@round:1', roundNumber: 1 }]
    const { result } = renderHook(() => useCaseRoundTabs(item))
    expect(result.current.activeRoundTag).toBeNull()
  })

  it('首个轮次只有执行结果、没有指标数据时，默认激活首个有指标数据的轮次（V9.7.10 tabHasMetricData）', () => {
    // 报告 417 真实形态：指标只落在 @round:2，@round:1 只出现在结果字段
    const item = caseWith(['A@round:2'])
    item.algorithmResults = [{ paramCode: 'query@round:1', roundNumber: 1 }]
    const { result } = renderHook(() => useCaseRoundTabs(item))
    expect(result.current.roundTabs.map((t) => t.label)).toEqual(['第 1 轮', '第 2 轮'])
    expect(result.current.activeRoundTag).toBe('round:2')
    expect(result.current.currentRoundMetricKeys).toEqual(['A@round:2'])
  })
})
