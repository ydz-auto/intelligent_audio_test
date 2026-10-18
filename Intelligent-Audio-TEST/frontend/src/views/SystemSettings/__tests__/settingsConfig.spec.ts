/**
 * 系统设置六域权限门控测试（INT-743 P1-1/P3-2）
 *
 * 覆盖 AUTH_MODE=off 全显短路（总表 §2.6 注 4）与域/分区权限判定纯逻辑。
 * settingsPermissionsOpen(readEnv) 注入 reader 供非 off 用例；默认环境
 * （vitest 未注入 VITE_AUTH_MODE）回退 off，与路由守卫同源。
 */
import { describe, it, expect } from 'vitest';
import { AuthMode } from '@/domain/enums';
import {
  settingsPermissionsOpen,
  canAccessDomain,
  canAccessSection,
  canAccessDomainByPermission,
  canAccessSectionByPermission,
  settingsDomains,
  SYSTEM_SETTINGS_PERMISSIONS,
} from '../settingsConfig';

describe('settingsPermissionsOpen（AUTH_MODE=off 全显短路）', () => {
  it('off → 全开', () => {
    expect(settingsPermissionsOpen(() => AuthMode.OFF)).toBe(true);
  });

  it('dev / prod → 不短路', () => {
    expect(settingsPermissionsOpen(() => AuthMode.DEV)).toBe(false);
    expect(settingsPermissionsOpen(() => AuthMode.PROD)).toBe(false);
  });

  it('未注入（默认环境 vitest）→ 回退 off', () => {
    expect(settingsPermissionsOpen()).toBe(true);
  });
});

describe('canAccessDomain / canAccessSection（组合：off 短路）', () => {
  const auth = settingsDomains.find(d => d.id === 'auth')!;

  it('off 模式下无任何权限也全显（六域树不被锁死，P1-1）', () => {
    const never = () => false;
    for (const domain of settingsDomains) {
      expect(canAccessDomain(domain, never)).toBe(true);
    }
    // OAuth 分区显式权限在 off 下同样放行（收编后不缩权限）
    expect(canAccessSection(auth, auth.sections[1], never)).toBe(true);
  });

  it('SYSTEM_SETTINGS_PERMISSIONS 覆盖各域门槛（用户/角色/OAuth/日志）', () => {
    expect(SYSTEM_SETTINGS_PERMISSIONS).toContain('user:read');
    expect(SYSTEM_SETTINGS_PERMISSIONS).toContain('role:read');
    expect(SYSTEM_SETTINGS_PERMISSIONS).toContain('auth:manage_provider');
    expect(SYSTEM_SETTINGS_PERMISSIONS).toContain('log:manage');
    // iam 域门槛 user:read：持有即见
    const iam = settingsDomains.find(d => d.id === 'iam')!;
    expect(canAccessDomainByPermission(iam, (p: string) => p === 'user:read')).toBe(true);
  });
});

describe('canAccessDomainByPermission（纯权限判定）', () => {
  it('无域门槛（appearance）→ 恒可见', () => {
    const appearance = settingsDomains.find(d => d.id === 'appearance')!;
    expect(canAccessDomainByPermission(appearance, () => false)).toBe(true);
  });

  it('单码门槛：持有 → 可见；缺失 → 不可见', () => {
    const site = settingsDomains.find(d => d.id === 'site')!;
    const have = (p: string) => p === 'user:read';
    expect(canAccessDomainByPermission(site, have)).toBe(true);
    expect(canAccessDomainByPermission(site, () => false)).toBe(false);
  });

  it('多码门槛（auth 域 user:read 或 auth:manage_provider）任一满足即可', () => {
    const auth = settingsDomains.find(d => d.id === 'auth')!;
    // hasAny 为变参：对 auth 域的两码任一持有即放行
    expect(canAccessDomainByPermission(auth, (...have: string[]) => have.includes('user:read'))).toBe(true);
    expect(canAccessDomainByPermission(auth, (...have: string[]) => have.includes('auth:manage_provider'))).toBe(true);
    expect(canAccessDomainByPermission(auth, () => false)).toBe(false);
  });
});

describe('canAccessSectionByPermission（域门槛继承 + 分区门槛叠加）', () => {
  it('分区显式门槛（auth/oauth-providers 需 auth:manage_provider）', () => {
    const auth = settingsDomains.find(d => d.id === 'auth')!;
    const oauth = auth.sections[1]; // path: auth/oauth-providers
    expect(oauth.permission).toBe('auth:manage_provider');
    expect(canAccessSectionByPermission(auth, oauth, (p: string) => p === 'auth:manage_provider')).toBe(true);
    expect(canAccessSectionByPermission(auth, oauth, (p: string) => p === 'user:read')).toBe(false);
  });

  it('分区无显式门槛 → 继承域门槛', () => {
    const site = settingsDomains.find(d => d.id === 'site')!;
    expect(canAccessSectionByPermission(site, site.sections[0], (p: string) => p === 'user:read')).toBe(true);
    expect(canAccessSectionByPermission(site, site.sections[0], () => false)).toBe(false);
  });

  it('域门槛不满足时分区一律不可见', () => {
    const operations = settingsDomains.find(d => d.id === 'operations')!;
    expect(canAccessSectionByPermission(operations, operations.sections[0], () => false)).toBe(false);
  });
});
