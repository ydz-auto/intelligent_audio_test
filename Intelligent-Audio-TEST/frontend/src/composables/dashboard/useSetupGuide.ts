// -*- coding: utf-8 -*-
/**
 * 开始使用引导卡逻辑（INT-736 / React 04_控制台 §3.5）
 *
 * 四步完成度探针全部来自 /home/stats/details 实测字段（camelCase 域模型），
 * 不新增接口；localStorage `iatp:dashboard:v1:setup-guide` 持久化展开/折叠。
 */
import { computed, ref } from 'vue'
import type { HomeStatsDetails } from '../../domain/model/stats'

const STORAGE_KEY = 'iatp:dashboard:v1:setup-guide'

export interface SetupStep {
  key: 'cases' | 'devices' | 'tasks' | 'reports'
  label: string
  desc: string
  icon: string
}

export const SETUP_STEPS: SetupStep[] = [
  { key: 'cases', label: '配置用例', desc: '创建或导入测试用例', icon: 'fa-list-check' },
  { key: 'devices', label: '连接设备', desc: '接入真机或播放设备', icon: 'fa-headphones' },
  { key: 'tasks', label: '执行任务', desc: '发起端到端 / API 测试', icon: 'fa-play' },
  { key: 'reports', label: '查看报告', desc: '分析评估结果', icon: 'fa-file-alt' },
]

export function useSetupGuide(details: () => HomeStatsDetails | null) {
  /** null = 跟随完成度默认（未全部完成展开）；true/false = 用户手动展开/折叠 */
  const manualExpanded = ref<boolean | null>(null)

  const stepCompleted = computed(() => {
    const d = details()
    return (key: string): boolean => {
      if (!d) return false
      switch (key) {
        case 'cases': return (d.testCases?.total ?? 0) > 0
        case 'devices': return (d.devices?.online ?? 0) > 0
        case 'tasks': return (d.tasks?.total ?? 0) > 0
        case 'reports': return (d.reports ?? 0) > 0
        default: return false
      }
    }
  })

  const completedCount = computed(() => SETUP_STEPS.filter(s => stepCompleted.value(s.key)).length)
  const setupComplete = computed(() => completedCount.value >= SETUP_STEPS.length)

  const expanded = computed<boolean>({
    get: () => manualExpanded.value ?? !setupComplete.value,
    set: (v: boolean) => {
      manualExpanded.value = v
      localStorage.setItem(STORAGE_KEY, v ? 'expanded' : 'collapsed')
    },
  })

  /** 初始化：读取 localStorage 持久化展开态 */
  function init() {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'expanded') manualExpanded.value = true
    else if (stored === 'collapsed') manualExpanded.value = false
    else manualExpanded.value = null
  }

  return {
    steps: SETUP_STEPS,
    stepCompleted,
    completedCount,
    setupComplete,
    expanded,
    init,
  }
}
