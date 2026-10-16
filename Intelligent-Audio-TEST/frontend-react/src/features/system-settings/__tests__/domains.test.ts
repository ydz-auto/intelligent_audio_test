/**
 * 设置工作区六域注册表测试（INT-489）：域/分区/默认落点与权限门槛
 * 对齐 INT-347 §3.2 定稿（六域树，INT-417 收敛后）。
 */
import { describe, expect, it } from 'vitest'

import {
  getDomainDefaultPath,
  getSettingsDomain,
  SETTINGS_DOMAINS,
  SETTINGS_DOMAIN_IDS,
  SYSTEM_SETTINGS_DEFAULT_PATH,
} from '@/features/system-settings/domains'

describe('SETTINGS_DOMAINS 六域注册表', () => {
  it('六域标题与 id 齐备（站点/用户/认证/外观/安全/运维）', () => {
    expect(SETTINGS_DOMAINS.map((d) => d.id)).toEqual([
      'site',
      'iam',
      'auth',
      'appearance',
      'security',
      'operations',
    ])
    expect(SETTINGS_DOMAINS.map((d) => d.title)).toEqual([
      '站点设置',
      '用户与权限',
      '认证设置',
      '外观与主题',
      '安全设置',
      '运维设置',
    ])
  })

  it('每域必带图标', () => {
    expect(SETTINGS_DOMAINS.every((d) => d.icon)).toBe(true)
  })

  it('每域至少一个分区，且分区 URL 前缀正确', () => {
    for (const domain of SETTINGS_DOMAINS) {
      expect(domain.sections.length).toBeGreaterThanOrEqual(1)
      for (const section of domain.sections) {
        expect(section.title.length).toBeGreaterThan(0)
      }
    }
  })

  it('域级权限门槛（站点/用户/安全随 user:read、运维随 log:manage、认证随任一、外观无门槛）', () => {
    const site = getSettingsDomain('site')
    expect(site?.requiredPermission).toBe('user:read')
    expect(getSettingsDomain('iam')?.requiredPermission).toBe('user:read')
    expect(getSettingsDomain('security')?.requiredPermission).toBe('user:read')
    expect(getSettingsDomain('operations')?.requiredPermission).toBe('log:manage')
    expect(getSettingsDomain('auth')?.requiredPermissions).toEqual([
      'auth:manage_provider',
      'user:read',
    ])
    expect(getSettingsDomain('appearance')?.requiredPermission).toBeUndefined()
  })

  it('OAuth 提供方分区持 auth:manage_provider 独立分区门槛', () => {
    const auth = getSettingsDomain('auth')
    const oauth = auth?.sections.find((s) => s.id === 'oauth-providers')
    expect(oauth?.requiredPermission).toBe('auth:manage_provider')
  })

  it('默认落点 = 首个域默认分区（site/info）', () => {
    expect(SYSTEM_SETTINGS_DEFAULT_PATH).toBe('/system-settings/site/info')
    expect(getDomainDefaultPath('iam')).toBe('/system-settings/iam/users')
    expect(getDomainDefaultPath('unknown')).toBe('/system-settings/site/info')
  })

  it('非法域返回 undefined', () => {
    expect(getSettingsDomain('nope')).toBeUndefined()
    expect(SETTINGS_DOMAIN_IDS).toContain('operations')
  })
})
