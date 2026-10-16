/**
 * 导航壳/侧栏 config 完整性测试（INT-377 基座产出）：路由/权限/activeUrls
 * 与 04_控制台.md §3.2 口径一致；URL 不重复、每项必带图标与权限码。
 */
import { describe, expect, it } from 'vitest'

import { ROOT_SIDEBAR_NAV } from '@/components/layout/config/sidebar-nav.config'
import { SYSTEM_SETTINGS_VIEW } from '@/components/layout/config/system-settings.config'
import { resolveSidebarView } from '@/components/layout/lib/sidebar-view-registry'

const allItems = ROOT_SIDEBAR_NAV.flatMap((group) => group.items)

describe('ROOT_SIDEBAR_NAV 完整性', () => {
  it('五组导航分组标题齐备', () => {
    expect(ROOT_SIDEBAR_NAV.map((g) => g.title)).toEqual([
      '总览',
      '测试执行',
      '测试资产',
      'AI 工具',
      '管理',
    ])
  })

  it('每组至少一项，条目总数与规范一致', () => {
    expect(allItems.length).toBe(11)
    expect(ROOT_SIDEBAR_NAV.every((g) => g.items.length >= 1)).toBe(true)
  })

  it('每个条目必带 icon 与权限判定（requiredPermission 或 requiredPermissions）', () => {
    for (const item of allItems) {
      expect(item.icon).toBeDefined()
      const hasPermissionGate = Boolean(item.requiredPermission) ||
        Boolean(item.requiredPermissions?.length)
      expect(hasPermissionGate).toBe(true)
    }
  })

  it('一级 URL 无重复', () => {
    const urls = allItems.map((i) => i.url).filter(Boolean)
    expect(new Set(urls).size).toBe(urls.length)
  })

  it('系统设置入口经 drill-in 视图且其子项 URL 均在 /system-settings 下', () => {
    const systemSettings = allItems.find((i) =>
      SYSTEM_SETTINGS_VIEW.pathPattern.test(String(i.url ?? ''))
    )
    expect(systemSettings).toBeDefined()
    const viewGroups = SYSTEM_SETTINGS_VIEW.getNavGroups()
    for (const group of viewGroups) {
      for (const item of group.items) {
        expect(String(item.url)).toMatch(/^\/system-settings\//)
      }
    }
  })
})

describe('resolveSidebarView', () => {
  it('/system-settings 路径命中嵌套视图，其余返回 null', () => {
    expect(resolveSidebarView('/system-settings/site')?.id).toBe(
      'system-settings'
    )
    expect(resolveSidebarView('/system-settings')?.id).toBe('system-settings')
    expect(resolveSidebarView('/dashboard')).toBeNull()
  })

  it('getNavGroupsForPath 仅命中视图时返回导航组', () => {
    const groups = resolveSidebarView('/system-settings/users')
    expect(groups?.getNavGroups().length).toBeGreaterThanOrEqual(1)
    expect(resolveSidebarView('/tasks')).toBeNull()
  })
})
