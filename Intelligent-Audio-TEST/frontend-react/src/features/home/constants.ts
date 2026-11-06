import {
  AppWindow,
  ArrowLeftRight,
  AudioLines,
  AudioWaveform,
  BrainCircuit,
  ClipboardList,
  DatabaseZap,
  FileBarChart,
  Gauge,
  Headphones,
  Languages,
  Layers,
  ListChecks,
  Mic,
  Music,
  PhoneCall,
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
  badge: '算法可插拔 · 从 ASR 到实时语音大模型',
  titleLine1: '智能语音测试平台',
  titleLine2: '让每一次语音交互都可度量',
  // 负责人 2026-10-16 定稿：highlight 并入多友商横向对比核心价值（多友商同集同指标同时实测）
  highlight: '真实设备、真实链路、真实指标，多友商横向对比，看清真实用户体验。',
  // 负责人 2026-10-16 文案基准：HERO 描述以 V9.7.10 为最终基准（白话讲功能，无 marketing 腔）
  description:
    '一站式语音测试与评估解决方案，支持多维度语音评估，提供完整的测试任务管理、报告分析功能。',
  primaryAction: '立即开始测试',
  primaryActionAuthed: '进入工作台',
  secondaryAction: '查看文档',
  checks: [
    '多设备并行测试',
    '实时进度推送',
    '自动化评估引擎',
    '可视化对比报告',
    '多算法类型支持',
  ],
  orbitCaption: '一个平台，覆盖语音测试全流程',
  brandRow: ['Android 真机', '鸿蒙设备', '语音 API', '自动评估'],
  brandRowLink: '开始一次测试',
} as const

