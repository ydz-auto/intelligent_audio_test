import {
  ArrowLeftRight,
  ClipboardList,
  DatabaseZap,
  FileBarChart,
  Gauge,
  Headphones,
  Layers,
  ListChecks,
  Music,
  ShieldCheck,
  Smartphone,
  Star,
  Users,
  type LucideIcon,
} from 'lucide-react'

/**
 * 首页文案与 mock 常量（03_首页.md §6 中文全量；红线④）。
 */

export const HOME_BRAND_NAME = '智能语音测试平台'

/** ① 品牌区 */
export const HERO = {
  badge: '端到端测试 · API 测试 · 多维评估',
  titleLine1: '智能语音测试平台',
  titleLine2: '让每一次语音交互都可度量',
  // 负责人 2026-10-16 定稿：highlight 并入多友商横向对比核心价值（多友商同集同指标同时实测）
  highlight: '真实设备、真实链路、真实指标，多友商横向对比，看清真实用户体验。',
  description:
    '面向语音团队的端到端测试与 API 测试解决方案：多设备并行执行、自动化任务调度、多维度评估与可视化报告，一个平台全部完成。',
  primaryAction: '立即开始测试',
  primaryActionAuthed: '进入工作台',
  secondaryAction: '查看文档',
  checks: [
    '多设备并行测试',
    '实时进度推送',
    '自动化评估引擎',
    '可视化对比报告',
    '细粒度权限控制',
  ],
  orbitCaption: '一个平台，覆盖语音测试全流程',
  brandRow: ['Android 真机', '鸿蒙设备', '语音 API', '自动评估'],
  brandRowLink: '选择你的测试类型',
} as const

/** 枢纽图四节点（四色取图表色板 chart-1~4，只上图标色） */
export const ORBIT_NODES: {
  name: string
  icon: LucideIcon
  color: string
  position: string
}[] = [
  {
    name: '端到端测试',
    icon: Smartphone,
    color: 'text-chart-1',
    position: 'top-8 left-0 sm:left-4',
  },
  {
    name: 'API 测试',
    icon: ArrowLeftRight,
    color: 'text-chart-2',
    position: 'top-14 right-0 sm:right-4',
  },
  {
    name: '设备集群',
    icon: Headphones,
    color: 'text-chart-3',
    position: 'bottom-14 left-0 sm:left-4',
  },
  {
    name: '报告分析',
    icon: FileBarChart,
    color: 'text-chart-4',
    position: 'bottom-8 right-0 sm:right-4',
  },
]

/** 卖点四卡 */
export const HERO_BENEFITS: {
  icon: LucideIcon
  title: string
  description: string
}[] = [
  {
    icon: Layers,
    title: '多设备并行',
    description: '真机集群同时跑同一套用例',
  },
  {
    icon: ShieldCheck,
    title: '任务稳定调度',
    description: '异步执行 + 失败重试 + 断点恢复',
  },
  {
    icon: Star,
    title: '多维自动评估',
    description: '准确率、召回率、F1、流畅度一次算全',
  },
  {
    icon: FileBarChart,
    title: '报告开箱即用',
    description: '单任务详情 + 跨任务对比 + 多格式导出',
  },
]

/** 平台规模条（数据形态对照 HomeStatsDetails；未登录整条替换为登录引导） */
export const STATS_BAR = {
  label: '平台规模',
  anonymousText: '登录后可查看平台实时规模',
  anonymousAction: '登录',
} as const

