/**
 * 全局 Agent 工作台「本页 Agent 能力」映射（interfaces 层 features/agent-workbench；
 * 08_AI对话页.md §3.1B 2026-10-17 负责人反馈：**每页 agent 可做的事情不一样**）。
 *
 * 域能力与工具摘要摘录自 doc/agent化/01_功能介绍.md §2.1 能力地图 / §3.x（61 工具分域）；
 * 命中规则：路由前缀最长优先。Demo 态仅展示能力标签与快捷指令（点击回填输入框、
 * 不自动发送、不假接线），真实工具执行待后端立项（红线：不杜撰数据交互面）。
 */

export type PageAgentCapability = {
  /** 路由前缀（pathname 等于或以该前缀开头即命中；同一卡内多个前缀取最长） */
  match: string[]
  /** 页面名（侧栏/顶栏口径，中文） */
  pageLabel: string
  /** 域能力名（01_功能介绍.md §2.1 能力地图，中文） */
  domainLabel: string
  /** 该域 Agent 工具摘要（中文，1-4 项；仅展示用） */
  tools: string[]
  /** 快捷指令（点击回填输入框，不自动发送） */
  quickPrompts: string[]
}

export const PAGE_AGENT_CAPABILITIES: PageAgentCapability[] = [
  {
    match: ['/dashboard'],
    pageLabel: '工作台',
    domainLabel: '系统概览',
    tools: ['首页统计', '统计缓存刷新'],
    quickPrompts: ['汇总平台当前的用例、任务、设备与音频数量', '刷新首页统计数据'],
  },
  {
    match: ['/audio-import'],
    pageLabel: '音频导入',
    domainLabel: '音频导入与标注管理',
    tools: ['URL 导入', '上传+标注', '批量标注', '元数据更新'],
    quickPrompts: ['把这批录音文件导入进来，标注也一起带上', '按标注内容给这批音频分分类'],
  },
  {
    match: ['/testcases'],
    pageLabel: '用例管理',
    domainLabel: '用例生成与编辑 / 标签管理',
    tools: ['用例 CRUD', '轮次编辑', '复制变体', '批量打标'],
    quickPrompts: ['根据这批音频的标注生成测试用例', '给这几个用例打上标签'],
  },
  {
    match: ['/evaluation'],
    pageLabel: '评估维度',
    domainLabel: '评估维度配置',
    tools: ['维度 CRUD', '分类管理', '导入导出', '健康检查'],
    quickPrompts: ['新增一个评估维度', '检查评估维度配置是否健康'],
  },
  {
    match: ['/algorithm-config'],
    pageLabel: '算法配置',
    domainLabel: '算法配置管理',
    tools: ['算法定义', '参数管理', '参考参数', '热重载'],
    quickPrompts: ['从这批音频标注自动提取算法参数', '查看当前算法定义'],
  },
  {
    match: ['/tasks', '/start-test', '/test-execution'],
    pageLabel: '任务域',
    domainLabel: '任务执行与控制',
    tools: ['创建任务', '启动/停止', '失败重试', '结果重提取/重评估'],
    quickPrompts: ['查看当前任务的执行进度', '重跑失败的那几个用例'],
  },
  {
    match: ['/spl-mapping'],
    pageLabel: 'SPL 校准',
    domainLabel: 'SPL 声压级校准',
    tools: ['SPL 映射', '校准执行', '测试音', '校准历史'],
    quickPrompts: ['执行一次 SPL 校准', '查看最近的校准历史'],
  },
  {
    match: ['/devices'],
    pageLabel: '设备管理',
    domainLabel: '播放设备管理 / 设备驱动生成',
    tools: ['设备扫描', '设备测试', '状态检查', '驱动生成'],
    quickPrompts: ['扫描当前可用的播放设备', '测试这台播放设备的状态'],
  },
  {
    match: ['/logs'],
    pageLabel: '日志诊断',
    domainLabel: '日志诊断',
    tools: ['日志搜索', '失败诊断', '日志导出', '归档'],
    quickPrompts: ['搜索最近一次任务的错误日志', '帮我分析这批日志的失败原因'],
  },
  {
    match: [
      '/report-center',
      '/report-statistics',
      '/reports',
      '/history-reports',
      '/test-reports',
      '/report/',
      '/rankings',
    ],
    pageLabel: '报告域',
    domainLabel: '结果分析与报告 / 报告对比',
    tools: ['结果获取', '报告生成/对比', '趋势解读', '导出'],
    quickPrompts: ['解读这份报告的核心指标，指出异常项', '对比最近两次测试的报告，找出差异和退步项'],
  },
  {
    match: ['/system-settings'],
    pageLabel: '系统设置',
    domainLabel: '系统配置域',
    tools: ['用户与角色', 'OAuth 提供方', '日志运维'],
    quickPrompts: ['看看当前有哪些系统配置项', '查一下用户与角色配置'],
  },
  {
    // /ai-chat 整页即灵犀Agent 本体：浮窗与整页共享同一会话，能力即报告三件
    match: ['/ai-chat'],
    pageLabel: '灵犀Agent',
    domainLabel: '报告生成 / 对比 / 分析',
    tools: ['报告生成', '报告对比', '报告分析'],
    quickPrompts: ['帮我把最近的测试任务生成一份测试报告', '对比最近两次测试的报告，找出差异和退步项'],
  },
]

/** 命中当前路径的本页 Agent 能力（路由前缀最长优先；无命中返回 null——登录壳兜底不展示专页能力） */
export function getPageAgentCapability(
  pathname: string
): PageAgentCapability | null {
  let best: PageAgentCapability | null = null
  let bestLen = -1
  for (const cap of PAGE_AGENT_CAPABILITIES) {
    for (const prefix of cap.match) {
      if (pathname.startsWith(prefix) && prefix.length > bestLen) {
        best = cap
        bestLen = prefix.length
      }
    }
  }
  return best
}
