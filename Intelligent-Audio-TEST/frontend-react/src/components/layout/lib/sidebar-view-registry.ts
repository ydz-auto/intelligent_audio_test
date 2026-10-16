import { SYSTEM_SETTINGS_VIEW } from '../config/system-settings.config'
import type { NavGroup, SidebarView } from '../types'

/**
 * 已注册的嵌套侧栏视图（照 newAPI drill-in 机制裁剪 i18n）。
 * 新增嵌套工作区在此追加；匹配优先级为数组顺序，首个命中 pathPattern 生效。
 */
const SIDEBAR_VIEWS: readonly SidebarView[] = [SYSTEM_SETTINGS_VIEW]

/** 解析给定路径的嵌套视图；无匹配返回 null（渲染根导航） */
export function resolveSidebarView(pathname: string): SidebarView | null {
  return SIDEBAR_VIEWS.find((view) => view.pathPattern.test(pathname)) ?? null
}

/** 供命令面板等消费方取当前路径的导航组；无嵌套视图时返回 null */
export function getNavGroupsForPath(pathname: string): NavGroup[] | null {
  const view = resolveSidebarView(pathname)
  return view ? view.getNavGroups() : null
}
