/**
 * 端点级密钥池拆分/提取（infrastructure/adapters 层共享；INT-1437 密钥池）。
 * 交互形态（负责人裁定 2026-10-22，设计文档 §3.10.5）：端点行内多行 textarea，
 * 每行一个 key、可整段粘贴自动拆行；保存时 adapter 拆行转 `api_keys` 落库。
 * 留空不显式传 `api_keys`（后端按 endpoint URL 匹配保留既有池，不整块覆盖清空）。
 */

/** textarea 草稿 → 密钥数组：按 `\r?\n` 拆分 → trim → 过滤空行 */
export function splitApiKeysText(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
}

/** 端点级密钥池提取（写侧）：textarea 草稿（apiKeysText）优先，回退显式 apiKeys 数组；空/留空返回 [] */
export function extractEndpointApiKeys(ep: {
  apiKeysText?: string
  apiKeys?: string[]
}): string[] {
  const source = ep.apiKeysText ?? ep.apiKeys
  if (Array.isArray(source)) {
    return source.map((key) => String(key).trim()).filter(Boolean)
  }
  if (typeof source === 'string' && source.trim()) {
    return splitApiKeysText(source)
  }
  return []
}
