/**
 * agentWorkbenchStore 单测（INT-598 §3.1B/§7）：浮窗开关 store 单落位
 * infrastructure/stores/agentWorkbenchStore.ts——open/minimized 状态、
 * toggle/setMinimized/expandToFullPage 行为与 localStorage iatp:agent-workbench:v1 持久化。
 */
import { beforeEach, describe, expect, it } from 'vitest'

import { useAgentWorkbench } from '@/infrastructure/stores/agentWorkbenchStore'

describe('useAgentWorkbench', () => {
  beforeEach(() => {
    window.localStorage.clear()
    useAgentWorkbench.setState({ open: false, minimized: false })
  })

  it('初始态关闭、未最小化', () => {
    expect(useAgentWorkbench.getState().open).toBe(false)
    expect(useAgentWorkbench.getState().minimized).toBe(false)
  })

  it('toggle 打开浮窗并重置最小化', () => {
    useAgentWorkbench.getState().setMinimized(true)
    useAgentWorkbench.getState().toggle()
    expect(useAgentWorkbench.getState().open).toBe(true)
    expect(useAgentWorkbench.getState().minimized).toBe(false)
  })

  it('最小化只置 minimized，不关浮窗', () => {
    useAgentWorkbench.setState({ open: true })
    useAgentWorkbench.getState().setMinimized(true)
    expect(useAgentWorkbench.getState().open).toBe(true)
    expect(useAgentWorkbench.getState().minimized).toBe(true)
  })

  it('expandToFullPage 关闭浮窗并重置最小化（展开整页语义）', () => {
    useAgentWorkbench.setState({ open: true, minimized: false })
    useAgentWorkbench.getState().expandToFullPage()
    expect(useAgentWorkbench.getState().open).toBe(false)
    expect(useAgentWorkbench.getState().minimized).toBe(false)
  })

  it('persist 写入 localStorage iatp:agent-workbench:v1', () => {
    useAgentWorkbench.getState().setOpen(true)
    const raw = window.localStorage.getItem('iatp:agent-workbench:v1')
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw ?? '{}') as { state?: { open?: boolean } }
    expect(parsed.state?.open).toBe(true)
  })
})