/** ② 从这里开始 */
export const QUICK_START = {
  eyebrow: '01 / 开始测试',
  heading: '五步跑通一次语音测试。',
  subtext:
    '从选择算法到查看报告，平台把流程拆成五步——每一步都有页面承接。',
  algorithmNote: '全局算法可在导航栏右上角一次切换',
  steps: [
    { name: '选择算法', description: '配置测试算法参数' },
    { name: '选择用例', description: '创建或选择测试用例' },
    { name: '选择设备', description: '配置测试设备参数' },
    { name: '执行测试', description: '运行语音测试流程' },
    { name: '查看结果', description: '分析测试评估报告' },
  ],
  cards: [
    {
      key: 'e2e',
      icon: Smartphone,
      color: 'bg-primary/10 text-primary',
      title: '端到端测试',
      description:
        '在真实设备上执行端到端语音测试，支持多设备并行与实时进度监控。',
      badges: ['多设备并行', '实时监控', '自动化流程'],
      action: '开始端到端测试',
      to: '/E2ETest',
    },
    {
      key: 'api',
      icon: ArrowLeftRight,
      color: 'bg-secondary/10 text-secondary',
      title: 'API 测试',
      description:
        '测试语音识别和翻译 API 的性能与准确率，支持批量测试与结果对比分析。',
      badges: ['性能测试', '批量执行', '对比分析'],
      action: '开始 API 测试',
      to: '/APITest',
    },
  ],
} as const

/** ③ 为什么选择本平台 */
export const WHY_CHOOSE_US = {
  eyebrow: '为什么选择本平台',
  heading: '更快的执行，更全的评估，更可信的报告。',
  subtext: '把设备、用例、执行、评估、报告收进一个平台，团队把时间花在分析结果上。',
  reasons: [
    {
      icon: Smartphone,
      title: '真实设备测试',
      description:
        '在 Android/鸿蒙真机上执行完整语音测试流程，模拟真实用户场景，快速对比不同设备表现。',
    },
    {
      icon: ArrowLeftRight,
      title: '多友商横向对比',
      description:
        '多个厂商模型/APP/API 在同一测试集、同一指标下同时实测，横向排名看清业界水平。',
    },
    {
      icon: Star,
      title: '自动化评估引擎',
      description:
        '准确率、召回率、F1、翻译质量（COMET）、流畅度（气泡率/停顿率）多指标自动计算。',
    },
    {
      icon: Gauge,
      title: '高效任务调度',
      description:
        '异步 IO + 智能负载均衡，多任务并行互不阻塞；WebSocket 实时推送进度。',
    },
    {
      icon: Users,
      title: '细粒度权限体系',
      description:
        '角色化管理员、测试工程师、算法工程师、设备管理员、游客五类角色的页面与操作可见性。',
    },
    {
      icon: DatabaseZap,
      title: '数据全量自有',
      description: '测试资产、音频库、报告全部留在本地部署环境，支持导出与归档。',
    },
  ],
  footerLinks: [
    { label: '查看测试类型', to: '#console-entries' },
    { label: '阅读使用手册', to: '/user-guide' },
    { label: '了解权限体系', to: '/user-guide' },
  ],
}

/** ④ 工作台功能入口（八卡；bg-chart-N/12 语义软底，§3.5） */
export const CONSOLE_ENTRIES = {
  eyebrow: '02 / 功能入口',
  heading: '八个模块，覆盖测试全生命周期。',
  consoleLink: '进入工作台',
  emptyText: '登录后可查看全部功能入口',
  footnote:
    '声压级映射、标签管理、算法配置、日志查看在工作台内可直达；页面入口随角色权限渲染。',
  cards: [
    {
      key: 'tasks',
      icon: ClipboardList,
      name: '任务管理',
      summary: '任务记录、发布任务与合并对比，历史结果随时回溯。',
      to: '/tasks',
      permission: 'task:read',
      color: 'bg-chart-1/12 text-chart-1 dark:bg-chart-1/20',
    },
    {
      key: 'e2e',
      icon: Smartphone,
      name: '端到端测试',
      summary: '真机执行五步流程，进度实时推送。',
      to: '/E2ETest',
      permission: 'task:execute',
      color: 'bg-chart-2/12 text-chart-2 dark:bg-chart-2/20',
    },
    {
      key: 'api',
      icon: ArrowLeftRight,
      name: 'API 测试',
      summary: '批量测试语音 API，响应时间与成功率一目了然。',
      to: '/APITest',
      permission: 'task:execute',
      color: 'bg-chart-3/12 text-chart-3 dark:bg-chart-3/20',
    },
    {
      key: 'testcases',
      icon: ListChecks,
      name: '用例管理',
      summary: '分组与标签体系，批量导入导出，用例集中维护。',
      to: '/testcases',
      permission: 'testcase:read',
      color: 'bg-chart-4/12 text-chart-4 dark:bg-chart-4/20',
    },
    {
      key: 'audio',
      icon: Music,
      name: '音频管理',
      summary: '多格式批量导入，导入即可自动生成测试用例。',
      to: '/audio-import',
      permission: 'audio:read',
      color: 'bg-chart-5/12 text-chart-5 dark:bg-chart-5/20',
    },
    {
      key: 'devices',
      icon: Headphones,
      name: '设备管理',
      summary: 'Android/鸿蒙真机与播放设备，状态自动巡检。',
      to: '/devices',
      permission: 'device:read',
      color: 'bg-chart-1/12 text-chart-1 dark:bg-chart-1/20',
    },
    {
      key: 'reports',
      icon: FileBarChart,
      name: '报告中心',
      summary: '单任务报告与跨任务对比，多格式导出。',
      to: '/reports',
      permission: 'report:read',
      color: 'bg-chart-2/12 text-chart-2 dark:bg-chart-2/20',
    },
    {
      key: 'evaluation',
      icon: Star,
      name: '评估维度',
      summary: '自定义评估指标与 API 集成，口径集中管理。',
      // 评估维度页未建（未建路由命中 404 页为可视稿预期，同基座 /rankings /about 口径）
      to: '/Evaluation',
      permission: 'evaluation:read',
      color: 'bg-chart-3/12 text-chart-3 dark:bg-chart-3/20',
    },
  ],
}

