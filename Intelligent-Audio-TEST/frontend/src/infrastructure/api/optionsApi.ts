/**
 * 系统选项 API（INT-620 对齐 newAPI `/api/option/` KV 通道）
 *
 * - GET /api/option/：全量 KV 拉取（领域默认基线 ∪ 库中已存覆盖）
 * - PUT /api/option/：单键写入 `{ key, value }`
 *
 * 注意：option 路由为**根级挂载无 /api/v1 前缀**（api_gateway/app.py INT-620），
 * 而 request client 默认 baseUrl 为 /api/v1，故此处构造显式绝对 URL 绕过前缀。
 * 权限码：option:read / option:write。
 */
import { request } from '../http/client'

/** 构造 /api/option/ 显式绝对 URL（浏览器与 Electron 主进程均可用） */
function optionBaseUrl(): string {
  const base = typeof window !== 'undefined' && window.location?.origin
    ? window.location.origin
    : 'http://localhost'
  return `${base}/api/option/`
}

/** 全量系统选项 KV（GET /api/option/） */
export async function getSystemOptions(): Promise<Record<string, unknown>> {
  const data = await request<Record<string, unknown>>('GET', optionBaseUrl())
  return data || {}
}

/** 读取站点公告（site.notice；公告页签数据源） */
export async function getSiteNotice(): Promise<string> {
  try {
    const options = await getSystemOptions()
    return typeof options['site.notice'] === 'string' ? options['site.notice'] as string : ''
  } catch {
    return ''
  }
}

/** 读取站点名称（site.name；公共站头/页脚品牌兜底） */
export async function getSiteName(): Promise<string> {
  try {
    const options = await getSystemOptions()
    return typeof options['site.name'] === 'string' ? options['site.name'] as string : ''
  } catch {
    return ''
  }
}

/** 单键写入系统选项（PUT /api/option/ { key, value }；option:write） */
export async function putSystemOption(key: string, value: unknown): Promise<void> {
  await request('PUT', optionBaseUrl(), { key, value })
}
