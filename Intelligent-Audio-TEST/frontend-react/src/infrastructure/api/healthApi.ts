import type { SystemHealthResponse } from '@/domain/models/about'

import { apiClient } from './client'

/**
 * 服务状态健康检查 API（infrastructure 层）。
 * 数据形态对照 api_gateway/app.py:175-186（GET /health：status/service/version/database，
 * 根路径公开无权限）+ auth_service/app.py:79-84（GET /health：status/service）。
 *
 * 真实请求经统一 client.ts（baseURL /api/v1 → api_gateway，dev 走 rsbuild 代理），
 * snake_case↔camelCase 仅限本层——本端点返回字段与领域模型同名，无需转换。
 */

/**
 * GET /api/v1/system/health（api_gateway 汇总端点：网关 + 认证服务健康聚合）。
 * 待 INT-766（FEAT 卡）：后端未落该端点 → 请求失败（404）→ 状态卡按 06_关于.md
 * §3.1.1 实施注意降级「检测中」（值「—」+ 徽章「检测中」+ 整卡 Alert），不显示 mock「正常」。
 * 公开健康数据，skipAuthRedirect：关于页为公开路由，避免 401 触发全局登出跳转。
 */
export async function fetchSystemHealth(): Promise<SystemHealthResponse> {
  return apiClient.get<SystemHealthResponse>('/system/health', {
    skipAuthRedirect: true,
  })
}
