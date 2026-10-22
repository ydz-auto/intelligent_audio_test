/**
 * 开始使用引导卡状态（application 层，纯逻辑可单测）。
 * 四步完成度探针全部来自 /home/stats/details 实测字段（不新增接口，04_控制台.md §3.4）；
 * 展开/折叠 localStorage 持久化（iatp:dashboard:v1:setup-guide），
 * 默认「未全部完成则展开」（manualExpanded ?? !setupComplete，对齐 newAPI）。
 */
import {
  FileBarChart,
  Headphones,
  ListChecks,
  Play,
  type LucideIcon,
} from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'

import type { HomeStatsDetails } from '@/domain/models/home'

const SETUP_GUIDE_STORAGE_KEY = 'iatp:dashboard:v1:setup-guide'

export interface SetupStep {
  key: string
  title: string
  description: string
  icon: LucideIcon
  completed: boolean
}

function readSavedExpanded(): boolean | null {
  if (typeof window === 'undefined') return null
  const saved = window.localStorage.getItem(SETUP_GUIDE_STORAGE_KEY)
  if (saved === 'expanded') return true
  if (saved === 'collapsed') return false
  return null
}

function saveExpanded(expanded: boolean): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(
    SETUP_GUIDE_STORAGE_KEY,
    expanded ? 'expanded' : 'collapsed'
  )
}

export function useSetupGuide(details?: HomeStatsDetails) {
  const [manualExpanded, setManualExpanded] = useState<boolean | null>(() =>
    readSavedExpanded()
  )

  const steps = useMemo<SetupStep[]>(
    () => [
      {
        key: 'testcases',
        title: '配置用例',
        description: '创建或导入测试用例',
        icon: ListChecks,
        completed: (details?.testCases.total ?? 0) > 0,
      },
      {
        key: 'devices',
        title: '连接设备',
        description: '接入真机或播放设备',
        icon: Headphones,
        completed: (details?.devices.online ?? 0) > 0,
      },
      {
        key: 'tasks',
        title: '执行任务',
        description: '发起语音测试任务',
        icon: Play,
        completed: (details?.tasks.total ?? 0) > 0,
      },
      {
        key: 'reports',
        title: '查看报告',
        description: '分析评估结果',
        icon: FileBarChart,
        completed: (details?.reports ?? 0) > 0,
      },
    ],
    [details]
  )

  const completedCount = steps.filter((step) => step.completed).length
  const setupComplete = completedCount === steps.length
  const expanded = manualExpanded ?? !setupComplete

  const toggle = useCallback(() => {
    setManualExpanded((prev) => {
      const next = !(prev ?? !setupComplete)
      saveExpanded(next)
      return next
    })
  }, [setupComplete])

  return { steps, completedCount, setupComplete, expanded, toggle }
}
