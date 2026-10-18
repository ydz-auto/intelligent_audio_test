/**
 * IAM/系统设置 DTO → 领域模型适配器（infrastructure 层，INT-729 接线）。
 * snake_case → camelCase 收敛只发生在本层；interfaces/application 只消费
 * camelCase 领域对象。角色/权限码与中文名映射照 ROLE_META / PERMISSION_CATALOG
 * 事实来源（seed_rbac.py，INT-347 §2.0）。
 */
import { ROLE_META } from '@/domain/models/role'
import type { PlatformRole } from '@/domain/models/role'
import { PERMISSION_CATALOG } from '@/domain/models/permission'
import type { Permission, PermissionModule } from '@/domain/models/permission'
import type { OAuthProvider, OAuthFieldMapping } from '@/domain/models/oauth-provider'
import type { LogArchiveStatus } from '@/domain/models/log-archive'
import type { PlatformUser, PlatformUserStatus } from '@/domain/models/user'
import type {
  AuthPermissionDto,
  AuthRoleDto,
  AuthUserDto,
  LogArchiveStatusDto,
  OAuthProviderAdminDto,
} from '@/infrastructure/dto/iam.dto'

/** 后端 status（active/inactive/locked）→ 领域（active/disabled/locked） */
export function toPlatformUserStatus(status: string): PlatformUserStatus {
  if (status === 'inactive') return 'disabled'
  if (status === 'locked') return 'locked'
  return 'active'
}

/** 领域 status → 后端 status（update 载荷用） */
export function toBackendUserStatus(status: PlatformUserStatus): string {
  if (status === 'disabled') return 'inactive'
  return status
}

export function toPlatformUser(dto: AuthUserDto): PlatformUser {
  const roleCode = dto.role_name || ''
  return {
    id: String(dto.id),
    username: dto.username,
    displayName: dto.display_name ?? '',
    email: dto.email ?? '',
    roleCode,
    roleName: ROLE_META[roleCode as keyof typeof ROLE_META]?.name ?? roleCode,
    status: toPlatformUserStatus(dto.status),
    /** 生效权限（角色基线 ∪ overrides）——列表「生效权限数」列口径 */
    permissions: dto.permissions ?? [],
    /** 附加权限 overrides 明细（详情查询返回；列表为空数组） */
    extraPermissions: (dto.overrides ?? [])
      .filter((o) => o.granted)
      .map((o) => o.code),
    createdAt: dto.created_at ?? '',
  }
}

export function toPlatformRole(dto: AuthRoleDto): PlatformRole {
  return {
    id: String(dto.id),
    code: dto.name,
    name: ROLE_META[dto.name as keyof typeof ROLE_META]?.name ?? dto.name,
    description: dto.description ?? '',
    isSystem: Boolean(dto.is_system),
    permissions: dto.permissions ?? [],
    userCount: 0,
  }
}

/** 模块前缀 → 中文模块名（静态目录外的后端新增前缀） */
const EXTRA_MODULE_NAME: Record<string, string> = {
  lab: '实验室',
  status: '站点状态',
  option: '系统选项',
  'task.result.review': '任务结果复核',
}

/**
 * 后端全量权限点 → 分组模块目录。
 * 已知权限码按静态 PERMISSION_CATALOG 模块归属（保留 22 模块分组与顺序）；
 * 后端新增权限码按前缀分组（模块名取 EXTRA_MODULE_NAME，未知前缀用原始前缀）。
 */
export function toPermissionModules(dtos: AuthPermissionDto[]): PermissionModule[] {
  const codeModuleId = new Map<string, string>()
  for (const module of PERMISSION_CATALOG) {
    for (const permission of module.permissions) {
      codeModuleId.set(permission.code, module.id)
    }
  }
  const knownGroups = new Map<string, Permission[]>()
  const extraGroups = new Map<string, Permission[]>()
  for (const dto of dtos) {
    const permission: Permission = {
      id: dto.id,
      code: dto.name,
      name: dto.description || dto.name,
      module: dto.name,
    }
    const moduleId = codeModuleId.get(dto.name)
    if (moduleId) {
      permission.module = moduleId
      const list = knownGroups.get(moduleId)
      if (list) list.push(permission)
      else knownGroups.set(moduleId, [permission])
    } else {
      const prefix = dto.name.split(':')[0] || dto.name
      permission.module = prefix
      const list = extraGroups.get(prefix)
      if (list) list.push(permission)
      else extraGroups.set(prefix, [permission])
    }
  }
  const modules: PermissionModule[] = []
  for (const module of PERMISSION_CATALOG) {
    const permissions = knownGroups.get(module.id)
    if (permissions && permissions.length > 0) {
      modules.push({ id: module.id, name: module.name, permissions })
    }
  }
  const extraIds = [...extraGroups.keys()].sort((a, b) => a.localeCompare(b, 'zh'))
  for (const prefix of extraIds) {
    modules.push({
      id: prefix,
      name: EXTRA_MODULE_NAME[prefix] ?? prefix,
      permissions: extraGroups.get(prefix) as Permission[],
    })
  }
  for (const module of modules) {
    module.permissions.sort((a, b) => a.code.localeCompare(b.code))
  }
  return modules
}

const FIELD_MAP = {
  userIdentifier: 'user_id_field',
  userName: 'username_field',
  displayName: 'display_name_field',
  email: 'email_field',
} as const

export function toOAuthProvider(dto: OAuthProviderAdminDto): OAuthProvider {
  return {
    id: String(dto.id),
    name: dto.name,
    slug: dto.slug,
    icon: dto.icon || undefined,
    status: dto.enabled ? 'enabled' : 'disabled',
    clientId: dto.client_id,
    clientSecret: dto.has_client_secret ? '••••••••••••••••' : undefined,
    authorizationEndpoint: dto.authorize_url,
    tokenEndpoint: dto.token_url,
    userinfoEndpoint: dto.userinfo_url,
    scopes: dto.scopes,
    fieldMapping: {
      userIdentifier: dto.user_id_field,
      userName: dto.username_field,
      displayName: dto.display_name_field,
      email: dto.email_field,
    },
    createdAt: dto.created_at,
  }
}

/** OAuthProvider 领域输入 → 后端 snake_case 载荷 */
export function toOAuthProviderCreatePayload(
  input: Omit<OAuthProvider, 'id' | 'createdAt'> & { clientSecret?: string }
): Record<string, string | boolean> {
  const payload: Record<string, string | boolean> = {
    name: input.name,
    slug: input.slug,
    icon: input.icon ?? '',
    enabled: input.status === 'enabled',
    client_id: input.clientId,
    client_secret: input.clientSecret ?? '',
    authorize_url: input.authorizationEndpoint,
    token_url: input.tokenEndpoint,
    userinfo_url: input.userinfoEndpoint,
    scopes: input.scopes,
  }
  for (const [domainField, backendField] of Object.entries(FIELD_MAP)) {
    payload[backendField] =
      input.fieldMapping?.[domainField as keyof OAuthFieldMapping] ?? ''
  }
  return payload
}

export function toLogArchiveStatus(dto: LogArchiveStatusDto): LogArchiveStatus {
  return {
    totalLogs: dto.totalLogs ?? 0,
    hotLogs: dto.hotLogs ?? 0,
    coldLogs: dto.coldLogs ?? 0,
    archiveDir: dto.archiveDir ?? '',
    taskArchives: dto.taskArchives ?? 0,
    caseArchives: dto.caseArchives ?? 0,
    otherArchives: dto.otherArchives ?? 0,
  }
}
