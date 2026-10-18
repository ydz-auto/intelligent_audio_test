// -*- coding: utf-8 -*-
/**
 * 站点健康状态 API —— INT-745（关于页版本与服务状态卡）
 *
 * `/health` 是 api_gateway 根路径公开端点（无 /api/v1 前缀；nginx 未反代，
 * dev 经 Vite `/health` 代理规则转发到后端）。本模块直接用 origin + /health，
 * 不走 client 的 /api/v1 前缀；请求失败由调用方降级「检测中」。
 */
import { request } from '../http/client'
import type { HealthStatus } from '../../domain/model/system'

export const healthApi = {
  async getHealth(): Promise<HealthStatus> {
    return request<HealthStatus>('GET', `${window.location.origin}/health`)
  },
}
