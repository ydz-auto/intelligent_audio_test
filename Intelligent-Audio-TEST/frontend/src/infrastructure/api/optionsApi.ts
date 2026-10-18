/**
 * 系统选项 KV API —— GET/PUT /api/option/
 *
 * 后端 option_bp 挂根前缀 `/api`（非 `/api/v1`，见 api_gateway/app.py INT-620），
 * 与前端 API 基址 `/api/v1` 不同前缀；故以 `/../option/` 让 URL 归一化为 `/api/option/`
 * （浏览器 fetch / Node fetch 均按 URL 规范合并 `..`，dev/prod 一致）。
 */
import { request } from '../http/client'
import type { SystemOptions } from '../../domain/model/system'

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
