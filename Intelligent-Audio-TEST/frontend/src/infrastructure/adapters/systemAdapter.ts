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
  if (!dto) return { id: 0, username: '', extraPermissions: [] }
  return {
    id: toSafeNumber(dto.id),
    username: dto.username ?? '',
    email: dto.email ?? '',
    status: dto.status ?? 'active',
    roleId: dto.role_id ?? null,
    roleName: dto.role_name ?? '',
    permissions: dto.permissions ?? [],
    // 附加权限 overrides 明细（仅详情查询返回；list 不含 → []）
    extraPermissions: (dto.overrides ?? [])
      .filter(o => o.granted)
      .map(o => o.code),
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

/**
 * 权限码前缀 → 中文模块名（静态目录照 seed_rbac.py 模块归属；
 * 权限码本身无模块字段，按前缀分组，与 React iam-adapter 静态目录同源）。
 */
const PERMISSION_MODULE_NAMES: Record<string, string> = {
  task: '任务',
  published_task: '已发布任务',
  testcase: '测试用例',
  audio: '音频',
  device: '被测设备',
  playback: '播放设备',
  spl: '声压级',
  digital_spl: '数字域 RMS→SPL',
  api_config: 'API 配置',
  report: '报告',
  benchmark: 'Benchmark 排行',
  evaluation: '评估',
  algorithm: '算法配置',
  group: '用例分组',
  tag: '标签',
  log: '日志',
  home: '首页',
  lab: '实验室',
  status: '站点状态',
  option: '系统选项',
  sse: 'SSE',
  user: '用户',
  role: '角色',
  auth: '认证',
  permission: '权限',
}

/** 权限码 → 归属模块中文名（'*' 独立成组；未知前缀回退原始前缀）。
 *  前缀取首个分隔段（冒号或点，如 task:read / task.result.review / report:studio:edit）。 */
export function permissionModuleName(code: string): string {
  if (code === '*') return '超级权限'
  const prefix = code.split(/[:.]/)[0]
  return PERMISSION_MODULE_NAMES[prefix] ?? prefix
}

/** 权限点 → Domain（name 即权限码；id 供差量撤销引用；module 按静态目录分组） */
export function toPermissionItem(dto: PermissionItemDto | null | undefined): PermissionItem {
  if (!dto) return { code: '', description: '', module: '' }
  const code = dto.name ?? ''
  return {
    id: toSafeNumber(dto.id),
    code,
    description: dto.description ?? '',
    module: permissionModuleName(code),
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
