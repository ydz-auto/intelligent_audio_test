/**
 * 全局 Agent 工作台「本页 Agent 能力」映射（application 层 composable；
 * 08_AI对话页.md §3.1B 2026-10-17 负责人口径：**每页 agent 可做的事不一样**，
 * 照 React page-agent-capabilities.ts 平移）。
 *
 * 命中规则：路由前缀最长优先；无命中返回 null（登录壳兜底不展示专页能力）。
 * 域能力/快捷指令与空态全能力分组（CAPABILITY_GROUPS §3.3 区二）同源，
 * /ai-chat=全能力（61 工具 / 11 域分组，2026-10-17 08:06 负责人口径：主工作台主推全部能力）。
 * 点击快捷指令仅回填输入框、不自动发送、不假接线（红线）。
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  CAPABILITY_GROUPS,
  type CapabilityGroup,
} from '../../domain/constants/aiChat'

export interface PageAgentCapability {
  /** 页面名（侧栏/顶栏口径，中文） */
  pageLabel: string
  /** 域能力名（01_功能介绍.md §2.2，中文） */
  domainLabel: string
  /** 工具数（§2.2 实测；null=配置域不在 61 工具清单，Agent 化待后端立项） */
  toolCount: number | null
  /** 快捷指令（点击回填输入框，不自动发送；无码域为空） */
  quickPrompts: string[]
  /** 是否可执行（无码域统一标「待接入」，可显不可执行） */
  executable: boolean
}

/** 路由前缀 → 全能力分组（§3.1B 映射；与 00 总表路由落点一致） */
const PAGE_AGENT_MATCHES: Array<{ match: string[]; group: CapabilityGroup }> = [
  { match: ['/dashboard'], group: CAPABILITY_GROUPS.find((g) => g.key === 'dashboard')! },
  { match: ['/audio-import'], group: CAPABILITY_GROUPS.find((g) => g.key === 'audio')! },
  { match: ['/testcases'], group: CAPABILITY_GROUPS.find((g) => g.key === 'testcase')! },
  { match: ['/evaluation'], group: CAPABILITY_GROUPS.find((g) => g.key === 'evaluation')! },
  { match: ['/AlgorithmConfig'], group: CAPABILITY_GROUPS.find((g) => g.key === 'algorithm')! },
  { match: ['/tasks', '/start-test'], group: CAPABILITY_GROUPS.find((g) => g.key === 'task')! },
  { match: ['/SPLMapping'], group: CAPABILITY_GROUPS.find((g) => g.key === 'spl')! },
  { match: ['/devices'], group: CAPABILITY_GROUPS.find((g) => g.key === 'device')! },
  { match: ['/logs'], group: CAPABILITY_GROUPS.find((g) => g.key === 'log')! },
  {
    match: ['/report-center', '/report-statistics', '/reports', '/report'],
    group: CAPABILITY_GROUPS.find((g) => g.key === 'report')!,
  },
  { match: ['/system-settings'], group: CAPABILITY_GROUPS.find((g) => g.key === 'system-settings')! },
]

/** 命中当前路径的本页 Agent 能力（路由前缀最长优先；无命中返回 null） */
export function getPageAgentCapability(
  pathname: string
): PageAgentCapability | null {
  // /ai-chat 整页即灵犀Agent 本体：主推全部能力（61 工具 / 11 域分组，
  // 2026-10-17 08:06 负责人口径：主工作台主推全部能力、不只报告三件）
  if (pathname.startsWith('/ai-chat')) {
    const allPrompts = CAPABILITY_GROUPS
      .map((g) => g.prompt)
      .filter((p): p is string => Boolean(p))
    return {
      pageLabel: '灵犀Agent',
      domainLabel: '全能力（61 工具 / 11 域分组）',
      toolCount: 61,
      quickPrompts: allPrompts,
      executable: true,
    }
  }
  let best: PageAgentCapability | null = null
  let bestLen = -1
  for (const { match, group } of PAGE_AGENT_MATCHES) {
    for (const prefix of match) {
      if (pathname.startsWith(prefix) && prefix.length > bestLen) {
        best = {
          pageLabel: group.label,
          domainLabel: group.domainLabel,
          toolCount: group.toolCount,
          quickPrompts: group.prompt ? [group.prompt] : [],
          executable: group.prompt !== null,
        }
        bestLen = prefix.length
      }
    }
  }
  return best
}

/** 当前路由的本页 Agent 能力（hash 路由下 path 不含 #/ 前缀） */
export function usePageAgentCapability() {
  const route = useRoute()
  const capability = computed(() =>
    getPageAgentCapability(route.path)
  )
  return { capability }
}
