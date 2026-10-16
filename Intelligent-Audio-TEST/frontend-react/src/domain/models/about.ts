/**
 * 关于页领域模型（domain 层）。
 * 服务状态数据形态对照 api_gateway/app.py:175-186（GET /health：status/service/version/database）
 * 与 auth_service/app.py:79-84（GET /health：status/service），后续接线时字段不返工（红线④）。
 */

/** 状态徽章三态：正常（success 软底）/ 异常（destructive 软底）/ 检测中（muted） */
export type ServiceTone = 'success' | 'destructive' | 'muted'

/** 版本与服务状态卡行数据 */
export type ServiceStatusLine = {
  label: string
  /** 展示值（平台版本号 / 服务名 / 库名）；取不到时由上游填「—」 */
  value: string
  tone: ServiceTone
  /** 徽章文案：正常 / 异常 / 检测中 */
  badge: string
}

/** API 网关 GET /health 响应（api_gateway/app.py:175-186 实测形态） */
export type GatewayHealthResponse = {
  status: 'ok' | string
  service: string
  version: string
  database?: string | null
}

/** 认证服务 GET /health 响应（auth_service/app.py:79-84 实测形态） */
export type AuthHealthResponse = {
  status: 'ok' | string
  service: string
}
