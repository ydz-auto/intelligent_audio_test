/**
 * 网络代理配置校验（INT-839，前后端双校验，与后端同规则）
 *
 * 规则：
 * - proxyType 非空 → proxyUrl 必填且必须带 user:pass@ 前缀（格式 user:pass@host:port，不含 scheme）；
 * - proxyType 为空 → proxyUrl 必须为空（不使用代理）。
 *
 * 返回 null = 合法；否则返回错误文案。APIEditModal 与 CRUDFormModal（真实 API 编辑/新增弹窗）
 * 共用本规则，保证两处口径一致。
 */
export function validateProxy(proxyType: unknown, proxyUrl: unknown): string | null {
  const type = proxyType ? String(proxyType) : ''
  const url = typeof proxyUrl === 'string' ? proxyUrl.trim() : ''

  if (type) {
    if (!url) {
      return '已选择代理类型时，代理地址必填（格式 user:pass@host:port）'
    }
    if (!/^[^:@]+:[^@]+@\S+$/.test(url)) {
      return '代理地址必须以 user:pass@ 开头（格式 user:pass@host:port）'
    }
  } else if (url) {
    return '未选择代理类型时，代理地址必须为空'
  }
  return null
}
