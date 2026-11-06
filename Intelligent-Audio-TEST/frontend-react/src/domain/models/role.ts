/**
 * 角色领域模型（domain 层）。
 * 事实来源：seed_rbac.py:174-253（五系统角色 + 角色×权限串全量，INT-347 §2.0 实测）。
 * 字段口径沿用 auth_service/domain/entities/role.py：is_system 内置角色不可删除、
 * admin 的 `*` 不可移除（role_bp.py:56 实测约束）。
 */

export type RoleCode = 'admin' | 'tester' | 'algo_engineer' | 'device_admin' | 'guest'

export type PlatformRole = {
  id: string
  code: RoleCode | string
  name: string
  description: string
  /** 系统内置角色不可删除（role.py is_system 实测） */
  isSystem: boolean
  /** 角色权限码集合（admin 持 `*` 通配） */
  permissions: string[]
  /** 引用用户数（列表列；mock 口径） */
  userCount: number
}

export const ROLE_META: Record<RoleCode, { name: string; description: string }> = {
  admin: { name: '超级管理员', description: '持有全部权限（通配 *），管理平台所有功能' },
  tester: {
    name: '测试工程师',
    description: '负责测试任务、用例、音频与报告的创建与执行',
  },
  algo_engineer: {
    name: '算法工程师',
    description: '负责算法配置、评估维度与报告发布',
  },
  device_admin: {
    name: '设备管理员',
    description: '负责被测设备、播放设备与 SPL 校准管理',
  },
  guest: { name: '游客', description: '只读访问报告与首页统计' },
}

/** 五系统角色（seed_rbac.py:174-180 ROLES 全量） */
export const SYSTEM_ROLES: PlatformRole[] = [
  {
    id: 'role-admin',
    code: 'admin',
    name: ROLE_META.admin.name,
    description: ROLE_META.admin.description,
    isSystem: true,
    permissions: ['*'],
    userCount: 1,
  },
  {
    id: 'role-tester',
    code: 'tester',
    name: ROLE_META.tester.name,
    description: ROLE_META.tester.description,
    isSystem: true,
    permissions: [
      'task:read', 'task:create', 'task:update', 'task:delete', 'task:execute',
      'task:merge', 'task:batch', 'task:reextract', 'task:publish',
      'task:export', 'task:import', 'task:cherry_pick',
      'published_task:read', 'published_task:execute', 'published_task:version',
      'published_task:archive',
      'testcase:read', 'testcase:create', 'testcase:update', 'testcase:delete',
      'testcase:copy', 'testcase:preview', 'testcase:import_export',
      'audio:read', 'audio:upload', 'audio:update', 'audio:delete',
      'audio:convert', 'audio:folder',
      'device:read',
      'api_config:read', 'api_config:create', 'api_config:update',
      'api_config:delete', 'api_config:test',
      'report:read', 'report:create', 'report:update', 'report:delete',
      'report:compare', 'report:download_log',
      'benchmark:ranking:read', 'benchmark:ranking:compute',
      'benchmark:baseline:read', 'benchmark:baseline:write',
      'benchmark:baseline:publish', 'benchmark:mapping:manage',
      'evaluation:read', 'evaluation:execute', 'evaluation:dim_manage',
      'evaluation:category_manage', 'evaluation:import_export',
      'algorithm:read', 'algorithm:case_param_manage',
      'group:read', 'group:create', 'group:update', 'group:delete',
      'tag:read', 'tag:create', 'tag:update', 'tag:delete',
      'log:read', 'log:manage', 'log:websocket',
      'home:read', 'home:refresh',
      'sse:read',
      'auth:login', 'auth:callback', 'auth:refresh', 'auth:logout', 'auth:me',
    ],
    userCount: 8,
  },
  {
    id: 'role-algo',
    code: 'algo_engineer',
    name: ROLE_META.algo_engineer.name,
    description: ROLE_META.algo_engineer.description,
    isSystem: true,
    permissions: [
      'task:read',
      'published_task:read',
      'testcase:read',
      'audio:read',
      'api_config:read',
      'report:read', 'report:create', 'report:update', 'report:publish',
      'report:compare', 'report:download_log',
      'benchmark:ranking:read', 'benchmark:ranking:compute',
      'benchmark:baseline:read', 'benchmark:baseline:write',
      'benchmark:baseline:publish', 'benchmark:mapping:manage',
      'evaluation:read', 'evaluation:dim_manage', 'evaluation:category_manage',
      'evaluation:import_export',
      'algorithm:read', 'algorithm:definition_manage', 'algorithm:group_manage',
      'algorithm:param_manage', 'algorithm:case_param_manage',
      'group:read',
      'tag:read',
      'log:read', 'log:websocket',
      'home:read',
      'sse:read',
      'auth:login', 'auth:callback', 'auth:refresh', 'auth:logout', 'auth:me',
    ],
    userCount: 3,
  },
  {
    id: 'role-device',
    code: 'device_admin',
    name: ROLE_META.device_admin.name,
    description: ROLE_META.device_admin.description,
    isSystem: true,
    permissions: [
      'device:read', 'device:create', 'device:update', 'device:delete',
      'device:control',
      'playback:read', 'playback:create', 'playback:update', 'playback:delete',
      'playback:control',
      'spl:read', 'spl:create', 'spl:update', 'spl:delete', 'spl:test_tone',
      'digital_spl:read', 'digital_spl:create', 'digital_spl:update', 'digital_spl:delete',
      'home:read',
      'sse:read',
      'auth:login', 'auth:callback', 'auth:refresh', 'auth:logout', 'auth:me',
    ],
    userCount: 2,
  },
  {
    id: 'role-guest',
    code: 'guest',
    name: ROLE_META.guest.name,
    description: ROLE_META.guest.description,
    isSystem: true,
    permissions: [
      'report:read', 'report:compare',
      'home:read',
      'sse:read',
      'auth:login', 'auth:callback', 'auth:refresh', 'auth:logout', 'auth:me',
    ],
    userCount: 2,
  },
]

/** 角色名 → 权限串解析（用户归属角色渲染；admin 通配由 hasPermission 处理） */
export function getSystemRole(code: string): PlatformRole | undefined {
  return SYSTEM_ROLES.find((role) => role.code === code)
}
