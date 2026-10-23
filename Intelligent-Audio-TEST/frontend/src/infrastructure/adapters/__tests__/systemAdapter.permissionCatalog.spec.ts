/**
 * 系统设置权限目录 adapter 契约测试（INT-743 P1-2/P3-2）
 *
 * 覆盖 GET /auth/permissions 实际返回 {id, name, description}（name 即权限码，
 * seed_rbac.py 语义）→ Domain 的显式映射：权限码展示、模块分组（静态目录）、
 * 权限点 ID（撤销引用）、用户 overrides 明细。防「复用既有 DTO 后适配器读到空
 * code/module、权限码空白」的接线回归。
 */
import { describe, it, expect } from 'vitest';
import {
  toPermissionItem,
  toPermissionList,
  toSystemUser,
  permissionModuleName,
} from '../systemAdapter';

describe('toPermissionItem（GET /auth/permissions：{id, name, description}）', () => {
  it('name 即权限码：映射 code + id + description + 模块分组', () => {
    const result = toPermissionItem({
      id: 1,
      name: 'task:read',
      description: '查看任务',
    });
    expect(result).toEqual({
      id: 1,
      code: 'task:read',
      description: '查看任务',
      module: '任务',
    });
  });

  it('role:read 归「角色」模块；user:read 归「用户」模块', () => {
    expect(toPermissionItem({ id: 2, name: 'role:read' })?.module).toBe('角色');
    expect(toPermissionItem({ id: 3, name: 'user:read' })?.module).toBe('用户');
    expect(toPermissionItem({ id: 4, name: 'log:manage' })?.module).toBe('日志');
  });

  it('未知前缀回退原始前缀（非空、可辨认）', () => {
    expect(toPermissionItem({ id: 9, name: 'weird:foo' })?.module).toBe('weird');
    expect(toPermissionItem({ id: 9, name: 'weird:foo' })?.code).toBe('weird:foo');
  });

  it('通配 * 独立成「超级权限」模块（admin 角色 0 勾选场景可辨认）', () => {
    expect(toPermissionItem({ id: 117, name: '*', description: '超级权限（通配所有操作）' })).toEqual({
      id: 117,
      code: '*',
      description: '超级权限（通配所有操作）',
      module: '超级权限',
    });
  });

  it('多段权限码按首段分组（task.result.review → 任务；report:studio:edit → 报告）', () => {
    expect(toPermissionItem({ id: 13, name: 'task.result.review' })?.module).toBe('任务');
    expect(toPermissionItem({ id: 14, name: 'report:studio:edit' })?.module).toBe('报告');
  });

  it('null / 空条目兜底为空项，不产生 undefined code', () => {
    expect(toPermissionItem(null)).toEqual({ code: '', description: '', module: '' });
    expect(toPermissionItem(undefined)).toEqual({ code: '', description: '', module: '' });
  });
});

describe('toPermissionList', () => {
  it('逐条复用 toPermissionItem，保留 id/code/module', () => {
    const result = toPermissionList({
      permissions: [
        { id: 1, name: 'task:read', description: '查看任务' },
        { id: 2, name: 'role:read', description: '查看角色' },
      ],
    });
    expect(result.permissions).toHaveLength(2);
    expect(result.permissions[0]).toMatchObject({ id: 1, code: 'task:read', module: '任务' });
    expect(result.permissions[1]).toMatchObject({ id: 2, code: 'role:read', module: '角色' });
  });

  it('null 兜底为空列表', () => {
    expect(toPermissionList(null).permissions).toEqual([]);
  });
});

describe('permissionModuleName（静态目录）', () => {
  it('已知前缀 → 中文模块名', () => {
    expect(permissionModuleName('algorithm:read')).toBe('算法配置');
    expect(permissionModuleName('audio:upload')).toBe('音频');
    expect(permissionModuleName('published_task:read')).toBe('已发布任务');
    expect(permissionModuleName('digital_spl:read')).toBe('数字域 RMS→SPL');
    expect(permissionModuleName('api_config:test')).toBe('API 配置');
  });

  it('未知前缀 → 原始前缀；* → 超级权限', () => {
    expect(permissionModuleName('unknown:x')).toBe('unknown');
    expect(permissionModuleName('*')).toBe('超级权限');
  });
});

describe('toSystemUser（用户详情 overrides → extraPermissions）', () => {
  it('granted 覆盖 → 附加权限码列表（基线口径，对齐 React）', () => {
    const result = toSystemUser({
      id: 1,
      username: 'alice',
      permissions: ['task:read', 'role:read'],
      overrides: [
        { permission_id: 1, code: 'task:read', granted: true },
        { permission_id: 9, code: 'log:manage', granted: true },
        { permission_id: 2, code: 'role:read', granted: false },
      ],
    });
    expect(result.extraPermissions).toEqual(['task:read', 'log:manage']);
    // 生效权限（角色基线 ∪ overrides）保持原样
    expect(result.permissions).toEqual(['task:read', 'role:read']);
  });

  it('无 overrides（列表条目）→ extraPermissions 空数组', () => {
    expect(toSystemUser({ id: 2, username: 'bob' }).extraPermissions).toEqual([]);
  });

  it('列表 permission_count → permissionCount（INT-1465 列表瘦身，不再回 permissions 全集）', () => {
    const result = toSystemUser({ id: 3, username: 'carol', role_name: 'tester', permission_count: 91 });
    expect(result.permissionCount).toBe(91);
    // 列表条目不再携带 permissions → 兜底空数组，列口径只认 permissionCount
    expect(result.permissions).toEqual([]);
  });

  it('缺 permission_count（详情条目 / 旧契约）→ permissionCount 兜底 0，不产生 NaN', () => {
    expect(toSystemUser({ id: 4, username: 'dave' }).permissionCount).toBe(0);
  });

  it('null 兜底', () => {
    expect(toSystemUser(null)).toEqual({ id: 0, username: '', extraPermissions: [], permissionCount: 0 });
  });
});