/** 枢纽图四节点（四色取图表色板 chart-1~4，只上图标色） */
export const ORBIT_NODES: {
  name: string
  icon: LucideIcon
  color: string
  position: string
}[] = [
  {
    name: '测试用例',
    icon: ListChecks,
    color: 'text-chart-1',
    position: 'top-8 left-0 sm:left-4',
  },
  {
    name: '被测 API',
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

/**
 * 算法能力 floating 节点（INT-421 负责人口径：四角节点卡与连线不变，算法能力项
 * 不接 SVG 连线、不进四象限几何，浮置环绕）——2026-10-17 INT-635 重新设计：
 * 圆形玻璃徽章 + 悬浮文字标签（徽章 `rounded-full border bg-card/90 shadow-md`，
 * 图标上图表色板 chart-1~5 / 场景语义灰，卡面中性；每枚带与图标色同源的辉光阴影），
 * 弃原「虚线描边 + 半透明底」盒式（与四角实线卡视觉同质，负责人反馈）。
 * 尺寸小于主节点卡，浮置于外圈环带（上下中/左右中）与四角节点间隙。
 * 算法名以 08_算法配置/智能语音算法配置适配/智能语音算法配置化方案.md §2.3 种子数据
 * + voice_llm改造方案.md 为准；「说话人分割」「通话」「会议纪要」无独立算法类型，
 * 按应用场景叙事，不立独立算法条目。
 */
export const ORBIT_ALGORITHM_NODES: {
  name: string
  icon: LucideIcon
  color: string
  position: string
  /** 辉光阴影色（与图标色同源：chart-N 对应 / 场景语义灰 neutral），浮动粒子感 */
  glow: string
  /** 旗舰强调：实时语音大模型（voice_llm），ring-2 ring-primary/40 + shadow-primary/20 */
  flagship?: boolean
}[] = [
  {
    name: '实时语音大模型',
    icon: BrainCircuit,
    color: 'text-chart-1',
    glow: 'shadow-primary/20',
    position: 'top-0 left-1/2 -translate-x-1/2',
    flagship: true,
  },
  {
    name: '语音识别 ASR',
    icon: Mic,
    color: 'text-chart-2',
    glow: 'shadow-chart-2/25',
    position: 'top-1/2 right-0 sm:right-2 -translate-y-1/2',
  },
  {
    name: '语音合成 TTS',
    icon: AudioLines,
    color: 'text-chart-3',
    glow: 'shadow-chart-3/25',
    position: 'top-1/2 left-0 sm:left-2 -translate-y-1/2',
  },
  {
    name: '翻译',
    icon: Languages,
    color: 'text-chart-4',
    glow: 'shadow-chart-4/25',
    position: 'bottom-0 left-1/2 -translate-x-1/2',
  },
  {
    name: '声纹识别 · 说话人分割',
    icon: AudioWaveform,
    color: 'text-chart-5',
    glow: 'shadow-chart-5/25',
    // 对角间隙（左上/右下）仅 lg+ 展示——小屏断点容纳不下六枚且不遮挡四角节点（03_首页.md §7 断言）
    position: 'top-[24%] left-0 sm:left-2 hidden lg:flex',
  },
  {
    name: '通话与会话场景',
    icon: PhoneCall,
    color: 'text-muted-foreground',
    glow: 'shadow-neutral/15',
    position: 'bottom-[24%] right-0 sm:right-2 hidden lg:flex',
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
  /**
   * API 在线率告警阈值（03_首页.md §3.2「在线率低于阈值时该项标 Alert 色并附故障告警角标」；
   * 阈值收敛在此，不在组件里写魔法数字）。
   */
  apiOnlineRateAlertThreshold: 0.8,
  apiAlertBadge: '故障告警',
} as const

/** ② 从这里开始 */
export const QUICK_START = {
  eyebrow: '01 / 开始测试',
  heading: '四步跑通一次语音测试。',
  // 负责人 2026-10-16 文案重写：流程不选算法（算法已全局化），subtext 直白讲真实流程
  subtext: '选好用例和设备/API 就能开始测试，执行进度实时可见，跑完自动评估并生成报告。',
  steps: [
    { name: '选择用例', description: '创建或选择测试用例' },
    { name: '选择设备/API', description: '同屏选择设备与 API' },
    { name: '执行测试', description: '运行语音测试流程' },
    { name: '查看结果', description: '分析测试评估报告' },
  ],
  cards: [
    {
      key: 'start',
      icon: Smartphone,
      color: 'bg-primary/10 text-primary',
      title: '开始测试',
      description:
        '选择用例与设备/API，在同一流程内完成语音测试与报告生成，多设备并行实时监控。',
      badges: ['设备+API 混合', '实时监控', '自动评估'],
      action: '开始测试',
      to: '/start-test',
    },
    {
      key: 'reports',
      icon: FileBarChart,
      color: 'bg-secondary/10 text-secondary',
      title: '报告中心',
      description:
        '单任务报告与跨任务对比报告，多格式导出，历史结果随时回溯与横向排名。',
      badges: ['对比报告', '多格式导出', '历史回溯'],
      action: '查看报告',
      to: '/reports',
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
    { label: '开始一次测试', to: '/start-test' },
    { label: '阅读使用手册', to: '/user-guide' },
    { label: '了解权限体系', to: '/user-guide' },
  ],
}

/** ④ 工作台功能入口（七卡；bg-chart-N/12 语义软底，§3.5；e2e/api 已并入开始测试） */
export const CONSOLE_ENTRIES = {
  eyebrow: '02 / 功能入口',
  // 负责人 2026-10-16 文案基准：去「覆盖测试全生命周期」营销腔，白话讲功能模块
  heading: '七个功能模块，覆盖从用例到报告的测试流程。',
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
      key: 'start-test',
      icon: Smartphone,
      name: '开始测试',
      summary: '选用例 + 设备/API 混合执行，进度实时推送，自动评估。',
      to: '/start-test',
      permission: 'task:execute',
      color: 'bg-chart-2/12 text-chart-2 dark:bg-chart-2/20',
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

/** ⑤ 接入测试对象（03_首页.md §3.6，INT-420 负责人口径：被测设备/被测APP/被测API 三对象卡 + 接入演示三页签，示例值一律标注「示例数据」） */
export const TEST_OBJECT_ACCESS = {
  eyebrow: '03 / 接入测试对象',
  heading: '把被测对象接进平台。',
  subtext:
    '被测设备、被测应用与被测 API 三类对象都可以接进平台——接入后统一调度、统一执行、统一评估，测试从一台真机或一个端点开始。',
  objects: [
    {
      key: 'device',
      icon: Smartphone,
      name: '被测设备',
      description: 'Android（ADB）/ 鸿蒙（HDC）真机接入，在线状态自动巡检。',
      action: '去设备管理',
      to: '/devices',
    },
    {
      key: 'app',
      icon: AppWindow,
      name: '被测 APP',
      description:
        '在设备卡内安装 APK/HAP、启动/停止应用、清理应用数据——测试前先装载目标应用。',
      action: '去装载应用',
      to: '/devices',
    },
    {
      key: 'api',
      icon: ArrowLeftRight,
      name: '被测 API',
      description:
        'HTTP / HTTP 流式 / Realtime WebSocket 三类端点统一管理，连接测试与健康分实时可见。',
      action: '去配置 API',
      to: '/APITest',
    },
  ],
  guideLink: '查看接入指引',
  demoNote:
    '示例中的设备地址、序列号、包名与 API 值均为示例数据；实际接入以你的真实环境为准，完整说明见文档。',
  /** 接入演示三页签（access-demo.tsx 消费；命令与响应对照 device_service/前端实测，值为示例数据） */
  demoTabs: [
    {
      id: 'device-connect',
      label: '设备连接',
      group: 'ADB / HDC',
      method: 'GET',
      endpoint: 'adb devices -l',
      code: `# Android 真机接入（示例数据）
adb connect <设备IP>:5555
adb devices -l
# 鸿蒙真机接入（示例数据）
hdc list targets
hdc -t <设备序列号> shell power-shell wakeup`,
    },
    {
      id: 'app-install',
      label: '应用装卸',
      group: '平台内操作',
      method: '—',
      endpoint: '/devices 设备管理',
      code: `/devices 设备管理
  └─ 设备卡 ▸ 操作菜单「安装应用」
     └─ 输入服务器侧安装包路径（APK/HAP）→ 确认执行
  └─ 设备卡 ▸ 操作菜单「卸载应用」
     └─ 输入应用包名 → 确认执行

# 底层命令（示例数据，device_operation_executor 实测）
adb install -r -t <服务器侧APK路径>
adb uninstall <应用包名>
hdc -t <设备序列号> install -r <服务器侧HAP路径>
hdc -t <设备序列号> shell bm uninstall -n <应用包名>`,
    },
    {
      id: 'api-health',
      label: 'API 连接测试',
      group: 'TestAPIConnection',
      method: 'POST',
      endpoint: '/api/v1/apis/:id/health',
      code: `POST /api/v1/apis/:id/health

{
  "code": 0,
  "message": "连接测试完成",
  "data": {
    "id": 1,
    "status": "online",
    "health_score": 95,
    "endpoints_status": "true",
    "status_code": 200,
    "response_time": "120.50ms",
    "error": null,
    "warning": null
  }
}`,
    },
  ],
  /** 尾行「常用入口」（03_首页.md §3.6 尾部：首次使用资产准备顺序） */
  tail: {
    heading: '常用入口',
    note: '首次使用按 配置维度 → 配置设备 → 导入音频 的顺序准备资产。',
    actions: [
      { label: '配置播放设备', to: '/devices' },
      { label: '配置评估维度', to: '/Evaluation' },
      { label: '导入测试音频', to: '/audio-import' },
    ],
  },
} as const

/** ⑥ 数据与可靠性 */
export const DATA_RELIABILITY = {
  eyebrow: '数据与可靠性',
  heading: '任务交给平台，结果实时可查。',
  // 负责人 2026-10-16 文案基准：去「三层机制托底」营销腔，白话讲三个真实机制干什么
  subtext: '异步调度让任务提交即返回，事件推送让进度实时可见，失败重试保证结果完整。',
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
  // 负责人 2026-10-16 文案重写：去 newAPI 腔，白话讲本地部署 + RBAC 五角色 + 操作审计日志
  heading: '本地部署，数据与权限自己掌控。',
  subtext:
    '平台部署在你的内网环境：测试数据、音频库与报告都留在本地；账号按管理员、测试工程师、算法工程师、设备管理员、游客五类角色划分权限；登录、任务执行与配置变更都记录审计日志。',
  commitments: [
    {
      title: '本地化部署',
      description: '平台与测试数据运行在你的内网环境，音频库与报告存在本地。',
    },
    {
      title: '账号与角色权限',
      description: '五类角色各管各的权限，页面与操作按权限串逐项控制。',
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
      answer: '不需要。在页面上完成 选择用例 → 选择设备 → 执行 的三步操作即可发起测试。',
    },
    {
      id: 'prepare',
      question: '首次使用先准备什么？',
      answer:
        '按顺序：① 在「评估维度」配置指标与权重；② 在「设备管理」连接真机或播放设备；③ 在「音频管理」导入测试音频（可选自动生成用例）。',
    },
    {
      id: 'choose',
      question: '一次测试能同时覆盖设备和 API 吗？',
      answer:
        '可以。开始测试中同一流程可同时选择设备与 API（混合执行），同一套用例可由物理设备、HTTP API、WebSocket API 链路消费。',
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
  description: '面向语音团队的一站式测试与评估平台。',
  copyright: (year: number) => `© ${year} 智能语音测试平台. 保留所有权利。`,
} as const

/** 需要登录对话框（站头机制归导航栏卡，本页未登录走登录引导降级） */
export const ANONYMOUS_GUARD_TEXT = '登录后可查看'
