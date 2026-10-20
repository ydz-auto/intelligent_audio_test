/**
 * 网络代理配置校验（INT-839，前后端双校验，与后端同规则）
 *
 * 规则镜像后端 api_test_service/infrastructure/adapters/proxy_utils.py validate_proxy：
 * - proxyType 非空 → 必须是 http/https/socks5/socks5h 之一；
 *   proxyUrl 必填且带 user:pass@ 认证段，格式 [user:pass@]host[:port]，
 *   不含 scheme 前缀；端口若存在必须为数字（镜像 split_proxy_url 的 urlparse 校验）。
 * - proxyType 为空 → proxyUrl 必须为空（不使用代理）。
 *
 * 返回 null = 合法；否则返回错误文案。APIEditModal 与 CRUDFormModal（真实 API 编辑/新增弹窗）
 * 共用本规则，保证两处口径一致。
 */
import { ProxyType } from '../domain/enums'

/** 合法代理类型白名单（镜像后端 PROXY_TYPES，值 = domain/enums.ts ProxyType 原值） */
const PROXY_TYPES = Object.values(ProxyType)

/** 镜像后端 split_proxy_url：分解 [user:pass@]host[:port] → host / 端口串 / user / password */
function splitProxyUrl(raw: string): { host: string; portStr: string; user: string; password: string } {
  const atIdx = raw.lastIndexOf('@')
  const auth = atIdx >= 0 ? raw.slice(0, atIdx) : ''
  const hostPart = atIdx >= 0 ? raw.slice(atIdx + 1) : raw

  let host = ''
  let portStr = ''
  if (hostPart.startsWith('[')) {
    // IPv6 字面量（[::1] 或 [::1]:port）：闭合括号后才是端口段
    const close = hostPart.indexOf(']')
    if (close >= 0) {
      host = hostPart.slice(0, close + 1)
      const rest = hostPart.slice(close + 1)
      if (rest.startsWith(':')) {
        portStr = rest.slice(1)
      } else if (rest) {
        host = '' // 闭合括号后存在非端口字符 → 非法地址（走「必须为 host:port 格式」）
      }
    }
  } else {
    const colonIdx = hostPart.lastIndexOf(':')
    if (colonIdx >= 0) {
      host = hostPart.slice(0, colonIdx)
      portStr = hostPart.slice(colonIdx + 1)
    } else {
      host = hostPart
    }
  }

  const authColonIdx = auth.indexOf(':')
  const user = authColonIdx >= 0 ? auth.slice(0, authColonIdx) : ''
  const password = authColonIdx >= 0 ? auth.slice(authColonIdx + 1) : ''
  return { host, portStr, user, password }
}

export function validateProxy(proxyType: unknown, proxyUrl: unknown): string | null {
  const type = proxyType ? String(proxyType).trim() : ''
  const url = typeof proxyUrl === 'string' ? proxyUrl.trim() : ''

  // proxyType 为空 → proxyUrl 必须为空（不使用代理）
  if (!type) {
    if (url) {
      return '未选择代理类型时，代理地址必须为空'
    }
    return null
  }

  // proxyType 必须是合法代理类型白名单
  if (!(PROXY_TYPES as readonly string[]).includes(type)) {
    return `非法的代理类型 (proxyType): ${type}，仅支持 ${PROXY_TYPES.join(' / ')}`
  }

  // proxyType 非空 → proxyUrl 必填
  if (!url) {
    return '已选择代理类型时，代理地址必填（格式 user:pass@host:port）'
  }

  // 契约规定 proxyUrl 不含 scheme 前缀，带 scheme 会在执行侧拼出双重 scheme → 源头拒绝
  if (url.includes('://')) {
    return '代理地址不应包含 scheme 前缀（去掉 http:// 等），格式 user:pass@host:port'
  }

  // 镜像 split_proxy_url：端口若存在必须为数字（非法端口后端 urlparse 抛 ValueError）
  const { host, portStr, user, password } = splitProxyUrl(url)
  if (!host) {
    return '无效的代理地址，必须为 user:pass@host:port 格式'
  }
  if (portStr && !/^\d+$/.test(portStr)) {
    return '无效的代理地址：端口必须为数字，格式 user:pass@host:port'
  }
  if (!user || !password) {
    return '代理地址必须带 user:pass@ 认证段'
  }
  return null
}
