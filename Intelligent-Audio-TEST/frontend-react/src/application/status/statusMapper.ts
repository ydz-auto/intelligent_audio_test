import type {
  AuthHealthResponse,
  GatewayHealthResponse,
  ServiceStatusLine,
  ServiceTone,
} from '@/domain/models/about'

/**
 * 健康检查响应 → 状态卡行数据（application 层纯函数，无副作用）。
 * 口径（06_关于.md §3.1.1/§4.4）：
 * - ok → 正常（success 软底）；非 ok → 异常（destructive 软底）；请求失败 → 检测中（muted）
 * - 平台版本统一取 /health version；失败 → 值「—」+ 徽章「检测中」
 * - 网关 /health 整卡请求失败 → 全卡降级「检测中」+ 提示条（§4.4），不阻断正文
 */

const NORMAL_BADGE = '正常'
const ABNORMAL_BADGE = '异常'
const DETECTING_BADGE = '检测中'
const MISSING_VALUE = '—'

function toneOf(status: string | undefined, failed: boolean): ServiceTone {
  if (failed || status === undefined) return 'muted'
  return status === 'ok' ? 'success' : 'destructive'
}

function badgeOf(tone: ServiceTone): string {
  if (tone === 'success') return NORMAL_BADGE
  if (tone === 'destructive') return ABNORMAL_BADGE
  return DETECTING_BADGE
}

export type ServiceHealthState = {
  version: string
  versionTone: ServiceTone
  gateway: ServiceStatusLine
  auth: ServiceStatusLine
  database: string | null
  /** 网关 /health 整卡失败 → 提示条（§4.4「服务状态检测失败」） */
  anyFailure: boolean
}

export function toServiceHealthState(params: {
  gateway?: GatewayHealthResponse
  auth?: AuthHealthResponse
  gatewayFailed: boolean
  authFailed: boolean
}): ServiceHealthState {
  const gatewayFailed = params.gatewayFailed || !params.gateway
  const authFailed = params.authFailed || !params.auth

  // 网关 /health 失败 → 全卡降级（版本「—」+ 三徽章「检测中」+ 提示条，§4.4）
  const versionTone = toneOf(params.gateway?.status, gatewayFailed)
  const gatewayTone = toneOf(params.gateway?.status, gatewayFailed)
  const authTone = toneOf(params.auth?.status, gatewayFailed || authFailed)

  return {
    version: gatewayFailed ? MISSING_VALUE : (params.gateway?.version ?? MISSING_VALUE),
    versionTone,
    gateway: {
      label: 'API 网关',
      value: params.gateway?.service ?? MISSING_VALUE,
      tone: gatewayTone,
      badge: badgeOf(gatewayTone),
    },
    auth: {
      label: '认证服务',
      value: params.auth?.service ?? MISSING_VALUE,
      tone: authTone,
      badge: badgeOf(authTone),
    },
    database: gatewayFailed ? null : (params.gateway?.database ?? null),
    anyFailure: gatewayFailed,
  }
}
