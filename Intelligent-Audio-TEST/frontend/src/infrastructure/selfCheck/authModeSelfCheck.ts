/**
 * 认证模式启动自检（INT-180）——Infrastructure 编排层
 *
 * 应用启动后拉取后端 /auth/mode（公开端点），与本地生效 VITE_AUTH_MODE
 * 比对（domain/services/authModeCheck 纯逻辑）；错位 → 控制台警告 +
 * 动态挂载页面提示条（两侧当前值 + 修正指引）。提示型自检：
 * 不阻塞启动、不阻塞登录；后端不可达 / 未回值（旧后端）静默跳过。
 */
import { createApp } from 'vue'
import { getEffectiveAuthMode } from '../../domain/enums'
import { checkAuthMode, type AuthModeCheckResult } from '../../domain/services/authModeCheck'
import { authApi } from '../api/authApi'
import AuthModeMismatchBanner from '../../components/common/AuthModeMismatchBanner.vue'

/** 错位时挂载页面提示条（独立根实例，不侵入应用组件树） */
export function showAuthModeMismatchBanner(result: AuthModeCheckResult): void {
  if (typeof document === 'undefined') return
  const mountEl = document.createElement('div')
  mountEl.dataset.authModeBanner = 'true'
  document.body.appendChild(mountEl)
  createApp(AuthModeMismatchBanner, {
    frontendMode: result.frontendMode,
    backendMode: result.backendMode,
    backendModeKnown: result.backendModeKnown,
  }).mount(mountEl)
}

/** 启动自检入口（fire-and-forget：任何失败静默，不影响启动与登录） */
export function runAuthModeSelfCheck(): void {
  void (async () => {
    let backendMode = ''
    try {
      backendMode = await authApi.getAuthMode()
    } catch {
      console.debug('[auth_mode 自检] 后端 /auth/mode 不可达，跳过比对')
      return
    }
    if (!backendMode) {
      console.debug('[auth_mode 自检] 后端未报告 auth_mode（旧后端），跳过比对')
      return
    }
    const result = checkAuthMode(getEffectiveAuthMode(), backendMode)
    if (!result.mismatch) return
    console.warn(
      `[auth_mode 自检] 前后端认证模式错位：前端 VITE_AUTH_MODE="${result.frontendMode}"，` +
        `后端 AUTH_MODE="${result.backendMode}"。` +
        '请使两侧一致（本地 dev server 以进程 env 注入 VITE_AUTH_MODE——' +
        '.env.development 优先级高于 .env.local，只改 .env.local 会被静默覆盖，' +
        '且 dev server 不热加载 env 需重启；生产构建显式注入 VITE_AUTH_MODE），' +
        '详见 docs/oauth.md §6.1。',
    )
    showAuthModeMismatchBanner(result)
  })()
}
