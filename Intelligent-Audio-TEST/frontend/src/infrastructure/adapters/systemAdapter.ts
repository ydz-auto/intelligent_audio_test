/**
 * 系统设置域 Adapter —— snake_case DTO ↔ camelCase Domain
 */
import type {
  SystemUser,
  SystemUserPage,
  SystemRole,
  SystemRoleList,
  PermissionItem,
  PermissionList,
  SiteSettings,
  SystemOptions,
} from '../../domain/model/system'
import { toPaginated, toSafeNumber } from './commonAdapter'
import type { PaginatedDto } from '../dto'
import type {
  UserItemDto,
  RoleItemDto,
  PermissionItemDto,
  RoleListDto,
  PermissionListDto,
} from '../dto/systemDto'

/** 用户条目 → Domain */
export function toSystemUser(dto: UserItemDto | null | undefined): SystemUser {
  if (!dto) return { id: 0, username: '' }
  return {
    id: toSafeNumber(dto.id),
    username: dto.username ?? '',
    email: dto.email ?? '',
    status: dto.status ?? 'active',
    roleId: dto.role_id ?? null,
    roleName: dto.role_name ?? '',
    permissions: dto.permissions ?? [],
    createdAt: dto.created_at ?? '',
  }
}

/** 用户分页 → Domain */
export function toSystemUserPage(dto: PaginatedDto<UserItemDto> | null | undefined): SystemUserPage {
  const page = toPaginated(dto, toSystemUser)
  return {
    items: page.items,
    total: page.total,
    page: page.page,
    perPage: page.perPage,
    pages: page.pages,
  }
}

/** 角色条目 → Domain */
export function toSystemRole(dto: RoleItemDto | null | undefined): SystemRole {
  if (!dto) return { id: 0, name: '' }
  return {
    id: toSafeNumber(dto.id),
    name: dto.name ?? '',
    description: dto.description ?? '',
    permissions: dto.permissions ?? [],
    isSystem: !!dto.is_system,
    userCount: toSafeNumber(dto.user_count),
    createdAt: dto.created_at ?? '',
  }
}

/** 角色列表 → Domain */
export function toSystemRoleList(dto: RoleListDto | null | undefined): SystemRoleList {
  return { roles: (dto?.roles ?? []).map(toSystemRole) }
}

/** 权限点 → Domain */
export function toPermissionItem(dto: PermissionItemDto | null | undefined): PermissionItem {
  if (!dto) return { code: '' }
  return {
    code: dto.code ?? '',
    description: dto.description ?? '',
    module: dto.module ?? '',
  }
}

/** 权限列表 → Domain */
export function toPermissionList(dto: PermissionListDto | null | undefined): PermissionList {
  return { permissions: (dto?.permissions ?? []).map(toPermissionItem) }
}

/** 站点 KV 取子集 → SiteSettings（显式字段映射，缺省回退） */
export function toSiteSettings(options: SystemOptions): SiteSettings {
  const value = (key: string): string =>
    typeof options[key] === 'string' ? String(options[key]) : ''
  const bool = (key: string): boolean | undefined => {
    const v = options[key]
    if (v === undefined || v === null) return undefined
    if (typeof v === 'boolean') return v
    if (v === 'true' || v === '1') return true
    if (v === 'false' || v === '0') return false
    return undefined
  }
  return {
    siteName: value('site.name'),
    siteLogo: value('site.logo'),
    siteFooter: value('site.footer'),
    siteSupportEmail: value('site.support_email'),
    siteNotice: value('site.notice'),
    showBreadcrumb: bool('site.navigation.show_breadcrumb'),
    showAlgorithmSwitcher: bool('site.navigation.show_algorithm_switcher'),
  }
}