/** ⑤ 平台架构演示（终端示例逐字取自 doc/接口文档/07_任务管理.md §7.11 与 sse_bp.py 实测格式） */
export const PLATFORM_DEMO = {
  eyebrow: '03 / 开发者友好',
  heading: '工具照常用，平台接进来。',
  description:
    '测试执行、进度查询、日志订阅全部走 REST 与 SSE 标准接口——脚本化集成与平台操作同样简单。',
  checks: ['REST API 全域覆盖', 'SSE 实时事件推送', '接口文档站内可读'],
  apiManualLink: '阅读 API 手册',
  terminalFooter:
    '示例中的地址与任务 ID 请替换为你的实际环境；完整错误码见 API 手册。',
  commonEntries: {
    title: '常用入口',
    description: '首次使用按 配置维度 → 配置设备 → 导入音频 的顺序准备资产。',
    buttons: [
      { label: '配置播放设备', to: '/devices' },
      { label: '配置评估维度', to: '/Evaluation' },
      { label: '导入测试音频', to: '/audio-import' },
    ],
  },
}

export const PROGRESS_EXAMPLE = {
  id: 'progress',
  label: '进度轮询',
  method: 'GET',
  endpoint: '/api/v1/tasks/{id}/progress',
  code: `curl "/api/v1/tasks/{id}/progress" \\
  -H "Authorization: Bearer $TOKEN"

# 响应（示例数据）
{
  "total": 100,
  "completed": 50,
  "failed": 5,
  "progress": 50,
  "current_case": "case_001",
  "status": "running"
}`,
}

export const SSE_EXAMPLE = {
  id: 'sse',
  label: '实时事件',
  method: 'GET',
  endpoint: '/api/v1/sse/events',
  code: `curl -N "/api/v1/sse/events" \\
  -H "Authorization: Bearer $TOKEN" \\
  -H "Accept: text/event-stream"

# 事件流（示例数据）
event: task_progress
data: {"task_id":1,"progress":50,"status":"running"}`,
}

/** ⑥ 数据与可靠性 */
export const DATA_RELIABILITY = {
  eyebrow: '数据与可靠性',
  heading: '任务交给平台，结果实时可查。',
  subtext:
    '异步调度保证吞吐，事件推送保证时效，失败重试保证完整——三层机制托底每一次测试。',
  cards: [
    {
      title: '异步执行',
      description: '任务提交即返回，最大并发与队列长度可配置。',
    },
    {
      title: '失败重试',
      description: '失败用例支持重试与跳过，任务级断点恢复。',
    },
    {
      title: '实时推送',
      description: 'SSE/WebSocket 双通道，任务状态秒级更新。',
    },
  ],
  chainLabel: '全流程可追溯',
  chain: ['任务提交', '设备执行', '实时进度', '自动评估', '报告生成'],
  footnote: '评估指标口径与权重在工作台「评估维度」中配置。',
} as const

