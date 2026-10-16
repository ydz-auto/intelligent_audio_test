/**
 * 用户与角色 mock 数据源（infrastructure 层，红线④：mock 常量）。
 * 用户形态对照 user_bp.py 契约（GET /users 分页 ≤100 + status/keyword/role_id 过滤）；
 * 角色/权限目录取 seed_rbac.py 事实（见 domain/models/role.ts、permission.ts）。
 */
import { PERMISSION_CATALOG } from '@/domain/models/permission'
import { SYSTEM_ROLES } from '@/domain/models/role'
import type { PlatformRole } from '@/domain/models/role'
import type { PlatformUser } from '@/domain/models/user'

export const MOCK_PLATFORM_USERS: PlatformUser[] = [
  {
    id: '1',
    username: 'admin',
    displayName: '演示管理员',
    email: 'admin@example.com',
    roleCode: 'admin',
    roleName: '超级管理员',
    status: 'active',
    extraPermissions: [],
    createdAt: '2026-01-15T09:00:00Z',
  },
  {
    id: '2',
    username: 'tester_zhang',
    displayName: '张测试',
    email: 'zhang@example.com',
    roleCode: 'tester',
    roleName: '测试工程师',
    status: 'active',
    extraPermissions: ['report:publish'],
    createdAt: '2026-02-02T03:30:00Z',
  },
  {
    id: '3',
    username: 'tester_li',
    displayName: '李测试',
    email: 'li@example.com',
    roleCode: 'tester',
    roleName: '测试工程师',
    status: 'disabled',
    extraPermissions: [],
    createdAt: '2026-02-10T07:15:00Z',
  },
  {
    id: '4',
    username: 'algo_wang',
    displayName: '王算法',
    email: 'wang@example.com',
    roleCode: 'algo_engineer',
    roleName: '算法工程师',
    status: 'active',
    extraPermissions: ['benchmark:ranking:compute'],
    createdAt: '2026-03-05T01:45:00Z',
  },
  {
    id: '5',
    username: 'device_zhao',
    displayName: '赵设备',
    email: 'zhao@example.com',
    roleCode: 'device_admin',
    roleName: '设备管理员',
    status: 'active',
    extraPermissions: [],
    createdAt: '2026-03-20T08:20:00Z',
  },
  {
    id: '6',
    username: 'guest_01',
    displayName: '访客一号',
    email: 'guest1@example.com',
    roleCode: 'guest',
    roleName: '游客',
    status: 'locked',
    extraPermissions: [],
    createdAt: '2026-04-11T02:10:00Z',
  },
  {
    id: '7',
    username: 'guest_02',
    displayName: '访客二号',
    email: 'guest2@example.com',
    roleCode: 'guest',
    roleName: '游客',
    status: 'active',
    extraPermissions: [],
    createdAt: '2026-05-01T06:55:00Z',
  },
]

/** mock：角色列表（系统角色 + 自定义示例角色） */
export const MOCK_PLATFORM_ROLES: PlatformRole[] = [
  ...SYSTEM_ROLES,
  {
    id: 'role-quality',
    code: 'quality_lead',
    name: '质量负责人',
    description: '在算法工程师基础上可导出报告日志（自定义角色示例）',
    isSystem: false,
    permissions: [
      'task:read',
      'testcase:read',
      'audio:read',
      'report:read', 'report:create', 'report:update', 'report:publish',
      'report:compare', 'report:download_log',
      'evaluation:read', 'evaluation:dim_manage',
      'algorithm:read',
      'log:read',
      'home:read',
      'sse:read',
      'auth:login', 'auth:callback', 'auth:refresh', 'auth:logout', 'auth:me',
    ],
    userCount: 1,
  },
]

/** mock：权限点目录（22 模块全量，仅只读暴露） */
export const MOCK_PERMISSION_CATALOG = PERMISSION_CATALOG

export async function fetchMockUsers(): Promise<PlatformUser[]> {
  return MOCK_PLATFORM_USERS
}

export async function fetchMockRoles(): Promise<PlatformRole[]> {
  return MOCK_PLATFORM_ROLES
}
