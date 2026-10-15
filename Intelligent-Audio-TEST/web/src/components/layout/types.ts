import type { LucideIcon } from 'lucide-react'
import type { LinkProps } from '@tanstack/react-router'

/**
 * 导航类型（本平台适配版，照 newAPI layout/types 结构裁剪）：
 * - 去除 i18n（文案直接用中文常量，红线③）；
 * - 去除 chat-presets 动态项与后端角色阈值，权限码对齐 doc/UX设计规范/04_控制台.md §3.2。
 */

type BaseNavItem = {
  title: string
  external?: boolean
  badge?: string
  icon?: LucideIcon
  activeUrls?: (LinkProps['to'] | (string & {}))[]
  /** 持有该权限码才可见 */
  requiredPermission?: string
  /** 持有任一权限码即可见（如系统设置入口） */
  requiredPermissions?: string[]
}

/** 单链接导航项 */
export type NavLink = BaseNavItem & {
  url: LinkProps['to'] | (string & {})
  items?: never
}

/** 折叠子菜单导航项 */
export type NavCollapsible = BaseNavItem & {
  items: (BaseNavItem & { url: LinkProps['to'] | (string & {}) })[]
  url?: never
}

export type NavItem = NavCollapsible | NavLink

export type NavGroup = {
  id?: string
  title: string
  items: NavItem[]
}

export type SidebarData = {
  navGroups: NavGroup[]
}

export type TopNavLink = {
  title: string
  href: string
  isActive?: boolean
  disabled?: boolean
  external?: boolean
}

/** 嵌套侧栏视图的返回项描述 */
export type SidebarViewParent = {
  /** 返回按钮目标 */
  to: LinkProps['to'] | (string & {})
  /** 可见文案（已本地化，如「返回控制台」） */
  label: string
}

/**
 * 嵌套侧栏视图配置（Vercel 式 drill-in）：URL 进入专属工作区时
 * 侧栏树整树替换 + 头部「返回」入口。
 */
export type SidebarView = {
  /** 稳定标识（驱动过渡动画 key） */
  id: string
  /** 激活该视图的路径匹配 */
  pathPattern: RegExp
  parent: SidebarViewParent
  /** 导航组构建器 */
  getNavGroups: () => NavGroup[]
}

/** useSidebarView 的返回值：view 为 null 表示根导航 */
export type ResolvedSidebarView = {
  key: string
  view: SidebarView | null
  navGroups: NavGroup[]
}