/** ⑦ 部署与数据边界 */
export const DEPLOYMENT_TRUST = {
  eyebrow: '05 / 部署与边界',
  heading: '数据留在本地，权限各归其位。',
  subtext:
    '面向企业内网的部署形态：数据不出域，权限有边界，操作有痕迹。',
  commitments: [
    {
      title: '本地化部署',
      description: '平台与全部测试数据运行在内网环境，音频库与报告不出域。',
    },
    {
      title: '账号与角色隔离',
      description: 'RBAC 五角色 + 权限串逐页逐按钮控制可见与可操作。',
    },
    {
      title: '操作留痕',
      description: '登录、任务执行、配置变更记录审计日志，支持按时间检索。',
    },
  ],
  card: {
    badge: '内网部署',
    title: '系统信息',
    description: '当前部署的运行环境。',
    rows: [
      { label: '系统版本', value: '—' },
      { label: '后端框架', value: 'Flask + PostgreSQL' },
      { label: 'Python', value: '3.12' },
      { label: '接口版本', value: 'API v1' },
    ],
    action: '进入工作台',
    anonymousAction: '立即体验',
    manualLink: '阅读使用手册',
  },
  compliance: {
    label: '数据边界清晰',
    badges: ['本地存储', '账号隔离', '审计日志'],
    links: ['用户协议', '隐私政策'],
  },
} as const

/** ⑧ 常见问题 */
export const FAQ = {
  heading: '开始之前，你可能想问。',
  subtext: '从准备资产到看懂报告，五个最常被问到的问题。',
  notice: '站点维护与更新公告在右上角通知中心查看。',
  items: [
    {
      id: 'code',
      question: '需要写代码才能用吗？',
      answer:
        '不需要。在页面上完成 选择用例 → 选择设备 → 执行 的三步操作即可发起测试；开发同学也可以走 REST API 与 SSE 集成（见 API 手册）。',
    },
    {
      id: 'prepare',
      question: '首次使用先准备什么？',
      answer:
        '按顺序：① 在「评估维度」配置指标与权重；② 在「设备管理」连接真机或播放设备；③ 在「音频管理」导入测试音频（可选自动生成用例）。',
    },
    {
      id: 'choose',
      question: '端到端测试和 API 测试怎么选？',
      answer:
        '要验证整机语音链路（唤醒、识别、播报）选端到端测试；只验证识别/翻译服务的指标选 API 测试。两者可复用同一套用例与标签。',
    },
    {
      id: 'debug',
      question: '测试失败了怎么排查？',
      answer:
        '先看任务详情的失败统计与日志（/LogView），常见原因：设备离线、音频格式不支持、算法参数不匹配；细项对照使用手册「执行失败自查」一节。',
    },
    {
      id: 'export',
      question: '报告能导出吗？',
      answer:
        '支持单任务报告导出与跨任务对比报告（CSV/PDF，随任务域实施范围）；历史报告页可按时间与类型筛选后批量下载。',
    },
  ],
} as const

/** ⑨ 尾部 CTA */
export const CTA_BAND = {
  // 负责人 2026-10-16 定稿：eyebrow 去算法切换话术，改品牌句
  eyebrow: '智能语音测试平台，让每一次测试都有结果。',
  heading: '准备好开始下一次测试了吗？',
  primaryAction: '进入工作台',
  primaryActionAnonymous: '立即体验',
  secondaryAction: '查看文档',
} as const

/** 页脚（§6 页脚文案；公开壳随导航栏卡定稿后合并） */
export const FOOTER = {
  description: '面向语音团队的端到端测试与 API 测试平台。',
  copyright: (year: number) => `© ${year} 智能语音测试平台. 保留所有权利。`,
} as const

/** 需要登录对话框（站头机制归导航栏卡，本页未登录走登录引导降级） */
export const ANONYMOUS_GUARD_TEXT = '登录后可查看'
