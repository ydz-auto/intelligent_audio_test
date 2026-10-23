/**
 * 系统设置域领域模型 —— camelCase
 * 站点选项 KV（/api/option/）、用户与角色（/api/v1/auth/users|roles）。
 * 仅 views/composables/store 允许从 '@/domain' import。
 */

/** 系统选项全量 KV（GET /api/option/ 返回扁平 dict；键见后端 SYSTEM_OPTION_DEFAULTS） */
export interface SystemOptions {
  [key: string]: string | number | boolean | string[] | null
}

/** 站点设置域常用键（便于页面显式读写，缺失时后端返回领域默认基线） */
export interface SiteSettings {
  /** 站点名称 */
  siteName?: string
  /** 站点 Logo（URL 或 base64） */
  siteLogo?: string
  /** 站点页脚文案 */
  siteFooter?: string
  /** 支持邮箱 */
  siteSupportEmail?: string
  /** 站点公告内容 */
  siteNotice?: string
  /** 导航模块开关：面包屑 */
  showBreadcrumb?: boolean
  /** 导航模块开关：算法切换器 */
  showAlgorithmSwitcher?: boolean
}

/** 用户管理（GET /api/v1/auth/users 条目；auth 服务回传字段，可选兜底） */
export interface SystemUser {
  id: number
  username: string
  email?: string
  /** active / inactive / locked */
  status?: string
  roleId?: number | null
  roleName?: string
  /** 生效权限（角色基线 ∪ overrides）权限码全集——仅详情查询；列表条目为空数组 */
  permissions?: string[]
  /** 生效权限数（列表列口径，INT-1465 列表接口返回的 permission_count；详情走 permissions.length） */
  permissionCount: number
  /** 附加权限 overrides 明细（仅详情查询返回；granted 过滤后的权限码列表） */
  extraPermissions?: string[]
  createdAt?: string
}

/** 角色管理（GET /api/v1/auth/roles 条目） */
export interface SystemRole {
  id: number
  name: string
  description?: string
  /** 权限码数组（admin 角色含 '*'） */
  permissions?: string[]
  /** 内置角色不可删除 */
  isSystem?: boolean
  userCount?: number
  createdAt?: string
}

/** 权限点（GET /api/v1/auth/permissions 条目） */
export interface PermissionItem {
  /** 权限点 ID（撤销用户附加权限时引用） */
  id?: number
  code: string
  description?: string
  /** 归属模块中文名（静态目录分组键） */
  module?: string
}

/** 用户列表（分页信封） */
export interface SystemUserPage {
  items: SystemUser[]
  total: number
  page: number
  perPage: number
  pages: number
}

/** 角色列表响应（roles 数组信封） */
export interface SystemRoleList {
  roles: SystemRole[]
}

/** 权限列表响应（permissions 数组信封） */
export interface PermissionList {
  permissions: PermissionItem[]
}

/**
 * 站点健康状态 Domain 模型 —— INT-745（关于页）
 */
export interface HealthStatus {
  /** ok / error 等 */
  status: string
  /** 服务名（api_gateway） */
  service: string
  /** 平台版本（Config.PLATFORM_VERSION，如 V9.7.31） */
  version: string
  /** 当前数据库名 */
  database: string
}
