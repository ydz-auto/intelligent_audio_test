import type {
  AuthHealthResponse,
  GatewayHealthResponse,
} from '@/domain/models/about'

/**
 * 服务状态 /health API 桩（infrastructure 层，红线④：mock 常量）。
 * 数据形态对照 api_gateway/app.py:175-186（status/service/version/database，
 * 根路径公开无权限）+ auth_service/app.py:79-84（status/service）。
 */

/** mock：API 网关 /health（version 取 Config.PLATFORM_VERSION，库名取 database_name_of） */
export const MOCK_GATEWAY_HEALTH: GatewayHealthResponse = {
  status: 'ok',
  service: 'api_gateway',
  version: 'V9.7.31',
  database: 'intelligent_audio_test',
}

/** mock：认证服务 /health（独立服务端口 5009；勿用 5001——5001 是 task_service） */
export const MOCK_AUTH_HEALTH: AuthHealthResponse = {
  status: 'ok',
  service: 'auth_service',
}

/**
 * TODO(API 接线): GET /health（api_gateway 根路径；nginx 只反代 /api/、/socket.io/、/ws，
 * 根路径 /health 未反代——06_关于.md §3.1.1 实施注意：需补 nginx location /health 反代
 * 或后端落 /api/v1/system/health 汇总端点；未落前状态卡降级「检测中」）。
 */
export async function fetchGatewayHealth(): Promise<GatewayHealthResponse> {
  return MOCK_GATEWAY_HEALTH
}

/**
 * TODO(API 接线): GET /health（auth_service 独立服务端口 5009——
 * docker-compose.yml:409-420、shared/config/service_ports.py:12、auth_service/config/config.py:15）。
 */
export async function fetchAuthHealth(): Promise<AuthHealthResponse> {
  return MOCK_AUTH_HEALTH
}
