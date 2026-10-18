/**
 * 个人中心页用例（application 层，13_个人中心 §3/§4/§7）：
 * 身份（auth store 会话缓存）+ 个人数据快捷区（我的收藏计数）+ OAuth 绑定 +
 * 权限概览分组 + 区块可见性门槛；改密/资料编辑为待 FEAT 壳（入口保留、提交即提示）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../../store/authStore'
import { profilePort } from './profilePort'
import { useModalControl } from '../modal/useModal'
import { MODAL_TYPES } from '../modal/constants'
import { useNotification } from '../modal/useNotification'
import type { OAuthBinding, OAuthProvider } from '../../domain/model/auth'
import type { FavoriteCounts } from '../../domain/model/profile'

/** 系统设置快捷行门槛（INT-417 收窄四码；00 总表 §2.6 头像下拉系统设置项同集合） */
const SYSTEM_SETTINGS_PERMISSIONS = ['user:read', 'role:read', 'auth:manage_provider', 'log:manage']

/** 用户名哈希取色（照 13_个人中心 §1.2 lib/avatar.ts：hsl(hash%360, 54+hash%8%, 52+(hash>>4)%8%)） */
export function hashUsername(username: string): number {
  let hash = 0
  for (let i = 0; i < username.length; i++) {
    hash = ((hash << 5) - hash + username.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
}

export function getUserAvatarStyle(username: string): string {
  const hash = hashUsername(username)
  return `hsl(${hash % 360}, ${54 + (hash % 8)}%, ${52 + ((hash >> 4) % 8)}%)`
}

/** 头像 fallback：用户名首字符大写 */
export function getUserAvatarFallback(username: string): string {
  const trimmed = username.trim()
  return trimmed ? trimmed.charAt(0).toUpperCase() : '?'
}

/** 权限码按模块前缀分组（§3.4.1）：{模块}（{n}）组头 + 码列表，去重排序 */
export function groupPermissions(permissions: string[]): Array<{ module: string; codes: string[] }> {
  const groups = new Map<string, Set<string>>()
  for (const code of permissions) {
    const module = code.includes(':') ? code.split(':')[0] : code
    const set = groups.get(module) ?? new Set<string>()
    set.add(code)
    groups.set(module, set)
  }
  return [...groups.entries()]
    .map(([module, codes]) => ({ module, codes: [...codes].sort() }))
    .sort((a, b) => a.module.localeCompare(b.module))
}

export function useProfilePage() {
  const authStore = useAuthStore()
  const route = useRoute()
  const router = useRouter()
  const modalControl = useModalControl()
  const notification = useNotification()

  // ===== 身份（auth store 会话缓存；/auth/me 缺 roleName → 前端缓存兜底）=====
  const user = computed(() => authStore.user)
  const username = computed(() => authStore.username)
  const roleName = computed(() => authStore.roleName)
  const permissions = computed(() => authStore.permissions)
  const avatarStyle = computed(() => getUserAvatarStyle(username.value))
  const avatarFallback = computed(() => getUserAvatarFallback(username.value))

  // ===== 个人数据快捷区 =====
  const favorites = ref<FavoriteCounts>({ task: 0, report: 0, testcase: 0 })
  const favoritesLoading = ref(false)
  const favoritesTotal = computed(
    () => favorites.value.task + favorites.value.report + favorites.value.testcase
  )

  /** 「我的任务」格（task:read）；「我的报告」格（report:read）——不满足整格隐藏 */
  const canSeeMyTasks = computed(() => authStore.hasPermission('task:read'))
  const canSeeMyReports = computed(() => authStore.hasPermission('report:read'))

  // ===== OAuth 绑定（§3.5.2）=====
  const bindings = ref<OAuthBinding[]>([])
  const providers = ref<OAuthProvider[]>([])
  const loadingBindings = ref(false)
  const binding = ref(false)
  const unbinding = ref(false)
  const bindingsLocked = computed(() => binding.value || unbinding.value)

  /** 提供方 × 绑定态合并行（提供方启用项全量渲染；绑定信息叠加到对应行） */
  const bindingRows = computed(() => {
    const bindingMap = new Map(bindings.value.map((b) => [b.providerId, b]))
    return providers.value.map((provider) => ({ provider, binding: bindingMap.get(provider.id) }))
  })

  const emptyBindings = computed(() => providers.value.length === 0)

  async function loadOAuthBindings() {
    loadingBindings.value = true
    try {
      const [bindingList, providerList] = await Promise.all([
        profilePort.listOAuthBindings(),
        profilePort.listPublicOAuthProviders(),
      ])
      bindings.value = bindingList
      providers.value = providerList
    } catch (e: any) {
      notification.error(e?.detail || e?.message || '加载绑定信息失败')
    } finally {
      loadingBindings.value = false
    }
  }

  /** 绑定：整页跳转授权（intent=bind）→ 回调携 bind_ticket 回本页落库 */
  function startBind(slug: string) {
    if (bindingsLocked.value) return
    window.location.href = profilePort.getOAuthAuthorizeUrl(slug, 'bind')
  }

  /** 携绑定票据落库（bind_ticket 回调回传） */
  async function completeBind(ticket: string) {
    binding.value = true
    try {
      await profilePort.completeOAuthBinding(ticket)
      notification.success('绑定成功')
      await loadOAuthBindings()
    } catch (e: any) {
      notification.error(`绑定失败：${e?.detail || e?.message || '未知原因'}`)
    } finally {
      binding.value = false
    }
  }

  /** 解绑：BASIC_CONFIRM（danger）确认 → DELETE 落库 → 刷新 */
  async function unbind(b: OAuthBinding) {
    try {
      await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '确认解绑',
        content: `确认解绑「${b.providerName}」？解绑后将无法使用该第三方账号登录。`,
        confirmText: '解绑',
        cancelText: '取消',
        danger: true,
      })
    } catch {
      return // 用户取消
    }
    unbinding.value = true
    try {
      await profilePort.unbindOAuthProvider(b.providerId)
      notification.success('解绑成功')
      await loadOAuthBindings()
    } catch (e: any) {
      notification.error(`解绑失败：${e?.detail || e?.message || '未知原因'}`)
    } finally {
      unbinding.value = false
    }
  }

  // ===== 账号安全壳（F2 改密 / F3 资料编辑，待 FEAT）=====
  function openChangePassword() {
    return modalControl.open(MODAL_TYPES.CHANGE_PASSWORD, { username: username.value })
  }

  function openEditProfile() {
    return modalControl.open(MODAL_TYPES.EDIT_PROFILE, { username: username.value })
  }

  // ===== 权限概览 =====
  const groupedPermissions = computed(() => groupPermissions(permissions.value))
  const isWildcard = computed(() => permissions.value.includes('*'))

  // ===== 快捷入口 =====
  const canSeeSettingsQuickLink = computed(() =>
    SYSTEM_SETTINGS_PERMISSIONS.some((code) => authStore.hasPermission(code))
  )

  // ===== 复制用户 ID =====
  async function copyUserId() {
    try {
      await navigator.clipboard.writeText(String(user.value?.id ?? ''))
      notification.success('用户 ID 已复制')
    } catch {
      notification.warning('复制失败，请手动复制')
    }
  }

  // ===== 绑定回调（bind_ticket/bind_error）onMount 消化（§3.5.2）=====
  async function handleBindCallback() {
    const bindTicket = route.query.bind_ticket as string | undefined
    const bindError = route.query.bind_error as string | undefined
    if (bindTicket || bindError) {
      router.replace({ query: {} })
    }
    if (bindError) {
      notification.error(`绑定失败：${bindError}`)
    }
    if (bindTicket) {
      await completeBind(bindTicket)
      return
    }
  }

  async function loadFavorites() {
    favoritesLoading.value = true
    try {
      const ids = await profilePort.listFavoriteIds('')
      favorites.value = {
        task: ids.task.length,
        report: ids.report.length,
        testcase: ids.testcase.length,
      }
    } catch (e: any) {
      console.warn('[useProfilePage] 收藏计数加载失败', e)
    } finally {
      favoritesLoading.value = false
    }
  }

  onMounted(async () => {
    await handleBindCallback()
    await Promise.all([loadOAuthBindings(), loadFavorites()])
  })

  return {
    user,
    username,
    roleName,
    permissions,
    avatarStyle,
    avatarFallback,
    // 快捷区
    favorites,
    favoritesLoading,
    favoritesTotal,
    canSeeMyTasks,
    canSeeMyReports,
    // 绑定
    bindings,
    providers,
    bindingRows,
    emptyBindings,
    loadingBindings,
    bindingsLocked,
    startBind,
    unbind,
    // 壳
    openChangePassword,
    openEditProfile,
    // 权限概览
    groupedPermissions,
    isWildcard,
    // 快捷入口
    canSeeSettingsQuickLink,
    copyUserId,
  }
}
