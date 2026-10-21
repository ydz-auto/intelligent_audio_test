/**
 * 导航壳/侧栏 config 完整性测试（INT-377 基座产出 + INT-486 六组终态对齐 + INT-1153 增项）：
 * 路由/权限/activeUrls 与 04_控制台.md §3.2（INT-486 口径）一致；URL 不重复、
 * 每项必带图标；普通项必带权限码，magic 炫彩入口（INT-1153「连接你的 agent」）除外。
 */
import { describe, expect, it } from 'vitest'

import { ROOT_SIDEBAR_NAV } from '@/components/layout/config/sidebar-nav.config'
import { SYSTEM_SETTINGS_VIEW } from '@/components/layout/config/system-settings.config'
import { resolveSidebarView } from '@/components/layout/lib/sidebar-view-registry'

const allItems = ROOT_SIDEBAR_NAV.flatMap((group) => group.items)

describe('ROOT_SIDEBAR_NAV 完整性', () => {
  it('六组导航分组标题齐备（INT-486 终态：总览/AI 工具/测试执行/测试资产/测试配置/管理）', () => {
    expect(ROOT_SIDEBAR_NAV.map((g) => g.title)).toEqual([
      '总览',
      'AI 工具',
      '测试执行',
      '测试资产',
      '测试配置',
      '管理',
    ])
  })

  it('每组至少一项，条目总数与规范一致（INT-486 六组 + INT-1153 AI 工具组「连接你的 agent」= 15 项）', () => {
    expect(allItems.length).toBe(15)
    expect(ROOT_SIDEBAR_NAV.every((g) => g.items.length >= 1)).toBe(true)
  })

  it('总览组首项为「概览」指向 /dashboard', () => {
    const overview = ROOT_SIDEBAR_NAV.find((g) => g.id === 'overview')
    expect(overview?.items[0]?.title).toBe('概览')
    expect(overview?.items[0]?.url).toBe('/dashboard')
  })

  it('测试配置组四项齐备（算法配置/评估维度/SPL 映射/标签管理）', () => {
    const testConfig = ROOT_SIDEBAR_NAV.find((g) => g.id === 'test-config')
    expect(testConfig?.items.map((i) => i.title)).toEqual([
      '算法配置',
      '评估维度',
      'SPL 映射',
      '标签管理',
    ])
    expect(testConfig?.items.map((i) => i.url)).toEqual([
      '/AlgorithmConfig',
      '/Evaluation',
      '/SPLMapping',
      '/TagManagement',
    ])
  })

  it('每个条目必带 icon；普通项必带权限判定（magic 炫彩入口除外）', () => {
    for (const item of allItems) {
      expect(item.icon).toBeDefined()
      // INT-1153「连接你的 agent」为 magic 炫彩入口：登录即可见（token 管理按当前用户本人），不需额外权限码
      if (item.magic) continue
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
    // 叶子 URL 递归收集（支持 NavCollapsible 嵌套）
    const leafUrls: string[] = []
    for (const group of viewGroups) {
      for (const item of group.items) {
        if (item.items) {
          leafUrls.push(...item.items.map((leaf) => String(leaf.url)))
        } else {
          leafUrls.push(String(item.url))
        }
      }
    }
    for (const url of leafUrls) {
      expect(url).toMatch(/^\/system-settings\//)
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
