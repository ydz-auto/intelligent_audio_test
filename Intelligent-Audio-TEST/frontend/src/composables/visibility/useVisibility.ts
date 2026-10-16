/**
 * 可见性（INT-423/467）前端共享助手 —— 新建偏好 / owner 判定 / 动作入口可见性。
 *
 * 依赖方向：Presentation → Application(Port) → Infrastructure；本模块只读 authStore
 * 与 localStorage，不触碰 infrastructure（可见性切换走各资源 Port 的 updateVisibility）。
 */
import { Visibility, type VisibilityType } from '@/domain/enums'
import { useAuthStore } from '@/store/authStore'

/** localStorage 新建可见性偏好键（INT-467：各表单新建默认沿用） */
export const VISIBILITY_PREF_KEY = 'visibility_pref'

/** 可见性筛选 chips 选项（「全部」由 BadgeFilter showAll 承担，此处只给具体值） */
export const VISIBILITY_FILTER_OPTIONS: { value: string; label: string }[] = [
  { value: Visibility.SHARED, label: '共享' },
  { value: Visibility.PRIVATE, label: '私有' },
]

/** 读取新建偏好（缺省 shared；非法值回落 shared） */
export function getVisibilityPref(): VisibilityType {
  try {
    const v = localStorage.getItem(VISIBILITY_PREF_KEY)
    if (v === Visibility.PRIVATE || v === Visibility.SHARED) return v
  } catch { /* 隐私模式/序列化异常忽略 */ }
  return Visibility.SHARED
}

/** 写入新建偏好（选择器切换时记录，各表单新建一致沿用） */
export function setVisibilityPref(v: VisibilityType): void {
  try { localStorage.setItem(VISIBILITY_PREF_KEY, v) } catch { /* 隐私模式忽略 */ }
}

/** 是否为管理员（permissions 含 * 通配；AUTH_MODE=off 后端注入 ['*'] 恒过） */
export function isAdminUser(): boolean {
  const auth = useAuthStore()
  return auth.hasPermission('*')
}

/** owner 判定：createdByUserId 与当前登录用户 id 一致 */
export function isOwner(createdByUserId?: number | null): boolean {
  const auth = useAuthStore()
  const uid = auth.user?.id
  return createdByUserId != null && uid != null && Number(createdByUserId) === Number(uid)
}

/**
 * 详情/编辑入口可见性（INT-423/467 前端口径）：
 * - 共享资源 → 回落既有权限点（页面既有 can() 承担，此处恒放行）
 * - 私有资源 → 仅 owner 可编辑/删除；admin 可见但入口隐藏（对非 owner 显示 403 提示）
 * - 私有 + owner 缺失（AUTH_MODE=off 单用户开发态，owner 列 NULL）→ 视为当前用户资源放行
 */
export function canEditResource(
  resource: { visibility?: string | null; createdByUserId?: number | null } | null | undefined,
): boolean {
  if (!resource) return false
  if (resource.visibility !== Visibility.PRIVATE) return true
  if (resource.createdByUserId == null) return true
  return isOwner(resource.createdByUserId)
}

/**
 * 网络/后端错误 → 统一「资源不存在或无权访问」语义（INT-467：路由直达不泄露资源名）。
 * 后端详情对私有非 owner 统一 404（防探测口径）；前端据此展示通用文案并可选跳 404 页。
 */
export function isNotFoundOrForbidden(error: unknown): boolean {
  const e = error as { code?: number; status?: number }
  const code = Number(e?.code ?? e?.status)
  return code === 404 || code === 403 || code === 400
}
