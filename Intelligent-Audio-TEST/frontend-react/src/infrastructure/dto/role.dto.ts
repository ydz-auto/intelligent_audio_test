/**
 * 角色 / 权限点 DTO（infrastructure/dto 层；snake_case ↔ camelCase 唯一转换层）。
 * 对照 api_gateway role_bp.py + auth_service servicer 响应契约：
 * GET /auth/roles → { roles: [{ id, name, description, permissions, is_system }] }；
 * GET /auth/permissions → { permissions: [{ id, name, description }] }——后端权限点
 * `name` 字段承载权限码（如 'task:read'），`description` 为中文描述（seed_rbac 原值）。
 * 模块分组（22 业务模块中文名）属前端领域事实（domain/models/permission.ts），
 * 本层负责把扁平权限点回填到模块骨架。
 */
import type { PermissionModule } from '@/domain/models/permission'
import { PERMISSION_CATALOG } from '@/domain/models/permission'
import { ROLE_META, type PlatformRole, type RoleCode } from '@/domain/models/role'

export interface RoleDto {
  id: number
  name: string
  description: string
  permissions: string[]
  is_system: boolean
}

export interface RolesResultDto {
  roles: RoleDto[]
}

export interface PermissionDto {
  /** 权限点主键（seed 自增） */
  id: number
  /** 权限码（如 'task:read'；后端 `name` 字段承载） */
  name: string
  /** 中文描述（如 '查看任务'） */
  description: string
}

export interface PermissionsResultDto {
  permissions: PermissionDto[]
}

/** 后端角色 dict → Domain PlatformRole（code=后端 name；系统角色中文名取 ROLE_META，自定义角色回退 name） */
export function toPlatformRole(raw: RoleDto): PlatformRole {
  const code = raw.name ?? ''
  return {
    id: String(raw.id),
    code,
    name: ROLE_META[code as RoleCode]?.name ?? raw.name ?? raw.description ?? code,
    description: raw.description ?? '',
    isSystem: Boolean(raw.is_system),
    permissions: Array.isArray(raw.permissions) ? raw.permissions : [],
    // 后端角色列表不返回 user_count；getRoles 以用户列表计数补全（≤100 分页上限）
    userCount: 0,
  }
}

/**
 * 后端扁平权限点 → Domain PermissionModule[]。
 * 模块骨架取领域 PERMISSION_CATALOG（22 模块中文名 + 码归属）；后端码/描述回填，
 * 后端多出目录未收录的权限点按码前缀归入兜底模块（seed 与目录同源，正常不触发）。
 */
export function toPermissionModules(raw: PermissionDto[]): PermissionModule[] {
  const descByCode = new Map((raw ?? []).map((permission) => [permission.name, permission.description]))
  const modules: PermissionModule[] = PERMISSION_CATALOG.map((module) => ({
    id: module.id,
    name: module.name,
    permissions: module.permissions.map((permission) => ({
      code: permission.code,
      name: descByCode.get(permission.code) ?? permission.name,
      module: module.name,
    })),
  }))

  const known = new Set(
    PERMISSION_CATALOG.flatMap((module) => module.permissions.map((permission) => permission.code))
  )
  const extra = (raw ?? []).filter((permission) => !known.has(permission.name))
  if (extra.length > 0) {
    const bucket = new Map<string, Array<{ code: string; name: string; module: string }>>()
    for (const permission of extra) {
      const prefix =
        permission.name === '*'
          ? 'wildcard'
          : permission.name.split(':')[0] || 'other'
      const list = bucket.get(prefix) ?? []
      list.push({
        code: permission.name,
        name: permission.description || permission.name,
        module: prefix,
      })
      bucket.set(prefix, list)
    }
    for (const [prefix, permissions] of bucket) {
      modules.push({ id: prefix, name: prefix, permissions })
    }
  }
  return modules
}
