/**
 * 本页 Agent 能力映射纯函数测试（interfaces 层 features/agent-workbench；
 * §3.1B 2026-10-17 口径：每页 agent 可做的事不同，路由前缀最长优先命中）。
 */
import { describe, expect, it } from 'vitest'

import {
  getPageAgentCapability,
  PAGE_AGENT_CAPABILITIES,
} from '../page-agent-capabilities'

describe('getPageAgentCapability', () => {
  it('工作台 → 系统概览', () => {
    expect(getPageAgentCapability('/dashboard')?.domainLabel).toBe('系统概览')
  })

  it('用例管理 → 用例生成与编辑 / 标签管理', () => {
    expect(getPageAgentCapability('/testcases')?.domainLabel).toBe(
      '用例生成与编辑 / 标签管理'
    )
  })

  it('报告域各路由 → 结果分析与报告（长前缀优先，/report/ 与 /report-center 不串）', () => {
    expect(getPageAgentCapability('/report-center')?.pageLabel).toBe('报告域')
    expect(getPageAgentCapability('/reports')?.pageLabel).toBe('报告域')
    expect(getPageAgentCapability('/report/1201')?.pageLabel).toBe('报告域')
    expect(getPageAgentCapability('/report-statistics')?.pageLabel).toBe('报告域')
  })

  it('/ai-chat → 灵犀Agent（整页即本体，报告三件）', () => {
    const cap = getPageAgentCapability('/ai-chat')
    expect(cap?.pageLabel).toBe('灵犀Agent')
    expect(cap?.tools).toEqual(['报告生成', '报告对比', '报告分析'])
  })

  it('带子路径命中设备域', () => {
    expect(getPageAgentCapability('/devices/players')?.domainLabel).toBe(
      '播放设备管理 / 设备驱动生成'
    )
  })

  it('登录壳兜底未命中 → null（不渲染专页能力条）', () => {
    expect(getPageAgentCapability('/not-a-real-route')).toBeNull()
  })

  it('映射表每项均有中文文案与快捷指令', () => {
    for (const cap of PAGE_AGENT_CAPABILITIES) {
      expect(cap.match.length).toBeGreaterThan(0)
      expect(cap.pageLabel.length).toBeGreaterThan(0)
      expect(cap.domainLabel.length).toBeGreaterThan(0)
      expect(cap.tools.length).toBeGreaterThan(0)
      expect(cap.quickPrompts.length).toBeGreaterThan(0)
      // 快捷指令为自然语言指令（至少一个中文字符），且不自动发送语义（只回填）
      for (const prompt of cap.quickPrompts) {
        expect(prompt).toMatch(/[一-龥]/)
      }
    }
  })
})
