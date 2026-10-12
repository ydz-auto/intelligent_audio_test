/**
 * 认证模式启动自检 —— 纯比对逻辑（INT-180）
 *
 * 目标：让"后端改 AUTH_MODE、前端构建期 VITE_AUTH_MODE 无感知"的静默
 * 失配在启动时自曝。比对为提示型：不一致不阻塞启动与登录流程。
 *
 * 网络失败 / 后端未回值（旧后端无 /auth/mode）视为"不可比"→ 静默，
 * 避免对无法验证的场景误报。
 */
import { AUTH_MODE_VALUES } from '../enums'

/** 自检结果（camelCase Domain；两侧当前值供提示展示） */
export interface AuthModeCheckResult {
  /** true = 两侧模式错位，需要提示 */
  mismatch: boolean
  /** 前端本地生效值（VITE_AUTH_MODE，未注入回退 off） */
  frontendMode: string
  /** 后端报告值（GET /auth/mode 的 auth_mode） */
  backendMode: string
  /** 后端值是否在合法枚举集合内（false 时提示额外指向取值合法性） */
  backendModeKnown: boolean
}

/** 比对前端本地生效模式与后端报告模式；backendMode 为空 = 不可比 → 静默 */
export function checkAuthMode(frontendMode: string, backendMode: string): AuthModeCheckResult {
  const backend = (backendMode ?? '').trim()
  const backendModeKnown = (AUTH_MODE_VALUES as readonly string[]).includes(backend)
  return {
    mismatch: backend !== '' && frontendMode !== backend,
    frontendMode,
    backendMode: backend,
    backendModeKnown,
  }
}
