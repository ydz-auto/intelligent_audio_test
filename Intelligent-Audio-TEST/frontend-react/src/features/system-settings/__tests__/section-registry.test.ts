/**
 * 分区注册器工厂测试（INT-489）：nav items / 按 id 取内容 / 元信息 / 默认分区。
 */
import { describe, expect, it } from 'vitest'

import { createSectionRegistry } from '../utils/section-registry'

const registry = createSectionRegistry<'a' | 'b', Record<string, unknown>>({
  sections: [
    {
      id: 'a',
      title: '分区A',
      requiredPermission: 'user:read',
      build: () => 'content-a',
    },
    {
      id: 'b',
      title: '分区B',
      build: () => 'content-b',
    },
  ],
  defaultSection: 'a',
  basePath: '/system-settings/site',
})

describe('createSectionRegistry', () => {
  it('getSectionNavItems 生成 path 风格 URL 与分区权限门槛', () => {
    expect(registry.getSectionNavItems()).toEqual([
      {
        id: 'a',
        title: '分区A',
        url: '/system-settings/site/a',
        requiredPermission: 'user:read',
        requiredPermissions: undefined,
      },
      {
        id: 'b',
        title: '分区B',
        url: '/system-settings/site/b',
        requiredPermission: undefined,
        requiredPermissions: undefined,
      },
    ])
  })

  it('getSectionContent 按 id 返回构建内容，未知 id 返回 null', () => {
    expect(registry.getSectionContent('a', {})).toBe('content-a')
    expect(registry.getSectionContent('b', {})).toBe('content-b')
    // 未知 id：TS 上受类型约束，运行时防御返回 null
    expect(
      registry.getSectionContent('unknown' as 'a', {})
    ).toBeNull()
  })

  it('getSectionMeta 返回标题与分区门槛，未知回退 id', () => {
    expect(registry.getSectionMeta('a')).toEqual({
      title: '分区A',
      requiredPermission: 'user:read',
      requiredPermissions: undefined,
    })
    expect(registry.getSectionMeta('unknown' as 'a').title).toBe('unknown')
  })

  it('getSectionIds / getDefaultSection / getSectionById', () => {
    expect(registry.getSectionIds()).toEqual(['a', 'b'])
    expect(registry.getDefaultSection()).toBe('a')
    expect(registry.getSectionById('b')?.title).toBe('分区B')
    expect(registry.getSectionById('unknown' as 'a')).toBeUndefined()
  })
})
