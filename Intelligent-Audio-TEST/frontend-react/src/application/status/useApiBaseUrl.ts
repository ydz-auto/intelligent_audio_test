import { useEffect, useState } from 'react'

import {
  fetchSiteStatus,
  type SiteStatusDto,
} from '@/infrastructure/api/statusApi'

/**
 * API 根地址解析纯函数（07_文档.md §7 application/status/useApiBaseUrl.ts）。
 * 只消费 camelCase DTO（status.apiBaseUrl || status.serverAddress），
 * 校验协议/凭据，非法或缺失回退站点根 + `/api`（平台 API 根，Vue
 * API_CONFIG.baseUrl='/api/v1' 实测），去尾部 `/` 与 `/v1`。
 * 展开口径：{{API_BASE_URL}} = `{apiBaseUrl}/v1` = 站点根 + `/api/v1`（§2 映射表）。
 */
export function resolveApiBaseUrl(status: SiteStatusDto): string {
  const fallback = `${window.location.origin}/api`
  const candidate = status.apiBaseUrl || status.serverAddress
  if (typeof candidate !== 'string' || !candidate.trim()) return fallback

  try {
    const address = new URL(candidate.trim())
    if (
      (address.protocol !== 'https:' && address.protocol !== 'http:') ||
      address.username ||
      address.password
    ) {
      return fallback
    }
    address.search = ''
    address.hash = ''
    // Examples embed this public address in shell strings as well as URLs.
    address.pathname = address.pathname.replaceAll("'", '%27')
    return address.toString().replace(/\/+$/, '').replace(/\/v1$/, '')
  } catch {
    return fallback
  }
}

/**
 * API 根地址 hook：占位符 {{API_BASE_URL}} 依据。
 * 平台现无 /api/status 端点，mock 返回 null 字段 → 回退站点根 + `/api`；
 * 预留 status 字段覆盖（对齐 newAPI useApiBaseUrl 降级逻辑）。
 */
export function useApiBaseUrl(): string {
  const [apiBaseUrl, setApiBaseUrl] = useState(() =>
    resolveApiBaseUrl({ apiBaseUrl: null, serverAddress: null })
  )

  useEffect(() => {
    let cancelled = false
    void fetchSiteStatus().then((status) => {
      if (cancelled) return
      setApiBaseUrl(resolveApiBaseUrl(status))
    })
    return () => {
      cancelled = true
    }
  }, [])

  return apiBaseUrl
}
