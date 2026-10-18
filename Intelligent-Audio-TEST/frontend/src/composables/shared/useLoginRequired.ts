/**
 * 公开页受限项引导 —— INT-745
 *
 * 公共页（首页门户/关于/文档/排行榜）里出现的业务入口（「开始测试」等）：
 *  - AUTH_MODE=off（现状部署）或已登录 → 直接导航
 *  - 未登录且后端启用认证 → 弹「需要登录」Dialog（5 秒倒计时）→ 跳 /login?redirect=
 * 对齐总表 §2.2 受限项口径（未登录=受限项，点击弹「需要登录」Dialog）。
 */
import type { RouteLocationRaw } from 'vue-router'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../store/authStore'
import { AuthMode, getEffectiveAuthMode } from '../../domain/enums'
import { useModalControl } from '../modal/useModal'
import { MODAL_TYPES } from '../modal/constants'

export function useLoginRequired() {
  const router = useRouter()
  const authStore = useAuthStore()
  const modal = useModalControl()

  /**
   * 受限业务入口点击统一出口。
   * @param to 目标路由（字符串路径或路由对象）
   * @param moduleName 需要登录对话框里的模块名（如「端到端测试」）
   */
  function navigateEntry(to: RouteLocationRaw, moduleName = '') {
    const authMode = getEffectiveAuthMode()
    if (authMode === AuthMode.OFF || authStore.isLoggedIn) {
      router.push(to)
      return
    }
    const path = typeof to === 'string' ? to : ((to as { path?: string }).path ?? '/')
    modal.open(MODAL_TYPES.LOGIN_REQUIRED, { moduleName, redirect: path })
      .then(() => {
        router.push({ name: 'login', query: { redirect: path } })
      })
      .catch(() => {
        // 用户取消：留在当前页
      })
  }

  return { navigateEntry }
}
