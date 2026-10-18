/**
 * 全局 Agent 工作台浮窗开关 Store（infrastructure/stores 单落位；08_AI对话页 §3.1B）。
 * 浮窗「跨页驻留」：登录壳任意页面可开、切换页面不关闭；开关状态持久化
 * localStorage `iatp:agent-workbench:v1`（跨刷新/路由保持）。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { AGENT_WORKBENCH_STORAGE_KEY } from '../domain/model/aiChat'

interface AgentWorkbenchPrefs {
  open: boolean
  minimized: boolean
}

function loadPrefs(): AgentWorkbenchPrefs {
  try {
    const raw = localStorage.getItem(AGENT_WORKBENCH_STORAGE_KEY)
    if (!raw) return { open: false, minimized: false }
    const parsed = JSON.parse(raw) as Partial<AgentWorkbenchPrefs>
    return {
      open: parsed.open === true,
      minimized: parsed.minimized === true,
    }
  } catch {
    return { open: false, minimized: false }
  }
}

function persist(prefs: AgentWorkbenchPrefs): void {
  try {
    localStorage.setItem(
      AGENT_WORKBENCH_STORAGE_KEY,
      JSON.stringify(prefs)
    )
  } catch {
    // 隐私模式等场景忽略
  }
}

export const useAgentWorkbenchStore = defineStore('agentWorkbench', () => {
  const initial = loadPrefs()
  const open = ref(initial.open)
  const minimized = ref(initial.minimized)

  function setOpen(value: boolean): void {
    open.value = value
    persist({ open: open.value, minimized: minimized.value })
  }

  function toggle(): void {
    setOpen(!open.value)
  }

  function setMinimized(value: boolean): void {
    minimized.value = value
    persist({ open: open.value, minimized: minimized.value })
  }

  return {
    open,
    minimized,
    setOpen,
    toggle,
    setMinimized,
  }
})
