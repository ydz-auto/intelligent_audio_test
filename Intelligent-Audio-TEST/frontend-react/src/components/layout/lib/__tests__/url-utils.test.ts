/**
 * components/layout/lib/url-utils 纯函数测试（照 newAPI 纯函数粒度：
 * 导航激活态判定——根路径/查询串/子菜单/首段匹配）。
 */
import { describe, expect, it } from 'vitest'

import {
  checkIsActive,
  normalizeHref,
} from '@/components/layout/lib/url-utils'
import type { NavItem } from '@/components/layout/types'

const linkItem: NavItem = { title: '任务管理', url: '/tasks' }

const activeUrlsItem: NavItem = {
  title: '任务管理',
  url: '/tasks',
  activeUrls: ['/tasks'],
}

const collapsibleItem: NavItem = {
  title: '系统设置',
  items: [
    { title: '站点设置', url: '/system-settings/site' },
    { title: '算法设置', url: '/system-settings/algorithm' },
  ],
}

describe('normalizeHref', () => {
  it('去掉查询串与尾部斜杠', () => {
    expect(normalizeHref('/tasks?tab=daily')).toBe('/tasks')
    expect(normalizeHref('/reports/')).toBe('/reports')
  })

  it('根路径保持单斜杠', () => {
    expect(normalizeHref('/')).toBe('/')
    expect(normalizeHref('/?x=1')).toBe('/')
  })
})

describe('checkIsActive', () => {
  it('普通链接按精确路径匹配（当前 URL 可带查询串）', () => {
    expect(checkIsActive('/tasks', linkItem)).toBe(true)
    expect(checkIsActive('/tasks?tab=merged', linkItem)).toBe(true)
    expect(checkIsActive('/tasks/123', linkItem)).toBe(false)
  })

  it('activeUrls 对当前 URL 去查询串后精确命中', () => {
    expect(checkIsActive('/tasks?tab=merged', activeUrlsItem)).toBe(true)
    expect(checkIsActive('/tasks/42', activeUrlsItem)).toBe(true)
    expect(checkIsActive('/tasks/42/rounds', activeUrlsItem)).toBe(true)
    // 路径段边界：/testcasesx 前缀相同但非子路径，不命中
    expect(checkIsActive('/tasksetup', activeUrlsItem)).toBe(false)
  })

  it('activeUrls 子路径命中（INT-490 P1：/testcases 命中双视图 /testcases/$view）', () => {
    const testcasesItem: NavItem = {
      title: '用例管理',
      url: '/testcases',
      activeUrls: ['/testcases'],
    }
    expect(checkIsActive('/testcases', testcasesItem)).toBe(true)
    expect(checkIsActive('/testcases/by-group', testcasesItem)).toBe(true)
    expect(checkIsActive('/testcases/by-tag?search=中文', testcasesItem)).toBe(true)
    expect(checkIsActive('/testcases-list', testcasesItem)).toBe(false)
  })

  it('折叠项任一子项命中即激活', () => {
    expect(checkIsActive('/system-settings/site', collapsibleItem)).toBe(true)
    expect(checkIsActive('/system-settings/algorithm', collapsibleItem)).toBe(
      true
    )
    expect(checkIsActive('/dashboard', collapsibleItem)).toBe(false)
  })

  it('mainNav 模式按首段路径匹配', () => {
    expect(checkIsActive('/tasks/123', linkItem, true)).toBe(true)
    expect(checkIsActive('/reports', linkItem, true)).toBe(false)
  })
})
