/**
 * Auto 进度归约单测（INT-2474 §9.4）。
 * 关注点：五维预算水位换算、最高比例、暂停原因文案、终态分类
 * （超预算 / 熔断不得展示成成功）。
 */
import { describe, expect, it } from 'vitest'

import {
  AGENT_RUN_PAUSE_REASON,
  AGENT_RUN_STATUS,
  type AgentAutoProgress,
  type AgentRun,
} from '@/domain/models/agent'
import {
  AUTO_TERMINAL_KIND,
  autoBudgetRows,
  autoMaxRatio,
  autoPhaseText,
  autoTerminalCopy,
  autoTerminalKind,
  formatAutoUsageSummary,
  formatElapsed,
  formatPercent,
  pauseReasonText,
  toMegabytes,
  toMinutes,
} from '@/application/agent/auto-progress'

function progress(overrides: Partial<AgentAutoProgress> = {}): AgentAutoProgress {
  return {
    step: 2,
    usage: {
      rounds: 3,
      toolCalls: 6,
      tokens: 1000,
      elapsedSeconds: 90,
      outputBytes: 2 * 1024 * 1024,
    },
    limits: {
      maxRounds: 60,
      maxToolCalls: 120,
      maxTokens: 2000,
      maxDurationSeconds: 1800,
      maxOutputBytes: 20 * 1024 * 1024,
    },
    ratio: 0.5,
    consecutiveFailures: 0,
    artifactCount: 0,
    artifacts: [],
    ...overrides,
  }
}

function run(overrides: Partial<AgentRun> = {}): AgentRun {
  return {
    id: 'r-1',
    sessionId: 's-1',
    status: AGENT_RUN_STATUS.RUNNING,
    mode: 'auto',
    ...overrides,
  }
}

describe('单位换算', () => {
  it('秒 → 分钟、字节 → MB 保留一位小数', () => {
    expect(toMinutes(90)).toBe(1.5)
    expect(toMinutes(1800)).toBe(30)
    expect(toMegabytes(1536 * 1024)).toBe(1.5)
    expect(formatPercent(0.8123)).toBe('81%')
    expect(formatElapsed(61)).toBe('1 分 1 秒')
    expect(formatElapsed(30)).toBe('30 秒')
  })
})

describe('autoBudgetRows', () => {
  it('五维顺序固定，limit ≤0 / 缺省的维度不参与比例', () => {
    const rows = autoBudgetRows(progress().usage, {
      maxRounds: 60,
      maxToolCalls: 0,
      maxTokens: undefined,
      maxDurationSeconds: 1800,
      maxOutputBytes: 20 * 1024 * 1024,
    })
    expect(rows.map((row) => row.dimension)).toEqual([
      'maxRounds',
      'maxToolCalls',
      'maxTokens',
      'maxDurationSeconds',
      'maxOutputBytes',
    ])
    expect(rows[0]).toMatchObject({ used: 3, limit: 60, ratio: 0.05 })
    expect(rows[1].limit).toBeUndefined()
    expect(rows[1].ratio).toBeUndefined()
    expect(rows[1].text).toBe('6 次')
    expect(rows[2].limit).toBeUndefined()
    // 时长 / 输出按分钟 / MB 展示
    expect(rows[3].text).toBe('1.5 / 30 分钟')
    expect(rows[4].text).toBe('2 / 20 MB')
  })

  it('最高比例优先取服务端 ratio，缺失时按行计算', () => {
    expect(autoMaxRatio(progress({ ratio: 0.42 }))).toBe(0.42)
    const fallback = autoMaxRatio(
      progress({ ratio: 0, limits: { maxRounds: 6, maxToolCalls: 12 } })
    )
    // 轮次 3/6 = 0.5 最高
    expect(fallback).toBeCloseTo(0.5)
    expect(autoMaxRatio(null)).toBe(0)
  })

  it('摘要只列前两个已启用维度 + 总比例', () => {
    expect(formatAutoUsageSummary(progress({ ratio: 0.5 }))).toBe(
      '轮次 3 / 60 轮 · 工具调用 6 / 120 次 · 已用 50%'
    )
  })
})

describe('暂停原因文案', () => {
  it('预算阈值 / 连续失败分别给明确说明', () => {
    expect(pauseReasonText(AGENT_RUN_PAUSE_REASON.BUDGET_THRESHOLD)).toContain(
      '预算'
    )
    expect(
      pauseReasonText(AGENT_RUN_PAUSE_REASON.CONSECUTIVE_TOOL_FAILURES, 2)
    ).toBe('连续 2 次工具失败，已暂停自动重试')
    expect(pauseReasonText(undefined)).toContain('已暂停')
  })
})

describe('终态分类（不把超预算 / 熔断展示成成功）', () => {
  it('SUCCEEDED → 成功；BUDGET_EXCEEDED → 超预算', () => {
    expect(autoTerminalKind(run({ status: AGENT_RUN_STATUS.SUCCEEDED }))).toBe(
      AUTO_TERMINAL_KIND.SUCCEEDED
    )
    expect(
      autoTerminalKind(run({ status: AGENT_RUN_STATUS.BUDGET_EXCEEDED }))
    ).toBe(AUTO_TERMINAL_KIND.BUDGET_EXCEEDED)
    expect(
      autoTerminalCopy(autoTerminalKind(run({ status: AGENT_RUN_STATUS.BUDGET_EXCEEDED })))
    ).toMatchObject({ title: 'Auto 超出预算已停止' })
  })

  it('FAILED + CONSECUTIVE_TOOL_FAILURES → 熔断（不是普通失败）', () => {
    const kind = autoTerminalKind(
      run({
        status: AGENT_RUN_STATUS.FAILED,
        error: 'CONSECUTIVE_TOOL_FAILURES',
      })
    )
    expect(kind).toBe(AUTO_TERMINAL_KIND.CIRCUIT_BREAK)
    expect(autoTerminalCopy(kind)?.title).toBe('Auto 已熔断停止')
  })

  it('其他 FAILED 仍是失败；CANCELLED 是已结束；进行中返回 null', () => {
    expect(
      autoTerminalKind(run({ status: AGENT_RUN_STATUS.FAILED, error: 'LLM_ERROR' }))
    ).toBe(AUTO_TERMINAL_KIND.FAILED)
    expect(autoTerminalKind(run({ status: AGENT_RUN_STATUS.CANCELLED }))).toBe(
      AUTO_TERMINAL_KIND.CANCELLED
    )
    expect(autoTerminalKind(run({ status: AGENT_RUN_STATUS.RUNNING }))).toBeNull()
    expect(autoTerminalCopy(null)).toBeNull()
  })
})

describe('autoPhaseText', () => {
  it('phase 对应中文阶段', () => {
    expect(autoPhaseText(progress({ phase: 'resume' }))).toBe('已确认继续')
    expect(autoPhaseText(progress({ phase: 'continue' }))).toBe('续跑中')
    expect(autoPhaseText(progress({ phase: 'step' }))).toBe('执行中')
  })
})
