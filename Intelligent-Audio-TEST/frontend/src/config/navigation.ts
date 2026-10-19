/**
 * 导航配置（UX设计-VUE 总表 §2.2/§2.3/§2.5 落地）
 *
 * - 顶栏 TopNav 六项：主页/工作台/报告/排行榜/文档/关于（§2.2）
 * - 左侧栏六组十四项（§2.3）：逐项权限过滤、空组整组隐藏、当前页高亮
 * - 系统设置 drill-in 六域设置树（§2.5，照 React features/system-settings/domains.ts）
 *
 * 权限口径：permission = hasPermission（任一）；permissions = hasAnyPermission（任一）。
 * 样式：Font Awesome 图标 + 原 Vue token，不引入 React/newAPI 形态。
 */

// ===== 顶栏六项（§2.2）=====
export interface TopNavLink {
  title: string
  href: string
  /** 权限码（不满足隐藏）；undefined = 全员含未登录 */
  permission?: string
  /** 受限项：未登录点击弹「需要登录」Dialog（5 秒倒计时跳 /login?redirect=） */
  restricted?: boolean
  /** 公开项：未登录也可见可点 */
  public?: boolean
}

export const TOP_NAV_LINKS: TopNavLink[] = [
  { title: '主页', href: '/', public: true },
  { title: '工作台', href: '/dashboard', permission: 'home:read', restricted: true },
  { title: '报告', href: '/reports', permission: 'report:read' },
  { title: '排行榜', href: '/rankings', permission: 'benchmark:ranking:read' },
  { title: '文档', href: '/user-guide', public: true },
  { title: '关于', href: '/about', public: true },
]

// ===== 左侧栏六组十四项（§2.3）=====
export interface NavItem {
  title: string
  url: string
  icon: string
  /** 单权限（hasPermission） */
  permission?: string
  /** 多权限任一（hasAnyPermission） */
  permissions?: string[]
  /** 同项高亮子路由前缀（如任务详情 /tasks/:id） */
  activeUrls?: string[]
}

export interface NavGroup {
  id: string
  title: string
  items: NavItem[]
}

export const ROOT_SIDEBAR_NAV: NavGroup[] = [
  {
    id: 'overview',
    title: '总览',
    items: [
      { title: '概览', url: '/dashboard', icon: 'fas fa-gauge-high', permission: 'home:read' },
    ],
  },
  {
    id: 'ai-tools',
    title: 'AI 工具',
    items: [
      { title: '灵犀Agent', url: '/ai-chat', icon: 'fas fa-robot', permission: 'report:read' },
    ],
  },
  {
    id: 'testing',
    title: '测试执行',
    items: [
      { title: '开始测试', url: '/start-test', icon: 'fas fa-play', permissions: ['task:execute', 'algorithm:read'] },
      { title: '任务管理', url: '/tasks', icon: 'fas fa-clipboard-list', permission: 'task:read', activeUrls: ['/tasks'] },
    ],
  },
  {
    id: 'assets',
    title: '测试资产',
    items: [
      { title: '用例管理', url: '/testcases', icon: 'fas fa-list-check', permission: 'testcase:read', activeUrls: ['/testcases'] },
      { title: '音频管理', url: '/audio-import', icon: 'fas fa-music', permission: 'audio:read' },
      { title: '设备管理', url: '/devices', icon: 'fas fa-headphones', permission: 'device:read' },
      { title: '报告中心', url: '/report-center', icon: 'fas fa-file-chart-bar', permission: 'report:read' },
    ],
  },
  {
    id: 'test-config',
    title: '测试配置',
    items: [
      { title: '算法配置', url: '/AlgorithmConfig', icon: 'fas fa-cogs', permission: 'algorithm:read' },
      { title: '评估维度', url: '/Evaluation', icon: 'fas fa-star', permission: 'evaluation:read' },
      { title: 'SPL 映射', url: '/SPLMapping', icon: 'fas fa-wave-square', permissions: ['spl:read', 'digital_spl:read'] },
      { title: '标签管理', url: '/TagManagement', icon: 'fas fa-tags', permission: 'tag:read' },
    ],
  },
  {
    id: 'admin',
    title: '管理',
    items: [
      { title: '日志查看', url: '/logs', icon: 'fas fa-file-alt', permission: 'log:read' },
      {
        title: '系统设置', url: '/system-settings/site', icon: 'fas fa-gear',
        permissions: ['user:read', 'role:read', 'auth:manage_provider', 'log:manage'],
      },
    ],
  },
]

// ===== 系统设置六域设置树（§2.5，drill-in 替换侧栏整树）=====
export interface SettingsSection {
  id: string
  title: string
  permission?: string
  permissions?: string[]
}

export interface SettingsDomain {
  id: string
  title: string
  icon: string
  permission?: string
  permissions?: string[]
  defaultSection: string
  sections: SettingsSection[]
}

export const SETTINGS_DOMAINS: SettingsDomain[] = [
  {
    id: 'site', title: '站点设置', icon: 'fas fa-gear',
    permission: 'user:read', defaultSection: 'info',
    sections: [
      { id: 'info', title: '站点信息' },
      { id: 'notice', title: '站点公告' },
      { id: 'navigation', title: '导航模块' },
    ],
  },
  {
    id: 'iam', title: '用户与权限', icon: 'fas fa-users',
    permission: 'user:read', defaultSection: 'users',
    sections: [
      { id: 'users', title: '用户管理' },
      { id: 'roles', title: '角色权限管理' },
    ],
  },
  {
    id: 'auth', title: '认证设置', icon: 'fas fa-shield-halved',
    permissions: ['auth:manage_provider', 'user:read'], defaultSection: 'methods',
    sections: [
      { id: 'methods', title: '认证方式' },
      { id: 'oauth-providers', title: 'OAuth 提供方', permission: 'auth:manage_provider' },
    ],
  },
  {
    id: 'appearance', title: '外观与主题', icon: 'fas fa-palette',
    defaultSection: 'presets',
    sections: [
      { id: 'presets', title: '主题预设' },
      { id: 'fine-tuning', title: '外观微调' },
    ],
  },
  {
    id: 'security', title: '安全设置', icon: 'fas fa-shield',
    permission: 'user:read', defaultSection: 'access-control',
    sections: [
      { id: 'access-control', title: '访问控制' },
    ],
  },
  {
    id: 'operations', title: '运维设置', icon: 'fas fa-wrench',
    permission: 'log:manage', defaultSection: 'log-maintenance',
    sections: [
      { id: 'log-maintenance', title: '日志维护' },
    ],
  },
]

/** 系统设置默认落点（首个域默认分区） */
export const SYSTEM_SETTINGS_DEFAULT_PATH = `/system-settings/${SETTINGS_DOMAINS[0].id}/${SETTINGS_DOMAINS[0].defaultSection}`

/** 命中系统设置路径判定（drill-in 替换侧栏整树） */
export const SYSTEM_SETTINGS_PATH_PATTERN = /^\/system-settings(\/|$)/

// ===== 侧栏「固定/收起」偏好（INT-894）=====
/** 持久化键，照 React `iatp:sidebar:v1:state` cookie 同 key；localStorage 存「展开」布尔（缺省展开） */
export const SIDEBAR_STATE_KEY = 'iatp:sidebar:v1:state'
