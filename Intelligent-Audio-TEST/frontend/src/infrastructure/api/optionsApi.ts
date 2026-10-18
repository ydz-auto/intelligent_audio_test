/**
 * 系统选项 KV API —— GET/PUT /api/option/
 *
 * 后端 option_bp 挂根前缀 `/api`（非 `/api/v1`，见 api_gateway/app.py INT-620），
 * 与前端 API 基址 `/api/v1` 不同前缀；故以 `/../option/` 让 URL 归一化为 `/api/option/`
 * （浏览器 fetch / Node fetch 均按 URL 规范合并 `..`，dev/prod 一致）。
 *
 * 双形态导出（INT-808 集成合并）：
 * - `optionsApi` 对象（INT-743 配置运维，optionsPort 直通封装，系统设置六域用）；
 * - 函数式 `getSystemOptions/getSiteNotice/getSiteName/putSystemOption`（INT-620 壳层，
 *   SystemBrand/NotificationPopover 等布局组件用）。
 */
import { request } from '../http/client'
import type { SystemOptions } from '../../domain/model/system'

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

export const optionsApi = {
  /** 全量 KV 拉取（领域默认基线 ∪ 库中已存覆盖） */
  async getAll(): Promise<SystemOptions> {
    return request<SystemOptions>('GET', '/../option/')
  },

  /** 单键写入 */
  async update(key: string, value: string | number | boolean | string[]): Promise<string> {
    return request<string>('PUT', '/../option/', { key, value })
  },
}
